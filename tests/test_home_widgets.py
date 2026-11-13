#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 46, the Home widget rows, written from the spec: the
settings rows with their help, preview and strings, the Home expressions and
the off state they give, the variables, the three playlists, the Home XML
wiring, the navigation chains for every combination of shown rows, and the
helper's own paths: the pick command, publishing a named list, the play
command and the rename or delete of a list a row uses.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs, the rig of stubbed labels, builtins and
library calls, and the reader of Kodi's boolean grammar all come from
tests/test_watchlist.py (itself built on tests/test_lists_api.py). Navigation
is read the way Kodi reads it: the first onup, ondown, onleft or onright
whose condition is true wins, and a condition on Control.IsVisible is true
for the controls the test lists as visible. How a row looks on a TV is the
live check's job. Exits non zero when a check fails.

Usage:
    python3 tests/test_home_widgets.py
</remarks>
"""

import itertools
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_watchlist as W  # noqa: E402  (installs the Kodi stubs, imports service)

T = W.T
service = W.service
Env = W.Env
evaluate = W.evaluate
EXPRESSIONS = W.EXPRESSIONS
XML = W.XML
SKIN = W.SKIN
ROOT = W.ROOT
FAILURES = []
CHECKS = []

SOURCES = ["recent_movies", "recent_episodes", "inprogress_movies", "inprogress_episodes",
           "unwatched_movies", "unwatched_tvshows", "random_movies"]
LABEL_IDS = [31910, 31911, 31912, 31913, 31914, 31915, 31916]
LIB_ID = {1: "9252", 2: "9254", 3: "9256"}
STATIC_ID = {1: "9253", 2: "9255", 3: "9257"}
TABS = ["9210", "9212", "9214"]


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def check(cond, what):
    """
    <summary>Records one check and its result, failing when it does not hold.</summary>
    <param name="cond">True when the check passes.</param>
    <param name="what">What was being checked.</param>
    <returns>The condition, so a caller can stop early.</returns>
    """
    CHECKS.append((bool(cond), what))
    if not cond:
        fail(what)
    return bool(cond)


def parse(name):
    """
    <summary>Parses one file of the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>The XML root.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def controls(root, cid):
    """
    <summary>Every control with an id, wherever it sits.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>A list of elements, possibly empty.</returns>
    """
    return [c for c in root.iter("control") if c.get("id") == cid]


def first_target(ctrl, tag, env):
    """
    <summary>Where a control's navigation tag leads, the first true condition winning.</summary>
    <param name="ctrl">The control element.</param>
    <param name="tag">onup, ondown, onleft or onright.</param>
    <param name="env">The state the conditions are read against.</param>
    <returns>The target id as text, or None when none matches or a condition lies beyond what the reader knows.</returns>
    """
    for node in ctrl.findall(tag):
        cond = node.get("condition")
        try:
            ok = evaluate(cond, env) if cond else True
        except (ValueError, KeyError):
            return None
        if ok:
            return (node.text or "").strip()
    return None


def lookup(root, name):
    """
    <summary>Reads one skin variable as a list of (condition, text) pairs.</summary>
    <param name="root">An XML root holding the variable.</param>
    <param name="name">The variable's name.</param>
    <returns>The pairs in file order, or None when the variable is absent.</returns>
    """
    for var in root.iter("variable"):
        if var.get("name") == name:
            return [(v.get("condition"), (v.text or "").strip()) for v in var.findall("value")]
    return None


def resolve(pairs, env):
    """
    <summary>The first value of a variable whose condition holds.</summary>
    <param name="pairs">The pairs from lookup.</param>
    <param name="env">The state.</param>
    <returns>The text, or None when none holds.</returns>
    """
    for cond, text in pairs:
        if not cond or evaluate(cond, env):
            return text
    return None


# ---- Strings, settings, help and preview --------------------------------------

def test_strings():
    """
    <summary>Strings 31906 to 31918, 31920 and 31893 exist once each with the
    spec's texts, and the two help strings carry a Where: line.</summary>
    """
    print("running test_strings")
    po = W.read(W.STRINGS)
    for sid in list(range(31906, 31919)) + [31920, 31893]:
        check(bool(T.STRINGS.get(sid)), "string %d is missing or empty" % sid)
        check(po.count('msgctxt "#%d"' % sid) == 1, "string %d should be defined exactly once" % sid)
    check(T.STRINGS.get(31917) == "List: %s", "31917 should be 'List: %%s', got %r" % T.STRINGS.get(31917))
    check(T.STRINGS.get(31893) == "Off", "31893 should be 'Off', got %r" % T.STRINGS.get(31893))
    check(T.STRINGS.get(31920) == "Choose what Home Row %d shows", "31920, got %r" % T.STRINGS.get(31920))
    for sid in (31909, 31918):
        check("Where:" in T.STRINGS.get(sid, ""), "help string %d should carry a Where: line" % sid)
    labels = [T.STRINGS.get(s, "") for s in LABEL_IDS]
    check(len(set(labels)) == 7 and all(labels), "the seven source labels should be distinct and not empty, got %r" % labels)


def test_settings_rows():
    """
    <summary>Rows 7186 to 7188: buttons labelled with the row string and the
    row's source name, OK sends pick:N, each id is used once.</summary>
    """
    print("running test_settings_rows")
    root = parse("SkinSettings.xml")
    for n, (cid, sid) in enumerate((("7186", 31906), ("7187", 31907), ("7188", 31908)), 1):
        found = controls(root, cid)
        if not check(len(found) == 1, "row %s should exist exactly once, got %d" % (cid, len(found))):
            continue
        row = found[0]
        check(row.get("type") == "button", "row %s should be a button" % cid)
        want = "$LOCALIZE[%d] $VAR[WidgetRowName%d]" % (sid, n)
        check(row.findtext("label") == want, "row %s label should be %r, got %r" % (cid, want, row.findtext("label")))
        clicks = [(o.text or "").strip() for o in row.findall("onclick")]
        check(clicks == ["Skin.SetString(widget_command,pick:%d)" % n],
              "row %s OK should send pick:%d, got %r" % (cid, n, clicks))
    # Off by default: nothing outside the settings page sets a row.
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml") and name != "SkinSettings.xml":
            text = W.read(os.path.join(XML, name))
            check(not re.search(r"SetString\(widget[123],", text), "%s should not switch a Home row on" % name)
    check(not re.search(r"widget[123]", W.read(os.path.join(SKIN, "addon.xml"))), "addon.xml should not name a row")


