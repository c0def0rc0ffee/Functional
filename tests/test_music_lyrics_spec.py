#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 42, Lyrics on the Music Screen, written from the spec
alone: the settings row with its help, preview and strings, the command pass
update_lyrics_command, the install and settings offer _lyrics_offer, and the
lyrics window skin file the add-on drives.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_watchlist.py (built on tests/test_lists_api.py). Builtins, dialogs,
add-on settings, the wait for an install and JSON-RPC are all mocks, so no
network is touched. Exits non zero when a test fails.

Usage:
    python3 tests/test_music_lyrics_spec.py
</remarks>
"""

import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_home_hero_spec as H  # noqa: E402  (installs the Kodi stubs, imports service)

W = H.W
T = W.T
service = W.service
XML = W.XML
SKIN = W.SKIN
EXPRESSIONS = W.EXPRESSIONS

ADDON = "script.cu.lrclyrics"
ISLRC = "Window(home).Property(culrc.islrc)"
LYRICS = "Window(home).Property(culrc.lyrics)"
SAMPLE = "[00:10.00]First line\n[00:20.00]Second line\n[00:30.00]Third line\n"


def parse_xml(name):
    """
    <summary>Parses one file of the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>The XML root.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def find_row(root, cid):
    """
    <summary>The control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element, or None.</returns>
    """
    return next((c for c in root.iter("control") if c.get("id") == cid), None)


def condition_true(text, truth):
    """
    <summary>Evaluates a Kodi condition built from plus, bar, bang and brackets.</summary>
    <param name="text">The condition, with no references left in it.</param>
    <param name="truth">A function from one plain condition to True or False.</param>
    <returns>The value.</returns>
    """
    expr, atoms = H.condition_atoms(text)
    values = [truth(a) for a in atoms]
    return bool(eval(expr, {"__builtins__": {}}, {"v": values}))  # noqa: S307 (own generated text)


