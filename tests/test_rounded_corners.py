#!/usr/bin/env python3
"""
<summary>
Tests for the Rounded Corners switch (roadmap item 44): every image drawn
through a corner mask has a square twin with the same box and art that shows
when the switch is off, every mask referenced exists as a PNG with an alpha
channel, nothing but the user's own click sets the switch, its Library page
row has a help panel line and its strings, and the row overlaps nothing on
that page.
</summary>
<remarks>
No Kodi is needed; the XML is parsed with ElementTree. Kodi reads the diffuse
file name literally, so the skin draws the rounded form as a second image
control beside the square one, each gated on the switch one way or the other.
That pairing is the whole mechanism, so the test checks it structurally: for
each masked image, the nearest earlier image control in the same parent with
the same left, top, width and height is its twin, and the twin must carry the
same texture text and the same visible condition with the gate negated.
Boxes written as $PARAM[...] are compared as text. Exits non zero when a
check fails.

Usage:
    python3 tests/test_rounded_corners.py
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
MEDIA = os.path.join(SKIN, "media")
PO = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(SKIN, "service.py")

GATE = "rounded_corners"
ON = "Skin.HasSetting(%s)" % GATE
OFF = "!" + ON
SWITCH_ID = "7318"
HELP_STRING = "31812"
STRINGS = ("31699", "31812")
BOX = ("left", "top", "right", "bottom", "width", "height")

FAILURES = []


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


def box(el):
    """
    <summary>Reads an element's position and size as text.</summary>
    <param name="el">A control element.</param>
    <returns>A tuple of the six box values, empty strings where unset.</returns>
    """
    return tuple(text(el, t) for t in BOX)


def texture_key(el):
    """
    <summary>Describes a control's texture without its diffuse mask, so a
    masked image and its square twin compare equal.</summary>
    <param name="el">An image control element.</param>
    <returns>The texture's text and its attributes other than diffuse.</returns>
    """
    tex = el.find("texture")
    if tex is None:
        return None
    attrs = {k: v for k, v in tex.attrib.items() if k != "diffuse"}
    return ((tex.text or "").strip(), tuple(sorted(attrs.items())))


def visibles(el):
    """
    <summary>Joins a control's visible conditions into one expression.</summary>
    <param name="el">A control element.</param>
    <returns>The conditions joined with " + ", or "" when there are none.</returns>
    """
    return " + ".join((v.text or "").strip() for v in el.findall("visible"))


def parse_all():
    """
    <summary>Parses every XML file in the skin's xml folder.</summary>
    <returns>A list of (file name, root element) pairs.</returns>
    """
    out = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            out.append((name, ET.parse(os.path.join(XML, name)).getroot()))
    return out


def test_masked_images_have_square_twins(trees):
    """
    <summary>For every image drawn through a corner mask, finds its square twin
    and checks box, texture and gating line up.</summary>
    <param name="trees">The parsed XML files.</param>
    """
    print("running test_masked_images_have_square_twins")
    masked = 0
    for name, root in trees:
        for parent in root.iter():
            children = list(parent)
            for i, el in enumerate(children):
                if el.tag != "control":
                    continue
                tex = el.find("texture")
                if tex is None or not tex.get("diffuse", "").startswith("masks/"):
                    continue
                masked += 1
                vis = visibles(el)
                if ON not in vis or OFF in vis:
                    fail("%s: masked image %s is not gated on %s" % (name, box(el), ON))
                twin = None
                for prev in reversed(children[:i]):
                    if prev.tag == "control" and prev.get("type") == el.get("type") and box(prev) == box(el):
                        twin = prev
                        break
                if twin is None:
                    fail("%s: masked image %s has no square twin with the same box" % (name, box(el)))
                    continue
                if OFF not in visibles(twin):
                    fail("%s: the twin of masked image %s is not gated on %s" % (name, box(el), OFF))
                if visibles(twin).replace(OFF, ON) != vis:
                    fail("%s: masked image %s and its twin differ beyond the gate: %r vs %r"
                         % (name, box(el), vis, visibles(twin)))
                if texture_key(twin) != texture_key(el):
                    fail("%s: masked image %s and its twin draw different textures: %r vs %r"
                         % (name, box(el), texture_key(el), texture_key(twin)))
    if masked < 5:
        fail("only %d masked images found, fewer than the item adds" % masked)
    print("  %d masked images paired" % masked)


def test_masks_exist(trees):
    """
    <summary>Checks every mask the XML names is a PNG with an alpha channel,
    resolving $PARAM[mask] through the include defaults and passed values.</summary>
    <param name="trees">The parsed XML files.</param>
    """
    print("running test_masks_exist")
    names = set()
    for name, root in trees:
        for tex in root.iter("texture"):
            d = tex.get("diffuse", "")
            if d.startswith("masks/"):
                names.add(d[len("masks/"):-len(".png")])
        for param in root.iter("param"):
            if param.get("name") == "mask":
                names.add(param.get("value") or param.get("default") or "")
    names.discard("$PARAM[mask]")
    names.discard("")
    for mask in sorted(names):
        path = os.path.join(MEDIA, "masks", mask + ".png")
        if not os.path.isfile(path):
            fail("mask %s.png is named in the XML but missing from media/masks" % mask)
            continue
        with open(path, "rb") as fh:
            head = fh.read(29)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            fail("mask %s.png is not a PNG" % mask)
            continue
        width, height, depth, colour = struct.unpack(">IIBB", head[16:26])
        if colour not in (4, 6):
            fail("mask %s.png has no alpha channel (colour type %d)" % (mask, colour))
        print("  %s.png %dx%d" % (mask, width, height))
    if not names:
        fail("no mask is named anywhere in the XML")


def test_off_by_default(trees):
    """
    <summary>Proves nothing turns the switch on except the user's own click
    on its radio button in Skin Settings.</summary>
    <param name="trees">The parsed XML files.</param>
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
                fail("service.py:%d mentions the setting; the service must not touch it" % number)
    root = dict(trees)["SkinSettings.xml"]
    radios = [c for c in root.iter("control") if c.get("id") == SWITCH_ID]
    if len(radios) != 1 or radios[0].get("type") != "radiobutton":
        fail("expected one radiobutton with id %s in SkinSettings.xml" % SWITCH_ID)
        return
    if text(radios[0], "selected") != ON:
        fail("radiobutton %s does not reflect %s" % (SWITCH_ID, ON))