def test_help_and_preview():
    """
    <summary>The help map gives each row its string, the rows are in
    settings_help_shown, in settings_preview_none and in no other preview
    expression.</summary>
    """
    print("running test_help_and_preview")
    help_text = W.read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    for cid, sid in (("7186", "31909"), ("7187", "31918"), ("7188", "31918")):
        check('<value condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (cid, sid) in help_text,
              "the help map should give %s string %s" % (cid, sid))
        check(evaluate(EXPRESSIONS["settings_help_shown"], Env(focus={cid})), "%s should be in settings_help_shown" % cid)
        check(evaluate(EXPRESSIONS["settings_preview_none"], Env(focus={cid})), "%s should be in settings_preview_none" % cid)
    for name, text in sorted(EXPRESSIONS.items()):
        if name == "settings_preview_none" or name == "settings_help_shown":
            continue
        for cid in ("7186", "7187", "7188"):
            if "preview" in name or "stage" in name:
                check("Control.HasFocus(%s)" % cid not in text, "%s should not be in the expression %s" % (cid, name))
    for cid in ("7186", "7187", "7188"):
        check(not evaluate(EXPRESSIONS["settings_preview_shown"], Env(focus={cid})), "%s should not be in settings_preview_shown" % cid)


# ---- Expressions and the off state --------------------------------------------

def test_expressions():
    """
    <summary>widgets_on follows the three strings; menu_top and menu_bottom
    read exactly as before with every row off, for every menu position; one
    row on forces the top; greeting_room and its flipped form read menu_top.</summary>
    """
    print("running test_expressions")
    for combo in itertools.product(["", "recent_movies", "list"], repeat=3):
        strings = {"widget%d" % i: v for i, v in enumerate(combo, 1)}
        want = any(combo)
        check(evaluate("$EXP[widgets_on]", Env(strings=strings)) == want,
              "widgets_on for %r should be %s" % (combo, want))
    check("$EXP[menu_top]" in EXPRESSIONS["greeting_room"], "greeting_room should read $EXP[menu_top]")
    check("$EXP[menu_top]" in EXPRESSIONS["greeting_room_flipped"], "greeting_room_flipped should read $EXP[menu_top]")
    for pos in ("", "top", "bottom", "centre", "middle", "other"):
        off = Env(strings={"menu_position": pos})
        check(not evaluate("$EXP[widgets_on]", off), "widgets_on should be false with all rows off, position %r" % pos)
        check(evaluate("$EXP[menu_top]", off) == (pos == "top"), "menu_top with rows off, position %r, should be unchanged" % pos)
        check(evaluate("$EXP[menu_bottom]", off) == (pos == "bottom"), "menu_bottom with rows off, position %r, should be unchanged" % pos)
        # greeting_room must follow menu_top however it is spelt.
        check(evaluate("$EXP[greeting_room]", off) == evaluate("$EXP[greeting_room]", Env(strings={"menu_position": pos})),
              "greeting_room should be stable for position %r" % pos)
        for row in (1, 2, 3):
            on = Env(strings={"menu_position": pos, "widget%d" % row: "random_movies"})
            check(evaluate("$EXP[menu_top]", on), "menu_top should be true with row %d on, position %r" % (row, pos))
            check(not evaluate("$EXP[menu_bottom]", on), "menu_bottom should be false with row %d on, position %r" % (row, pos))
            check(evaluate("$EXP[greeting_room]", on) == evaluate("$EXP[menu_top]", on) or
                  "$EXP[menu_top]" in EXPRESSIONS["greeting_room"],
                  "greeting_room should follow menu_top with row %d on" % row)


def test_variables():
    """
    <summary>WidgetRowPathN and WidgetRowNameN give the spec's paths and names
    for every source, the list name for a list, and Off when the row is off.</summary>
    """
    print("running test_variables")
    root = parse("Includes.xml")
    paths = ["special://skin/playlists/recent_movies.xsp", "special://skin/playlists/recent_episodes.xsp",
             "$VAR[ContinueMoviesPath]", "$VAR[ContinueEpisodesPath]",
             "special://skin/playlists/widget_unwatched_movies.xsp",
             "special://skin/playlists/widget_unwatched_tvshows.xsp",
             "special://skin/playlists/widget_random_movies.xsp"]
    check(lookup(root, "ContinueMoviesPath") is not None and lookup(root, "ContinueEpisodesPath") is not None,
          "the Continue paths the in progress rows reuse should exist")
    for n in (1, 2, 3):
        path_var = lookup(root, "WidgetRowPath%d" % n)
        name_var = lookup(root, "WidgetRowName%d" % n)
        if not check(path_var is not None and name_var is not None, "the variables for row %d should exist" % n):
            continue
        for src, path, sid in zip(SOURCES, paths, LABEL_IDS):
            env = Env(strings={"widget%d" % n: src})
            check(resolve(path_var, env) == path, "row %d path for %s should be %s, got %r" % (n, src, path, resolve(path_var, env)))
            check(resolve(name_var, env) == "$LOCALIZE[%d]" % sid, "row %d name for %s should be label %d, got %r" % (n, src, sid, resolve(name_var, env)))
        lst = Env(strings={"widget%d" % n: "list", "widget%d_list" % n: "Weekend"})
        name = resolve(name_var, lst) or ""
        check("widget%d_list" % n in name, "row %d name for a list should read widget%d_list, got %r" % (n, n, name))
        off = resolve(name_var, Env())
        check(off == "$LOCALIZE[31893]", "row %d name when off should be 31893, got %r" % (n, off))
        for p in ("", "list"):
            got = resolve(path_var, Env(strings={"widget%d" % n: p}))
            check(got in (None, ""), "row %d path for source %r should be empty, got %r" % (n, p, got))


def test_playlists():
    """
    <summary>The three playlists: rules, order and limit as the spec gives.</summary>
    """
    print("running test_playlists")
    base = os.path.join(SKIN, "playlists")
    specs = {"widget_unwatched_movies.xsp": ("movies", "playcount"),
             "widget_unwatched_tvshows.xsp": ("tvshows", "numwatched"),
             "widget_random_movies.xsp": ("movies", None)}
    for name, (kind, field) in specs.items():
        path = os.path.join(base, name)
        if not check(os.path.exists(path), "%s should exist" % name):
            continue
        root = ET.parse(path).getroot()
        check(root.tag == "smartplaylist" and root.get("type") == kind, "%s should be a %s playlist" % (name, kind))
        check(root.findtext("limit") == "15", "%s should have limit 15, got %r" % (name, root.findtext("limit")))
        rules = root.findall("rule")
        order = root.find("order")
        if field:
            ok = len(rules) == 1 and rules[0].get("field") == field and rules[0].get("operator") == "is" \
                and rules[0].findtext("value") == "0"
            check(ok, "%s should have the one rule %s is 0" % (name, field))
            check(order is not None and order.text == "dateadded" and order.get("direction") == "descending",
                  "%s should be newest added first" % name)
        else:
            check(not rules, "%s should have no rules" % name)
            check(order is not None and order.text == "random", "%s should be in random order" % name)
    for name in ("recent_movies.xsp", "recent_episodes.xsp"):
        check(os.path.exists(os.path.join(base, name)), "%s should still exist" % name)


# ---- Home wiring ---------------------------------------------------------------

class NEnv(Env):
    """<summary>An Env that also knows which add-ons are installed.</summary>"""

    def __init__(self, addons=(), **kw):
        """
        <summary>Keep the state.</summary>
        <param name="addons">Ids of installed add-ons.</param>
        <param name="kw">Everything Env takes.</param>
        """
        super().__init__(**kw)
        self.addons = set(addons)