def skin_files_mentioning(number):
    """
    <summary>Lists the skin's text files that contain a number as a whole number.</summary>
    <param name="number">The number, for example a string id.</param>
    <returns>A list of paths.</returns>
    """
    needle = re.compile(r"(?<!\d)%d(?!\d)" % number)
    found = []
    for base, _dirs, files in os.walk(SKIN):
        for name in files:
            path = os.path.join(base, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if needle.search(text):
                found.append(path)
    return found


class Busy:
    """<summary>A dialog thread that is still running.</summary>"""

    def is_alive(self):
        """<summary>Still running.</summary><returns>True.</returns>"""
        return True


class LyricsRig(W.Rig):
    """
    <summary>The shared rig plus add-on conditions, add-on
    settings, a yes or no answer, and a record of dialogs.</summary>
    """

    def __init__(self):
        """<summary>Install the stubs and the starting state: nothing installed, no audio.</summary>"""
        super().__init__()
        self.installed = False
        self.enabled = False
        self.settings = {"service": False, "hide_dialog": False}
        self.set_calls = []
        self.answer = True
        self.yesno_calls = []
        self.select_calls = []
        self.addon_ids = []
        self.waits = 0
        self.arrive_after = None
        self.install_ran = False
        self.saved_extra = (T.xbmcaddon.Addon, getattr(T._Dialog, "yesno", None),
                            T.xbmc.getCondVisibility, T._Monitor.waitForAbort)
        T.xbmcaddon.Addon = self.addon
        T._Monitor.waitForAbort = self.wait_for_abort
        T._Dialog.yesno = self.yesno
        service.xbmc.getCondVisibility = self.cond
        service._COMMANDS_TAKEN.clear()
        service.xbmc.executebuiltin = self.builtin

    def restore(self):
        """<summary>Put every stub back, including the extras.</summary>"""
        T.xbmcaddon.Addon, T._Dialog.yesno, T.xbmc.getCondVisibility, T._Monitor.waitForAbort = self.saved_extra
        super().restore()

    def cond(self, text):
        """
        <summary>getCondVisibility for what the helper may ask, joined conditions included.</summary>
        <param name="text">The condition.</param>
        <returns>True when it holds in the rig's state.</returns>
        """
        def one(atom):
            """<summary>One plain condition.</summary><param name="atom">The text.</param><returns>The value.</returns>"""
            if atom == "System.HasAddon(%s)" % ADDON:
                return self.installed
            if atom == "System.AddonIsEnabled(%s)" % ADDON:
                return self.installed and self.enabled
            if atom == "Skin.HasSetting(music_lyrics)":
                # MUSIC-LYRICS-FIX: the switch as it stands after an install.
                return getattr(self, "switch_on", True)
            return W.Rig.cond(self, atom)
        return condition_true(text, one)

    def addon(self, addon_id=None, *_a):
        """
        <summary>xbmcaddon.Addon for the lyrics add-on, with settings the test controls.</summary>
        <param name="addon_id">The add-on id asked for.</param>
        <returns>An object with the setting calls and the strings call the service may make.</returns>
        """
        self.addon_ids.append(addon_id)
        rig = self

        class _A:
            """<summary>A stand in add-on.</summary>"""

            def getSettingBool(self, key):  # noqa: N802 (Kodi API)
                """<summary>A boolean setting.</summary><param name="key">Its id.</param><returns>The value.</returns>"""
                return rig.settings.get(key, False)

            def setSettingBool(self, key, value):  # noqa: N802 (Kodi API)
                """<summary>Records a write.</summary><param name="key">Its id.</param><param name="value">The value.</param><returns>True.</returns>"""
                rig.set_calls.append((key, value))
                rig.settings[key] = value
                return True

            def getLocalizedString(self, _sid):  # noqa: N802 (Kodi API)
                """<summary>No text.</summary><param name="_sid">Ignored.</param><returns>Empty text.</returns>"""
                return ""

            def getAddonInfo(self, _key):  # noqa: N802 (Kodi API)
                """<summary>No info.</summary><param name="_key">Ignored.</param><returns>Empty text.</returns>"""
                return ""

        return _A()

    def yesno(self, *args, **_kw):
        """
        <summary>Records the question and answers as the test says.</summary>
        <returns>The set answer.</returns>
        """
        self.yesno_calls.append(args)
        return self.answer

    def builtin(self, cmd, *_a):
        """
        <summary>Records a builtin, noting when the install starts.</summary>
        <param name="cmd">The builtin.</param>
        """
        if cmd == "InstallAddon(%s)" % ADDON:
            self.install_ran = True
        W.Rig.builtin(self, cmd, *_a)

    def wait_for_abort(self, timeout=None):
        """
        <summary>Counts a wait. Once the install has run and arrive_after waits have passed, the add-on appears, enabled.</summary>
        <param name="timeout">Seconds Kodi would wait; ignored.</param>
        <returns>False, as Kodi is never closing here.</returns>
        """
        self.waits += 1
        if self.install_ran and self.arrive_after is not None and self.waits >= self.arrive_after:
            self.installed, self.enabled = True, True
        return False

    def rpc_methods(self, method):
        """
        <summary>The JSON-RPC calls made to one method.</summary>
        <param name="method">The method name.</param>
        <returns>A list of parameter dicts.</returns>
        """
        return [p for m, p in self.rpc if m == method]


class SettingsRowSpec(unittest.TestCase):
    """<summary>Requirement 1: the setting, its row, help, preview and strings.</summary>"""

    def test_row_is_a_radiobutton_in_grouplist_7027(self):
        """<summary>7407 is a radiobutton with label 31945 inside grouplist 7027, reading the setting.</summary>"""
        root = parse_xml("SkinSettings.xml")
        parents = {c: p for p in root.iter() for c in p}
        rows = [c for c in root.iter("control") if c.get("id") == "7407"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label").strip(), "31945")
        self.assertEqual(row.findtext("selected").strip(), "Skin.HasSetting(music_lyrics)")
        node, inside = row, False
        while node in parents:
            node = parents[node]
            if node.tag == "control" and node.get("id") == "7027" and node.get("type") == "grouplist":
                inside = True
        self.assertTrue(inside, "7407 should sit inside grouplist 7027")

    def test_section_label_7068_precedes_the_row(self):
        """<summary>Label 7068 with string 31944 comes before 7407 in grouplist 7027.</summary>"""
        root = parse_xml("SkinSettings.xml")
        grouplist = find_row(root, "7027")
        self.assertIsNotNone(grouplist)
        ids = [c.get("id") for c in grouplist.iter("control")]
        self.assertIn("7068", ids)
        self.assertIn("7407", ids)
        self.assertLess(ids.index("7068"), ids.index("7407"))
        self.assertEqual(find_row(root, "7068").findtext("label").strip(), "31944")

    def test_onclick_lines_in_order(self):
        """<summary>The row runs the off command, the on command, then the toggle, in that order.</summary>"""
        row = find_row(parse_xml("SkinSettings.xml"), "7407")
        got = [(o.get("condition"), (o.text or "").strip()) for o in row.findall("onclick")]
        self.assertEqual(got, [
            ("Skin.HasSetting(music_lyrics)", "Skin.SetString(lyrics_command,off)"),
            ("!Skin.HasSetting(music_lyrics)", "Skin.SetString(lyrics_command,on)"),
            (None, "Skin.ToggleSetting(music_lyrics)"),
        ])

    def test_setting_is_never_defaulted_on(self):
        """<summary>Nothing in the skin's files switches music_lyrics on by default.</summary>"""
        pattern = re.compile(r"SetBool\(music_lyrics|music_lyrics[^\n]{0,80}default[^\n]{0,20}true|default[^\n]{0,40}music_lyrics", re.I)
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

    def test_help_line_is_31946_and_shown_for_the_row(self):
        """<summary>The help text for 7407 is 31946, and 7407 is in settings_help_shown.</summary>"""
        root = parse_xml("Includes_SettingsHelp.xml")
        hit = [(v.get("condition"), (v.text or "").strip()) for v in root.iter("value")
               if v.get("condition") == "Control.HasFocus(7407)"]
        self.assertEqual(hit, [("Control.HasFocus(7407)", "$LOCALIZE[31946]")])
        self.assertIn("Control.HasFocus(7407)", EXPRESSIONS["settings_help_shown"])

    def test_preview_form_is_none(self):
        """<summary>7407 is in settings_preview_none.</summary>"""
        self.assertIn("Control.HasFocus(7407)", EXPRESSIONS["settings_preview_none"])

    def test_label_31945_text(self):
        """<summary>String 31945 reads Lyrics on the Music Screen.</summary>"""
        self.assertEqual(T.STRINGS.get(31945), "Lyrics on the Music Screen")

    def test_string_31953_is_gone_everywhere(self):
        """<summary>Nothing in the skin folder mentions string 31953.</summary>"""
        self.assertEqual(skin_files_mentioning(31953), [])

    def test_strings_31944_to_31952_and_31954_exist(self):
        """<summary>Each of those strings is defined once and is not empty.</summary>"""
        path = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
        with open(path, encoding="utf-8") as fh:
            po = fh.read()
        for sid in list(range(31944, 31953)) + [31954]:
            self.assertTrue(T.STRINGS.get(sid), "string %d missing or empty" % sid)
            self.assertEqual(po.count('msgctxt "#%d"' % sid), 1, "string %d should be defined once" % sid)

    def test_string_31690_is_gone_everywhere(self):
        """<summary>Nothing in the skin folder mentions string 31690 any more.</summary>"""
        self.assertEqual(skin_files_mentioning(31690), [])

    def test_music_osd_has_no_lyric_reference(self):
        """<summary>MusicOSD.xml no longer mentions MusicLyric.</summary>"""
        with open(os.path.join(XML, "MusicOSD.xml"), encoding="utf-8") as fh:
            self.assertNotIn("MusicLyric", fh.read())


class CommandSpec(unittest.TestCase):
    """<summary>Requirement 2: FunctionalHelper.update_lyrics_command."""

    def setUp(self):
        """<summary>Install the rig and a helper whose dialog slot records what is spawned.</summary>"""
        self.rig = LyricsRig()
        self.helper = W.helper_with([])
        self.spawned = []
        self.helper._spawn_dialog = lambda worker: self.spawned.append(worker)
        self.offers = []
        self.helper._lyrics_offer = lambda on: self.offers.append(on)

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def send(self, value):
        """
        <summary>Sets lyrics_command and runs one pass.</summary>
        <param name="value">The command text.</param>
        """
        service._COMMANDS_TAKEN.clear()
        self.rig.set_skin("lyrics_command", value)
        self.helper.update_lyrics_command()

    def test_on_starts_the_offer_switched_on(self):
        """<summary>The command on spawns one worker that runs the offer with True.</summary>"""
        self.send("on")
        self.assertEqual(len(self.spawned), 1)
        self.spawned[0]()
        self.assertEqual(self.offers, [True])

    def test_off_starts_the_offer_switched_off(self):
        """<summary>The command off spawns one worker that runs the offer with False.</summary>"""
        self.send("off")
        self.assertEqual(len(self.spawned), 1)
        self.spawned[0]()
        self.assertEqual(self.offers, [False])

    def test_other_or_empty_commands_do_nothing(self):
        """<summary>An empty or unknown command spawns nothing.</summary>"""
        self.send("")
        self.send("something")
        self.assertEqual(self.spawned, [])

    def test_a_running_dialog_is_not_interrupted(self):
        """<summary>With a dialog thread already alive, no offer is started.</summary>"""
        self.helper._dialog_thread = Busy()
        self.send("on")
        self.assertEqual(self.spawned, [])


class OfferSpec(unittest.TestCase):
    """<summary>Requirement 3: FunctionalHelper._lyrics_offer."""

    def setUp(self):
        """<summary>Install the rig and a helper. Nothing is installed at first.</summary>"""
        self.rig = LyricsRig()
        self.helper = W.helper_with([])
        self.rig.builtins.clear()

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def toasts(self):
        """<summary>Notifications shown so far.</summary><returns>A list of argument tuples.</returns>"""
        return list(T._Dialog.toasts)

    def test_addon_id_constant(self):
        """<summary>The helper names the lyrics add-on script.cu.lrclyrics.</summary>"""
        self.assertEqual(self.helper.LYRICS_ADDON, ADDON)

    def test_on_not_installed_no_shows_a_notification_only(self):
        """<summary>A No shows a notification and runs no install, enable or settings change.</summary>"""
        self.rig.answer = False
        self.helper._lyrics_offer(True)
        self.assertEqual(len(self.rig.yesno_calls), 1)
        self.assertEqual(len(self.toasts()), 1)
        self.assertNotIn("InstallAddon(%s)" % ADDON, self.rig.builtins)
        self.assertEqual(self.rig.rpc_methods("Addons.SetAddonEnabled"), [])
        self.assertEqual(self.rig.set_calls, [])

    def test_on_not_installed_yes_installs_and_waits_for_it(self):
        """<summary>A Yes runs InstallAddon, waits for System.HasAddon, then goes on to the service question.</summary>"""
        self.rig.answer = True
        self.rig.arrive_after = 3
        self.helper._lyrics_offer(True)
        self.assertIn("InstallAddon(%s)" % ADDON, self.rig.builtins)
        self.assertGreaterEqual(self.rig.waits, 3)
        self.assertLess(self.rig.waits, 60)
        self.assertEqual(len(self.rig.yesno_calls), 2)
        self.assertEqual(self.rig.set_calls, [("service", True)])
        self.assertIn("RunScript(%s)" % ADDON, self.rig.builtins)

    def test_switched_off_during_the_install_stops_there(self):
        """<summary>MUSIC-LYRICS-FIX: with the switch off again once the install lands, no further question or change.</summary>"""
        self.rig.answer = True
        self.rig.arrive_after = 3
        self.rig.switch_on = False
        self.helper._lyrics_offer(True)
        self.assertIn("InstallAddon(%s)" % ADDON, self.rig.builtins)
        self.assertEqual(len(self.rig.yesno_calls), 1)
        self.assertEqual(self.rig.set_calls, [])
        self.assertNotIn("RunScript(%s)" % ADDON, self.rig.builtins)

    def test_install_wait_is_bounded_at_sixty_steps(self):
        """<summary>If the add-on never arrives the wait gives up after at most 60 steps and nothing further is changed.</summary>"""
        self.rig.answer = True
        self.rig.arrive_after = None
        self.helper._lyrics_offer(True)
        self.assertLessEqual(self.rig.waits, 60)
        self.assertGreaterEqual(self.rig.waits, 1)
        self.assertEqual(self.rig.set_calls, [])
        self.assertNotIn("RunScript(%s)" % ADDON, self.rig.builtins)

    def test_on_installed_but_disabled_yes_enables(self):
        """<summary>A Yes calls Addons.SetAddonEnabled with enabled true.</summary>"""
        self.rig.installed, self.rig.enabled = True, False
        self.rig.settings = {"service": True}
        self.rig.answer = True
        self.helper._lyrics_offer(True)
        self.assertEqual(len(self.rig.yesno_calls), 1)
        calls = self.rig.rpc_methods("Addons.SetAddonEnabled")
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0].get("enabled"), True)
        self.assertEqual(calls[0].get("addonid"), ADDON)

    def test_on_installed_but_disabled_no_stops(self):
        """<summary>A No leaves the add-on alone and asks nothing further.</summary>"""
        self.rig.installed, self.rig.enabled = True, False
        self.rig.answer = False
        self.helper._lyrics_offer(True)
        self.assertEqual(len(self.rig.yesno_calls), 1)
        self.assertEqual(self.rig.rpc_methods("Addons.SetAddonEnabled"), [])
        self.assertEqual(self.rig.set_calls, [])

    def test_on_enabled_service_off_yes_sets_it_and_runs_script(self):
        """<summary>With service false, a Yes sets service True and runs RunScript.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.settings = {"service": False}
        self.rig.answer = True
        self.helper._lyrics_offer(True)
        self.assertEqual(len(self.rig.yesno_calls), 1)
        self.assertEqual(self.rig.set_calls, [("service", True)])
        self.assertIn("RunScript(%s)" % ADDON, self.rig.builtins)
        self.assertIn(ADDON, self.rig.addon_ids)

    def test_on_enabled_service_off_no_changes_nothing(self):
        """<summary>A No writes no setting and runs no script.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.answer = False
        self.helper._lyrics_offer(True)
        self.assertEqual(self.rig.set_calls, [])
        self.assertNotIn("RunScript(%s)" % ADDON, self.rig.builtins)

    def test_on_enabled_service_on_asks_nothing(self):
        """<summary>When service is already true there is no question and no change.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.settings = {"service": True}
        self.helper._lyrics_offer(True)
        self.assertEqual(self.rig.yesno_calls, [])
        self.assertEqual(self.rig.set_calls, [])
        self.assertEqual(self.rig.rpc_methods("Addons.SetAddonEnabled"), [])

    def test_hide_dialog_is_never_read_or_written(self):
        """<summary>No path through the offer touches the hide_dialog setting.</summary>"""
        reads = []
        rig = self.rig
        real = rig.addon

        def watching(addon_id=None, *_a):
            """<summary>An add-on that records which settings are read.</summary><param name="addon_id">The id.</param><returns>The stand in.</returns>"""
            obj = real(addon_id)
            inner = obj.getSettingBool
            obj.getSettingBool = lambda key: (reads.append(key), inner(key))[1]
            return obj

        T.xbmcaddon.Addon = watching
        for installed, enabled, answer, pick, on in ((True, True, True, 0, True), (True, True, True, 0, False),
                                                      (True, False, True, 1, True), (True, True, True, 1, False)):
            rig.installed, rig.enabled, rig.answer, rig.pick = installed, enabled, answer, pick
            rig.settings = {"service": False}
            self.helper._lyrics_offer(on)
        self.assertNotIn("hide_dialog", reads)
        self.assertNotIn("hide_dialog", [k for k, _v in rig.set_calls])

    def test_off_installed_offers_three_choices(self):
        """<summary>Switched off and installed, select is offered three lines.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.pick = -1
        self.helper._lyrics_offer(False)
        self.assertEqual(len(self.rig.picked_from), 3)

    def test_off_installed_choice_0_does_nothing(self):
        """<summary>Choice 0 changes nothing: no setting, no disable, no window, no builtin.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.pick = 0
        self.helper._lyrics_offer(False)
        self.assertEqual(self.rig.set_calls, [])
        self.assertEqual(self.rig.rpc_methods("Addons.SetAddonEnabled"), [])
        self.assertEqual(self.rig.builtins, [])

    def test_off_installed_choice_1_disables_the_addon(self):
        """<summary>Choice 1 calls Addons.SetAddonEnabled with enabled false.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.pick = 1
        self.helper._lyrics_offer(False)
        calls = self.rig.rpc_methods("Addons.SetAddonEnabled")
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0].get("enabled"), False)
        self.assertEqual(calls[0].get("addonid"), ADDON)

    def test_off_installed_choice_2_opens_the_browser_and_notifies(self):
        """<summary>Choice 2 opens the lyrics add-on browser page and shows a notification.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.pick = 2
        self.helper._lyrics_offer(False)
        self.assertIn("ActivateWindow(addonbrowser,addons://user/xbmc.python.lyrics/,return)", self.rig.builtins)
        self.assertEqual(len(self.toasts()), 1)

    def test_off_installed_cancelled_select_does_nothing(self):
        """<summary>Backing out of the three way choice (index minus one) changes nothing.</summary>"""
        self.rig.installed, self.rig.enabled = True, True
        self.rig.pick = -1
        self.helper._lyrics_offer(False)
        self.assertEqual(self.rig.set_calls, [])
        self.assertEqual(self.rig.rpc_methods("Addons.SetAddonEnabled"), [])
        self.assertEqual(self.rig.builtins, [])

    def test_off_not_installed_does_nothing(self):
        """<summary>With the switch off and the add-on absent there is no question, no call and no builtin.</summary>"""
        self.helper._lyrics_offer(False)
        self.assertIsNone(self.rig.picked_from)
        self.assertEqual(self.rig.yesno_calls, [])
        self.assertEqual(self.rig.builtins, [])
        self.assertEqual(self.rig.rpc, [])
        self.assertEqual(self.rig.set_calls, [])


class LyricsWindowXmlSpec(unittest.TestCase):
    """<summary>Requirement 4: the lyrics window skin file."""

    PATH = os.path.join(XML, "script-cu-lrclyrics-main.xml")

    def test_file_exists_and_parses(self):
        """<summary>The file is there and is well formed XML.</summary>"""
        self.assertTrue(os.path.isfile(self.PATH))
        ET.parse(self.PATH)

    def test_list_110_and_label_200_exist(self):
        """<summary>A list with id 110 and a label with id 200, the ids the add-on drives.</summary>"""
        root = ET.parse(self.PATH).getroot()
        lists = [c for c in root.iter("control") if c.get("id") == "110" and c.get("type") == "list"]
        labels = [c for c in root.iter("control") if c.get("id") == "200" and c.get("type") == "label"]
        self.assertEqual(len(lists), 1)
        self.assertEqual(len(labels), 1)

    def test_switch_picks_the_look(self):
        """<summary>MUSIC-LYRICS-FIX: the plain panel shows only with the switch off, and list 110 has a focused layout for the switch on and a plain one for off.</summary>"""
        root = ET.parse(self.PATH).getroot()
        groups = [g for g in root.iter("control") if g.get("type") == "group"
                  and (g.findtext("visible") or "").strip() == "!Skin.HasSetting(music_lyrics)"]
        self.assertEqual(len(groups), 1)
        lst = [c for c in root.iter("control") if c.get("id") == "110"][0]
        conds = [f.get("condition") for f in lst.findall("focusedlayout")]
        self.assertEqual(conds, ["Skin.HasSetting(music_lyrics)", None])

    def test_it_uses_none_of_the_addons_own_media(self):
        """<summary>No texture or other text is named culrc-something.</summary>"""
        with open(self.PATH, encoding="utf-8") as fh:
            self.assertIsNone(re.search(r"culrc[-]", fh.read()))


if __name__ == "__main__":
    unittest.main(verbosity=1)
