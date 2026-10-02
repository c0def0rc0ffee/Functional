"""
<summary>
Build both release zips for skin.functional.
</summary>
<remarks>
USE THIS to build. Never zip the skin by hand or with PowerShell's
Compress-Archive, which emits zip entries with backslash separators and
(more importantly) no explicit directory entries: Linux Kodi (LibreELEC,
Bazzite, every non-Windows build) refuses to install zips that lack
directory records, even though Windows Kodi accepts them silently.

This script writes portable zips:
  - forward-slash path separators
  - explicit directory entries for every folder
  - members in sorted order, files stored 0644 and folders 0755
  - DEFLATE compression
  - written to a part file, verified, then renamed into place
  - reads the version straight out of skin.functional/addon.xml so the
    output filenames always match the manifest (addon.xml is the version
    source of truth, because Kodi requires it there, so no separate VERSION file)

Usage:
    python3 build_zip.py
    python3 build_zip.py --news     after a version bump: copy that version's
                                    CHANGELOG.md section into addon.xml's news
                                    element and stop
    python3 build_zip.py --force    rebuild an already-released version even
                                    if the content has changed (normally that
                                    aborts: bump the addon.xml version instead)

Output:
    Skin Dist/skin.functional-<version>.zip      Kodi-installable skin only
    Skin Git/skin.functional-<version>-src.zip   full source snapshot: the
                                                 tree as pushed to GitHub, minus
                                                 the local-only release tooling
                                                 and PROJECT_NOTES.md

Both zips are also copied to every folder listed in release-mirror.conf, if
that file exists. See mirror_targets() for the format. Without the file the
build simply produces the two zips, so a fresh clone works unchanged.
</remarks>
"""

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "skin.functional")
DIST = os.path.join(REPO, "Skin Dist")
GIT = os.path.join(REPO, "Skin Git")

# Directory names that must never ship anywhere. @eaDir is Synology NAS
# indexing metadata, whose @SynoEAStream entries crash Kodi's zip
# extraction on install (seen on Kodi 21 / Linux).
JUNK_DIRS = ("__pycache__", ".git", "@eaDir", "#recycle", ".svn")
JUNK_FILES = ("Thumbs.db", "desktop.ini", ".DS_Store")
# Compiled Python left outside a __pycache__ dir (Python 2 leftovers, or a
# tool writing next to the source) is build junk, never shippable content.
JUNK_FILE_GLOBS = ("*.pyc", "*.pyo")
# Every zip is written under its final name plus this suffix, verified, and
# only then renamed into place.
PART_SUFFIX = ".part"

# Extra exclusions for the source zip: the output folders themselves,
# session data, and archive/temp/log files anywhere in the tree.
SRC_ZIP_EXCLUDE_DIRS = ("Skin Dist", "Skin Git", "$RECYCLE.BIN")
# The one dot directory git is told to keep (see the ignore file); the
# source zip keeps it too so it still equals the tracked file list.
SRC_KEEP_DOT_DIRS = (".github",)
# Every other dot directory is skipped, so local editor and tooling state
# can never reach a published zip. The mirror config names a machine on a
# private network, so it stays out of the snapshot too.
# The release tooling is local only. publish.conf and release-mirror.conf name
# a machine on a private network, and the rest is of no use to anyone reading
# the source, so none of it belongs in a snapshot that may be handed out.
SRC_ZIP_EXCLUDE_GLOBS = ("*.zip", "*.7z", "*.tmp", "*.log",
                         "*.pyc", "*.pyo",
                         "release-mirror.conf", "publish.conf",
                         "publish-github.sh", "push-source.sh",
                         ".publish-allow", "GITHUB-RELEASE-GUIDE.md",
                         "Github repository", "PROJECT_NOTES.md")
# Editor and tooling state is excluded too, but its filename patterns are NOT
# written here: this file is tracked and ships inside the source zip, and a
# published file must not carry those names. They live in .git/info/exclude,
# which is local to this clone and never published, and are read back out by
# git_ignored_globs() below. A missing or empty exclude file stops the build
# before anything is written (name_rules() is the first thing main() calls),
# because packaging without it is the whole risk.


GIT_EXCLUDE_FILE = os.path.join(".git", "info", "exclude")


