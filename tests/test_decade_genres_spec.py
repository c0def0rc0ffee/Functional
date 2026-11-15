#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 33, Decade and Several Genres, written from the spec
alone: the settings row with its help, preview and strings, the decade
helpers, the age node builder, the rule readers, the genre toggle command,
the age sync, the ticking picker slots, and the slide out XML.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the rig of stubbed labels, builtins and
library calls come from tests/test_watchlist.py (built on tests/test_lists_api.py),
which imports the real service.py against them. XML conditions are read with
the small reader of Kodi's boolean grammar kept in tests/test_home_hero_spec.py.
Exits non zero when a test fails.

Usage:
    python3 tests/test_decade_genres_spec.py
</remarks>
"""

import collections
import datetime
import itertools
import json
import os
import re
import sys
import unittest
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_watchlist as W  # noqa: E402  (installs the Kodi stubs, imports service)
import test_home_hero_spec as H  # noqa: E402  (the condition reader)

T = W.T
service = W.service
XML = W.XML

DECADES = ("2020", "2010", "2000", "1990", "1980", "1970", "1960", "1950", "pre1950")
BETWEEN = {"2020": ["2020", "2029"], "2010": ["2010", "2019"], "2000": ["2000", "2009"],
           "1990": ["1990", "1999"], "1980": ["1980", "1989"], "1970": ["1970", "1979"],
           "1960": ["1960", "1969"], "1950": ["1950", "1959"], "pre1950": ["0", "1949"]}
YEAR = datetime.date.today().year
EXTRAS = "Skin.HasSetting(filter_extras)"
SLOT1_EMPTY = "String.IsEmpty(Window(home).Property(GenrePick.1.Label))"
GENRES = {("movie", 1): "Comedy", ("movie", 2): "Drama", ("movie", 3): "action",
          ("tvshow", 1): "Comedy", ("tvshow", 9): "Sitcom"}


def parse(name):
    """
    <summary>Parses one file of the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>The XML root.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def control(root, cid):
    """
    <summary>The first control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element, or None.</returns>
    """
    return next((c for c in root.iter("control") if c.get("id") == cid), None)


def xsp_url(base, rules, kind="movies"):
    """
    <summary>Builds a videodb path with an xsp playlist.</summary>
    <param name="base">The node, such as videodb://movies/titles/.</param>
    <param name="rules">The list of rule dicts to put under and.</param>
    <param name="kind">The playlist type.</param>
    <returns>The path.</returns>
    """
    doc = {"name": "x", "type": kind, "rules": {"and": rules}}
    return base + "?xsp=" + urllib.parse.quote(json.dumps(doc, separators=(",", ":")))


def decode(url):
    """
    <summary>Splits a node path into its base and decoded playlist.</summary>
    <param name="url">A path.</param>
    <returns>(base, document or None).</returns>
    """
    base, sep, query = url.partition("?xsp=")
    return base, (json.loads(urllib.parse.unquote(query)) if sep else None)


class DecadeRig(W.Rig):
    """<summary>The shared rig with the videos window reading as active.</summary>"""

    def __init__(self):
        """<summary>Install the stubs and move the shared clock well on, so no timing guard
        left by an earlier test applies.</summary>"""
        super().__init__()
        self.clock.now += 1000

    def cond(self, text):
        """
        <summary>Adds Window.IsActive(videos) to what the rig answers.</summary>
        <param name="text">The condition.</param>
        <returns>True for the videos window, else the rig's answer.</returns>
        """
        if text == "Window.IsActive(videos)":
            return True
        return super().cond(text)


def make_helper():
    """
    <summary>A helper with no lists and the invented genre table.</summary>
    <returns>A FunctionalHelper.</returns>
    """
    helper = W.helper_with([])
    helper._genre_names = dict(GENRES)
    return helper


class SettingsSpec(unittest.TestCase):
    """<summary>Requirement 1: the setting, its row, help, preview and strings.</summary>"""

    def test_row_follows_7215_in_grouplist_7021(self):
        """<summary>Radiobutton 7217 sits in grouplist 7021 straight after 7215 with label 31965.</summary>"""
        root = parse("SkinSettings.xml")
        group = control(root, "7021")
        self.assertEqual(group.get("type"), "grouplist")
        ids = [c.get("id") for c in group.findall("control")]
        self.assertEqual(ids[ids.index("7215") + 1], "7217")
        self.assertNotIn("7216", ids)
        row = control(root, "7217")
        self.assertEqual(row.get("type"), "radiobutton")
        self.assertEqual(row.findtext("label").strip(), "31965")

    def test_row_reads_and_toggles_filter_extras(self):
        """<summary>The row is selected by and toggles Skin.HasSetting(filter_extras).</summary>"""
        row = control(parse("SkinSettings.xml"), "7217")
        self.assertEqual(row.findtext("selected").strip(), "Skin.HasSetting(filter_extras)")
        self.assertEqual(row.findtext("onclick").strip(), "Skin.ToggleSetting(filter_extras)")

    def test_setting_is_off_by_default(self):
        """<summary>Nothing in the skin turns filter_extras on by default.</summary>"""
        found = []
        for base, _dirs, files in os.walk(W.SKIN):
            for name in files:
                if name.endswith((".xml", ".po")):
                    with open(os.path.join(base, name), encoding="utf-8") as fh:
                        for n, line in enumerate(fh, 1):
                            if re.search(r"SetBool\(filter_extras", line):
                                found.append("%s:%d" % (name, n))
        self.assertEqual(found, [])

    def test_help_text_and_help_list(self):
        """<summary>Help 31966 is given for 7217 and 7217 is in settings_help_shown.</summary>"""
        root = parse("Includes_SettingsHelp.xml")
        hit = [(v.text or "").strip() for v in root.iter("value")
               if v.get("condition") == "Control.HasFocus(7217)"]
        self.assertEqual(hit, ["$LOCALIZE[31966]"])
        self.assertIn("Control.HasFocus(7217)", W.EXPRESSIONS["settings_help_shown"])

    def test_preview_none(self):
        """<summary>7217 is in settings_preview_none.</summary>"""
        self.assertIn("Control.HasFocus(7217)", W.EXPRESSIONS["settings_preview_none"])

    def test_strings_exist(self):
        """<summary>Strings 31965 to 31968 exist and are not empty.</summary>"""
        for sid in range(31965, 31969):
            self.assertTrue(T.STRINGS.get(sid), "string %d missing" % sid)

    def test_7316_goes_up_to_7217(self):
        """<summary>The onup of 7316 is 7217.</summary>"""
        self.assertEqual(control(parse("SkinSettings.xml"), "7316").findtext("onup").strip(), "7217")


