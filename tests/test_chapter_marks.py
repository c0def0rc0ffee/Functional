#!/usr/bin/env python3
"""
<summary>
Tests for the chapter marks (roadmap item 40): every ranges control in the
video OSD and the seek bar, and every progress control in the OSD (which had
none before this item), is gated by show_chapter_marks as a top level
condition, so with the switch off they draw nothing; nothing in the skin
turns it on but the row's own toggle; the ticks are drawn from Player.Chapters with
the right texture alone and only for a file with chapters; the ticks centre
on their bar and the OSD bar keeps to the free band of the panel; the
settings row toggles its own switch, has its label and help line, and is
reachable from every video OSD row.
</summary>
<remarks>
The free band check is made in the bottom OSD's geometry only: the top
position moves the whole OSD group by one fixed offset (OsdTopModeShift),
so the bar keeps its place in the panel. build_preview_art.py also sets
the switch, for its own pictures, and puts it back; it is not part of the
skin and is not scanned.
</remarks>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. Whether the
ticks land on the chapter starts is the live check's job: Kodi 21 reported
"0.00000,24.43874,24.43874,49.98833,49.98833,74.42708" for a four chapter
clip on 07/11/2026, and the ticks were seen at those three points. The
preview wiring of the row is covered by test_settings_preview.py with every
other row. Exits non zero when a check fails.

Usage:
    python3 tests/test_chapter_marks.py
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
TICK = os.path.join(SKIN, "media", "chapter_tick.png")
GATE = "show_chapter_marks"
ROW = "7323"
OSD_ROWS = ("7302", "7303", "7304", "7305", "7313")
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


def gated(visibles):
    """
    <summary>Whether a control is hidden whenever the switch is off.</summary>
    <param name="visibles">The visible conditions of the control and its
    ancestors.</param>
    <returns>True when one of them has no top level "|" and has
    Skin.HasSetting(show_chapter_marks) as a top level "+" part, so it is
    false whenever the setting is.</returns>
    """
    want = "Skin.HasSetting(%s)" % GATE
    for cond in visibles:
        if len(top_level(cond, "|")) == 1 and want in top_level(cond, "+"):
            return True
    return False


def controls(name):
    """
    <summary>Every control of a window with the visible conditions above it.</summary>
    <param name="name">The window file under xml/.</param>
    <returns>(control element, list of visible texts of it and its ancestors).</returns>
    """
    found = []

    def walk(node, visibles):
        here = visibles + [v.text or "" for v in node.findall("visible")]
        if node.tag == "control":
            found.append((node, here))
        for child in node:
            if child.tag in ("control", "controls"):
                walk(child, here)

    walk(ET.fromstring(read(name)), [])
    return found


def test_gated_off():
    """
    <summary>Proves every control the item adds draws nothing while the switch
    is off: each ranges control in the two windows, and every progress control
    in the OSD, which had none before this item.</summary>
    """
    print("running test_gated_off")
    seen = 0
    for name in ("VideoOSD.xml", "DialogSeekBar.xml"):
        for node, visibles in controls(name):
            kind = node.get("type")
            ours = kind == "ranges" or (name == "VideoOSD.xml" and kind == "progress")
            if not ours:
                continue
            seen += 1
            if not gated(visibles):
                fail("%s: a %s control is not gated by %s" % (name, kind, GATE))
    if seen != 5:
        fail("expected 5 controls behind the switch (OSD bar, cache, ticks, two seek bar ticks), found %d" % seen)


def test_off_by_default():
    """
    <summary>Proves nothing in the skin turns the switch on except its row's
    toggle in Skin Settings: no other XML writes it, with or without a value,
    and no Python file in the skin mentions it.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            for number, line in enumerate(read(name).splitlines(), start=1):
                if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s[,)]" % GATE, line):
                    writers.append((name, number, line.strip()))
    if len(writers) != 1 or writers[0][0] != "SkinSettings.xml" or "ToggleSetting" not in writers[0][2]:
        fail("the only writer of %s should be the toggle in SkinSettings.xml, found %s" % (GATE, writers))
    for folder, _, files in os.walk(SKIN):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    if GATE in handle.read():
                        fail("%s mentions %s; the skin's Python must not touch it" % (name, GATE))


