#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 49, Declutter (DECLUTTER): after a set idle time Home
fades to its background, keeping only the pieces whose Keep row is ticked.
</summary>
<remarks>
No Kodi is needed; these read the skin's XML. They prove the switch is off by
default and gates every fade, that the delay cycle, its label and the idle
expression agree on the same choices, that each Home piece carries the fade
with the right Keep setting while the background and the closed Continue
Watching pop up do not, and that the shared includes the settings stage
draws are left untouched. What the fade looks like is the live check's job.
Exits non zero when a test fails.

Usage:
    python3 tests/test_declutter.py
</remarks>
"""

import glob
import os
import re
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "skin.functional", "xml")

# The delay choices in seconds; empty, the default, is one minute.
DELAYS = {"30", "120", "300", "600"}


def read(path):
    """
    <summary>The whole text of one file, closed again afterwards.</summary>
    <param name="path">The file to read.</param>
    <returns>Its text.</returns>
    """
    with open(path, encoding="utf-8") as f:
        return f.read()


def root(file_name):
    """
    <summary>The parsed root of one skin XML file.</summary>
    <param name="file_name">File in the xml folder.</param>
    <returns>The root element.</returns>
    """
    return ET.parse(os.path.join(XML, file_name)).getroot()


def named(file_name, tag, name):
    """
    <summary>One named include, variable or expression from a skin XML file.</summary>
    <param name="file_name">File in the xml folder.</param>
    <param name="tag">include, variable or expression.</param>
    <param name="name">Its name attribute.</param>
    <returns>The element.</returns>
    """
    for el in root(file_name).iter(tag):
        if el.get("name") == name:
            return el
    raise AssertionError("no %s %s" % (tag, name))


def control(cid):
    """
    <summary>One control of SkinSettings.xml by id.</summary>
    <param name="cid">The control id as a string.</param>
    <returns>The control element.</returns>
    """
    for el in root("SkinSettings.xml").iter("control"):
        if el.get("id") == cid:
            return el
    raise AssertionError("no control " + cid)


def home_fades():
    """
    <summary>Each Home.xml include, mapped to the keep value of the DeclutterFade its parent group carries.</summary>
    <returns>A dict of include content name to keep value: "false" for the
    include's default, None where the parent has no fade.</returns>
    """
    tree = root("Home.xml")
    parents = {child: parent for parent in tree.iter() for child in parent}
    found = {}
    for inc in tree.iter("include"):
        name = inc.get("content")
        if not name or name == "DeclutterFade":
            continue
        keep = None
        for sibling in parents[inc]:
            if sibling.tag == "include" and sibling.get("content") == "DeclutterFade":
                param = sibling.find("param[@name='keep']")
                keep = param.get("value") if param is not None else "false"
        found.setdefault(name, keep)
    return found


class OffByDefault(unittest.TestCase):
    """<summary>Nothing fades until the user switches Declutter on.</summary>"""

    def test_switch_gates_the_expression(self):
        """<summary>declutter_on needs Skin.HasSetting(declutter), and the switch row toggles that setting.</summary>"""
        self.assertIn("Skin.HasSetting(declutter) +", named("Includes.xml", "expression", "declutter_on").text)
        row = control("7190")
        self.assertEqual(row.find("onclick").text, "Skin.ToggleSetting(declutter)")

    def test_nothing_switches_it_on(self):
        """<summary>No XML or Python sets the switch by itself, so a fresh install has it off.</summary>"""
        files = glob.glob(os.path.join(XML, "*.xml")) + [os.path.join(XML, "..", "service.py")]
        for path in files:
            text = read(path)
            self.assertNotRegex(text, r"Skin\.SetBool\(declutter\)", path)

    def test_every_fade_waits_for_declutter_on(self):
        """<summary>Both fades of the include name $EXP[declutter_on], fade from 100 to 0 and snap back.</summary>"""
        anims = named("Includes.xml", "include", "DeclutterFade").findall("definition/animation")
        self.assertEqual(len(anims), 2)
        for a in anims:
            self.assertIn("$EXP[declutter_on]", a.get("condition"))
            self.assertEqual((a.get("effect"), a.get("start"), a.get("end")), ("fade", "100", "0"))
            self.assertEqual(a.get("reversible"), "false")
            self.assertEqual(a.text, "Conditional")

    def test_reduce_motion_takes_no_time(self):
        """<summary>1500 ms normally, 0 ms under reduce_motion.</summary>"""
        anims = named("Includes.xml", "include", "DeclutterFade").findall("definition/animation")
        times = {("!Skin.HasSetting(reduce_motion)" in a.get("condition")): a.get("time") for a in anims}
        self.assertEqual(times, {True: "1500", False: "0"})


class DelayChoices(unittest.TestCase):
    """<summary>The cycle, its label and the idle expression agree.</summary>"""

    def test_cycle_visits_every_choice_once(self):
        """<summary>The 7191 cycle sets each delay and resets back to the default.</summary>"""
        clicks = [c.text for c in control("7191").findall("onclick")]
        set_to = {m.group(1) for c in clicks for m in [re.search(r"SetString\(declutter_delay,(\d+)\)", c)] if m}
        self.assertEqual(set_to, DELAYS)
        self.assertTrue(any("Skin.Reset(declutter_delay)" in c for c in clicks))

    def test_idle_expression_matches_each_choice(self):
        """<summary>Each choice pairs with System.IdleTime of the same seconds, and the fallback is 60.</summary>"""
        text = named("Includes.xml", "expression", "declutter_idle").text
        for d in DELAYS:
            self.assertIn("String.IsEqual(Skin.String(declutter_delay),%s) + System.IdleTime(%s)]" % (d, d), text)
        self.assertTrue(text.rstrip().endswith("System.IdleTime(60)]"))

    def test_label_names_each_choice(self):
        """<summary>DeclutterDelayLabel has a value for each choice plus the default.</summary>"""
        values = named("Includes.xml", "variable", "DeclutterDelayLabel").findall("value")
        conds = {re.search(r",(\d+)\)", v.get("condition")).group(1) for v in values if v.get("condition")}
        self.assertEqual(conds, DELAYS)
        self.assertEqual(len([v for v in values if not v.get("condition")]), 1)


class HomePieces(unittest.TestCase):
    """<summary>Each Home piece carries the fade with its own Keep setting.</summary>"""

    EXPECTED = {
        "BgCaptions": "Skin.HasSetting(declutter_keep_captions)",
        "BgStepButtons": "Skin.HasSetting(declutter_keep_captions)",
        "HomeHero": "false",
        "HomeStatsColumn": "!Skin.HasSetting(declutter_drop_stats)",
        "HomeLogo": "Skin.HasSetting(declutter_keep_logo)",
        "HomeFooter": "Skin.HasSetting(declutter_keep_logo)",
        "HomeWeather": "!Skin.HasSetting(declutter_drop_clock)",
        "HomeClock": "!Skin.HasSetting(declutter_drop_clock)",
        "HomeMenu": "false",
        "HomeWidgetRows": "false",
        "HomeCornerBar": "Skin.HasSetting(declutter_keep_cornerbar)",
        "HomeContinueTabs": "false",
        "ComingUpLine": "Skin.HasSetting(declutter_keep_comingup)",
    }

    def test_each_piece_has_its_keep(self):
        """<summary>The keep value on each piece's group is the one its row toggles.</summary>"""
        found = home_fades()
        for name, keep in self.EXPECTED.items():
            self.assertEqual(found.get(name), keep, name)

    def test_background_never_fades(self):
        """<summary>The two background includes sit outside any faded group.</summary>"""
        found = home_fades()
        self.assertIsNone(found["WindowBackground"])
        self.assertIsNone(found["SkinBackground"])

    def test_keep_rows_toggle_the_same_settings(self):
        """<summary>Rows 7192 to 7197 toggle the settings the pieces read, are greyed while off, and the clock and stats read as kept by default.</summary>"""
        rows = {"7192": "declutter_drop_clock", "7193": "declutter_drop_stats",
                "7194": "declutter_keep_comingup", "7195": "declutter_keep_captions",
                "7196": "declutter_keep_cornerbar", "7197": "declutter_keep_logo"}
        for cid, setting in rows.items():
            row = control(cid)
            self.assertEqual(row.find("onclick").text, "Skin.ToggleSetting(%s)" % setting)
            self.assertEqual(row.find("enable").text, "Skin.HasSetting(declutter)")
            inverted = setting.startswith("declutter_drop_")
            self.assertEqual(row.find("selected").text.startswith("!"), inverted, cid)
        self.assertEqual(control("7191").find("enable").text, "Skin.HasSetting(declutter)")