class DecadeHelpersSpec(unittest.TestCase):
    """<summary>Requirement 2: DECADES, decade_rule and decade_from_values.</summary>"""

    def test_decades_tuple(self):
        """<summary>service.DECADES lists the nine values newest first.</summary>"""
        self.assertEqual(tuple(service.DECADES), DECADES)

    def test_decade_rule_for_every_decade(self):
        """<summary>decade_rule gives a year between rule for each decade, pre1950 from 0 to 1949.</summary>"""
        for decade, values in BETWEEN.items():
            self.assertEqual(service.decade_rule(decade),
                             {"field": "year", "operator": "between", "value": values}, decade)

    def test_decade_rule_rejects_other_values(self):
        """<summary>Anything else, empty, unknown, a number or None gives None.</summary>"""
        for bad in ("", "1940", "1991", "2030", "all", "PRE1950", None):
            self.assertIsNone(service.decade_rule(bad), repr(bad))

    def test_decade_from_values_inverts_the_rule(self):
        """<summary>decade_from_values returns the decade for each rule's values.</summary>"""
        for decade, values in BETWEEN.items():
            self.assertEqual(service.decade_from_values(values), decade)

    def test_decade_from_values_compares_strings(self):
        """<summary>Numbers match as their text.</summary>"""
        self.assertEqual(service.decade_from_values([1990, 1999]), "1990")
        self.assertEqual(service.decade_from_values([0, 1949]), "pre1950")

    def test_decade_from_values_unknown_is_empty(self):
        """<summary>A list that is no decade, or the wrong length, gives the empty string.</summary>"""
        for bad in ([], ["1990"], ["1990", "2000"], ["1990", "1999", "x"], ["1999", "1990"]):
            self.assertEqual(service.decade_from_values(bad), "", repr(bad))


class AgeNodeSpec(unittest.TestCase):
    """<summary>Requirement 3: FunctionalHelper._age_node.</summary>"""

    def setUp(self):
        """<summary>Install the rig and build a helper with known genres.</summary>"""
        self.rig = DecadeRig()
        self.helper = make_helper()
        self.year = YEAR

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def rules(self, url):
        """
        <summary>The rule list of a node path.</summary>
        <param name="url">A path with an xsp.</param>
        <returns>(base, doc, rules).</returns>
        """
        base, doc = decode(url)
        self.assertIsNotNone(doc, url)
        return base, doc, doc["rules"]["and"]

    def test_single_known_genre_is_the_genre_node(self):
        """<summary>No age, one known genre, no text or decade gives the plain genre node.</summary>"""
        self.assertEqual(self.helper._age_node("movies", 0, "Comedy"), "videodb://movies/genres/1/")
        self.assertEqual(self.helper._age_node("tvshows", 0, ["Sitcom"]), "videodb://tvshows/genres/9/")

    def test_unknown_genre_falls_back_to_a_playlist(self):
        """<summary>A genre with no known id is a genre rule, not a node.</summary>"""
        _b, doc, rules = self.rules(self.helper._age_node("movies", 0, "Western"))
        self.assertEqual(rules, [{"field": "genre", "operator": "is", "value": ["Western"]}])

    def test_no_rule_gives_the_bare_node(self):
        """<summary>With nothing to filter by the answer is AGE_NODES[kind] alone.</summary>"""
        for kind in ("movies", "tvshows"):
            self.assertEqual(self.helper._age_node(kind, 0, ""), self.helper.AGE_NODES[kind])
            self.assertEqual(self.helper._age_node(kind, 0, ["", ""], "", "bogus"),
                             self.helper.AGE_NODES[kind])

    def test_age_rule(self):
        """<summary>Years gives a lessthan rule on the cutoff year, with name, type and and group.</summary>"""
        base, doc, rules = self.rules(self.helper._age_node("movies", 10, ""))
        self.assertEqual(base, self.helper.AGE_NODES["movies"])
        self.assertEqual(doc["name"], "age")
        self.assertEqual(doc["type"], "movies")
        self.assertEqual(rules, [{"field": "year", "operator": "lessthan",
                                  "value": [str(self.year - 10)]}])

    def test_decade_rule(self):
        """<summary>A valid decade adds its between rule.</summary>"""
        _b, _d, rules = self.rules(self.helper._age_node("tvshows", 0, "", "", "1980"))
        self.assertEqual(rules, [service.decade_rule("1980")])

    def test_invalid_decade_is_ignored(self):
        """<summary>An unknown decade adds no rule.</summary>"""
        _b, _d, rules = self.rules(self.helper._age_node("movies", 5, "", "", "1985"))
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["field"], "year")

    def test_several_genres_make_one_rule(self):
        """<summary>A list of genres is a single is rule holding every name, empty entries dropped.</summary>"""
        _b, _d, rules = self.rules(self.helper._age_node("movies", 0, ["Comedy", "", "Drama"]))
        self.assertEqual(rules, [{"field": "genre", "operator": "is", "value": ["Comedy", "Drama"]}])

    def test_title_rule(self):
        """<summary>Text gives a title contains rule.</summary>"""
        _b, _d, rules = self.rules(self.helper._age_node("movies", 0, "", "night & day"))
        self.assertEqual(rules, [{"field": "title", "operator": "contains", "value": ["night & day"]}])

    def test_single_genre_with_text_or_decade_or_age_is_a_playlist(self):
        """<summary>Any other term stops the genre node shortcut.</summary>"""
        for args in ((0, "Comedy", "x", ""), (0, "Comedy", "", "1990"), (3, "Comedy", "", "")):
            url = self.helper._age_node("movies", *args)
            self.assertIn("?xsp=", url, args)

    def test_everything_together_in_order(self):
        """<summary>Age, decade, genre, title in that order, in one and group.</summary>"""
        _b, _d, rules = self.rules(
            self.helper._age_node("tvshows", 20, ["Comedy", "Sitcom"], "show", "2000"))
        self.assertEqual([r["field"] for r in rules], ["year", "year", "genre", "title"])
        self.assertEqual(rules[0]["operator"], "lessthan")
        self.assertEqual(rules[1], service.decade_rule("2000"))
        self.assertEqual(rules[2]["value"], ["Comedy", "Sitcom"])
        self.assertEqual(rules[3]["value"], ["show"])

    def test_xsp_is_quoted_compact_json(self):
        """<summary>The query is url quoted and carries compact JSON.</summary>"""
        url = self.helper._age_node("movies", 0, ["Comedy", "Drama"])
        query = url.partition("?xsp=")[2]
        self.assertNotIn(" ", query)
        self.assertNotIn("{", query)
        self.assertEqual(urllib.parse.unquote(query),
                         json.dumps(json.loads(urllib.parse.unquote(query)), separators=(",", ":")))


