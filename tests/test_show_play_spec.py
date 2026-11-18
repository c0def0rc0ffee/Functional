#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 32, Play Choices for Shows, written from the spec alone:
the settings row with its help, preview and strings, the hold menu button and
its navigation, the SHOW_PLAY_CHOICES constant, show_start_index for every mode,
the show_command channel, and the pick dialog with its episode lookup and playlist calls.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the rig of stubbed labels, builtins and
library calls come from tests/test_watchlist.py (built on tests/test_lists_api.py),
which imports the real service.py against them. Dialogs and JSON-RPC are mocks,
so no network is touched. The XML is read only for the controls and names the
spec gives by id. Exits non zero when a test fails.

Usage:
    python3 tests/test_show_play_spec.py
</remarks>
"""

import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_watchlist as W  # noqa: E402  (installs the Kodi stubs, imports service)

T = W.T
service = W.service
XML = W.XML

def parse(name):
    """
    <summary>Parses one file of the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>The XML root.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def read(name):
    """
    <summary>Reads one file of the skin's xml folder as text.</summary>
    <param name="name">The file name.</param>
    <returns>The text.</returns>
    """
    with open(os.path.join(XML, name), encoding="utf-8") as handle:
        return handle.read()


def control(root, cid):
    """
    <summary>The first control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element or None.</returns>
    """
    return next((c for c in root.iter("control") if c.get("id") == cid), None)


def ep_row(episodeid, season, episode, playcount):
    """
    <summary>One episode as the library returns it.</summary>
    <param name="episodeid">The episode id, or None to leave it out.</param>
    <param name="season">The season.</param>
    <param name="episode">The episode number.</param>
    <param name="playcount">The play count.</param>
    <returns>A dict.</returns>
    """
    row = {"season": season, "episode": episode, "playcount": playcount}
    if episodeid is not None:
        row["episodeid"] = episodeid
    return row


def ep(season, episode, playcount=0):
    """
    <summary>One queued episode record.</summary>
    <param name="season">The season, 0 for a special.</param>
    <param name="episode">The episode number.</param>
    <param name="playcount">The play count.</param>
    <returns>A dict.</returns>
    """
    return {"season": season, "episode": episode, "playcount": playcount}