class StageUntouched(unittest.TestCase):
    """<summary>The fade lives in Home.xml only, so the settings stage, which draws the same includes, never fades.</summary>"""

    def test_shared_includes_carry_no_fade(self):
        """<summary>Includes_Home.xml and Includes_SettingsPreview.xml never name DeclutterFade or declutter_on.</summary>"""
        for name in ("Includes_Home.xml", "Includes_SettingsPreview.xml"):
            text = read(os.path.join(XML, name))
            self.assertNotIn("DeclutterFade", text, name)
            self.assertNotIn("declutter_on", text, name)


class CirclesAndGreeting(unittest.TestCase):
    """<summary>CIRCLES-FADE and GREETING-DECLUTTER, 18/11/2026: the round buttons and the greeting always go, even when their row or the clock is kept.</summary>"""

    CIRCLES = ("stats", "lists", "fav", "addons", "settings", "power")

    def test_every_round_button_carries_the_fade(self):
        """<summary>Each of the six round buttons in HomeCornerBar fades on circles_fade, and no pill does.</summary>"""
        bar = named("Includes_Home.xml", "include", "HomeCornerBar")
        faded = set()
        for el in bar.iter("control"):
            for inc in el.findall("include"):
                if inc.get("content") == "HomeCircleFade":
                    param = inc.find("param")
                    self.assertEqual(param.get("value"), "$PARAM[circles_fade]")
                    faded.add(el.get("id"))
        self.assertEqual(faded, {"$PARAM[id_%s]" % c for c in self.CIRCLES})

    def test_circle_fade_is_off_unless_asked(self):
        """<summary>circles_fade defaults to false and the fade honours reduce_motion.</summary>"""
        bar = named("Includes_Home.xml", "include", "HomeCornerBar")
        defaults = {p.get("name"): p.get("default") for p in bar.findall("param")}
        self.assertEqual(defaults.get("circles_fade"), "false")
        fade = named("Includes_Home.xml", "include", "HomeCircleFade")
        times = sorted(a.get("time") for a in fade.iter("animation"))
        self.assertEqual(times, ["0", "1500"])
        for a in fade.iter("animation"):
            self.assertIn("$PARAM[when]", a.get("condition"))
            self.assertEqual(a.get("reversible"), "false")

    def test_home_passes_declutter_and_stage_does_not(self):
        """<summary>Home's three corner bars pass the declutter condition; the stage's three pass nothing.</summary>"""
        home = [i for i in root("Home.xml").iter("include") if i.get("content") == "HomeCornerBar"]
        self.assertEqual(len(home), 3)
        for inc in home:
            params = {p.get("name"): p.get("value") for p in inc.findall("param")}
            self.assertEqual(params.get("circles_fade"), "$EXP[declutter_on]")
        stage = [i for i in root("Includes_Home.xml").iter("include") if i.get("content") == "HomeCornerBar"]
        self.assertTrue(stage)
        for inc in stage:
            self.assertNotIn("circles_fade", {p.get("name") for p in inc.findall("param")})

    def test_greeting_gives_way_on_home_only(self):
        """<summary>greeting_room is false while Home is decluttered, and only on Home, so the stage keeps its greeting.</summary>"""
        room = named("Includes.xml", "expression", "greeting_room").text
        self.assertIn("![$EXP[declutter_on] + Window.IsActive(home)]", room)
        flipped = named("Includes.xml", "expression", "greeting_room_flipped").text
        self.assertNotIn("declutter", flipped)