def test_ticks():
    """
    <summary>Checks each ranges control reads Player.Chapters, draws the right
    texture alone (a left or middle texture would fill the span between
    chapters), stands down below two chapters, and that the tick texture is a
    PNG with no metadata chunks.</summary>
    """
    print("running test_ticks")
    for name in ("VideoOSD.xml", "DialogSeekBar.xml"):
        for node, visibles in controls(name):
            if node.get("type") != "ranges":
                continue
            if node.findtext("info") != "Player.Chapters":
                fail("%s: a ranges control reads %s" % (name, node.findtext("info")))
            if node.findtext("righttexture") != "chapter_tick.png":
                fail("%s: a ranges control does not draw chapter_tick.png on the right" % name)
            for extra in ("lefttexture", "midtexture"):
                if node.find(extra) is not None:
                    fail("%s: a ranges control draws a %s" % (name, extra))
            bg = node.find("texturebg")
            if bg is None or not (bg.get("colordiffuse") or "").startswith("00"):
                fail("%s: a ranges control has a visible background" % name)
            if not any("Integer.IsGreater(Player.ChapterCount,1)" in top_level(v, "+") for v in visibles):
                fail("%s: a ranges control shows without two chapters" % name)
    with open(TICK, "rb") as handle:
        data = handle.read()
    chunks, i = [], 8
    while i < len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        chunks.append(data[i + 4:i + 8].decode("ascii"))
        i += 12 + length
    if chunks != ["IHDR", "IDAT", "IEND"]:
        fail("chapter_tick.png carries chunks %s" % chunks)


def box(node):
    """
    <summary>A control's vertical extent as (edge tag, value, height).</summary>
    <param name="node">The control.</param>
    <returns>("bottom" or "top", int, int).</returns>
    """
    edge = "bottom" if node.find("bottom") is not None else "top"
    return edge, int(node.findtext(edge)), int(node.findtext("height"))


def test_geometry():
    """
    <summary>Checks each tick row is centred on the bar it marks, 4 above and
    below, over the same width, and that the OSD bar and ticks keep to the free
    band of the panel between the accent stripe (ends y 890) and the title and
    clock (from y 900, glyphs from about 910), x 240 to 1880.</summary>
    """
    print("running test_geometry")
    for name in ("VideoOSD.xml", "DialogSeekBar.xml"):
        found = controls(name)
        ticks = [n for n, _ in found if n.get("type") == "ranges"]
        bars = [n for n, _ in found if n.get("type") == "progress" and n.findtext("info") == "Player.Progress"]
        for tick in ticks:
            edge, pos, height = box(tick)
            match = [b for b in bars if box(b)[0] == edge and b.findtext("left") == tick.findtext("left")
                     and b.findtext("width") == tick.findtext("width")]
            if len(match) != 1:
                fail("%s: no single bar under the ticks at %s %d" % (name, edge, pos))
                continue
            _, bpos, bheight = box(match[0])
            if (pos, height) != (bpos - 4, bheight + 8):
                fail("%s: ticks at %s %d height %d are not centred on the bar at %d height %d"
                     % (name, edge, pos, height, bpos, bheight))
            if name == "VideoOSD.xml":
                top = 1080 - pos - height
                if top < 892 or top + height > 908:
                    fail("VideoOSD.xml: ticks run y %d to %d, outside the free band 892 to 908" % (top, top + height))
                left, width = int(tick.findtext("left")), int(tick.findtext("width"))
                if left < 240 or left + width > 1880:
                    fail("VideoOSD.xml: ticks run x %d to %d, outside 240 to 1880" % (left, left + width))


def test_row():
    """
    <summary>Checks the row reads and toggles its own switch, has its label and
    a help line with a Where line, sits in the right column clear of the text
    below it, and is reachable with right from every video OSD row.</summary>
    """
    print("running test_row")
    settings = {n.get("id"): n for n in ET.fromstring(read("SkinSettings.xml")).iter("control") if n.get("id")}
    row = settings.get(ROW)
    if row is None:
        fail("row %s is missing" % ROW)
        return
    if row.findtext("selected") != "Skin.HasSetting(%s)" % GATE:
        fail("row %s does not show %s" % (ROW, GATE))
    if row.findtext("onclick") != "Skin.ToggleSetting(%s)" % GATE:
        fail("row %s does not toggle %s" % (ROW, GATE))
    if row.findtext("disabledcolor") != "disabled":
        fail("row %s has no disabledcolor" % ROW)
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
    if left + int(row.findtext("width")) > 1840 or top + int(row.findtext("height")) > 680:
        fail("row %s runs past the page edge or into the caching note at y 680" % ROW)
    if row.findtext("onleft") != OSD_ROWS[0]:
        fail("left from row %s should go back to %s" % (ROW, OSD_ROWS[0]))
    if row.find("onright") is not None:
        fail("right from row %s should go nowhere, as on the other right column rows" % ROW)
    for rid in OSD_ROWS:
        if settings[rid].findtext("onright") != ROW:
            fail("right from row %s does not reach row %s" % (rid, ROW))


if __name__ == "__main__":
    test_gated_off()
    test_off_by_default()
    test_ticks()
    test_geometry()
    test_row()
    if FAILURES:
        print("test_chapter_marks: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_chapter_marks: all checks passed")
