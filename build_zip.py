"""
Build both release zips for skin.functional.

USE THIS, NOT PowerShell's Compress-Archive. Compress-Archive emits zip
entries with backslash separators and (more importantly) no explicit
directory entries — Linux Kodi (LibreELEC, Bazzite, every non-Windows
build) refuses to install zips that lack directory records, even though
Windows Kodi accepts them silently.

This script writes portable zips:
  - forward-slash path separators
  - explicit directory entries for every folder
  - DEFLATE compression
  - reads the version straight out of skin.functional/addon.xml so the
    output filenames always match the manifest (addon.xml is the version
    source of truth — Kodi requires it there, so no separate VERSION file)

Usage:
    python build_zip.py        (or: powershell -File build-zip.ps1)

Output:
    Skin Dist/skin.functional-<version>.zip      Kodi-installable skin only
    Skin Git/skin.functional-<version>-src.zip   full source snapshot — the
                                                 exact tree pushed to GitHub

Both zips are also copied to every folder listed in release-mirror.conf, if
that file exists. See mirror_targets() for the format. Without the file the
build simply produces the two zips, so a fresh clone works unchanged.
"""

import fnmatch
import os
import re
import shutil
import sys
import zipfile

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "skin.functional")
DIST = os.path.join(REPO, "Skin Dist")
GIT = os.path.join(REPO, "Skin Git")

# Directory names that must never ship anywhere. @eaDir is Synology NAS
# indexing metadata — its @SynoEAStream entries crash Kodi's zip
# extraction on install (seen on Kodi 21 / Linux).
JUNK_DIRS = ("__pycache__", ".git", "@eaDir", "#recycle", ".svn")
JUNK_FILES = ("Thumbs.db", "desktop.ini", ".DS_Store")

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
                         "release-mirror.conf", "publish.conf",
                         "publish-github.sh", "push-source.sh",
                         ".publish-allow", "GITHUB-RELEASE-GUIDE.md",
                         "Github repository", "PROJECT_NOTES.md")

MIRROR_CONF = os.path.join(REPO, "release-mirror.conf")


def read_version():
    addon_xml = os.path.join(SRC, "addon.xml")
    with open(addon_xml, encoding="utf-8") as fh:
        text = fh.read()
    # Match the addon-tag's version attribute specifically — not the XML
    # declaration's version="1.0" on the first line.
    m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', text)
    if not m:
        sys.exit("Could not find <addon version=\"…\"> in addon.xml")
    return m.group(1)


def is_junk_file(name):
    return name in JUNK_FILES or "@SynoEAStream" in name


def dir_entry(arcname):
    """A directory entry an extractor on any platform can descend into.

    A bare ZipInfo carries no permission bits, which reads as mode 0000, and
    a directory with no execute bit cannot be entered. Built on Windows that
    goes unnoticed, because the entry is stamped MS-DOS and Unix extractors
    ignore its mode. Built on Linux the entry is stamped Unix, the mode is
    obeyed, and the install unpacks a tree nothing can read. Setting the mode
    explicitly makes the two builds behave the same.
    """
    info = zipfile.ZipInfo(arcname)
    info.external_attr = (0o40755 << 16) | 0x10   # drwxr-xr-x, DOS dir flag
    return info


def write_zip(out, walk_root, arc_base, exclude_dirs=(), exclude_globs=()):
    """Zip walk_root into out with portable entries.

    arc_base: prefix inside the zip ("" = contents at zip root,
    "skin.functional" = wrapped in that folder as Kodi expects).
    Returns the number of files written.
    """
    if os.path.exists(out):
        os.remove(out)

    seen_dirs = set()
    file_count = 0

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if arc_base:
            # Top-level directory entry first — Linux Kodi requires this.
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
    """Re-open the zip and hard-fail on junk, corruption, or a missing
    expected entry. A contaminated zip crashes Kodi at install time, so
    refusing to produce one beats discovering it on the media centre."""
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
        sys.exit(f"ABORTED — bad zip {os.path.basename(out)}: "
                 f"junk/forbidden={bad} missing={missing} corrupt={corrupt} "
                 f"unreadable_dirs={unreadable}")


def mirror_targets():
    """Folders every built zip is copied into.

    Read from release-mirror.conf beside this script: one destination per
    line, blank lines and # comments ignored. The same share is reached by a
    different path depending on the machine (a UNC path on Windows, a mount
    point on Linux), so list every path the folder is known by and the first
    one that exists is used.

    No file means no mirroring, which is what a fresh clone should do. A file
    that exists but names nowhere reachable is an error, not a shrug: the
    whole point of listing a destination is that builds must land there.
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
        sys.exit("ABORTED — no destination in release-mirror.conf is "
                 "reachable:\n  " + "\n  ".join(candidates) +
                 "\nMount the share and build again, or comment the line out.")
    return live[:1]


def mirror(paths, *zips):
    """Copy each zip into each destination, failing loudly on any problem.

    A build that reports success while the copy silently failed is the one
    outcome worth going out of the way to prevent, so the size of every copy
    is checked against the source before the build is called done.
    """
    for dest in paths:
        for src in zips:
            target = os.path.join(dest, os.path.basename(src))
            try:
                shutil.copyfile(src, target)
                copied = os.path.getsize(target)
            except OSError as exc:
                sys.exit(f"ABORTED — could not copy "
                         f"{os.path.basename(src)} to {dest}: {exc}")
            original = os.path.getsize(src)
            if copied != original:
                sys.exit(f"ABORTED — {os.path.basename(src)} copied to {dest} "
                         f"is {copied:,} bytes, expected {original:,}.")
            print(f"Mirrored: {target}")


def report(label, out, files, dirs):
    size = os.path.getsize(out)
    print(f"Built {label}: {out}")
    print(f"  files: {files}   dirs: {dirs}   size: {size:,} bytes")


def main():
    if not os.path.isdir(SRC):
        sys.exit(f"Source folder missing: {SRC}")
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(GIT, exist_ok=True)

    version = read_version()

    # Resolved before anything is built: an unreachable share should stop the
    # run at once rather than after two zips have been written.
    mirrors = mirror_targets()

    # --- Dist zip: the installable skin folder only ---
    dist_out = os.path.join(DIST, f"skin.functional-{version}.zip")
    files, dirs = write_zip(dist_out, SRC, "skin.functional")
    verify_zip(dist_out,
               must_contain=("skin.functional/", "skin.functional/addon.xml"),
               must_not_contain_globs=("*.zip", "*.7z", "*.tmp", "*.log"))
    report("dist", dist_out, files, dirs)

    # --- Source zip: the whole repo tree as pushed to GitHub ---
    src_out = os.path.join(GIT, f"skin.functional-{version}-src.zip")
    files, dirs = write_zip(src_out, REPO, "",
                            exclude_dirs=SRC_ZIP_EXCLUDE_DIRS,
                            exclude_globs=SRC_ZIP_EXCLUDE_GLOBS)
    verify_zip(src_out,
               must_contain=("skin.functional/addon.xml", "README.md",
                             ".gitignore", "build_zip.py"),
               must_not_contain_globs=SRC_ZIP_EXCLUDE_GLOBS)
    report("src", src_out, files, dirs)

    print("  verified: no junk entries, archive integrity OK")

    if mirrors:
        mirror(mirrors, dist_out, src_out)


if __name__ == "__main__":
    main()
