#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 20, Focused Title as Backdrop (the Home hero), written
from the spec alone: the settings row with its help, preview and strings, the
art picker, the detail table, the helper's per record lookup and its cache,
the switch watcher, the static list slots, and the XML off state.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the rig of stubbed labels, builtins and
library calls come from tests/test_watchlist.py (built on tests/test_lists_api.py),
which imports the real service.py against them. No network is touched: the
library reply is a mock. The XML off state is proved by reading the skin's own
expressions and visible conditions, with the switch false and every other
condition tried both ways. Exits non zero when a test fails.

Usage:
    python3 tests/test_home_hero_spec.py
</remarks>
"""

import collections
import itertools
import os
import random
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_watchlist as W  # noqa: E402  (installs the Kodi stubs, imports service)

T = W.T
service = W.service
XML = W.XML
SKIN = W.SKIN
EXPRESSIONS = W.EXPRESSIONS

POPUP_ROWS = {"9201", "9203", "9205", "9221", "9223", "9231", "9233", "9235"}
HOME_ROWS = {str(n) for n in list(range(9252, 9258)) + list(range(9262, 9268))}


def parse(name):
    """
    <summary>Parses one file of the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>The XML root.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def art_for(dbid):
    """
    <summary>The art the mocked library holds for a record.</summary>
    <param name="dbid">The library id.</param>
    <returns>A dict with fanart and clearlogo named after the id.</returns>
    """
    return {"fanart": "fanart_%d.jpg" % dbid, "clearlogo": "logo_%d.png" % dbid}


