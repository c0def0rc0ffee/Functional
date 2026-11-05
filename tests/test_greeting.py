#!/usr/bin/env python3
"""
<summary>
Tests for the Show Greeting switch (roadmap item 38): the helper's part of
day function and publisher, the Home clock variable's structure (the bare
time last with no condition, every greeting value behind the switch and the
room rule, the part of day read from the helper's property, profile variants
first and reading Kodi's own profile name), that nothing but the user's own
click sets the switch, its Home Screen row's help line and strings, and that
the row overlaps nothing on that page.
</summary>
<remarks>
No Kodi is needed. The xbmc modules are stubbed in sys.modules before the
real service.py is imported, so greeting_part and update_greeting are the
shipped code; the Home window stub records what is published. The XML is
parsed with ElementTree. Exits non zero when a check fails.

Usage:
    python3 tests/test_greeting.py
</remarks>
"""

import os
import re
import sys
import types
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
PO = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(SKIN, "service.py")

GATE = "show_greeting"
ON = "Skin.HasSetting(%s)" % GATE
VARIABLE = "HomeClockLine"
ROOM = "$EXP[greeting_room]"
PARTS = ("$EXP[greeting_part_morning]", "$EXP[greeting_part_afternoon]", "$EXP[greeting_part_evening]")
SWITCH_ID = "7319"
HELP_STRING = "31813"
STRINGS = ("31241", "31242", "31243", "31244", "31813")

PUBLISHED = {}
FAILURES = []


class _Window:
    """<summary>Stand in for xbmcgui.Window: records properties set on it.</summary>"""

    def __init__(self, _id=0):
        """<summary>Any window id is accepted.</summary>"""

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Records the property.</summary>"""
        PUBLISHED[key] = value

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Returns a recorded property or an empty string.</summary>"""
        return PUBLISHED.get(key, "")


def _stub_kodi():
    """
    <summary>Installs the xbmc module stubs service.py imports, then imports it.</summary>
    <returns>The imported service module.</returns>
    """
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
    xbmc.log = lambda *a, **k: None
    xbmc.executeJSONRPC = lambda _text: "{}"
    xbmc.getCondVisibility = lambda _text: False
    xbmc.getInfoLabel = lambda _label: ""
    xbmc.getLocalizedString = lambda _sid: ""
    xbmc.executebuiltin = lambda *a, **k: None
    xbmc.getSkinDir = lambda: "skin.functional"
    xbmc.Monitor = type("Monitor", (), {"abortRequested": lambda self: False,
                                        "waitForAbort": lambda self, _t=0: False})
    xbmc.Player = type("Player", (), {"isPlaying": lambda self: False})
    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.Window = _Window
    xbmcgui.Dialog = type("Dialog", (), {})
    xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = (
        "info", "warning", "error")
    xbmcgui.INPUT_ALPHANUM = 0
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda *_a: types.SimpleNamespace(
        getLocalizedString=lambda _sid: "", getAddonInfo=lambda _k: "")
    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda p: p
    xbmcvfs.exists = lambda _p: False
    xbmcvfs.mkdirs = lambda _p: True
    for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon),
                      ("xbmcvfs", xbmcvfs)):
        sys.modules[name] = mod
    sys.path.insert(0, SKIN)
    import service  # noqa: E402
    return service


