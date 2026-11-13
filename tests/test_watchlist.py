#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 22, the Watchlist tab in the Continue Watching pop up,
written from the spec: the watchlist_url function, the settings rows and their
help, preview and strings, the Home expressions and the off state they give,
the tab positions for every combination of shown tabs, the tab clicks, the
third page of the pop up, and the helper's own paths from the settings to the
Home properties, the pick command and the play command.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py. XML conditions are evaluated by a small reader of
Kodi's boolean grammar (a bang for not, a plus for and, a bar for or, square
brackets to group), so a tab's left edge is the sum of the slide animations
whose condition is true. How the tab looks on a TV is the live check's job.
Exits non zero when a check fails.

Usage:
    python3 tests/test_watchlist.py
</remarks>
"""

import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
STRINGS = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
FAILURES = []
CHECKS = []


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


def read(path):
    """
    <summary>Reads a text file.</summary>
    <param name="path">The path.</param>
    <returns>The text.</returns>
    """
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def find_control(root, cid):
    """
    <summary>The control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element or None.</returns>
    """
    return next((c for c in root.iter("control") if c.get("id") == cid), None)


def url_doc(url):
    """
    <summary>The JSON playlist inside a videodb path.</summary>
    <param name="url">A path from videodb_url.</param>
    <returns>(base, playlist document), or (url, None) when there is none.</returns>
    """
    if not url or "?xsp=" not in url:
        return url, None
    base, _sep, query = url.partition("?xsp=")
    return base, json.loads(urllib.parse.unquote(query))


def flat_rules(rules):
    """
    <summary>Every plain rule inside a rule or an and or or group.</summary>
    <param name="rules">A rule or a group.</param>
    <returns>A list of rule dicts that carry a field.</returns>
    """
    if isinstance(rules, list):
        return [r for item in rules for r in flat_rules(item)]
    if "and" in rules:
        return flat_rules(rules["and"])
    if "or" in rules:
        return flat_rules(rules["or"])
    return [rules]


# ---- A reader for Kodi's boolean conditions ----------------------------------

class Env:
    """<summary>The state a skin condition is read against.</summary>"""

    def __init__(self, strings=None, settings=(), counts=None, props=None, focus=(), visible=()):
        """
        <summary>Keep the state.</summary>
        <param name="strings">Skin.String values by name.</param>
        <param name="settings">Names of Skin.HasSetting switches that are on.</param>
        <param name="counts">Container item counts by id.</param>
        <param name="props">Home window properties.</param>
        <param name="focus">Ids of the focused control.</param>
        <param name="visible">Ids of the visible controls.</param>
        """
        self.strings = dict(strings or {})
        self.settings = set(settings)
        self.counts = dict(counts or {})
        self.props = dict(props or {})
        self.focus = set(focus)
        self.visible = set(visible)


EXPRESSIONS = {}
for _name in sorted(os.listdir(XML)):
    if _name.endswith(".xml"):
        for _node in ET.parse(os.path.join(XML, _name)).getroot().iter("expression"):
            EXPRESSIONS[_node.get("name")] = (_node.text or "").strip()


def expand(text, params=None):
    """
    <summary>Replaces every $PARAM and $EXP reference by its bracketed text.</summary>
    <param name="text">A condition.</param>
    <param name="params">Include parameter values by name.</param>
    <returns>The condition with no references left.</returns>
    """
    params = params or {}
    for _ in range(40):
        before = text
        text = re.sub(r"\$PARAM\[(\w+)\]", lambda m: "[" + str(params[m.group(1)]) + "]", text)
        text = re.sub(r"\$EXP\[(\w+)\]", lambda m: "[" + EXPRESSIONS[m.group(1)] + "]", text)
        if text == before:
            return text
    raise ValueError("references did not settle: " + text)


def atom(text, env):
    """
    <summary>Evaluates one plain condition.</summary>
    <param name="text">The condition, with no operators outside brackets.</param>
    <param name="env">The state.</param>
    <returns>True or False.</returns>
    <exception cref="ValueError">When the condition is not one this reader knows.</exception>
    """
    text = text.strip()
    if text in ("true", "false"):
        return text == "true"
    m = re.fullmatch(r"Skin\.HasSetting\((\w+)\)", text)
    if m:
        return m.group(1) in env.settings
    m = re.fullmatch(r"String\.IsEmpty\(Skin\.String\((\w+)\)\)", text)
    if m:
        return not env.strings.get(m.group(1), "")
    m = re.fullmatch(r"String\.IsEqual\(Skin\.String\((\w+)\),(\w+)\)", text)
    if m:
        return env.strings.get(m.group(1), "") == m.group(2)
    m = re.fullmatch(r"Integer\.(IsGreater|IsEqual)\(Container\((\d+)\)\.NumItems,(\d+)\)", text)
    if m:
        have, want = env.counts.get(m.group(2), 0), int(m.group(3))
        return have > want if m.group(1) == "IsGreater" else have == want
    m = re.fullmatch(r"Integer\.(IsGreater|IsEqual)\(Window\(home\)\.Property\(([\w.]+)\),(\d+)\)", text)
    if m:
        raw = env.props.get(m.group(2), "")
        if not raw.lstrip("-").isdigit():
            return False
        have, want = int(raw), int(m.group(3))
        return have > want if m.group(1) == "IsGreater" else have == want
    m = re.fullmatch(r"Control\.HasFocus\((\d+)\)", text)
    if m:
        return m.group(1) in env.focus
    m = re.fullmatch(r"Control\.IsVisible\((\d+)\)", text)
    if m:
        return m.group(1) in env.visible
    raise ValueError("condition not understood: " + text)


def evaluate(text, env, params=None):
    """
    <summary>Evaluates a Kodi condition: bang is not, plus is and, bar is or, brackets group.</summary>
    <param name="text">The condition.</param>
    <param name="env">The state.</param>
    <param name="params">Include parameter values by name.</param>
    <returns>True or False.</returns>
    <remarks>An empty condition is true, as Kodi reads it.</remarks>
    """
    text = expand(text or "", params).strip()
    if not text:
        return True
    pos = [0]

    def peek():
        """<summary>The next character.</summary><returns>A character or ''.</returns>"""
        while pos[0] < len(text) and text[pos[0]] == " ":
            pos[0] += 1
        return text[pos[0]] if pos[0] < len(text) else ""

    def parse_or():
        """<summary>One or group.</summary><returns>Its value.</returns>"""
        value = parse_and()
        while peek() == "|":
            pos[0] += 1
            other = parse_and()
            value = value or other
        return value

    def parse_and():
        """<summary>One and group.</summary><returns>Its value.</returns>"""
        value = parse_not()
        while peek() == "+":
            pos[0] += 1
            other = parse_not()
            value = value and other
        return value

    def parse_not():
        """<summary>One negation, bracket or plain condition.</summary><returns>Its value.</returns>"""
        if peek() == "!":
            pos[0] += 1
            return not parse_not()
        if peek() == "[":
            pos[0] += 1
            value = parse_or()
            if peek() != "]":
                raise ValueError("unbalanced brackets in " + text)
            pos[0] += 1
            return value
        depth, start = 0, pos[0]
        while pos[0] < len(text):
            ch = text[pos[0]]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and ch in "+|]":
                break
            pos[0] += 1
        return atom(text[start:pos[0]], env)

    value = parse_or()
    if pos[0] != len(text):
        raise ValueError("trailing text in condition: " + text)
    return value


# ---- The URL ------------------------------------------------------------------

def test_url():
    """
    <summary>watchlist_url: a videodb path for movies or tvshows, one rule tag
    is the tag, newest added first, limit 12, a different path per tag and per
    kind.</summary>
    """
    print("running test_url")
    for kind, base in (("movies", "videodb://movies/titles/"), ("tvshows", "videodb://tvshows/titles/")):
        got_base, doc = url_doc(service.watchlist_url(kind, "Sci Fi & Fantasy"))
        if not check(doc is not None, "%s: the path should carry an xsp playlist" % kind):
            continue
        check(got_base == base, "%s: the path should start at %s, got %r" % (kind, base, got_base))
        check(doc.get("type") == kind, "%s: the playlist type should be the kind, got %r" % (kind, doc.get("type")))
        rules = flat_rules(doc["rules"])
        check(len(rules) == 1, "%s: there should be exactly one rule, got %r" % (kind, rules))
        rule = rules[0]
        value = rule.get("value")
        value = value if isinstance(value, list) else [value]
        check(rule.get("field") == "tag" and rule.get("operator") == "is" and value == ["Sci Fi & Fantasy"],
              "%s: the rule should be tag is the tag, got %r" % (kind, rule))
        check(doc.get("order") == {"method": "dateadded", "direction": "descending"},
              "%s: newest added first, got %r" % (kind, doc.get("order")))
        check(doc.get("limit") == 12, "%s: the limit should be 12, got %r" % (kind, doc.get("limit")))
    check(service.watchlist_url("movies", "a") != service.watchlist_url("movies", "b"),
          "different tags should give different paths so the row reloads")
    check(service.watchlist_url("movies", "a") == service.watchlist_url("movies", "a"),
          "the same tag should give the same path so the row is left alone")
    check(service.watchlist_url("movies", "a") != service.watchlist_url("tvshows", "a"),
          "the two kinds should not share a path")


# ---- Settings, strings and help -----------------------------------------------

def test_strings():
    """
    <summary>Strings 31891 to 31905 exist once each and are not empty, and the
    three help strings carry a Where: line.</summary>
    """
    print("running test_strings")
    po = read(STRINGS)
    for sid in range(31891, 31906):
        check(bool(T.STRINGS.get(sid)), "string %d is missing or empty" % sid)
        check(po.count('msgctxt "#%d"' % sid) == 1, "string %d should be defined exactly once" % sid)
    for sid in (31896, 31898, 31901):
        check("Where:" in T.STRINGS.get(sid, ""), "the help string %d should carry a Where: line" % sid)
    check(T.STRINGS.get(31899) == "Watch later", "string 31899 should be Watch later, got %r" % T.STRINGS.get(31899))


def test_settings_rows():
    """
    <summary>Rows 7183 to 7185: labels, enable conditions, what OK runs, the
    Off, Tag, List, Off cycle on the source, and no default switched on.</summary>
    """
    print("running test_settings_rows")
    root = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    rows = {cid: find_control(root, cid) for cid in ("7183", "7184", "7185")}
    for cid, row in rows.items():
        check(row is not None and row.get("type") == "button", "row %s should be a button" % cid)
    if any(r is None for r in rows.values()):
        return
    check(rows["7183"].findtext("label") == "$LOCALIZE[31892] $VAR[WatchlistSourceLabel]",
          "7183 label, got %r" % rows["7183"].findtext("label"))
    check(rows["7184"].findtext("label") == "$LOCALIZE[31897] $VAR[WatchlistTagLabel]",
          "7184 label, got %r" % rows["7184"].findtext("label"))
    check(rows["7185"].findtext("label") == "$LOCALIZE[31900] $VAR[WatchlistListLabel]",
          "7185 label, got %r" % rows["7185"].findtext("label"))
    check(rows["7184"].findtext("onclick") == "Skin.SetString(watchlist_tag)", "7184 should open the keyboard on watchlist_tag")
    check(rows["7185"].findtext("onclick") == "Skin.SetString(watchlist_command,pick)", "7185 should send pick")
    # The cycle: every onclick condition is read before any runs.
    state = ""
    seen = []
    for _step in range(4):
        env = Env(strings={"watchlist_source": state})
        todo = [o.text for o in rows["7183"].findall("onclick") if evaluate(o.get("condition"), env)]
        for action in todo:
            m = re.fullmatch(r"Skin\.SetString\(watchlist_source,(\w+)\)", action)
            if m:
                state = m.group(1)
            elif action == "Skin.Reset(watchlist_source)":
                state = ""
        seen.append(state)
    check(seen == ["tag", "list", "", "tag"], "OK should cycle empty, tag, list, empty, got %r" % seen)
    # Enable conditions.
    for source, want in (("", (True, False, False)), ("tag", (True, True, False)), ("list", (True, False, True))):
        for cid, expected in zip(("7183", "7184", "7185"), want):
            got = evaluate(rows[cid].findtext("enable"), Env(strings={"watchlist_source": source}))
            check(got == expected, "row %s enabled with source %r should be %s, got %s" % (cid, source, expected, got))
    check(not evaluate(rows["7183"].findtext("enable"), Env(strings={"watchlist_source": "tag"}, settings={"hide_continue"})),
          "7183 should be disabled while Continue Watching is hidden")
    # Off by default: nothing sets the source except the row itself.
    for name in os.listdir(XML):
        if name.endswith(".xml") and name != "SkinSettings.xml":
            check("SetString(watchlist_source" not in read(os.path.join(XML, name)),
                  "%s should not switch the Watchlist on" % name)
    check("watchlist_source" not in read(os.path.join(SKIN, "addon.xml")), "addon.xml should not name the source")


def test_help_and_preview():
    """
    <summary>The three help strings are mapped and listed, 7183 previews as
    the stage and in stage_region_tabs, and 7184 and 7185 preview as none.</summary>
    """
    print("running test_help_and_preview")
    help_text = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    for cid, sid in (("7183", "31896"), ("7184", "31898"), ("7185", "31901")):
        check('<value condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (cid, sid) in help_text,
              "the help map should give %s string %s" % (cid, sid))
        check(evaluate(EXPRESSIONS["settings_help_shown"], Env(focus={cid})), "%s should be in settings_help_shown" % cid)
    check(evaluate(EXPRESSIONS["settings_preview_shown"], Env(focus={"7183"})), "7183 should be in settings_preview_shown")
    check(evaluate(EXPRESSIONS["stage_region_tabs"], Env(focus={"7183"})), "7183 should be in stage_region_tabs")
    check(not evaluate(EXPRESSIONS["settings_preview_none"], Env(focus={"7183"})), "7183 should not be in settings_preview_none")
    for cid in ("7184", "7185"):
        check(evaluate(EXPRESSIONS["settings_preview_none"], Env(focus={cid})), "%s should be in settings_preview_none" % cid)
        for name in ("settings_preview_shown", "stage_region_tabs"):
            check(not evaluate(EXPRESSIONS[name], Env(focus={cid})), "%s should not be in %s" % (cid, name))


# ---- Home expressions and the off state ---------------------------------------

def test_expressions_off_and_on():
    """
    <summary>watch_on, watch_page and watch_tab_shown are all false while the
    source is empty, however full the rows and the count look, and follow the
    source when it is set; panel_tall is false on the Watchlist page.</summary>
    """
    print("running test_expressions_off_and_on")
    full = {"counts": {"9231": 3, "9233": 2}, "props": {"Watchlist.Count": "5"}}
    for panel in ("", "watch", "recent"):
        env = Env(strings={"watchlist_source": "", "home_panel": panel}, **full)
        for name in ("watch_on", "watch_page", "watch_tab_shown"):
            check(not evaluate("$EXP[%s]" % name, env), "%s should be false with the source empty, home_panel %r" % (name, panel))
    on_tag = Env(strings={"watchlist_source": "tag", "home_panel": "watch"}, **full)
    check(evaluate("$EXP[watch_on]", on_tag), "watch_on should be true for the tag source")
    check(evaluate("$EXP[watch_page]", on_tag), "watch_page should be true for source tag and home_panel watch")
    check(evaluate("$EXP[watch_tab_shown]", on_tag), "the tab should show for a tag with rows")
    check(not evaluate("$EXP[watch_page]", Env(strings={"watchlist_source": "tag", "home_panel": ""})),
          "watch_page should be false when the pop up is on another page")
    on_list = Env(strings={"watchlist_source": "list", "home_panel": "watch"}, **full)
    check(evaluate("$EXP[watch_tab_shown]", on_list), "the tab should show for a list with a count")
    check(not evaluate("$EXP[watch_tab_shown]", Env(strings={"watchlist_source": "list"}, props={"Watchlist.Count": "0"})),
          "the tab should not show for an empty list")
    check(not evaluate("$EXP[watch_tab_shown]", Env(strings={"watchlist_source": "tag"}, settings={"hide_continue"}, **full)),
          "the tab should not show while Continue Watching is hidden")
    check(not evaluate("$EXP[panel_tall]", Env(strings={"watchlist_source": "tag", "home_panel": "watch"})),
          "panel_tall should be false on the Watchlist page")
    check(evaluate("$EXP[panel_tall]", Env(strings={"watchlist_source": "", "home_panel": "watch"})),
          "panel_tall should be unchanged (true) with the Watchlist off")


# ---- Tab positions --------------------------------------------------------------

def tabs_include():
    """
    <summary>The HomeContinueTabs include.</summary>
    <returns>The include element.</returns>
    """
    root = ET.parse(os.path.join(XML, "Includes_Home.xml")).getroot()
    return next(i for i in root.iter("include") if i.get("name") == "HomeContinueTabs")


def tab_left(tab, params, env):
    """
    <summary>A tab's left edge: its left plus every Conditional slide that applies.</summary>
    <param name="tab">The control element.</param>
    <param name="params">The include parameters.</param>
    <param name="env">The state.</param>
    <returns>The left edge in pixels.</returns>
    """
    left = int(tab.findtext("left"))
    for anim in tab.findall("animation"):
        if anim.text == "Conditional" and anim.get("effect") == "slide":
            if evaluate(anim.get("condition"), env, params):
                left += int(anim.get("end").split(",")[0])
    return left


def test_tab_positions():
    """
    <summary>With each of the seven combinations of shown tabs the left edges
    are 490, 810, 1130 for three, 650 and 970 for two and 810 for one, on both
    edges, and with the Watchlist off nothing moves from where it was.</summary>
    """
    print("running test_tab_positions")
    inc = tabs_include()
    ids = {"bottom": ("9210", "9212", "9214"), "top": ("9211", "9213", "9215")}
    for edge, trio in ids.items():
        tabs = [find_control(inc, i) for i in trio]
        if not check(all(t is not None for t in tabs), "the %s edge should have the three tabs %r" % (edge, trio)):
            continue
        for c in (True, False):
            for r in (True, False):
                for w in (True, False):
                    shown = [c, r, w]
                    if not any(shown):
                        continue
                    params = {"shown_continue": str(c).lower(), "shown_recent": str(r).lower(),
                              "shown_watch": str(w).lower(), "recent_gate": "true",
                              "flip_continue": "false", "flip_recent": "false"}
                    count = sum(shown)
                    want = [810 - 160 * (count - 1) + 320 * i for i in range(count)]
                    got = [tab_left(t, params, Env()) for t, s in zip(tabs, shown) if s]
                    check(got == want, "%s edge, continue %s recent %s watch %s: lefts should be %r, got %r"
                          % (edge, c, r, w, want, got))
    # The three at once, by name.
    params = {"shown_continue": "true", "shown_recent": "true", "shown_watch": "true", "recent_gate": "true",
              "flip_continue": "false", "flip_recent": "false"}
    got = [tab_left(find_control(inc, i), params, Env()) for i in ("9210", "9212", "9214")]
    check(got == [490, 810, 1130], "Continue, Recently Added, Watchlist should sit at 490, 810, 1130, got %r" % got)
    # The existing four tabs gain a slide conditioned on shown_watch only.
    for tid in ("9210", "9211", "9212", "9213"):
        tab = find_control(inc, tid)
        extra = [a for a in tab.findall("animation")
                 if a.get("effect") == "slide" and a.get("end") == "-160,0" and a.get("condition") == "$PARAM[shown_watch]"]
        check(len(extra) == 1, "tab %s should gain one slide of -160 conditioned on shown_watch only" % tid)
    # Off: the default parameter reads false, so the old two tabs sit where they were.
    off = Env(strings={"watchlist_source": ""}, counts={"9231": 3}, props={"Watchlist.Count": "4"})
    defaults = {p.get("name"): p.get("default") for p in inc.findall("param")}
    check(defaults.get("shown_watch") == "$EXP[watch_tab_shown]", "shown_watch should default to $EXP[watch_tab_shown]")
    params = dict(defaults, shown_continue="true", shown_recent="true")
    got = [tab_left(find_control(inc, i), params, off) for i in ("9210", "9212")]
    check(got == [650, 970], "with the Watchlist off the two old tabs should stay at 650 and 970, got %r" % got)
    params = dict(defaults, shown_continue="true", shown_recent="false")
    check(tab_left(find_control(inc, "9210"), params, off) == 810, "with the Watchlist off Continue alone should stay at 810")
    for tid in ("9214", "9215"):
        vis = find_control(inc, tid).findtext("visible")
        check(not evaluate(vis, off, dict(defaults, shown_continue="true", shown_recent="true", continue_tab_top="false")),
              "tab %s should not be visible with the Watchlist off" % tid)
        check(find_control(inc, tid).findtext("label") == "31891", "tab %s should be labelled 31891" % tid)


def test_tab_visibility_on():
    """
    <summary>With a tag source and rows, the bottom tab shows on the bottom
    edge and the top tab on the top edge, never both.</summary>
    """
    print("running test_tab_visibility_on")
    inc = tabs_include()
    defaults = {p.get("name"): p.get("default") for p in inc.findall("param")}
    for top, shown_id, hidden_id in (("", "9214", "9215"), ("top", "9215", "9214")):
        env = Env(strings={"watchlist_source": "tag", "continue_tab": top}, counts={"9231": 2})
        check(evaluate(find_control(inc, shown_id).findtext("visible"), env, defaults),
              "tab %s should show on the %s edge" % (shown_id, top or "bottom"))
        check(not evaluate(find_control(inc, hidden_id).findtext("visible"), env, defaults),
              "tab %s should not show on the %s edge" % (hidden_id, top or "bottom"))


def tab_click(tab, env):
    """
    <summary>The actions a click on a tab runs: every condition read first.</summary>
    <param name="tab">The control element.</param>
    <param name="env">The state before the click.</param>
    <returns>The action texts in order.</returns>
    """
    return [o.text for o in tab.findall("onclick") if evaluate(o.get("condition"), env)]


def test_tab_clicks():
    """
    <summary>The Watchlist tab opens the pop up on its page or closes it when
    already there, focusing 9231 or 9233 for a tag and 9235 for a list only;
    the Continue tab switches from the Watchlist page rather than closing.</summary>
    """
    print("running test_tab_clicks")
    inc = tabs_include()
    for tid in ("9214", "9215"):
        tab = find_control(inc, tid)
        closed_tag = Env(strings={"watchlist_source": "tag"}, counts={"9231": 3, "9233": 2})
        got = tab_click(tab, closed_tag)
        check("Skin.SetBool(continue_open)" in got and "Skin.SetString(home_panel,watch)" in got and "SetFocus(9231)" in got
              and "SetFocus(9235)" not in got and "Skin.Reset(continue_open)" not in got,
              "%s closed, tag: should open on the watch page and focus 9231, got %r" % (tid, got))
        got = tab_click(tab, Env(strings={"watchlist_source": "tag"}, counts={"9231": 0, "9233": 2}))
        check("SetFocus(9233)" in got and "SetFocus(9231)" not in got, "%s tag with no films should focus 9233, got %r" % (tid, got))
        got = tab_click(tab, Env(strings={"watchlist_source": "list"}, counts={"9231": 3}))
        check("SetFocus(9235)" in got and "SetFocus(9231)" not in got and "SetFocus(9233)" not in got,
              "%s list should focus 9235 only, got %r" % (tid, got))
        got = tab_click(tab, Env(strings={"watchlist_source": "tag", "home_panel": "watch"}, settings={"continue_open"},
                                 counts={"9231": 3}))
        check("Skin.Reset(continue_open)" in got and not any(a.startswith("SetFocus") for a in got),
              "%s open on the Watchlist page should close it, got %r" % (tid, got))
        got = tab_click(tab, Env(strings={"watchlist_source": "tag", "home_panel": ""}, settings={"continue_open"},
                                 counts={"9231": 3}))
        check("Skin.Reset(continue_open)" not in got and "Skin.SetString(home_panel,watch)" in got and "SetFocus(9231)" in got,
              "%s open on another page should switch to the Watchlist page, got %r" % (tid, got))
    for tid in ("9210", "9211"):
        tab = find_control(inc, tid)
        got = tab_click(tab, Env(strings={"watchlist_source": "tag", "home_panel": "watch"}, settings={"continue_open"},
                                 counts={"9201": 2}))
        check("Skin.Reset(continue_open)" not in got and "Skin.Reset(home_panel)" in got and "SetFocus(9201)" in got,
              "%s clicked on the Watchlist page should switch to Continue, got %r" % (tid, got))
        got = tab_click(tab, Env(strings={"home_panel": ""}, settings={"continue_open"}, counts={"9201": 2}))
        check("Skin.Reset(continue_open)" in got, "%s clicked on the Continue page should still close, got %r" % (tid, got))


# ---- Page 3 of the pop up ------------------------------------------------------

def test_page_three():
    """
    <summary>Rows 9231 and 9233 read the two path properties and show only for
    the tag source; row 9235 holds WatchlistItems and shows only for the list
    source; the twelve slots bind to Watchlist.N.* and send play:N; the page
    itself is off screen unless watch_page.</summary>
    """
    print("running test_page_three")
    home = ET.parse(os.path.join(XML, "Home.xml")).getroot()
    for cid, prop in (("9231", "watchlist_movies_path"), ("9233", "watchlist_tvshows_path")):
        ctl = find_control(home, cid)
        if not check(ctl is not None, "row %s is missing from Home.xml" % cid):
            continue
        content = ctl.find("content")
        check(content is not None and (content.text or "").strip() == "$INFO[Window(home).Property(%s)]" % prop,
              "row %s should read %s" % (cid, prop))
        vis = ctl.findtext("visible")
        for source, want in (("tag", True), ("list", False), ("", False)):
            check(evaluate(vis, Env(strings={"watchlist_source": source})) == want,
                  "row %s visible with source %r should be %s" % (cid, source, want))
    row = find_control(home, "9235")
    if check(row is not None, "row 9235 is missing from Home.xml"):
        check(row.find("content") is not None and any(i.get("content") == "WatchlistItems" for i in row.iter("include")),
              "row 9235 should hold the WatchlistItems include")
        for source, want in (("list", True), ("tag", False), ("", False)):
            check(evaluate(row.findtext("visible"), Env(strings={"watchlist_source": source})) == want,
                  "row 9235 visible with source %r should be %s" % (source, want))
    inc = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
    items = next((i for i in inc.iter("include") if i.get("name") == "WatchlistItems"), None)
    if check(items is not None, "the WatchlistItems include is missing"):
        slots = [next(p.get("value") for p in i.findall("param") if p.get("name") == "n")
                 for i in items.iter("include") if i.get("content") == "WatchlistItem"]
        check(slots == [str(n) for n in range(1, 13)], "WatchlistItems should hold slots 1 to 12, got %r" % slots)
    one = next((i for i in inc.iter("include") if i.get("name") == "WatchlistItem"), None)
    if check(one is not None, "the WatchlistItem include is missing"):
        text = ET.tostring(one, encoding="unicode")
        for field in ("Label", "Sub", "Thumb"):
            check("Window(home).Property(Watchlist.$PARAM[n].%s)" % field in text, "a slot should bind to Watchlist.N.%s" % field)
        check("Skin.SetString(watchlist_command,play:$PARAM[n])" in text, "a slot click should send play:N")
    page = None
    for grp in home.iter("control"):
        if grp.get("type") == "group" and any(c.get("id") == "9231" for c in grp.iter("control")) \
                and not any(c.get("id") == "9201" for c in grp.iter("control")) and grp.find("animation") is not None:
            page = grp
    if check(page is not None, "the Watchlist page group was not found"):
        slide = next((a for a in page.findall("animation") if a.get("effect") == "slide"), None)
        check(slide is not None and evaluate(slide.get("condition"), Env(strings={"watchlist_source": ""})),
              "with the Watchlist off the page should be slid out of sight")
        check(slide is not None and not evaluate(slide.get("condition"), Env(strings={"watchlist_source": "tag", "home_panel": "watch"})),
              "on the Watchlist page it should not be slid away")


def test_stage_and_home_params():
    """
    <summary>The settings stage passes shown_watch as !Skin.HasSetting
    (hide_continue) + $EXP[watch_on] and Home passes nothing, so Home uses the
    default.</summary>
    """
    print("running test_stage_and_home_params")
    inc = ET.parse(os.path.join(XML, "Includes_Home.xml")).getroot()
    stage = [i for i in inc.iter("include") if i.get("content") == "HomeContinueTabs"]
    values = [p.get("value") for i in stage for p in i.findall("param") if p.get("name") == "shown_watch"]
    check(values == ["!Skin.HasSetting(hide_continue) + $EXP[watch_on]"], "the stage should pass shown_watch, got %r" % values)
    home = ET.parse(os.path.join(XML, "Home.xml")).getroot()
    uses = [i for i in home.iter("include") if i.get("content") == "HomeContinueTabs"]
    check(len(uses) == 1 and not uses[0].findall("param"), "Home should use the include with no parameters")
    off = Env(strings={"watchlist_source": ""})
    check(not evaluate(values[0], off), "the stage should show no Watchlist tab with the source empty")
    check(evaluate(values[0], Env(strings={"watchlist_source": "list"})), "the stage should show the tab with a source on")
    check(not evaluate(values[0], Env(strings={"watchlist_source": "list"}, settings={"hide_continue"})),
          "the stage should not show the tab while Continue Watching is hidden")


# ---- The service ---------------------------------------------------------------

class Clock:
    """<summary>A clock the test moves by hand.</summary>"""

    def __init__(self):
        """<summary>Start well after zero.</summary>"""
        self.now = 10000.0

    def __call__(self):
        """<summary>The time now.</summary><returns>Seconds.</returns>"""
        return self.now


CLOCK = Clock()


class Rig:
    """<summary>The stubs around one helper: labels, builtins, library calls, toasts and the pick answer.</summary>"""

    def __init__(self):
        """<summary>Install the stubs, keeping what they replace.</summary>"""
        self.labels = {}
        self.builtins = []
        self.rpc = []
        self.pick = 0
        self.picked_from = None
        self.clock = CLOCK
        self.saved = (service._jsonrpc, service.threading.Thread, service.xbmc.getInfoLabel,
                      service.xbmc.getCondVisibility, service.xbmc.executebuiltin,
                      getattr(T._Dialog, "select", None), service.time.monotonic, service.time.time)
        T.PROPS.clear()
        T.SKIN_SETTINGS.clear()
        T._Dialog.toasts = []
        service._jsonrpc = self.jsonrpc
        service.threading.Thread = Quick
        service.xbmc.getInfoLabel = lambda label: self.labels.get(label, "")
        service.xbmc.getCondVisibility = self.cond
        service.xbmc.executebuiltin = self.builtin
        T._Dialog.select = self.select
        service.time.monotonic = self.clock
        service.time.time = self.clock

    def restore(self):
        """<summary>Put every stub back.</summary>"""
        (service._jsonrpc, service.threading.Thread, service.xbmc.getInfoLabel, service.xbmc.getCondVisibility,
         service.xbmc.executebuiltin, old_select, service.time.monotonic, service.time.time) = self.saved
        if old_select is None:
            del T._Dialog.select
        else:
            T._Dialog.select = old_select
        T.PROPS.clear()
        T.SKIN_SETTINGS.clear()

    def set_skin(self, name, value):
        """
        <summary>Set a Skin.String.</summary>
        <param name="name">The string's name.</param>
        <param name="value">Its value.</param>
        """
        self.labels["Skin.String(%s)" % name] = value

    def cond(self, text):
        """
        <summary>getCondVisibility for what the helper may ask.</summary>
        <param name="text">The condition.</param>
        <returns>True for the Home window, a switch that is on, or a string that matches.</returns>
        """
        if text == "Window.IsActive(home)":
            return True
        m = re.fullmatch(r"Skin\.HasSetting\((\w+)\)", text)
        if m:
            return m.group(1) in T.SKIN_SETTINGS
        m = re.fullmatch(r"String\.IsEqual\(Skin\.String\((\w+)\),(\w+)\)", text)
        if m:
            return self.labels.get("Skin.String(%s)" % m.group(1), "") == m.group(2)
        m = re.fullmatch(r"String\.IsEmpty\(Skin\.String\((\w+)\)\)", text)
        if m:
            return not self.labels.get("Skin.String(%s)" % m.group(1), "")
        return False

    def builtin(self, cmd, *_a):
        """
        <summary>Record a builtin and let Skin.SetString and Skin.Reset land in the labels.</summary>
        <param name="cmd">The builtin.</param>
        """
        self.builtins.append(cmd)
        m = re.fullmatch(r"Skin\.SetString\((\w+),(.*)\)", cmd, re.S)
        if m:
            self.labels["Skin.String(%s)" % m.group(1)] = m.group(2).replace("\\,", ",")
        m = re.fullmatch(r"Skin\.Reset\((\w+)\)", cmd)
        if m:
            self.labels.pop("Skin.String(%s)" % m.group(1), None)

    def select(self, heading, items, *_a, **_kw):
        """
        <summary>Answer a select dialog with the chosen index, recording what was offered.</summary>
        <param name="heading">The dialog's title.</param>
        <param name="items">The lines offered.</param>
        <returns>The chosen index.</returns>
        """
        self.picked_from = list(items)
        return self.pick

    def jsonrpc(self, method, params=None):
        """
        <summary>Answer a library call, recording it.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        self.rpc.append((method, params or {}))
        if method == "VideoLibrary.GetSeasonDetails":
            return {"result": {"seasondetails": {"tvshowid": 31, "season": 2}}}
        return {"result": "OK"}

    def opened(self):
        """
        <summary>The Player.Open calls so far.</summary>
        <returns>A list of parameter dicts.</returns>
        """
        return [p for m, p in self.rpc if m == "Player.Open"]

    def windows(self):
        """
        <summary>The ActivateWindow builtins so far.</summary>
        <returns>A list of builtin texts.</returns>
        """
        return [b for b in self.builtins if b.startswith("ActivateWindow(")]