class ShowRig(W.Rig):
    """
    <summary>The shared rig, with a library that answers VideoLibrary.GetEpisodes from
    a list the test sets and can fail Playlist.Add.</summary>
    """

    def __init__(self):
        """<summary>Install the stubs and an empty queue reply.</summary>"""
        self.episodes = []
        self.add_reply = None
        self.headings = []
        super().__init__()

    def select(self, heading=None, items=None, *_a, **_kw):
        """
        <summary>Record the heading and offered lines, answer with self.pick.</summary>
        <param name="heading">The dialog title.</param>
        <param name="items">The lines offered.</param>
        <returns>The chosen index.</returns>
        """
        self.headings.append(heading)
        self.picked_from = list(items or [])
        return self.pick

    def jsonrpc(self, method, params=None):
        """
        <summary>Record a call and the episode lookup and a failing Add.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        if method == "VideoLibrary.GetEpisodes":
            self.rpc.append((method, params or {}))
            return {"result": {"episodes": list(self.episodes)}}
        if method == "Playlist.Add" and self.add_reply is not None:
            self.rpc.append((method, params or {}))
            return self.add_reply
        return super().jsonrpc(method, params)

    def methods(self):
        """
        <summary>The JSON-RPC method names called so far.</summary>
        <returns>A list of names in call order.</returns>
        """
        return [m for m, _p in self.rpc]

    def params_of(self, method):
        """
        <summary>The parameters of the first call to a method.</summary>
        <param name="method">JSON-RPC method.</param>
        <returns>The dict, or None when never called.</returns>
        """
        return next((p for m, p in self.rpc if m == method), None)


def new_helper():
    """
    <summary>A helper with no lists loaded.</summary>
    <returns>A FunctionalHelper.</returns>
    """
    return W.helper_with([])


class SettingsRowTests(unittest.TestCase):
    """<summary>Spec point 1: the setting, its row, help, preview and strings.</summary>"""

    def test_row_7216_follows_7215_in_grouplist_7021(self):
        """<summary>Radiobutton 7216 sits in grouplist 7021 straight after 7215.</summary>"""
        root = parse("SkinSettings.xml")
        group = control(root, "7021")
        self.assertIsNotNone(group, "grouplist 7021 should exist")
        ids = [c.get("id") for c in group.iter("control") if c.get("id")]
        self.assertIn("7215", ids)
        self.assertIn("7216", ids)
        self.assertEqual(ids.index("7216"), ids.index("7215") + 1)
        self.assertEqual(control(group, "7216").get("type"), "radiobutton")

    def test_row_7216_label_selected_and_onclick(self):
        """<summary>7216 is labelled 31955, selected by the setting and toggles it.</summary>"""
        row = control(parse("SkinSettings.xml"), "7216")
        self.assertIsNotNone(row)
        self.assertEqual(row.findtext("label"), "31955")
        self.assertEqual(row.findtext("selected"), "Skin.HasSetting(show_play_menu)")
        self.assertEqual(row.findtext("onclick"), "Skin.ToggleSetting(show_play_menu)")

    def test_help_text_for_7216(self):
        """<summary>Help string 31963 is given for focus on 7216.</summary>"""
        text = read("Includes_SettingsHelp.xml")
        self.assertRegex(text, r'Control\.HasFocus\(7216\)"\s*>\s*\$LOCALIZE\[31963\]')

    def test_7216_in_settings_help_shown(self):
        """<summary>7216 is in the settings_help_shown expression.</summary>"""
        root = parse("Includes_SettingsHelp.xml")
        shown = next((e.text or "" for e in root.iter("expression") if e.get("name") == "settings_help_shown"), "")
        self.assertIn("Control.HasFocus(7216)", shown)

    def test_7216_in_settings_preview_none(self):
        """<summary>7216 is in the settings_preview_none expression.</summary>"""
        root = parse("Includes_SettingsPreview.xml")
        none = next((e.text or "" for e in root.iter("expression") if e.get("name") == "settings_preview_none"), "")
        self.assertIn("Control.HasFocus(7216)", none)

    def test_strings_31955_to_31963_exist(self):
        """<summary>Every string from 31955 to 31963 exists and is not empty.</summary>"""
        for sid in list(range(31955, 31964)) + [31975, 31976]:
            self.assertTrue(T.STRINGS.get(sid), "string %d should exist and have text" % sid)

    def test_last_row_7316_goes_up_to_the_last_library_row(self):
        """<summary>Control 7316 in SkinSettings.xml goes up to the last row of grouplist 7021, which follows 7216 (later items add rows after it).</summary>"""
        root = parse("SkinSettings.xml")
        row = control(root, "7316")
        self.assertIsNotNone(row)
        ids = [c.get("id") for c in control(root, "7021").findall("control")]
        self.assertIn("7216", ids)
        self.assertEqual([e.text for e in row.findall("onup")], [ids[-1]])


class HoldMenuTests(unittest.TestCase):
    """<summary>Spec point 2: the hold menu button 953 and its neighbours.</summary>"""

    @classmethod
    def setUpClass(cls):
        """<summary>Parse the include and the dialog once.</summary>"""
        includes = parse("Includes.xml")
        cls.include = next(i for i in includes.iter("include") if i.get("name") == "ShowPlayContextButton")
        cls.button = next(c for c in cls.include.iter("control") if c.get("type") == "button")
        cls.dialog = parse("DialogContextMenu.xml")

    def test_button_label_is_31956(self):
        """<summary>The button is labelled 31956.</summary>"""
        self.assertEqual(self.button.findtext("label"), "31956")

    def test_button_id_comes_from_the_param_and_dialog_passes_953(self):
        """<summary>The button takes its id from the include param, which the dialog sets to 953.</summary>"""
        self.assertEqual(self.button.get("id"), "$PARAM[id]")
        use = next((i for i in self.dialog.iter("include")
                    if i.get("content") == "ShowPlayContextButton"), None)
        self.assertIsNotNone(use, "DialogContextMenu should use the include")
        params = {p.get("name"): p.get("value") for p in use.findall("param")}
        self.assertEqual(params.get("id"), "953")
        self.assertEqual(params.get("onup"), "952")
        # HOLD-MENU-FOCUS: Down goes to Kodi's first entry, 1001, not to the
        # grouplist, which brought back the entry used last time.
        self.assertEqual(params.get("ondown"), "1001")

    def test_visible_condition_has_every_required_term(self):
        """<summary>Visibility needs the setting, the videos window, a tvshow, a positive DBID and not a parent folder.</summary>"""
        cond = self.button.findtext("visible") or ""
        terms = [t.strip() for t in cond.split("+")]
        for needed in ("Skin.HasSetting(show_play_menu)", "Window.IsActive(videos)",
                       "String.IsEqual(ListItem.DBTYPE,tvshow)", "Integer.IsGreater(ListItem.DBID,0)",
                       "!ListItem.IsParentFolder"):
            self.assertIn(needed, terms)

    def test_setting_false_means_button_cannot_show(self):
        """<summary>The setting is an and term and the condition has no or, so with it false 953 cannot show.</summary>"""
        cond = self.button.findtext("visible") or ""
        self.assertNotIn("|", cond)
        self.assertNotIn("[", cond)
        self.assertIn("Skin.HasSetting(show_play_menu)", [t.strip() for t in cond.split("+")])

    def test_onclick_lines_in_order(self):
        """<summary>The three onclick lines are the title property, the command, then Close.</summary>"""
        clicks = [e.text for e in self.button.findall("onclick")]
        self.assertEqual(clicks, ["SetProperty(show_play_title,$ESCINFO[ListItem.Label],10000)",
                                  "Skin.SetString(show_command,pick:$INFO[ListItem.DBID])",
                                  "Action(Close)"])

    def test_button_onup_and_ondown_come_from_params(self):
        """<summary>953's onup and ondown are the include params, set to 952 and 996.</summary>"""
        self.assertEqual(self.button.findtext("onup"), "$PARAM[onup]")
        self.assertEqual(self.button.findtext("ondown"), "$PARAM[ondown]")

    def test_952_ondown_is_953(self):
        """<summary>The Collection row 952 goes down to 953.</summary>"""
        use = next(i for i in self.dialog.iter("include")
                   if i.get("content") == "CollectionContextButton")
        params = {p.get("name"): p.get("value") for p in use.findall("param")}
        self.assertEqual(params.get("id"), "952")
        self.assertEqual(params.get("ondown"), "953")

    def test_grouplist_996_onup_is_953(self):
        """<summary>Grouplist 996 goes up to 953.</summary>"""
        group = control(self.dialog, "996")
        self.assertIn("953", [e.text for e in group.findall("onup")])

    def test_image_999_and_grouplist_996_slide_for_953(self):
        """<summary>Both slide down 60 for Control.IsVisible(953), as they do for 950, 951 and 952.</summary>"""
        for cid in ("999", "996"):
            node = control(self.dialog, cid)
            slides = {a.get("condition") for a in node.findall("animation")
                      if a.get("effect") == "slide" and a.get("end") == "0,60"}
            for shown in ("950", "951", "952", "953"):
                self.assertIn("Control.IsVisible(%s)" % shown, slides, "control %s, row %s" % (cid, shown))