def fail(msg):
    """
    <summary>Records one failure; the run carries on so every miss is listed.</summary>
    <param name="msg">What failed, with the file where there is one.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def text(el, tag):
    """
    <summary>Returns a child element's text, or an empty string.</summary>
    <param name="el">The parent element.</param>
    <param name="tag">The child's tag.</param>
    <returns>The child's text stripped, or "" when absent.</returns>
    """
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse(name):
    """
    <summary>Parses one XML file from the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>Its root element.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def test_part_of_day(service):
    """
    <summary>Checks every hour maps to the part the changelog states, and
    the publisher writes the property on a change only.</summary>
    <param name="service">The imported service module.</param>
    """
    print("running test_part_of_day")
    for hour in range(24):
        want = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
        got = service.greeting_part(hour)
        if got != want:
            fail("greeting_part(%d) is %r, expected %r" % (hour, got, want))
    helper = object.__new__(service.FunctionalHelper)
    PUBLISHED.clear()
    service.time.localtime = lambda *_a: types.SimpleNamespace(tm_hour=9)
    try:
        helper.update_greeting()
        if PUBLISHED.get("greeting_part") != "morning":
            fail("update_greeting did not publish morning at 09:00")
        PUBLISHED.clear()
        helper.update_greeting()
        if PUBLISHED:
            fail("update_greeting republished an unchanged part")
        service.time.localtime = lambda *_a: types.SimpleNamespace(tm_hour=19)
        helper.update_greeting()
        if PUBLISHED.get("greeting_part") != "evening":
            fail("update_greeting did not publish evening at 19:00")
    finally:
        import time
        service.time.localtime = time.localtime


def test_clock_variable():
    """
    <summary>Checks the clock variable: the last value is the bare time with
    no condition, every other value needs the room rule, which needs the
    switch, the parts come from the helper's property in morning,
    afternoon, evening order, and the profile variants come first and read
    Kodi's profile name.</summary>
    """
    print("running test_clock_variable")
    root = parse("Includes.xml")
    exprs = {e.get("name"): (e.text or "").strip() for e in root.iter("expression")}
    room = exprs.get("greeting_room", "")
    if ON not in room or "menu_position" not in room or "Tile.Count" not in room:
        fail("greeting_room must need the switch and test the menu position and tile count")
    for part in ("morning", "afternoon", "evening"):
        if exprs.get("greeting_part_" + part) != "String.IsEqual(Window(home).Property(greeting_part),%s)" % part:
            fail("expression greeting_part_%s does not read the helper's property" % part)
    var = next((v for v in root.iter("variable") if v.get("name") == VARIABLE), None)
    if var is None:
        fail("Includes.xml has no variable %s" % VARIABLE)
        return
    values = list(var.findall("value"))
    if len(values) != 7:
        fail("%s has %d values, expected 7" % (VARIABLE, len(values)))
        return
    last = values[-1]
    if last.get("condition") or (last.text or "").strip() != "$INFO[System.Time]":
        fail("%s: the last value must be the bare time with no condition" % VARIABLE)
    for v in values[:-1]:
        cond = v.get("condition") or ""
        if ROOM not in cond:
            fail("%s: value %r shows without the room rule" % (VARIABLE, (v.text or "").strip()))
        if "$INFO[System.Time]" not in (v.text or ""):
            fail("%s: value %r drops the time" % (VARIABLE, (v.text or "").strip()))
    conds = [v.get("condition") or "" for v in values[:-1]]
    for i, part in enumerate(PARTS):
        if part not in conds[i] or part not in conds[i + 3]:
            fail("%s: values are not in morning, afternoon, evening order" % VARIABLE)
    for v, c in zip(values[:3], conds[:3]):
        if "Integer.IsGreater(System.ProfileCount,1)" not in c or "$INFO[System.ProfileName]" not in (v.text or ""):
            fail("%s: a profile value lacks the profile count test or Kodi's profile name" % VARIABLE)
    for v in values[3:]:
        if "ProfileName" in (v.text or ""):
            fail("%s: a plain value names the profile" % VARIABLE)
    # The clock lives in the HomeClock include (Includes_Home.xml) since the
    # settings preview groundwork; Home.xml draws it through that include.
    users = [l for name in ("Home.xml", "Includes_Home.xml") for l in parse(name).iter("label")
             if "$VAR[%s]" % VARIABLE in (l.text or "")]
    if len(users) != 1:
        fail("the clock variable should be read by exactly one label, found %d" % len(users))
    home = parse("Home.xml")
    if not any(i.get("content") == "HomeClock" for i in home.iter("include")):
        fail("Home.xml does not draw the HomeClock include")


