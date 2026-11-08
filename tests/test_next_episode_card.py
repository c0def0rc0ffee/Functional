#!/usr/bin/env python3
"""
<summary>
Tests for the next episode card (roadmap item 17, phase E1): when the card
goes up (the first chapter in the closing window or a set time before the
end, whichever is earlier), which episode it offers (next unwatched or next
in order, never a special), the service path from a start through the
lookup to the card and Play Now, every case that gets no card (switch off,
live TV, not a library episode, a queue with a next item, a menu open), the
card coming down when playback stops or the switch goes off, the dialog's
XML, and the two settings rows with their help lines and preview form.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py, as in test_start_badge.py. Threads are run at once
and the dialog is a stand in, so the whole path can be driven tick by tick.
What the card looks like, that Kodi gives it the focus, and which keys still
reach the player are the live check's job. Exits non zero when a check
fails.

Usage:
    python3 tests/test_next_episode_card.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
STRINGS = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
CARD_XML = "script-functional-nextcard.xml"
FAILURES = []
# The stubs' own answers, put back before each helper is built.
STUB_COND, STUB_LABEL = service.xbmc.getCondVisibility, service.xbmc.getInfoLabel

# Seen live 08/11/2026 on a Jellyfin episode: 3635 s, three chapters given
# as four positions, the credits chapter at 93.25% (about 4 minutes from the
# end) and a short one at 98.5%.
LIVE_TOTAL = 3635.0
LIVE_CHAPTERS = "0.00000,93.25053,93.25053,98.50447"


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def read(path):
    """
    <summary>Reads a text file.</summary>
    <param name="path">The path.</param>
    <returns>The text.</returns>
    """
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_timing():
    """
    <summary>parse_chapter_starts and next_card_at on the live episode and
    on the edge cases: no chapters, a bad label, a late sting only, the last
    act of a short episode, the 92% watched point on short ones, and a
    runtime too short for a card.</summary>
    """
    print("running test_timing")
    starts = service.parse_chapter_starts(LIVE_CHAPTERS, LIVE_TOTAL)
    if len(starts) != 2 or abs(starts[0] - LIVE_TOTAL * 0.9325053) > 0.01:
        fail("the live chapter label should give two starts above zero, got %r" % starts)
    if service.parse_chapter_starts("", LIVE_TOTAL) or service.parse_chapter_starts("0,50,x", LIVE_TOTAL):
        fail("an empty or broken chapter label should give no starts")
    if service.parse_chapter_starts(LIVE_CHAPTERS, 0):
        fail("an unknown runtime should give no starts")
    at = service.next_card_at(LIVE_TOTAL, starts, 60)
    if at is None or abs(at - starts[0]) > 0.01:
        fail("on the live episode the card should go up at the credits chapter, got %r" % at)
    if service.next_card_at(LIVE_TOTAL, [], 60) != LIVE_TOTAL - 60:
        fail("with no chapters the card should go up 60 s before the end")
    if service.next_card_at(LIVE_TOTAL, [LIVE_TOTAL - 30], 60) != LIVE_TOTAL - 60:
        fail("a sting 30 s from the end should not hold the card back past the fallback")
    short = 1320.0
    if service.next_card_at(short, [short - 200], 90) != short - 90:
        fail("the last act of a 22 minute episode, 200 s out, was taken for its credits")
    if service.next_card_at(short, [short - 100], 30) != short - 100:
        fail("a chapter 100 s from the end of a 22 minute episode should bring the card forward")
    if abs(service.next_card_at(short, [short - 120], 30) - short * 0.92) > 0.01:
        fail("a chapter before 92% of the runtime should not bring the card before Kodi's watched point")
    if abs(service.next_card_at(660.0, [], 120) - 660.0 * 0.92) > 0.01:
        fail("on an 11 minute cartoon a 2 minute fallback should be cut to the 92% watched point")
    if service.next_card_at(100, [], 60) is not None or service.next_card_at(0, [], 60) is not None:
        fail("a runtime too short or unknown should get no card")


def test_pick():
    """
    <summary>pick_next_episode: next unwatched skips what has been seen,
    next in order does not, specials never count, seasons follow on, and
    nothing after the last episode or a special playing gives None.</summary>
    """
    print("running test_pick")
    eps = [
        {"episodeid": 1, "season": 1, "episode": 1, "playcount": 1},
        {"episodeid": 2, "season": 1, "episode": 2, "playcount": 0},
        {"episodeid": 3, "season": 1, "episode": 3, "playcount": 1},
        {"episodeid": 4, "season": 2, "episode": 1, "playcount": 0},
        {"episodeid": 9, "season": 0, "episode": 1, "playcount": 0},
    ]
    pick = service.pick_next_episode
    if (pick(eps, 1, 2, "unwatched") or {}).get("episodeid") != 4:
        fail("next unwatched after S1E2 should skip the watched S1E3 to S2E1")
    if (pick(eps, 1, 2, "inorder") or {}).get("episodeid") != 3:
        fail("next in order after S1E2 should be S1E3, watched or not")
    if (pick(list(reversed(eps)), 1, 1, "inorder") or {}).get("episodeid") != 2:
        fail("the pick should not depend on the order the library returns")
    if pick(eps, 2, 1, "inorder") is not None:
        fail("nothing comes after the last episode, specials included")
    if pick(eps, 0, 1, "inorder") is not None:
        fail("a special playing should get no card")


class Box:
    """
    <summary>A pretend box: the conditions and info labels the card asks for, and a player.</summary>
    <remarks>Answers the service's compound conditions term by term and
    raises on a term it does not know, so a test fails if the code starts
    asking something these tests do not model.</remarks>
    """

    def __init__(self):
        """<summary>Switch off, a library episode S1E2 of show 31 playing in fullscreen.</summary>"""
        self.labels = {
            "Skin.String(next_card)": "",
            "Skin.String(next_card_secs)": "",
            "VideoPlayer.TvShowDBID": "31",
            "VideoPlayer.Season": "1",
            "VideoPlayer.Episode": "2",
            "Player.Chapters": LIVE_CHAPTERS,
            "Playlist.Length(video)": "1",
            "Playlist.Position(video)": "1",
        }
        self.flags = {
            "Player.HasVideo": True,
            "VideoPlayer.Content(livetv)": False,
            "Window.IsActive(fullscreenvideo)": True,
            "System.HasActiveModalDialog": False,
            "Window.IsActive(videoosd)": False,
            "Window.IsActive(seekbar)": False,
            "Window.IsActive(fullscreeninfo)": False,
            "Player.Paused": False,
        }
        self.time = 10.0
        self.total = LIVE_TOTAL
        self.rpc = []
        self.cards = []
        self.choice = ""

    def cond(self, text):
        """
        <summary>getCondVisibility for "a + b + !c".</summary>
        <param name="text">The condition.</param>
        <returns>Whether every term holds.</returns>
        """
        result = True
        for term in (t.strip() for t in text.split("+")):
            neg = term.startswith("!")
            key = term[1:] if neg else term
            if key not in self.flags:
                raise AssertionError("the card asked an unexpected condition: %r" % key)
            result = result and (self.flags[key] != neg)
        return result

    def label(self, text):
        """
        <summary>getInfoLabel over the box.</summary>
        <param name="text">The label.</param>
        <returns>Its value.</returns>
        """
        if text not in self.labels:
            raise AssertionError("the card asked an unexpected label: %r" % text)
        return self.labels[text]

    def jsonrpc(self, method, params=None):
        """
        <summary>A library with S1E1 to S1E3 and S2E1 of show 31, S1E3 watched; records every call.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        self.rpc.append((method, params))
        if method == "VideoLibrary.GetTVShowDetails":
            # E2 reads the show's key before the episodes; show 31 has a TVDB
            # id, and any other id is a show the library does not have.
            if (params or {}).get("tvshowid") != 31:
                return {"result": {}}
            return {"result": {"tvshowdetails": {"title": "Show", "year": 2024,
                                                 "uniqueid": {"tvdb": "31031"}}}}
        if method == "VideoLibrary.GetEpisodes":
            eps = [
                {"episodeid": 101, "season": 1, "episode": 1, "playcount": 1, "title": "One"},
                {"episodeid": 102, "season": 1, "episode": 2, "playcount": 0, "title": "Two"},
                {"episodeid": 103, "season": 1, "episode": 3, "playcount": 1, "title": "Three"},
                {"episodeid": 201, "season": 2, "episode": 1, "playcount": 0, "title": "Four",
                 "resume": {"position": 300.0}, "showtitle": "Show", "art": {"thumb": "t.jpg"}},
            ]
            return {"result": {"episodes": eps}}
        return {"result": "OK"}


