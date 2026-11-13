#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 31, the More like this row on the information dialog,
written from the spec: the setting row and its cycle, the label variable, the
help, preview and strings, the dialog's list, plot sizes and navigation, the
off state, the service's InfoLikePath, and the browse, sort and limit
attributes of the other library rows.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py; the condition reader, the Rig and the URL helpers are
borrowed from tests/test_watchlist.py and tests/test_hide_continue.py. Exits
non zero when a check fails.

Usage:
    python3 tests/test_more_like_this.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)
import test_watchlist as W  # noqa: E402
import test_hide_continue as H  # noqa: E402

service = T.service
XML = W.XML
STRINGS = W.STRINGS
check = W.check
read = W.read
Env = W.Env
url_doc = W.url_doc
flat_rules = W.flat_rules
holds = H.holds


def _extra_atom(text, env, _base=W.atom):
    """
    <summary>The watchlist reader plus Window(home).Property emptiness tests.</summary>
    <param name="text">One plain condition.</param>
    <param name="env">The state.</param>
    <param name="_base">The reader being extended.</param>
    <returns>True or False.</returns>
    """
    m = re.fullmatch(r"String\.IsEmpty\(Window\(home\)\.Property\(([\w.]+)\)\)", text.strip())
    if m:
        return not env.props.get(m.group(1), "")
    return _base(text, env)


W.atom = _extra_atom


def dialog():
    """
    <summary>The information dialog's XML.</summary>
    <returns>The root element.</returns>
    """
    return ET.parse(os.path.join(XML, "DialogVideoInfo.xml")).getroot()


def by_id(root, cid):
    """
    <summary>The first control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element or None.</returns>
    """
    return W.find_control(root, cid)


def target(control, tag, env):
    """
    <summary>Where a navigation tag leads, taking the first line whose condition holds.</summary>
    <param name="control">The control element.</param>
    <param name="tag">"onup", "ondown", "onleft" or "onright".</param>
    <param name="env">The state.</param>
    <returns>The destination text, or None when no line applies.</returns>
    """
    for node in control.findall(tag):
        if W.evaluate(node.get("condition") or "", env):
            return (node.text or "").strip()
    return None


def strings_po():
    """
    <summary>The English strings by id.</summary>
    <returns>A dict of id text to msgid.</returns>
    """
    text = read(STRINGS)
    return {m.group(1): m.group(2) for m in re.finditer(r'msgctxt "#(\d+)"\nmsgid "(.*)"', text)}


# ---- The setting row -----------------------------------------------------------

def test_setting_row():
    """
    <summary>Row 7214 sits in grouplist 7021 after 7213, shows its label, cycles
    through the four values, goes left to 7230, and 7316 goes up to it.</summary>
    """
    print("running test_setting_row")
    root = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    group = by_id(root, "7021")
    check(group is not None and group.get("type") == "grouplist", "7021 is a grouplist")
    ids = [c.get("id") for c in group.findall("control")] if group is not None else []
    check("7214" in ids and "7213" in ids and ids.index("7214") == ids.index("7213") + 1,
          "row 7214 is inside 7021 straight after 7213")
    row = by_id(root, "7214")
    check(row is not None and row.get("type") == "button", "7214 is a button")
    if row is None:
        return
    check(row.findtext("label") == "$LOCALIZE[31933] $VAR[MoreLikeLabel]", "7214 label is the heading plus the value")
    check(row.findtext("onleft") == "7230", "left from 7214 goes to 7230")
    clicks = [(c.get("condition") or "", (c.text or "").strip()) for c in row.findall("onclick")]
    check(len(clicks) == 4, "7214 has four onclick lines")
    # Kodi reads every condition before any line runs, so run the lines that way.
    for start, expect in (("", "collection"), ("collection", "director"), ("director", "genre"), ("genre", "")):
        env = Env(strings={"more_like": start})
        fired = [cmd for cond, cmd in clicks if W.evaluate(cond, env)]
        want = "Skin.SetString(more_like,%s)" % expect if expect else "Skin.Reset(more_like)"
        check(fired == [want], "click from %r gives %r (got %r)" % (start, want, fired))
    last = by_id(root, "7316")
    check(last is not None and last.findtext("onup") == "7214", "7316 onup is 7214, the list's last row")
    check(ids[-1] == "7214", "7214 is the last row of 7021")


