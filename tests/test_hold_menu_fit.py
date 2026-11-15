#!/usr/bin/env python3
"""
<summary>
Tests for HOLD-MENU-FIT (15/11/2026): the hold menu keeps every entry on
screen whatever skin rows show above Kodi's own list.
</summary>
<remarks>
Kodi places DialogContextMenu so that control 999's height fits the screen,
and sizes 999 from its declared height less the grouplist maximum plus the
rows Kodi added. The skin rows 950 to 953 sit above that list, so 999 is
declared with room for the most of them that show at once and draws nothing,
and Kodi's rows paint their own panel instead. No Kodi is needed; these read
the XML. Exits non zero when a test fails.

Usage:
    python3 tests/test_hold_menu_fit.py
</remarks>
"""

import os
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
XML = os.path.join(HERE, "..", "skin.functional", "xml")
ROW = 60                 # height of one menu row
SKIN_ROWS_AT_ONCE = 3    # 950, 951, and 952 (a film) or 953 (a show)
HEADING = 110            # the panel heading above 999, which Kodi does not count


def control(root, cid):
    """
    <summary>The control with an id in a parsed window.</summary>
    <param name="root">The window's root element.</param>
    <param name="cid">The id as text.</param>
    <returns>The element.</returns>
    """
    for c in root.iter("control"):
        if c.get("id") == cid:
            return c
    raise AssertionError("no control " + cid)


class HoldMenuFit(unittest.TestCase):
    """<summary>The measure Kodi places the menu by leaves room for the skin rows.</summary>"""

    def setUp(self):
        """<summary>Parse the hold menu window.</summary>"""
        self.root = ET.parse(os.path.join(XML, "DialogContextMenu.xml")).getroot()

    def test_measure_has_room_for_the_skin_rows(self):
        """<summary>999's declared height is the grouplist maximum, the heading and three skin rows.</summary>"""
        group_max = int(control(self.root, "996").find("height").get("max"))
        measure = int(control(self.root, "999").findtext("height"))
        self.assertEqual(measure, group_max + HEADING + SKIN_ROWS_AT_ONCE * ROW)
        heading = int(control(self.root, "999").findtext("top"))
        self.assertEqual(heading, HEADING)

    def test_measure_draws_nothing(self):
        """<summary>999 is fully transparent (00FFFFFF, since Kodi draws an all zero colour as opaque white).</summary>"""
        texture = control(self.root, "999").find("texture")
        self.assertEqual(texture.get("colordiffuse"), "00FFFFFF")

    def test_kodi_rows_paint_the_panel(self):
        """<summary>Button template 1000 paints the panel colour behind every row Kodi clones from it.</summary>"""
        nofocus = control(self.root, "1000").find("texturenofocus")
        self.assertEqual(nofocus.get("colordiffuse"), "bg_panel")
        self.assertEqual((nofocus.text or "").strip(), "white.png")

    def test_film_and_show_rows_have_their_own_conditions(self):
        """<summary>The Collection row needs an item in a set (ListItem.SetId) and Play This Show a library show; Kodi gives only films a set, so the two do not show together and three skin rows is the most at once. This checks the two conditions, not Kodi's data.</summary>"""
        inc = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
        found = {}
        for include in inc.iter("include"):
            if include.get("name") in ("CollectionContextButton", "ShowPlayContextButton"):
                for c in include.iter("control"):
                    if c.get("type") == "button":
                        found[include.get("name")] = c.findtext("visible") or ""
        self.assertIn("ListItem.SetId", found["CollectionContextButton"])
        self.assertIn("String.IsEqual(ListItem.DBTYPE,tvshow)", found["ShowPlayContextButton"])


if __name__ == "__main__":
    unittest.main()