class RuleFromPathSpec(unittest.TestCase):
    """<summary>Requirement 4: FunctionalHelper._rule_from_path.</summary>"""

    def call(self, *args, **kw):
        """
        <summary>Calls the static reader.</summary>
        <returns>Its answer.</returns>
        """
        return service.FunctionalHelper._rule_from_path(*args, **kw)

    def test_first_rule_with_the_field(self):
        """<summary>Returns the operator and values of the first matching rule.</summary>"""
        url = xsp_url("videodb://movies/titles/", [
            {"field": "genre", "operator": "is", "value": ["Comedy", "Drama"]},
            {"field": "genre", "operator": "contains", "value": ["x"]}])
        self.assertEqual(self.call(url, "genre"), ("is", ["Comedy", "Drama"]))

    def test_values_come_back_as_strings(self):
        """<summary>Numbers are returned as text.</summary>"""
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "year", "operator": "between", "value": [1990, 1999]}])
        self.assertEqual(self.call(url, "year"), ("between", ["1990", "1999"]))

    def test_single_value_is_a_one_item_list(self):
        """<summary>A non list value is wrapped.</summary>"""
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "year", "operator": "lessthan", "value": "2000"}])
        self.assertEqual(self.call(url, "year"), ("lessthan", ["2000"]))

    def test_absent_field(self):
        """<summary>A field with no rule gives an empty answer.</summary>"""
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "year", "operator": "lessthan", "value": ["2000"]}])
        self.assertEqual(self.call(url, "genre"), ("", []))

    def test_no_xsp(self):
        """<summary>A path without a playlist gives an empty answer.</summary>"""
        self.assertEqual(self.call("videodb://movies/genres/1/", "genre"), ("", []))
        self.assertEqual(self.call("", "genre"), ("", []))

    def test_broken_json(self):
        """<summary>Broken JSON gives an empty answer, not an error.</summary>"""
        for tail in ("%7Bnot", "", "%5B%5D"):
            self.assertEqual(self.call("videodb://movies/titles/?xsp=" + tail, "genre"), ("", []))

    def test_kinds_filter(self):
        """<summary>A playlist type outside kinds gives an empty answer; inside it, the rule.</summary>"""
        url = xsp_url("videodb://tvshows/titles/",
                      [{"field": "genre", "operator": "is", "value": ["Comedy"]}], "tvshows")
        self.assertEqual(self.call(url, "genre", kinds=("movies",)), ("", []))
        self.assertEqual(self.call(url, "genre", kinds=("tvshows",)), ("is", ["Comedy"]))
        self.assertEqual(self.call(url, "genre"), ("is", ["Comedy"]))