class ConstantTests(unittest.TestCase):
    """<summary>Spec point 3: the choices constant.</summary>"""

    def test_show_play_choices(self):
        """<summary>SHOW_PLAY_CHOICES is the tuple next, first, queue.</summary>"""
        self.assertEqual(service.SHOW_PLAY_CHOICES, ("next", "first", "queue"))


class StartIndexTests(unittest.TestCase):
    """<summary>Spec point 4: show_start_index.</summary>"""

    def idx(self, items, mode):
        """
        <summary>Calls the function under test.</summary>
        <param name="items">The queue.</param>
        <param name="mode">first or next.</param>
        <returns>The index or None.</returns>
        """
        return service.show_start_index(items, mode)

    def test_empty_queue_gives_none(self):
        """<summary>No items gives None in both modes.</summary>"""
        self.assertIsNone(self.idx([], "first"))
        self.assertIsNone(self.idx([], "next"))

    def test_only_specials_gives_none(self):
        """<summary>A queue of specials, season 0 or no season, gives None in both modes.</summary>"""
        items = [ep(0, 1), {"episode": 2, "playcount": 0}]
        self.assertIsNone(self.idx(items, "first"))
        self.assertIsNone(self.idx(items, "next"))

    def test_first_is_first_regular_episode(self):
        """<summary>first returns the first regular episode, skipping specials.</summary>"""
        self.assertEqual(self.idx([ep(1, 1), ep(1, 2)], "first"), 0)
        self.assertEqual(self.idx([ep(0, 1), {"episode": 9, "playcount": 0}, ep(1, 1)], "first"), 2)

    def test_first_ignores_watched_state(self):
        """<summary>first returns the first regular episode even when watched.</summary>"""
        self.assertEqual(self.idx([ep(1, 1, 3), ep(1, 2, 0)], "first"), 0)

    def test_next_with_nothing_watched_is_first_regular(self):
        """<summary>next with no regular episode watched gives the first regular one.</summary>"""
        self.assertEqual(self.idx([ep(0, 1), ep(1, 1), ep(1, 2)], "next"), 1)

    def test_next_watched_special_does_not_count(self):
        """<summary>A watched special never counts, so next still gives the first regular episode.</summary>"""
        self.assertEqual(self.idx([ep(0, 1, 2), ep(1, 1), ep(1, 2)], "next"), 1)

    def test_next_is_first_after_last_watched(self):
        """<summary>next gives the first regular episode after the last watched regular one.</summary>"""
        self.assertEqual(self.idx([ep(1, 1, 1), ep(1, 2, 1), ep(1, 3), ep(1, 4)], "next"), 2)

    def test_next_after_last_watched_skips_gaps(self):
        """<summary>With a watched, unwatched, watched, unwatched pattern next follows the last watched one.</summary>"""
        items = [ep(1, 1, 1), ep(1, 2, 0), ep(1, 3, 1), ep(1, 4, 0)]
        self.assertEqual(self.idx(items, "next"), 3)

    def test_next_skips_specials_after_last_watched(self):
        """<summary>A special after the last watched episode is not chosen, the next regular one is.</summary>"""
        items = [ep(1, 1, 1), ep(0, 1, 0), ep(1, 2, 0)]
        self.assertEqual(self.idx(items, "next"), 2)

    def test_next_wraps_to_first_unwatched_when_none_follow(self):
        """<summary>When nothing regular follows the last watched, the first unwatched regular episode anywhere is used.</summary>"""
        self.assertEqual(self.idx([ep(1, 1), ep(1, 2), ep(1, 3, 1)], "next"), 0)
        self.assertEqual(self.idx([ep(1, 1, 1), ep(1, 2, 0), ep(1, 3, 1)], "next"), 1)

    def test_next_wrap_skips_a_leading_special(self):
        """<summary>The wrap round ignores specials and counts positions with them included.</summary>"""
        self.assertEqual(self.idx([ep(0, 1), ep(1, 1), ep(1, 2, 1)], "next"), 1)

    def test_next_all_watched_gives_none(self):
        """<summary>Every regular episode watched gives None, even with an unwatched special.</summary>"""
        self.assertIsNone(self.idx([ep(1, 1, 1), ep(1, 2, 2)], "next"))
        self.assertIsNone(self.idx([ep(0, 1, 0), ep(1, 1, 1), ep(1, 2, 2)], "next"))

    def test_indexes_count_specials_in_the_given_list(self):
        """<summary>Positions are in the given list, with specials counted.</summary>"""
        items = [ep(0, 1), ep(0, 2), ep(0, 3), ep(2, 1, 1), ep(2, 2)]
        self.assertEqual(self.idx(items, "first"), 3)
        self.assertEqual(self.idx(items, "next"), 4)


