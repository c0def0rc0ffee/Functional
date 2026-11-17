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


if __name__ == "__main__":
    unittest.main()