class GenresForPathSpec(unittest.TestCase):
    """<summary>Requirement 5: FunctionalHelper._genres_for_path.</summary>"""

    def setUp(self):
        """<summary>A helper with the invented genre table.</summary>"""
        self.rig = DecadeRig()
        self.helper = make_helper()

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def test_genre_node_gives_its_name(self):
        """<summary>A genres node gives the one name from the table.</summary>"""
        self.assertEqual(self.helper._genres_for_path("videodb://movies/genres/2/"), ["Drama"])
        self.assertEqual(self.helper._genres_for_path("videodb://tvshows/genres/9/"), ["Sitcom"])

    def test_xsp_gives_every_non_empty_value(self):
        """<summary>A playlist gives all its genre values, empty ones dropped.</summary>"""
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "genre", "operator": "is", "value": ["Comedy", "", "Drama"]}])
        self.assertEqual(self.helper._genres_for_path(url), ["Comedy", "Drama"])

    def test_other_paths_give_nothing(self):
        """<summary>No genre, an unknown id or an empty path gives an empty list.</summary>"""
        self.assertEqual(self.helper._genres_for_path("videodb://movies/titles/"), [])
        self.assertEqual(self.helper._genres_for_path("videodb://movies/genres/99/"), [])
        self.assertEqual(self.helper._genres_for_path(""), [])
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "year", "operator": "lessthan", "value": ["2000"]}])
        self.assertEqual(self.helper._genres_for_path(url), [])