def test_label_variable():
    """
    <summary>MoreLikeLabel gives 31934, 31935, 31936 and 31893 for Off.</summary>
    """
    print("running test_label_variable")
    root = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
    var = next((v for v in root.iter("variable") if v.get("name") == "MoreLikeLabel"), None)
    check(var is not None, "variable MoreLikeLabel exists")
    if var is None:
        return
    for value, want in (("collection", "31934"), ("director", "31935"), ("genre", "31936"), ("", "31893")):
        env = Env(strings={"more_like": value})
        got = next(((v.text or "").strip() for v in var.findall("value") if W.evaluate(v.get("condition") or "", env)), None)
        check(got == "$LOCALIZE[%s]" % want, "MoreLikeLabel for %r is %s (got %r)" % (value, want, got))


def test_help_preview_strings():
    """
    <summary>Help 31937 with a Where line, listed as shown; no preview; the strings exist.</summary>
    """
    print("running test_help_preview_strings")
    help_text = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    preview = read(os.path.join(XML, "Includes_SettingsPreview.xml"))
    po = strings_po()
    shown = help_text.split('<expression name="settings_help_shown">')[1].split("</expression>")[0]
    check("Control.HasFocus(7214)" in shown, "settings_help_shown lists 7214")
    entry = re.search(r'Control\.HasFocus\(7214\)">\$LOCALIZE\[(\d+)\]', help_text)
    check(bool(entry) and entry.group(1) == "31937", "the help map sends 7214 to 31937")
    check("[CR]Where: " in po.get("31937", ""), "string 31937 has a Where line")
    none = preview.split('<expression name="settings_preview_none">')[1].split("</expression>")[0]
    check("Control.HasFocus(7214)" in none, "7214 is in settings_preview_none")
    others = re.findall(r"Control\.HasFocus\(7214\)", preview)
    check(len(others) == 1, "7214 appears in the preview file only once, in the none list")
    for sid in ("31933", "31934", "31935", "31936", "31937", "31938", "31893"):
        check(bool(po.get(sid)), "string %s exists and is not empty" % sid)
    check(po.get("31938") == "MORE LIKE THIS", "string 31938 is MORE LIKE THIS")


# ---- The dialog ------------------------------------------------------------------

def test_list_attributes():
    """
    <summary>List 9360 reads InfoLikePath with the promised content attributes.</summary>
    """
    print("running test_list_attributes")
    lst = by_id(dialog(), "9360")
    check(lst is not None and lst.get("type") == "list", "9360 is a list")
    if lst is None:
        return
    content = lst.find("content")
    check(content is not None and (content.text or "").strip() == "$INFO[Window(home).Property(InfoLikePath)]",
          "9360 content is the InfoLikePath property")
    attrs = content.attrib if content is not None else {}
    for key, want in (("target", "videos"), ("sortby", "year"), ("sortorder", "descending"),
                      ("limit", "12"), ("browse", "never")):
        check(attrs.get(key) == want, "9360 content %s is %s (got %r)" % (key, want, attrs.get(key)))
    vis = lst.find("visible")
    check(vis is not None and vis.get("allowhiddenfocus") == "true", "9360 visible allows hidden focus")


def shown_state(choice, path, items):
    """
    <summary>Which of the new pieces draw for a state.</summary>
    <param name="choice">The more_like value.</param>
    <param name="path">The InfoLikePath value.</param>
    <param name="items">The number of items in 9360.</param>
    <returns>(list shown, heading shown, short plot shown, full plot shown).</returns>
    """
    root = dialog()
    base = Env(strings={"more_like": choice}, props={"InfoLikePath": path}, counts={"9360": items})
    lst_vis = W.evaluate(by_id(root, "9360").findtext("visible"), base)
    env = Env(strings={"more_like": choice}, props={"InfoLikePath": path}, counts={"9360": items},
              visible={"9360"} if lst_vis else set())
    heading = next(c for c in root.iter("control") if c.get("type") == "label" and c.findtext("label") == "31938")
    boxes = {c.findtext("height"): c for c in root.iter("control")
             if c.get("type") == "textbox" and c.findtext("label") == "$INFO[ListItem.Plot]"}
    short, full = boxes.get("110"), boxes.get("290")
    return (lst_vis, W.evaluate(heading.findtext("visible"), env),
            W.evaluate(short.findtext("visible"), env), W.evaluate(full.findtext("visible"), env))


