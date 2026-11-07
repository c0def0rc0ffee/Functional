#!/usr/bin/env python3
"""
<summary>
Tests for the OSD sleep button (roadmap item 41): the moon button and its
glyph are gated by show_osd_sleep_button and stand down with the power
menu's sleep rows; nothing in the skin turns the switch on but the row's own
toggle; the button hangs off the left of the transport row at the spacing of
the row and is reached with Left from Previous; it opens the power menu in
its sleep only form, which hides the power rows, leaves the sleep rows'
visibility alone, renames the first of them, and is cleared by the menu's
onunload and by every other opener; the settings row toggles its own
switch, has its label and help line, and leads to and from the row above.
</summary>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. Whether the
menu looks right in its sleep only form, and whether the timer it sets
runs, is the live check's job. The preview wiring of the row is covered by
test_settings_preview.py with every other row. Exits non zero when a check
fails.

Usage:
    python3 tests/test_osd_sleep_button.py
</remarks>
"""

import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
STRINGS = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
GLYPH = os.path.join(SKIN, "media", "icons", "sleep.png")
GATE = "show_osd_sleep_button"
TIMER_HIDDEN = "Skin.HasSetting(hide_sleep_timer)"
ONLY = "Window(home).Property(sleep_menu_only)"
BUTTON = "215"
ROW = "7324"
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


def top_level(expr, op):
    """
    <summary>Splits a Kodi condition on an operator outside any brackets.</summary>
    <param name="expr">The condition.</param>
    <param name="op">"+" or "|".</param>
    <returns>The parts, stripped.</returns>
    """
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(expr):
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        elif ch == op and depth == 0:
            parts.append(expr[start:i].strip())
            start = i + 1
    parts.append(expr[start:].strip())
    return parts


def requires(cond, part):
    """
    <summary>Whether a condition is false whenever part is false.</summary>
    <param name="cond">The visible condition.</param>
    <param name="part">A condition that must hold for it to be true.</param>
    <returns>True when cond has no top level "|" and part is one of its top
    level "+" parts.</returns>
    """
    return len(top_level(cond, "|")) == 1 and part in top_level(cond, "+")


def osd_controls():
    """
    <summary>The controls of the video OSD's wrapper group by id, plus the
    images, in order.</summary>
    <returns>(dict of id to control, list of image controls).</returns>
    """
    root = ET.fromstring(read("VideoOSD.xml"))
    ids, images = {}, []
    for node in root.iter("control"):
        if node.get("id"):
            ids[node.get("id")] = node
        if node.get("type") == "image":
            images.append(node)
    return ids, images


def test_gated_off():
    """
    <summary>Proves the button and its glyph draw nothing while the switch is
    off, and nothing while the power menu's sleep rows are hidden.</summary>
    """
    print("running test_gated_off")
    ids, images = osd_controls()
    glyphs = [i for i in images if i.findtext("texture") == "icons/sleep.png"]
    if BUTTON not in ids:
        fail("button %s is missing" % BUTTON)
        return
    if len(glyphs) != 1:
        fail("expected one image drawing icons/sleep.png, found %d" % len(glyphs))
    for node in [ids[BUTTON]] + glyphs:
        cond = node.findtext("visible") or ""
        if not requires(cond, "Skin.HasSetting(%s)" % GATE):
            fail("a sleep button control is not gated by %s: %r" % (GATE, cond))
        if not requires(cond, "!" + TIMER_HIDDEN):
            fail("a sleep button control shows while the sleep timer is hidden: %r" % cond)


def test_off_by_default():
    """
    <summary>Proves nothing in the skin turns the switch on except its row's
    toggle in Skin Settings, and that only the button sets the sleep only
    form of the power menu.</summary>
    """
    print("running test_off_by_default")
    writers, setters = [], []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        for number, line in enumerate(read(name).splitlines(), start=1):
            if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s[,)]" % GATE, line):
                writers.append((name, number, line.strip()))
            if re.search(r"SetProperty\(sleep_menu_only,", line):
                setters.append((name, number))
    if len(writers) != 1 or writers[0][0] != "SkinSettings.xml" or "ToggleSetting" not in writers[0][2]:
        fail("the only writer of %s should be the toggle in SkinSettings.xml, found %s" % (GATE, writers))
    if len(setters) != 1 or setters[0][0] != "VideoOSD.xml":
        fail("sleep_menu_only should be set by the OSD button alone, found %s" % setters)
    for folder, _, files in os.walk(SKIN):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    text = handle.read()
                if GATE in text or "sleep_menu_only" in text:
                    fail("%s mentions the sleep button; the skin's Python must not touch it" % name)