class CommandChannelTests(unittest.TestCase):
    """<summary>Spec point 5: update_show_command.</summary>"""

    def setUp(self):
        """<summary>Install the rig, a helper and a recorder for _show_play_pick.</summary>"""
        self.rig = ShowRig()
        self.helper = new_helper()
        self.calls = []
        self.helper._show_play_pick = lambda show_id, title: self.calls.append((show_id, title))

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def send(self, command, title="Invented Show"):
        """
        <summary>Set the command and title, then run the command pass.</summary>
        <param name="command">The show_command value.</param>
        <param name="title">The show_play_title property.</param>
        """
        T.PROPS["show_play_title"] = title
        self.rig.set_skin("show_command", command)
        self.helper.update_show_command()

    def test_pick_with_positive_id_starts_the_dialog(self):
        """<summary>pick:N with a positive N starts _show_play_pick with the id and the title property.</summary>"""
        self.send("pick:12", "Invented Show")
        self.assertEqual(self.calls, [(12, "Invented Show")])

    def test_pick_passes_an_integer_id(self):
        """<summary>The id reaches _show_play_pick as an int.</summary>"""
        self.send("pick:7")
        self.assertIsInstance(self.calls[0][0], int)

    def test_no_command_does_nothing(self):
        """<summary>An empty channel starts nothing.</summary>"""
        self.helper.update_show_command()
        self.assertEqual(self.calls, [])

    def test_other_commands_do_nothing(self):
        """<summary>Anything that is not pick:N starts nothing.</summary>"""
        for command in ("play", "pick", "pick:", "pick:abc", "pick:1.5", "queue:3", "PICK:4"):
            self.send(command)
        self.assertEqual(self.calls, [])

    def test_non_positive_id_does_nothing(self):
        """<summary>pick:0 and a negative id start nothing.</summary>"""
        self.send("pick:0")
        self.send("pick:-5")
        self.assertEqual(self.calls, [])


