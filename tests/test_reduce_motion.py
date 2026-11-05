#!/usr/bin/env python3
"""
<summary>
Tests for the Reduce Motion switch (roadmap item 43): every timed animation in
the skin's XML outside the seasonal theme includes is gated on the switch, the
switch is off by default and nothing turns it on, and its Skin Settings row has
a help panel line and its strings.
</summary>
<remarks>
No Kodi is needed; the XML is read as text, line by line, joining the few
elements that run over more than one line, and the include name a line
belongs to is the last include name opened above it. An animation counts as timed when it
has a time attribute above zero, or, in the child effect form, when any of its
effect elements has one. An animation with no time attribute is treated as
instant, which is how this skin uses them (the infobar clearance slides); if
Kodi ever defaulted them to a duration they would need the gate too.

The seasonal decorations (the ThemeXxx, ChristmasLayers and XmasXxx includes)
keep their own switches by design, as the item's changelog entry says, so
they are the one allowed exception. Exits non zero when a check fails.

Usage:
    python3 tests/test_reduce_motion.py
</remarks>
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "skin.functional", "xml")
PO = os.path.join(ROOT, "skin.functional", "language",
                  "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(ROOT, "skin.functional", "service.py")

GATE = "reduce_motion"
SEASONAL_PREFIXES = ("Theme", "ChristmasLayers", "Xmas")
SWITCH_ID = "7317"
HELP_STRING = "31811"
STRINGS = ("31697", "31698", "31811")

FAILURES = []


def fail(msg):
    """
    <summary>Records one failure; the run carries on so every miss is listed.</summary>
    <param name="msg">What failed, with file and line where there is one.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def read_lines(path):
    """
    <summary>Returns a file's lines, decoded as UTF-8.</summary>
    <param name="path">Absolute path of the file.</param>
    <returns>A list of lines without their newlines.</returns>
    """
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def attr(line, name):
    """
    <summary>Reads one XML attribute from a single line of markup.</summary>
    <param name="line">The line holding the element.</param>
    <param name="name">The attribute name.</param>
    <returns>The attribute's value, or None when it is absent.</returns>
    """
    m = re.search(r'\b%s="([^"]*)"' % re.escape(name), line)
    return m.group(1) if m else None


def timed(line):
    """
    <summary>Says whether an animation or effect line runs for any time.</summary>
    <param name="line">A line holding an animation or effect element.</param>
    <returns>True when its time attribute is present and above zero. A
    parameterised time ($PARAM[...]) counts as timed, since every caller of
    those includes passes a real duration.</returns>
    """
    value = attr(line, "time")
    if value is None:
        return False
    if value.startswith("$"):
        return True
    try:
        return int(value) > 0
    except ValueError:
        return True


def test_every_timed_animation_is_gated():
    """
    <summary>Walks every XML file and reports each timed animation whose
    condition does not name the switch, outside the seasonal includes.</summary>
    <remarks>Handles both forms: the one line attribute form, and the
    child effect form where the condition sits on the animation element and
    the durations on the effect elements under it.</remarks>
    """
    print("running test_every_timed_animation_is_gated")
    seen = 0
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        path = os.path.join(XML, name)
        include = ""
        open_anim = None  # (line number, condition) of a child effect animation
        open_timed = False
        pending = None  # (line number, text) of an element split across lines
        for number, raw in enumerate(read_lines(path), start=1):
            if pending is not None:
                pending = (pending[0], pending[1] + " " + raw.strip())
                if ">" not in raw:
                    continue
                number, line = pending
                pending = None
            else:
                line = raw
            m = re.search(r'<include name="([^"]+)"', line)
            if m:
                include = m.group(1)
            seasonal = include.startswith(SEASONAL_PREFIXES)
            if open_anim is not None:
                if "<effect" in line and timed(line):
                    open_timed = True
                if "</animation>" in line:
                    seen += 1
                    if open_timed and not seasonal and GATE not in (open_anim[1] or ""):
                        fail("%s:%d child effect animation is not gated on %s"
                             % (name, open_anim[0], GATE))
                    open_anim = None
                    open_timed = False
                continue
            if "<animation" not in line:
                continue
            if "<animation type=" in line:
                open_anim = (number, attr(line, "condition"))
                open_timed = False
                continue
            if ">" not in line.split("<animation", 1)[1]:
                pending = (number, line)
                continue
            seen += 1
            if timed(line) and not seasonal and GATE not in (attr(line, "condition") or ""):
                fail("%s:%d timed animation is not gated on %s" % (name, number, GATE))
    if seen < 100:
        fail("only %d animations were read, which is fewer than the skin has" % seen)
    print("  %d animations read" % seen)


def test_off_by_default():
    """
    <summary>Proves nothing turns the switch on except the user's own click
    on its radio button in Skin Settings.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        for number, line in enumerate(read_lines(os.path.join(XML, name)), start=1):
            if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s\)" % GATE, line):
                writers.append((name, number, line.strip()))
    if len(writers) != 1:
        fail("expected exactly one writer of the setting, found %d: %s"
             % (len(writers), writers))
    elif writers[0][0] != "SkinSettings.xml" or "ToggleSetting" not in writers[0][2]:
        fail("the only writer should be the toggle in SkinSettings.xml, found %s" % (writers[0],))
    for number, line in enumerate(read_lines(SERVICE), start=1):
        if GATE in line:
            fail("service.py:%d mentions the setting; the service must not touch it" % number)
    lines = read_lines(os.path.join(XML, "SkinSettings.xml"))
    starts = [i for i, l in enumerate(lines) if 'id="%s"' % SWITCH_ID in l and "radiobutton" in l]
    if len(starts) != 1:
        fail("expected one radiobutton with id %s in SkinSettings.xml, found %d" % (SWITCH_ID, len(starts)))
        return
    block = "\n".join(lines[starts[0]:starts[0] + 40])
    if "<selected>Skin.HasSetting(%s)</selected>" % GATE not in block:
        fail("radiobutton %s does not reflect Skin.HasSetting(%s)" % (SWITCH_ID, GATE))


def test_help_line_and_strings():
    """
    <summary>Checks the switch has its help panel entry in both halves of
    the settings help include, and that its three strings exist.</summary>
    """
    print("running test_help_line_and_strings")
    help_lines = read_lines(os.path.join(XML, "Includes_SettingsHelp.xml"))
    expression = [l for l in help_lines if 'name="settings_help_shown"' in l]
    if not expression or "Control.HasFocus(%s)" % SWITCH_ID not in expression[0]:
        fail("settings_help_shown does not list control %s" % SWITCH_ID)
    mapping = 'condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (SWITCH_ID, HELP_STRING)
    if not any(mapping in l for l in help_lines):
        fail("the help map has no line for control %s to string %s" % (SWITCH_ID, HELP_STRING))
    po = "\n".join(read_lines(PO))
    for sid in STRINGS:
        if 'msgctxt "#%s"' % sid not in po:
            fail("strings.po has no string %s" % sid)
    m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % HELP_STRING, po)
    if m and "[CR]Where:" not in m.group(1):
        fail("help string %s has no Where line" % HELP_STRING)


if __name__ == "__main__":
    test_every_timed_animation_is_gated()
    test_off_by_default()
    test_help_line_and_strings()
    if FAILURES:
        print("test_reduce_motion: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_reduce_motion: all checks passed")
