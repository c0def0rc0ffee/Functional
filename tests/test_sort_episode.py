#!/usr/bin/env python3
"""
<summary>
Tests for SORT-EPISODE (11/11/2026): the Sort menu in MyVideoNav has an
Episode button that shows only in an episode list and puts the list back in
Kodi's episode order.
</summary>
<remarks>
Kodi keeps one sort for every episode list (the videonavepisodes view state),
so a Rating picked in one show left every show by rating, and the menu had no
way back. No Kodi is needed: MyVideoNav.xml is parsed, the strings file and
service.py are read as text. The checks cover the button's sort id, its
visibility, the up and down navigation around it in both states, its string,
and the service knowing the sort so the direction and the tracker follow it.
Whether Kodi takes sort 23 in a real episode list is the live check's job.
Exits non zero when a check fails.

Usage:
    python3 tests/test_sort_episode.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
NAV = os.path.join(SKIN, "xml", "MyVideoNav.xml")
PO = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(SKIN, "service.py")

FAILURES = []


def check(ok, msg):
    """
    <summary>Records one check; a failure is printed and the run carries on.</summary>
    <param name="ok">Whether the check passed.</param>
    <param name="msg">What was checked.</param>
    """
    if not ok:
        FAILURES.append(msg)
        print("FAIL: " + msg)


def control(root, cid):
    """
    <summary>Finds a control by id anywhere in the window.</summary>
    <param name="root">The parsed window.</param>
    <param name="cid">The control id as text.</param>
    <returns>The element, or None.</returns>
    """
    for element in root.iter("control"):
        if element.get("id") == cid:
            return element
    return None


def moves(element, tag):
    """
    <summary>A control's navigation targets for one direction.</summary>
    <param name="element">The control.</param>
    <param name="tag">onup or ondown.</param>
    <returns>(condition, target) pairs, the condition "" when there is none.</returns>
    """
    return [(e.get("condition", ""), (e.text or "").strip()) for e in element.findall(tag)]


def main():
    """
    <summary>Runs every check and exits non zero if any failed.</summary>
    <returns>The exit code.</returns>
    """
    print("running test_sort_episode")
    root = ET.parse(NAV).getroot()
    button = control(root, "8036")
    check(button is not None, "the Episode button 8036 exists")
    if button is not None:
        clicks = [(e.text or "").strip() for e in button.findall("onclick")]
        check("Container.SetSortMethod(23)" in clicks, "it sorts by episode number (23)")
        check("Skin.SetString(sort_want,asc)" in clicks, "first to last")
        check("Skin.SetString(sort_active,episode)" in clicks, "and tells the tracker")
        visible = (button.findtext("visible") or "").replace(" ", "")
        check("Container.Content(episodes)" in visible and "Skin.HasSetting(sort_menu_open)" in visible,
              "it shows only in an episode list with the Sort menu open")
        check((button.findtext("label") or "").strip() == "31880", "its label is string 31880")
        check(moves(button, "onup") == [("", "8002")] and moves(button, "ondown") == [("", "8031")],
              "it sits between Sort and Title")
    sort = control(root, "8002")
    title = control(root, "8031")
    check(moves(sort, "ondown") == [("Control.IsVisible(8036)", "8036"), ("!Control.IsVisible(8036)", "8031")],
          "down from Sort goes to Episode when it shows, else Title")
    check(moves(title, "onup") == [("Control.IsVisible(8036)", "8036"), ("!Control.IsVisible(8036)", "8002")],
          "up from Title goes to Episode when it shows, else Sort")
    children = [c.get("id") for c in list(root.iter("control")) if c.get("id") in ("8002", "8036", "8031")]
    check(children == ["8002", "8036", "8031"], "it is drawn between Sort and Title")

    with open(PO, encoding="utf-8") as handle:
        po = handle.read()
    check(re.search(r'msgctxt "#31880"\nmsgid "Episode"\n', po) is not None, "string 31880 reads Episode")

    with open(SERVICE, encoding="utf-8") as handle:
        service = handle.read()
    check('"episode": 23' in service, "the service knows the episode sort id")
    check('"episode": "asc"' in service, "and its natural direction")

    if FAILURES:
        print("{0} check(s) failed".format(len(FAILURES)))
        return 1
    print("test_sort_episode: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