_BASE_ATOM = W.atom


def _atom(text, env):
    """
    <summary>Evaluates one plain condition, adding Weather.IsFetched (read as false), System.HasAddon and the empty test on a Home property.</summary>
    <param name="text">The condition.</param>
    <param name="env">The state.</param>
    <returns>True or False.</returns>
    <exception cref="ValueError">When the condition is not one the reader knows.</exception>
    """
    t = text.strip()
    if t == "Weather.IsFetched":
        return False
    m = re.fullmatch(r"System\.HasAddon\(([\w.]+)\)", t)
    if m:
        return m.group(1) in getattr(env, "addons", ())
    m = re.fullmatch(r"String\.IsEmpty\(Window\(home\)\.Property\(([\w.]+)\)\)", t)
    if m:
        return not env.props.get(m.group(1), "")
    return _BASE_ATOM(text, env)


_EXPAND_CACHE = {}
_BASE_EXPAND = W.expand


def _expand(text, params=None):
    """
    <summary>A cached expand, so the large sweeps stay quick.</summary>
    <param name="text">A condition.</param>
    <param name="params">Include parameters; uncached when given.</param>
    <returns>The condition with no references left.</returns>
    """
    if params:
        return _BASE_EXPAND(text, params)
    if text not in _EXPAND_CACHE:
        _EXPAND_CACHE[text] = _BASE_EXPAND(text, params)
    return _EXPAND_CACHE[text]


W.atom = _atom
W.expand = _expand

NARROW_LIB = {n: str(int(LIB_ID[n]) + 10) for n in (1, 2, 3)}
NARROW_STATIC = {n: str(int(STATIC_ID[n]) + 10) for n in (1, 2, 3)}
ALL_ROW_IDS = set(LIB_ID.values()) | set(STATIC_ID.values()) | set(NARROW_LIB.values()) | set(NARROW_STATIC.values())
LIB_IDS = set(LIB_ID.values()) | set(NARROW_LIB.values())
CAPS = ["9302", "9303", "9304"]
BARS = ["9110", "9120", "9100"]
ENGAGE_ON = dict(settings={"show_engage_list"}, addons={"service.engage"}, props={"Engage.Next.1.Label": "x"})


def row_of(cid):
    """
    <summary>The row a row list id belongs to.</summary>
    <param name="cid">The id as text.</param>
    <returns>1, 2 or 3.</returns>
    </summary>
    """
    for n in (1, 2, 3):
        if cid in (LIB_ID[n], STATIC_ID[n], NARROW_LIB[n], NARROW_STATIC[n]):
            return n
    raise KeyError(cid)


def row_group(g9250, n):
    """
    <summary>The group holding one row's four lists inside the grouplist.</summary>
    <param name="g9250">The grouplist element.</param>
    <param name="n">The row, 1 to 3.</param>
    <returns>The group element, or None.</returns>
    </summary>
    """
    mine = {LIB_ID[n], STATIC_ID[n], NARROW_LIB[n], NARROW_STATIC[n]}
    best = None
    for grp in g9250.iter("control"):
        if grp.get("type") != "group":
            continue
        ids = {c.get("id") for c in grp.iter("control")}
        if mine <= ids and not (ids & (ALL_ROW_IDS - mine)):
            best = grp
    return best


def engage_env(on, **kw):
    """
    <summary>An environment with the Engage Coming Up panel on or off.</summary>
    <param name="on">True when engage_list_shown should hold.</param>
    <param name="kw">Other Env fields (strings and so on).</param>
    <returns>An NEnv.</returns>
    </summary>
    """
    if on:
        kw.setdefault("settings", set())
        kw["settings"] = set(kw["settings"]) | ENGAGE_ON["settings"]
        kw["props"] = dict(kw.get("props") or {}, **ENGAGE_ON["props"])
        return NEnv(addons=ENGAGE_ON["addons"], **kw)
    return NEnv(**kw)


def test_engage_expression():
    """
    <summary>The evaluator reads engage_list_shown: on only with the setting,
    the add-on and a next item together.</summary>
    """
    print("running test_engage_expression")
    check(evaluate("$EXP[engage_list_shown]", engage_env(True)), "engage_list_shown should hold with all three parts")
    check(not evaluate("$EXP[engage_list_shown]", engage_env(False)), "engage_list_shown should be false with nothing set")
    check(not evaluate("$EXP[engage_list_shown]", NEnv(settings={"show_engage_list"}, props={"Engage.Next.1.Label": "x"})),
          "engage_list_shown should need the add-on")


