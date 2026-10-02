"""
<summary>
Build the Kodi repository tree for auto updates.
</summary>
<remarks>
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
Superseded copies there are moved into Builds/old/, never deleted.

The tree is assembled in a part folder and swapped in when complete, the
md5 written last, and addons.xml takes the skin's entry from the addon.xml
inside the copied zip, so the feed can never describe one build and serve
another.

Run build_zip.py first: the skin zip it produces is copied in here, never
rebuilt, so the repo tree always ships the exact zip that was tested.

Usage:
    python3 build_zip.py && python3 build_repo.py
</remarks>
"""

import hashlib
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

from build_zip import (DIST, PART_SUFFIX, REPO, name_rules, read_version,
                       verify_zip, write_zip)

REPO_ADDON = "repository.functional"
# The repository add-on's source lives with the other repository add-ons in
# "Kodi Addons/Repositories", not in this project tree, so it stays out of
# the published skin source.
REPO_ADDON_SRC = os.path.join(os.path.dirname(REPO), "Repositories",
                              "Functional", REPO_ADDON)
OUT = os.path.join(DIST, "repo")


def addon_xml_version(path):
    """
    <summary>
    Read the version attribute of the addon element.
    </summary>
    <param name="path">Path to an addon.xml.</param>
    <returns>The version string.</returns>
    <exception cref="SystemExit">When the attribute cannot be found.</exception>
    <remarks>
    Read with utf-8-sig so an editor added BOM is dropped rather than carried
    into the manifest ahead of the declaration, which Kodi's parser rejects.
    </remarks>
    """
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    return version_in(text, path)


def version_in(text, where):
    """
    <summary>
    The version attribute of the addon element in an addon.xml's text.
    </summary>
    <param name="text">The manifest text.</param>
    <param name="where">How to name the manifest in an error.</param>
    <returns>The version string.</returns>
    <exception cref="SystemExit">When the attribute cannot be found.</exception>
    """
    m = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', text)
    if not m:
        sys.exit(f"Could not find <addon version=\"…\"> in {where}")
    return m.group(1)


def addon_xml_body(text):
    """
    <summary>
    The <addon>…</addon> element only, declaration stripped, for
    inclusion in the combined addons.xml manifest.
    </summary>
    <param name="text">The text of an addon.xml.</param>
    <returns>The element text, stripped.</returns>
    """
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
    return text.strip()


def skin_manifest_from_zip(zip_path, expected_version):
    """
    <summary>
    The skin's addon.xml as it sits inside the zip the feed will serve.
    </summary>
    <param name="zip_path">The built skin zip.</param>
    <param name="expected_version">The version its file name claims.</param>
    <returns>The manifest text, BOM dropped.</returns>
    <exception cref="SystemExit">When the zip holds no manifest, or the manifest's version is not the one in the file name.</exception>
    <remarks>
    addons.xml used to be assembled from the working tree's addon.xml while
    the zip beside it had been built earlier, so an edit to the manifest
    after the build (a dependency, the news) made the feed describe one
    add-on and serve another. What Kodi is told and what Kodi downloads now
    come from the same bytes.
    </remarks>
    """
    with zipfile.ZipFile(zip_path) as z:
        try:
            raw = z.read("skin.functional/addon.xml")
        except KeyError:
            sys.exit(f"ABORTED: {zip_path} holds no skin.functional/addon.xml.")
    text = raw.decode("utf-8-sig")
    inside = version_in(text, f"addon.xml inside {os.path.basename(zip_path)}")
    if inside != expected_version:
        sys.exit(f"ABORTED: {os.path.basename(zip_path)} holds version {inside}, "
                 f"not {expected_version}. Run build_zip.py again.")
    return text


