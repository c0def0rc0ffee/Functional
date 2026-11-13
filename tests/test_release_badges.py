#!/usr/bin/env python3
"""
<summary>
Tests for the release badges (roadmap item 21): a truth table over every
switch combination and kind of tile proves the gallery draws nothing new
while the switches are off, each switch owns its own mark, a tile without a
poster draws none and two badges never overlap; the badges sit inside the
narrowest tile and clear the watched corner; each row toggles its own switch
and has its label and help line; the labels name every value Kodi reports.
</summary>
<remarks>
No Kodi is needed; the XML is read with ElementTree and as text. What a badge
looks like on a poster is the live check's job. The preview wiring of the
three rows is covered by test_settings_preview.py with every other row.
Exits non zero when a check fails.

Usage:
    python3 tests/test_release_badges.py
</remarks>
"""

import itertools
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "skin.functional", "xml")
STRINGS = os.path.join(ROOT, "skin.functional", "language", "resource.language.en_gb", "strings.po")
SWITCHES = {"7210": "show_badge_4k", "7211": "show_badge_hdr", "7212": "show_badge_res"}
# Kodi's own words, from the comment at ItemResolutionLabel and the HDR types it reports.
RESOLUTIONS = {"8K": "8K", "4K": "4K", "1080": "1080", "720": "720", "576": "SD", "540": "SD", "480": "SD"}
HDR_TYPES = {"hdr10": "HDR", "dolbyvision": "DV", "hlg": "HLG"}
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


def includes():
    """
    <summary>Parses Includes.xml.</summary>
    <returns>The root element.</returns>
    """
    return ET.fromstring(read("Includes.xml"))


def expression(root, name):
    """
    <summary>Finds one named expression.</summary>
    <param name="root">The Includes.xml root.</param>
    <param name="name">The expression's name.</param>
    <returns>Its text, empty when it is missing.</returns>
    """
    for node in root.iter("expression"):
        if node.get("name") == name:
            return node.text or ""
    fail("expression %s is missing" % name)
    return ""


def label_for(root, variable, info, value):
    """
    <summary>Works out what a label variable says for one value of an info label,
    walking its steps in order as Kodi does.</summary>
    <param name="root">The Includes.xml root.</param>
    <param name="variable">The variable's name.</param>
    <param name="info">The info label its conditions read.</param>
    <param name="value">The value to try.</param>
    <returns>The text of the first step that matches.</returns>
    """
    for node in root.iter("variable"):
        if node.get("name") != variable:
            continue
        for step in node.findall("value"):
            condition = step.get("condition")
            if condition is None or condition == "String.IsEqual(%s,%s)" % (info, value):
                return step.text
    return None


def evaluate(expr, state):
    """
    <summary>Evaluates a Kodi boolean expression, for the truth table.</summary>
    <param name="expr">The condition, with any $EXP[...] already put in.</param>
    <param name="state">Maps each condition to true or false.</param>
    <returns>The result, by Kodi's grammar: + binds tighter than |, ! tightest.</returns>
    <exception cref="KeyError">A condition the table does not know, so an expression
    that starts reading something new fails loudly here.</exception>
    """
    tokens = re.findall(r"\[|\]|\+|\||!|[A-Za-z][\w.]*\([^()]*(?:\([^()]*\))?[^()]*\)", expr)
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def parse_or():
        value = parse_and()
        while peek() == "|":
            pos[0] += 1
            right = parse_and()
            value = value or right
        return value

    def parse_and():
        value = parse_not()
        while peek() == "+":
            pos[0] += 1
            right = parse_not()
            value = value and right
        return value

    def parse_not():
        token = peek()
        pos[0] += 1
        if token == "!":
            return not parse_not()
        if token == "[":
            value = parse_or()
            pos[0] += 1
            return value
        return state[token]

    return parse_or()


def tile_state(switches, resolution, hdr, poster=True):
    """
    <summary>Builds the truth table state for one tile.</summary>
    <param name="switches">The set of badge switches that are on.</param>
    <param name="resolution">The tile's ListItem.VideoResolution, empty for none.</param>
    <param name="hdr">The tile's ListItem.HdrType, empty for none.</param>
    <param name="poster">Whether the tile has a poster.</param>
    <returns>Every condition the badges may read, and its value.</returns>
    """
    state = {"Skin.HasSetting(%s)" % s: s in switches for s in SWITCHES.values()}
    state["String.IsEmpty(ListItem.Art(poster))"] = not poster
    state["String.IsEmpty(ListItem.VideoResolution)"] = not resolution
    state["String.IsEmpty(ListItem.HdrType)"] = not hdr
    for value in RESOLUTIONS:
        state["String.IsEqual(ListItem.VideoResolution,%s)" % value] = resolution == value
    return state