class GenreToggleSpec(unittest.TestCase):
    """<summary>Requirement 6: update_genre_command with the toggle command.</summary>"""

    def setUp(self):
        """<summary>Install the rig and a helper; the node on screen is a movies node.</summary>"""
        self.rig = DecadeRig()
        self.helper = make_helper()
        self.year = YEAR

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def slot(self, n, name):
        """
        <summary>Fills one picker slot's label on the Home window.</summary>
        <param name="n">The slot number.</param>
        <param name="name">The genre name it shows.</param>
        """
        T.PROPS["GenrePick.%s.Label" % n] = name

    def show(self, path, command="", name="", decade="", age=""):
        """
        <summary>Sets the screen state and runs the command once. A name is put in slot 1
        and, unless a command is given, sent as __toggle__:1.</summary>
        <param name="path">The folder path on screen.</param>
        <param name="command">Skin.String(genre_command), or empty to toggle the name in slot 1.</param>
        <param name="name">The genre name placed in slot 1.</param>
        <param name="decade">Skin.String(decade_filter).</param>
        <param name="age">Skin.String(age_filter).</param>
        """
        self.rig.labels["Container.FolderPath"] = path
        if name:
            self.slot(1, name)
        self.rig.set_skin("genre_command", command or "%s:1" % self.helper.GENRE_TOGGLE)
        self.rig.set_skin("decade_filter", decade)
        self.rig.set_skin("age_filter", age)
        self.helper.update_genre_command()

    def updates(self):
        """
        <summary>The Container.Update builtins issued so far.</summary>
        <returns>A list of the paths inside them.</returns>
        """
        return [b[len("Container.Update("):-1] for b in self.rig.builtins
                if b.startswith("Container.Update(")]

    def test_toggle_adds_a_genre(self):
        """<summary>A name not in force is added to the genres from the path.</summary>"""
        path = xsp_url("videodb://movies/titles/",
                       [{"field": "genre", "operator": "is", "value": ["Comedy"]}])
        self.show(path, name="Drama")
        self.assertEqual(self.updates(), [self.helper._age_node("movies", 0, ["Comedy", "Drama"])])

    def test_toggle_removes_a_genre(self):
        """<summary>A name already in force is taken out.</summary>"""
        path = xsp_url("videodb://movies/titles/",
                       [{"field": "genre", "operator": "is", "value": ["Comedy", "Drama"]}])
        self.show(path, name="Comedy")
        self.assertEqual(self.updates(), [self.helper._age_node("movies", 0, ["Drama"])])

    def test_toggle_from_a_genre_node(self):
        """<summary>The genre of a genres node counts as in force.</summary>"""
        self.show("videodb://movies/genres/1/", name="Drama")
        self.assertEqual(self.updates(), [self.helper._age_node("movies", 0, ["Comedy", "Drama"])])

    def test_toggle_the_last_genre_off(self):
        """<summary>Removing the only genre reloads the bare node.</summary>"""
        self.show("videodb://movies/genres/1/", name="Comedy")
        self.assertEqual(self.updates(), [self.helper.AGE_NODES["movies"]])

    def test_toggle_in_tv_shows_uses_the_tvshows_node(self):
        """<summary>A tvshows path gives a tvshows node.</summary>"""
        self.show("videodb://tvshows/genres/9/", name="Comedy")
        self.assertEqual(self.updates(), [self.helper._age_node("tvshows", 0, ["Sitcom", "Comedy"])])

    def test_toggle_keeps_the_decade(self):
        """<summary>With the switch on, a decade in Skin.String(decade_filter) is passed on.</summary>"""
        T.SKIN_SETTINGS.add("filter_extras")
        self.show("videodb://movies/genres/1/", name="Drama", decade="1990")
        _b, doc = decode(self.updates()[0])
        fields = [r["field"] for r in doc["rules"]["and"]]
        self.assertEqual(fields, ["year", "genre"])
        self.assertEqual(doc["rules"]["and"][0], service.decade_rule("1990"))

    def test_toggle_drops_the_decade_with_the_switch_off(self):
        """<summary>With filter_extras off any decade_filter value is ignored.</summary>"""
        for decade in ("1990", "pre1950"):
            self.rig.clock.now += 10
            self.rig.builtins[:] = []
            self.show("videodb://movies/genres/1/", name="Drama", decade=decade)
            _b, doc = decode(self.updates()[0])
            self.assertEqual([r["field"] for r in doc["rules"]["and"]], ["genre"], decade)

    def test_toggle_ignores_a_bad_decade(self):
        """<summary>A decade string that is not a DECADES value is ignored.</summary>"""
        T.SKIN_SETTINGS.add("filter_extras")
        self.show("videodb://movies/genres/1/", name="Drama", decade="1985")
        _b, doc = decode(self.updates()[0])
        self.assertEqual([r["field"] for r in doc["rules"]["and"]], ["genre"])

    def test_toggle_keeps_title_text(self):
        """<summary>A title rule in the path is carried over.</summary>"""
        path = xsp_url("videodb://movies/titles/", [
            {"field": "genre", "operator": "is", "value": ["Comedy"]},
            {"field": "title", "operator": "contains", "value": ["night"]}])
        self.show(path, name="Drama")
        _b, doc = decode(self.updates()[0])
        self.assertIn({"field": "title", "operator": "contains", "value": ["night"]},
                      doc["rules"]["and"])

    def test_empty_slot_does_nothing(self):
        """<summary>A slot with no label reloads nothing.</summary>"""
        self.show("videodb://movies/genres/1/", command="__toggle__:5")
        self.assertEqual(self.updates(), [])

    def test_bad_slot_numbers_do_nothing(self):
        """<summary>A slot that is not a positive integer reloads nothing.</summary>"""
        self.slot(1, "Drama")
        for bad in ("__toggle__:", "__toggle__:0", "__toggle__:-1", "__toggle__:x", "__toggle__:1.5"):
            self.rig.clock.now += 10
            self.show("videodb://movies/genres/1/", command=bad)
        self.assertEqual(self.updates(), [])

    def test_slot_label_is_the_genre_toggled(self):
        """<summary>The name comes from the slot asked for, not from another slot.</summary>"""
        self.slot(1, "Comedy")
        self.slot(2, "Drama")
        self.show("videodb://movies/genres/1/", command="__toggle__:2")
        self.assertEqual(self.updates(), [self.helper._age_node("movies", 0, ["Comedy", "Drama"])])

    def test_no_genre_toggle_property_is_used(self):
        """<summary>A stale genre_toggle property has no effect.</summary>"""
        T.PROPS["genre_toggle"] = "Drama"
        self.slot(1, "Comedy")
        self.show("videodb://movies/genres/1/")
        self.assertEqual(self.updates(), [self.helper.AGE_NODES["movies"]])

    def test_two_different_slots_in_a_row_both_apply(self):
        """<summary>Two slots toggled in a row with the path unchanged give both genres.</summary>"""
        self.slot(1, "Drama")
        self.slot(2, "action")
        path = "videodb://movies/genres/1/"
        self.show(path, command="__toggle__:1")
        self.show(path, command="__toggle__:2")
        self.assertEqual(len(self.updates()), 2)
        self.assertEqual(self.updates()[1],
                         self.helper._age_node("movies", 0, ["Comedy", "Drama", "action"]))

    def test_pending_genres_are_forgotten_after_the_time(self):
        """<summary>Once GENRE_PENDING_SECS has passed the path's genres are used again.</summary>"""
        self.assertEqual(self.helper.GENRE_PENDING_SECS, 3.0)
        self.slot(1, "Drama")
        self.slot(2, "action")
        path = "videodb://movies/genres/1/"
        self.show(path, command="__toggle__:1")
        self.rig.clock.now += self.helper.GENRE_PENDING_SECS + 1
        self.show(path, command="__toggle__:2")
        self.assertEqual(self.updates()[1], self.helper._age_node("movies", 0, ["Comedy", "action"]))

    def test_pending_genres_still_hold_just_inside_the_time(self):
        """<summary>A toggle inside the time, with the path unchanged, builds on the remembered genres.</summary>"""
        self.slot(1, "Drama")
        self.slot(2, "action")
        path = "videodb://movies/genres/1/"
        self.show(path, command="__toggle__:1")
        self.rig.clock.now += self.helper.GENRE_PENDING_SECS - 1.0
        self.show(path, command="__toggle__:2")
        self.assertEqual(self.updates()[1],
                         self.helper._age_node("movies", 0, ["Comedy", "Drama", "action"]))

    def test_path_catching_up_ends_the_pending_genres(self):
        """<summary>Once the path equals the pending node, the path's genres are used.</summary>"""
        self.slot(1, "Drama")
        self.slot(2, "Drama")
        self.show("videodb://movies/genres/1/", command="__toggle__:1")
        node = self.updates()[0]
        self.rig.clock.now += 1.5
        self.slot(2, "Comedy")
        self.show(node, command="__toggle__:2")
        self.assertEqual(self.updates()[1], self.helper._age_node("movies", 0, ["Drama"]))

    def test_same_slot_twice_within_the_guard_is_taken_once(self):
        """<summary>The same command sent twice inside the guard's second runs once.</summary>"""
        self.slot(1, "Drama")
        path = "videodb://movies/genres/1/"
        self.show(path, command="__toggle__:1")
        self.show(path, command="__toggle__:1")
        self.assertEqual(len(self.updates()), 1)

    def test_plain_name_picks_one_genre(self):
        """<summary>A plain name loads that one genre.</summary>"""
        self.show("videodb://movies/genres/1/", command="Drama")
        self.assertEqual(self.updates(), [self.helper._age_node("movies", 0, "Drama")])

    def test_all_drops_the_genres(self):
        """<summary>__all__ drops the genres and keeps the rest.</summary>"""
        path = xsp_url("videodb://movies/titles/", [
            {"field": "genre", "operator": "is", "value": ["Comedy", "Drama"]}])
        self.show(path, command="__all__")
        self.assertEqual(self.updates(), [self.helper.AGE_NODES["movies"]])

    def test_toggle_constant(self):
        """<summary>GENRE_TOGGLE is the text __toggle__.</summary>"""
        self.assertEqual(self.helper.GENRE_TOGGLE, "__toggle__")