class Quick:
    """<summary>A thread that runs its target as soon as it is started.</summary>"""

    def __init__(self, target=None, args=(), **_kw):
        """<summary>Keep the target.</summary><param name="target">What to run.</param><param name="args">Its arguments.</param>"""
        self.target, self.args = target, args

    def start(self):
        """<summary>Run the target now.</summary>"""
        self.target(*self.args)

    def is_alive(self):
        """<summary>Never still running.</summary><returns>False.</returns>"""
        return False

    def join(self, *_a, **_kw):
        """<summary>Nothing to wait for.</summary>"""


def step(helper, rig, seconds=11):
    """
    <summary>Moves the shared clock on and runs one fast ticker pass.</summary>
    <param name="helper">The FunctionalHelper.</param>
    <param name="rig">The rig whose clock moves.</param>
    <param name="seconds">How far to move the clock first.</param>
    <remarks>
    The clock only ever moves forward, across tests too, because the helper
    may keep its pacing in state shared by every instance.
    </remarks>
    """
    rig.clock.now += seconds
    helper.update_watchlist()


def item(label, dbtype="movie", dbid=0, file="", kind="video", **extra):
    """
    <summary>One list item record as lists.json stores it.</summary>
    <param name="label">The title.</param>
    <param name="dbtype">movie, episode, tvshow, season, musicvideo or song.</param>
    <param name="dbid">The library id, 0 for none.</param>
    <param name="file">The file or plugin path.</param>
    <param name="kind">video or music.</param>
    <param name="extra">Other record fields.</param>
    <returns>A dict.</returns>
    """
    rec = {"label": label, "dbtype": dbtype, "dbid": dbid, "file": file, "kind": kind,
           "thumb": "thumb_" + label + ".jpg", "duration": 5400, "year": "1999"}
    rec.update(extra)
    return rec


