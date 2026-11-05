#!/usr/bin/env python3
"""
<summary>
Tests for the settings preview (roadmap item 47), growing with its sub items.
Sub item 1, the groundwork: every flip parameter in Includes_Home.xml defaults
to false, is read only in the exclusive or form that reduces to the plain
setting while false, and is never passed by Home.xml, so Home draws as it
always did; and every settings row has its help entry, which the preview
contract builds on.
</summary>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. The later
sub items add the preview map, the regions, the pictures and the four line
help measure here, as PLAN-settings-preview.md section 5 lays out. Exits
non zero when a check fails.

Usage:
    python3 tests/test_settings_preview.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "skin.functional", "xml")
HOME_INCLUDES = ("HomeStatsColumn", "HomeLogo", "HomeWeather", "HomeClock",
                 "HomeFooter", "HomeContinueTabs")
# Which setting or expression each flip wraps; a flip round the wrong read is a defect.
FLIP_READS = {
    "flip_movies": "Skin.HasSetting(hide_movies_count)",
    "flip_tvshows": "Skin.HasSetting(hide_tvshows_count)",
    "flip_logo": "Skin.HasSetting(hide_logo)",
    "flip_weather": "$EXP[weather_widget_shown]",
    "flip_datetime": "Skin.HasSetting(hide_datetime)",
    "flip_version": "Skin.HasSetting(hide_version)",
    "flip_continue": "$EXP[continue_tab_shown]",
    "flip_recent": "$EXP[recent_tab_shown]",
}
ROW_TYPES = ("button", "radiobutton", "spincontrolex", "spincontrol", "slider", "edit")
TOKEN = r"(?:\$EXP\[\w+\]|[^\[\]|+ ]+)"
# One operand: the exclusive or sits in its own brackets, because Kodi binds
# + tighter than |, and a bare A | B + C would drop the C from the A side.
XOR = re.compile(r"\[\[(!?)(" + TOKEN + r") \+ !\$PARAM\[(flip_\w+)\]\] \| \[(!?)\2 \+ \$PARAM\[\3\]\]\]")

FAILURES = []


def fail(msg):
    """
    <summary>Records one failure; the run carries on so every miss is listed.</summary>
    <param name="msg">What failed, with the file where there is one.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def parse(name):
    """
    <summary>Parses one XML file from the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>Its root element.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def test_flip_parameters():
    """
    <summary>Checks each Home include declares its flips with a false default,
    reads each one only in the exclusive or form, and that Home passes none.</summary>
    """
    print("running test_flip_parameters")
    root = parse("Includes_Home.xml")
    found = {i.get("name") for i in root.findall("include")}
    for name in HOME_INCLUDES:
        if name not in found:
            fail("Includes_Home.xml has no include %s" % name)
    for inc in root.findall("include"):
        declared = {p.get("name"): p.get("default") for p in inc.findall("param")}
        for pname, default in declared.items():
            if not pname.startswith("flip_"):
                fail("%s: parameter %s is not a flip" % (inc.get("name"), pname))
            if default != "false":
                fail("%s: flip %s defaults to %r, not false" % (inc.get("name"), pname, default))
        body = ET.tostring(inc.find("definition"), encoding="unicode")
        used = set(re.findall(r"\$PARAM\[(flip_\w+)\]", body))
        for pname in declared:
            if pname not in used:
                fail("%s: flip %s is declared but never read" % (inc.get("name"), pname))
        for pname in used:
            if pname not in declared:
                fail("%s: flip %s is read but not declared" % (inc.get("name"), pname))
        stripped = XOR.sub("", body)
        stray = re.findall(r"\$PARAM\[(flip_\w+)\]", stripped)
        if stray:
            fail("%s: flips read outside the exclusive or form: %s" % (inc.get("name"), sorted(set(stray))))
        for m in XOR.finditer(body):
            if m.group(1) == m.group(4):
                fail("%s: the two halves of a flip on %s carry the same sign" % (inc.get("name"), m.group(2)))
            if FLIP_READS.get(m.group(3)) != m.group(2):
                fail("%s: flip %s is wrapped round %s, expected %s"
                     % (inc.get("name"), m.group(3), m.group(2), FLIP_READS.get(m.group(3))))
        for pname, token in FLIP_READS.items():
            if pname in declared:
                if token in XOR.sub("", body):
                    fail("%s: %s is read bare somewhere, outside its flip" % (inc.get("name"), token))
        if body.count("[") != body.count("]"):
            fail("%s: unbalanced brackets in its definition" % inc.get("name"))
    home = parse("Home.xml")
    for inc in home.iter("include"):
        if inc.get("content") in HOME_INCLUDES:
            passed = [p.get("name") for p in inc.findall("param")]
            if passed:
                fail("Home.xml passes %s to %s; Home never flips" % (passed, inc.get("content")))
    calls = [i.get("content") for i in home.iter("include") if i.get("content") in HOME_INCLUDES]
    if calls != list(HOME_INCLUDES):
        fail("Home.xml draws the pieces as %s, expected %s" % (calls, list(HOME_INCLUDES)))


def test_every_row_has_a_help_entry():
    """
    <summary>Checks every settings row on every page is in the help expression
    and the help map, which the preview map will mirror.</summary>
    """
    print("running test_every_row_has_a_help_entry")
    settings = parse("SkinSettings.xml")
    rows = []
    for g in settings.iter("control"):
        vis = " ".join((v.text or "") for v in g.findall("visible"))
        if g.get("type") == "group" and "settings_category" in vis:
            for c in g.iter("control"):
                if c.get("type") in ROW_TYPES and c.get("id"):
                    label = c.find("label")
                    if label is None or not (label.text or "").strip():
                        continue  # an unlabeled tap target, not a settings row
                    rows.append(c.get("id"))
    rows = sorted(set(rows))
    helpers = parse("Includes_SettingsHelp.xml")
    shown = next((e.text or "" for e in helpers.iter("expression") if e.get("name") == "settings_help_shown"), "")
    mapped = {m for v in helpers.iter("value") for m in re.findall(r"Control\.HasFocus\((\d+)\)", v.get("condition") or "")}
    listed = set(re.findall(r"Control\.HasFocus\((\d+)\)", shown))
    for rid in rows:
        if rid not in listed:
            fail("row %s is not in settings_help_shown" % rid)
        if rid not in mapped:
            fail("row %s has no line in the help map" % rid)
    print("  %d rows checked" % len(rows))


if __name__ == "__main__":
    test_flip_parameters()
    test_every_row_has_a_help_entry()
    if FAILURES:
        print("test_settings_preview: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_settings_preview: all checks passed")