def test_home_wiring():
    """
    <summary>HomeWidgetRows follows HomeMenu on Home; 9250 shows only with
    widgets_on and slides down 70 while corner_bar_top; each row group shows
    only while its string is set; each row has a heading that slides 500 right
    beside Engage, four lists (wide and narrow, library and list) placed and
    shown as the spec says, and an empty message; WidgetItems has twelve slots.</summary>
    """
    print("running test_home_wiring")
    home = parse("Home.xml")
    parent = next((p for p in home.iter() if any(c.tag == "include" and c.get("content") == "HomeWidgetRows" for c in p)), None)
    if check(parent is not None, "Home.xml should include HomeWidgetRows"):
        names = [c.get("content") for c in parent if c.tag == "include"]
        i = names.index("HomeWidgetRows")
        check(i > 0 and names[i - 1] == "HomeMenu", "HomeWidgetRows should follow HomeMenu directly, got %r" % names[max(0, i - 1):i + 1])
    inc = parse("Includes_Home.xml")
    g = controls(inc, "9250")
    if not check(len(g) == 1 and g[0].get("type") == "grouplist", "9250 should be one grouplist"):
        return
    g = g[0]
    check(g.findtext("orientation") in (None, "vertical"), "9250 should be vertical, got %r" % g.findtext("orientation"))
    for strings, want in (({}, False), ({"widget2": "random_movies"}, True), ({"widget3": "list"}, True)):
        check(evaluate(g.findtext("visible"), Env(strings=strings)) == want, "9250 visibility for %r should be %s" % (strings, want))
    slides = [a for a in g.findall("animation") if a.get("effect") == "slide" and "70" in " ".join(a.attrib.values()).replace("condition", "")]
    if check(len(slides) >= 1, "9250 should slide down 70 while corner_bar_top"):
        for pos, want in (("tl", True), ("tc", True), ("tr", True), ("bl", False), ("", False)):
            got = any(evaluate(a.get("condition"), Env(strings={"corner_bar_position": pos})) for a in slides)
            check(got == want, "the 70 slide with corner_bar_position %r should be %s, got %s" % (pos, want, got))
    check(bool(T.STRINGS.get(31921)) and T.STRINGS[31921] == "Nothing here yet", "31921 should be 'Nothing here yet', got %r" % T.STRINGS.get(31921))
    for n in (1, 2, 3):
        grp = row_group(g, n)
        if not check(grp is not None, "row %d should have its own group with all four lists inside 9250" % n):
            continue
        vis = grp.findtext("visible")
        check(vis is not None, "row %d group should have a visible condition" % n)
        for value in ["", "recent_movies", "random_movies", "list"]:
            check(evaluate(vis, Env(strings={"widget%d" % n: value})) == bool(value),
                  "row %d group with widget%d %r should be %s" % (n, n, value, bool(value)))
        check(not evaluate(vis, Env(strings={"widget%d" % (n % 3 + 1): "list"})), "row %d should not show for another row's string" % n)
        heads = [e for e in grp.iter("control") if e.get("type") == "label" and "$VAR[WidgetRowName%d]" % n in ET.tostring(e, encoding="unicode")]
        if check(len(heads) >= 1, "row %d should have a heading from WidgetRowName%d" % (n, n)):
            slid = [a for h in heads for a in h.findall("animation") if a.get("effect") == "slide" and "500" in " ".join(a.attrib.values())]
            check(len(slid) >= 1, "row %d heading should slide 500 while engage_list_shown" % n)
            if slid:
                check(any(evaluate(a.get("condition"), engage_env(True)) for a in slid), "row %d heading should slide with Engage on" % n)
                check(not any(evaluate(a.get("condition"), engage_env(False)) for a in slid), "row %d heading should not slide with Engage off" % n)
        variants = (("wide library", LIB_ID[n], "0", "1460", False, False), ("wide list", STATIC_ID[n], "0", "1460", True, False),
                    ("narrow library", NARROW_LIB[n], "500", "960", False, True), ("narrow list", NARROW_STATIC[n], "500", "960", True, True))
        for label, cid, left, width, is_list, narrow in variants:
            found = controls(grp, cid)
            if not check(len(found) == 1, "row %d %s list %s should exist once" % (n, label, cid)):
                continue
            c = found[0]
            check(c.get("type") in ("list", "panel", "fixedlist"), "%s should be a list" % cid)
            check(c.findtext("orientation") == "horizontal", "%s should be horizontal, got %r" % (cid, c.findtext("orientation")))
            check(c.findtext("left") == left and c.findtext("width") == width,
                  "%s should be left %s width %s, got %r %r" % (cid, left, width, c.findtext("left"), c.findtext("width")))
            if is_list:
                uses = [i for i in c.iter("include") if i.get("content") == "WidgetItems"]
                check(len(uses) == 1 and [(p.get("name"), p.get("value")) for p in uses[0].findall("param")] == [("r", str(n))],
                      "%s should hold WidgetItems with r = %d" % (cid, n))
            else:
                content = c.find("content")
                check(content is not None and (content.text or "").strip() == "$VAR[WidgetRowPath%d]" % n, "%s content should be WidgetRowPath%d" % (cid, n))
                limit = content.get("limit") if content is not None else None
                check(limit == "15" or c.findtext("limit") == "15" or (content is not None and content.findtext("limit") == "15"),
                      "%s should have limit 15" % cid)
            for eng in (False, True):
                for src in SOURCES + ["list", ""]:
                    env = engage_env(eng, strings={"widget%d" % n: src})
                    want = (src == "list") == is_list and src != "" and eng == narrow
                    check(evaluate(c.findtext("visible"), env) == want,
                          "%s with source %r and Engage %s should be visible=%s" % (cid, src, eng, want))
        # The empty message: shown for a shown row with nothing in it, never otherwise.
        notes = [e for e in grp.iter("control") if e.get("type") == "label" and "31921" in (e.findtext("label") or "")]
        if check(len(notes) >= 1, "row %d should carry the 'Nothing here yet' label 31921" % n):
            for eng in (False, True):
                for src, items in (("recent_movies", 0), ("recent_movies", 4), ("list", 0), ("list", 4)):
                    lid = (NARROW_LIB if eng else LIB_ID)[n] if src != "list" else (NARROW_STATIC if eng else STATIC_ID)[n]
                    env = engage_env(eng, strings={"widget%d" % n: src}, counts={lid: items},
                                     props={"Widget.%d.Count" % n: str(items), **({"Engage.Next.1.Label": "x"} if eng else {})},
                                     visible={lid})
                    shown = any(evaluate(e.findtext("visible"), env) for e in notes if e.findtext("visible") is not None)
                    check(shown == (items == 0), "row %d, source %s, %d items, Engage %s: the empty label should be %s" % (n, src, items, eng, items == 0))
    inc2 = parse("Includes.xml")
    items = next((i for i in inc2.iter("include") if i.get("name") == "WidgetItems"), None)
    if check(items is not None, "the WidgetItems include should be defined"):
        slots = [i for i in items.iter("include") if i.get("content") == "WidgetItem"]
        check(len(slots) == 12, "WidgetItems should hold 12 WidgetItem slots, got %d" % len(slots))
        values = {p.get("value") for i in slots for p in i.findall("param")}
        check({str(m) for m in range(1, 13)} <= values, "the 12 slots should be numbered 1 to 12, got %r" % sorted(values))
    one = next((i for i in inc2.iter("include") if i.get("name") == "WidgetItem"), None)
    if check(one is not None, "the WidgetItem include should be defined"):
        text = ET.tostring(one, encoding="unicode")
        for field in ("Label", "Sub", "Thumb"):
            check(re.search(r"Window\(home\)\.Property\(Widget\.[^)]*\.%s\)" % field, text) is not None,
                  "a slot should bind to Widget.N.M.%s" % field)
        check(re.search(r"Skin\.SetString\(widget_command,play:\$PARAM\[\w+\]:\$PARAM\[\w+\]\)", text) is not None,
              "a slot click should send play:N:M")


def test_menu_position_row():
    """
    <summary>The Menu Position setting is disabled while any Home row is on.</summary>
    """
    print("running test_menu_position_row")
    root = parse("SkinSettings.xml")
    rows = [c for c in root.iter("control") if (c.findtext("label") or "").startswith("$LOCALIZE[31257]")]
    if not check(len(rows) == 1, "there should be one Menu Position row (label 31257), got %d" % len(rows)):
        return
    check(rows[0].findtext("enable") == "!$EXP[widgets_on]", "Menu Position enable should be !$EXP[widgets_on], got %r" % rows[0].findtext("enable"))
    check(evaluate(rows[0].findtext("enable"), Env()), "Menu Position should be enabled with every row off")
    check(not evaluate(rows[0].findtext("enable"), Env(strings={"widget2": "list"})), "Menu Position should be disabled with a row on")


# ---- Navigation ----------------------------------------------------------------

def focus_files():
    """
    <summary>The parsed xml files that hold Home's focus lines.</summary>
    <returns>A list of XML roots.</returns>
    </summary>
    """
    return [parse(n) for n in ("Home.xml", "Includes.xml", "Includes_Home.xml")]