def service_module():
    """
    <summary>service.py with the Kodi stubs in place, loaded the way the Coming up tests load it.</summary>
    <returns>The service module.</returns>
    """
    import sys
    sys.path.insert(0, HERE)
    import test_lists_api as T  # installs the Kodi stubs, imports service
    return T.service


def cycle_of(cid, setting):
    """
    <summary>The values one cycling settings button walks through, starting from empty.</summary>
    <param name="cid">The button id.</param>
    <param name="setting">The Skin.String it cycles.</param>
    <returns>The values in order, "" for empty, ending when the walk is back at empty.</returns>
    """
    steps = {}
    for click in control(cid).findall("onclick"):
        cond, act = click.get("condition"), click.text
        start = "" if cond.startswith("String.IsEmpty") else cond.split(",")[1].rstrip(")")
        steps[start] = "" if act.startswith("Skin.Reset") else act.split(",")[1].rstrip(")")
        assert setting in cond and setting in act, (cid, cond, act)
    walk, value = [""], steps[""]
    while value != "":
        walk.append(value)
        value = steps[value]
    return walk


class ComingUpCount(unittest.TestCase):
    """<summary>DECLUTTER-COUNT, 18/11/2026: Coming Up While Decluttered keeps the next few slots and their headings.</summary>"""

    def test_ranks_keep_whole_slots(self):
        """<summary>An item and its item2 share a rank, a heading takes the slot under it, an Ends At line the slot before.</summary>"""
        service = service_module()
        window = [{"kind": k} for k in
                  ("item", "item2", "heading", "slot", "slot", "ends", "heading", "slot", "pad", "", "")]
        self.assertEqual(service.coming_up_ranks(window),
                         ["1", "1", "2", "2", "3", "3", "4", "4", "4", "4", "4"])
        self.assertEqual(service.coming_up_ranks([{"kind": ""}, {"kind": ""}]), ["", ""])

    def test_rank_is_published(self):
        """<summary>update_coming_up_lines writes Rank beside Kind, Label, When and Sep.</summary>"""
        text = read(os.path.join(HERE, "..", "skin.functional", "service.py"))
        self.assertIn('for field in ("kind", "label", "when", "sep", "rank"):', text)
        self.assertIn("coming_up_ranks(window)", text)

    def test_row_cycles_and_needs_coming_up_kept(self):
        """<summary>7198 cycles All, 1, 2, 3, 5 and is greyed until Declutter and Keep Coming Up List are both on.</summary>"""
        self.assertEqual(cycle_of("7198", "declutter_comingup_count"), ["", "1", "2", "3", "5"])
        self.assertEqual(control("7198").find("enable").text,
                         "Skin.HasSetting(declutter) + Skin.HasSetting(declutter_keep_comingup)")
        label = named("Includes.xml", "variable", "DeclutterComingUpLabel")
        conds = {v.get("condition") for v in label.findall("value") if v.get("condition")}
        self.assertEqual(conds, {"String.IsEqual(Skin.String(declutter_comingup_count),%d)" % n for n in (1, 2, 3, 5)})

    def test_every_line_fades_past_the_count(self):
        """<summary>ComingUpLine's line group fades on each count only while decluttered, honouring reduce_motion.</summary>"""
        line = named("Includes.xml", "include", "ComingUpLine")
        anims = [a for a in line.iter("animation") if "declutter_comingup_count" in (a.get("condition") or "")]
        self.assertEqual(sorted(a.get("time") for a in anims), ["0", "1500"])
        for a in anims:
            cond = a.get("condition")
            self.assertTrue(cond.startswith("$EXP[declutter_on] + "), cond)
            for n in (1, 2, 3, 5):
                self.assertIn("Integer.IsGreater(Window(home).Property(ComingUp.$PARAM[line].Rank),%d)" % n, cond)


