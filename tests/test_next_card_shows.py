#!/usr/bin/env python3
"""
<summary>
Tests for the per show choice of the next episode card (roadmap item 17,
phase E2): the key a show is kept under, shows.json read, written and set
aside when damaged, how a show's choice bends the Playback page's rule, the
card's lookup honouring it, the picker the info screen's Next Card button
opens, and the button itself.
</summary>
<remarks>
No Kodi is needed. The pretend box, player and threads come from
tests/test_next_episode_card.py, and through it the Kodi stubs and the real
service.py from tests/test_lists_api.py, whose temporary profile holds the
shows.json these tests write. How the button and the picker look is the
live check's job. Exits non zero when a check fails.

Usage:
    python3 tests/test_next_card_shows.py
</remarks>
"""

import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_next_episode_card as N  # noqa: E402  (stubs, service and the pretend box)

service = N.service
T = N.T
XML = N.XML
FAILURES = []
SHOWS = os.path.join(T.PROFILE, "addon_data", "skin.functional", "shows.json")


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def aside_files():
    """<summary>The set aside copies of a damaged shows.json.</summary><returns>Sorted names.</returns>"""
    folder = os.path.dirname(SHOWS)
    if not os.path.isdir(folder):
        return []
    return sorted(n for n in os.listdir(folder) if n.startswith("shows.json.bad"))


def clear_store():
    """<summary>Start with no shows.json, no part file and nothing set aside.</summary>"""
    folder = os.path.dirname(SHOWS)
    for name in ["shows.json", "shows.json.part"] + aside_files():
        path = os.path.join(folder, name)
        if os.path.exists(path):
            os.remove(path)  # the test profile's own files, made by these tests


def write_raw(text):
    """<summary>Put a shows.json in place by hand, as a user editing it would.</summary>"""
    os.makedirs(os.path.dirname(SHOWS), exist_ok=True)
    with open(SHOWS, "w", encoding="utf-8") as handle:
        handle.write(text)


def read_doc():
    """<summary>shows.json as written.</summary><returns>The parsed document.</returns>"""
    with open(SHOWS, encoding="utf-8") as handle:
        return json.load(handle)


def helper():
    """<summary>A fresh helper built against the stubs' own answers.</summary><returns>It.</returns>"""
    service.xbmc.getCondVisibility, service.xbmc.getInfoLabel = N.STUB_COND, N.STUB_LABEL
    return service.FunctionalHelper()


def test_pure():
    """
    <summary>show_keys, show_choice, set_show_choice and show_card_rule on
    their own: key order and the all noughts id, a choice found under any
    key and moved to the first, other records and fields left alone.</summary>
    """
    print("running test_pure")
    keys = service.show_keys
    if keys({"imdb": "tt1", "tmdb": "2", "tvdb": "3"}, "X", 2020) != ["tvdb:3", "tmdb:2", "imdb:tt1", "title:x|2020"]:
        fail("keys should run TVDB, TMDb, IMDb, then the title")
    if keys({"tvdb": "0", "tmdb": "00", "imdb": ""}, "X", 0) != ["title:x|0"]:
        fail("an id of noughts or nothing is no id")
    if keys(None, "", 0) != [] or service.show_key(None, "", 0) is not None:
        fail("with no ids and no title there should be no key")
    if service.show_key({"tmdb": "7"}, " Breaking Bad ", "2008") != "tmdb:7":
        fail("the first key should be the best id")

    doc = {"version": 3, "extra": {"keep": True}, "shows": {
        "tmdb:7": {"title": "Old", "next_card": "inorder", "skip": "intro"},
        "tvdb:5": "not a record",
        "tvdb:6": {"title": "Typo", "next_card": "Off"},
    }}
    k = ["tvdb:9", "tmdb:7", "title:old|0"]
    if service.show_choice(doc, k) != "inorder":
        fail("a choice kept under a show's second key should be found")
    if service.show_choice(doc, ["tvdb:6"]) is not None:
        fail("a mistyped choice should read as none, not as a choice")
    service.set_show_choice(doc, k, "Old", "off")
    if doc["shows"].get("tvdb:9") != {"title": "Old", "next_card": "off"}:
        fail("a new choice should go under the first key, got %r" % doc["shows"].get("tvdb:9"))
    if doc["shows"].get("tmdb:7") != {"title": "Old", "skip": "intro"}:
        fail("the old key should lose its choice and keep phase F's field, got %r" % doc["shows"].get("tmdb:7"))
    if doc["shows"].get("tvdb:5") != "not a record" or doc["shows"].get("tvdb:6") != {"title": "Typo", "next_card": "Off"}:
        fail("records of other shows, readable or not, should be left exactly as they were")
    if doc.get("version") != 3 or doc.get("extra") != {"keep": True}:
        fail("top level keys should be left exactly as they were")
    service.set_show_choice(doc, k, "Old", None)
    if "tvdb:9" in doc["shows"]:
        fail("the default should drop a record left with only its title")
    for bad in ("[]", '{"version": 1}', "not json"):
        try:
            service.parse_show_doc(bad)
            fail("%r should be refused" % bad)
        except ValueError:
            pass
    if service.parse_show_doc('\ufeff{"shows": {}}') != {"shows": {}}:
        fail("a byte order mark should be allowed")

    rule = service.show_card_rule
    for glob, choice, want in (("", "inorder", ""), ("", None, ""), ("unwatched", "off", ""),
                               ("unwatched", "inorder", "inorder"), ("inorder", "unwatched", "unwatched"),
                               ("inorder", None, "inorder"), ("unwatched", "junk", "unwatched")):
        if rule(glob, choice) != want:
            fail("show_card_rule(%r, %r) should be %r" % (glob, choice, want))