def ignore_file_lines():
    """
    <summary>
    Every pattern line from the ignore files, with the local exclude file
    required: a build without it stops rather than packaging unprotected.
    </summary>
    <returns>
    list of stripped, non-comment, non-blank lines from .gitignore (when
    present) and .git/info/exclude, in that order.
    </returns>
    <exception cref="SystemExit">
    When .git/info/exclude is missing or holds no pattern at all.
    </exception>
    <remarks>
    .gitignore is optional here: it ships, so it can only ever hold
    patterns that are safe to publish. .git/info/exclude is not optional.
    It is the one place the editor and tooling filenames are allowed to
    live, so a build that cannot read it would pack them into the source
    zip without a word. Until 22/09/2026 a missing file fell back to "no
    patterns" so that a snapshot build still worked, and verify_zip() then
    tested the zip against that same empty set, which is exactly the case
    the check exists for. Failing closed here means the after-build check
    always has something real to test against, and matches what
    publish-github.sh already does before staging.
    </remarks>
    """
    lines = []
    exclude_count = 0
    for rel in (".gitignore", GIT_EXCLUDE_FILE):
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            if rel == GIT_EXCLUDE_FILE:
                sys.exit(f"ABORTED: {rel} is missing, so the editor and "
                         "tooling exclusions are gone. Not building.")
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
                if rel == GIT_EXCLUDE_FILE:
                    exclude_count += 1
    if exclude_count == 0:
        sys.exit(f"ABORTED: {GIT_EXCLUDE_FILE} holds no patterns, so the "
                 "editor and tooling exclusions are gone. Not building.")
    return lines


def git_ignored_root_files():
    """
    <summary>
    Root level filenames that git is told to ignore, read at build time.
    </summary>
    <returns>tuple of filenames.</returns>
    <exception cref="SystemExit">
    Passed up from ignore_file_lines() when .git/info/exclude is missing
    or empty.
    </exception>
    <remarks>
    The source snapshot is meant to match `git ls-files` exactly, so whatever
    git ignores has to be left out of the zip as well. Reading the names out
    of the ignore files rather than listing them above keeps the list in step
    on its own, and keeps local only filenames from being written into this
    file, which does ship.

    Only root anchored plain filenames are taken ("/Notes.md"). Directory
    rules, wildcards and negations are left to the existing globs, so a
    pattern here can never widen the exclusion beyond one named file.
    </remarks>
    """
    names = []
    for line in ignore_file_lines():
        if (line.startswith("!") or not line.startswith("/")
                or line.endswith("/")):
            continue
        name = line[1:]
        if name and "/" not in name and "*" not in name:
            names.append(name)
    return tuple(names)


def git_ignored_globs():
    """
    <summary>
    Unanchored filename patterns git is told to ignore, read at build time.
    </summary>
    <returns>tuple of fnmatch patterns.</returns>
    <exception cref="SystemExit">
    Passed up from ignore_file_lines() when .git/info/exclude is missing
    or empty.
    </exception>
    <remarks>
    Companion to git_ignored_root_files(). That one takes only root anchored
    plain filenames, which is deliberately narrow; this one takes the
    unanchored filename patterns ("*.bak", "id_rsa*"), which match a bare
    filename at ANY depth, exactly like the explicit globs above.

    The point of both is the same: the names stay in the ignore files instead
    of being typed into this one, because this file ships. A pattern with a
    slash in it is skipped, since directory rules are already handled by the
    walker (every dot directory is dropped) and a path shaped pattern would
    not match the bare filename these globs are tested against anyway.
    </remarks>
    """
    patterns = []
    for line in ignore_file_lines():
        if line.startswith(("!", "/")) or line.endswith("/") or "/" in line:
            continue
        patterns.append(line)
    return tuple(patterns)


def git_ignored_dir_rules():
    """
    <summary>
    Folder patterns git is told to ignore, and the ones it is told to keep.
    </summary>
    <returns>(ignored, kept): two tuples of fnmatch patterns, each tested against one path component.</returns>
    <exception cref="SystemExit">
    Passed up from ignore_file_lines() when .git/info/exclude is missing
    or empty.
    </exception>
    <remarks>
    Third companion to git_ignored_root_files() and git_ignored_globs(). A
    rule ending in a slash names a folder. The slash that anchors one to the
    root is dropped, so a folder rule is matched at any depth here, which is
    wider than git and errs on the safe side. A negated folder rule is
    returned as kept, so the one dot folder git tracks is not treated as
    forbidden. Rules with a slash in the middle are left out, as before.
    </remarks>
    """
    ignored, kept = [], []
    for line in ignore_file_lines():
        if not line.endswith("/"):
            continue
        negated = line.startswith("!")
        core = line.lstrip("!").strip("/")
        if not core or "/" in core:
            continue
        (kept if negated else ignored).append(core)
    return tuple(ignored), tuple(kept)


def name_rules():
    """
    <summary>
    Every filename and folder pattern no zip may contain, read from the
    ignore files in one go.
    </summary>
    <returns>(file globs, folder globs, kept folder globs).</returns>
    <exception cref="SystemExit">
    Passed up from ignore_file_lines() when .git/info/exclude is missing
    or empty.
    </exception>
    <remarks>
    main() calls this before anything is written, so a build without the
    local exclude file stops with no zip on disk. Until 02/10/2026 the file
    was first read after the installable zip had been written, and that zip
    was never tested against the patterns at all: a local only note dropped
    inside the skin folder would have shipped to every device. The same
    rules now judge the installable zip, the source zip and the repository
    add-on zip. They carry the secret filename patterns too, because those
    are ordinary lines of the tracked ignore file.
    </remarks>
    """
    ignored, kept = git_ignored_dir_rules()
    files = SRC_ZIP_EXCLUDE_GLOBS + git_ignored_root_files() + git_ignored_globs()
    return files, ignored + JUNK_DIRS, kept


