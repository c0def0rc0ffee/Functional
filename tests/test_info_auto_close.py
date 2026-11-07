#!/usr/bin/env python3
"""
<summary>
Tests for the fullscreen info card's timed close and title logo (roadmap
item 19): the card starts its close alarm only when a time is chosen, in
the minutes and seconds form the alarm needs, and has an onunload that
cancels it; the picker cycles Off and four times, recovers from any other
value, and is the only writer of its string; the logo and the year above
it draw only with the logo switch on, for a library film with a logo,
exactly where the title then stands down;
the two settings rows have their labels, help lines and form None, and lead
to and from their neighbours.
</summary>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. Whether
Kodi closes the card on time, and how a logo looks, is the live check's
job, and the logo is only seen there on a library film, so no picture of it
ships. Exits non zero when a check fails.

Usage:
    python3 tests/test_info_auto_close.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
STRINGS = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
TIME = "fsinfo_close"
LOGO = "fsinfo_logo"
VALUES = ["05", "10", "20", "30"]
FILM = "String.IsEmpty(VideoPlayer.TVShowTitle)"
HAS_LOGO = "!String.IsEmpty(Player.Art(clearlogo))"
MOVIE = "VideoPlayer.Content(movies)"
LOGO_ON = "Skin.HasSetting(%s) + %s + %s" % (LOGO, MOVIE, HAS_LOGO)
FAILURES = []


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def read(name):
    """
    <summary>Reads one skin XML file as text.</summary>
    <param name="name">The file name under xml/.</param>
    <returns>The text.</returns>
    """
    with open(os.path.join(XML, name), encoding="utf-8") as handle:
        return handle.read()


def body():
    """
    <summary>The FsInfoCardBody include, parsed.</summary>
    <returns>The include element.</returns>
    """
    for inc in ET.fromstring(read("Includes.xml")).iter("include"):
        if inc.get("name") == "FsInfoCardBody":
            return inc
    raise SystemExit("FsInfoCardBody is missing")


def test_timer():
    """
    <summary>Checks the card's onload starts the alarm only when a time is
    set, as 00:SS so Kodi reads seconds, closing this dialog, and that the
    onunload cancels it silently.</summary>
    """
    print("running test_timer")
    root = ET.fromstring(read("DialogFullScreenInfo.xml"))
    loads = root.findall("onload")
    if len(loads) != 1 or loads[0].get("condition") != "!String.IsEmpty(Skin.String(%s))" % TIME:
        fail("the card should start its alarm only when %s is set" % TIME)
    elif loads[0].text != "AlarmClock(%s,Dialog.Close(fullscreeninfo),00:$INFO[Skin.String(%s)],silent)" % (TIME, TIME):
        fail("the alarm reads %r" % loads[0].text)
    if root.findtext("onunload") != "CancelAlarm(%s,true)" % TIME:
        fail("the card does not cancel its alarm when it closes")


def test_picker():
    """
    <summary>Checks the picker cycles Off, 05, 10, 20, 30 and back to Off,
    any other value goes back to Off, each value has a label, and nothing
    else in the skin writes the string.</summary>
    """
    print("running test_picker")
    settings = {n.get("id"): n for n in ET.fromstring(read("SkinSettings.xml")).iter("control") if n.get("id")}
    row = settings.get("7325")
    if row is None:
        fail("row 7325 is missing")
        return
    cycle, fallback = {}, []
    others = "!String.IsEmpty(Skin.String(%s))" % TIME + "".join(
        " + !String.IsEqual(Skin.String(%s),%s)" % (TIME, v) for v in VALUES)
    for click in row.findall("onclick"):
        cond = click.get("condition") or ""
        if cond == others:
            fallback.append(click.text)
            continue
        frm = "" if cond == "String.IsEmpty(Skin.String(%s))" % TIME else \
            (re.fullmatch(r"String\.IsEqual\(Skin\.String\(%s\),(\d+)\)" % TIME, cond) or [None, "?"])[1]
        to = "" if click.text == "Skin.Reset(%s)" % TIME else \
            (re.fullmatch(r"Skin\.SetString\(%s,(\d+)\)" % TIME, click.text or "") or [None, "?"])[1]
        cycle[frm] = to
    if cycle != dict(zip([""] + VALUES, VALUES + [""])):
        fail("the picker cycles %s" % cycle)
    if fallback != ["Skin.Reset(%s)" % TIME]:
        fail("an unexpected value does not go back to Off on OK")
    var = re.search(r'<variable name="FsInfoCloseLabel">(.*?)</variable>', read("Includes.xml"), re.S)
    for v in VALUES:
        if not var or 'String.IsEqual(Skin.String(%s),%s)">%ds</value>' % (TIME, v, int(v)) not in var.group(1):
            fail("FsInfoCloseLabel has no %ds for %s" % (int(v), v))
    if not var or "<value>$LOCALIZE[31103]</value>" not in var.group(1):
        fail("FsInfoCloseLabel does not fall back to Off")
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml") and name != "SkinSettings.xml" and \
                re.search(r"Skin\.(SetString|Reset)\(%s[,)]" % TIME, read(name)):
            fail("%s writes %s" % (name, TIME))


def test_logo():
    """
    <summary>Checks the logo and the year above it draw only for a library
    film (VideoPlayer.Content(movies)) with a logo while the switch is on,
    the title without an episode stands down exactly then,
    the episode title is untouched, nothing but the row toggles the switch,
    and the logo keeps between the year and the metadata row.</summary>
    """
    print("running test_logo")
    inc = body()
    logos = [n for n in inc.iter("control") if n.get("type") == "image" and "clearlogo" in (n.findtext("texture") or "")]
    years = [n for n in inc.iter("control") if n.get("type") == "label" and n.findtext("label") == "$INFO[VideoPlayer.Year]"]
    if len(logos) != 1 or len(years) != 1:
        fail("expected one logo image and one year label, found %d and %d" % (len(logos), len(years)))
        return
    for node in logos + years:
        if node.findtext("visible") != LOGO_ON:
            fail("a logo control shows on %r" % node.findtext("visible"))
    titles = [n for n in inc.iter("control") if n.get("type") == "label" and
              (n.findtext("label") or "").startswith("$INFO[VideoPlayer.Title]")]
    film = [t for t in titles if "Year" in t.findtext("label")]
    episode = [t for t in titles if "Year" not in t.findtext("label")]
    if len(film) != 1 or film[0].findtext("visible") != "%s + ![%s]" % (FILM, LOGO_ON):
        fail("the film title does not stand down exactly where the logo shows")
    if len(episode) != 1 or episode[0].findtext("visible") != "!" + FILM:
        fail("the episode title has changed")
    logo, year = logos[0], years[0]
    if int(year.findtext("top")) + int(year.findtext("height")) > int(logo.findtext("top")) or \
            int(logo.findtext("top")) + int(logo.findtext("height")) > 112:
        fail("the logo overlaps the year above it or the metadata row at 112")
    if logo.find("aspectratio") is None or logo.findtext("aspectratio") != "keep":
        fail("the logo does not keep its shape")
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml") and name != "SkinSettings.xml" and \
                re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s[,)]" % LOGO, read(name)):
            fail("%s writes %s" % (name, LOGO))
    for folder, _, files in os.walk(SKIN):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    text = handle.read()
                if LOGO in text or TIME in text:
                    fail("%s mentions an item 19 setting; the skin's Python must not touch them" % name)


def test_rows():
    """
    <summary>Checks rows 7325 and 7326: labels, help lines with a Where line,
    form None, the right column under 7324 clear of the text below, Up and
    Down between them and 7324, and Left to the rows beside them.</summary>
    <remarks>Right from the left column goes to the top of the right column,
    as everywhere on the page, so it is not checked to reach these rows.</remarks>
    """
    print("running test_rows")
    settings = {n.get("id"): n for n in ET.fromstring(read("SkinSettings.xml")).iter("control") if n.get("id")}
    picker, toggle, above = settings.get("7325"), settings.get("7326"), settings.get("7324")
    if picker is None or toggle is None or above is None:
        fail("row 7324, 7325 or 7326 is missing")
        return
    if toggle.findtext("selected") != "Skin.HasSetting(%s)" % LOGO or toggle.findtext("onclick") != "Skin.ToggleSetting(%s)" % LOGO:
        fail("row 7326 does not show and toggle %s" % LOGO)
    if picker.findtext("label") != "$LOCALIZE[31826] $VAR[FsInfoCloseLabel]" or toggle.findtext("label") != "31828":
        fail("the rows' labels are wrong")
    with open(STRINGS, encoding="utf-8") as handle:
        strings = handle.read()
    help_text = read("Includes_SettingsHelp.xml")
    shown = re.search(r'name="settings_help_shown">(.*)</expression>', help_text)
    preview = read("Includes_SettingsPreview.xml")
    none = re.search(r'name="settings_preview_none">(.*)</expression>', preview)
    for rid in ("7325", "7326"):
        if not shown or "Control.HasFocus(%s)" % rid not in shown.group(1):
            fail("settings_help_shown does not list row %s" % rid)
        entry = re.search(r'Control\.HasFocus\(%s\)">\$LOCALIZE\[(\d+)\]' % rid, help_text)
        line = entry and re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
        if not line or "[CR]Where: " not in line.group(1):
            fail("row %s has no help with a Where line" % rid)
        if not none or "Control.HasFocus(%s)" % rid not in none.group(1):
            fail("row %s is not in settings_preview_none" % rid)
    for row, prev in ((picker, above), (toggle, picker)):
        if row.findtext("left") != "1380" or int(row.findtext("top")) != int(prev.findtext("top")) + 80:
            fail("row %s is not straight under row %s" % (row.get("id"), prev.get("id")))
        if int(row.findtext("top")) + int(row.findtext("height")) > 680:
            fail("row %s runs into the caching note at y 680" % row.get("id"))
    nav = {
        "7324": ("ondown", "7325"), "7325": ("onup", "7324"),
    }
    for rid, (tag, want) in nav.items():
        if settings[rid].findtext(tag) != want:
            fail("%s from row %s should reach %s" % (tag, rid, want))
    if picker.findtext("ondown") != "7326" or toggle.findtext("onup") != "7325" or toggle.find("ondown") is not None:
        fail("rows 7325 and 7326 do not lead to each other, or 7326 leads further down")
    if picker.findtext("onleft") != "7304" or toggle.findtext("onleft") != "7305" or \
            picker.find("onright") is not None or toggle.find("onright") is not None:
        fail("left from 7325 and 7326 should reach the rows beside them, and right nowhere")


if __name__ == "__main__":
    test_timer()
    test_picker()
    test_logo()
    test_rows()
    if FAILURES:
        print("test_info_auto_close: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_info_auto_close: all checks passed")