def test_store():
    """
    <summary>shows.json through the helper: written and read back, a save
    keeps everything else in the file, a hand edit while running is seen
    before the next save, every damaged file is set aside under its own
    name, a file that cannot be set aside is never written over, and a
    failed write is reported and forgotten.</summary>
    """
    print("running test_store")
    clear_store()
    h = helper()
    K = ["tvdb:9", "title:nine|0"]
    if h._show_choice(K) is not None:
        fail("with no file every show should have no choice")
    if not h._show_choice_set(K, "Nine", "inorder") or not os.path.isfile(SHOWS) or os.path.exists(SHOWS + ".part"):
        fail("shows.json was not written, or its part file was left behind")
    if helper()._show_choice(K) != "inorder":
        fail("a new helper did not read the choice back")

    write_raw(json.dumps({"version": 2, "extra": 1, "shows": {
        "tvdb:9": {"title": "Nine", "next_card": "inorder", "skip": "intro"},
        "tvdb:4": "junk", "tvdb:6": {"title": "Typo", "next_card": "Off"}}}))
    if h._show_choice(K) != "inorder":
        fail("a hand edit made while running was not read")
    h._show_choice_set(K, "Nine", None)
    doc = read_doc()
    if doc.get("version") != 2 or doc.get("extra") != 1:
        fail("a save lost or changed a top level key: %r" % doc)
    if doc["shows"].get("tvdb:9") != {"title": "Nine", "skip": "intro"}:
        fail("the default should drop the choice and keep phase F's field, got %r" % doc["shows"].get("tvdb:9"))
    if doc["shows"].get("tvdb:4") != "junk" or doc["shows"].get("tvdb:6") != {"title": "Typo", "next_card": "Off"}:
        fail("a save lost or changed another show's record")

    write_raw("{ damaged once")
    if h._show_choice(K) is not None or len(aside_files()) != 1 or os.path.exists(SHOWS):
        fail("a damaged file should read as empty and be set aside")
    h._show_choice_set(K, "Nine", "off")
    write_raw("{ damaged twice")
    h._show_choice(K)
    if len(aside_files()) != 2:
        fail("a second damaged file should be set aside under its own name, got %r" % aside_files())
    else:
        firsts = []
        for name in aside_files():
            with open(os.path.join(os.path.dirname(SHOWS), name), encoding="utf-8") as handle:
                firsts.append(handle.read())
        if sorted(firsts) != ["{ damaged once", "{ damaged twice"]:
            fail("a set aside copy was written over: %r" % firsts)

    clear_store()
    write_raw("{ damaged, cannot move")
    real_rename = service.os.rename
    try:
        def no_rename(*_a):
            """<summary>A rename that fails, as on a read only folder.</summary>"""
            raise OSError("read only")
        service.os.rename = no_rename
        h2 = helper()
        ok = h2._show_choice_set(K, "Nine", "off")
    finally:
        service.os.rename = real_rename
    with open(SHOWS, encoding="utf-8") as handle:
        if ok or handle.read() != "{ damaged, cannot move":
            fail("a damaged file that could not be set aside was written over")

    clear_store()
    h3 = helper()
    real_replace = service.os.replace
    try:
        def no_replace(*_a):
            """<summary>A replace that fails, as on a full disc.</summary>"""
            raise OSError("disc full")
        service.os.replace = no_replace
        ok = h3._show_choice_set(K, "Nine", "inorder")
    finally:
        service.os.replace = real_replace
    if ok or h3._show_choice(K) is not None:
        fail("a failed write should report False and leave no choice in memory")
    clear_store()