class DeclutterDim(unittest.TestCase):
    """<summary>DECLUTTER-DIM, 18/11/2026: Dim While Decluttered sets the background dim on Home while decluttered.</summary>"""

    LEVELS = ("0", "25", "50", "75", "90")

    def test_row_cycles(self):
        """<summary>7217 cycles As Usual, then 0, 25, 50, 75 and 90, and is greyed while Declutter is off.</summary>"""
        self.assertEqual(cycle_of("7217", "declutter_dim"), [""] + list(self.LEVELS))
        self.assertEqual(control("7217").find("enable").text, "Skin.HasSetting(declutter)")

    def test_dim_wins_on_home_only(self):
        """<summary>Both background dim variables open with one value per level, each gated on declutter_home.</summary>"""
        home = named("Includes.xml", "expression", "declutter_home").text
        self.assertEqual(home, "$EXP[declutter_on] + Window.IsActive(home)")
        for name in ("BgOverlayColor", "BgImageDiffuse"):
            values = named("Includes.xml", "variable", name).findall("value")
            first = [v.get("condition") for v in values[:5]]
            self.assertEqual(first, ["$EXP[declutter_home] + String.IsEqual(Skin.String(declutter_dim),%s)" % n
                                     for n in self.LEVELS], name)
            self.assertFalse(any("declutter" in (v.get("condition") or "") for v in values[5:]), name)

    def test_help_and_preview_know_the_rows(self):
        """<summary>Both new rows have a help line and sit in the no preview list.</summary>"""
        help_xml = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
        for cid, string in (("7198", "31987"), ("7217", "31990")):
            self.assertIn('<value condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (cid, string), help_xml)
            self.assertIn("Control.HasFocus(%s)" % cid, named("Includes_SettingsHelp.xml", "expression", "settings_help_shown").text)
            self.assertIn("Control.HasFocus(%s)" % cid, named("Includes_SettingsPreview.xml", "expression", "settings_preview_none").text)


if __name__ == "__main__":
    unittest.main()