def test_off_by_default():
    """
    <summary>Proves nothing turns the switch on except the user's own click
    on its radio button in Skin Settings, and the service never reads it.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        with open(os.path.join(XML, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, start=1):
                if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s\)" % GATE, line):
                    writers.append((name, number, line.strip()))
    if len(writers) != 1 or writers[0][0] != "SkinSettings.xml" or "ToggleSetting" not in writers[0][2]:
        fail("expected the toggle in SkinSettings.xml to be the only writer, found %s" % writers)
    with open(SERVICE, encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            if GATE in line:
                fail("service.py:%d reads the switch; the XML alone gates on it" % number)
    root = parse("SkinSettings.xml")
    radios = [c for c in root.iter("control") if c.get("id") == SWITCH_ID]
    if len(radios) != 1 or radios[0].get("type") != "radiobutton":
        fail("expected one radiobutton with id %s in SkinSettings.xml" % SWITCH_ID)
        return
    if text(radios[0], "selected") != ON:
        fail("radiobutton %s does not reflect %s" % (SWITCH_ID, ON))


def test_help_line_and_strings():
    """
    <summary>Checks the switch has its help panel entry in both halves of the
    settings help include, and that its strings exist with a Where line.</summary>
    """
    print("running test_help_line_and_strings")
    root = parse("Includes_SettingsHelp.xml")
    shown = [e for e in root.iter("expression") if e.get("name") == "settings_help_shown"]
    if not shown or "Control.HasFocus(%s)" % SWITCH_ID not in (shown[0].text or ""):
        fail("settings_help_shown does not list control %s" % SWITCH_ID)
    found = any(v.get("condition") == "Control.HasFocus(%s)" % SWITCH_ID
                and (v.text or "").strip() == "$LOCALIZE[%s]" % HELP_STRING
                for v in root.iter("value"))
    if not found:
        fail("the help map has no line for control %s to string %s" % (SWITCH_ID, HELP_STRING))
    with open(PO, encoding="utf-8") as fh:
        po = fh.read()
    for sid in STRINGS:
        if 'msgctxt "#%s"' % sid not in po:
            fail("strings.po has no string %s" % sid)
    m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % HELP_STRING, po)
    if m and "[CR]Where:" not in m.group(1):
        fail("help string %s has no Where line" % HELP_STRING)


def test_home_screen_rows_do_not_overlap():
    """
    <summary>On the settings page holding the switch, checks no two controls
    in the same column overlap vertically.</summary>
    """
    print("running test_home_screen_rows_do_not_overlap")
    root = parse("SkinSettings.xml")
    parent_map = {c: p for p in root.iter() for c in p}
    radio = next((c for c in root.iter("control") if c.get("id") == SWITCH_ID), None)
    if radio is None:
        fail("control %s not found" % SWITCH_ID)
        return
    page = parent_map[radio]
    rows = []
    for c in page:
        if c.tag != "control":
            continue
        try:
            left, top, height = int(text(c, "left")), int(text(c, "top")), int(text(c, "height"))
        except ValueError:
            continue
        if height < 10:
            continue  # a heading's underline rule, not a row
        rows.append((left, top, top + height, c.get("id") or c.get("type")))
    rows.sort()
    checked = 0
    for a, b in zip(rows, rows[1:]):
        if a[0] == b[0]:
            checked += 1
            if b[1] < a[2]:
                fail("settings page: %s (%d to %d) overlaps %s (%d to %d) in the column at %d"
                     % (a[3], a[1], a[2], b[3], b[1], b[2], a[0]))
    print("  %d adjacent pairs checked" % checked)


if __name__ == "__main__":
    SERVICE_MODULE = _stub_kodi()
    test_part_of_day(SERVICE_MODULE)
    test_clock_variable()
    test_off_by_default()
    test_help_line_and_strings()
    test_home_screen_rows_do_not_overlap()
    if FAILURES:
        print("test_greeting: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_greeting: all checks passed")