def test_visibility_and_off_state():
    """
    <summary>The heading, short plot, full plot and list follow the choice, the
    path and the item count; with the choice Off nothing new draws.</summary>
    """
    print("running test_visibility_and_off_state")
    root = dialog()
    heading = [c for c in root.iter("control") if c.get("type") == "label" and c.findtext("label") == "31938"]
    check(len(heading) == 1, "one heading label 31938 in the dialog")
    boxes = [c.findtext("height") for c in root.iter("control")
             if c.get("type") == "textbox" and c.findtext("label") == "$INFO[ListItem.Plot]"]
    check(sorted(boxes) == ["110", "290"], "plot textboxes of height 110 and 290 exist (got %s)" % boxes)
    check(shown_state("", "", 0) == (False, False, False, True), "Off, no path: only the full plot draws")
    check(shown_state("", "x", 5) == (False, False, False, True), "Off with a stale path and items: only the full plot")
    check(shown_state("genre", "", 0) == (False, False, False, True), "set but no path: nothing new, full plot")
    check(shown_state("genre", "x", 5) == (True, True, True, False), "set, path and items: list, heading, short plot")
    check(shown_state("collection", "x", 0) == (True, False, False, True), "set, path, no items: list only, full plot")


def test_dialog_navigation():
    """
    <summary>Navigation of 9360, the cast slots and the action buttons.</summary>
    """
    print("running test_dialog_navigation")
    root = dialog()
    lst = by_id(root, "9360")
    cast = {"InfoCast.1.Name": "Someone"}
    for props, want in ((cast, "8001"), ({}, "9000")):
        env = Env(props=props)
        check(target(lst, "ondown", env) == want, "9360 down with%s cast goes to %s" % ("" if props else "out", want))
    env = Env()
    check(target(lst, "onup", env) == "9360", "9360 up stays on itself")
    check(target(lst, "onleft", env) == "9360", "9360 left stays on itself")
    check(target(lst, "onright", env) == "9360", "9360 right stays on itself")
    check(target(lst, "onback", env) == "9000", "9360 back goes to 9000")

    buttons = by_id(root, "9000")
    shown = {"9360"}
    for props, counts, vis, want, why in (
            (cast, {"9360": 4}, shown, "8001", "cast present"),
            (cast, {}, set(), "8001", "cast present and no row"),
            ({}, {"9360": 4}, shown, "9360", "no cast, row with items"),
            ({}, {"9360": 0}, shown, "9000", "no cast, row empty"),
            ({}, {"9360": 4}, set(), "9000", "no cast, row hidden"),
            ({}, {}, set(), "9000", "nothing at all")):
        got = target(buttons, "onup", Env(props=props, counts=counts, visible=vis))
        check(got == want, "action buttons up with %s goes to %s (got %s)" % (why, want, got))

    incl = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
    slot = next((i for i in incl.iter("include") if i.get("name") == "InfoCastSlot"), None)
    check(slot is not None, "include InfoCastSlot exists")
    if slot is None:
        return
    btn = next((c for c in slot.iter("control") if c.get("type") == "button"), None)
    ups = btn.findall("onup") if btn is not None else []
    check(len(ups) >= 2, "a cast slot has a conditional onup and its old onup")
    for counts, vis, want in (({"9360": 3}, {"9360"}, "9360"), ({"9360": 0}, {"9360"}, "$PARAM[id]"),
                              ({"9360": 3}, set(), "$PARAM[id]"), ({}, set(), "$PARAM[id]")):
        got = target(btn, "onup", Env(counts=counts, visible=vis))
        check(got == want, "cast slot up with counts %s visible %s goes to %s (got %s)" % (counts, sorted(vis), want, got))
    check(ups and ups[0].get("condition") and (ups[-1].get("condition") is None),
          "the row line comes before the old unconditional onup")
    strip = next((i for i in incl.iter("include") if i.get("name") == "InfoCastStrip"), None)
    used = len([i for i in strip.iter("include") if i.get("content") == "InfoCastSlot"]) if strip is not None else 0
    check(used == 8, "the strip uses InfoCastSlot for all eight slots (got %d)" % used)


# ---- The other library rows ------------------------------------------------------