class PickDialogTests(unittest.TestCase):
    """<summary>Spec point 6: _show_play_pick, the episode lookup and the playlist calls.</summary>"""

    def setUp(self):
        """<summary>Install the rig and a helper.</summary>"""
        self.rig = ShowRig()
        self.helper = new_helper()

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def run_pick(self, choice, title="Invented Show", show_id=12, episodes=None):
        """
        <summary>Run the dialog with a chosen answer and a library reply.</summary>
        <param name="choice">The index the dialog returns.</param>
        <param name="title">The title passed in.</param>
        <param name="show_id">The library id passed in.</param>
        <param name="episodes">The episodes the library returns.</param>
        """
        self.rig.pick = choice
        self.rig.episodes = episodes if episodes is not None else []
        self.helper._show_play_pick(show_id, title)

    def toast_has(self, sid):
        """
        <summary>Whether a notification carried the text of a string.</summary>
        <param name="sid">The string id.</param>
        <returns>True when some toast argument holds the text.</returns>
        """
        text = T.STRINGS[sid]
        return any(text in str(part) for args in T._Dialog.toasts for part in args)

    def add_params(self, ids):
        """
        <summary>The Playlist.Add parameters the spec gives.</summary>
        <param name="ids">The episode ids in order.</param>
        <returns>The dict.</returns>
        """
        return {"playlistid": 1, "item": [{"episodeid": i} for i in ids]}

    def three(self):
        """
        <summary>Three regular episodes given out of order, plus a special and one with no id.</summary>
        <returns>The library list.</returns>
        """
        return [ep_row(9, 0, 1, 0), ep_row(32, 2, 1, 0), ep_row(31, 1, 2, 1),
                ep_row(30, 1, 1, 1), ep_row(None, 1, 3, 0)]

    def test_dialog_offers_three_choices_headed_by_the_title(self):
        """<summary>The select dialog has three lines and the show title as its heading.</summary>"""
        self.run_pick(-1, title="Invented Show")
        self.assertEqual(len(self.rig.picked_from), 3)
        self.assertEqual(self.rig.headings, ["Invented Show"])

    def test_empty_title_uses_string_31957(self):
        """<summary>With an empty title the heading is the text of string 31957.</summary>"""
        self.run_pick(-1, title="")
        self.assertEqual(self.rig.headings, [T.STRINGS[31957]])

    def test_cancel_makes_no_jsonrpc_call(self):
        """<summary>A cancelled dialog makes no JSON-RPC call at all.</summary>"""
        self.run_pick(-1, episodes=self.three())
        self.assertEqual(self.rig.rpc, [])

    def test_lookup_request_is_exact(self):
        """<summary>The first call is VideoLibrary.GetEpisodes with the show id, properties and ascending episode sort.</summary>"""
        self.run_pick(2, show_id=345, episodes=self.three())
        self.assertEqual(self.rig.rpc[0], ("VideoLibrary.GetEpisodes", {
            "tvshowid": 345, "properties": ["season", "episode", "playcount"],
            "sort": {"method": "episode", "order": "ascending"}}))

    def test_no_episodes_notifies_31975_and_stops(self):
        """<summary>With no usable episodes there is notification 31975 and no Playlist call, for every choice.</summary>"""
        for choice in (0, 1, 2):
            self.rig.rpc[:] = []
            T._Dialog.toasts = []
            self.run_pick(choice, episodes=[])
            self.assertEqual(self.rig.methods(), ["VideoLibrary.GetEpisodes"], "choice %d" % choice)
            self.assertTrue(self.toast_has(31975), "choice %d" % choice)

    def test_only_specials_or_idless_episodes_count_as_none(self):
        """<summary>Specials and episodes without an id are dropped, which can leave none.</summary>"""
        self.run_pick(2, episodes=[ep_row(9, 0, 1, 0), ep_row(None, 1, 1, 0)])
        self.assertEqual(self.rig.methods(), ["VideoLibrary.GetEpisodes"])
        self.assertTrue(self.toast_has(31975))

    def test_queue_adds_sorted_regular_episodes_only(self):
        """<summary>Choice 2 makes no Clear, one Add with the kept episodes sorted by season then episode, a 31961 notification and no Player.Open.</summary>"""
        self.run_pick(2, episodes=self.three())
        self.assertEqual(self.rig.methods(), ["VideoLibrary.GetEpisodes", "Playlist.Add"])
        self.assertEqual(self.rig.params_of("Playlist.Add"), self.add_params([30, 31, 32]))
        self.assertTrue(self.toast_has(31961))

    def test_next_calls_in_order_and_resumes(self):
        """<summary>Choice 0 clears, adds, then opens at the next episode's position with resume True.</summary>"""
        self.run_pick(0, episodes=self.three())
        self.assertEqual(self.rig.methods(),
                         ["VideoLibrary.GetEpisodes", "Playlist.Clear", "Playlist.Add", "Player.Open"])
        self.assertEqual(self.rig.params_of("Playlist.Clear"), {"playlistid": 1})
        self.assertEqual(self.rig.params_of("Playlist.Add"), self.add_params([30, 31, 32]))
        self.assertEqual(self.rig.params_of("Player.Open"),
                         {"item": {"playlistid": 1, "position": 2}, "options": {"resume": True}})

    def test_first_opens_at_the_start_without_resume(self):
        """<summary>Choice 1 opens at the first regular episode with resume False, even when it is watched.</summary>"""
        self.run_pick(1, episodes=self.three())
        self.assertEqual(self.rig.methods(),
                         ["VideoLibrary.GetEpisodes", "Playlist.Clear", "Playlist.Add", "Player.Open"])
        self.assertEqual(self.rig.params_of("Player.Open"),
                         {"item": {"playlistid": 1, "position": 0}, "options": {"resume": False}})

    def test_position_comes_from_show_start_index_on_the_kept_list(self):
        """<summary>The position equals show_start_index applied to the kept, sorted episodes.</summary>"""
        kept = [{"season": 1, "episode": 1, "playcount": 1}, {"season": 1, "episode": 2, "playcount": 1},
                {"season": 2, "episode": 1, "playcount": 0}]
        rows = [ep_row(5, 2, 1, 0), ep_row(3, 1, 2, 1), ep_row(2, 1, 1, 1)]
        self.run_pick(0, episodes=rows)
        self.assertEqual(self.rig.params_of("Player.Open")["item"]["position"],
                         service.show_start_index(kept, "next"))

    def test_next_with_everything_watched_notifies_31962_and_stops(self):
        """<summary>When next has no start index there is notification 31962 and no Playlist call.</summary>"""
        self.run_pick(0, episodes=[ep_row(1, 1, 1, 1), ep_row(2, 1, 2, 1)])
        self.assertEqual(self.rig.methods(), ["VideoLibrary.GetEpisodes"])
        self.assertTrue(self.toast_has(31962))

    def test_failed_add_notifies_31976_and_does_not_open(self):
        """<summary>A Playlist.Add reply whose result is not OK gives notification 31976 and no Player.Open, for every choice.</summary>"""
        for choice in (0, 1, 2):
            self.rig.rpc[:] = []
            T._Dialog.toasts = []
            self.rig.add_reply = {"error": {"code": -1}}
            self.run_pick(choice, episodes=self.three())
            self.assertNotIn("Player.Open", self.rig.methods(), "choice %d" % choice)
            self.assertTrue(self.toast_has(31976), "choice %d" % choice)
        self.rig.add_reply = None

    def test_strings_31975_and_31976_exist(self):
        """<summary>The two new strings exist with text.</summary>"""
        self.assertTrue(T.STRINGS.get(31975))
        self.assertTrue(T.STRINGS.get(31976))


if __name__ == "__main__":
    unittest.main()