def test_help_line_and_strings(trees):
    """
    <summary>Checks the switch has its help panel entry in both halves of the
    settings help include, and that its strings exist with a Where line.</summary>
    <param name="trees">The parsed XML files.</param>
    """
    print("running test_help_line_and_strings")
    root = dict(trees)["Includes_SettingsHelp.xml"]
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


def test_library_page_rows_do_not_overlap(trees):
    """
    <summary>On the Library page, checks no two controls in the same column
    overlap vertically, since the item moved every row below its own.</summary>
    <param name="trees">The parsed XML files.</param>
    """
    print("running test_library_page_rows_do_not_overlap")
    root = dict(trees)["SkinSettings.xml"]
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
                fail("Library page: %s (%d to %d) overlaps %s (%d to %d) in the column at %d"
                     % (a[3], a[1], a[2], b[3], b[1], b[2], a[0]))
    print("  %d adjacent pairs checked" % checked)


if __name__ == "__main__":
    TREES = parse_all()
    test_masked_images_have_square_twins(TREES)
    test_masks_exist(TREES)
    test_off_by_default(TREES)
    test_help_line_and_strings(TREES)
    test_library_page_rows_do_not_overlap(TREES)
    if FAILURES:
        print("test_rounded_corners: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_rounded_corners: all checks passed")