def install(box):
    """
    <summary>Wire the service to the box: conditions, labels, JSON-RPC, a
    player, threads that run at once, and a stand in for the dialog.</summary>
    <param name="box">The Box.</param>
    <returns>A fresh FunctionalHelper.</returns>
    <remarks>The helper is built first, against the stubs' own answers,
    since its constructor asks about settings the card never reads.</remarks>
    """
    service.xbmc.getCondVisibility, service.xbmc.getInfoLabel = STUB_COND, STUB_LABEL
    helper = service.FunctionalHelper()
    service.xbmc.getCondVisibility = box.cond
    service.xbmc.getInfoLabel = box.label
    service._jsonrpc = box.jsonrpc

    class Player:
        """<summary>The box's player.</summary>"""

        def getTime(self):  # noqa: N802 (Kodi API)
            """<summary>Playing time.</summary><returns>Seconds.</returns>"""
            return box.time

        def getTotalTime(self):  # noqa: N802 (Kodi API)
            """<summary>Runtime.</summary><returns>Seconds.</returns>"""
            return box.total

        def isPlaying(self):  # noqa: N802 (Kodi API)
            """<summary>Whether a video is playing.</summary><returns>The box's flag.</returns>"""
            return box.flags["Player.HasVideo"]

    class Thread:
        """<summary>A thread that runs its target as soon as it is started.</summary>"""

        def __init__(self, target=None, args=(), **_kw):
            """<summary>Keep the target.</summary>"""
            self.target, self.args = target, args

        def start(self):
            """<summary>Run the target now.</summary>"""
            self.target(*self.args)

        def is_alive(self):
            """<summary>Never still running.</summary><returns>False.</returns>"""
            return False

    class Dialog:
        """<summary>Stands in for WindowXMLDialog: records the card and returns the box's choice.</summary>"""

        def __init__(self, *args, **_kw):
            """<summary>Record the file the card was opened from.</summary>"""
            self.props = {}
            self.args = args
            self.choice = ""
            self.closed = False

        def setProperty(self, key, value):  # noqa: N802 (Kodi API)
            """<summary>Keep a property for the test to read.</summary>"""
            self.props[key] = value

        def doModal(self):  # noqa: N802 (Kodi API)
            """<summary>Record the card and take the box's choice.</summary>"""
            box.cards.append(self)
            self.choice = box.choice

        def close(self):
            """<summary>Note the close.</summary>"""
            self.closed = True

    service.xbmc.Player = Player
    service.xbmcgui.WindowXMLDialog = Dialog
    service.threading.Thread = Thread
    return helper