def write_atomic(path, text):
    """
    <summary>
    Write a small text file so it is either wholly there or not there at all.
    </summary>
    <param name="path">Final path.</param>
    <param name="text">Content, written as UTF-8 with LF line ends and nothing added.</param>
    <remarks>
    Written to a part file and renamed. Kodi compares addons.xml with its
    md5 byte for byte, so a half written one is a broken feed.
    </remarks>
    """
    part = path + PART_SUFFIX
    with open(part, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(part, path)


def main():
    """
    <summary>
    Assemble the Kodi repository tree under Skin Dist/repo.
    </summary>
    <exception cref="SystemExit">
    When build_zip.py has not produced the skin zip first, the local exclude
    file is missing, a zip holds a forbidden name, the skin zip's own
    manifest disagrees with its file name, or the combined manifest does not
    parse and list both add-ons at the expected versions.
    </exception>
    <remarks>
    The tree is assembled in a part folder beside the real one and swapped
    in only when complete, with the md5 written last, so Skin Dist/repo is
    never a half built feed: the publish script pushes that folder verbatim,
    and Kodi silently rejects a feed whose md5 does not match.

    Zips and verifies the repository add-on, copies the install once zip to
    Builds/, copies (never rebuilds) the already tested skin zip, moves
    superseded zips into an old folder beside each (moved, never deleted),
    then writes the combined addons.xml (the skin's entry from the manifest
    inside the copied zip, the repository add-on's from its source) and its
    md5. The digest is
    written with no trailing newline because Kodi compares the fetched text
    byte for byte.
    </remarks>
    """
    skin_version = read_version()
    repo_version = addon_xml_version(os.path.join(REPO_ADDON_SRC, "addon.xml"))

    skin_zip = os.path.join(DIST, f"skin.functional-{skin_version}.zip")
    if not os.path.isfile(skin_zip):
        sys.exit(f"Missing {skin_zip}\nRun build_zip.py first.")

    # Read first: no local exclude file, no build. The same name rules that
    # judge the skin zip judge the repository add-on's.
    rules = name_rules()
    verify_zip(skin_zip,
               must_contain=("skin.functional/", "skin.functional/addon.xml"),
               rules=rules)
    skin_manifest = skin_manifest_from_zip(skin_zip, skin_version)

    # Assembled from scratch in a part folder every run, so a version bump
    # can never leave a stale zip behind: the tree is pushed verbatim, and an
    # old zip next to a new manifest would be dead weight on every clone of
    # the branch. Everything in it is a copy of a zip kept elsewhere.
    work = OUT + PART_SUFFIX
    if os.path.isdir(work):
        shutil.rmtree(work)
    skin_dir = os.path.join(work, "zips", "skin.functional")
    repo_dir = os.path.join(work, "zips", REPO_ADDON)
    os.makedirs(skin_dir)
    os.makedirs(repo_dir)

    # --- repository add-on zip: the one file a user installs by hand ---
    repo_zip = os.path.join(repo_dir, f"{REPO_ADDON}-{repo_version}.zip")
    files, dirs, part = write_zip(repo_zip, REPO_ADDON_SRC, REPO_ADDON)
    verify_zip(part,
               must_contain=(f"{REPO_ADDON}/", f"{REPO_ADDON}/addon.xml"),
               rules=rules, discard=True)
    os.replace(part, repo_zip)
    print(f"Built repo add-on: {os.path.basename(repo_zip)}")
    print(f"  files: {files}   dirs: {dirs}")

    # The install-once zip, kept beside the add-on source. Older versions
    # are moved into Builds/old so the folder holds exactly the current
    # build. Moved, never deleted: a superseded release is still a release.
    builds = os.path.join(os.path.dirname(REPO_ADDON_SRC), "Builds")
    os.makedirs(builds, exist_ok=True)
    builds_old = os.path.join(builds, "old")
    for old in sorted(os.listdir(builds)):
        if (old.startswith(REPO_ADDON + "-") and old.endswith(".zip")
                and old != os.path.basename(repo_zip)):
            os.makedirs(builds_old, exist_ok=True)
            shutil.move(os.path.join(builds, old), os.path.join(builds_old, old))
            print(f"Moved old repository zip to Builds/old/: {old}")
    handout = os.path.join(builds, os.path.basename(repo_zip))
    shutil.copyfile(repo_zip, handout + PART_SUFFIX)
    os.replace(handout + PART_SUFFIX, handout)
    print(f"Copied for handout: {handout}")

    # --- skin zip: copied, not rebuilt ---
    shutil.copyfile(skin_zip, os.path.join(skin_dir,
                                           os.path.basename(skin_zip)))
    print(f"Copied skin zip: {os.path.basename(skin_zip)}")

    # Older skin zips are moved out of the dist folder so it holds exactly
    # the version the feed ships. Moved, never deleted: build_zip.py's
    # "already released with different content" guard looks in old/ as well
    # as the dist folder, and a superseded release is still a release.
    old_dir = os.path.join(DIST, "old")
    for old in sorted(os.listdir(DIST)):
        if (old.startswith("skin.functional-") and old.endswith(".zip")
                and old != os.path.basename(skin_zip)):
            os.makedirs(old_dir, exist_ok=True)
            shutil.move(os.path.join(DIST, old), os.path.join(old_dir, old))
            print(f"Moved old skin zip to old/: {old}")

    # --- manifest and checksum ---
    with open(os.path.join(REPO_ADDON_SRC, "addon.xml"), encoding="utf-8-sig") as fh:
        repo_manifest = fh.read()
    manifest = "\n".join((
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<addons>",
        addon_xml_body(skin_manifest),
        addon_xml_body(repo_manifest),
        "</addons>",
        "",
    ))
    # Prove the combined manifest before it is written: it must parse and
    # list exactly these two add-ons at exactly these versions.
    try:
        listed = {a.get("id"): a.get("version")
                  for a in ET.fromstring(manifest.encode("utf-8")).findall("addon")}
    except ET.ParseError as exc:
        sys.exit(f"ABORTED: the combined addons.xml is not well formed: {exc}")
    wanted = {"skin.functional": skin_version, REPO_ADDON: repo_version}
    if listed != wanted:
        sys.exit(f"ABORTED: addons.xml would list {listed}, expected {wanted}.")
    write_atomic(os.path.join(work, "addons.xml"), manifest)

    digest = hashlib.md5(manifest.encode("utf-8")).hexdigest()
    # Digest only, no trailing newline: Kodi compares the fetched checksum
    # text against its own computation, so any extra byte breaks updates.
    # Written last, so a tree without it is plainly unfinished.
    write_atomic(os.path.join(work, "addons.xml.md5"), digest)

    # Swap the finished tree in. The folder it replaces holds only copies.
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.replace(work, OUT)

    print(f"Wrote addons.xml (skin {skin_version}, repo add-on {repo_version})")
    print(f"Wrote addons.xml.md5 ({digest})")
    print(f"Repo tree ready: {OUT}")


if __name__ == "__main__":
    main()