def test_other_rows():
    """
    <summary>Every other library row has browse never, its limit and its sort.</summary>
    """
    print("running test_other_rows")
    rows = {}
    for name in ("Home.xml", "Includes_Home.xml"):
        for node in ET.parse(os.path.join(XML, name)).getroot().iter("control"):
            if node.get("type") == "list" and node.get("id"):
                content = node.find("content")
                if content is not None:
                    rows.setdefault(node.get("id"), []).append(content)
    want = {"9201": ("lastplayed", "descending", "12"), "9203": ("lastplayed", "descending", "12"),
            "9205": ("tvshowtitle", "ascending", "12"), "9231": ("dateadded", "descending", "12"),
            "9233": ("dateadded", "descending", "12")}
    for rid in ("9252", "9254", "9256", "9262", "9264", "9266"):
        want[rid] = (None, None, "15")
    for rid, (sortby, order, limit) in sorted(want.items()):
        found = rows.get(rid, [])
        check(bool(found), "row %s has a content tag" % rid)
        for content in found:
            check(content.get("browse") == "never", "row %s has browse never" % rid)
            check(content.get("limit") == limit, "row %s has limit %s (got %r)" % (rid, limit, content.get("limit")))
            if sortby:
                check(content.get("sortby") == sortby and content.get("sortorder") == order,
                      "row %s sorts %s %s (got %r %r)" % (rid, sortby, order, content.get("sortby"), content.get("sortorder")))


# ---- The service -------------------------------------------------------------------

class LikeRig(W.Rig):
    """<summary>The watchlist rig plus the information dialog's window test and a count of property writes.</summary>"""

    def __init__(self):
        """<summary>Install the stubs and count Home property writes.</summary>"""
        super().__init__()
        self.active = True
        self.writes = 0
        self._set, self._clear = T._Window.setProperty, T._Window.clearProperty
        rig = self

        def counted_set(win, key, value):
            """<summary>Count a write to InfoLikePath, then store it.</summary><param name="win">The window.</param><param name="key">Name.</param><param name="value">Text.</param>"""
            if key == "InfoLikePath":
                rig.writes += 1
            return rig._set(win, key, value)

        def counted_clear(win, key):
            """<summary>Count a clear of InfoLikePath, then clear it.</summary><param name="win">The window.</param><param name="key">Name.</param>"""
            if key == "InfoLikePath":
                rig.writes += 1
            return rig._clear(win, key)

        T._Window.setProperty, T._Window.clearProperty = counted_set, counted_clear

    def restore(self):
        """<summary>Put every stub back.</summary>"""
        T._Window.setProperty, T._Window.clearProperty = self._set, self._clear
        super().restore()

    def cond(self, text):
        """
        <summary>The watchlist answers plus Window.IsActive(movieinformation).</summary>
        <param name="text">The condition.</param>
        <returns>True or False.</returns>
        """
        if text == "Window.IsActive(movieinformation)":
            return self.active
        return super().cond(text)

    def item(self, dbtype="movie", title="Alien", set_="", director="", genre=""):
        """
        <summary>Describe the item the dialog is showing.</summary>
        <param name="dbtype">ListItem.DBType.</param>
        <param name="title">ListItem.Title.</param>
        <param name="set_">ListItem.Set.</param>
        <param name="director">ListItem.Director.</param>
        <param name="genre">ListItem.Genre.</param>
        """
        for key, value in (("DBType", dbtype), ("Title", title), ("Set", set_), ("Director", director),
                           ("Genre", genre)):
            self.labels["ListItem.%s" % key] = value
        self.labels["ListItem.Property(DBType)"] = dbtype
        self.labels["ListItem.Label"] = title


def tick(rig, helper):
    """
    <summary>Run one fast tick of the More like this service.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    <returns>The InfoLikePath now ('' when unset).</returns>
    """
    helper.update_info_like()
    return T.PROPS.get("InfoLikePath", "")


def fresh(choice, **item):
    """
    <summary>A rig with a choice and an item, and a new helper.</summary>
    <param name="choice">The more_like value.</param>
    <param name="item">Arguments for LikeRig.item.</param>
    <returns>(rig, helper).</returns>
    """
    rig = LikeRig()
    rig.set_skin("more_like", choice)
    rig.item(**item)
    return rig, service.FunctionalHelper()


def rules_of(path):
    """
    <summary>The base and the rules list of a path.</summary>
    <param name="path">An InfoLikePath.</param>
    <returns>(base, rules or None, whole document or None).</returns>
    """
    base, doc = url_doc(path)
    rules = doc["rules"].get("and") if doc else None
    return base, rules, doc