def badges_drawn(root, state):
    """
    <summary>Works out which badges a tile draws.</summary>
    <param name="root">The Includes.xml root.</param>
    <param name="state">A tile_state() result.</param>
    <returns>A sorted list of (top, label) for each badge shown.</returns>
    """
    exps = {n: expression(root, n) for n in ("gallery_badge_res", "gallery_badge_hdr")}
    body = [n for n in root.iter("include") if n.get("name") == "GalleryTileBody"][0]
    drawn = []
    for use in body.iter("include"):
        if use.get("content") != "GalleryBadge":
            continue
        params = {p.get("name"): p.get("value") for p in use.findall("param")}
        shown = params["shown"]
        for name, text in exps.items():
            shown = shown.replace("$EXP[%s]" % name, "[%s]" % text)
        if evaluate(shown, state):
            drawn.append((int(params["top"]), params["label"]))
    return sorted(drawn)


def test_truth_table():
    """
    <summary>Walks every switch combination over every kind of tile.</summary>
    <remarks>
    This is what proves off by default: with all three off nothing is drawn on
    any tile. It also proves each switch owns its own mark, a tile without a
    poster draws none, and the HDR badge drops below the top one and never
    sits on it.
    </remarks>
    """
    print("running test_truth_table")
    root = includes()
    res_label, hdr_label = "$VAR[GalleryBadgeResLabel]", "$VAR[GalleryBadgeHdrLabel]"
    names = list(SWITCHES.values())
    combos = [set(c) for n in range(len(names) + 1) for c in itertools.combinations(names, n)]
    for switches, resolution, hdr, poster in itertools.product(combos, [""] + list(RESOLUTIONS), ["", "hdr10"], [True, False]):
        top = bool(resolution) and ("show_badge_4k" if resolution in ("4K", "8K") else "show_badge_res") in switches
        low = bool(hdr) and "show_badge_hdr" in switches
        wanted = []
        if poster and top:
            wanted.append((10, res_label))
        if poster and low:
            wanted.append((44 if top else 10, hdr_label))
        got = badges_drawn(root, tile_state(switches, resolution, hdr, poster))
        if got != wanted:
            fail("switches %s on a %r %r tile (poster %s) draw %s, not %s" % (sorted(switches), resolution, hdr, poster, got, wanted))


def test_badge_is_gated():
    """
    <summary>Checks the badge include obeys its condition and nothing else sets a switch.</summary>
    <remarks>
    The truth table reads the params, so it would not see the definition lose
    its visible line. Nothing but the row's own click may set a switch, or a
    default or the service could turn a badge on unasked.
    </remarks>
    """
    print("running test_badge_is_gated")
    badge = [n for n in includes().iter("include") if n.get("name") == "GalleryBadge"][0]
    if [p.text for p in badge.findall("param") if p.get("name") == "shown"] != ["false"]:
        fail("GalleryBadge must default to hidden")
    group = badge.find("definition/control")
    if group.findtext("visible") != "$PARAM[shown]":
        fail("GalleryBadge does not use its shown param")
    if len(badge.findall("definition/control")) != 1:
        fail("GalleryBadge has a control outside its gated group")
    for name in sorted(os.listdir(XML)):
        text = read(name)
        for setting in SWITCHES.values():
            for match in re.finditer(r"Skin\.(?:SetBool|ToggleSetting)\(%s[,)]" % setting, text):
                if name != "SkinSettings.xml" or match.group(0).startswith("Skin.SetBool"):
                    fail("%s sets %s outside its own row" % (name, setting))
    with open(os.path.join(ROOT, "skin.functional", "service.py"), encoding="utf-8") as handle:
        service = handle.read()
    for setting in SWITCHES.values():
        if setting in service:
            fail("service.py touches %s" % setting)