def forbidden_members(names, rules):
    """
    <summary>
    The member names a set of name rules forbids.
    </summary>
    <param name="names">Zip member names, forward slashes, folders ending in a slash.</param>
    <param name="rules">The triple from name_rules().</param>
    <returns>List of offending names, in the order given.</returns>
    <remarks>
    A file is judged by its bare name. Every folder on the way to it is
    judged too, against the folder rules and against the file rules, since
    an ignore pattern without a slash matches a folder as readily as a file.
    </remarks>
    """
    file_globs, dir_globs, kept = rules
    bad = []
    for name in names:
        parts = [p for p in name.split("/") if p]
        folders = parts if name.endswith("/") else parts[:-1]
        hit = (not name.endswith("/") and parts
               and any(fnmatch.fnmatch(parts[-1], g) for g in file_globs))
        for folder in folders:
            if any(fnmatch.fnmatch(folder, k) for k in kept):
                continue
            if any(fnmatch.fnmatch(folder, g) for g in dir_globs + file_globs):
                hit = True
        if hit:
            bad.append(name)
    return bad


def git_tracked_files():
    """
    <summary>
    The files git tracks, as git lists them.
    </summary>
    <returns>Sorted list of paths relative to the repo root.</returns>
    <exception cref="SystemExit">When git cannot list the tree.</exception>
    <remarks>
    The source zip is meant to be exactly this list. No list means no way
    to prove it, so that stops the build too.
    </remarks>
    """
    try:
        out = subprocess.run(["git", "-C", REPO, "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"ABORTED: git ls-files could not run ({exc}), so the source "
                 "zip cannot be checked against the tracked files. Not building.")
    return sorted(p for p in out.decode("utf-8", "surrogateescape").split("\0") if p)


def refuse_untracked(names, what):
    """
    <summary>
    Stop the build unless a list of files equals what git tracks.
    </summary>
    <param name="names">File paths as they would sit, or do sit, in the source zip.</param>
    <param name="what">How to name the list in the message.</param>
    <exception cref="SystemExit">On any difference, each side listed.</exception>
    <remarks>
    The source zip is built by walking the working tree, so without this a
    stray file nobody added (a scratch note, a sync conflict copy) is packed
    and, at publish time, pushed. A tracked file the walk leaves out shows
    up the same way.
    </remarks>
    """
    have, want = set(names), set(git_tracked_files())
    if have == want:
        return
    extra, missing = sorted(have - want), sorted(want - have)
    sys.exit(f"ABORTED: {what} does not match git ls-files.\n"
             f"  not tracked by git (git add it, or exclude it): {extra}\n"
             f"  tracked but not packed: {missing}")


MIRROR_CONF = os.path.join(REPO, "release-mirror.conf")


def read_version():
    """
    <summary>
    Read the skin version from addon.xml.
    </summary>
    <returns>The version attribute of the addon element, not the XML declaration's.</returns>
    <exception cref="SystemExit">When the attribute cannot be found.</exception>
    """
    addon_xml = os.path.join(SRC, "addon.xml")
    with open(addon_xml, encoding="utf-8-sig") as fh:
        text = fh.read()
    # Match the addon-tag's version attribute specifically, not the XML
    # declaration's version="1.0" on the first line.
    m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', text)
    if not m:
        sys.exit("Could not find <addon version=\"…\"> in addon.xml")
    return m.group(1)


CHANGELOG = os.path.join(REPO, "CHANGELOG.md")
NEWS_MAX_LINES = 20


def names_version(heading, version):
    """
    <summary>
    Whether a changelog heading names exactly this version.
    </summary>
    <param name="heading">One heading line, hashes included.</param>
    <param name="version">Version string exactly as in addon.xml.</param>
    <returns>True only for a whole version: 0.12.1 does not match a heading for 0.12.16, 10.12.1 or 0.12.1-rc1.</returns>
    <remarks>
    Until 02/10/2026 this was a substring test, so building 0.12.1 would
    have taken the notes of the newest 0.12.1x release above it. The publish
    script picks the release notes with the same rule.
    </remarks>
    """
    return re.search(r"(?<![\d.])" + re.escape(version) + r"(?!\d|\.\d|[-~+]\w)",
                     heading) is not None


def changelog_section(version):
    """
    <summary>
    The bullet lines of one version's section in CHANGELOG.md, as plain
    text lines ready for the addon.xml news element.
    </summary>
    <param name="version">Version string exactly as in addon.xml.</param>
    <returns>List of lines, empty when the file or the section is missing.</returns>
    <remarks>
    A section starts at a heading (one to three hashes) that names exactly
    this version, see names_version(), and runs to the next heading of the
    same or a higher level, the same rule publish-github.sh uses to pick the
    release notes, so the news and the notes can never disagree. A deeper
    heading inside the section (a "###" under a "##") does not end it; it is
    kept as a plain line. Bullet markers are dropped and wrapped bullet lines
    rejoined; anything else in the section is kept as it is. Capped at
    NEWS_MAX_LINES, since Kodi's add-on info screen is not the place for a
    long read.
    </remarks>
    """
    if not os.path.isfile(CHANGELOG):
        return []
    lines, level = [], 0
    with open(CHANGELOG, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            heading = re.match(r"^(#{1,6}) ", line)
            if heading:
                depth = len(heading.group(1))
                if level:
                    if depth <= level:
                        break
                    lines.append(line[depth:].strip())
                elif depth <= 3 and names_version(line, version):
                    level = depth
                continue
            if not level:
                continue
            if re.match(r"^\s*[-*] ", line):
                lines.append(re.sub(r"^\s*[-*] ", "", line).strip())
            elif line.startswith("  ") and lines:
                lines[-1] += " " + line.strip()
            elif line.strip():
                lines.append(line.strip())
    return lines[:NEWS_MAX_LINES]


def news_in(text):
    """
    <summary>
    The text of the news element in an addon.xml, read with a real XML parser.
    </summary>
    <param name="text">The whole addon.xml as text.</param>
    <returns>The element's text, or None when there is no news element.</returns>
    <exception cref="SystemExit">When the manifest is not well formed or holds more than one news element.</exception>
    <remarks>
    Parsing rather than pattern matching is what makes sync_news() work
    whatever the indentation: the comparison is of the text Kodi will read,
    not of how the line happens to be laid out.
    </remarks>
    """
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        sys.exit(f"ABORTED: skin.functional/addon.xml is not well formed: {exc}")
    found = root.findall(".//news")
    if len(found) > 1:
        sys.exit("ABORTED: skin.functional/addon.xml holds more than one <news> "
                 "element. Leave one, on a line of its own.")
    return (found[0].text or "") if found else None


def sync_news(version, write):
    """
    <summary>
    Keep addon.xml's news element equal to the changelog section for the
    version being built.
    </summary>
    <param name="version">Version string from addon.xml.</param>
    <param name="write">True rewrites addon.xml; False only compares.</param>
    <returns>True when addon.xml already matched, or was just rewritten.</returns>
    <exception cref="SystemExit">In check mode, when the two disagree: run
    the news flag and commit addon.xml. In write mode, when the element
    cannot be placed or the rewritten manifest does not read back as
    expected; nothing is written in that case. A version with no changelog
    section is allowed and carries no news.</exception>
    <remarks>
    The element lives inside the metadata extension, before assets, and is
    replaced in place when present, keeping whatever indentation the file
    uses. Written into the tracked addon.xml rather than only into the zip
    so that what ships is what git holds. Both modes judge the result by
    parsing it (news_in()), so this either works or says why not: until
    02/10/2026 a manifest indented with spaces matched neither pattern and
    both modes returned success having done nothing.
    </remarks>
    """
    addon_xml = os.path.join(SRC, "addon.xml")
    with open(addon_xml, encoding="utf-8-sig") as handle:
        text = handle.read()
    lines = changelog_section(version)
    expected = "\n".join(lines) if lines else None
    if news_in(text) == expected:
        return True
    if not write:
        sys.exit("ABORTED: addon.xml's <news> does not match the CHANGELOG.md "
                 f"section for {version}. Run: python3 build_zip.py --news, "
                 "then commit addon.xml.")
    escaped = "\n".join(l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        for l in lines)
    current = re.search(r"^([ \t]*)<news>.*?</news>[ \t]*\r?\n", text, re.S | re.M)
    if current:
        block = (current.group(1) + "<news>" + escaped + "</news>\n") if lines else ""
        wanted = text[:current.start()] + block + text[current.end():]
    else:
        anchor = re.search(r"^([ \t]*)<assets>", text, re.M)
        indent = anchor.group(1) if anchor else None
        if not anchor:
            # No assets element: fall back to the end of the metadata extension.
            anchor = re.search(r'<extension\b[^>]*point="xbmc\.addon\.metadata".*?^([ \t]*)</extension>',
                               text, re.S | re.M)
            if anchor:
                indent = anchor.group(1) + "\t"
        if not anchor:
            sys.exit("ABORTED: no place for <news> in skin.functional/addon.xml: "
                     "it has neither an <assets> element on its own line nor a "
                     "metadata extension. Nothing was written.")
        at = anchor.start(1)
        wanted = text[:at] + indent + "<news>" + escaped + "</news>\n" + text[at:]
    if news_in(wanted) != expected:
        sys.exit("ABORTED: the rewritten addon.xml would not read back with the "
                 f"CHANGELOG.md section for {version} as its news (is the "
                 "existing <news> element on a line of its own?). Nothing was "
                 "written.")
    with open(addon_xml, "w", encoding="utf-8") as handle:
        handle.write(wanted)
    print(f"addon.xml <news> set from CHANGELOG.md ({len(lines)} line(s))")
    return True


def is_junk_file(name):
    """
    <summary>
    Whether a filename is filesystem or NAS litter that must never be packed.
    </summary>
    <param name="name">Bare filename.</param>
    <returns>True for JUNK_FILES, Synology @SynoEAStream entries and any JUNK_FILE_GLOBS match.</returns>
    """
    return (name in JUNK_FILES or "@SynoEAStream" in name
            or any(fnmatch.fnmatch(name, g) for g in JUNK_FILE_GLOBS))


def dir_entry(arcname):
    """
    <summary>
    A directory entry an extractor on any platform can descend into.
    </summary>
    <remarks>
    A bare ZipInfo carries no permission bits, which reads as mode 0000, and
    a directory with no execute bit cannot be entered. Built on Windows that
    goes unnoticed, because the entry is stamped MS-DOS and Unix extractors
    ignore its mode. Built on Linux the entry is stamped Unix, the mode is
    obeyed, and the install unpacks a tree nothing can read. Setting the mode
    explicitly makes the two builds behave the same.
    </remarks>
    <param name="arcname">Directory path inside the zip, with its trailing slash.</param>
    <returns>A ZipInfo stamped drwxr-xr-x with the DOS directory flag.</returns>
    """
    info = zipfile.ZipInfo(arcname)
    info.external_attr = (0o40755 << 16) | 0x10   # drwxr-xr-x, DOS dir flag
    return info


def run_checks():
    """
    <summary>
    Run checks/skin_checks.py and stop the build on any finding.
    </summary>
    <exception cref="SystemExit">
    When the checker is missing, cannot run, or reports a finding.
    </exception>
    <remarks>
    The static checks are the test suite this project has (include and
    parameter cross references, string ids, navigation targets after include
    expansion, setting name drift, colours and fonts, the service's call
    targets, the dash and attribution rules). A red gate never ships, so a
    missing checker is treated the same as a failing one rather than skipped.
    </remarks>
    """
    script = os.path.join(REPO, "checks", "skin_checks.py")
    if not os.path.isfile(script):
        sys.exit("ABORTED: checks/skin_checks.py is missing, so the static "
                 "checks cannot run. Not building.")
    print("Static checks:")
    result = subprocess.run([sys.executable, script], cwd=REPO)
    if result.returncode != 0:
        sys.exit("ABORTED: the static checks found problems (listed above). "
                 "Not building.")


def collect_members(walk_root, arc_base, exclude_dirs=(), exclude_globs=(),
                    keep_dot_dirs=()):
    """
    <summary>
    Decide what a zip of walk_root will contain, without writing anything.
    </summary>
    <param name="walk_root">Folder whose contents are packed.</param>
    <param name="arc_base">Prefix inside the zip; empty puts the contents at the zip root.</param>
    <param name="exclude_dirs">Directory names skipped at any depth.</param>
    <param name="exclude_globs">fnmatch patterns tested against each bare filename.</param>
    <param name="keep_dot_dirs">Dot directory names packed all the same.</param>
    <returns>
    List of (member name, source path) sorted by member name; the source
    path is None for a directory entry.
    </returns>
    <remarks>
    Sorted so two builds of one tree list their members in the same order
    whatever order the filesystem hands them out in. A folder always sorts
    ahead of what is inside it, so the explicit directory entries Linux Kodi
    needs still come first. Splitting this from write_zip() is what lets
    main() judge the member list before any zip exists.
    </remarks>
    """
    members = {}
    if arc_base:
        # Top-level directory entry, because Linux Kodi requires this.
        members[arc_base + "/"] = None
    for root, dirs, files in os.walk(walk_root):
        # Dot directories hold local editor and tooling state, never
        # anything a user of the skin needs, so none of them are packed.
        dirs[:] = [d for d in dirs
                   if d not in JUNK_DIRS and d not in exclude_dirs
                   and (not d.startswith(".") or d in keep_dot_dirs)]
        for d in dirs:
            rel = os.path.relpath(os.path.join(root, d), walk_root)
            members["/".join(filter(None, [arc_base,
                                           rel.replace(os.sep, "/")])) + "/"] = None
        for f in files:
            if is_junk_file(f):
                continue
            if any(fnmatch.fnmatch(f, g) for g in exclude_globs):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, walk_root)
            members["/".join(filter(None, [arc_base,
                                           rel.replace(os.sep, "/")]))] = full
    return sorted(members.items())


def write_zip(out, walk_root, arc_base, exclude_dirs=(), exclude_globs=(),
              keep_dot_dirs=()):
    """
    <summary>
    Zip walk_root with portable entries into a part file beside out.
    </summary>
    <remarks>
    arc_base: prefix inside the zip ("" = contents at zip root,
    "skin.functional" = wrapped in that folder as Kodi expects).

    The archive is written to out plus PART_SUFFIX and out itself is never
    touched: the caller verifies the part file and only then renames it over
    out (os.replace), so a failed or interrupted build can neither leave a
    half written zip under a release name nor destroy a zip that was already
    there. Members are written in sorted order with fixed modes, files 0644
    and directories 0755, whatever the working tree's own modes are.
    </remarks>
    <param name="out">Final path of the zip; only the part file beside it is written.</param>
    <param name="walk_root">Folder whose contents are packed.</param>
    <param name="arc_base">Prefix inside the zip; empty puts the contents at the zip root.</param>
    <param name="exclude_dirs">Directory names skipped at any depth.</param>
    <param name="exclude_globs">fnmatch patterns tested against each bare filename.</param>
    <param name="keep_dot_dirs">Dot directory names packed all the same.</param>
    <returns>Tuple of files written, directory entries written, and the part file's path.</returns>
    """
    part = out + PART_SUFFIX
    file_count = dir_count = 0
    with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for arcname, full in collect_members(walk_root, arc_base, exclude_dirs,
                                             exclude_globs, keep_dot_dirs):
            if full is None:
                z.writestr(dir_entry(arcname), b"")
                dir_count += 1
                continue
            info = zipfile.ZipInfo.from_file(full, arcname, strict_timestamps=False)
            info.external_attr = 0o100644 << 16      # -rw-r--r--
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as handle:
                z.writestr(info, handle.read())
            file_count += 1
    return file_count, dir_count, part


def verify_zip(out, must_contain=(), must_not_contain_globs=(), rules=None,
               discard=False):
    """
    <summary>
    Re-open the zip and hard-fail on junk, corruption, a forbidden or
    duplicated member, or a missing expected entry. A contaminated zip
    crashes Kodi at install time, so refusing to produce one beats
    discovering it on the media centre.
    </summary>
    <param name="out">Zip to check.</param>
    <param name="must_contain">Member names that must be present.</param>
    <param name="must_not_contain_globs">fnmatch patterns no member basename may match.</param>
    <param name="rules">Name rules from name_rules(); every member is tested against them when given.</param>
    <param name="discard">True removes the file before aborting. Pass it only for a part file this run has just written.</param>
    <exception cref="SystemExit">On any junk, forbidden, duplicated or missing member, a backslash in a name, corruption, or an unreadable directory entry.</exception>
    <remarks>
    This never deletes unless told to. It used to remove whatever it was
    given, which included a kept, already released zip.
    </remarks>
    """
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        bad = [n for n in names
               if "@eaDir" in n or "@SynoEAStream" in n
               or "Thumbs.db" in n or ".DS_Store" in n or "\\" in n]
        bad += [n for n in names
                if any(fnmatch.fnmatch(os.path.basename(n), g)
                       for g in must_not_contain_globs)]
        if rules is not None:
            bad += forbidden_members(names, rules)
        duplicated = sorted({n for n in names if names.count(n) > 1})
        missing = [m for m in must_contain if m not in names]
        corrupt = z.testzip()
        # A directory without its execute bit cannot be descended into, so
        # the install unpacks a tree Kodi cannot read. Only a Unix-stamped
        # entry has its mode obeyed, which is why this stays silent on a
        # Windows build and bites on a Linux one.
        unreadable = [i.filename for i in z.infolist()
                      if i.filename.endswith("/") and i.create_system == 3
                      and not (i.external_attr >> 16) & 0o111]
    if bad or corrupt or missing or unreadable or duplicated:
        if discard:
            os.remove(out)
        sys.exit(f"ABORTED: bad zip {os.path.basename(out)}: "
                 f"junk/forbidden={sorted(set(bad))} missing={missing} "
                 f"corrupt={corrupt} unreadable_dirs={unreadable} "
                 f"duplicated={duplicated}")


def released_zip(version):
    """
    <summary>
    The installable zip already built for a version, wherever it now sits.
    </summary>
    <param name="version">Version string from addon.xml.</param>
    <returns>Its path, or None when the version has never been built here.</returns>
    <remarks>
    build_repo.py moves superseded skin zips into the old folder under the
    dist folder, so a released version is as likely to be there as in the
    dist folder itself. The rebuild guard looked only in the dist folder
    until 02/10/2026, which let an older version be rebuilt with different
    content the moment a newer one had been built.
    </remarks>
    """
    name = f"skin.functional-{version}.zip"
    for folder in (DIST, os.path.join(DIST, "old")):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def zip_members(path):
    """
    <summary>
    Map of member name -> CRC, the content identity of a zip. Timestamps
    are left out on purpose so an identical rebuild compares as identical.
    </summary>
    <param name="path">Zip to read.</param>
    <returns>Dict of member name to CRC.</returns>
    """
    with zipfile.ZipFile(path) as z:
        return {i.filename: i.CRC for i in z.infolist()}


def mirror_targets():
    """
    <summary>
    Folders every built zip is copied into.
    </summary>
    <remarks>
    Read from release-mirror.conf beside this script: one destination per
    line, blank lines and # comments ignored. The same share is reached by a
    different path depending on the machine (a UNC path on Windows, a mount
    point on Linux), so list every path the folder is known by and the first
    one that exists is used.

    No file means no mirroring, which is what a fresh clone should do. A file
    that exists but names nowhere reachable is an error, not a shrug: the
    whole point of listing a destination is that builds must land there.
    </remarks>
    <returns>A list holding the first reachable destination, or empty when there is no config or it names nothing.</returns>
    <exception cref="SystemExit">When the config names destinations and none is reachable.</exception>
    """
    if not os.path.isfile(MIRROR_CONF):
        return []

    candidates = []
    with open(MIRROR_CONF, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                candidates.append(line)

    if not candidates:
        return []

    live = [p for p in candidates if os.path.isdir(p)]
    if not live:
        sys.exit("ABORTED: no destination in release-mirror.conf is "
                 "reachable:\n  " + "\n  ".join(candidates) +
                 "\nMount the share and build again, or comment the line out.")
    return live[:1]


def mirror(paths, *zips):
    """
    <summary>
    Copy each zip into each destination, failing loudly on any problem.
    </summary>
    <remarks>
    A build that reports success while the copy silently failed is the one
    outcome worth going out of the way to prevent, so the size of every copy
    is checked against the source before the build is called done.
    </remarks>
    <param name="paths">Destination folders.</param>
    <param name="zips">Files to copy.</param>
    <exception cref="SystemExit">On a failed copy or a size mismatch.</exception>
    """
    for dest in paths:
        for src in zips:
            target = os.path.join(dest, os.path.basename(src))
            try:
                shutil.copyfile(src, target)
                copied = os.path.getsize(target)
            except OSError as exc:
                sys.exit(f"ABORTED: could not copy "
                         f"{os.path.basename(src)} to {dest}: {exc}")
            original = os.path.getsize(src)
            if copied != original:
                sys.exit(f"ABORTED: {os.path.basename(src)} copied to {dest} "
                         f"is {copied:,} bytes, expected {original:,}.")
            print(f"Mirrored: {target}")


def report(label, out, files, dirs):
    """
    <summary>
    Print one built zip's path, entry counts and size.
    </summary>
    <param name="label">dist or src.</param>
    <param name="out">Path of the zip.</param>
    <param name="files">Files written.</param>
    <param name="dirs">Directory entries written.</param>
    """
    size = os.path.getsize(out)
    print(f"Built {label}: {out}")
    print(f"  files: {files}   dirs: {dirs}   size: {size:,} bytes")


def main():
    """
    <summary>
    Build the Dist and source zips for the current version, verify both and mirror them.
    </summary>
    <exception cref="SystemExit">
    On an unknown argument, a missing source folder, a missing or empty
    local exclude file, a news element that does not match the changelog, a
    static check finding, a forbidden name anywhere in what would be packed,
    a packed file git does not track (or a tracked file left out), an
    unreachable mirror, a changed rebuild of a released version without
    --force, or any verification failure.
    </exception>
    <remarks>
    --force and --news are accepted. --news only rewrites addon.xml's news
    element from CHANGELOG.md and stops; a normal build refuses to run while
    the two disagree.

    Order matters and is deliberate. The ignore files are read and the
    exclude file validated first; then the member lists of both zips are
    worked out and judged (forbidden names, and the source list against
    git ls-files); only then is anything written. Each zip is written to a
    part file, verified, and renamed into place, so nothing half built ever
    carries a release name.

    An already built version, in the dist folder or its old folder, is
    compared with the fresh part file by member set and CRC; a differing
    rebuild aborts unless --force is given, so two archives can never share
    one version number, and an identical one keeps the existing file so its
    bytes stay exactly as shipped. The source zip's exclusions are read from
    the ignore files at build time, never listed here, because this file
    ships.
    </remarks>
    """
    args = sys.argv[1:]
    force = "--force" in args
    news_only = "--news" in args
    unknown = [a for a in args if a not in ("--force", "--news")]
    if unknown:
        sys.exit(f"Unknown argument(s): {' '.join(unknown)} "
                 "(--force and --news are accepted)")

    if not os.path.isdir(SRC):
        sys.exit(f"Source folder missing: {SRC}")
    # First of all, before a single byte is written: no exclude file, no
    # build. The same rules then judge every zip this run produces.
    rules = name_rules()
    if news_only:
        # After a version bump: copy the changelog section into addon.xml
        # and stop, so the bump commit carries the news with it.
        sync_news(read_version(), write=True)
        return
    sync_news(read_version(), write=False)
    run_checks()

    version = read_version()

    # Ignore files are read at build time, not at import time, so an edit to
    # them takes effect on the next build without touching this script.
    src_globs = rules[0]
    print(f"  {len(src_globs)} source exclusions in force, "
          f"{GIT_EXCLUDE_FILE} read and non-empty")

    # --- Judge both member lists before anything exists on disk ---
    dist_names = [name for name, _ in collect_members(SRC, "skin.functional")]
    bad = forbidden_members(dist_names, rules)
    if bad:
        sys.exit("ABORTED: the skin folder holds files that must never ship "
                 f"(local only, secret looking or junk names): {bad}. "
                 "Move them out of skin.functional. Nothing was built.")
    src_names = [name for name, full in
                 collect_members(REPO, "", exclude_dirs=SRC_ZIP_EXCLUDE_DIRS,
                                 exclude_globs=src_globs,
                                 keep_dot_dirs=SRC_KEEP_DOT_DIRS)
                 if full is not None]
    refuse_untracked(src_names, "the working tree, as the source zip would pack it,")

    os.makedirs(DIST, exist_ok=True)
    os.makedirs(GIT, exist_ok=True)

    # Resolved before anything is built: an unreachable share should stop the
    # run at once rather than after two zips have been written.
    mirrors = mirror_targets()

    # --- Dist zip: the installable skin folder only ---
    # A version that is already built must not be silently rebuilt with
    # different content: the zip may be released, and two different archives
    # under one version number poison every cache and update check. The new
    # zip is packed to a part file first, compared by member set and CRC,
    # and only an identical rebuild proceeds (keeping the existing file, so
    # its bytes and checksums stay exactly as shipped).
    dist_out = os.path.join(DIST, f"skin.functional-{version}.zip")
    dist_must = ("skin.functional/", "skin.functional/addon.xml")
    files, dirs, part = write_zip(dist_out, SRC, "skin.functional")
    verify_zip(part, must_contain=dist_must, rules=rules, discard=True)
    existing = released_zip(version)
    if existing and not force:
        try:
            changed = zip_members(part) != zip_members(existing)
        except zipfile.BadZipFile as exc:
            os.remove(part)
            sys.exit(f"ABORTED: the existing {existing} cannot be read ({exc}). "
                     "It has been left alone; move it aside, or pass --force "
                     "to replace it.")
        os.remove(part)
        if changed:
            sys.exit(f"ABORTED: version {version} already released with "
                     f"different content ({existing}), so bump the addon.xml "
                     "version first (or pass --force to overwrite the "
                     "existing zip).")
        if existing != dist_out:
            # Superseded and moved to the old folder by build_repo.py: bring
            # a copy of those exact bytes back rather than a fresh archive.
            shutil.copyfile(existing, dist_out)
            print(f"Existing {os.path.basename(dist_out)} found in "
                  f"{os.path.basename(os.path.dirname(existing))}/ with "
                  "identical content, copied back as is")
        else:
            print(f"Existing {os.path.basename(dist_out)} has identical "
                  "content, kept as is")
        # Checked, never deleted: a kept release that fails here needs a
        # person to look at it.
        verify_zip(dist_out, must_contain=dist_must, rules=rules)
    else:
        os.replace(part, dist_out)
    report("dist", dist_out, files, dirs)

    # --- Source zip: the whole repo tree as pushed to GitHub ---
    src_out = os.path.join(GIT, f"skin.functional-{version}-src.zip")
    files, dirs, part = write_zip(src_out, REPO, "",
                                  exclude_dirs=SRC_ZIP_EXCLUDE_DIRS,
                                  exclude_globs=src_globs,
                                  keep_dot_dirs=SRC_KEEP_DOT_DIRS)
    verify_zip(part,
               must_contain=("skin.functional/addon.xml", "README.md",
                             ".gitignore", "build_zip.py"),
               rules=rules, discard=True)
    with zipfile.ZipFile(part) as z:
        packed = [n for n in z.namelist() if not n.endswith("/")]
    try:
        refuse_untracked(packed, f"{os.path.basename(src_out)}")
    except SystemExit:
        os.remove(part)
        raise
    os.replace(part, src_out)
    report("src", src_out, files, dirs)

    print("  verified: no junk or forbidden entries, archive integrity OK, "
          "source zip equals git ls-files")

    if mirrors:
        mirror(mirrors, dist_out, src_out)


if __name__ == "__main__":
    main()