class HeroRig(W.Rig):
    """
    <summary>The shared rig, with a library that answers art requests and
    counts the calls it gets.</summary>
    """

    def __init__(self):
        """<summary>Install the stubs and an empty art call record.</summary>"""
        self.fail_replies = False
        super().__init__()

    def jsonrpc(self, method, params=None):
        """
        <summary>Answer a library call, recording it. An art request gets art
        named after the id; with fail_replies set it gets a reply without a result.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        params = params or {}
        if params.get("properties") == ["art"]:
            self.rpc.append((method, params))
            if self.fail_replies == "silent":
                return {}
            if self.fail_replies:
                return {"error": {"code": -1}}
            dbid = [v for k, v in params.items() if k != "properties"][0]
            keymap = {"VideoLibrary.GetMovieDetails": "moviedetails",
                      "VideoLibrary.GetEpisodeDetails": "episodedetails",
                      "VideoLibrary.GetTVShowDetails": "tvshowdetails",
                      "VideoLibrary.GetSeasonDetails": "seasondetails"}
            return {"result": {keymap[method]: {"art": art_for(dbid)}}}
        return super().jsonrpc(method, params)

    def art_calls(self):
        """
        <summary>The art requests made so far.</summary>
        <returns>A list of (method, params).</returns>
        """
        return [(m, p) for m, p in self.rpc if p.get("properties") == ["art"]]


def new_helper():
    """
    <summary>A helper with no lists loaded.</summary>
    <returns>A FunctionalHelper.</returns>
    """
    return W.helper_with([])


def record(dbtype="movie", dbid=7):
    """
    <summary>One list record.</summary>
    <param name="dbtype">The library type.</param>
    <param name="dbid">The library id.</param>
    <returns>A dict.</returns>
    """
    return W.item("Title %d" % dbid, dbtype, dbid)


def tick(helper, rig):
    """
    <summary>Moves the clock on and runs the Home rows and the Watchlist passes.</summary>
    <param name="helper">The helper.</param>
    <param name="rig">The rig whose clock moves.</param>
    """
    rig.clock.now += 11
    helper.update_widgets()
    helper.update_watchlist()


def condition_atoms(text):
    """
    <summary>Splits a fully expanded Kodi condition into a Python expression
    over numbered atoms.</summary>
    <param name="text">The expanded condition.</param>
    <returns>(python expression text, list of atom texts).</returns>
    """
    atoms, out = [], []
    for tok in re.split(r"([\[\]+|!])", text):
        tok = tok.strip()
        if not tok:
            continue
        if tok == "[":
            out.append("(")
        elif tok == "]":
            out.append(")")
        elif tok == "+":
            out.append(" and ")
        elif tok == "|":
            out.append(" or ")
        elif tok == "!":
            out.append(" not ")
        else:
            if tok not in atoms:
                atoms.append(tok)
            out.append("v[%d]" % atoms.index(tok))
    return "".join(out), atoms


def can_show_with_switch_off(visibles):
    """
    <summary>Whether a control's visible conditions, all of which must hold,
    can be true with Skin.HasSetting(home_hero) false.</summary>
    <param name="visibles">The raw condition texts of one control.</param>
    <returns>True when some state of every other condition makes it visible.</returns>
    """
    params = collections.defaultdict(lambda: "p")
    combined = " + ".join("[" + W.expand(v, params) + "]" for v in visibles)
    expr, atoms = condition_atoms(combined)
    code = compile(expr, "<condition>", "eval")
    fixed = {i: False for i, a in enumerate(atoms) if a == "Skin.HasSetting(home_hero)"}
    free = [i for i in range(len(atoms)) if i not in fixed]
    if len(free) <= 14:
        combos = itertools.product([False, True], repeat=len(free))
    else:
        rng = random.Random(20)
        combos = (tuple(rng.random() < 0.5 for _ in free) for _ in range(4000))
    for combo in combos:
        v = [False] * len(atoms)
        for i, val in fixed.items():
            v[i] = val
        for i, val in zip(free, combo):
            v[i] = val
        if eval(code, {"__builtins__": {}}, {"v": v}):  # noqa: S307 (own generated text)
            return True
    return False


class SettingsRowSpec(unittest.TestCase):
    """<summary>Requirement 1: the setting, its row, help, preview and strings.</summary>"""

    def test_row_is_a_radiobutton_on_the_home_screen_list(self):
        """<summary>Row 7189 is a radiobutton inside grouplist 7020 with label 31942 and the toggle onclick.</summary>"""
        root = parse("SkinSettings.xml")
        parents = {c: p for p in root.iter() for c in p}
        rows = [c for c in root.iter("control") if c.get("id") == "7189"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label").strip(), "31942")
        self.assertEqual(row.findtext("onclick").strip(), "Skin.ToggleSetting(home_hero)")
        node, inside = row, False
        while node in parents:
            node = parents[node]
            if node.tag == "control" and node.get("id") == "7020" and node.get("type") == "grouplist":
                inside = True
        self.assertTrue(inside, "7189 should sit inside grouplist 7020")

    def test_selected_state_reads_the_setting(self):
        """<summary>The row shows the state of Skin.HasSetting(home_hero).</summary>"""
        root = parse("SkinSettings.xml")
        row = [c for c in root.iter("control") if c.get("id") == "7189"][0]
        self.assertEqual(row.findtext("selected").strip(), "Skin.HasSetting(home_hero)")

    def test_setting_is_never_defaulted_on(self):
        """<summary>Nothing in the skin's XML or add-on files turns home_hero on by default.</summary>"""
        pattern = re.compile(r"(SetBool\(home_hero|home_hero[^\n]{0,80}default[^\n]{0,20}true|default[^\n]{0,40}home_hero)", re.I)
        found = []
        for base, _dirs, files in os.walk(SKIN):
            for name in files:
                if name.endswith((".xml", ".po")):
                    path = os.path.join(base, name)
                    with open(path, encoding="utf-8") as fh:
                        for n, line in enumerate(fh, 1):
                            if pattern.search(line):
                                found.append("%s:%d" % (path, n))
        self.assertEqual(found, [])

    def test_help_line_is_string_31943_and_shown_for_the_row(self):
        """<summary>The help text for 7189 is 31943, and 7189 is in settings_help_shown.</summary>"""
        root = parse("Includes_SettingsHelp.xml")
        hit = [(v.get("condition"), (v.text or "").strip()) for v in root.iter("value")
               if v.get("condition") == "Control.HasFocus(7189)"]
        self.assertEqual(hit, [("Control.HasFocus(7189)", "$LOCALIZE[31943]")])
        self.assertIn("Control.HasFocus(7189)", EXPRESSIONS["settings_help_shown"])

    def test_preview_form_is_none(self):
        """<summary>7189 is in settings_preview_none.</summary>"""
        self.assertIn("Control.HasFocus(7189)", EXPRESSIONS["settings_preview_none"])

    def test_strings_exist(self):
        """<summary>Strings 31942 and 31943 exist and are not empty.</summary>"""
        for sid in (31942, 31943):
            self.assertTrue(T.STRINGS.get(sid), "string %d missing" % sid)