def test_row_focus_lines_carry_tests():
    """
    <summary>Every focus line naming a row list, other than a list pointing at
    itself, tests that the list is visible and has items.</summary>
    """
    print("running test_row_focus_lines_carry_tests")
    seen = 0
    for root in focus_files():
        for c in root.iter("control"):
            for tag in ("onup", "ondown", "onleft", "onright", "onback"):
                for e in c.findall(tag):
                    cid = (e.text or "").strip()
                    if cid not in ALL_ROW_IDS or cid == c.get("id"):
                        continue
                    seen += 1
                    cond = e.get("condition") or ""
                    n = row_of(cid)
                    count = "Integer.IsGreater(Container(%s).NumItems,0)" % cid if cid in LIB_IDS \
                        else "Integer.IsGreater(Window(home).Property(Widget.%d.Count),0)" % n
                    check("Control.IsVisible(%s)" % cid in cond, "%s line to %s should test visibility, got %r" % (tag, cid, cond))
                    check(count in cond, "%s line to %s should test for items, got %r" % (tag, cid, cond))
    check(seen > 12, "expected many focus lines naming row lists, saw %d" % seen)


def first_visible(order, visible):
    """
    <summary>The first id of an ordered list that is visible.</summary>
    <param name="order">Ids in priority order.</param>
    <param name="visible">The visible ids.</param>
    <returns>An id, or None.</returns>
    </summary>
    """
    return next((i for i in order if i in visible), None)


def build(states, top, engage, tabs, caps, bars, focus=()):
    """
    <summary>An environment for one arrangement of the Home screen.</summary>
    <param name="states">Three row states: off, lib, lib0, list or list0 (0 means no items).</param>
    <param name="top">True for a corner bar at the top.</param>
    <param name="engage">True with Engage's panel showing.</param>
    <param name="tabs">Visible bottom tab ids.</param>
    <param name="caps">Visible bottom caption ids.</param>
    <param name="bars">Visible corner bar ids.</param>
    <param name="focus">Focused control ids.</param>
    <returns>(env, targets, with_items) where targets maps a row to its visible list id and with_items lists the rows that can take focus.</returns>
    </summary>
    """
    strings = {"corner_bar_position": "tl" if top else "bl", "menu_position": "top"}
    visible = set(tabs) | set(caps) | set(bars)
    counts, props, targets, with_items = {}, {}, {}, []
    for n, st in enumerate(states, 1):
        if st == "off":
            strings["widget%d" % n] = ""
            counts[LIB_ID[n]] = counts[NARROW_LIB[n]] = 5
            props["Widget.%d.Count" % n] = "5"
            continue
        is_list = st.startswith("list")
        strings["widget%d" % n] = "list" if is_list else "recent_movies"
        cid = (NARROW_STATIC if engage else STATIC_ID)[n] if is_list else (NARROW_LIB if engage else LIB_ID)[n]
        full = not st.endswith("0")
        visible.add(cid)
        targets[n] = cid
        if is_list:
            props["Widget.%d.Count" % n] = "4" if full else "0"
        else:
            counts[cid] = 4 if full else 0
        if full:
            with_items.append(n)
    env = engage_env(engage, strings=strings, counts=counts, props=props, visible=visible, focus=set(focus))
    return env, targets, with_items


EXTRAS = [(t, c, b) for t in ((), ("9210", "9212", "9214"), ("9212",), ("9214",))
          for c in ((), tuple(CAPS), ("9303",)) for b in ((), ("9100",), ("9110", "9120"), ("9120", "9100"))]
STATES = ["off", "lib", "lib0", "list", "list0"]


def sweep_cases():
    """
    <summary>The arrangements the navigation test runs: every row state with a rotating spread of the other options,
    and a full spread of the other options for a few representative row states.</summary>
    <returns>A list of (states, top, engage, tabs, caps, bars).</returns>
    </summary>
    """
    cases = []
    idx = 0
    for states in itertools.product(STATES, repeat=3):
        for top in (False, True):
            for engage in (False, True):
                for shift in (0, 29):
                    tabs, caps, bars = EXTRAS[(idx * 7 + shift) % len(EXTRAS)]
                    cases.append((states, top, engage, tabs, caps, bars))
                    idx += 1
    for states in (("lib", "list", "lib"), ("off", "lib0", "list"), ("lib", "off", "off"), ("list0", "off", "lib0")):
        for top in (False, True):
            for engage in (False, True):
                for tabs, caps, bars in EXTRAS:
                    cases.append((states, top, engage, tabs, caps, bars))
    return cases


