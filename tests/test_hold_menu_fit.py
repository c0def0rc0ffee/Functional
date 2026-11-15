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
import sys
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


class HoldMenuFocus(unittest.TestCase):
    """<summary>HOLD-MENU-FOCUS: the menu opens on its first row, and Down walks every row in order.</summary>"""

    def setUp(self):
        """<summary>Parse the hold menu window.</summary>"""
        self.root = ET.parse(os.path.join(XML, "DialogContextMenu.xml")).getroot()

    def test_opens_on_kodis_first_entry_without_skin_rows(self):
        """<summary>With none of 950 to 953 or 960 showing, onload focuses 1001, Kodi's first cloned row.</summary>"""
        loads = [(o.get("condition") or "", (o.text or "").strip()) for o in self.root.findall("onload")]
        first = [c for c, action in loads if action == "SetFocus(1001)"]
        self.assertEqual(len(first), 1)
        for cid in ("950", "951", "952", "953", "960"):
            self.assertIn("!Control.IsVisible(%s)" % cid, first[0])

    def test_down_from_the_skin_rows_lands_on_kodis_first_entry(self):
        """<summary>953, the lowest skin row, goes Down to 1001 rather than to grouplist 996.</summary>"""
        use = [i for i in self.root.iter("include") if i.get("content") == "ShowPlayContextButton"][0]
        params = {p.get("name"): p.get("value") for p in use.findall("param")}
        self.assertEqual(params["ondown"], "1001")

    def test_down_from_kodis_last_entry_wraps_to_the_skin_rows(self):
        """<summary>Grouplist 996 goes Down to 950, whose hidden chain reaches the first skin row showing, or 1001.</summary>"""
        self.assertEqual((control(self.root, "996").findtext("ondown") or "").strip(), "950")

    def test_checker_knows_kodi_creates_1001(self):
        """<summary>The navigation check counts 1001 as present in this window only.</summary>"""
        sys.path.insert(0, os.path.join(HERE, "..", "checks"))
        import skin_checks
        self.assertEqual(skin_checks.RUNTIME_IDS, {"DialogContextMenu.xml": ("1001",)})


if __name__ == "__main__":
    unittest.main()
