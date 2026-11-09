#!/usr/bin/env python3
"""
<summary>
Tests for Text on Accent (roadmap item 48): the helper's shade function and
its write into accent_custom_text, the AccentTextColor variable's structure
(white last with no condition, the dark value gated on the setting being
Auto and the accent being light), the same evaluated as Kodi would over a
truth table of presets, custom shades and themes, that no white text is left on an accent
fill and no variable text has strayed onto a dark panel, that nothing but
the Overall page row writes the setting, and that the row has its label,
help line, strings, preview entries and overlaps nothing on its page.
</summary>
<remarks>
No Kodi is needed. The xbmc modules are stubbed in sys.modules before the
real service.py is imported, so accent_text_shade and update_accent are the
shipped code. The XML is parsed with ElementTree and every focusedcolor,
textcolor and selectedcolor tag is sorted by what Kodi draws behind it, with
the rules written up in PLAN-accent-text.md: a texturefocus of an accent
white.png is a fill, a border.png frame is not; a label inside a
focusedlayout with an accent white.png plate at least 24 px tall is on a
fill; a button's own text is on a fill when its texturenofocus is one
(the skip pill, always focused, draws the accent in both states); a label outside a layout is on a fill only when an earlier image in
its group draws such a plate. Defaults.xml is skipped: Kodi never loads it
and it was left as it was. Exits non zero when a check fails.
Usage:
    python3 tests/test_accent_text.py
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

SETTING = "accent_text"
ROW_ID = "7333"
SHARED_ROW_ID = "7320"
VARIABLE = "AccentTextColor"
LABEL_VARIABLE = "AccentTextLabel"
EXPRESSION = "accent_light"
DARK = "FF101418"
WHITE = "FFFFFFFF"
VAR_TAG = "$VAR[%s]" % VARIABLE
ACCENT = "$VAR[AccentColor]"
ACCENT_HI = "$VAR[AccentHiColor]"
HELP_STRING = "31855"
STRINGS = ("31854", "31855", "31856", "31857")
COLOUR_TAGS = ("focusedcolor", "textcolor", "selectedcolor")
SKIPPED_FILES = ("Defaults.xml",)
# YIQ brightness per preset, from PLAN-accent-text.md: dark text from 128 up
PRESETS = {
    "FF1E88E5": "light", "FFE53935": "light", "FF43A047": "light", "FFFB8C00": "dark",
    "FFFFB300": "dark", "FF8E24AA": "light", "FF00897B": "light", "FFEC407A": "light",
    "FFA3101B": "light", "FFC62828": "light", "FFFFEB3B": "dark",
}

PRESET_NAMES = {
    "blue": "FF1E88E5", "red": "FFE53935", "green": "FF43A047", "orange": "FFFB8C00",
    "amber": "FFFFB300", "purple": "FF8E24AA", "teal": "FF00897B", "pink": "FFEC407A",
}
THEMES = ("", "halloween", "devilsnight", "christmas", "christmaseve")

BUILTINS = []
INFO = {}
FAILURES = []


class _Window:
    """<summary>Stand in for xbmcgui.Window: accepts and ignores properties.</summary>"""

    def __init__(self, _id=0):
        """<summary>Any window id is accepted.</summary>"""

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Ignored.</summary>"""

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Always empty.</summary>"""
        return ""


def _stub_kodi():
    """
    <summary>Installs the xbmc module stubs service.py imports, then imports it.</summary>
    <returns>The imported service module.</returns>
    <remarks>getInfoLabel answers from INFO and executebuiltin appends to
    BUILTINS, so update_accent's reads and writes can be driven and seen.</remarks>
    """
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
    xbmc.log = lambda *a, **k: None
    xbmc.executeJSONRPC = lambda _text: "{}"
    xbmc.getCondVisibility = lambda _text: False
    xbmc.getInfoLabel = lambda label: INFO.get(label, "")
    xbmc.getLocalizedString = lambda _sid: ""
    xbmc.executebuiltin = lambda text, *a, **k: BUILTINS.append(text)
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


def test_shade(service):
    """
    <summary>Checks the shade function on every preset, on the custom yellow
    that started the item, at the 128 boundary, on case and spaces, and on
    values that are not a colour.</summary>
    <param name="service">The imported service module.</param>
    """
    print("running test_shade")
    for value, want in PRESETS.items():
        got = service.accent_text_shade(value)
        if got != want:
            fail("accent_text_shade(%s) is %r, expected %r" % (value, got, want))
    if service.accent_text_shade("FF808080") != "dark":
        fail("a brightness of exactly 128 should take dark text")
    if service.accent_text_shade("FF7F7F7F") != "light":
        fail("a brightness of 127 should take white text")
    if service.accent_text_shade(" ffffb300 ") != "dark":
        fail("lower case with spaces should be read as the colour it is")
    if service.accent_text_shade("00FFB300") != "dark":
        fail("alpha should be ignored")
    for bad in ("", None, "FFB300", "FFFFB3000", "GGFFB300", "amber"):
        if service.accent_text_shade(bad) != "":
            fail("accent_text_shade(%r) should be empty" % (bad,))


def test_update_accent_writes_shade(service):
    """
    <summary>Checks update_accent writes accent_custom_text beside the
    highlight: dark for a light custom accent, light for a dark one, empty
    for a value that is not a colour, and nothing at all when the value has
    not changed.</summary>
    <param name="service">The imported service module.</param>
    """
    print("running test_update_accent_writes_shade")
    helper = object.__new__(service.FunctionalHelper)
    helper._accent_custom_seen = None
    cases = (("FFFFEB3B", "dark", "FFFFF17C"), ("FF1E88E5", "light", "FF69AFED"), ("rubbish", "", ""))
    for value, shade, highlight in cases:
        INFO.clear()
        INFO["Skin.String(accent_custom)"] = value
        del BUILTINS[:]
        helper.update_accent()
        want_text = 'Skin.SetString(accent_custom_text,"%s")' % shade
        want_hi = 'Skin.SetString(accent_custom_hi,"%s")' % highlight
        if want_text not in BUILTINS:
            fail("update_accent on %s did not write %s, wrote %s" % (value, want_text, BUILTINS))
        if want_hi not in BUILTINS:
            fail("update_accent on %s did not keep writing the highlight %s" % (value, want_hi))
        del BUILTINS[:]
        helper.update_accent()
        if BUILTINS:
            fail("update_accent wrote again with the value unchanged: %s" % BUILTINS)


def test_variable_structure():
    """
    <summary>Checks the variable resolves to white unless the setting is Auto
    and the accent is light, and that the light accent expression names the
    two light presets, the custom shade, and never a seasonal theme.</summary>
    """
    print("running test_variable_structure")
    root = parse("Includes.xml")
    var = next((v for v in root.iter("variable") if v.get("name") == VARIABLE), None)
    if var is None:
        fail("Includes.xml has no variable %s" % VARIABLE)
        return
    values = list(var.findall("value"))
    if len(values) != 2:
        fail("%s should have two values, found %d" % (VARIABLE, len(values)))
        return
    dark, white = values
    cond = dark.get("condition") or ""
    if (dark.text or "").strip() != DARK:
        fail("the dark value is %r, expected %s, the skin's bg" % (dark.text, DARK))
    if "String.IsEqual(Skin.String(%s),auto)" % SETTING not in cond or "$EXP[%s]" % EXPRESSION not in cond:
        fail("the dark value must need the setting to be auto and the accent to be light, found %r" % cond)
    if (white.text or "").strip() != WHITE or white.get("condition"):
        fail("the last value must be white with no condition, so an unset setting draws today's look")
    expr = next((e for e in root.iter("expression") if e.get("name") == EXPRESSION), None)
    if expr is None:
        fail("Includes.xml has no expression %s" % EXPRESSION)
        return
    body = expr.text or ""
    for needed in ("String.IsEqual(Skin.String(accent_color),amber)", "String.IsEqual(Skin.String(accent_color),orange)",
                   "String.IsEqual(Skin.String(accent_color),custom)", "String.IsEqual(Skin.String(accent_custom_text),dark)",
                   "!$EXP[theme_halloween]", "!$EXP[theme_christmas]"):
        if needed not in body:
            fail("%s lacks %s" % (EXPRESSION, needed))
    for preset in ("blue", "red", "green", "purple", "teal", "pink"):
        if "accent_color),%s)" % preset in body:
            fail("%s names %s, which takes white text" % (EXPRESSION, preset))
    label = next((v for v in root.iter("variable") if v.get("name") == LABEL_VARIABLE), None)
    if label is None or [(v.text or "").strip() for v in label.findall("value")] != ["$LOCALIZE[31857]", "$LOCALIZE[31856]"]:
        fail("%s should read Auto then White" % LABEL_VARIABLE)


def _tokens(expression):
    """
    <summary>Splits a Kodi boolean expression into operators and atoms.</summary>
    <param name="expression">The expression text.</param>
    <returns>A list of "[", "]", "+", "|", "!" and atom strings; an atom is
    an info condition such as String.IsEqual(Skin.String(a),b) or a $EXP
    reference, read up to the next operator outside its own brackets.</returns>
    """
    tokens, i = [], 0
    while i < len(expression):
        ch = expression[i]
        if ch.isspace():
            i += 1
        elif ch in "[]+|!":
            tokens.append(ch)
            i += 1
        else:
            depth, start = 0, i
            while i < len(expression):
                c = expression[i]
                if c in "([":
                    depth += 1
                elif c in ")]":
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0 and (c in "+|" or c.isspace()):
                    break
                i += 1
            tokens.append(expression[start:i])
    return tokens


def evaluate(expression, state, expressions):
    """
    <summary>Evaluates a Kodi boolean expression against a skin state.</summary>
    <param name="expression">The expression text, as written in the XML.</param>
    <param name="state">Skin strings and Home properties by name, missing
    ones empty.</param>
    <param name="expressions">Every named expression of Includes.xml, for
    $EXP references, each wrapped in brackets as Kodi stores them.</param>
    <returns>True or False, with Kodi's precedence: ! binds tightest, then
    + (and), then | (or), and [ ] groups.</returns>
    <remarks>Only the atoms this skin's accent logic uses are understood:
    String.IsEqual and String.IsEmpty over Skin.String and
    Window(home).Property, and $EXP. Anything else is a test failure, not a
    guess.</remarks>
    """
    tokens = _tokens(expression)
    pos = [0]

    def atom(token):
        m = re.fullmatch(r"\$EXP\[([A-Za-z0-9_]+)\]", token)
        if m:
            if m.group(1) not in expressions:
                fail("expression %s is not defined" % m.group(1))
                return False
            return evaluate(expressions[m.group(1)], state, expressions)
        m = re.fullmatch(r"String\.IsEqual\((?:Skin\.String|Window\(home\)\.Property)\(([A-Za-z0-9_]+)\),([^)]*)\)", token)
        if m:
            return state.get(m.group(1), "") == m.group(2)
        m = re.fullmatch(r"String\.IsEmpty\((?:Skin\.String|Window\(home\)\.Property)\(([A-Za-z0-9_]+)\)\)", token)
        if m:
            return state.get(m.group(1), "") == ""
        fail("the evaluator does not understand %r" % token)
        return False

    def primary():
        token = tokens[pos[0]]
        pos[0] += 1
        if token == "!":
            return not primary()
        if token == "[":
            value = disjunction()
            if pos[0] >= len(tokens) or tokens[pos[0]] != "]":
                fail("unbalanced brackets in %r" % expression)
                return value
            pos[0] += 1
            return value
        return atom(token)

    def conjunction():
        value = primary()
        while pos[0] < len(tokens) and tokens[pos[0]] == "+":
            pos[0] += 1
            value = primary() and value
        return value

    def disjunction():
        value = conjunction()
        while pos[0] < len(tokens) and tokens[pos[0]] == "|":
            pos[0] += 1
            value = conjunction() or value
        return value

    result = disjunction()
    if pos[0] != len(tokens):
        fail("trailing tokens in %r" % expression)
    return result


def dark_text(state, root):
    """
    <summary>Which colour the AccentTextColor variable resolves to for a state.</summary>
    <param name="state">Skin strings and Home properties by name.</param>
    <param name="root">Includes.xml parsed.</param>
    <returns>True when the first value whose condition holds is the dark one.</returns>
    """
    expressions = {e.get("name"): "[" + (e.text or "") + "]" for e in root.iter("expression")}
    var = next(v for v in root.iter("variable") if v.get("name") == VARIABLE)
    for value in var.findall("value"):
        cond = value.get("condition")
        if cond is None or evaluate(cond, state, expressions):
            return (value.text or "").strip() == DARK
    return False


def test_variable_truth_table():
    """
    <summary>Evaluates the variable's condition and the light accent expression
    as Kodi would, over every preset, the custom shades and every theme, with
    the setting unset and set to Auto: unset is never dark, Auto is dark on
    exactly the presets the shade table calls light and on a custom accent
    the service called dark, and never under a seasonal theme.</summary>
    """
    print("running test_variable_truth_table")
    root = parse("Includes.xml")
    expressions = {e.get("name"): "[" + (e.text or "") + "]" for e in root.iter("expression")}
    for name, body in expressions.items():
        if name == EXPRESSION:
            for preset in PRESET_NAMES:
                named = "accent_color),%s)" % preset in body
                light = PRESETS[PRESET_NAMES[preset]] == "dark"
                if named != light:
                    fail("%s %s %s but the shade table says its text is %s" % (
                        EXPRESSION, "names" if named else "omits", preset, PRESETS[PRESET_NAMES[preset]]))
    states = []
    for preset in list(PRESET_NAMES) + [""]:
        states.append({"accent_color": preset})
    for shade in ("dark", "light", ""):
        states.append({"accent_color": "custom", "accent_custom": "FFFFEB3B", "accent_custom_text": shade})
    states.append({"accent_color": "custom", "accent_custom": "", "accent_custom_text": "dark"})
    checked = 0
    for base in states:
        for theme in THEMES:
            for setting in ("", "auto", "white", "rubbish"):
                state = dict(base, theme_name=theme, accent_text=setting)
                got = dark_text(state, root)
                if setting != "auto" or theme:
                    want = False
                elif state["accent_color"] == "custom":
                    want = state["accent_custom"] != "" and state["accent_custom_text"] == "dark"
                else:
                    want = PRESETS.get(PRESET_NAMES.get(state["accent_color"], ""), "light") == "dark"
                checked += 1
                if got != want:
                    fail("state %s resolves %s, expected %s" % (state, "dark" if got else "white", "dark" if want else "white"))
    print("  %d states evaluated" % checked)


def _is_plate(el):
    """
    <summary>Whether a texture element draws a solid accent fill.</summary>
    <param name="el">A texture, texturefocus or similar element, or None.</param>
    <returns>True for white.png diffused with either accent variable and no
    border attribute; border.png frames and tinted icons are not fills.</returns>
    """
    if el is None or el.get("border"):
        return False
    return el.get("colordiffuse", "") in (ACCENT, ACCENT_HI) and (el.text or "").strip() == "white.png"


def _tall(ctrl):
    """
    <summary>Whether an image control is tall enough to be a plate.</summary>
    <param name="ctrl">The image control.</param>
    <returns>True at 24 px or more, or with no numeric height; a thinner
    accent image is a rule or stripe with text beside it, not on it.</returns>
    """
    height = text(ctrl, "height")
    return not height.isdigit() or int(height) >= 24


def classify(el, parent):
    """
    <summary>Sorts one colour tag by what Kodi draws behind its text.</summary>
    <param name="el">A focusedcolor, textcolor or selectedcolor element.</param>
    <param name="parent">The child to parent map of its tree.</param>
    <returns>"accent" when the text sits on an accent fill, "panel" otherwise.</returns>
    """
    ctrl = parent.get(el)
    if el.tag == "textcolor" and _is_plate(ctrl.find("texturenofocus")):
        return "accent"
    if el.tag == "focusedcolor":
        focus = ctrl.find("texturefocus")
        if _is_plate(focus):
            return "accent"
        if focus is not None:
            return "panel"
    layout = None
    node = parent.get(el)
    while node is not None:
        if node.tag in ("focusedlayout", "itemlayout"):
            layout = node
            break
        node = parent.get(node)
    if layout is not None:
        if layout.tag == "itemlayout":
            return "panel"
        for img in layout.iter("control"):
            if img.get("type") == "image" and _is_plate(img.find("texture")) and _tall(img):
                return "accent"
        return "panel"
    group = parent.get(ctrl)
    if group is None:
        return "panel"
    for sib in group:
        if sib is ctrl:
            break
        if sib.tag == "control" and sib.get("type") == "image" and _is_plate(sib.find("texture")) and _tall(sib):
            return "accent"
    return "panel"


def test_every_tag_matches_its_background():
    """
    <summary>Checks no white focusedcolor, textcolor or selectedcolor is left
    on an accent fill, and the variable is used only on one: text on the
    skin's dark panels, over video or over fanart stays white.</summary>
    """
    print("running test_every_tag_matches_its_background")
    on_accent = 0
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml") or name in SKIPPED_FILES:
            continue
        root = parse(name)
        parent = {c: p for p in root.iter() for c in p}
        for el in root.iter():
            if el.tag not in COLOUR_TAGS:
                continue
            value = (el.text or "").strip()
            if value not in ("white", WHITE, VAR_TAG):
                continue
            where = classify(el, parent)
            ctrl = parent.get(el)
            label = "%s %s id=%s" % (name, ctrl.get("type", ctrl.tag), ctrl.get("id", ""))
            if value == VAR_TAG:
                on_accent += 1
                if where != "accent":
                    fail("%s has %s on a dark panel; that text stays white (%s)" % (label, VAR_TAG, el.tag))
            elif where == "accent":
                fail("%s has white %s on an accent fill; it should read %s" % (label, el.tag, VAR_TAG))
    if on_accent < 400:
        fail("only %d tags read %s; the sweep found about 500" % (on_accent, VAR_TAG))
    print("  %d tags read the variable" % on_accent)


def test_off_by_default():
    """
    <summary>Checks nothing but the row's own clicks write the setting, and
    that the service never touches it.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        with open(os.path.join(XML, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, start=1):
                if re.search(r"Skin\.(SetString|Reset|SetBool|ToggleSetting)\(%s[,)]" % SETTING, line):
                    writers.append((name, number))
    if {w[0] for w in writers} != {"SkinSettings.xml"} or len(writers) != 2:
        fail("the row's two clicks in SkinSettings.xml should be the only writers, found %s" % writers)
    with open(SERVICE, encoding="utf-8") as fh:
        if re.search(r"\b%s\b" % SETTING, fh.read()):
            fail("service.py mentions the setting; it is skin XML only")


def test_row():
    """
    <summary>Checks the Overall page row: its label and variable, its two
    clicks cycling White and Auto, its focus links to the row it shares a
    line with, that it overlaps nothing on the page, its help entry, its
    strings with a Where line, and its preview entries.</summary>
    """
    print("running test_row")
    settings = parse("SkinSettings.xml")
    parent = {c: p for p in settings.iter() for c in p}
    row = next((c for c in settings.iter("control") if c.get("id") == ROW_ID), None)
    shared = next((c for c in settings.iter("control") if c.get("id") == SHARED_ROW_ID), None)
    if row is None or shared is None:
        fail("SkinSettings.xml lacks control %s or %s" % (ROW_ID, SHARED_ROW_ID))
        return
    if text(row, "label") != "$LOCALIZE[31854] $VAR[%s]" % LABEL_VARIABLE:
        fail("row label is %r" % text(row, "label"))
    if text(row, "focusedcolor") != VAR_TAG:
        fail("the row's own focused text should read the variable")
    clicks = [(c.get("condition") or "", (c.text or "").strip()) for c in row.findall("onclick")]
    want = [("String.IsEqual(Skin.String(%s),auto)" % SETTING, "Skin.Reset(%s)" % SETTING),
            ("!String.IsEqual(Skin.String(%s),auto)" % SETTING, "Skin.SetString(%s,auto)" % SETTING)]
    if clicks != want:
        fail("the row's clicks are %s" % clicks)
    if text(shared, "onright") != ROW_ID or text(row, "onleft") != SHARED_ROW_ID:
        fail("rows %s and %s should link left and right" % (SHARED_ROW_ID, ROW_ID))
    if text(row, "top") != text(shared, "top") or int(text(row, "left")) < int(text(shared, "left")) + int(text(shared, "width")):
        fail("the row should sit on the same line as %s, to its right" % SHARED_ROW_ID)
    # The page's labels may share a box when their visibility conditions
    # are exclusive (the two seasonal theme notes), so rows are checked
    # against each other and the new row against everything.
    page = parent[row]
    boxes = []
    for c in page:
        if c.tag != "control":
            continue
        try:
            left, top, width, height = (int(text(c, t)) for t in ("left", "top", "width", "height"))
        except ValueError:
            continue
        if height < 10:
            continue
        boxes.append((left, top, left + width, top + height, c.get("id") or c.get("type"), c.get("id") is not None))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if not (a[5] and b[5]) and ROW_ID not in (a[4], b[4]):
                continue
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                fail("Overall page: %s overlaps %s" % (a[4], b[4]))
    help_root = parse("Includes_SettingsHelp.xml")
    shown = next((e for e in help_root.iter("expression") if e.get("name") == "settings_help_shown"), None)
    if shown is None or "Control.HasFocus(%s)" % ROW_ID not in (shown.text or ""):
        fail("settings_help_shown does not list control %s" % ROW_ID)
    if not any(v.get("condition") == "Control.HasFocus(%s)" % ROW_ID and (v.text or "").strip() == "$LOCALIZE[%s]" % HELP_STRING
               for v in help_root.iter("value")):
        fail("the help map has no line for control %s to string %s" % (ROW_ID, HELP_STRING))
    with open(PO, encoding="utf-8") as fh:
        po = fh.read()
    for sid in STRINGS:
        if 'msgctxt "#%s"' % sid not in po:
            fail("strings.po has no string %s" % sid)
    m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % HELP_STRING, po)
    if m and "[CR]Where:" not in m.group(1):
        fail("help string %s has no Where line" % HELP_STRING)
    preview = parse("Includes_SettingsPreview.xml")
    image = next((e for e in preview.iter("expression") if e.get("name") == "settings_preview_image"), None)
    if image is None or "Control.HasFocus(%s)" % ROW_ID not in (image.text or ""):
        fail("the row is not a picture row in settings_preview_image")
    pictures = {(v.text or "").strip() for v in preview.iter("value") if "Control.HasFocus(%s)" % ROW_ID in (v.get("condition") or "")}
    if pictures != {"preview/accent_text_default.png", "preview/accent_text_auto.png"}:
        fail("the picture variable names %s for the row" % sorted(pictures))


if __name__ == "__main__":
    SERVICE_MODULE = _stub_kodi()
    test_shade(SERVICE_MODULE)
    test_update_accent_writes_shade(SERVICE_MODULE)
    test_variable_structure()
    test_variable_truth_table()
    test_every_tag_matches_its_background()
    test_off_by_default()
    test_row()
    if FAILURES:
        print("test_accent_text: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_accent_text: all checks passed")