def start(helper):
    """<summary>Delivers Player.OnAVStart the way Kodi does, then one tick.</summary>"""
    helper.onNotification("xbmc", "Player.OnAVStart", "{}")
    helper.update_next_card()


def lookups(box):
    """<summary>How many episode lookups the box has seen.</summary><returns>The count.</returns>"""
    return sum(1 for m, _ in box.rpc if m == "VideoLibrary.GetEpisodes")


def test_service():
    """
    <summary>Drives update_next_card: off by default does nothing, a start
    with the switch on looks the next episode up, the card waits for its
    time and for the fullscreen video with nothing open, Play Now opens the
    next episode with its resume point, Back plays nothing, and every case
    that should get no card gets none.</summary>
    """
    print("running test_service")
    saved = (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
             service.xbmc.Player, getattr(service.xbmcgui, "WindowXMLDialog", None), service.threading.Thread)
    try:
        # Off by default: a start does nothing, no lookup and no card, ever.
        box = Box()
        h = install(box)
        if box.labels["Skin.String(next_card)"]:
            fail("the test box should start with the card off")
        start(h)
        box.time = LIVE_TOTAL - 100
        for _ in range(3):
            h.update_next_card()
        if lookups(box) or box.cards:
            fail("with the switch off a start looked an episode up or put a card up")

        # On, next unwatched: lookup on start, nothing before the credits chapter.
        box = Box()
        box.labels["Skin.String(next_card)"] = "unwatched"
        h = install(box)
        h.onNotification("xbmc", "Player.OnAVStart", "{}")
        if lookups(box):
            fail("the notification thread looked the episode up itself")
        h.update_next_card()
        if lookups(box) != 1:
            fail("a start with the switch on did not look the next episode up")
        box.time = LIVE_TOTAL * 0.93
        h.update_next_card()
        if box.cards:
            fail("the card went up before the credits chapter")
        box.flags["Window.IsActive(videoosd)"] = True
        box.time = LIVE_TOTAL * 0.94
        h.update_next_card()
        if box.cards:
            fail("the card went up over the open OSD")
        box.flags["Window.IsActive(videoosd)"] = False
        box.choice = "play"
        h.update_next_card()
        if len(box.cards) != 1:
            fail("the card did not go up at the credits chapter once the OSD closed")
        else:
            card = box.cards[0]
            if card.args[0] != CARD_XML:
                fail("the card was not opened from %s" % CARD_XML)
            if card.props.get("NextCard.Marker") != "S2E1" or card.props.get("NextCard.Title") != "Four":
                fail("next unwatched after S1E2 should offer S2E1 Four, got %r" % card.props)
        opens = [p for m, p in box.rpc if m == "Player.Open"]
        if opens != [{"item": {"episodeid": 201}, "options": {"resume": True}}]:
            fail("Play Now should open S2E1 from its resume point, got %r" % opens)
        h.update_next_card()
        if len(box.cards) != 1:
            fail("the card went up twice for one start")

        # Next in order, Back: S1E3 offered, nothing played.
        box = Box()
        box.labels["Skin.String(next_card)"] = "inorder"
        box.labels["Player.Chapters"] = ""
        box.labels["Skin.String(next_card_secs)"] = "30"
        box.choice = "back"
        h = install(box)
        start(h)
        box.time = LIVE_TOTAL - 31
        h.update_next_card()
        if box.cards:
            fail("with no chapters and 30s set, the card went up 31 s out")
        box.time = LIVE_TOTAL - 29
        h.update_next_card()
        if len(box.cards) != 1 or box.cards[0].props.get("NextCard.Marker") != "S1E3":
            fail("next in order after S1E2 should offer S1E3 at 30 s out")
        if any(m == "Player.Open" for m, _ in box.rpc):
            fail("Back played something")

        # No card: live TV, not a library episode, a special, a queue with a next item.
        for what, key, value in (
                ("live TV", "VideoPlayer.Content(livetv)", True),
                ("a video with no show", "VideoPlayer.TvShowDBID", ""),
                ("a special", "VideoPlayer.Season", "0"),
                ("an episode with no number", "VideoPlayer.Episode", ""),
                ("a queue with a next item", "Playlist.Length(video)", "3")):
            box = Box()
            box.labels["Skin.String(next_card)"] = "unwatched"
            if key in box.flags:
                box.flags[key] = value
            else:
                box.labels[key] = value
            h = install(box)
            start(h)
            box.time = LIVE_TOTAL - 10
            h.update_next_card()
            h.update_next_card()
            if box.cards:
                fail("%s got a card" % what)

        # A card up comes down when playback stops or the switch goes off.
        for what, change in (("playback stopping", ("flags", "Player.HasVideo", False)),
                             ("the switch going off", ("labels", "Skin.String(next_card)", ""))):
            box = Box()
            box.labels["Skin.String(next_card)"] = "unwatched"
            h = install(box)
            start(h)
            open_card = service.xbmcgui.WindowXMLDialog(CARD_XML)
            h._card_dialog = open_card
            getattr(box, change[0])[change[1]] = change[2]
            h.update_next_card()
            if not open_card.closed or h._card_dialog is not None and not open_card.closed:
                fail("the card did not come down on %s" % what)

        # The lookup asks only for what comes after the playing episode.
        f = service.FunctionalHelper._card_filter(1, 250, "unwatched")
        text = repr(f)
        if "'value': '250'" not in text or "'playcount'" not in text or "'value': '1'" not in text:
            fail("the unwatched lookup should filter past S1E250 and on play count, got %r" % f)
        if "playcount" in repr(service.FunctionalHelper._card_filter(1, 250, "inorder")):
            fail("the in order lookup should not filter on play count")

        # A new start drops a lookup that was for the last one.
        box = Box()
        box.labels["Skin.String(next_card)"] = "unwatched"
        h = install(box)
        start(h)
        gen = h._card_gen
        h._card_reset()
        h._card_lookup(gen, 31, 1, 2, "unwatched")
        if h._card_next is not None:
            fail("a lookup for an earlier start set the offer")
    finally:
        (service.xbmc.getCondVisibility, service.xbmc.getInfoLabel, service._jsonrpc,
         service.xbmc.Player, wxd, service.threading.Thread) = saved
        if wxd is None:
            del service.xbmcgui.WindowXMLDialog
        else:
            service.xbmcgui.WindowXMLDialog = wxd


