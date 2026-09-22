"""
<summary>
Build both release zips for skin.functional.
</summary>
<remarks>
USE THIS, NOT PowerShell's Compress-Archive. Compress-Archive emits zip
entries with backslash separators and (more importantly) no explicit
directory entries, and Linux Kodi (LibreELEC, Bazzite, every non-Windows
build) refuses to install zips that lack directory records, even though
Windows Kodi accepts them silently.

This script writes portable zips:
  - forward-slash path separators
  - explicit directory entries for every folder
  - DEFLATE compression
  - reads the version straight out of skin.functional/addon.xml so the
    output filenames always match the manifest (addon.xml is the version
    source of truth, because Kodi requires it there, so no separate VERSION file)

Usage:
    python build_zip.py        (or: powershell -File build-zip.ps1)
    python build_zip.py --force    rebuild an already-released version even
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

# Extra exclusions for the source zip: the output folders themselves,
# session data, and archive/temp/log files anywhere in the tree.
SRC_ZIP_EXCLUDE_DIRS = ("Skin Dist", "Skin Git", "$RECYCLE.BIN")
# Every dot directory is skipped as well, so local editor and tooling state
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
# (ignore_file_lines()), because packaging without it is the whole risk.


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


def changelog_section(version):
    """
    <summary>
    The bullet lines of one version's section in CHANGELOG.md, as plain
    text lines ready for the addon.xml news element.
    </summary>
    <param name="version">Version string exactly as in addon.xml.</param>
    <returns>List of lines, empty when the file or the section is missing.</returns>
    <remarks>
    A section starts at a heading whose text contains the version and runs
    to the next heading, the same rule publish-github.sh uses to pick the
    release notes, so the news and the notes can never disagree. Bullet
    markers are dropped and wrapped bullet lines rejoined; anything else in
    the section is kept as it is. Capped at NEWS_MAX_LINES, since Kodi's
    add-on info screen is not the place for a long read.
    </remarks>
    """
    if not os.path.isfile(CHANGELOG):
        return []
    lines, seen = [], False
    with open(CHANGELOG, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if re.match(r"^#{1,3} ", line):
                if seen:
                    break
                seen = version in line
                continue
            if not seen:
                continue
            if re.match(r"^\s*[-*] ", line):
                lines.append(re.sub(r"^\s*[-*] ", "", line).strip())
            elif line.startswith("  ") and lines:
                lines[-1] += " " + line.strip()
            elif line.strip():
                lines.append(line.strip())
    return lines[:NEWS_MAX_LINES]


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
    the news flag and commit addon.xml. A version with no changelog section
    is allowed and carries no news.</exception>
    <remarks>
    The element lives inside the metadata extension, before assets, and is
    replaced in place when present. Written into the tracked addon.xml
    rather than only into the zip so that what ships is what git holds.
    </remarks>
    """
    addon_xml = os.path.join(SRC, "addon.xml")
    with open(addon_xml, encoding="utf-8-sig") as handle:
        text = handle.read()
    lines = changelog_section(version)
    escaped = "\n".join(l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        for l in lines)
    block = ("\t\t<news>" + escaped + "</news>\n") if lines else ""
    current = re.search(r"\t\t<news>.*?</news>\n", text, re.S)
    if current:
        wanted = text.replace(current.group(0), block)
    elif block:
        wanted = text.replace("\t\t<assets>", block + "\t\t<assets>", 1)
    else:
        wanted = text
    if wanted == text:
        return True
    if not write:
        sys.exit("ABORTED: addon.xml's <news> does not match the CHANGELOG.md "
                 f"section for {version}. Run: python3 build_zip.py --news, "
                 "then commit addon.xml.")
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


def write_zip(out, walk_root, arc_base, exclude_dirs=(), exclude_globs=()):
    """
    <summary>
    Zip walk_root into out with portable entries.
    </summary>
    <remarks>
    arc_base: prefix inside the zip ("" = contents at zip root,
    "skin.functional" = wrapped in that folder as Kodi expects).
    Returns the number of files written.
    </remarks>
    <param name="out">Zip to write; an existing file is replaced.</param>
    <param name="walk_root">Folder whose contents are packed.</param>
    <param name="arc_base">Prefix inside the zip; empty puts the contents at the zip root.</param>
    <param name="exclude_dirs">Directory names skipped at any depth.</param>
    <param name="exclude_globs">fnmatch patterns tested against each bare filename.</param>
    <returns>Tuple of files written and directory entries written.</returns>
    """
    if os.path.exists(out):
        os.remove(out)

    seen_dirs = set()
    file_count = 0

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if arc_base:
            # Top-level directory entry first, because Linux Kodi requires this.
            z.writestr(dir_entry(arc_base + "/"), b"")
            seen_dirs.add(arc_base + "/")

        for root, dirs, files in os.walk(walk_root):
            # Dot directories hold local editor and tooling state, never
            # anything a user of the skin needs, so none of them are packed.
            dirs[:] = [d for d in dirs
                       if d not in JUNK_DIRS and d not in exclude_dirs
                       and not d.startswith(".")]

            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), walk_root)
                arcname = "/".join(filter(None, [arc_base,
                                                 rel.replace(os.sep, "/")])) + "/"
                if arcname not in seen_dirs:
                    z.writestr(dir_entry(arcname), b"")
                    seen_dirs.add(arcname)

            for f in files:
                if is_junk_file(f):
                    continue
                if any(fnmatch.fnmatch(f, g) for g in exclude_globs):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, walk_root)
                arcname = "/".join(filter(None, [arc_base,
                                                 rel.replace(os.sep, "/")]))
                z.write(full, arcname)
                file_count += 1

    return file_count, len(seen_dirs)