def test_badges_fit_the_tile():
    """
    <summary>Keeps the stack inside the narrowest tile and clear of the watched corner.</summary>
    <remarks>Two badges high, on the left, so a tile needs only one badge's width
    and the corner's. Both widths are read from the XML, the corner's from the
    widest control tinted as the corner in the tile body.</remarks>
    """
    print("running test_badges_fit_the_tile")
    root = includes()
    widths = [int(v) for v in re.findall(r'name="poster_w" value="(\d+)"', read("MyVideoNav.xml"))]
    heights = [int(v) for v in re.findall(r'name="poster_h" value="(\d+)"', read("MyVideoNav.xml"))]
    badge = [n for n in root.iter("include") if n.get("name") == "GalleryBadge"][0]
    group = badge.find("definition/control")
    left, width, height = (int(group.findtext(t)) for t in ("left", "width", "height"))
    for child in group.findall("control"):
        if int(child.findtext("width")) > width or int(child.findtext("height")) > height:
            fail("a control in GalleryBadge is bigger than the badge")
    body = [n for n in root.iter("include") if n.get("name") == "GalleryTileBody"][0]
    corners = [c for c in body.iter("control") if "corner_triangle.png" in (c.findtext("texture") or "")]
    if not corners:
        fail("the watched corner is not where this test looks for it")
        return
    corner = max(int(c.findtext("width")) + int(c.findtext("right")) for c in corners)
    if left + width > min(widths) + 8 - corner:
        fail("a %d wide badge at %d runs into the watched corner on a %d tile" % (width, left, min(widths)))
    if 44 + height > min(heights):
        fail("the stack runs off the shortest poster")


def test_labels():
    """
    <summary>Checks each value Kodi reports reads as it should on the badge.</summary>
    """
    print("running test_labels")
    root = includes()
    for value, wanted in RESOLUTIONS.items():
        got = label_for(root, "GalleryBadgeResLabel", "ListItem.VideoResolution", value)
        if got != wanted:
            fail("resolution %s reads %r on the badge, not %r" % (value, got, wanted))
    for value, wanted in HDR_TYPES.items():
        got = label_for(root, "GalleryBadgeHdrLabel", "ListItem.HdrType", value)
        if got != wanted:
            fail("HDR type %s reads %r on the badge, not %r" % (value, got, wanted))


def test_rows():
    """
    <summary>Checks each row reads and toggles its own switch and has its label and help.</summary>
    """
    print("running test_rows")
    settings = ET.fromstring(read("SkinSettings.xml"))
    rows = {n.get("id"): n for n in settings.iter("control") if n.get("id") in SWITCHES}
    help_text = read("Includes_SettingsHelp.xml")
    with open(STRINGS, encoding="utf-8") as handle:
        strings = handle.read()
    for rid, setting in SWITCHES.items():
        row = rows.get(rid)
        if row is None:
            fail("row %s is missing" % rid)
            continue
        if row.findtext("selected") != "Skin.HasSetting(%s)" % setting:
            fail("row %s does not show %s" % (rid, setting))
        if row.findtext("onclick") != "Skin.ToggleSetting(%s)" % setting:
            fail("row %s does not toggle %s" % (rid, setting))
        if 'msgctxt "#%s"' % row.findtext("label") not in strings:
            fail("row %s has no label string" % rid)
        entry = re.search(r'Control\.HasFocus\(%s\)">\$LOCALIZE\[(\d+)\]' % rid, help_text)
        if not entry:
            fail("row %s has no help entry" % rid)
            continue
        line = re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
        if not line or "[CR]Where: " not in line.group(1):
            fail("row %s's help has no Where line" % rid)
    group = [n for n in settings.iter("control") if n.get("id") == "7021"][0]
    if group.findtext("ondown") != "7316":
        fail("Down from the last badge row no longer reaches the row below the list")
    below = [n for n in settings.iter("control") if n.get("id") == "7316"][0]
    # STUDIO-LOGO-FIX: rows added after the badges (item 34's 7213) make
    # the list's own last row the target, not 7212 by name.
    last = [n.get("id") for n in group if n.tag == "control" and n.get("id")][-1]
    if below.findtext("onup") != last:
        fail("Up from the row below the list should land on the list's last row, %s" % last)
    if not {n.get("id") for n in group.findall("control")} >= set(SWITCHES):
        fail("the badge rows are not in the Visible Fields list")


if __name__ == "__main__":
    test_truth_table()
    test_badge_is_gated()
    test_badges_fit_the_tile()
    test_labels()
    test_rows()
    if FAILURES:
        print("test_release_badges: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_release_badges: all checks passed")