def test_dialog_class():
    """
    <summary>The real NextCardDialog on a stand in base: OK on Play Now sets
    "play" and closes, Back and the back key set "back" and close, and the
    player keys and every other key are left alone for Kodi to act on (a
    pause forwarded by hand toggled twice live).</summary>
    """
    print("running test_dialog_class")
    saved = (getattr(service.xbmcgui, "WindowXMLDialog", None), service.xbmc.Player, service.xbmc.getCondVisibility)
    calls = []

    class Base:
        """<summary>WindowXMLDialog as far as the card uses it.</summary>"""

        def __init__(self, *_a, **_kw):
            """<summary>Not closed yet.</summary>"""
            self.closed = False

        def close(self):
            """<summary>Note the close.</summary>"""
            self.closed = True

    class Player:
        """<summary>Records what the card asks of the player.</summary>"""

        def pause(self):
            """<summary>Note a pause toggle.</summary>"""
            calls.append("pause")

        def stop(self):
            """<summary>Note a stop.</summary>"""
            calls.append("stop")

    class Action:
        """<summary>A Kodi action with one id.</summary>"""

        def __init__(self, aid):
            """<summary>Keep the id.</summary>"""
            self.aid = aid

        def getId(self):  # noqa: N802 (Kodi API)
            """<summary>The id.</summary><returns>It.</returns>"""
            return self.aid

    paused = {"v": False}
    try:
        service.xbmcgui.WindowXMLDialog = Base
        service.xbmc.Player = Player
        service.xbmc.getCondVisibility = lambda text: paused["v"] if text == "Player.Paused" else False
        H = service.FunctionalHelper
        cls = service._next_card_dialog_class(H)

        def card():
            """<summary>A fresh card.</summary><returns>It.</returns>"""
            return cls(H.NEXT_CARD_XML, "", "Default", "1080i")

        d = card()
        d.onClick(H.NEXT_CARD_PLAY_ID)
        if d.choice != "play" or not d.closed:
            fail("OK on Play Now should choose play and close the card")
        d = card()
        d.onClick(H.NEXT_CARD_PLAY_ID + 1)
        if d.choice or d.closed:
            fail("a click on anything else should do nothing")
        for aid in (10, 92):
            d = card()
            d.onAction(Action(aid))
            if d.choice != "back" or not d.closed:
                fail("action %d should hide the card" % aid)
        del calls[:]
        d = card()
        for aid in (12, 229, 79, 13, 88, 89):
            d.onAction(Action(aid))
        if d.choice or d.closed or calls:
            fail("pause, play, stop and volume should be left to Kodi, not handled by the card")
        del calls[:]
        d = card()
        for aid in (1, 2, 3, 4, 7):
            d.onAction(Action(aid))
        if d.choice or d.closed or calls:
            fail("arrows and select as actions should be left to the card's own controls")
    finally:
        wxd, service.xbmc.Player, service.xbmc.getCondVisibility = saved
        if wxd is None:
            del service.xbmcgui.WindowXMLDialog
        else:
            service.xbmcgui.WindowXMLDialog = wxd