class AgeSyncSpec(unittest.TestCase):
    """<summary>Requirement 7: the age sync in update_age_command.</summary>"""

    def setUp(self):
        """<summary>Install the rig with the videos window active and no command pending.</summary>"""
        self.rig = DecadeRig()
        self.helper = make_helper()
        self.helper._age_last_path = "videodb://movies/titles/"
        self.year = YEAR

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def sync(self, path, age="", decade=""):
        """
        <summary>Shows a new path with the given filter strings and runs the command handler.</summary>
        <param name="path">The folder path now on screen.</param>
        <param name="age">The age_filter before.</param>
        <param name="decade">The decade_filter before.</param>
        """
        self.rig.labels["Container.FolderPath"] = path
        self.rig.set_skin("age_command", "")
        self.rig.set_skin("age_filter", age)
        self.rig.set_skin("decade_filter", decade)
        self.helper.update_age_command()

    def value(self, name):
        """
        <summary>A Skin.String as the rig now holds it.</summary>
        <param name="name">The string's name.</param>
        <returns>The value, or the empty string.</returns>
        """
        return self.rig.labels.get("Skin.String(%s)" % name, "").strip('"')

    def test_lessthan_sets_age_and_clears_decade(self):
        """<summary>A lessthan year rule sets age_filter to years ago and clears decade_filter.</summary>"""
        path = xsp_url("videodb://movies/titles/",
                       [{"field": "year", "operator": "lessthan", "value": [str(self.year - 20)]}])
        self.sync(path, decade="1990")
        self.assertEqual(self.value("age_filter"), "20")
        self.assertEqual(self.value("decade_filter"), "")

    def test_between_sets_decade_and_clears_age(self):
        """<summary>A between year rule sets decade_filter from its values and clears age_filter.</summary>"""
        path = xsp_url("videodb://movies/titles/",
                       [{"field": "year", "operator": "between", "value": ["1970", "1979"]}])
        self.sync(path, age="10")
        self.assertEqual(self.value("decade_filter"), "1970")
        self.assertEqual(self.value("age_filter"), "")

    def test_between_before_1950(self):
        """<summary>The 0 to 1949 rule is the pre1950 decade.</summary>"""
        path = xsp_url("videodb://movies/titles/",
                       [{"field": "year", "operator": "between", "value": ["0", "1949"]}])
        self.sync(path)
        self.assertEqual(self.value("decade_filter"), "pre1950")


class GenrePickSpec(unittest.TestCase):
    """<summary>Requirement 8: FunctionalHelper._genre_pick_publish.</summary>"""

    def setUp(self):
        """<summary>Install the rig with the switch on and a helper with the genre table.</summary>"""
        self.rig = DecadeRig()
        T.SKIN_SETTINGS.add("filter_extras")
        self.helper = make_helper()

    def tearDown(self):
        """<summary>Put the stubs back.</summary>"""
        self.rig.restore()

    def slots(self):
        """
        <summary>The published slots.</summary>
        <returns>A list of (label, ticked) for every slot with a label, in order.</returns>
        """
        out = []
        for n in range(1, 130):
            label = T.PROPS.get("GenrePick.%d.Label" % n, "")
            if label:
                out.append((label, T.PROPS.get("GenrePick.%d.Ticked" % n, "")))
        return out

    def test_max_is_120(self):
        """<summary>GENRE_PICK_MAX is 120.</summary>"""
        self.assertEqual(self.helper.GENRE_PICK_MAX, 120)

    def test_movie_names_sorted_ignoring_case_with_ticks(self):
        """<summary>Movie names are sorted case insensitively and the path's genres are ticked.</summary>"""
        self.helper._genre_pick_publish("videodb://movies/genres/2/")
        self.assertEqual(self.slots(), [("action", ""), ("Comedy", ""), ("Drama", "1")])

    def test_tv_path_uses_tvshow_names(self):
        """<summary>A videodb://tvshows path lists tvshow genres.</summary>"""
        self.helper._genre_pick_publish("videodb://tvshows/genres/9/")
        self.assertEqual(self.slots(), [("Comedy", ""), ("Sitcom", "1")])

    def test_several_ticks_from_a_playlist(self):
        """<summary>Every genre of a playlist's genre rule is ticked.</summary>"""
        url = xsp_url("videodb://movies/titles/",
                      [{"field": "genre", "operator": "is", "value": ["Comedy", "Drama"]}])
        self.helper._genre_pick_publish(url)
        self.assertEqual(self.slots(), [("action", ""), ("Comedy", "1"), ("Drama", "1")])

    def test_slots_beyond_the_list_are_cleared(self):
        """<summary>A shorter list after a longer one leaves no stale slots.</summary>"""
        self.helper._genre_pick_publish("videodb://movies/genres/1/")
        self.assertEqual(len(self.slots()), 3)
        self.helper._genre_pick_publish("videodb://tvshows/genres/1/")
        self.assertEqual(len(self.slots()), 2)
        self.assertEqual(T.PROPS.get("GenrePick.3.Label", ""), "")

    def test_capped_at_the_maximum(self):
        """<summary>More genres than the maximum fill exactly 120 slots.</summary>"""
        self.helper._genre_names = {("movie", i): "Genre %03d" % i for i in range(150)}
        self.helper._genre_pick_publish("videodb://movies/titles/")
        self.assertEqual(len(self.slots()), 120)
        self.assertEqual(T.PROPS.get("GenrePick.120.Label"), "Genre 119")
        self.assertEqual(T.PROPS.get("GenrePick.121.Label", ""), "")

    def test_rewrites_only_on_change(self):
        """<summary>A second call with the same names and ticks writes no property.</summary>"""
        self.helper._genre_pick_publish("videodb://movies/genres/1/")
        writes = []
        original = T._Window.setProperty

        def spy(window, key, value):
            """<summary>Records the write, then makes it.</summary>"""
            writes.append(key)
            original(window, key, value)

        T._Window.setProperty = spy
        try:
            self.helper._genre_pick_publish("videodb://movies/genres/1/")
            self.assertEqual([k for k in writes if k.startswith("GenrePick.")], [])
            self.helper._genre_pick_publish("videodb://movies/genres/2/")
            self.assertTrue([k for k in writes if k.startswith("GenrePick.")])
        finally:
            T._Window.setProperty = original

    def test_switch_off_clears_every_slot(self):
        """<summary>With the switch off the slots written before are cleared.</summary>"""
        self.helper._genre_pick_publish("videodb://movies/genres/1/")
        T.SKIN_SETTINGS.discard("filter_extras")
        self.helper._genre_pick_publish("videodb://movies/genres/1/")
        self.assertEqual(self.slots(), [])
        self.assertEqual([k for k in T.PROPS if k.startswith("GenrePick.") and T.PROPS[k]], [])

    def test_empty_path_clears_every_slot(self):
        """<summary>An empty path clears the slots even with the switch on.</summary>"""
        self.helper._genre_pick_publish("videodb://movies/genres/1/")
        self.helper._genre_pick_publish("")
        self.assertEqual(self.slots(), [])