class HeroArtSpec(unittest.TestCase):
    """<summary>Requirement 2: service.hero_art.</summary>"""

    def test_fanart_wins_over_show_fanart(self):
        """<summary>art["fanart"] is preferred to art["tvshow.fanart"].</summary>"""
        self.assertEqual(service.hero_art({"fanart": "a", "tvshow.fanart": "b"})[0], "a")

    def test_falls_back_to_show_fanart(self):
        """<summary>Without fanart, tvshow.fanart is used.</summary>"""
        self.assertEqual(service.hero_art({"tvshow.fanart": "b"})[0], "b")

    def test_empty_fanart_falls_back(self):
        """<summary>An empty fanart string counts as missing.</summary>"""
        self.assertEqual(service.hero_art({"fanart": "", "tvshow.fanart": "b"})[0], "b")

    def test_logo_wins_over_show_logo(self):
        """<summary>clearlogo is preferred to tvshow.clearlogo.</summary>"""
        self.assertEqual(service.hero_art({"clearlogo": "x", "tvshow.clearlogo": "y"})[1], "x")

    def test_falls_back_to_show_logo(self):
        """<summary>Without clearlogo, tvshow.clearlogo is used.</summary>"""
        self.assertEqual(service.hero_art({"tvshow.clearlogo": "y"})[1], "y")

    def test_both_together(self):
        """<summary>Fanart and logo are picked independently into a pair.</summary>"""
        self.assertEqual(service.hero_art({"fanart": "f", "tvshow.clearlogo": "y"}), ("f", "y"))

    def test_none_and_empty_give_empty_pair(self):
        """<summary>None, an empty dict and a dict of unrelated keys give two empty strings.</summary>"""
        self.assertEqual(service.hero_art(None), ("", ""))
        self.assertEqual(service.hero_art({}), ("", ""))
        self.assertEqual(service.hero_art({"poster": "p"}), ("", ""))


