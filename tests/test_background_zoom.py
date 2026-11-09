#!/usr/bin/env python3
"""
<summary>
Tests for the slow zoom on the background (roadmap item 37): the switch is off
by default and only its own row writes it, the zoom draws nothing while it is
off, Reduce Motion stops it, it sits on the picture layers only and never on
the dim, the captions or the theme layers, and its Skin Settings row has its
strings, its help line and its place on the preview stage.
</summary>
<remarks>
No Kodi is needed. The zoom's condition is evaluated over every combination of
the switch, Reduce Motion and the stage's flip by turning Kodi's boolean
syntax into Python, so "draws nothing while off" is proved rather than read.
Whether the zoom looks right is the live check's job. Exits non zero when a
check fails.

Usage:
    python3 tests/test_background_zoom.py
</remarks>
"""

import itertools
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "skin.functional", "xml")
PO = os.path.join(ROOT, "skin.functional", "language",
                  "resource.language.en_gb", "strings.po")

SETTING = "bg_zoom"
ROW_ID = "7138"
LABEL = "31876"
HELP = "31877"
# <summary>The picture layers of SkinBackground, by the texture each draws.</summary>
PICTURES = ("Window(home).Property(home_bg_fanart)", "Skin.String(home_background)")
SCREEN_W, SCREEN_H = 1920, 1080

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


def include(root, name):
    """
    <summary>Finds a named include definition.</summary>
    <param name="root">The parsed includes file.</param>
    <param name="name">The include's name.</param>
    <returns>The include element, or None.</returns>
    """
    return next((i for i in root.findall("include") if i.get("name") == name), None)


def evaluate(expr, values):
    """
    <summary>Evaluates a Kodi boolean expression over given truth values.</summary>
    <param name="expr">The expression, with brackets, + for and, | for or and ! for not.</param>
    <param name="values">A dict of each operand's text to its truth value.</param>
    <returns>The expression's value.</returns>
    <exception cref="KeyError">An operand has no value given, so the test
    would otherwise guess.</exception>
    <remarks>Kodi binds + tighter than |, as Python binds and tighter than or.</remarks>
    """
    out = []
    for tok in re.findall(r"\$PARAM\[\w+\]|\[|\]|\+|\||!|[^\[\]+|!\s]+(?:\([^)]*\))?", expr):
        out.append({"[": "(", "]": ")", "+": " and ", "|": " or ", "!": " not "}.get(tok)
                   or str(values[tok]))
    return eval("".join(out), {"__builtins__": {}})


def test_zoom_animation():
    """
    <summary>Checks BgZoom is one pulsing zoom that covers the screen, draws
    nothing while the switch is off, stops under Reduce Motion, and shows on
    the stage only when the flip turns it on.</summary>
    """
    print("running test_zoom_animation")
    inc = include(parse("Includes.xml"), "BgZoom")
    if inc is None:
        fail("Includes.xml has no BgZoom include")
        return
    params = {p.get("name"): p.get("default") for p in inc.findall("param")}
    if params != {"flip_zoom": "false"}:
        fail("BgZoom should declare only flip_zoom, default false, found %s" % params)
    anims = inc.findall("definition/animation")
    if len(anims) != 1:
        fail("BgZoom should hold one animation, found %d" % len(anims))
        return
    a = anims[0]
    if a.get("effect") != "zoom" or (a.text or "").strip() != "Conditional" or a.get("pulse") != "true":
        fail("BgZoom must be a pulsing conditional zoom")
    # reversible, Kodi would ease the picture back for up to a whole pass once
    # the switch or Reduce Motion stops it, which is motion Reduce Motion forbids
    if a.get("reversible") != "false":
        fail("BgZoom must not be reversible, so it stops at once")
    if a.get("start") != "100" or not 100 < float(a.get("end", "0")) <= 120:
        fail("the zoom must run from 100 to a little over 100, found %s to %s" % (a.get("start"), a.get("end")))
    cx, cy = (float(v) for v in a.get("center", "-1,-1").split(","))
    # zooming in about a point on the screen keeps every edge outside the screen
    if not (0 <= cx <= SCREEN_W and 0 <= cy <= SCREEN_H):
        fail("the zoom centre %s,%s is off the screen, so an edge would show" % (cx, cy))
    if int(a.get("time", "0")) < 10000:
        fail("the zoom must be slow, found %s ms" % a.get("time"))
    cond = a.get("condition", "")
    for on, reduce_motion, flip in itertools.product((False, True), repeat=3):
        values = {"Skin.HasSetting(%s)" % SETTING: on, "Skin.HasSetting(reduce_motion)": reduce_motion,
                  "$PARAM[flip_zoom]": flip}
        got = evaluate(cond, values)
        want = (on != flip) and not reduce_motion
        if got != want:
            fail("zoom condition with setting=%s reduce_motion=%s flip=%s gives %s, expected %s"
                 % (on, reduce_motion, flip, got, want))


