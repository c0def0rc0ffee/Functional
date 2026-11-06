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
Sub item 4: the picture rows in the map are exactly the generator's table,
every picture exists at panel size with no text chunk and is named by the
picture variables, and the two pictures of one setting really differ. No
step of a dim ladder is the all zero colour Kodi draws as white.
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

import importlib.util
import itertools
import os
import re
import struct
import sys
import zlib
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "skin.functional", "xml")
HOME_INCLUDES = ("HomeStatsColumn", "HomeLogo", "HomeWeather", "HomeClock",
                 "HomeMenu", "HomeFooter", "HomeContinueTabs")
# <summary>The variable that wants Kodi's opaque white from an all zero colour:
# the idle round buttons on Home, as the comment beside it says.</summary>
WHITE_BY_CHOICE = ("HomeRoundButtonIdleColor",)
# Which setting or expression each flip wraps; a flip round the wrong read is a defect.
FLIP_READS = {
    "flip_movies": "Skin.HasSetting(hide_movies_count)",
    "flip_tvshows": "Skin.HasSetting(hide_tvshows_count)",
    "flip_jellystat": "Skin.HasSetting(hide_jellystat)",
    "flip_engage": "$EXP[engage_block_shown]",
    "flip_logo": "Skin.HasSetting(hide_logo)",
    "flip_weather": "$EXP[weather_widget_shown]",
    "flip_datetime": "Skin.HasSetting(hide_datetime)",
    "flip_version": "Skin.HasSetting(hide_version)",
    "flip_continue": "$PARAM[shown_continue]",
    "flip_recent": "$PARAM[shown_recent]",
    "flip_add": "Skin.HasSetting(bg_add_button)",
    "flip_step": "Skin.HasSetting(bg_step_buttons)",
    "flip_fav": "Skin.HasSetting(hide_favourites)",
    "flip_addons": "Skin.HasSetting(hide_addons)",
    "flip_power": "Skin.HasSetting(hide_power)",
    "flip_lists": "Skin.HasSetting(show_lists_icon)",
    "flip_stats": "Skin.HasSetting(show_stats_icon)",
}
# A flip done as a pair of labels, plain and flipped, rather than an exclusive or.
PAIR_FLIPS = {"flip_greeting": ("$VAR[HomeClockLine]", "$VAR[HomeClockLineFlipped]")}
# Which Skin Settings row each flip follows in the stage.
STAGE_FLIPS = {
    "flip_movies": "7107", "flip_tvshows": "7108", "flip_jellystat": "7137", "flip_engage": "7149", "flip_logo": "7104", "flip_weather": "7122",
    "flip_datetime": "7106", "flip_greeting": "7319", "flip_version": "7105",
    "flip_continue": "7128", "flip_recent": "7144", "flip_add": "7147", "flip_step": "7148",
    "flip_fav": "7123", "flip_addons": "7109", "flip_power": "7112", "flip_lists": "7136", "flip_stats": "7139",
}
SWITCH = "settings_preview"
SWITCH_ID = "7322"
HELP_STRING = "31814"
# every page: since sub item 5 each row is on the stage, a picture row, or named as having no preview
STAGE_PAGES = ("home", "background", "mainmenu", "overall", "media", "video", "lists", "addons", "radarr")
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
        definition = inc.find("definition")
        body = ET.tostring(definition if definition is not None else inc, encoding="unicode")
        used = set(re.findall(r"\$PARAM\[(flip_\w+)\]", body))
        for pname in flips:
            if pname not in used:
                fail("%s: flip %s is declared but never read" % (inc.get("name"), pname))
        for pname in used:
            if pname not in flips:
                fail("%s: flip %s is read but not declared" % (inc.get("name"), pname))
        stripped = XOR.sub("", body)
        # a flip handed on to a nested include is a pass through, not a read
        stripped = re.sub(r'<param name="(flip_\w+)" value="\$PARAM\[\1\]" ?/>', "", stripped)
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
        if inc.get("content") in HOME_INCLUDES + ("BgCaptions", "BgStepButtons", "HomeCornerBar"):
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
                passed.setdefault(p.get("name"), set()).add(p.get("value"))
    for pname, row in STAGE_FLIPS.items():
        if passed.get(pname) != {"Control.HasFocus(%s)" % row}:
            fail("HomeStage passes %s as %r, expected the focus of row %s on every instance" % (pname, passed.get(pname), row))
    for pname in passed:
        if pname not in STAGE_FLIPS:
            fail("HomeStage passes an unknown flip %s" % pname)
    bars = [i for i in stage.iter("include") if i.get("content") == "HomeCornerBar"]
    for bar in bars:
        got = {p.get("name") for p in bar.findall("param") if p.get("name", "").startswith("flip_")}
        if got != {"flip_fav", "flip_addons", "flip_power", "flip_lists", "flip_stats"}:
            fail("a HomeCornerBar instance in the stage lacks a flip: %s" % sorted(got))
    if len(bars) != 3:
        fail("HomeStage should draw HomeCornerBar three times, found %d" % len(bars))
    settings = parse("SkinSettings.xml")
    settings_ids = {c.get("id") for c in settings.iter("control") if c.get("id")}
    stage_ids = set()
    drawn = {i.get("content") for i in stage.iter("include")}
    for inc in stage.iter("include"):
        for p in inc.findall("param"):
            if p.get("name", "").startswith("id") and (p.get("value") or "").isdigit():
                stage_ids.add(p.get("value"))
    # ids fixed inside the includes the stage draws, one level down
    for inc in root.findall("include"):
        if inc.get("name") in drawn:
            stage_ids |= set(re.findall(r'id="(\d+)"', ET.tostring(inc, encoding="unicode")))
            stage_ids |= {p.get("value") for p in inc.iter("param")
                          if p.get("name", "").startswith("id") and (p.get("value") or "").isdigit()}
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
    none = focus_ids(exprs.get("settings_preview_none"))
    for page in STAGE_PAGES:
        if page not in pages:
            fail("no settings page is called %s" % page)
        for rid in pages.get(page, []):
            homes = [n for n, ids in regions.items() if rid in ids]
            if rid in none:
                # named as having no preview on purpose: nowhere else
                if homes or rid in shown or rid in images:
                    fail("row %s on page %s has no preview on purpose and must not be mapped" % (rid, page))
                continue
            if rid in images:
                # the picture form: a pair of pictures in the panel, never the stage
                if homes or rid in shown:
                    fail("row %s on page %s is a picture row and must not be on the stage" % (rid, page))
                continue
            if rid not in shown:
                fail("row %s on page %s is not in settings_preview_shown" % (rid, page))
            if len(homes) != 1:
                fail("row %s on page %s is in %d stage regions, expected one" % (rid, page, len(homes)))
    for rid in shown | images | none | {i for ids in regions.values() for i in ids}:
        if rid not in all_rows:
            fail("preview map names %s, which is not a settings row" % rid)
    print("  %d regions, %d rows mapped" % (len(regions), len(shown)))