def test_button():
    """
    <summary>Checks the button sits 14 left of Previous at the row's size,
    its glyph is centred on it as the others are, Left from Previous reaches
    it, and OK sets the sleep only form before opening the power menu.</summary>
    """
    print("running test_button")
    ids, images = osd_controls()
    button, prev = ids.get(BUTTON), ids.get("200")
    if button is None or prev is None:
        fail("button %s or Previous is missing" % BUTTON)
        return
    for tag in ("bottom", "width", "height"):
        if button.findtext(tag) != prev.findtext(tag):
            fail("button %s %s is %s, Previous has %s" % (BUTTON, tag, button.findtext(tag), prev.findtext(tag)))
    if int(button.findtext("left")) != int(prev.findtext("left")) - 14 - int(button.findtext("width")):
        fail("button %s is not 14 left of Previous" % BUTTON)
    glyph = [i for i in images if i.findtext("texture") == "icons/sleep.png"]
    if glyph:
        g = glyph[0]
        if (int(g.findtext("left")), g.findtext("bottom"), g.findtext("width"), g.findtext("height")) != \
                (int(button.findtext("left")) + 16, "14", "48", "48"):
            fail("the moon is not centred on its button as the other glyphs are")
    if prev.findtext("onleft") != BUTTON:
        fail("Left from Previous does not reach button %s" % BUTTON)
    if button.findtext("onright") != "200" or button.findtext("onleft") != BUTTON:
        fail("button %s should go right to Previous and nowhere on left" % BUTTON)
    clicks = [c.text for c in button.findall("onclick")]
    if clicks != ["SetProperty(sleep_menu_only,true,home)", "ActivateWindow(shutdownmenu)"]:
        fail("button %s clicks %s" % (BUTTON, clicks))
    with open(GLYPH, "rb") as handle:
        data = handle.read()
    chunks, i = [], 8
    while i < len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        chunks.append(data[i + 4:i + 8].decode("ascii"))
        i += 12 + length
    if chunks != ["IHDR", "IDAT", "IEND"]:
        fail("sleep.png carries chunks %s" % chunks)


def test_menu():
    """
    <summary>Checks the power menu's sleep only form in the XML: every power
    row hides while it is set, no sleep row's visibility looks at it, the
    three panels behind take turns (whole menu, three rows, four rows), the
    title and the first row's label switch, the menu has an onunload that
    clears it, and every other opener of the menu clears it first.</summary>
    <remarks>That onunload actually runs on every way out is the live
    check's job.</remarks>
    """
    print("running test_menu")
    text = read("DialogButtonMenu.xml")
    root = ET.fromstring(text)
    empty = "String.IsEmpty(%s)" % ONLY
    sleep_rows, power_rows = [], []
    for item in root.iter("item"):
        clicks = " ".join(c.text or "" for c in item.findall("onclick"))
        (sleep_rows if "sleep_command" in clicks else power_rows).append(item)
    if len(sleep_rows) != 4 or len(power_rows) != 6:
        fail("expected 4 sleep rows and 6 power rows, found %d and %d" % (len(sleep_rows), len(power_rows)))
    for item in power_rows:
        if not requires(item.findtext("visible") or "", empty):
            fail("power row %s shows in the sleep only form" % item.findtext("label"))
    for item in sleep_rows:
        if "sleep_menu_only" in (item.findtext("visible") or ""):
            fail("sleep row %s depends on the sleep only form" % item.findtext("label"))
    panels = [n for n in root.iter("control") if n.get("type") == "image" and n.findtext("texture") == "white.png"
              and (n.find("texture").get("colordiffuse") == "bg_panel")]
    shown = sorted((p.findtext("visible"), p.findtext("height")) for p in panels)
    want = [(empty, "600"), ("!%s + !$EXP[sleep_armed]" % empty, "280"), ("!%s + $EXP[sleep_armed]" % empty, "340")]
    if shown != sorted(want):
        fail("the three panels do not take turns on the sleep only form: %s" % shown)
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml") or name == "VideoOSD.xml":
            continue
        lines = read(name).splitlines()
        for i, line in enumerate(lines):
            if re.search(r"<onclick>ActivateWindow\(shutdownmenu\)", line, re.I):
                if i == 0 or "ClearProperty(sleep_menu_only,home)" not in lines[i - 1]:
                    fail("%s line %d opens the power menu without clearing the sleep only form" % (name, i + 1))
    if root.findtext("onunload") != "ClearProperty(sleep_menu_only,home)":
        fail("the power menu does not clear the sleep only form when it closes")
    title = [n for n in root.iter("control") if n.get("id") == "2"]
    if not title or title[0].findtext("label") != "$VAR[PowerMenuTitle]":
        fail("the power menu title does not follow the sleep only form")
    includes = read("Includes.xml")
    var = re.search(r'<variable name="PowerMenuTitle">(.*?)</variable>', includes, re.S)
    if not var or "!%s\">$LOCALIZE[31424]" % empty not in var.group(1) or "<value>$LOCALIZE[31040]</value>" not in var.group(1):
        fail("PowerMenuTitle should read Sleep Timer in the sleep only form and Power otherwise")
    first = re.search(r'<variable name="SleepTimerMenuLabel">(.*?)</variable>', includes, re.S)
    values = first and re.findall(r'<value(?: condition="([^"]*)")?>([^<]*)</value>', first.group(1))
    if not values or [v for c, v in values if c.startswith("!" + empty)] != \
            ["$LOCALIZE[31825]  $INFO[Window(home).Property(sleep_remaining)]", "$LOCALIZE[31825]"] or \
            [v for c, v in values if not c.startswith("!" + empty)] != \
            ["$LOCALIZE[31424]  $INFO[Window(home).Property(sleep_remaining)]", "$LOCALIZE[31424]"]:
        fail("the first sleep row should read 31825 in the sleep only form and 31424, as before, otherwise")