def run_card(choice, global_rule):
    """
    <summary>One start of S1E2 of show 31 with the show's choice set, then a
    tick at the credits.</summary>
    <param name="choice">The show's stored choice, or None.</param>
    <param name="global_rule">Skin.String(next_card).</param>
    <returns>(box, helper) after the tick.</returns>
    """
    clear_store()
    if choice:
        helper()._show_choice_set(["tvdb:31031"], "Show", choice)
    box = N.Box()
    box.labels["Skin.String(next_card)"] = global_rule
    h = N.install(box)
    N.start(h)
    box.time = N.LIVE_TOTAL - 10
    h.update_next_card()
    return box, h


def test_lookup():
    """
    <summary>The card's lookup follows the show's choice: no card for "off",
    In Order over a global Unwatched, Unwatched over a global In Order, and
    nothing at all with the Playback switch off whatever the show says.</summary>
    """
    print("running test_lookup")
    saved = (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
             service.xbmc.Player, getattr(service.xbmcgui, "WindowXMLDialog", None), service.threading.Thread)
    try:
        box, _h = run_card("off", "unwatched")
        if N.lookups(box) or box.cards:
            fail("a show set to No Card looked episodes up or got a card")
        box, _h = run_card("inorder", "unwatched")
        if len(box.cards) != 1 or box.cards[0].props.get("NextCard.Marker") != "S1E3":
            fail("a show set to In Order should offer S1E3 over the global Unwatched")
        box, _h = run_card("unwatched", "inorder")
        if len(box.cards) != 1 or box.cards[0].props.get("NextCard.Marker") != "S2E1":
            fail("a show set to Unwatched should offer S2E1 over the global In Order")
        box, _h = run_card("inorder", "")
        if any(m.startswith("VideoLibrary.") for m, _ in box.rpc) or box.cards:
            fail("with the switch off a show's own choice should not bring the card back")
        box, _h = run_card(None, "unwatched")
        if len(box.cards) != 1 or box.cards[0].props.get("NextCard.Marker") != "S2E1":
            fail("a show with no choice should follow the global rule")
    finally:
        (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
         service.xbmc.Player, wxd, service.threading.Thread) = saved
        if wxd is None:
            del service.xbmcgui.WindowXMLDialog
        else:
            service.xbmcgui.WindowXMLDialog = wxd
        clear_store()