def verify_zip(out, must_contain=(), must_not_contain_globs=()):
    """
    <summary>
    Re-open the zip and hard-fail on junk, corruption, or a missing
    expected entry. A contaminated zip crashes Kodi at install time, so
    refusing to produce one beats discovering it on the media centre.
    </summary>
    <param name="out">Zip to check.</param>
    <param name="must_contain">Member names that must be present.</param>
    <param name="must_not_contain_globs">fnmatch patterns no member basename may match.</param>
    <exception cref="SystemExit">On any junk, forbidden or missing member, corruption, or an unreadable directory entry; the zip is removed first.</exception>
    """
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        bad = [n for n in names
               if "@eaDir" in n or "@SynoEAStream" in n
               or "Thumbs.db" in n or ".DS_Store" in n]
        bad += [n for n in names
                if any(fnmatch.fnmatch(os.path.basename(n), g)
                       for g in must_not_contain_globs)]
        missing = [m for m in must_contain if m not in names]
        corrupt = z.testzip()
        # A directory without its execute bit cannot be descended into, so
        # the install unpacks a tree Kodi cannot read. Only a Unix-stamped
        # entry has its mode obeyed, which is why this stays silent on a
        # Windows build and bites on a Linux one.
        unreadable = [i.filename for i in z.infolist()
                      if i.filename.endswith("/") and i.create_system == 3
                      and not (i.external_attr >> 16) & 0o111]
    if bad or corrupt or missing or unreadable:
        os.remove(out)
        sys.exit(f"ABORTED: bad zip {os.path.basename(out)}: "
                 f"junk/forbidden={bad} missing={missing} corrupt={corrupt} "
                 f"unreadable_dirs={unreadable}")


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
    On an unknown argument, a missing source folder, a news element that
    does not match the changelog, a static check finding,
    an unreachable mirror,
    a changed rebuild of a released version without --force, or any
    verification failure.
    </exception>
    <remarks>
    --force and --news are accepted. --news only rewrites addon.xml's news
    element from CHANGELOG.md and stops; a normal build refuses to run while
    the two disagree. An already built version is repacked to a
    temporary zip and compared by member set and CRC; a differing rebuild
    aborts unless --force is given, so two archives can never share one
    version number. The source zip's exclusions are read from the ignore
    files at build time, never listed here, because this file ships.
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
    if news_only:
        # After a version bump: copy the changelog section into addon.xml
        # and stop, so the bump commit carries the news with it.
        sync_news(read_version(), write=True)
        return
    sync_news(read_version(), write=False)
    run_checks()
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(GIT, exist_ok=True)

    version = read_version()

    # Resolved before anything is built: an unreachable share should stop the
    # run at once rather than after two zips have been written.
    mirrors = mirror_targets()

    # --- Dist zip: the installable skin folder only ---
    # A version that is already built must not be silently rebuilt with
    # different content: the zip may be released, and two different archives
    # under one version number poison every cache and update check. The new
    # zip is packed beside the old one first, compared by member set and CRC,
    # and only an identical rebuild proceeds (keeping the existing file, so
    # its bytes and checksums stay exactly as shipped).
    dist_out = os.path.join(DIST, f"skin.functional-{version}.zip")
    if os.path.exists(dist_out) and not force:
        rebuild = dist_out + ".rebuild"
        files, dirs = write_zip(rebuild, SRC, "skin.functional")
        changed = zip_members(rebuild) != zip_members(dist_out)
        os.remove(rebuild)
        if changed:
            sys.exit(f"ABORTED: version {version} already released with "
                     "different content, so bump the addon.xml version first "
                     "(or pass --force to overwrite the existing zip).")
        print(f"Existing {os.path.basename(dist_out)} has identical "
              "content, kept as is")
    else:
        files, dirs = write_zip(dist_out, SRC, "skin.functional")
    verify_zip(dist_out,
               must_contain=("skin.functional/", "skin.functional/addon.xml"),
               must_not_contain_globs=("*.zip", "*.7z", "*.tmp", "*.log",
                                       "*.pyc", "*.pyo"))
    report("dist", dist_out, files, dirs)

    # --- Source zip: the whole repo tree as pushed to GitHub ---
    # Ignore files are read here, not at import time, so an edit to them takes
    # effect on the next build without touching this script.
    src_globs = (SRC_ZIP_EXCLUDE_GLOBS + git_ignored_root_files()
                 + git_ignored_globs())
    print(f"  {len(src_globs)} source exclusions in force, "
          f"{GIT_EXCLUDE_FILE} read and non-empty")
    src_out = os.path.join(GIT, f"skin.functional-{version}-src.zip")
    files, dirs = write_zip(src_out, REPO, "",
                            exclude_dirs=SRC_ZIP_EXCLUDE_DIRS,
                            exclude_globs=src_globs)
    verify_zip(src_out,
               must_contain=("skin.functional/addon.xml", "README.md",
                             ".gitignore", "build_zip.py"),
               must_not_contain_globs=src_globs)
    report("src", src_out, files, dirs)

    print("  verified: no junk entries, archive integrity OK")

    if mirrors:
        mirror(mirrors, dist_out, src_out)


if __name__ == "__main__":
    main()
