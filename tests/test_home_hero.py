#!/usr/bin/env python3
"""
<summary>
Tests for the review fixes to roadmap item 20, the Home hero (HOME-HERO-FIX):
the background caption fades rather than hides, so its Add To List button stays
a navigation target; the hero and its dim never cover a video playing behind
Home; the pop up logo clears the band and a top corner bar.
</summary>
<remarks>
No Kodi is needed; these read the skin's XML. The service fix (an error answer
kept as empty) is covered in tests/test_home_hero_spec.py. Exits non zero when
a test fails.

Usage:
    python3 tests/test_home_hero.py
</remarks>
"""

import os
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "skin.functional", "xml")


def include(file_name, name):
    """
    <summary>One named include from a skin XML file.</summary>
    <param name="file_name">File in the xml folder.</param>
    <param name="name">The include's name.</param>
    <returns>The include element.</returns>
    """
    root = ET.parse(os.path.join(XML, file_name)).getroot()
    for inc in root.iter("include"):
        if inc.get("name") == name:
            return inc
    raise AssertionError("no include " + name)


class CaptionStaysReachable(unittest.TestCase):
    """<summary>The caption fades while the hero shows, it is not hidden.</summary>"""

    def test_caption_visible_ignores_the_hero(self):
        """<summary>The caption's visible condition does not name the hero, so Control.IsVisible(9302) holds for a row's Down.</summary>"""
        group = include("Includes_Home.xml", "BgCaption").find("definition/control")
        self.assertNotIn("hero", group.find("visible").text)

    def test_caption_fades_while_hero_shows(self):
        """<summary>Two Conditional fades to 0 on hero_showing, one per reduce motion state.</summary>"""
        group = include("Includes_Home.xml", "BgCaption").find("definition/control")
        fades = [a for a in group.findall("animation")
                 if a.get("effect") == "fade" and a.get("end") == "0"
                 and "$EXP[hero_showing]" in (a.get("condition") or "")]
        self.assertEqual(len(fades), 2)
        self.assertEqual(sorted(a.get("time") for a in fades), ["0", "300"])
        # A fade's start defaults to 0 in Kodi, so without start="100" the
        # caption was invisible all the time, hero or not (seen live).
        self.assertEqual({a.get("start") for a in fades}, {"100"})


class NoFanartPlate(unittest.TestCase):
    """<summary>HOME-HERO-FIX: a title with no fanart gets the plain plate, not the slideshow.</summary>"""

    def test_hero_showing_needs_focus_only(self):
        """<summary>hero_showing names the two focus expressions and no art, so the plate and logo show for a title with none.</summary>"""
        root = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
        text = [e.text for e in root.iter("expression") if e.get("name") == "hero_showing"][0]
        self.assertEqual(text.strip(), "$EXP[hero_popup_focus] | $EXP[hero_rows_focus]")

    def test_plate_sits_under_the_fanart(self):
        """<summary>The plate is a solid bg colour layer drawn just before the hero fanart.</summary>"""
        ctls = list(include("Includes.xml", "SkinBackground").iter("control"))
        fan = [i for i, c in enumerate(ctls) if (c.findtext("texture") or "") == "$VAR[HeroFanart]"][0]
        plate = ctls[fan - 1]
        self.assertEqual(plate.find("texture").get("colordiffuse"), "bg")


class VideoStaysInFront(unittest.TestCase):
    """<summary>The hero and its dim stand down for a video playing behind Home.</summary>"""

    def test_hero_image_and_dim_need_no_video(self):
        """<summary>Every control in SkinBackground that names hero_showing also needs !bg_video_showing for it.</summary>"""
        found = 0
        for ctl in include("Includes.xml", "SkinBackground").iter("control"):
            vis = ctl.find("visible")
            if vis is not None and "hero_showing" in vis.text:
                found += 1
                self.assertIn("$EXP[hero_showing] + !$EXP[bg_video_showing]", vis.text)
        self.assertEqual(found, 3)  # the plate, the fanart and the dim


class PopupLogoPlace(unittest.TestCase):
    """<summary>The pop up logo clears the band and gives way where it cannot.</summary>"""

    def setUp(self):
        """<summary>The pop up logo group, the first group of HomeHero.</summary>"""
        self.group = include("Includes_Home.xml", "HomeHero").find("definition/control")

    def test_logo_ends_above_the_tall_band(self):
        """<summary>Top plus height stays above y 356, where the tall band starts.</summary>"""
        top = int(self.group.find("top").text)
        height = int(self.group.find("height").text)
        self.assertLessEqual(top + height, 356)

    def test_logo_gives_way(self):
        """<summary>Left out with the tab at the top, and with a top corner bar over the tall band; moved down 80 for a top bar.</summary>"""
        vis = self.group.find("visible").text
        self.assertIn("!$EXP[continue_tab_top]", vis)
        self.assertIn("![$EXP[corner_bar_top] + $EXP[panel_tall]]", vis)
        slides = [a for a in self.group.findall("animation")
                  if a.get("effect") == "slide" and a.get("condition") == "$EXP[corner_bar_top]"]
        self.assertEqual([a.get("end") for a in slides], ["0,80"])
        self.assertLessEqual(int(self.group.find("top").text) + 80 + int(self.group.find("height").text), 676)


if __name__ == "__main__":
    unittest.main()