def test_picker():
    """
    <summary>The Next Card button's command opens the picker for that show,
    a junk command opens nothing, the current choice is preselected, the
    default line names the Playback page's choice, and the answer is kept.</summary>
    """
    print("running test_picker")
    saved = (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
             service.xbmc.Player, getattr(service.xbmcgui, "WindowXMLDialog", None),
             service.threading.Thread, service.xbmcgui.Dialog)
    asked = []

    class Dialog:
        """<summary>A select dialog that records what it was asked and answers from the list.</summary>"""
        answers = []

        def select(self, heading, options, preselect=0, **_kw):
            """<summary>Record the question; answer the next queued choice.</summary><returns>The index.</returns>"""
            asked.append((heading, list(options), preselect))
            return Dialog.answers.pop(0)

    try:
        clear_store()
        box = N.Box()
        box.labels["Skin.String(next_card)"] = "unwatched"
        box.labels["Skin.String(next_card_command)"] = "show:31"
        h = N.install(box)
        service.xbmcgui.Dialog = Dialog
        Dialog.answers = [2]
        h.update_next_card_command()
        if len(asked) != 1:
            fail("the button's command did not open the picker")
        else:
            heading, options, pre = asked[0]
            if "Show" not in heading or len(options) != 4 or "Unwatched" not in options[0] or pre != 0:
                fail("the picker should name the show, offer four lines with the default naming Unwatched, and start on it; got %r" % (asked[0],))
        if h._show_choice(["tvdb:31031"]) != "inorder":
            fail("choosing In Order was not kept")
        h._dialog_thread = None
        box.labels["Skin.String(next_card_command)"] = ""
        h.update_next_card_command()
        box.labels["Skin.String(next_card_command)"] = "show:31"
        Dialog.answers = [0]
        h.update_next_card_command()
        if len(asked) != 2 or asked[1][2] != 2:
            fail("the picker should start on the show's current choice, In Order")
        if h._show_choice(["tvdb:31031"]) is not None:
            fail("choosing the default should drop the show's choice")
        h._dialog_thread = None
        box.labels["Skin.String(next_card_command)"] = ""
        h.update_next_card_command()
        box.labels["Skin.String(next_card)"] = "inorder"
        box.labels["Skin.String(next_card_command)"] = "show:31"
        Dialog.answers = [-1]
        h.update_next_card_command()
        if len(asked) != 3 or "In Order" not in asked[2][1][0]:
            fail("with In Order on the Playback page the default line should name it")
        if h._show_choice(["tvdb:31031"]) is not None:
            fail("cancelling the picker should change nothing")
        box.labels["Skin.String(next_card)"] = "unwatched"
        for junk in ("show:", "show:x", "film:3", "show:-4"):
            h._dialog_thread = None
            box.labels["Skin.String(next_card_command)"] = ""
            h.update_next_card_command()
            box.labels["Skin.String(next_card_command)"] = junk
            h.update_next_card_command()
        if len(asked) != 3:
            fail("a junk command opened the picker")
    finally:
        (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
         service.xbmc.Player, wxd, service.threading.Thread, service.xbmcgui.Dialog) = saved
        if wxd is None:
            del service.xbmcgui.WindowXMLDialog
        else:
            service.xbmcgui.WindowXMLDialog = wxd
        clear_store()


def test_button():
    """
    <summary>The Next Card button: in the info screen's button row, shown
    only on a show and only with the card switched on, sending the show's
    id, with its label, and the row still fitting with all eight buttons.</summary>
    """
    print("running test_button")
    root = ET.fromstring(N.read(os.path.join(XML, "DialogVideoInfo.xml")))
    row = next((c for c in root.iter("control") if c.get("id") == "9000"), None)
    button = next((c for c in root.iter("control") if c.get("id") == "9352"), None)
    if row is None or button is None or button not in list(row):
        fail("button 9352 is not in the info screen's button row 9000")
        return
    if button.findtext("visible") != "String.IsEqual(ListItem.DBType,tvshow) + !String.IsEmpty(Skin.String(next_card))":
        fail("the button should show only on a show and only with the card on, so the screen is unchanged while off")
    if button.findtext("onclick") != "Skin.SetString(next_card_command,show:$INFO[ListItem.DBID])":
        fail("the button should send show: and the show's library id")
    if "$LOCALIZE[31852]" != button.findtext("label") or 'msgctxt "#31852"' not in N.read(N.STRINGS):
        fail("the button's label is missing")
    buttons = [c for c in row if c.tag == "control" and c.get("type") == "button"]
    used = sum(int(b.findtext("width")) for b in buttons) + int(row.findtext("itemgap")) * (len(buttons) - 1)
    if used > int(row.findtext("width")):
        fail("the button row needs %d but has %s" % (used, row.findtext("width")))


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_pure()
    test_store()
    test_lookup()
    test_picker()
    test_button()
    if FAILURES:
        print("test_next_card_shows: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_next_card_shows: all checks passed")


if __name__ == "__main__":
    main()
