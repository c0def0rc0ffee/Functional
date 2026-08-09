"""
Build the Kodi repository tree for auto updates.

Kodi can update the skin on its own once a device has the small
repository.functional add-on installed. That add-on points at three URLs
served straight from the "repo" branch of the GitHub repository:

    addons.xml       manifest listing every add-on and its current version
    addons.xml.md5   checksum Kodi polls to detect a change
    zips/<id>/<id>-<version>.zip   the installable zips themselves

This script assembles exactly that tree so publish-github.sh can push it:

    Skin Dist/repo/addons.xml
    Skin Dist/repo/addons.xml.md5
    Skin Dist/repo/zips/skin.functional/skin.functional-<version>.zip
    Skin Dist/repo/zips/repository.functional/repository.functional-<rv>.zip

A copy of the repository zip also lands in Repositories/Functional/Builds/
because that is the one file a user installs by hand, once per device.

Run build_zip.py first: the skin zip it produces is copied in here, never
rebuilt, so the repo tree always ships the exact zip that was tested.

Usage:
    python build_zip.py && python build_repo.py
"""

import hashlib
import os
import re
import shutil
import sys

from build_zip import DIST, REPO, read_version, verify_zip, write_zip

REPO_ADDON = "repository.functional"
# The repository add-on's source lives with the other repository add-ons in
# "Kodi Addons/Repositories", not in this project tree, so it stays out of
# the published skin source. See Repositories/Functional/PROJECT_NOTES.md.
REPO_ADDON_SRC = os.path.join(os.path.dirname(REPO), "Repositories",
                              "Functional", REPO_ADDON)
OUT = os.path.join(DIST, "repo")


def addon_xml_version(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', text)
    if not m:
        sys.exit(f"Could not find <addon version=\"…\"> in {path}")
    return m.group(1)


def addon_xml_body(path):
    """The <addon>…</addon> element only, declaration stripped, for
    inclusion in the combined addons.xml manifest."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
    return text.strip()


def main():
    skin_version = read_version()
    repo_version = addon_xml_version(os.path.join(REPO_ADDON_SRC, "addon.xml"))

    skin_zip = os.path.join(DIST, f"skin.functional-{skin_version}.zip")
    if not os.path.isfile(skin_zip):
        sys.exit(f"Missing {skin_zip}\nRun build_zip.py first.")

    # Rebuilt from scratch every run so a version bump can never leave a
    # stale zip behind: the tree is pushed verbatim, and an old zip next to
    # a new manifest would be dead weight on every clone of the branch.
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    skin_dir = os.path.join(OUT, "zips", "skin.functional")
    repo_dir = os.path.join(OUT, "zips", REPO_ADDON)
    os.makedirs(skin_dir)
    os.makedirs(repo_dir)

    # --- repository add-on zip: the one file a user installs by hand ---
    repo_zip = os.path.join(repo_dir, f"{REPO_ADDON}-{repo_version}.zip")
    files, dirs = write_zip(repo_zip, REPO_ADDON_SRC, REPO_ADDON)
    verify_zip(repo_zip,
               must_contain=(f"{REPO_ADDON}/", f"{REPO_ADDON}/addon.xml"))
    print(f"Built repo add-on: {repo_zip}")
    print(f"  files: {files}   dirs: {dirs}")

    # The install-once zip, kept beside the add-on source. Older versions
    # are cleared so the folder always holds exactly the current build.
    builds = os.path.join(os.path.dirname(REPO_ADDON_SRC), "Builds")
    os.makedirs(builds, exist_ok=True)
    for old in os.listdir(builds):
        if old.startswith(REPO_ADDON + "-") and old.endswith(".zip"):
            os.remove(os.path.join(builds, old))
    handout = os.path.join(builds, os.path.basename(repo_zip))
    shutil.copyfile(repo_zip, handout)
    print(f"Copied for handout: {handout}")

    # --- skin zip: copied, not rebuilt ---
    shutil.copyfile(skin_zip, os.path.join(skin_dir,
                                           os.path.basename(skin_zip)))
    print(f"Copied skin zip: {os.path.basename(skin_zip)}")

    # --- manifest and checksum ---
    manifest = "\n".join((
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<addons>",
        addon_xml_body(os.path.join(REPO, "skin.functional", "addon.xml")),
        addon_xml_body(os.path.join(REPO_ADDON_SRC, "addon.xml")),
        "</addons>",
        "",
    ))
    manifest_path = os.path.join(OUT, "addons.xml")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(manifest)

    digest = hashlib.md5(manifest.encode("utf-8")).hexdigest()
    # Digest only, no trailing newline: Kodi compares the fetched checksum
    # text against its own computation, so any extra byte breaks updates.
    with open(os.path.join(OUT, "addons.xml.md5"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(digest)

    print(f"Wrote addons.xml (skin {skin_version}, repo add-on {repo_version})")
    print(f"Wrote addons.xml.md5 ({digest})")
    print(f"Repo tree ready: {OUT}")


if __name__ == "__main__":
    main()