def test_navigation():
    """
    <summary>The focus order as one chain from the menu down: the menu goes to
    the bar (top) and then the first row with items; a row goes up to the row
    above, the bar when it is at the top, or the menu, and down to the row
    below, a caption, the bar when it is below, a tab or the menu; the bottom
    tabs go up to the last row only while the bar is not below the rows; the
    corner bar and the caption buttons reach the last row; left, right and back
    behave; a row that is empty is never chosen.</summary>
    """
    print("running test_navigation")
    inc = parse("Includes_Home.xml")
    fixed = set(TABS) | set(CAPS) | set(BARS) | ALL_ROW_IDS
    menu_down = [c for c in inc.iter("control") if any((d.text or "").strip() == "9252" for d in c.findall("ondown"))
                 and c.get("id") not in fixed and c.get("id") != "$PARAM[id_bar]"]
    bars_ctrl = [c for i in inc.iter("include") if i.get("name") == "HomeCornerBar" for c in i.iter("control") if c.get("id") == "$PARAM[id_bar]"]
    caps_ctrl = [c for i in inc.iter("include") if i.get("name") == "BgCaption" for c in i.iter("control")
                 if any((e.text or "").strip() in ALL_ROW_IDS for e in c.findall("onup"))]
    tab_ctrls = {t: controls(inc, t) for t in TABS}
    check(len(menu_down) >= 1, "the main menu should go down to the rows")
    check(len(bars_ctrl) == 1, "the corner bar include should have one bar control, got %d" % len(bars_ctrl))
    check(len(caps_ctrl) >= 1, "the caption buttons should go up to the rows")
    for t in TABS:
        check(len(tab_ctrls[t]) >= 1, "bottom tab %s should exist" % t)
    ran = 0
    for states, top, engage, tabs, caps, bars in sweep_cases():
        env, target, rows = build(states, top, engage, tabs, caps, bars)
        where = "states %r top %s engage %s tabs %r captions %r bars %r" % (states, top, engage, tabs, caps, bars)
        vis = env.visible
        bar = first_visible(BARS, vis)
        cap = first_visible(CAPS, vis)
        cap_up = first_visible(CAPS[::-1], vis)
        tab = first_visible(TABS, vis)
        below = (not top) and bool(bar)
        on = any(s != "off" for s in states)
        last = target[rows[-1]] if rows else None
        ran += 1
        if on:
            for m in menu_down:
                got = first_target(m, "ondown", env)
                if top and bar:
                    want = bar
                elif rows:
                    want = target[rows[0]]
                else:
                    want = None
                if want:
                    check(got == want, "menu down should reach %s, got %r, %s" % (want, got, where))
                else:
                    check(got not in ALL_ROW_IDS, "menu down should not reach an empty row, got %r, %s" % (got, where))
            for t in TABS:
                for c in tab_ctrls[t]:
                    got = first_target(c, "onup", env)
                    if rows and not below:
                        check(got == last, "tab %s up should reach row %d (%s), got %r, %s" % (t, rows[-1], last, got, where))
                    elif below:
                        check(got == bar, "tab %s up should reach the bar %s, got %r, %s" % (t, bar, got, where))
                    else:
                        check(got not in ALL_ROW_IDS, "tab %s up should not reach an empty row, got %r, %s" % (t, got, where))
            for b in bars_ctrl:
                up, down = first_target(b, "onup", env), first_target(b, "ondown", env)
                if not top:
                    want = cap_up or last or "9000"
                    check(up == want, "the bar up (bar at the bottom) should be %s, got %r, %s" % (want, up, where))
                else:
                    check(up == "9000", "the bar up (bar at the top) should be 9000, got %r, %s" % (up, where))
                if top and rows:
                    check(down == target[rows[0]], "the bar down (bar at the top) should reach row %d, got %r, %s" % (rows[0], down, where))
                elif tab:
                    check(down == tab or (top and rows), "the bar down should reach tab %s, got %r, %s" % (tab, down, where))
                check(down not in ALL_ROW_IDS or (top and rows), "the bar down should not reach a row here, got %r, %s" % (down, where))
            for fc in CAPS:
                fenv, _t, _r = build(states, top, engage, tabs, caps, bars, focus=(fc,))
                for c in caps_ctrl:
                    got = first_target(c, "onup", fenv)
                    if rows:
                        check(got == last, "caption %s up should reach row %d (%s), got %r, %s" % (fc, rows[-1], last, got, where))
                    else:
                        check(got not in ALL_ROW_IDS, "caption %s up should not reach an empty row, got %r, %s" % (fc, got, where))
            for idx, n in enumerate(rows):
                for c in controls(inc, target[n]):
                    up, down = first_target(c, "onup", env), first_target(c, "ondown", env)
                    if idx:
                        want_up = target[rows[idx - 1]]
                    elif top and bar:
                        want_up = bar
                    else:
                        want_up = "9000"
                    if idx + 1 < len(rows):
                        want_down = target[rows[idx + 1]]
                    elif cap:
                        want_down = cap
                    elif below:
                        want_down = bar
                    elif tab:
                        want_down = tab
                    else:
                        want_down = "9000"
                    check(up == want_up, "row %d up should be %s, got %r, %s" % (n, want_up, up, where))
                    check(down == want_down, "row %d down should be %s, got %r, %s" % (n, want_down, down, where))
                    check(first_target(c, "onback", env) == "9000", "row %d back should be 9000, %s" % (n, where))
                    for tag in ("onleft", "onright"):
                        check(first_target(c, tag, env) == c.get("id"), "row %d %s should stay in the list, %s" % (n, tag, where))
    check(ran > 1000, "the navigation sweep should cover many arrangements, ran %d" % ran)


def test_rows_off_changes_nothing():
    """
    <summary>With widget1 to widget3 empty, no focus line anywhere on Home can
    choose a row list, every line gives the same answer it gives with the new
    row lines taken away, and the corner bar and bottom captions keep their old
    answers.</summary>
    """
    print("running test_rows_off_changes_nothing")
    ctrls = [c for root in focus_files() for c in root.iter("control")]
    check(len(ctrls) > 100, "expected the Home focus lines to be found, got %d controls" % len(ctrls))
    for top in (False, True):
        for engage in (False, True):
            for tabs, caps, bars in EXTRAS[::5]:
                env, _t, _r = build(("off", "off", "off"), top, engage, tabs, caps, bars)
                where = "top %s engage %s tabs %r captions %r bars %r" % (top, engage, tabs, caps, bars)
                for c in ctrls:
                    for tag in ("onup", "ondown", "onleft", "onright", "onback"):
                        lines = c.findall(tag)
                        if not lines:
                            continue
                        got = first_target(c, tag, env)
                        check(got not in ALL_ROW_IDS or got == c.get("id"), "%s of %s should not choose a row list with every row off, got %r, %s" % (tag, c.get("id"), got, where))
                        kept = ET.Element("control")
                        for e in lines:
                            if (e.text or "").strip() not in ALL_ROW_IDS or (e.text or "").strip() == c.get("id"):
                                kept.append(e)
                        base = first_target(kept, tag, env)
                        check(got == base, "%s of %s should answer as it did before the rows, %r against %r, %s" % (tag, c.get("id"), got, base, where))
    # The corner bar up and the caption buttons: nothing new with every row off.
    inc = parse("Includes_Home.xml")
    bar = next(c for i in inc.iter("include") if i.get("name") == "HomeCornerBar" for c in i.iter("control") if c.get("id") == "$PARAM[id_bar]")
    for caps in ((), tuple(CAPS), ("9304",)):
        env, _t, _r = build(("off", "off", "off"), False, False, (), caps, ("9100",))
        check(first_target(bar, "onup", env) == "9000",
              "with every row off and the bar at the bottom, bar up should still be 9000 and not a caption button, got %r with captions %r"
              % (first_target(bar, "onup", env), caps))


# ---- The service ---------------------------------------------------------------

class WRig(W.Rig):
    """<summary>The shared rig, with a select dialog that keeps its heading and preselect.</summary>"""

    def __init__(self):
        """<summary>Install the stubs and an empty record of dialogs.</summary>"""
        self.dialogs = []
        super().__init__()

    def select(self, heading, items, *args, **kw):
        """
        <summary>Answer a select dialog and keep what was asked.</summary>
        <param name="heading">The title.</param>
        <param name="items">The lines offered.</param>
        <returns>The chosen index.</returns>
        """
        self.dialogs.append((heading, list(items), args, kw))
        self.picked_from = list(items)
        return self.pick


def step(helper, rig, seconds=11):
    """
    <summary>Moves the shared clock on and runs one fast ticker pass of update_widgets.</summary>
    <param name="helper">The FunctionalHelper.</param>
    <param name="rig">The rig whose clock moves.</param>
    <param name="seconds">How far to move the clock first.</param>
    """
    rig.clock.now += seconds
    helper.update_widgets()


def widget_sets(rig, n):
    """
    <summary>The builtins that set or reset a row's two strings.</summary>
    <param name="rig">The rig.</param>
    <param name="n">The row.</param>
    <returns>A list of builtin texts.</returns>
    """
    return [b for b in rig.builtins if re.match(r"Skin\.(SetString|Reset)\(widget%d(_list)?[,)]" % n, b)]


