#!/usr/bin/env python3
"""
<summary>
Tests for the settings preview (roadmap item 47), growing with its sub items.
Sub item 1, the groundwork: every flip parameter in Includes_Home.xml defaults
to false, is read only in the exclusive or form that reduces to the plain
setting while false, and is never passed by Home.xml, so Home draws as it
always did. Sub item 2: the Preview Settings switch is off by default and
set only by its own row, the stage wires every flip to the focus of the row
that switches that setting, every Home Screen row is in the preview map and
in exactly one stage region, and every settings row has its help entry.
</summary>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. The flip
on the greeting is a pair of labels rather than an exclusive or, because the
greeting switch is read inside a variable, so that one flip is checked as a
pair. The later sub items add the other pages' regions, the pictures and the
four line help measure here, as PLAN-settings-preview.md section 5 lays out.
Exits non zero when a check fails.

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
                 "HomeMenu", "HomeFooter", "HomeContinueTabs")
# Which setting or expression each flip wraps; a flip round the wrong read is a defect.
FLIP_READS = {
    "flip_movies": "Skin.HasSetting(hide_movies_count)",
    "flip_tvshows": "Skin.HasSetting(hide_tvshows_count)",
    "flip_logo": "Skin.HasSetting(hide_logo)",
    "flip_weather": "$EXP[weather_widget_shown]",
    "flip_datetime": "Skin.HasSetting(hide_datetime)",
    "flip_version": "Skin.HasSetting(hide_version)",
    "flip_continue": "$PARAM[shown_continue]",
    "flip_recent": "$PARAM[shown_recent]",
}
# A flip done as a pair of labels, plain and flipped, rather than an exclusive or.
PAIR_FLIPS = {"flip_greeting": ("$VAR[HomeClockLine]", "$VAR[HomeClockLineFlipped]")}
# Which Skin Settings row each flip follows in the stage.
STAGE_FLIPS = {
    "flip_movies": "7107", "flip_tvshows": "7108", "flip_logo": "7104", "flip_weather": "7122",
    "flip_datetime": "7106", "flip_greeting": "7319", "flip_version": "7105",
    "flip_continue": "7128", "flip_recent": "7144",
}
SWITCH = "settings_preview"
SWITCH_ID = "7322"
HELP_STRING = "31814"
STAGE_PAGES = ("home",)
ROW_TYPES = ("button", "radiobutton", "spincontrolex", "spincontrol", "slider", "edit")
TOKEN = r"(?:\$EXP\[\w+\]|\$PARAM\[\w+\]|[^\[\]|+ ]+)"
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
        flips = {k: v for k, v in declared.items() if k.startswith("flip_")}
        for pname, default in flips.items():
            if default != "false":
                fail("%s: flip %s defaults to %r, not false" % (inc.get("name"), pname, default))
        body = ET.tostring(inc.find("definition"), encoding="unicode")
        used = set(re.findall(r"\$PARAM\[(flip_\w+)\]", body))
        for pname in flips:
            if pname not in used:
                fail("%s: flip %s is declared but never read" % (inc.get("name"), pname))
        for pname in used:
            if pname not in flips:
                fail("%s: flip %s is read but not declared" % (inc.get("name"), pname))
        stripped = XOR.sub("", body)
        for pname in set(re.findall(r"\$PARAM\[(flip_\w+)\]", stripped)):
            if pname in PAIR_FLIPS:
                plain, flipped = PAIR_FLIPS[pname]
                if stripped.count("!$PARAM[%s]" % pname) != 1 or stripped.count("$PARAM[%s]" % pname) != 2:
                    fail("%s: pair flip %s must be read once plain and once negated" % (inc.get("name"), pname))
                if plain not in body or flipped not in body:
                    fail("%s: pair flip %s must draw %s and %s" % (inc.get("name"), pname, plain, flipped))
            else:
                fail("%s: flip %s is read outside the exclusive or form" % (inc.get("name"), pname))
        for m in XOR.finditer(body):
            if m.group(1) == m.group(4):
                fail("%s: the two halves of a flip on %s carry the same sign" % (inc.get("name"), m.group(2)))
            if FLIP_READS.get(m.group(3)) != m.group(2):
                fail("%s: flip %s is wrapped round %s, expected %s"
                     % (inc.get("name"), m.group(3), m.group(2), FLIP_READS.get(m.group(3))))
        for pname, token in FLIP_READS.items():
            if pname in flips:
                if token in XOR.sub("", body):
                    fail("%s: %s is read bare somewhere, outside its flip" % (inc.get("name"), token))
        if body.count("[") != body.count("]"):
            fail("%s: unbalanced brackets in its definition" % inc.get("name"))
    home = parse("Home.xml")
    for inc in home.iter("include"):
        if inc.get("content") in HOME_INCLUDES:
            passed = [p.get("name") for p in inc.findall("param") if p.get("name", "").startswith("flip_")]
            if passed:
                fail("Home.xml passes %s to %s; Home never flips" % (passed, inc.get("content")))
    calls = [i.get("content") for i in home.iter("include") if i.get("content") in HOME_INCLUDES]
    if calls != list(HOME_INCLUDES):
        fail("Home.xml draws the pieces as %s, expected %s" % (calls, list(HOME_INCLUDES)))


def focus_ids(text):
    """
    <summary>Reads the control ids named by Control.HasFocus in an expression.</summary>
    <param name="text">The expression text.</param>
    <returns>The set of ids as strings.</returns>
    """
    return set(re.findall(r"Control\.HasFocus\((\d+)\)", text or ""))


def settings_rows(settings):
    """
    <summary>Lists the labelled settings rows per page of SkinSettings.xml.</summary>
    <param name="settings">The parsed window.</param>
    <returns>A dict of page name to sorted list of row ids.</returns>
    """
    pages = {}
    for g in settings.iter("control"):
        vis = " ".join((v.text or "") for v in g.findall("visible"))
        m = re.search(r"settings_category\),(\w+)", vis)
        if g.get("type") != "group" or not m or m.group(1) in pages:
            continue
        rows = []
        for c in g.iter("control"):
            if c.get("type") in ROW_TYPES and c.get("id"):
                label = c.find("label")
                if label is None or not (label.text or "").strip():
                    continue  # an unlabeled tap target, not a settings row
                rows.append(c.get("id"))
        pages[m.group(1)] = sorted(set(rows))
    return pages


def test_stage_wiring():
    """
    <summary>Checks the stage passes every flip as the focus of the row that
    switches that setting, and gives Home's id bearing pieces ids of its own.</summary>
    """
    print("running test_stage_wiring")
    root = parse("Includes_Home.xml")
    stage = next((i for i in root.findall("include") if i.get("name") == "HomeStage"), None)
    if stage is None:
        fail("Includes_Home.xml has no HomeStage include")
        return
    passed = {}
    for inc in stage.iter("include"):
        for p in inc.findall("param"):
            if p.get("name", "").startswith("flip_"):
                passed[p.get("name")] = p.get("value")
    for pname, row in STAGE_FLIPS.items():
        if passed.get(pname) != "Control.HasFocus(%s)" % row:
            fail("HomeStage passes %s as %r, expected the focus of row %s" % (pname, passed.get(pname), row))
    for pname in passed:
        if pname not in STAGE_FLIPS:
            fail("HomeStage passes an unknown flip %s" % pname)
    settings = parse("SkinSettings.xml")
    settings_ids = {c.get("id") for c in settings.iter("control") if c.get("id")}
    stage_ids = set()
    for inc in stage.iter("include"):
        for p in inc.findall("param"):
            if p.get("name", "").startswith("id") and (p.get("value") or "").isdigit():
                stage_ids.add(p.get("value"))
    clash = stage_ids & settings_ids
    if clash:
        fail("HomeStage ids collide with Skin Settings ids: %s" % sorted(clash))
    menu = next((i for i in stage.iter("include") if i.get("content") == "HomeMenu"), None)
    if menu is None or {p.get("name"): p.get("value") for p in menu.findall("param")} != {"id": "9900", "p": "99"}:
        fail("HomeStage must draw HomeMenu with id 9900 and tile prefix 99")


def test_switch_off_by_default():
    """
    <summary>Proves nothing turns Preview Settings on except its own row, that
    the panel and both help heights hang on the switch, and that the service
    never touches it.</summary>
    """
    print("running test_switch_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        with open(os.path.join(XML, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, start=1):
                if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s\)" % SWITCH, line):
                    writers.append((name, number))
    if len(writers) != 1 or writers[0][0] != "SkinSettings.xml":
        fail("expected the toggle in SkinSettings.xml to be the only writer, found %s" % writers)
    with open(os.path.join(ROOT, "skin.functional", "service.py"), encoding="utf-8") as fh:
        if SWITCH in fh.read():
            fail("service.py mentions the switch; it is skin XML only")
    settings = parse("SkinSettings.xml")
    radios = [c for c in settings.iter("control") if c.get("id") == SWITCH_ID]
    if len(radios) != 1 or (radios[0].find("selected").text or "").strip() != "Skin.HasSetting(%s)" % SWITCH:
        fail("radiobutton %s must reflect Skin.HasSetting(%s)" % (SWITCH_ID, SWITCH))
    preview = parse("Includes_SettingsPreview.xml")
    shown = next((e.text for e in preview.iter("expression") if e.get("name") == "preview_panel_shown"), "")
    if "Skin.HasSetting(%s)" % SWITCH not in (shown or ""):
        fail("preview_panel_shown does not need the switch")
    stage_calls = [i for i in settings.iter("include") if i.get("content") == "HomeStage"]
    if len(stage_calls) != 1:
        fail("SkinSettings.xml should draw HomeStage once, found %d" % len(stage_calls))
    labels = [l for l in settings.iter("control") if l.get("type") in ("label", "textbox")
              and any("$VAR[SettingsHelp]" in (x.text or "") for x in l.findall("label"))]
    heights = sorted((l.get("type"), l.find("height").text, (l.find("visible").text or "").strip()) for l in labels)
    if heights != [("label", "256", "!$EXP[preview_panel_shown]"), ("textbox", "106", "$EXP[preview_panel_shown]")]:
        fail("the help must be a 256 tall label with the panel hidden and a 106 tall scrolling textbox with it shown, found %s" % heights)


def test_preview_map():
    """
    <summary>Checks every row on the stage pages is either on the stage, in the
    preview map and exactly one region, or a picture row kept off the stage,
    and that every mapped id is a real row.</summary>
    """
    print("running test_preview_map")
    settings = parse("SkinSettings.xml")
    pages = settings_rows(settings)
    all_rows = {r for rows in pages.values() for r in rows}
    preview = parse("Includes_SettingsPreview.xml")
    exprs = {e.get("name"): e.text or "" for e in preview.iter("expression")}
    shown = focus_ids(exprs.get("settings_preview_shown"))
    regions = {n: focus_ids(x) for n, x in exprs.items() if n.startswith("stage_region_")}
    images = focus_ids(exprs.get("settings_preview_image"))
    for page in STAGE_PAGES:
        for rid in pages.get(page, []):
            homes = [n for n, ids in regions.items() if rid in ids]
            if rid in images:
                # the picture form: no stage, and no panel until sub item 4 ships its pictures
                if homes or rid in shown:
                    fail("row %s on page %s is a picture row and must not be on the stage" % (rid, page))
                continue
            if rid not in shown:
                fail("row %s on page %s is not in settings_preview_shown" % (rid, page))
            if len(homes) != 1:
                fail("row %s on page %s is in %d stage regions, expected one" % (rid, page, len(homes)))
    for rid in shown | images | {i for ids in regions.values() for i in ids}:
        if rid not in all_rows:
            fail("preview map names %s, which is not a settings row" % rid)
    print("  %d regions, %d rows mapped" % (len(regions), len(shown)))


def test_every_row_has_a_help_entry():
    """
    <summary>Checks every settings row on every page is in the help expression
    and the help map, which the preview map will mirror.</summary>
    """
    print("running test_every_row_has_a_help_entry")
    settings = parse("SkinSettings.xml")
    rows = sorted({r for rs in settings_rows(settings).values() for r in rs})
    helpers = parse("Includes_SettingsHelp.xml")
    shown = next((e.text or "" for e in helpers.iter("expression") if e.get("name") == "settings_help_shown"), "")
    mapped = {m for v in helpers.iter("value") for m in focus_ids(v.get("condition"))}
    listed = focus_ids(shown)
    for rid in rows:
        if rid not in listed:
            fail("row %s is not in settings_help_shown" % rid)
        if rid not in mapped:
            fail("row %s has no line in the help map" % rid)
    if SWITCH_ID not in mapped:
        fail("the switch row has no help line")
    with open(os.path.join(ROOT, "skin.functional", "language", "resource.language.en_gb", "strings.po"), encoding="utf-8") as fh:
        po = fh.read()
    if 'msgctxt "#%s"' % HELP_STRING not in po:
        fail("strings.po has no help string %s" % HELP_STRING)
    print("  %d rows checked" % len(rows))


if __name__ == "__main__":
    test_flip_parameters()
    test_stage_wiring()
    test_switch_off_by_default()
    test_preview_map()
    test_every_row_has_a_help_entry()
    if FAILURES:
        print("test_settings_preview: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_settings_preview: all checks passed")