def test_row():
    """
    <summary>Checks the row reads and toggles its own switch, greys while the
    sleep timer is hidden, has its label and a help line with a Where line,
    sits under the chapter marks row clear of the text below, and that it
    and the chapter marks row lead to each other with Down and Up.</summary>
    <remarks>Right from the left column goes to the top of the right column,
    as on every page, so 7303 does not lead here; Left from here goes to
    7303, the row beside it.</remarks>
    """
    print("running test_row")
    settings = {n.get("id"): n for n in ET.fromstring(read("SkinSettings.xml")).iter("control") if n.get("id")}
    row, above = settings.get(ROW), settings.get("7323")
    if row is None or above is None:
        fail("row %s or 7323 is missing" % ROW)
        return
    if row.findtext("selected") != "Skin.HasSetting(%s)" % GATE:
        fail("row %s does not show %s" % (ROW, GATE))
    if row.findtext("onclick") != "Skin.ToggleSetting(%s)" % GATE:
        fail("row %s does not toggle %s" % (ROW, GATE))
    if row.findtext("enable") != "!" + TIMER_HIDDEN:
        fail("row %s does not grey while the sleep timer is hidden" % ROW)
    with open(STRINGS, encoding="utf-8") as handle:
        strings = handle.read()
    if 'msgctxt "#%s"' % row.findtext("label") not in strings:
        fail("row %s has no label string" % ROW)
    help_text = read("Includes_SettingsHelp.xml")
    shown = re.search(r'name="settings_help_shown">(.*)</expression>', help_text)
    if not shown or "Control.HasFocus(%s)" % ROW not in shown.group(1):
        fail("settings_help_shown does not list row %s" % ROW)
    entry = re.search(r'Control\.HasFocus\(%s\)">\$LOCALIZE\[(\d+)\]' % ROW, help_text)
    line = entry and re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
    if not line or "[CR]Where: " not in line.group(1):
        fail("row %s has no help with a Where line" % ROW)
    left, top = int(row.findtext("left")), int(row.findtext("top"))
    if left != int(above.findtext("left")) or top < int(above.findtext("top")) + int(above.findtext("height")):
        fail("row %s is not under row 7323 in the right column" % ROW)
    if left + int(row.findtext("width")) > 1840 or top + int(row.findtext("height")) > 680:
        fail("row %s runs past the page edge or into the caching note at y 680" % ROW)
    if above.findtext("ondown") != ROW or row.findtext("onup") != "7323":
        fail("rows 7323 and %s do not lead to each other" % ROW)
    if row.findtext("onleft") != "7303" or row.find("onright") is not None or row.find("ondown") is not None:
        fail("row %s should go left to 7303 and nowhere right or down" % ROW)


if __name__ == "__main__":
    test_gated_off()
    test_off_by_default()
    test_button()
    test_menu()
    test_row()
    if FAILURES:
        print("test_osd_sleep_button: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_osd_sleep_button: all checks passed")