def test_zoom_placement():
    """
    <summary>Checks the zoom is inside each picture layer and nowhere else: not
    on the dim overlay, the video, the captions or the seasonal layers.</summary>
    """
    print("running test_zoom_placement")
    root = parse("Includes.xml")
    bg = include(root, "SkinBackground")
    folder = include(root, "FolderSlideshow")
    if bg is None or folder is None:
        fail("Includes.xml lacks SkinBackground or FolderSlideshow")
        return
    if {p.get("name"): p.get("default") for p in bg.findall("param")}.get("flip_zoom") != "false":
        fail("SkinBackground must declare flip_zoom with a false default")
    zoomed = []
    for c in bg.iter("control"):
        has = any(i.get("content") == "BgZoom" for i in c.findall("include"))
        tex = c.find("texture")
        tex = tex.text if tex is not None else ""
        if has:
            zoomed.append(tex)
        elif any(p in (tex or "") for p in PICTURES):
            fail("the picture layer drawing %s has no zoom" % tex)
    if sorted(zoomed) != sorted("$INFO[%s]" % p for p in PICTURES):
        fail("the zoom sits on %s, expected the two picture layers only" % zoomed)
    multi = folder.findall("definition/control")
    if len(multi) != 1 or multi[0].get("type") != "multiimage" or \
            [i.get("content") for i in multi[0].findall("include")] != ["BgZoom"]:
        fail("FolderSlideshow's multiimage must carry the zoom")
    calls = [i for i in bg.iter("include") if i.get("content") in ("FolderSlideshow", "BgZoom")]
    for call in calls:
        passed = {p.get("name"): p.get("value") for p in call.findall("param")}
        if passed.get("flip_zoom") != "$PARAM[flip_zoom]":
            fail("SkinBackground's %s call does not pass the flip through" % call.get("content"))
    # parsed, not matched as text, so a use written any other way is counted too
    users = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            users += [name for i in parse(name).iter("include")
                      if (i.get("content") or (i.text or "").strip()) == "BgZoom"]
    if users != ["Includes.xml"] * 3:
        fail("BgZoom should be used three times, all in Includes.xml, found %s" % users)


def test_off_by_default():
    """
    <summary>Proves only the row's own toggle writes the setting, that no Python
    file in the skin touches it, and that Home never flips it.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        with open(os.path.join(XML, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, start=1):
                # SetBool takes an optional value, Skin.SetBool(bg_zoom,true)
                if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(\s*%s\s*[,)]" % SETTING, line):
                    writers.append((name, number))
    if len(writers) != 1 or writers[0][0] != "SkinSettings.xml":
        fail("expected the toggle in SkinSettings.xml to be the only writer, found %s" % writers)
    skin = os.path.dirname(XML)
    for folder, _dirs, files in os.walk(skin):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    if SETTING in fh.read():
                        fail("%s mentions %s; the zoom is skin XML only" % (os.path.relpath(os.path.join(folder, name), skin), SETTING))
    for inc in parse("Home.xml").iter("include"):
        if inc.get("content") == "SkinBackground" and any(p.get("name") == "flip_zoom" for p in inc.findall("param")):
            fail("Home.xml passes flip_zoom; Home never flips")


def test_settings_row():
    """
    <summary>Checks the row on the Background page, its strings, its help line
    with a Where line, and that the stage flips it.</summary>
    """
    print("running test_settings_row")
    settings = parse("SkinSettings.xml")
    rows = [c for c in settings.iter("control") if c.get("id") == ROW_ID]
    if len(rows) != 1:
        fail("expected one control %s in SkinSettings.xml, found %d" % (ROW_ID, len(rows)))
        return
    row = rows[0]
    page = next((g for g in settings.iter("control") if g.get("type") == "group"
                 and "settings_category),background)" in " ".join(v.text or "" for v in g.findall("visible"))
                 and row in list(g.iter("control"))), None)
    if page is None:
        fail("row %s is not on the Background page" % ROW_ID)
    checks = {"type": (row.get("type"), "radiobutton"),
              "label": ((row.findtext("label") or "").strip(), LABEL),
              "selected": ((row.findtext("selected") or "").strip(), "Skin.HasSetting(%s)" % SETTING),
              "onclick": ((row.findtext("onclick") or "").strip(), "Skin.ToggleSetting(%s)" % SETTING),
              "visible": ((row.findtext("visible") or "").strip(), "!String.IsEmpty(Skin.String(bg_mode))")}
    for what, (got, want) in checks.items():
        if got != want:
            fail("row %s %s is %r, expected %r" % (ROW_ID, what, got, want))
    with open(PO, encoding="utf-8") as fh:
        po = fh.read()
    for sid in (LABEL, HELP):
        if po.count('msgctxt "#%s"' % sid) != 1:
            fail("strings.po should define #%s once" % sid)
    m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % HELP, po)
    if not m or "[CR]Where: " not in m.group(1):
        fail("help string #%s needs a Where line" % HELP)
    with open(os.path.join(XML, "Includes_SettingsHelp.xml"), encoding="utf-8") as fh:
        helpxml = fh.read()
    if '<value condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (ROW_ID, HELP) not in helpxml:
        fail("Includes_SettingsHelp.xml does not map row %s to #%s" % (ROW_ID, HELP))
    preview = {e.get("name"): e.text or "" for e in parse("Includes_SettingsPreview.xml").iter("expression")}
    for name in ("settings_preview_shown", "stage_region_background"):
        if "Control.HasFocus(%s)" % ROW_ID not in preview.get(name, ""):
            fail("row %s is not in %s" % (ROW_ID, name))
    stage = include(parse("Includes_Home.xml"), "HomeStage")
    calls = [i for i in stage.iter("include") if i.get("content") == "SkinBackground"] if stage is not None else []
    if len(calls) != 1 or {p.get("name"): p.get("value") for p in calls[0].findall("param")}.get("flip_zoom") \
            != "Control.HasFocus(%s)" % ROW_ID:
        fail("HomeStage must pass flip_zoom as the focus of row %s" % ROW_ID)


def main():
    """
    <summary>Runs every check and reports.</summary>
    <returns>0 when all pass, 1 otherwise.</returns>
    """
    test_zoom_animation()
    test_zoom_placement()
    test_off_by_default()
    test_settings_row()
    if FAILURES:
        print("test_background_zoom: %d check(s) failed" % len(FAILURES))
        return 1
    print("test_background_zoom: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