def test_off_by_default():
    """
    <summary>Nothing sets next_card or next_card_secs but the two rows, and
    nothing opens the card but the service, so a skin with the row left alone
    draws nothing new.</summary>
    """
    print("running test_off_by_default")
    inc = read(os.path.join(XML, "Includes.xml"))
    var = inc.split('<variable name="NextCardLabel">')[1].split("</variable>")[0]
    if not var.rstrip().endswith("<value>$LOCALIZE[31103]</value>"):
        fail("an unset next_card should read Off on its row")
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml") or name == "SkinSettings.xml":
            continue
        text = read(os.path.join(XML, name))
        if re.search(r"Skin\.(SetString|SetBool|ToggleSetting|Reset)\(next_card(_secs)?[,)]", text):
            fail("%s sets the card's settings" % name)
        if name != CARD_XML and "script-functional-nextcard" in text.lower():
            fail("%s opens or names the card" % name)
    card = ET.fromstring(read(os.path.join(XML, CARD_XML)))
    if card.find("visible") is not None:
        fail("the card has a window visible condition, so Kodi could open it without the service")
    svc = read(os.path.join(SKIN, "service.py"))
    if svc.count('"script-functional-nextcard.xml"') != 1:
        fail("the service should name the card's file once")


def test_dialog():
    """
    <summary>The card's XML: a dialog with Play Now as its default control,
    the id the service listens for, and every label it shows.</summary>
    """
    print("running test_dialog")
    card = ET.fromstring(read(os.path.join(XML, CARD_XML)))
    strings = read(STRINGS)
    if card.get("type") != "dialog":
        fail("the card is not a dialog")
    button = [c for c in card.iter("control") if c.get("type") == "button"]
    if len(button) != 1 or button[0].get("id") != str(service.FunctionalHelper.NEXT_CARD_PLAY_ID):
        fail("the card should have one button, id %s" % service.FunctionalHelper.NEXT_CARD_PLAY_ID)
    if card.findtext("defaultcontrol") != str(service.FunctionalHelper.NEXT_CARD_PLAY_ID):
        fail("Play Now is not the card's default control")
    text = read(os.path.join(XML, CARD_XML))
    for prop in ("NextCard.Thumb", "NextCard.Marker", "NextCard.Show", "NextCard.Title"):
        if "Window.Property(%s)" % prop not in text:
            fail("the card does not show %s" % prop)
    for sid in re.findall(r"\$LOCALIZE\[(\d+)\]|<label>(\d+)</label>", text):
        sid = sid[0] or sid[1]
        if 'msgctxt "#%s"' % sid not in strings:
            fail("string %s on the card is missing" % sid)
    for c in card.iter("control"):
        left, top = int(c.findtext("left") or 0), int(c.findtext("top") or 0)
        if c.findtext("width") and left + int(c.findtext("width")) > 1920:
            fail("a card control runs off the screen")
        if c.findtext("height") and top + int(c.findtext("height")) > 1080:
            fail("a card control runs off the screen")