class HeroDetailsSpec(unittest.TestCase):
    """<summary>Requirement 3: service.HERO_DETAILS.</summary>"""

    def test_table_maps_the_four_types(self):
        """<summary>movie, episode, tvshow and season map to method, id key and result key.</summary>"""
        self.assertEqual(service.HERO_DETAILS["movie"],
                         ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"))
        self.assertEqual(service.HERO_DETAILS["episode"],
                         ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"))
        self.assertEqual(service.HERO_DETAILS["tvshow"],
                         ("VideoLibrary.GetTVShowDetails", "tvshowid", "tvshowdetails"))
        self.assertEqual(service.HERO_DETAILS["season"],
                         ("VideoLibrary.GetSeasonDetails", "seasonid", "seasondetails"))

    def test_table_holds_only_those_types(self):
        """<summary>No other type is in the table.</summary>"""
        self.assertEqual(set(service.HERO_DETAILS), {"movie", "episode", "tvshow", "season"})


class RecordHeroSpec(unittest.TestCase):
    """<summary>Requirement 4: FunctionalHelper._record_hero and its store.</summary>"""

    def setUp(self):
        """<summary>Install the rig and a helper with the switch on.</summary>"""
        self.rig = HeroRig()
        self.helper = new_helper()
        self.helper._hero_shown = True

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def test_off_returns_empty_without_a_call(self):
        """<summary>With the switch off nothing is asked of the library.</summary>"""
        self.helper._hero_shown = False
        self.assertEqual(self.helper._record_hero(record("movie", 7)), ("", ""))
        self.assertEqual(self.rig.art_calls(), [])

    def test_unknown_type_returns_empty(self):
        """<summary>A type outside HERO_DETAILS gives empty strings and no call.</summary>"""
        self.assertEqual(self.helper._record_hero(record("musicvideo", 7)), ("", ""))
        self.assertEqual(self.helper._record_hero(record("", 7)), ("", ""))
        self.assertEqual(self.rig.art_calls(), [])

    def test_zero_id_returns_empty(self):
        """<summary>A dbid of 0 gives empty strings and no call.</summary>"""
        self.assertEqual(self.helper._record_hero(record("movie", 0)), ("", ""))
        self.assertEqual(self.rig.art_calls(), [])

    def test_one_call_with_the_right_shape(self):
        """<summary>A movie makes one call to the movie method asking only for art.</summary>"""
        got = self.helper._record_hero(record("movie", 7))
        self.assertEqual(got, ("fanart_7.jpg", "logo_7.png"))
        self.assertEqual(self.rig.art_calls(),
                         [("VideoLibrary.GetMovieDetails", {"movieid": 7, "properties": ["art"]})])

    def test_each_type_uses_its_own_method_and_key(self):
        """<summary>Episode, tvshow and season requests use their table entries.</summary>"""
        for dbtype in ("episode", "tvshow", "season"):
            method, idkey, _res = service.HERO_DETAILS[dbtype]
            self.helper._record_hero(record(dbtype, 3))
            self.assertIn((method, {idkey: 3, "properties": ["art"]}), self.rig.art_calls())

    def test_second_call_is_kept(self):
        """<summary>The same record again makes no further call and gives the same pair.</summary>"""
        first = self.helper._record_hero(record("movie", 7))
        second = self.helper._record_hero(record("movie", 7))
        self.assertEqual(first, second)
        self.assertEqual(len(self.rig.art_calls()), 1)

    def test_same_id_other_type_is_a_separate_entry(self):
        """<summary>The store is keyed by type and id, so a movie 7 and an episode 7 each ask once.</summary>"""
        self.helper._record_hero(record("movie", 7))
        self.helper._record_hero(record("episode", 7))
        self.assertEqual(len(self.rig.art_calls()), 2)

    def test_error_reply_is_kept_as_empty(self):
        """<summary>HOME-HERO-FIX: an error answer (no such entry) gives empty strings and is not asked again.</summary>"""
        self.rig.fail_replies = True
        self.assertEqual(self.helper._record_hero(record("movie", 7)), ("", ""))
        self.rig.fail_replies = False
        self.assertEqual(self.helper._record_hero(record("movie", 7)), ("", ""))
        self.assertEqual(len(self.rig.art_calls()), 1)

    def test_failed_reply_is_not_kept(self):
        """<summary>A call that gets no answer gives empty strings and the next call tries again.</summary>"""
        self.rig.fail_replies = "silent"
        self.assertEqual(self.helper._record_hero(record("movie", 7)), ("", ""))
        self.assertEqual(len(self.rig.art_calls()), 1)
        self.rig.fail_replies = False
        self.assertEqual(self.helper._record_hero(record("movie", 7)), ("fanart_7.jpg", "logo_7.png"))
        self.assertEqual(len(self.rig.art_calls()), 2)

    def test_store_empties_at_the_limit(self):
        """<summary>At HERO_CACHE_MAX entries the store is emptied before the new one is added.</summary>"""
        limit = self.helper.HERO_CACHE_MAX
        self.assertGreater(limit, 0)
        for n in range(1, limit + 1):
            self.helper._record_hero(record("movie", n))
        self.assertEqual(len(self.helper._hero_art), limit)
        self.helper._record_hero(record("movie", limit + 1))
        self.assertEqual(len(self.helper._hero_art), 1)


class UpdateHeroSpec(unittest.TestCase):
    """<summary>Requirement 5: FunctionalHelper.update_hero.</summary>"""

    def setUp(self):
        """<summary>Install the rig and a helper, switch off.</summary>"""
        self.rig = HeroRig()
        self.helper = new_helper()

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def test_turning_on_stores_and_resets_both_times(self):
        """<summary>A change to on is stored and both republish times go to 0.0.</summary>"""
        self.helper._watch_last = 5.0
        self.helper._widget_last = 6.0
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        self.assertTrue(self.helper._hero_shown)
        self.assertEqual(self.helper._watch_last, 0.0)
        self.assertEqual(self.helper._widget_last, 0.0)

    def test_unchanged_does_nothing(self):
        """<summary>With the value unchanged, in either state, the times are left alone.</summary>"""
        # The first pass settles the starting value, which a new helper holds as None.
        self.helper.update_hero()
        self.helper._watch_last = 5.0
        self.helper._widget_last = 6.0
        self.helper.update_hero()
        self.assertEqual((self.helper._watch_last, self.helper._widget_last), (5.0, 6.0))
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        self.helper._watch_last = 7.0
        self.helper._widget_last = 8.0
        self.helper.update_hero()
        self.assertEqual((self.helper._watch_last, self.helper._widget_last), (7.0, 8.0))

    def test_turning_off_empties_the_store_and_resets_times(self):
        """<summary>A change to off empties the art store and sets both times to 0.0.</summary>"""
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        self.helper._record_hero(record("movie", 7))
        self.assertTrue(self.helper._hero_art)
        self.helper._watch_last = 5.0
        self.helper._widget_last = 6.0
        T.SKIN_SETTINGS.discard("home_hero")
        self.helper.update_hero()
        self.assertFalse(self.helper._hero_shown)
        self.assertEqual(len(self.helper._hero_art), 0)
        self.assertEqual((self.helper._watch_last, self.helper._widget_last), (0.0, 0.0))


class StaticSlotSpec(unittest.TestCase):
    """<summary>Requirement 6: the Home row and Watchlist art properties."""

    def setUp(self):
        """<summary>Install the rig and a helper holding one list of three movies, shown by Home row 1 and the Watchlist.</summary>"""
        self.rig = HeroRig()
        items = [record("movie", 11), record("movie", 12), record("movie", 13)]
        self.helper = W.helper_with([{"name": "Weekend", "items": items}])
        self.rig.set_skin("widget1", "list")
        self.rig.set_skin("widget1_list", "Weekend")
        self.rig.set_skin("watchlist_source", "list")
        self.rig.set_skin("watchlist_list", "Weekend")

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def test_on_publishes_fanart_and_logo(self):
        """<summary>With the switch on both surfaces publish fanart and logo for each slot.</summary>"""
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        tick(self.helper, self.rig)
        for slot, dbid in ((1, 11), (2, 12), (3, 13)):
            self.assertEqual(T.PROPS.get("Widget.1.%d.Fanart" % slot), "fanart_%d.jpg" % dbid)
            self.assertEqual(T.PROPS.get("Widget.1.%d.Logo" % slot), "logo_%d.png" % dbid)
            self.assertEqual(T.PROPS.get("Watchlist.%d.Fanart" % slot), "fanart_%d.jpg" % dbid)
            self.assertEqual(T.PROPS.get("Watchlist.%d.Logo" % slot), "logo_%d.png" % dbid)

    def test_slots_beyond_the_items_are_cleared(self):
        """<summary>After the list shrinks the unused slots publish nothing.</summary>"""
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        tick(self.helper, self.rig)
        del self.helper._lists[0]["items"][1:]
        tick(self.helper, self.rig)
        for slot in (2, 3):
            for key in ("Widget.1.%d.Fanart", "Widget.1.%d.Logo", "Watchlist.%d.Fanart", "Watchlist.%d.Logo"):
                self.assertFalse(T.PROPS.get(key % slot), key % slot)
        self.assertEqual(T.PROPS.get("Widget.1.1.Fanart"), "fanart_11.jpg")

    def test_off_publishes_empty_values(self):
        """<summary>With the switch off every art property is empty and no art request is made.</summary>"""
        tick(self.helper, self.rig)
        self.assertTrue(T.PROPS.get("Widget.1.1.Label"), "the row itself should still publish")
        for slot in (1, 2, 3):
            for key in ("Widget.1.%d.Fanart", "Widget.1.%d.Logo", "Watchlist.%d.Fanart", "Watchlist.%d.Logo"):
                self.assertEqual(T.PROPS.get(key % slot, ""), "", key % slot)
        self.assertEqual(self.rig.art_calls(), [])

    def test_turning_off_blanks_published_art(self):
        """<summary>After the switch goes off and the rows republish, the art is blank again.</summary>"""
        T.SKIN_SETTINGS.add("home_hero")
        self.helper.update_hero()
        tick(self.helper, self.rig)
        self.assertTrue(T.PROPS.get("Widget.1.1.Fanart"))
        T.SKIN_SETTINGS.discard("home_hero")
        self.helper.update_hero()
        tick(self.helper, self.rig)
        self.assertEqual(T.PROPS.get("Widget.1.1.Fanart", ""), "")
        self.assertEqual(T.PROPS.get("Watchlist.1.Logo", ""), "")


class XmlOffStateSpec(unittest.TestCase):
    """<summary>Requirements 7 and 8: the XML gating and the row ids."""

    def test_focus_expressions_need_the_setting(self):
        """<summary>hero_popup_focus and hero_rows_focus each contain Skin.HasSetting(home_hero), as a required term.</summary>"""
        for name in ("hero_popup_focus", "hero_rows_focus"):
            self.assertIn("Skin.HasSetting(home_hero)", EXPRESSIONS[name])
            self.assertTrue(EXPRESSIONS[name].lstrip().startswith("Skin.HasSetting(home_hero) +"),
                            name + " should require the setting before anything else")

    def test_hero_showing_is_built_from_them(self):
        """<summary>hero_showing refers to both focus expressions.</summary>"""
        self.assertIn("$EXP[hero_popup_focus]", EXPRESSIONS["hero_showing"])
        self.assertIn("$EXP[hero_rows_focus]", EXPRESSIONS["hero_showing"])

    def test_hero_showing_is_false_with_the_setting_off(self):
        """<summary>No state of the other conditions makes hero_showing true while the setting is off.</summary>"""
        self.assertFalse(can_show_with_switch_off(["$EXP[hero_showing]"]))

    def test_row_id_sets(self):
        """<summary>hero_popup_focus names exactly the pop up rows and hero_rows_focus exactly the Home rows.</summary>"""
        popup = set(re.findall(r"Control\.HasFocus\((\d+)\)", EXPRESSIONS["hero_popup_focus"]))
        rows = set(re.findall(r"Control\.HasFocus\((\d+)\)", EXPRESSIONS["hero_rows_focus"]))
        self.assertEqual(popup, POPUP_ROWS)
        self.assertEqual(rows, HOME_ROWS)

    def test_every_hero_control_is_hidden_when_off(self):
        """<summary>Every control whose visible condition mentions a hero expression needs the setting on, except the dim overlay, which only adds to its own condition.</summary>"""
        names = ("hero_showing", "hero_popup_focus", "hero_rows_focus")
        gated, exempt = [], []
        for fname in sorted(os.listdir(XML)):
            if not fname.endswith(".xml"):
                continue
            root = parse(fname)
            for ctrl in root.iter("control"):
                visibles = [(v.text or "").strip() for v in ctrl.findall("visible")]
                if not any(n in v for v in visibles for n in names):
                    continue
                joined = " ".join(visibles)
                # HOME-HERO-FIX: only the dim adds the hero to its own
                # condition now; the caption fades by animation instead.
                if "| [$EXP[hero_showing] + !$EXP[bg_video_showing]]" in joined:
                    exempt.append((fname, ctrl.get("id") or ctrl.get("type")))
                    continue
                gated.append((fname, ctrl.get("id") or ctrl.get("type")))
                self.assertFalse(can_show_with_switch_off(visibles),
                                 "%s control %s could show with the setting off" % (fname, ctrl.get("id")))
        self.assertGreaterEqual(len(gated), 3, "expected the backdrop, the logo and the focus layers")
        self.assertEqual(len(exempt), 1, "expected exactly the dim overlay: %r" % exempt)


if __name__ == "__main__":
    unittest.main(verbosity=1)