def test_service_pick():
    """
    <summary>pick:N offers Off, the seven sources and a List line per named
    list under the heading 31920, preselects the current choice, and Off, a
    source, a list or Cancel set the strings as the spec says.</summary>
    """
    print("running test_service_pick")
    rig = WRig()
    try:
        h = W.helper_with([{"name": "First", "items": [W.item("A", "movie", 1)]},
                           {"name": 'Say "Hi", all', "items": [W.item("B", "movie", 2)]}])
        want_lines = [T.STRINGS[31893]] + [T.STRINGS[s] for s in LABEL_IDS] + \
                     [T.STRINGS[31917] % "First", T.STRINGS[31917] % 'Say "Hi", all']
        for n in (1, 2, 3):
            rig.dialogs.clear()
            rig.builtins.clear()
            rig.pick = -1
            rig.set_skin("widget_command", "pick:%d" % n)
            step(h, rig)
            if not check(len(rig.dialogs) == 1, "pick:%d should open one select dialog, got %d" % (n, len(rig.dialogs))):
                continue
            heading, lines, args, kw = rig.dialogs[0]
            check(heading == T.STRINGS[31920] % n, "pick:%d heading should be %r, got %r" % (n, T.STRINGS[31920] % n, heading))
            check(len(lines) == 10, "pick:%d should offer ten lines, got %d" % (n, len(lines)))
            check([str(x) for x in lines[:8]] == want_lines[:8], "pick:%d should offer Off then the seven sources in order, got %r" % (n, lines[:8]))
            check(all(want in [str(x) for x in lines] or any(want.replace('"', "") == str(x).replace('"', "") for x in lines) for want in want_lines[8:]),
                  "pick:%d should offer a List: line per list, got %r" % (n, lines[8:]))
            check(not widget_sets(rig, n), "a cancelled pick:%d should set nothing, got %r" % (n, widget_sets(rig, n)))
        # Preselect follows the current choice.
        for current, extra, idx in (("", None, 0), ("random_movies", None, 7), ("list", "First", 8), ("list", 'Say "Hi", all', 9)):
            rig.dialogs.clear()
            rig.labels.pop("Skin.String(widget1_list)", None)
            rig.set_skin("widget1", current)
            if extra:
                rig.set_skin("widget1_list", extra.replace('"', ""))
            rig.pick = -1
            rig.set_skin("widget_command", "pick:1")
            step(h, rig)
            got = None
            if rig.dialogs:
                _h, _l, args, kw = rig.dialogs[0]
                got = kw.get("preselect", args[0] if args and isinstance(args[0], int) else None)
            check(got == idx, "with widget1 %r %r the preselect should be %d, got %r" % (current, extra, idx, got))
        # Each choice.
        for n in (1, 2, 3):
            for idx in (0, 1, 4, 7):
                rig.builtins.clear()
                rig.set_skin("widget%d" % n, "random_movies")
                rig.set_skin("widget%d_list" % n, "First")
                rig.pick = idx
                rig.set_skin("widget_command", "pick:%d" % n)
                step(h, rig)
                src = rig.labels.get("Skin.String(widget%d)" % n, "")
                lst = rig.labels.get("Skin.String(widget%d_list)" % n, "")
                if idx == 0:
                    check(src == "" and lst == "", "Off should reset widget%d and its list, got %r %r" % (n, src, lst))
                else:
                    check(src == SOURCES[idx - 1] and lst == "", "choice %d should set widget%d to %s and reset the list, got %r %r" % (idx, n, SOURCES[idx - 1], src, lst))
            rig.builtins.clear()
            rig.set_skin("widget%d" % n, "")
            rig.pick = 9
            rig.set_skin("widget_command", "pick:%d" % n)
            step(h, rig)
            check(rig.labels.get("Skin.String(widget%d)" % n) == "list", "choosing a list should set widget%d to list" % n)
            check('Skin.SetString(widget%d_list,"Say Hi, all")' % n in rig.builtins,
                  "the list should be set through the quoted setter with double quotes dropped, got %r" % rig.builtins)
        # A bad row number or word does nothing.
        for bad in ("pick:0", "pick:4", "pick:x", "pick:"):
            rig.dialogs.clear()
            rig.builtins.clear()
            rig.set_skin("widget_command", bad)
            step(h, rig)
            check(not rig.dialogs and not [b for b in rig.builtins if "widget" in b and "widget_command" not in b], "%s should do nothing" % bad)
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the pick path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_publish():
    """
    <summary>A row on a list publishes its video items, at most twelve in list
    order, with label, sub, thumb and count; unused slots are cleared; a
    non list row clears its count; names compare with double quotes dropped;
    a changed list shows after ten seconds.</summary>
    """
    print("running test_service_publish")
    rig = WRig()
    try:
        big = [W.item("Film %02d" % n, "movie", 100 + n) for n in range(1, 16)]
        big.insert(2, W.item("Some Song", "song", 0, "/music/a.flac", kind="music"))
        h = W.helper_with([{"name": "Big", "items": big},
                           {"name": 'Quote "d"', "items": [W.item("Q1", "movie", 1), W.item("Q2", "episode", 2, show="S", season="1", episode="2")]},
                           {"name": "Other", "items": [W.item("Not Me", "movie", 3)]}])
        rig.set_skin("widget1", "list")
        rig.set_skin("widget1_list", "Big")
        rig.set_skin("widget2", "list")
        rig.set_skin("widget2_list", "Quote d")
        rig.set_skin("widget3", "random_movies")
        T.PROPS["Widget.3.Count"] = "7"
        step(h, rig)
        videos = [it for it in h._lists[0]["items"] if it["kind"] == "video"][:12]
        check(T.PROPS.get("Widget.1.Count") == "12", "row 1 count should be 12, got %r" % T.PROPS.get("Widget.1.Count"))
        for m, it in enumerate(videos, 1):
            check(T.PROPS.get("Widget.1.%d.Label" % m) == it["label"], "row 1 slot %d label, got %r" % (m, T.PROPS.get("Widget.1.%d.Label" % m)))
            check(T.PROPS.get("Widget.1.%d.Sub" % m) == h._list_item_sub(it), "row 1 slot %d sub, got %r" % (m, T.PROPS.get("Widget.1.%d.Sub" % m)))
            check(T.PROPS.get("Widget.1.%d.Thumb" % m) == it["thumb"], "row 1 slot %d thumb, got %r" % (m, T.PROPS.get("Widget.1.%d.Thumb" % m)))
        check(not T.PROPS.get("Widget.1.13.Label"), "there should be no thirteenth slot")
        check("Some Song" not in [T.PROPS.get("Widget.1.%d.Label" % m) for m in range(1, 13)], "a music item should not be published")
        check(T.PROPS.get("Widget.2.Count") == "2" and T.PROPS.get("Widget.2.1.Label") == "Q1" and T.PROPS.get("Widget.2.2.Label") == "Q2",
              "row 2 should show its list with double quotes dropped from the name, got %r" % T.PROPS.get("Widget.2.Count"))
        check(not T.PROPS.get("Widget.2.3.Label"), "row 2 should not show items of another list")
        check(not T.PROPS.get("Widget.3.Count"), "a library row should clear its count, got %r" % T.PROPS.get("Widget.3.Count"))
        # A shorter list: unused slots clear.
        del h._lists[0]["items"][2:]
        step(h, rig)
        check(T.PROPS.get("Widget.1.Count") == "2", "after shrinking the count should be 2, got %r" % T.PROPS.get("Widget.1.Count"))
        for m in range(3, 13):
            for field in ("Label", "Sub", "Thumb"):
                check(not T.PROPS.get("Widget.1.%d.%s" % (m, field)), "row 1 slot %d %s should be cleared" % (m, field))
        # An item added is seen within ten seconds.
        h._lists[0]["items"].append(dict(h._lists[0]["items"][0], label="Brand New", dbid=555))
        step(h, rig)
        check(T.PROPS.get("Widget.1.3.Label") == "Brand New" and T.PROPS.get("Widget.1.Count") == "3", "an added item should show after ten seconds")
        # The row switched to a library source clears its count.
        rig.set_skin("widget1", "recent_movies")
        step(h, rig)
        check(not T.PROPS.get("Widget.1.Count"), "a row no longer on a list should clear its count, got %r" % T.PROPS.get("Widget.1.Count"))
        # A list that is not there publishes nothing.
        rig.set_skin("widget2_list", "Missing")
        step(h, rig)
        check(not T.PROPS.get("Widget.2.1.Label"), "an unknown list name should publish nothing")
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the publish path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_play():
    """
    <summary>play:N:M plays slot M of row N with resume by library id or file,
    opens a whole show or season page instead of playing, and an empty slot or
    a bad row does nothing.</summary>
    """
    print("running test_service_play")
    rig = WRig()
    try:
        lists = [{"name": "Weekend", "items": [
            W.item("Library Film", "movie", 7, "/media/films/a.mkv"),
            W.item("Plugin Film", "movie", 0, "plugin://plugin.video.example/play/?id=9"),
            W.item("Library Episode", "episode", 44, "/media/tv/b.mkv", show="Series", season="1", episode="3"),
            W.item("Whole Show", "tvshow", 31, "", count=12),
            W.item("A Season", "season", 55, "", count=8)]},
            {"name": "Midweek", "items": [W.item("Midweek Film", "movie", 8, "/media/films/c.mkv")]}]
        h = W.helper_with(lists)
        rig.set_skin("widget1", "list")
        rig.set_skin("widget1_list", "Weekend")
        rig.set_skin("widget3", "list")
        rig.set_skin("widget3_list", "Midweek")
        step(h, rig)

        def press(text):
            """
            <summary>Send a play command and let the helper handle it.</summary>
            <param name="text">The command text.</param>
            """
            rig.rpc.clear()
            rig.builtins.clear()
            rig.set_skin("widget_command", text)
            step(h, rig)

        for slot, want in ((1, {"movieid": 7}), (2, {"file": "plugin://plugin.video.example/play/?id=9"}), (3, {"episodeid": 44})):
            press("play:1:%d" % slot)
            opened = rig.opened()
            check(len(opened) == 1 and opened[0].get("item") == want and (opened[0].get("options") or {}).get("resume") is True,
                  "play:1:%d should play %r with resume, got %r" % (slot, want, opened))
            check(not rig.windows(), "play:1:%d should not open a window" % slot)
        press("play:3:1")
        opened = rig.opened()
        check(len(opened) == 1 and opened[0].get("item") == {"movieid": 8}, "play:3:1 should play row 3's slot, got %r" % opened)
        press("play:1:4")
        check(not rig.opened() and rig.windows() == ["ActivateWindow(Videos,videodb://tvshows/titles/31/,return)"],
              "a whole show should open its page, got %r %r" % (rig.opened(), rig.windows()))
        press("play:1:5")
        check(not rig.opened() and rig.windows() == ["ActivateWindow(Videos,videodb://tvshows/titles/31/2/,return)"],
              "a season should open its page, got %r %r" % (rig.opened(), rig.windows()))
        for bad in ("play:1:9", "play:1:12", "play:3:2", "play:2:1", "play:4:1", "play:0:1", "play:x:1", "play:1:x", "play:1"):
            press(bad)
            check(not rig.opened() and not rig.windows(), "%s should do nothing, got %r %r" % (bad, rig.opened(), rig.windows()))
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the play path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_list_renamed():
    """
    <summary>Renaming a list carries every widgetN_list that held it, leaves
    the others alone; deleting it resets that row's list and source so the row
    turns off.</summary>
    """
    print("running test_list_renamed")
    rig = WRig()
    try:
        h = W.helper_with([{"name": "Weekend", "items": [W.item("A", "movie", 1)]}])
        for n in (1, 2, 3):
            rig.set_skin("widget%d" % n, "list")
            rig.set_skin("widget%d_list" % n, "Weekend" if n != 2 else "Elsewhere")
        rig.builtins.clear()
        h._list_renamed("Nothing", "Else")
        check(not widget_sets(rig, 1) and not widget_sets(rig, 2) and not widget_sets(rig, 3), "renaming an unused list should change nothing, got %r" % rig.builtins)
        h._list_renamed("Weekend", "Saturday")
        check('Skin.SetString(widget1_list,"Saturday")' in rig.builtins and 'Skin.SetString(widget3_list,"Saturday")' in rig.builtins,
              "rows 1 and 3 should follow the rename, got %r" % rig.builtins)
        check(not widget_sets(rig, 2), "row 2 should be left alone by the rename, got %r" % widget_sets(rig, 2))
        check(rig.labels.get("Skin.String(widget1)") == "list" and rig.labels.get("Skin.String(widget3)") == "list",
              "a rename should leave the rows on")
        # The rig keeps the quotes the setter adds, which Kodi strips; put the plain name back.
        rig.set_skin("widget1_list", "Saturday")
        rig.set_skin("widget3_list", "Saturday")
        h._list_renamed("Saturday", "")
        check(not rig.labels.get("Skin.String(widget1_list)") and not rig.labels.get("Skin.String(widget1)"), "deleting should turn row 1 off")
        check(not rig.labels.get("Skin.String(widget3_list)") and not rig.labels.get("Skin.String(widget3)"), "deleting should turn row 3 off")
        check(rig.labels.get("Skin.String(widget2)") == "list" and rig.labels.get("Skin.String(widget2_list)") == "Elsewhere",
              "deleting should leave row 2, on another list, alone")
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the rename path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    for fn in (test_strings, test_settings_rows, test_help_and_preview, test_expressions, test_variables,
               test_playlists, test_engage_expression, test_home_wiring, test_menu_position_row,
               test_row_focus_lines_carry_tests, test_navigation, test_rows_off_changes_nothing, test_service_pick, test_service_publish,
               test_service_play, test_list_renamed):
        try:
            fn()
        except Exception as exc:  # a crash is a finding, reported rather than hidden
            fail("%s raised %s: %s" % (fn.__name__, type(exc).__name__, exc))
    passed = sum(1 for ok, _ in CHECKS if ok)
    print("test_home_widgets: %d of %d checks passed" % (passed, len(CHECKS)))
    if FAILURES:
        print("test_home_widgets: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_home_widgets: all checks passed")


if __name__ == "__main__":
    main()