class SlideOutSpec(unittest.TestCase):
    """<summary>Requirement 9: the XML of the library slide out and the ticking list.</summary>"""

    @classmethod
    def setUpClass(cls):
        """<summary>Parse the page and the includes once.</summary>"""
        cls.nav = parse("MyVideoNav.xml")
        cls.inc = parse("Includes.xml")

    def onclicks(self, cid):
        """
        <summary>The onclick texts of a control with their conditions.</summary>
        <param name="cid">The control id.</param>
        <returns>A list of (condition, text).</returns>
        """
        return [(o.get("condition", ""), (o.text or "").strip())
                for o in control(self.nav, cid).findall("onclick")]

    def test_8013_cannot_show_with_the_switch_off(self):
        """<summary>No state of the other conditions shows button 8013 with filter_extras off.</summary>"""
        visibles = [(v.text or "").strip() for v in control(self.nav, "8013").findall("visible")]
        self.assertIn("Skin.HasSetting(filter_extras)", " ".join(visibles))
        self.assertFalse(self.can_show(visibles, {EXTRAS: False}))

    @staticmethod
    def can_show(visibles, fixed):
        """
        <summary>Whether conditions that must all hold can be true with some atoms held.</summary>
        <param name="visibles">The raw condition texts.</param>
        <param name="fixed">Atom text mapped to the value it is held at.</param>
        <returns>True when some state of the other atoms makes the conditions hold.</returns>
        """
        params = collections.defaultdict(lambda: "p")
        combined = " + ".join("[" + W.expand(v, params) + "]" for v in visibles)
        expr, atoms = H.condition_atoms(combined)
        code = compile(expr, "<condition>", "eval")
        free = [i for i, a in enumerate(atoms) if a not in fixed]
        for combo in itertools.product([False, True], repeat=len(free)):
            v = [fixed.get(a, False) for a in atoms]
            for i, val in zip(free, combo):
                v[i] = val
            if eval(code, {"__builtins__": {}}, {"v": v}):  # noqa: S307 (own generated text)
                return True
        return False

    def test_8013_label(self):
        """<summary>The label is the Decade string then the decade variable.</summary>"""
        self.assertEqual(control(self.nav, "8013").findtext("label").strip(),
                         "$LOCALIZE[31967] $VAR[DecadeFilterLabel]")

    def test_8013_cycle_order(self):
        """<summary>Clicks step from empty through 2020 to pre1950 and then reset.</summary>"""
        clicks = self.onclicks("8013")
        steps = []
        for cond, text in clicks:
            m = re.fullmatch(r"String\.(IsEmpty|IsEqual)\(Skin\.String\(decade_filter\)(?:,(\w+))?\)", cond)
            if m:
                steps.append((m.group(2) or "", text))
        order = ["", "2020", "2010", "2000", "1990", "1980", "1970", "1960", "1950", "pre1950"]
        expected = [(a, "Skin.SetString(decade_filter,%s)" % b) for a, b in zip(order, order[1:])]
        expected.append(("pre1950", "Skin.Reset(decade_filter)"))
        self.assertEqual(steps, expected)

    def test_8013_resets_age_then_applies(self):
        """<summary>After the cycle comes Skin.Reset(age_filter), then the two age_command lines.</summary>"""
        texts = [t for _c, t in self.onclicks("8013")]
        reset = texts.index("Skin.Reset(decade_filter)")
        self.assertEqual(texts[reset + 1], "Skin.Reset(age_filter)")
        self.assertEqual(texts[reset + 2:], ["Skin.SetString(age_command,apply_tvshows)",
                                             "Skin.SetString(age_command,apply_movies)"])
        conds = [c for c, _t in self.onclicks("8013")][-2:]
        self.assertEqual(conds, ["Container.Content(tvshows)", "!Container.Content(tvshows)"])

    def test_8007_always_resets_decade(self):
        """<summary>Age has an unconditional Skin.Reset(decade_filter) onclick.</summary>"""
        self.assertIn(("", "Skin.Reset(decade_filter)"), self.onclicks("8007"))

    def test_menu_navigation_chain(self):
        """<summary>8007 down 8013, 8013 up 8007 and down 8012, 8012 up 8013.</summary>"""
        def nav(cid, key):
            """<summary>A control's navigation target.</summary>"""
            return control(self.nav, cid).findtext(key).strip()
        self.assertEqual(nav("8007", "ondown"), "8013")
        self.assertEqual(nav("8013", "onup"), "8007")
        self.assertEqual(nav("8013", "ondown"), "8012")
        self.assertEqual(nav("8012", "onup"), "8013")

    def test_ticking_list_9505(self):
        """<summary>List 9505 is in GenrePickerTicked and visible only with filter_extras on and slot 1 filled.</summary>"""
        holder = next(i for i in self.inc.iter("include") if i.get("name") == "GenrePickerTicked")
        lst = control(holder, "9505")
        self.assertIsNotNone(lst)
        self.assertEqual(lst.get("type"), "list")
        visible = lst.findtext("visible").strip()
        self.assertEqual(visible, "Skin.HasSetting(filter_extras) + "
                                  "!String.IsEmpty(Window(home).Property(GenrePick.1.Label))")
        self.assertFalse(self.can_show([visible], {SLOT1_EMPTY: True}))
        self.assertFalse(self.can_show([visible], {EXTRAS: False}))
        self.assertTrue(self.can_show([visible], {EXTRAS: True, SLOT1_EMPTY: False}))
        include_calls = [i for i in self.nav.iter("include") if i.get("content") == "GenrePickerTicked"]
        self.assertTrue(include_calls)

    def test_ticking_list_has_120_static_items(self):
        """<summary>The list holds GenrePickItem for n 1 to 120.</summary>"""
        holder = next(i for i in self.inc.iter("include") if i.get("name") == "GenrePickerTicked")
        lst = control(holder, "9505")
        content = lst.find("content")
        calls = []
        if content is not None:
            calls = [i for i in content.iter("include")]
        ns = []
        for call in calls:
            if call.get("content") == "GenrePickItem":
                ns.append(int(call.find("param").get("value")))
            elif call.get("content") == "GenrePickItems" or (call.text or "").strip() == "GenrePickItems":
                items = next(i for i in self.inc.iter("include") if i.get("name") == "GenrePickItems")
                ns = [int(i.find("param").get("value")) for i in items.iter("include")
                      if i.get("content") == "GenrePickItem"]
        if not ns:
            items = next(i for i in self.inc.iter("include") if i.get("name") == "GenrePickItems")
            ns = [int(i.find("param").get("value")) for i in items.iter("include")
                  if i.get("content") == "GenrePickItem"]
            self.assertTrue(re.search(r"GenrePickItems", ET.tostring(lst, encoding="unicode")))
        self.assertEqual(ns, list(range(1, 121)))

    def test_pick_item_reads_slots_and_toggles(self):
        """<summary>Each item takes label and ticked from the slot and its one click sends the toggle with its slot number.</summary>"""
        item = next(i for i in self.inc.iter("include") if i.get("name") == "GenrePickItem").find(".//item")
        self.assertEqual(item.findtext("label").strip(),
                         "$INFO[Window(home).Property(GenrePick.$PARAM[n].Label)]")
        prop = item.find("property")
        self.assertEqual(prop.get("name"), "ticked")
        self.assertEqual(prop.text.strip(), "$INFO[Window(home).Property(GenrePick.$PARAM[n].Ticked)]")
        clicks = [(o.text or "").strip() for o in item.findall("onclick")]
        self.assertEqual(clicks, ["Skin.SetString(genre_command,__toggle__:$PARAM[n])"])

    def test_no_genre_toggle_property_in_the_skin(self):
        """<summary>No XML file sets or reads a genre_toggle property.</summary>"""
        for name in sorted(os.listdir(XML)):
            if name.endswith(".xml"):
                with open(os.path.join(XML, name), encoding="utf-8") as fh:
                    self.assertNotIn("genre_toggle", fh.read(), name)

    def test_old_lists_stand_in_until_the_slots_are_filled(self):
        """<summary>Lists 9500 and 9501 cannot show with the switch on and slot 1 filled, and can otherwise.</summary>"""
        calls = {c.find("param[@name='id']").get("value"): c for c in self.nav.iter("include")
                 if c.get("content") == "GenrePickerList"}
        for cid in ("9500", "9501"):
            visible = calls[cid].find("param[@name='visible']").get("value")
            self.assertFalse(self.can_show([visible], {EXTRAS: True, SLOT1_EMPTY: False}), cid)
            self.assertTrue(self.can_show([visible], {EXTRAS: False}), cid)
            self.assertTrue(self.can_show([visible], {EXTRAS: True, SLOT1_EMPTY: True}), cid)

    def test_8005_focus_follows_the_same_split(self):
        """<summary>The focus onclicks of 8005 send focus to 9505 only when 9505 shows, else to 9500 or 9501.</summary>"""
        clicks = {(o.text or "").strip(): o.get("condition", "") for o in control(self.nav, "8005").findall("onclick")}
        # Opens on the list's first row (SetFocus with position 0).
        ticked = clicks["SetFocus(9505,0)"]
        self.assertFalse(self.can_show([ticked], {EXTRAS: False}))
        self.assertFalse(self.can_show([ticked], {SLOT1_EMPTY: True}))
        for target in ("SetFocus(9500)", "SetFocus(9501)"):
            plain = clicks[target]
            self.assertFalse(self.can_show([plain], {EXTRAS: True, SLOT1_EMPTY: False}), target)
            self.assertTrue(self.can_show([plain], {EXTRAS: False}), target)


if __name__ == "__main__":
    unittest.main(verbosity=1)