def test_service_matches():
    """
    <summary>The path for each choice and kind: base, rules, order and no limit.</summary>
    """
    print("running test_service_matches")
    cases = (
        ("collection", dict(set_="Alien Collection", director="D One", genre="Horror"),
         "set", "Alien Collection", "year", "descending"),
        ("director", dict(director="Dir One / Dir Two", set_="S", genre="Horror"),
         "director", "Dir One", "year", "descending"),
        ("genre", dict(genre="Horror / Sci Fi", set_="S", director="D"),
         "genre", "Horror", "year", "descending"),
    )
    for choice, item, field, value, method, direction in cases:
        rig, helper = fresh(choice, **item)
        try:
            path = tick(rig, helper)
            base, rules, doc = rules_of(path)
            check(base == service.VIDEODB_BASES["movies"] == "videodb://movies/titles/", "%s film: movies base" % choice)
            check(rules is not None and len(rules) == 2, "%s film: rules are an and of two" % choice)
            flat = flat_rules(doc["rules"]) if doc else []
            match = [r for r in flat if r["field"] == field]
            check(len(match) == 1 and match[0]["operator"] == "is" and match[0]["value"] == [value],
                  "%s film: %s is %r (got %s)" % (choice, field, value, match))
            title = [r for r in flat if r["field"] == "title"]
            check(len(title) == 1 and title[0]["operator"] == "isnot" and title[0]["value"] == ["Alien"],
                  "%s film: title isnot the item's own title" % choice)
            check(doc is not None and doc.get("type") == "movies", "%s film: playlist type is movies" % choice)
            order = (doc or {}).get("order", {})
            check(order.get("method") == method and (direction is None or order.get("direction") == direction),
                  "%s film: order %s %s (got %s)" % (choice, method, direction, order))
            check("limit" not in (doc or {}),
                  "%s film: no limit in the playlist" % choice)
            check("limit" not in path, "%s film: the word limit is not in the path at all" % choice)
            check(T.PROPS.get("InfoLikePath") == path, "%s film: published on the Home property" % choice)
        finally:
            rig.restore()


def test_service_genre_years():
    """
    <summary>MORE-LIKE-FIX: with the item's year known, a genre match keeps to
    five years either side; a collection or director match does not.</summary>
    """
    print("running test_service_genre_years")
    for choice, want in (("genre", True), ("director", False), ("collection", False)):
        rig, helper = fresh(choice, genre="Horror", director="D", set_="S")
        try:
            rig.labels["ListItem.Year"] = "2001"
            _base, doc = url_doc(tick(rig, helper))
            years = sorted((r["operator"], r["value"][0]) for r in flat_rules(doc["rules"]) if r["field"] == "year")
            if want:
                check(years == [("greaterthan", "1995"), ("lessthan", "2007")],
                      "genre: years 1996 to 2006 around 2001, got %r" % years)
            else:
                check(not years, "%s: no year window, got %r" % (choice, years))
        finally:
            rig.restore()


def test_service_title_and_rows():
    """
    <summary>The path rules really pick the right rows when run against sample rows.</summary>
    """
    print("running test_service_title_and_rows")
    rig, helper = fresh("genre", genre="Horror / Comedy", title="Alien")
    try:
        _base, doc = url_doc(tick(rig, helper))
        rule = doc["rules"]
        same = {"genre": ["Horror"], "title": ["Alien"]}
        other = {"genre": ["Horror"], "title": ["Aliens"]}
        wrong = {"genre": ["Comedy"], "title": ["Zed"]}

        def kodi_holds(row):
            """<summary>Run the playlist rules on a row whose values are lists.</summary><param name="row">A row.</param><returns>True when it passes.</returns>"""
            return all((r["value"][0] in row[r["field"]]) == (r["operator"] == "is") for r in flat_rules(rule))
        check(not kodi_holds(same), "the item itself is left out")
        check(kodi_holds(other), "another title of the genre is kept")
        check(not kodi_holds(wrong), "a title of another first genre is left out")
        check(callable(holds), "the borrowed holds helper is available")
    finally:
        rig.restore()


def test_service_show():
    """
    <summary>A show uses the tvshows base and its first genre whatever the choice.</summary>
    """
    print("running test_service_show")
    for choice in ("collection", "director", "genre"):
        rig, helper = fresh(choice, dbtype="tvshow", title="Some Show", genre="Drama / Crime",
                            set_="Ignored Set", director="Ignored Director")
        try:
            base, rules, doc = rules_of(tick(rig, helper))
            check(base == "videodb://tvshows/titles/", "%s show: tvshows base" % choice)
            flat = flat_rules(doc["rules"]) if doc else []
            genre = [r for r in flat if r["field"] == "genre"]
            check(len(flat) == 2 and len(genre) == 1 and genre[0]["value"] == ["Drama"] and genre[0]["operator"] == "is",
                  "%s show: genre is the first genre, and no set or director rule (got %s)" % (choice, flat))
            title = [r for r in flat if r["field"] == "title"]
            check(len(title) == 1 and title[0]["operator"] == "isnot" and title[0]["value"] == ["Some Show"],
                  "%s show: title isnot its own title" % choice)
            check(doc is not None and doc.get("type") == "tvshows", "%s show: playlist type is tvshows" % choice)
        finally:
            rig.restore()