def write_lists(lists):
    """
    <summary>Write lists.json in the temporary profile, without touching a helper.</summary>
    <param name="lists">The list dicts.</param>
    """
    os.makedirs(os.path.dirname(T.LISTS_FILE), exist_ok=True)
    for suffix in ("", ".previous"):
        if os.path.exists(T.LISTS_FILE + suffix):
            os.remove(T.LISTS_FILE + suffix)
    with open(T.LISTS_FILE, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "last": "", "sort": "", "lists": lists}, handle)


def helper_with(lists):
    """
    <summary>A helper that has loaded the given lists.</summary>
    <param name="lists">The list dicts.</param>
    <returns>A FunctionalHelper.</returns>
    """
    write_lists(lists)
    helper = service.FunctionalHelper()
    helper._lists_load()
    return helper


def tag_paths():
    """
    <summary>The two tag path properties.</summary>
    <returns>(movies, tvshows).</returns>
    """
    return T.PROPS.get("watchlist_movies_path", ""), T.PROPS.get("watchlist_tvshows_path", "")


def test_service_tag():
    """
    <summary>Source tag: both paths are watchlist_url for the tag, the default
    Watch later when the tag is empty, changing the tag changes both, and the
    count is cleared.</summary>
    """
    print("running test_service_tag")
    rig = Rig()
    try:
        h = helper_with([])
        T.PROPS["Watchlist.Count"] = "4"
        rig.set_skin("watchlist_source", "tag")
        step(h, rig)
        default = T.STRINGS[31899]
        check(tag_paths() == (service.watchlist_url("movies", default), service.watchlist_url("tvshows", default)),
              "an empty tag should use the default %r, got %r" % (default, tag_paths()))
        check(not T.PROPS.get("Watchlist.Count"), "the tag source should clear Watchlist.Count, got %r" % T.PROPS.get("Watchlist.Count"))
        first = tag_paths()
        rig.set_skin("watchlist_tag", "Later tonight")
        step(h, rig)
        check(tag_paths() == (service.watchlist_url("movies", "Later tonight"), service.watchlist_url("tvshows", "Later tonight")),
              "a named tag should reach both paths, got %r" % (tag_paths(),))
        check(tag_paths()[0] != first[0] and tag_paths()[1] != first[1], "changing the tag should change both paths")
        _base, doc = url_doc(T.PROPS.get("watchlist_movies_path", ""))
        rules = flat_rules(doc["rules"]) if doc else []
        value = rules[0].get("value") if rules else None
        check((value if isinstance(value, list) else [value]) == ["Later tonight"], "the movies path should carry the tag, got %r" % (rules,))
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the tag path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_list():
    """
    <summary>Source list: the named list's video items, at most 12, in order,
    with label, sub, thumb and count; the tag paths cleared; slots no longer
    used cleared; a changed list read again within about ten seconds.</summary>
    """
    print("running test_service_list")
    rig = Rig()
    try:
        items = [item("Film %02d" % n, "movie", 100 + n) for n in range(1, 16)]
        items.insert(2, item("Some Song", "song", 0, "/music/a.flac", kind="music"))
        items[0] = item("Episode One", "episode", 9, show="Series", season="1", episode="2")
        h = helper_with([{"name": "Other", "items": [item("Not Me", "movie", 1)]},
                         {"name": "Weekend", "items": items}])
        T.PROPS["watchlist_movies_path"] = "stale"
        T.PROPS["watchlist_tvshows_path"] = "stale"
        rig.set_skin("watchlist_source", "list")
        rig.set_skin("watchlist_list", "Weekend")
        step(h, rig)
        videos = [it for it in h._lists[1]["items"] if it["kind"] == "video"][:12]
        check(T.PROPS.get("Watchlist.Count") == "12", "the count should be 12 for fifteen video items, got %r" % T.PROPS.get("Watchlist.Count"))
        check(tag_paths() == ("", "") or not any(tag_paths()), "the tag paths should be cleared, got %r" % (tag_paths(),))
        for n, it in enumerate(videos, 1):
            check(T.PROPS.get("Watchlist.%d.Label" % n) == it["label"], "slot %d label should be %r, got %r" % (n, it["label"], T.PROPS.get("Watchlist.%d.Label" % n)))
            check(T.PROPS.get("Watchlist.%d.Sub" % n) == h._list_item_sub(it), "slot %d sub should be the Lists subtitle %r, got %r" % (n, h._list_item_sub(it), T.PROPS.get("Watchlist.%d.Sub" % n)))
            check(T.PROPS.get("Watchlist.%d.Thumb" % n) == it["thumb"], "slot %d thumb should be %r, got %r" % (n, it["thumb"], T.PROPS.get("Watchlist.%d.Thumb" % n)))
        check(not T.PROPS.get("Watchlist.13.Label"), "there should be no thirteenth slot")
        check("Some Song" not in [T.PROPS.get("Watchlist.%d.Label" % n) for n in range(1, 13)], "a music item should not be published")
        check(T.PROPS.get("Watchlist.1.Label") == "Episode One" and T.PROPS.get("Watchlist.2.Label") == "Film 02",
              "items should keep the list's own order")
        # A shorter list: the slots it no longer fills are cleared.
        del h._lists[1]["items"][2:]
        step(h, rig)
        check(T.PROPS.get("Watchlist.Count") == "2", "after the list shrank the count should be 2, got %r" % T.PROPS.get("Watchlist.Count"))
        for n in range(3, 13):
            for field in ("Label", "Sub", "Thumb"):
                check(not T.PROPS.get("Watchlist.%d.%s" % (n, field)), "slot %d %s should be cleared" % (n, field))
        # An item added: seen within about ten seconds.
        new = dict(h._lists[1]["items"][0], label="Brand New", dbid=555)
        h._lists[1]["items"].append(new)
        step(h, rig)
        check(T.PROPS.get("Watchlist.3.Label") == "Brand New" and T.PROPS.get("Watchlist.Count") == "3",
              "an item added to the list should show once ten seconds have passed, got %r" % T.PROPS.get("Watchlist.3.Label"))
        # The list named is not there: nothing from another list.
        rig.set_skin("watchlist_list", "Missing")
        step(h, rig)
        check(not T.PROPS.get("Watchlist.1.Label"), "an unknown list name should publish nothing")
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the list path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_off():
    """
    <summary>Source empty: every Watchlist property is cleared, after the tag
    source and after the list source.</summary>
    """
    print("running test_service_off")
    rig = Rig()
    try:
        h = helper_with([{"name": "Weekend", "items": [item("A", "movie", 1), item("B", "movie", 2)]}])
        for source in ("tag", "list"):
            rig.set_skin("watchlist_source", source)
            rig.set_skin("watchlist_list", "Weekend")
            step(h, rig)
            check(any(k.startswith("Watchlist.") or k.startswith("watchlist_") for k in T.PROPS if T.PROPS[k]),
                  "the %s source should have published something to clear" % source)
            rig.set_skin("watchlist_source", "")
            step(h, rig)
            left = {k: v for k, v in T.PROPS.items() if (k.startswith("Watchlist.") or k.startswith("watchlist_")) and v}
            check(not left, "with the source empty after %s every property should be cleared, left %r" % (source, left))
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the off path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_pick():
    """
    <summary>The pick command offers the list names and sets the chosen name
    on watchlist_list, quoted so a comma survives; with no lists it gives a
    notification and sets nothing.</summary>
    """
    print("running test_service_pick")
    rig = Rig()
    try:
        h = helper_with([{"name": "First", "items": [item("A", "movie", 1)]},
                         {"name": "Fri, Night", "items": [item("B", "movie", 2)]}])
        rig.set_skin("watchlist_source", "list")
        rig.set_skin("watchlist_command", "pick")
        rig.pick = 1
        step(h, rig)
        offered = rig.picked_from or []
        check(len(offered) == 2 and all(any(name in str(line) for line in offered) for name in ("First", "Fri, Night")),
              "the dialog should offer the list names, got %r" % (offered,))
        sets = [b for b in rig.builtins if b.startswith("Skin.SetString(watchlist_list,")]
        check(len(sets) == 1, "exactly one Skin.SetString(watchlist_list,...) should run, got %r" % sets)
        if sets:
            # WATCHLIST-FIX: the skin's _set_skin_string quotes the value, so
            # Kodi's builtin split keeps the comma inside it.
            check(sets[0] == 'Skin.SetString(watchlist_list,"Fri, Night")',
                  "the chosen name should be set quoted, got %r" % sets[0])
        # A cancelled dialog sets nothing.
        rig.builtins.clear()
        rig.labels.pop("Skin.String(watchlist_list)", None)
        rig.set_skin("watchlist_command", "pick")
        rig.pick = -1
        step(h, rig)
        check(not [b for b in rig.builtins if b.startswith("Skin.SetString(watchlist_list,")], "a cancelled pick should set nothing")
        # No lists at all.
        h2 = helper_with([])
        rig.builtins.clear()
        T._Dialog.toasts = []
        rig.set_skin("watchlist_command", "pick")
        rig.picked_from = None
        step(h2, rig)
        check(len(T._Dialog.toasts) >= 1, "with no lists there should be a notification, got %r and builtins %r" % (T._Dialog.toasts, rig.builtins))
        check(not [b for b in rig.builtins if b.startswith("Skin.SetString(watchlist_list,")], "with no lists nothing should be set")
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the pick path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_list_renamed():
    """
    <summary>WATCHLIST-FIX: renaming the chosen list carries watchlist_list to
    the new name, deleting it resets the setting, and a rename of another
    list leaves it alone (the review's finding 2).</summary>
    """
    print("running test_list_renamed")
    rig = Rig()
    try:
        h = helper_with([{"name": "Weekend", "items": [item("A", "movie", 1)]}])
        rig.set_skin("watchlist_list", "Weekend")
        rig.builtins.clear()
        h._list_renamed("Other", "Else")
        check(not rig.builtins, "renaming another list should change nothing, got %r" % rig.builtins)
        h._list_renamed("Weekend", "Saturday")
        check(rig.builtins == ['Skin.SetString(watchlist_list,"Saturday")'],
              "renaming the chosen list should carry the setting, got %r" % rig.builtins)
        rig.builtins.clear()
        rig.set_skin("watchlist_list", "Saturday")
        h._list_renamed("Saturday", "")
        check(rig.builtins == ["Skin.Reset(watchlist_list)"],
              "deleting the chosen list should reset the setting, got %r" % rig.builtins)
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the rename path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_service_play():
    """
    <summary>The play:N command: a library item plays by id with resume, a file
    item by path with resume, a whole show or season opens its videodb page and
    does not play, and an empty slot does nothing.</summary>
    """
    print("running test_service_play")
    rig = Rig()
    try:
        lists = [{"name": "Weekend", "items": [
            item("Library Film", "movie", 7, "/media/films/a.mkv"),
            item("Plugin Film", "movie", 0, "plugin://plugin.video.example/play/?id=9"),
            item("Library Episode", "episode", 44, "/media/tv/b.mkv", show="Series", season="1", episode="3"),
            item("Whole Show", "tvshow", 31, "", count=12),
            item("A Season", "season", 55, "", count=8),
        ]}]
        h = helper_with(lists)
        rig.set_skin("watchlist_source", "list")
        rig.set_skin("watchlist_list", "Weekend")
        step(h, rig)

        def press(n):
            """
            <summary>Send play:N and let the helper handle it.</summary>
            <param name="n">The slot number.</param>
            """
            rig.rpc.clear()
            rig.builtins.clear()
            rig.set_skin("watchlist_command", "play:%d" % n)
            step(h, rig)

        for slot, want in ((1, {"movieid": 7}), (2, {"file": "plugin://plugin.video.example/play/?id=9"}), (3, {"episodeid": 44})):
            press(slot)
            opened = rig.opened()
            check(len(opened) == 1 and opened[0].get("item") == want and (opened[0].get("options") or {}).get("resume") is True,
                  "slot %d should play %r with resume, got %r" % (slot, want, opened))
            check(not rig.windows(), "slot %d should not open a window" % slot)
        press(4)
        check(not rig.opened() and rig.windows() == ["ActivateWindow(Videos,videodb://tvshows/titles/31/,return)"],
              "a whole show should open its page and not play, got %r and %r" % (rig.opened(), rig.windows()))
        press(5)
        check(not rig.opened() and rig.windows() == ["ActivateWindow(Videos,videodb://tvshows/titles/31/2/,return)"],
              "a season should open its page and not play, got %r and %r" % (rig.opened(), rig.windows()))
        press(9)
        check(not rig.opened() and not rig.windows(), "an empty slot should do nothing, got %r %r" % (rig.opened(), rig.windows()))
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the play path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_url()
    test_strings()
    test_settings_rows()
    test_help_and_preview()
    test_expressions_off_and_on()
    test_tab_positions()
    test_tab_visibility_on()
    test_tab_clicks()
    test_page_three()
    test_stage_and_home_params()
    test_service_tag()
    test_service_list()
    test_service_off()
    test_service_pick()
    test_service_play()
    test_list_renamed()
    passed = sum(1 for ok, _ in CHECKS if ok)
    print("test_watchlist: %d of %d checks passed" % (passed, len(CHECKS)))
    if FAILURES:
        print("test_watchlist: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_watchlist: all checks passed")


if __name__ == "__main__":
    main()