def load_picture_table():
    """
    <summary>Imports the generator's table of picture rows without running it.</summary>
    <returns>The build_preview_art module.</returns>
    """
    spec = importlib.util.spec_from_file_location("build_preview_art", os.path.join(ROOT, "build_preview_art.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_info(path):
    """
    <summary>Reads a PNG's size and whether it carries a text chunk.</summary>
    <param name="path">The file.</param>
    <returns>(width, height, has_text) or None when it is not a PNG.</returns>
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    pos, has_text = 8, False
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind in (b"tEXt", b"iTXt", b"zTXt"):
            has_text = True
        pos += 12 + length
    return width, height, has_text


def png_pixels(path):
    """
    <summary>Decodes a PNG to its pixels, for telling two pictures apart.</summary>
    <param name="path">The PNG file.</param>
    <returns>(width, height, channels, pixel bytes), the scanlines unfiltered.</returns>
    <remarks>
    Standard library only, so the test runs under python3 -I: 8 bit RGB or
    RGBA, not interlaced, which is what the generator writes. Comparing the
    inflated stream byte for byte is not enough, since two captures a clock
    tick apart never match byte for byte even when nothing in them changed.
    </remarks>
    """
    with open(path, "rb") as handle:
        data = handle.read()
    pos, idat, header = 8, [], None
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        pos += 12 + length
    width, height, depth, colour, _, _, interlace = header
    if depth != 8 or colour not in (2, 6) or interlace:
        fail("%s is not an 8 bit RGB or RGBA PNG without interlace" % os.path.basename(path))
        return width, height, 3, b""
    channels = 3 if colour == 2 else 4
    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    out, previous = bytearray(), bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up = previous[i]
            upleft = previous[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + ((left + up) >> 1)) & 255
            elif kind == 4:
                p = left + up - upleft
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else upleft)) & 255
        out += line
        previous = line
    return width, height, channels, bytes(out)


def pixels_differing(first, second, tolerance=16):
    """
    <summary>Counts the pixels at which two decoded pictures differ.</summary>
    <param name="first">A png_pixels() result.</param>
    <param name="second">Another, of the same size.</param>
    <param name="tolerance">How far one channel must move to count: above the
    few levels by which a poster ghosting through a menu, or a dim over the
    dark backdrop, moves a pixel between two captures of the same thing.</param>
    <returns>The number of differing pixels, or the whole picture when the
    sizes differ.</returns>
    """
    if first[:3] != second[:3]:
        return first[0] * first[1]
    channels, a, b = first[2], first[3], second[3]
    count = 0
    for i in range(0, len(a), channels):
        for c in range(channels):
            if abs(a[i + c] - b[i + c]) > tolerance:
                count += 1
                break
    return count


def check_picker_cycle(entry, settings):
    """
    <summary>Checks a picker row's pictured values are exactly the values its
    own row in Skin Settings cycles through.</summary>
    <param name="entry">A picker row of the generator's table.</param>
    <param name="settings">SkinSettings.xml parsed.</param>
    <remarks>A value the row can reach but the table does not know would be
    shown the default picture by the map's fallback line, labelled as that
    value; the windows dim's 60 step was found that way.</remarks>
    """
    control = next((c for c in settings.iter("control") if c.get("id") == entry["row"]), None)
    if control is None:
        fail("no control %s in SkinSettings.xml for %s" % (entry["row"], entry["setting"]))
        return
    cycle = set()
    for click in control.iter("onclick"):
        text = click.text or ""
        for match in re.finditer(r"Skin\.SetString\(%s,([^)]*)\)" % re.escape(entry["setting"]), text):
            cycle.add(match.group(1))
        if "Skin.Reset(%s)" % entry["setting"] in text:
            cycle.add("")
    if cycle and cycle != set(entry["values"]):
        fail("%s pictures %s but its row cycles through %s" % (entry["setting"], sorted(entry["values"]), sorted(cycle)))


def test_pictures():
    """
    <summary>Checks the picture rows in the map are exactly the generator's table,
    every picture exists at panel size with no text chunk, and the picture
    variables name each one.</summary>
    """
    print("running test_pictures")
    art = load_picture_table()
    preview = parse("Includes_SettingsPreview.xml")
    exprs = {e.get("name"): e.text or "" for e in preview.iter("expression")}
    mapped = focus_ids(exprs.get("settings_preview_image"))
    table = {e["row"] for e in art.PICTURES}
    if mapped != table:
        fail("picture rows in the map %s differ from the generator's table %s" % (sorted(mapped - table), sorted(table - mapped)))
    toggles = focus_ids(exprs.get("settings_preview_image_toggle"))
    if toggles != {e["row"] for e in art.PICTURES if e["kind"] == "toggle"}:
        fail("settings_preview_image_toggle does not list exactly the toggle rows")
    variables = {v.get("name"): [(x.get("condition") or "", (x.text or "").strip()) for x in v.findall("value")]
                 for v in preview.iter("variable")}
    large = variables.get("SettingsPreviewPicture", [])
    now = variables.get("SettingsPreviewPictureNow", [])
    folder = os.path.join(ROOT, "skin.functional", "media", "preview")
    settings = parse("SkinSettings.xml")
    count = 0
    for e in art.PICTURES:
        for value in art.picture_values(e):
            name = art.picture_name(e["setting"], value)
            path = os.path.join(folder, name)
            count += 1
            if not os.path.isfile(path):
                fail("picture %s is missing" % name)
                continue
            info = png_info(path)
            if info is None or (info[0], info[1]) != tuple(art.PANEL):
                fail("picture %s is not a %dx%d PNG" % (name, art.PANEL[0], art.PANEL[1]))
            elif info[2]:
                fail("picture %s carries a text chunk" % name)
            if not any("Control.HasFocus(%s)" % e["row"] in c and v == "preview/" + name for c, v in large):
                fail("SettingsPreviewPicture has no line giving %s for row %s" % (name, e["row"]))
            if e["kind"] == "toggle" and not any("Control.HasFocus(%s)" % e["row"] in c and v == "preview/" + name for c, v in now):
                fail("SettingsPreviewPictureNow has no line giving %s for row %s" % (name, e["row"]))
        # a toggle's two pictures, or a picker's, must differ by more than a
        # clock tick or a video frame: two the same mean the capture missed the
        # setting (a leaked value, a crop off the control, a label not yet up)
        decoded = {}
        for value in art.picture_values(e):
            path = os.path.join(folder, art.picture_name(e["setting"], value))
            if os.path.isfile(path):
                decoded[value] = png_pixels(path)
        alike = {tuple(sorted(pair)) for pair in e.get("alike", [])}
        for pair in alike:
            if not set(pair) <= set(art.picture_values(e)):
                fail("%s declares an alike pair %s that is not among its values" % (e["setting"], pair))
        for first, second in itertools.combinations(sorted(decoded), 2):
            if (first, second) in alike:
                continue
            if pixels_differing(decoded[first], decoded[second]) < 50:
                fail("pictures for %s at %s and %s are the same" % (e["setting"], first, second))
        if e["kind"] == "picker":
            check_picker_cycle(e, settings)
    named = {v for _, v in large + now}
    for v in named:
        if not os.path.isfile(os.path.join(ROOT, "skin.functional", "media", v)):
            fail("the picture variables name %s, which does not exist" % v)
    print("  %d pictures checked" % count)


def test_no_dim_step_draws_white():
    """
    <summary>Keeps the white sheet from coming back at a no dim step.</summary>
    <remarks>
    Kodi draws an all zero colordiffuse as opaque white, so a dim ladder whose
    clear step is 00000000 covers the screen instead of leaving it alone. It
    was found through the picture of value 0, and a picture that shows it
    passes every other check here, so both the colours and the pictures are
    read. WHITE_BY_CHOICE names the one variable that wants the white. A
    picture fails at a fifth white: no good one passes a tenth, and the two
    sheets this caught were 37 and 57 per cent, the rest being the dialog or
    gallery on top of the sheet.
    </remarks>
    """
    print("running test_no_dim_step_draws_white")
    zero = r"(?:0x)?0{8}"
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        for variable in parse(name).iter("variable"):
            if variable.get("name") in WHITE_BY_CHOICE:
                continue
            for value in variable.findall("value"):
                if re.fullmatch(zero, (value.text or "").strip()):
                    fail("%s in %s has an all zero step, which Kodi draws as opaque white; use 00FFFFFF" % (variable.get("name"), name))
        with open(os.path.join(XML, name), encoding="utf-8") as handle:
            text = handle.read()
        if re.search(r"""(?:colordiffuse(?:=["']|>)|<param [^>]*value=["'])%s\b""" % zero, text):
            fail("%s sets an all zero colour, which Kodi draws as opaque white; use 00FFFFFF" % name)
    colours = os.path.join(ROOT, "skin.functional", "colors")
    for name in sorted(os.listdir(colours)):
        for colour in ET.parse(os.path.join(colours, name)).getroot():
            if re.fullmatch(zero, (colour.text or "").strip()):
                fail("colour %s in %s is all zero, which Kodi draws as opaque white; use 00FFFFFF" % (colour.get("name"), name))
    table = load_picture_table()
    for entry in table.PICTURES:
        if not entry["setting"].endswith("_dim"):
            continue
        for value in table.picture_values(entry):
            path = os.path.join(ROOT, "skin.functional", "media", "preview", table.picture_name(entry["setting"], value))
            width, height, channels, pixels = png_pixels(path)
            white = sum(1 for i in range(0, len(pixels), channels) if min(pixels[i:i + 3]) >= 240)
            if white * 5 > width * height:
                fail("%s is over a fifth white: the dim is covering the screen" % os.path.basename(path))


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
    test_pictures()
    test_no_dim_step_draws_white()
    test_every_row_has_a_help_entry()
    if FAILURES:
        print("test_settings_preview: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_settings_preview: all checks passed")