def test_service_empty_cases():
    """
    <summary>No match data, or an item that is not a film or show, gives an empty path.</summary>
    """
    print("running test_service_empty_cases")
    cases = (
        ("collection", dict(set_="", director="D", genre="G"), "film with no set"),
        ("director", dict(set_="S", director="", genre="G"), "film with no director"),
        ("genre", dict(set_="S", director="D", genre=""), "film with no genre"),
        ("genre", dict(dbtype="tvshow", genre=""), "show with no genre"),
        ("genre", dict(dbtype="season", set_="S", director="D", genre="G"), "season"),
        ("genre", dict(dbtype="episode", set_="S", director="D", genre="G"), "episode"),
        ("genre", dict(dbtype="", set_="S", director="D", genre="G"), "empty item"),
    )
    for choice, item, why in cases:
        rig, helper = fresh(choice, **item)
        try:
            T.PROPS["InfoLikePath"] = "stale"
            got = tick(rig, helper)
            check(got == "", "%s: empty path (got %r)" % (why, got))
        finally:
            rig.restore()


def test_service_gating_and_writes():
    """
    <summary>Off, closed dialog, first tick clearing, writing only on change.</summary>
    """
    print("running test_service_gating_and_writes")
    rig, helper = fresh("", set_="S", director="D", genre="G")
    try:
        T.PROPS["InfoLikePath"] = "stale"
        check(tick(rig, helper) == "", "choice Off: the first tick clears a stale value")
    finally:
        rig.restore()

    rig, helper = fresh("genre", genre="G")
    try:
        rig.active = False
        T.PROPS["InfoLikePath"] = "stale"
        check(tick(rig, helper) == "", "dialog closed: the first tick clears a stale value")
    finally:
        rig.restore()

    rig, helper = fresh("genre", genre="Horror", title="A")
    try:
        first = tick(rig, helper)
        check(first != "", "dialog open with a choice: a path is published")
        writes = rig.writes
        again = tick(rig, helper)
        check(again == first and rig.writes == writes, "the same state writes nothing more")
        rig.item(genre="Horror", title="B")
        changed = tick(rig, helper)
        check(changed != first and changed != "", "a new title gives a new path")
        check(rig.writes == writes + 1, "one write for the change")
        rig.active = False
        check(tick(rig, helper) == "", "closing the dialog clears the path")
        writes = rig.writes
        tick(rig, helper)
        check(rig.writes == writes, "staying closed writes nothing")
        rig.active = True
        rig.set_skin("more_like", "")
        check(tick(rig, helper) == "", "switching the choice Off clears the path")
        rig.set_skin("more_like", "genre")
        check(tick(rig, helper) != "", "switching it on again publishes")
    finally:
        rig.restore()

    rig, helper = fresh("genre", genre="Horror")
    try:
        before = rig.writes
        rig.active = False
        tick(rig, helper)
        tick(rig, helper)
        check(rig.writes - before <= 1, "an empty state with nothing stale writes at most once, on the first tick")
    finally:
        rig.restore()


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    for func in (test_setting_row, test_label_variable, test_help_preview_strings, test_list_attributes,
                 test_visibility_and_off_state, test_dialog_navigation, test_other_rows,
                 test_service_matches, test_service_genre_years, test_service_title_and_rows, test_service_show,
                 test_service_empty_cases, test_service_gating_and_writes):
        try:
            func()
        except Exception as exc:  # a crash is a finding, reported and counted
            W.fail("%s raised %s: %s" % (func.__name__, type(exc).__name__, exc))
    for ok, what in W.CHECKS:
        if ok:
            print("PASS: " + what)
    passed = sum(1 for ok, _ in W.CHECKS if ok)
    print("test_more_like_this: %d of %d checks passed" % (passed, len(W.CHECKS)))
    if W.FAILURES:
        print("test_more_like_this: %d check(s) failed" % len(W.FAILURES))
        sys.exit(1)
    print("test_more_like_this: all checks passed")


if __name__ == "__main__":
    main()