def test_rows():
    """
    <summary>Rows 7328 and 7329: labels with their values, cycles that
    cover every value and come back, 7329 hidden while the card is off, help
    lines with a Where line, form None, Up and Down between them and 7327,
    Left to the rows beside them, and the caching note moved clear of them
    and still on the page.</summary>
    """
    print("running test_rows")
    ss = read(os.path.join(XML, "SkinSettings.xml"))
    settings = {n.get("id"): n for n in ET.fromstring(ss).iter("control") if n.get("id")}
    help_text = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    preview = read(os.path.join(XML, "Includes_SettingsPreview.xml"))
    strings = read(STRINGS)
    rule, secs, above = settings.get("7328"), settings.get("7329"), settings.get("7327")
    if rule is None or secs is None:
        fail("rows 7328 and 7329 are missing")
        return
    if "$VAR[NextCardLabel]" not in rule.findtext("label") or "$VAR[NextCardSecsLabel]" not in secs.findtext("label"):
        fail("the rows do not show their values")
    clicks = [c.text for c in rule.findall("onclick")]
    if not any("Skin.SetString(next_card,unwatched)" in c for c in clicks) or \
            not any("Skin.SetString(next_card,inorder)" in c for c in clicks) or \
            not any("Skin.Reset(next_card)" in c for c in clicks):
        fail("row 7328 should cycle Off, Next Unwatched, Next in Order and back")
    clicks = " ".join(c.text for c in secs.findall("onclick"))
    for v in ("90", "120", "30"):
        if "Skin.SetString(next_card_secs,%s)" % v not in clicks:
            fail("row 7329 never sets %s" % v)
    if "Skin.Reset(next_card_secs)" not in clicks:
        fail("row 7329 never comes back to 60s")
    for v in service.NEXT_CARD_FALLBACK_CHOICES:
        if v != service.NEXT_CARD_FALLBACK_SECS and "Skin.SetString(next_card_secs,%d)" % v not in clicks:
            fail("the service accepts %d s but the row cannot set it" % v)
    if secs.findtext("visible") != "!String.IsEmpty(Skin.String(next_card))":
        fail("row 7329 should hide while the card is off")
    for rid in ("7328", "7329"):
        if "Control.HasFocus(%s)" % rid not in help_text.split("<expression name=\"settings_help_shown\">")[1].split("</expression>")[0]:
            fail("settings_help_shown does not list row %s" % rid)
        entry = re.search(r'Control\.HasFocus\(%s\)">\$LOCALIZE\[(\d+)\]' % rid, help_text)
        line = entry and re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
        if not line or "[CR]Where: " not in line.group(1):
            fail("row %s has no help with a Where line" % rid)
        none = preview.split('<expression name="settings_preview_none">')[1].split("</expression>")[0]
        if "Control.HasFocus(%s)" % rid not in none:
            fail("row %s is not in settings_preview_none" % rid)
    for row, up in ((rule, above), (secs, rule)):
        if row.findtext("left") != up.findtext("left") or int(row.findtext("top")) != int(up.findtext("top")) + 80:
            fail("row %s is not straight under row %s" % (row.get("id"), up.get("id")))
        if up.findtext("ondown") != row.get("id") or row.findtext("onup") != up.get("id"):
            fail("rows %s and %s do not lead to each other" % (up.get("id"), row.get("id")))
        if row.find("onright") is not None:
            fail("row %s should go nowhere right" % row.get("id"))
    if rule.findtext("onleft") != "7313" or secs.findtext("onleft") != "7313":
        fail("left from 7328 and 7329 should reach 7313, as from 7327")
    if not settings["7313"].findtext("onright"):
        fail("7313 should lead back right, or Left from the new rows is a one way trip")
    note = [c for c in ET.fromstring(ss).iter("control")
            if c.get("type") == "label" and "$LOCALIZE[31323]" in (c.findtext("label") or "")]
    if len(note) != 1:
        fail("the caching note is not found once")
    else:
        top, height = int(note[0].findtext("top")), int(note[0].findtext("height"))
        if top < int(secs.findtext("top")) + int(secs.findtext("height")):
            fail("the caching note overlaps row 7329")
        if top + height > 1080:
            fail("the caching note runs off the page")


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_timing()
    test_pick()
    test_service()
    test_dialog_class()
    test_off_by_default()
    test_dialog()
    test_rows()
    if FAILURES:
        print("test_next_episode_card: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_next_episode_card: all checks passed")


if __name__ == "__main__":
    main()
