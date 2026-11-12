#!/usr/bin/env python3
"""
<summary>
Tests for the skip intro and recap pill (roadmap item 16, phase F): the
service's pure functions (the Jellyfin item id in a playing path, the
servers in the Jellyfin add-on's data file, the marked parts, which part
plays at a time, the bar's fill, the switch on check's words), the helper
driven through stubs (nothing happens with the switch off, a lookup asks
each server in turn and logs neither address nor token, the pill opens
and closes on time, OK seeks and Back hides, the credits rule, the
commands), and the XML wiring (the dialog, the two Playback rows, their
focus links, help, strings and preview entries, and that nothing but the
rows' own clicks set the switches). Widened after review (08/11/2026) to the
request itself (token only header, no redirect, size and time caps),
finite times, the seek target, a video changed under the pill, the pill's
lifecycle and the check's bounds. Widened again (09/11/2026) for the
Jellyfin add-on's own skip buttons: the offer as the pill is switched on,
the give-back as it is switched off, the parts Jellyfin skips by itself,
and the pill giving way to Jellyfin's prompt. Widened 11/11/2026 for
phase F2, the per show choice: show_skip_rule in full, the start passing
the show's library id, the lookup sending nothing for a show set to No
Pill, and the credits following the show's own card and pill choices.
</summary>
<remarks>
No Kodi and no network are needed. The xbmc modules are stubbed in
sys.modules before the real service.py is imported, and _jellyfin_get,
threading.Thread and the dialog class's base are replaced per test, so
every helper method run here is the shipped code. Exits non zero when a
check fails.
Usage:
    python3 tests/test_skip_pill.py
</remarks>
"""
import ast
import json
import os
import re
import sys
import types
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
PO = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(SKIN, "service.py")
GENERATOR = os.path.join(ROOT, "build_preview_art.py")

SWITCH, CREDITS, CHANNEL = "skip_pill", "skip_pill_outro", "skip_command"
ROW, CREDITS_ROW = "7334", "7335"
DIALOG_XML = "script-functional-skippill.xml"
STRINGS = tuple(str(n) for n in range(31858, 31871))
HELP = {ROW: "31859", CREDITS_ROW: "31861"}
ITEM = "0123456789abcdef0123456789abcdef"
TOKEN = "secret-token-for-the-test"
ADDRESS = "http://jellyfin.invalid:8096"
PATH = "plugin://plugin.video.jellyfin/aa/bb/?filename=x.mkv&id=%s&dbid=1&mode=play" % ITEM

COND = {}          # condition text -> answer; anything else is False
INFO = {}          # infolabel -> answer
BUILTINS = []
LOGS = []
DIALOGS = []       # (kind, heading, text) from the Dialog stub
SEEKS = []
THREADS = []       # (target name, args) of every Thread started
PLAY_TIME = [0.0]
TOTAL_TIME = [0.0]
MODALS = []       # every pill that reached doModal
YESNO = [True]    # what the next yes or no dialog answers
FAILURES = []


def fail(msg):
    """
    <summary>Records one failure; the run carries on so every miss is listed.</summary>
    <param name="msg">What failed.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


class _Dialog:
    """<summary>Stand in for xbmcgui.Dialog: records what would be shown.</summary>"""

    def ok(self, heading, text):
        """<summary>Records an OK dialog.</summary>"""
        DIALOGS.append(("ok", heading, text))
        return True

    def notification(self, heading, text, *_a, **_k):
        """<summary>Records a toast.</summary>"""
        DIALOGS.append(("toast", heading, text))

    def yesno(self, heading, text, nolabel="", yeslabel="", **_k):
        """<summary>Records a yes or no question and answers with YESNO[0].</summary>"""
        DIALOGS.append(("yesno", heading, text, nolabel, yeslabel))
        return YESNO[0]


class _Control:
    """<summary>Stand in for a progress control: records its percent.</summary>"""

    def __init__(self):
        """<summary>Starts unset.</summary>"""
        self.percent = None

    def setPercent(self, value):  # noqa: N802 (Kodi API)
        """<summary>Records the fill.</summary>"""
        self.percent = value


class _WindowXMLDialog:
    """<summary>Stand in for xbmcgui.WindowXMLDialog: properties, one control, a scripted doModal.</summary>"""

    next_choice = ""
    during_modal = None   # called while the pill is open, to change the world under it

    def __init__(self, *args, **kwargs):
        """<summary>Records the XML file it was built from.</summary>"""
        self.args = args
        self.props = {}
        self.control = _Control()
        self.closed = False

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Keeps a window property.</summary>"""
        self.props[key] = value

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Reads a window property back.</summary>"""
        return self.props.get(key, "")

    def getControl(self, _control_id):  # noqa: N802 (Kodi API)
        """<summary>The one control.</summary>"""
        return self.control

    def doModal(self):  # noqa: N802 (Kodi API)
        """<summary>Opens, then acts as if the viewer pressed what next_choice names.</summary>"""
        MODALS.append(self)
        self.onInit()
        if _WindowXMLDialog.during_modal is not None:
            _WindowXMLDialog.during_modal()
        if _WindowXMLDialog.next_choice == "skip":
            self.onClick(9361)
        elif _WindowXMLDialog.next_choice == "back":
            self.onAction(types.SimpleNamespace(getId=lambda: 92))
        elif isinstance(_WindowXMLDialog.next_choice, int):
            self.onAction(types.SimpleNamespace(getId=lambda: _WindowXMLDialog.next_choice))

    def close(self):
        """<summary>Notes the close.</summary>"""
        self.closed = True


class _Thread:
    """<summary>Stand in for threading.Thread: records what would run and runs nothing.</summary>"""

    def __init__(self, target=None, args=(), name=None, daemon=None):
        """<summary>Keeps the target and its arguments.</summary>"""
        self.target, self.args = target, args

    def start(self):
        """<summary>Records the start.</summary>"""
        THREADS.append((getattr(self.target, "__name__", str(self.target)), self.args))


def _stub_kodi():
    """
    <summary>Installs the xbmc module stubs service.py imports, then imports it.</summary>
    <returns>The imported service module.</returns>
    """
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
    xbmc.log = lambda msg, *a, **k: LOGS.append(str(msg))
    xbmc.executeJSONRPC = lambda _text: "{}"
    xbmc.getCondVisibility = lambda text: COND.get(text, False)
    xbmc.getInfoLabel = lambda label: INFO.get(label, "")
    xbmc.getLocalizedString = lambda sid: "S%d" % sid if sid != 31868 else "%s is installed"
    xbmc.executebuiltin = lambda text, *a, **k: BUILTINS.append(text)
    xbmc.getSkinDir = lambda: "skin.functional"
    xbmc.Monitor = type("Monitor", (), {"abortRequested": lambda self: False,
                                        "waitForAbort": lambda self, _t=0: False})
    xbmc.Player = type("Player", (), {"isPlaying": lambda self: True,
                                      "getTime": lambda self: PLAY_TIME[0],
                                      "getTotalTime": lambda self: TOTAL_TIME[0],
                                      "seekTime": lambda self, t: SEEKS.append(t)})
    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.Window = type("Window", (), {"__init__": lambda self, _id=0: None,
                                         "setProperty": lambda self, k, v: None,
                                         "getProperty": lambda self, k: ""})
    xbmcgui.Dialog = _Dialog
    xbmcgui.WindowXMLDialog = _WindowXMLDialog
    xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = (
        "info", "warning", "error")
    xbmcgui.INPUT_ALPHANUM = 0
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = lambda *_a: types.SimpleNamespace(
        getLocalizedString=lambda _sid: "", getAddonInfo=lambda _k: "")
    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda p: p
    xbmcvfs.exists = lambda _p: False
    xbmcvfs.mkdirs = lambda _p: True
    for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon),
                      ("xbmcvfs", xbmcvfs)):
        sys.modules[name] = mod
    sys.path.insert(0, SKIN)
    import service  # noqa: E402
    service.threading.Thread = _Thread
    return service


def make_helper(service):
    """
    <summary>A FunctionalHelper with only the pill's state, as __init__ sets it.</summary>
    <param name="service">The imported service module.</param>
    <returns>The helper.</returns>
    """
    helper = object.__new__(service.FunctionalHelper)
    helper._skip_pending = False
    helper._skip_lock = service.threading.Lock()
    helper._skip_gen = 0
    helper._skip_items = None
    helper._skip_hidden = set()
    helper._skip_dialog = None
    helper._skip_shown = None
    helper._skip_opening = False
    helper._skip_hold_until = 0.0
    helper._skip_show = None
    return helper


def reset_world():
    """<summary>Clears every recorder and the player, and switches everything off.</summary>"""
    for store in (COND, INFO):
        store.clear()
    for store in (BUILTINS, LOGS, DIALOGS, SEEKS, THREADS, MODALS):
        del store[:]
    PLAY_TIME[0] = 0.0
    TOTAL_TIME[0] = 0.0
    YESNO[0] = True
    INFO["Player.FilenameAndPath"] = PATH
    _WindowXMLDialog.next_choice = ""
    _WindowXMLDialog.during_modal = None


def segment(kind, start, end):
    """
    <summary>One media segment as Jellyfin returns it.</summary>
    <param name="kind">The Type, such as Intro.</param>
    <param name="start">Start in seconds.</param>
    <param name="end">End in seconds.</param>
    <returns>The dict.</returns>
    """
    return {"Type": kind, "StartTicks": int(start * 10000000), "EndTicks": int(end * 10000000)}


# ---- the pure functions -----------------------------------------------------

def test_item_id(service):
    """<summary>The item id comes from both path shapes, and nothing else yields one.</summary>"""
    print("running test_item_id")
    cases = [
        (PATH, ITEM),
        (PATH.replace(ITEM, ITEM.upper()), ITEM),
        ("plugin://plugin.video.jellyfin/?id=01234567-89ab-cdef-0123-456789abcdef&mode=play", ITEM),
        ("http://server:8096/Videos/%s/stream.mkv?static=true" % ITEM, ITEM),
        ("https://server/videos/%s/master.m3u8" % ITEM, ITEM),
        ("plugin://plugin.video.emby/?id=%s" % ITEM, ""),
        ("plugin://plugin.video.jellyfin/?mode=play", ""),
        ("plugin://plugin.video.jellyfin/?id=notanid", ""),
        ("/media/films/x.mkv", ""),
        ("smb://box/films/%s/x.mkv" % ITEM, ""),
        ("", ""),
        (None, ""),
    ]
    for path, want in cases:
        got = service.jellyfin_item_id(path)
        if got != want:
            fail("jellyfin_item_id(%r) is %r, expected %r" % (path, got, want))


def test_servers(service):
    """<summary>The data file gives each usable server in order, and nothing for a bad file.</summary>"""
    print("running test_servers")
    doc = {"Servers": [
        {"address": ADDRESS + "/", "AccessToken": TOKEN, "UserId": "u1"},
        {"address": "ftp://nope", "AccessToken": "t"},
        {"address": "https://second.invalid", "AccessToken": ""},
        "rubbish",
        {"address": "https://third.invalid", "AccessToken": "t3"},
    ]}
    got = service.jellyfin_servers(json.dumps(doc))
    want = [(ADDRESS, TOKEN, "u1"), ("https://third.invalid", "t3", "")]
    if got != want:
        fail("jellyfin_servers gave %r, expected %r" % (got, want))
    for bad in ("", "not json", "[]", json.dumps({"Servers": None}), None):
        if service.jellyfin_servers(bad) != []:
            fail("jellyfin_servers(%r) should be empty" % (bad,))


def test_segments(service):
    """<summary>Ticks become seconds, only intro, recap and (when asked) credits are kept, bad parts are dropped.</summary>"""
    print("running test_segments")
    items = [
        segment("Outro", 1300, 1380),
        segment("Intro", 60, 90),
        segment("Recap", 0, 45),
        segment("Preview", 1380, 1400),
        segment("Commercial", 500, 560),
        segment("Intro", 200, 202),          # shorter than SKIP_MIN_SECS
        segment("Intro", 300, 250),          # reversed
        {"Type": "Intro", "StartTicks": None, "EndTicks": 10},
        {"Type": "Intro", "StartTicks": -10000000, "EndTicks": 100000000},
        "rubbish",
    ]
    got = service.skip_segments(items, False)
    want = [(0.0, 45.0, "recap"), (60.0, 90.0, "intro")]
    if got != want:
        fail("skip_segments without credits gave %r, expected %r" % (got, want))
    got = service.skip_segments(items, True)
    if got != want + [(1300.0, 1380.0, "credits")]:
        fail("skip_segments with credits gave %r" % (got,))
    if service.skip_segments(None, True) != []:
        fail("skip_segments(None) should be empty")


def test_segment_at(service):
    """<summary>The part playing is found up to its end margin, never a hidden one.</summary>"""
    print("running test_segment_at")
    parts = [(0.0, 45.0, "recap"), (60.0, 90.0, "intro")]
    margin = service.SKIP_END_MARGIN
    checks = [
        (0.0, parts[0]), (30.0, parts[0]), (45.0 - margin - 0.01, parts[0]), (45.0 - margin, None),
        (50.0, None), (60.0, parts[1]), (89.0, None), (95.0, None),
    ]
    for now, want in checks:
        got = service.skip_segment_at(parts, now)
        if got != want:
            fail("skip_segment_at at %.2f s is %r, expected %r" % (now, got, want))
    if service.skip_segment_at(parts, 70.0, {(60.0, 90.0)}) is not None:
        fail("a hidden part was offered again")
    if service.skip_segment_at(parts, 10.0, {(60.0, 90.0)}) != parts[0]:
        fail("hiding one part hid another")


def test_left_percent(service):
    """<summary>The bar is full at the start of a part, half way at the middle, empty at its end, and clamped.</summary>"""
    print("running test_left_percent")
    part = (60.0, 100.0, "intro")
    for now, want in ((60.0, 100), (80.0, 50), (100.0, 0), (50.0, 100), (120.0, 0)):
        got = service.skip_left_percent(part, now)
        if got != want:
            fail("skip_left_percent at %.0f s is %r, expected %r" % (now, got, want))
    if service.skip_left_percent((5.0, 5.0, "intro"), 5.0) != 0:
        fail("an empty part should give an empty bar")


def test_setup_message(service):
    """<summary>The switch on check picks the right words in every case.</summary>"""
    print("running test_setup_message")
    cases = [
        ((0, False, None, False), (31866, "")),
        ((1, True, None, True), (31870, "")),
        ((1, False, None, False), (31867, "")),
        ((1, False, ["Intro Skipper"], False), (31867, "")),
        ((1, True, ["Playback Reporting", "Intro Skipper"], False), (31868, "Intro Skipper")),
        ((1, True, ["theintrodb"], False), (31868, "theintrodb")),
        ((1, True, ["Playback Reporting"], False), (31869, "")),
        ((1, True, None, False), (31869, "")),
        ((2, True, ["Intro Skipper"], True), (31870, "")),
    ]
    for args, want in cases:
        got = service.skip_setup_message(*args)
        if got != want:
            fail("skip_setup_message%r is %r, expected %r" % (args, got, want))


# ---- the helper, driven through stubs ---------------------------------------

def test_off_by_default(service):
    """
    <summary>With the switch off a start asks nothing, and no other path does either:
    a start of a non Jellyfin video or live TV starts no lookup.</summary>
    """
    print("running test_off_by_default")
    helper = make_helper(service)
    reset_world()
    INFO["Player.FilenameAndPath"] = PATH
    helper._skip_pending = True
    helper.update_skip_pill()
    if THREADS:
        fail("with the switch off a start began %s" % THREADS)
    COND["Skin.HasSetting(skip_pill) + Player.HasVideo + !VideoPlayer.Content(livetv)"] = True
    INFO["Player.FilenameAndPath"] = "/films/x.mkv"
    helper._skip_pending = True
    helper.update_skip_pill()
    if THREADS:
        fail("a non Jellyfin video began %s" % THREADS)
    INFO["Player.FilenameAndPath"] = PATH
    helper._skip_pending = True
    helper.update_skip_pill()
    if [t[0] for t in THREADS] != ["_skip_lookup"] or THREADS[0][1][1:] != (ITEM, 0):
        fail("a Jellyfin start with the switch on should look its item up once, began %s" % THREADS)
    # F2: the show's library id goes with it
    del THREADS[:]
    INFO["VideoPlayer.TvShowDBID"] = "31"
    helper._skip_pending = True
    helper.update_skip_pill()
    if not THREADS or THREADS[0][1][1:] != (ITEM, 31):
        fail("a start of an episode should pass its show's library id, began %s" % THREADS)
    # the demo is ignored with the switch off
    reset_world()
    helper = make_helper(service)
    COND["Player.HasVideo"] = True
    helper._skip_demo(False)
    if helper._skip_items is not None:
        fail("the demo made a part with the switch off")


def test_lookup(service):
    """<summary>Each server is asked in turn until one knows the item; an old start's answer is dropped; no log names the server or the token.</summary>"""
    print("running test_lookup")
    reset_world()
    helper = make_helper(service)
    servers = [("http://first.invalid", "tok-first", "u"), (ADDRESS, TOKEN, "u")]
    asked = []

    def fake_get(server, path):
        asked.append((server[0], path))
        if server[0] == ADDRESS:
            return 200, {"Items": [segment("Intro", 10, 40), "rubbish"]}
        return 404, None

    original = service._jellyfin_get
    service._jellyfin_get = fake_get
    helper._skip_servers = lambda: servers
    try:
        helper._skip_lookup(0, ITEM)
        if asked != [("http://first.invalid", "/MediaSegments/" + ITEM), (ADDRESS, "/MediaSegments/" + ITEM)]:
            fail("the lookup asked %s" % asked)
        if helper._skip_items != [segment("Intro", 10, 40)]:
            fail("the lookup kept %r" % (helper._skip_items,))
        helper._skip_items = None
        helper._skip_gen = 5
        helper._skip_lookup(4, ITEM)
        if helper._skip_items is not None:
            fail("an answer for an older start was kept")
        # no server knows the item: nothing kept, and the log still names neither
        service._jellyfin_get = lambda server, path: (404, None)
        helper._skip_lookup(5, ITEM)
        if helper._skip_items is not None:
            fail("parts were kept when no server knew the item")
        if not any("no server answered" in line for line in LOGS):
            fail("a lookup no server answered was not logged")
        # and an unreachable server is passed over for the next one
        del asked[:]
        service._jellyfin_get = lambda server, path: (asked.append(server[0]) or (0, None)) if server[0] != ADDRESS else (200, {"Items": []})
        helper._skip_lookup(5, ITEM)
        if asked != ["http://first.invalid"] or helper._skip_items != []:
            fail("an unreachable first server stopped the lookup: asked %s, kept %r" % (asked, helper._skip_items))
        for line in LOGS:
            for secret in (TOKEN, ADDRESS, "first.invalid", "tok-first", ITEM):
                if secret in line:
                    fail("a log line names %s: %s" % (secret, line))
    finally:
        service._jellyfin_get = original


def test_show_rule(service):
    """
    <summary>F2: show_skip_rule for every switch, credits switch, card rule and
    show choice, against the agreed rule written out on its own.</summary>
    """
    print("running test_show_rule")
    for on in (False, True):
        for glob_credits in (False, True):
            for card in ("", "unwatched", "inorder"):
                for choice in (None, "intros", "credits", "off", "junk"):
                    if not on or choice == "off":
                        want = (False, False)
                    else:
                        wants = {"credits": True, "intros": False}.get(choice, glob_credits)
                        want = (True, wants and card == "")
                    got = service.show_skip_rule(on, glob_credits, card, choice)
                    if got != want:
                        fail("show_skip_rule(%r, %r, %r, %r) gave %r, want %r" % (on, glob_credits, card, choice, got, want))


def test_show_lookup(service):
    """
    <summary>F2: a show set to No Pill sends the server nothing; a show's
    choices are kept for the start they belong to and dropped by the next;
    a film follows the Playback page; With Credits on a show set to No
    Card offers the credits with the card on elsewhere, and a show set to
    Intros and Recaps never does.</summary>
    """
    print("running test_show_lookup")
    reset_world()
    helper = make_helper(service)
    store = {}
    asked = []
    helper._show_keys_for = lambda show: (["tvdb:%d" % show], "Show")
    helper._show_choice = lambda keys, field="next_card", allowed=None: store.get(field)
    helper._skip_servers = lambda: [(ADDRESS, TOKEN, "u")]
    original = service._jellyfin_get

    def fake_get(server, path):
        asked.append(path)
        return 200, {"Items": [segment("Intro", 60, 100), segment("Outro", 1300, 1380)]}

    service._jellyfin_get = fake_get
    try:
        store["skip_pill"] = "off"
        helper._skip_lookup(0, ITEM, 31)
        if asked or helper._skip_items is not None:
            fail("a show set to No Pill asked the server %s or kept parts" % asked)
        if not any("by its own choice" in line for line in LOGS):
            fail("No Pill for a show was not logged")
        store.update(skip_pill="credits", next_card="off")
        helper._skip_lookup(0, ITEM, 31)
        if len(asked) != 1 or helper._skip_show != ("credits", "off"):
            fail("the show's choices were not kept with its parts: asked %s, kept %r" % (asked, helper._skip_show))
        # the card is on globally, Skip Credits Too is off: the show's own choices still give credits
        on = "Skin.HasSetting(skip_pill) + Player.HasVideo"
        clear = ("Window.IsActive(fullscreenvideo) + !System.HasActiveModalDialog + !Window.IsActive(videoosd)"
                 " + !Window.IsActive(seekbar) + !Window.IsActive(fullscreeninfo)")
        COND[on] = COND[clear] = True
        INFO["Skin.String(next_card)"] = "unwatched"
        PLAY_TIME[0] = 1320.0
        helper.update_skip_pill()
        if not THREADS or THREADS[0][1][1] != (1300.0, 1380.0, "credits"):
            fail("With Credits on a show set to No Card should offer the credits: %s" % THREADS)
        # Intros and Recaps never offers them, even with Skip Credits Too on and the card off
        del THREADS[:]
        helper._skip_opening = False
        helper._skip_show = ("intros", None)
        INFO["Skin.String(next_card)"] = ""
        COND["Skin.HasSetting(skip_pill_outro)"] = True
        helper.update_skip_pill()
        if THREADS:
            fail("Intros and Recaps on a show offered the credits: %s" % THREADS)
        # a new start forgets the show's choices
        helper._skip_reset()
        if helper._skip_show is not None:
            fail("a new start kept the last show's choices")
        # an answer for an older start keeps neither parts nor choices
        helper._skip_gen = 9
        helper._skip_lookup(8, ITEM, 31)
        if helper._skip_items is not None or helper._skip_show is not None:
            fail("an older start's lookup was kept")
        # a film: no show query, defaults
        helper._show_keys_for = lambda show: fail("a film asked for a show's keys")
        helper._skip_lookup(9, ITEM, 0)
        if helper._skip_show is not None or helper._skip_items is None:
            fail("a film should keep its parts and follow the Playback page")
        # a failed read of the show falls back to the Playback page, it does not lose the pill
        def broken(_show):
            raise RuntimeError("library gone")
        helper._show_keys_for = broken
        helper._skip_items = None
        helper._skip_lookup(9, ITEM, 31)
        if helper._skip_items is None or helper._skip_show is not None:
            fail("a failed read of the show's choice should fall back to the defaults")
    finally:
        service._jellyfin_get = original


def test_pill_on_time(service):
    """
    <summary>The pill opens while a part plays and nothing else is up, waits while
    the OSD is open, moves its bar, closes when its part ends, and leaves the
    credits alone while the next episode card is on.</summary>
    """
    print("running test_pill_on_time")
    reset_world()
    helper = make_helper(service)
    helper._skip_items = [segment("Intro", 60, 100), segment("Outro", 1300, 1380)]
    on = "Skin.HasSetting(skip_pill) + Player.HasVideo"
    clear = ("Window.IsActive(fullscreenvideo) + !System.HasActiveModalDialog + !Window.IsActive(videoosd)"
             " + !Window.IsActive(seekbar) + !Window.IsActive(fullscreeninfo)")
    COND[on] = True
    PLAY_TIME[0] = 30.0
    helper.update_skip_pill()
    if THREADS:
        fail("the pill opened before its part")
    PLAY_TIME[0] = 70.0
    helper.update_skip_pill()
    if THREADS:
        fail("the pill opened over the OSD or a menu")
    COND[clear] = True
    helper.update_skip_pill()
    if [t[0] for t in THREADS] != ["_skip_run"] or THREADS[0][1][1] != (60.0, 100.0, "intro"):
        fail("the pill did not open for the intro: %s" % THREADS)
    if not helper._skip_opening:
        fail("a pill being built is not marked, so a second could open")
    helper.update_skip_pill()
    if len(THREADS) != 1:
        fail("a second pill was started while the first was being built")
    # the pill is up: its bar moves, and it closes when the OSD comes up or the part ends
    dialog = _WindowXMLDialog()
    helper._skip_opening = False
    helper._skip_dialog, helper._skip_shown = dialog, (60.0, 100.0, "intro")
    PLAY_TIME[0] = 80.0
    helper.update_skip_pill()
    if dialog.control.percent != 50 or dialog.closed:
        fail("the open pill's bar should be at 50, is %r (closed %s)" % (dialog.control.percent, dialog.closed))
    COND["Window.IsActive(videoosd) | Window.IsActive(seekbar) | Window.IsActive(fullscreeninfo)"] = True
    helper.update_skip_pill()
    if not dialog.closed:
        fail("the pill stayed up under the OSD")
    del COND["Window.IsActive(videoosd) | Window.IsActive(seekbar) | Window.IsActive(fullscreeninfo)"]
    dialog.closed = False
    PLAY_TIME[0] = 99.0
    helper.update_skip_pill()
    if not dialog.closed:
        fail("the pill stayed up past its part")
    # credits: offered with the sub switch, not while the card is on
    helper._skip_dialog = helper._skip_shown = None
    del THREADS[:]
    PLAY_TIME[0] = 1320.0
    helper.update_skip_pill()
    if THREADS:
        fail("credits were offered with Skip Credits Too off")
    COND["Skin.HasSetting(skip_pill_outro)"] = True
    INFO["Skin.String(next_card)"] = "unwatched"
    helper.update_skip_pill()
    if THREADS:
        fail("credits were offered while the next episode card is on")
    INFO["Skin.String(next_card)"] = ""
    helper.update_skip_pill()
    if not THREADS or THREADS[0][1][1] != (1300.0, 1380.0, "credits"):
        fail("credits were not offered with the sub switch on and the card off: %s" % THREADS)
    # switching off forgets everything
    helper._skip_opening = False
    COND[on] = False
    helper.update_skip_pill()
    if helper._skip_items is not None:
        fail("switching the pill off did not forget the parts")


def test_ok_and_back(service):
    """<summary>OK seeks to the part's end and Back does not; both hide the part for this start; a pill from an old start skips nothing.</summary>"""
    print("running test_ok_and_back")
    part = (60.0, 100.0, "intro")
    for choice, seeks in (("skip", [100.0]), ("back", []), ("", [])):
        reset_world()
        helper = make_helper(service)
        helper._skip_opening = True
        _WindowXMLDialog.next_choice = choice
        helper._skip_run(0, part, 80.0)
        if SEEKS != seeks:
            fail("choice %r seeked %s, expected %s" % (choice, SEEKS, seeks))
        hidden = {(60.0, 100.0)} if choice else set()
        if helper._skip_hidden != hidden:
            fail("choice %r left hidden %s" % (choice, helper._skip_hidden))
        if helper._skip_dialog is not None or helper._skip_opening:
            fail("choice %r left the pill marked open or opening" % choice)
    reset_world()
    helper = make_helper(service)
    original_class = service._skip_pill_dialog_class
    built = []

    def spy(owner):
        cls = original_class(owner)
        built.append(cls)
        return cls

    service._skip_pill_dialog_class = spy
    try:
        _WindowXMLDialog.next_choice = "skip"
        helper._skip_gen = 3
        helper._skip_run(2, part, 80.0)
        if SEEKS:
            fail("a pill from an older start skipped")
        # a new video starts while the pill is open: OK on the old pill seeks nothing
        reset_world()
        helper = make_helper(service)
        _WindowXMLDialog.next_choice = "skip"

        def new_start():
            helper._skip_gen += 1

        _WindowXMLDialog.during_modal = new_start
        helper._skip_run(0, part, 80.0)
        if SEEKS:
            fail("OK on a pill whose video was replaced while it was open seeked the new video")
        if helper._skip_hidden:
            fail("a replaced video's part was hidden in the new start")
        _WindowXMLDialog.during_modal = None
        reset_world()
        helper = make_helper(service)
        captured = {}
        _WindowXMLDialog.next_choice = ""
        real_init = _WindowXMLDialog.__init__

        def init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            captured["dialog"] = self

        _WindowXMLDialog.__init__ = init
        try:
            helper._skip_run(0, part, 80.0)
        finally:
            _WindowXMLDialog.__init__ = real_init
        dialog = captured.get("dialog")
        if dialog is None or dialog.args[0] != DIALOG_XML:
            fail("the pill was not built from %s" % DIALOG_XML)
        elif dialog.props.get("SkipPill.Label") != "S31862" or dialog.props.get("SkipPill.Percent") != "50":
            fail("the pill's properties were %s" % dialog.props)
        elif dialog.control.percent != 50:
            fail("the pill's bar opened at %r, expected 50" % dialog.control.percent)
    finally:
        service._skip_pill_dialog_class = original_class


def test_commands(service):
    """<summary>check runs the switch on check off the loop, demo makes up a part from now, anything else is ignored.</summary>"""
    print("running test_commands")
    reset_world()
    helper = make_helper(service)
    spawned = []
    helper._spawn_dialog = lambda worker: spawned.append(getattr(worker, "__name__", ""))
    service._COMMANDS_TAKEN.clear()
    INFO["Skin.String(skip_command)"] = "check"
    helper.update_skip_command()
    if spawned != ["_skip_check"]:
        fail("check spawned %s" % spawned)
    service._COMMANDS_TAKEN.clear()
    COND["Skin.HasSetting(skip_pill) + Player.HasVideo"] = True
    PLAY_TIME[0] = 10.0
    INFO["Skin.String(skip_command)"] = "demo"
    helper.update_skip_command()
    want = [segment("Intro", 9.0, 10.0 + service.SKIP_DEMO_SECS)]
    if helper._skip_items != want:
        fail("demo made %r, expected %r" % (helper._skip_items, want))
    service._COMMANDS_TAKEN.clear()
    INFO["Skin.String(skip_command)"] = "demo_credits"
    helper.update_skip_command()
    if not helper._skip_items or helper._skip_items[0]["Type"] != "Outro":
        fail("demo_credits made %r" % (helper._skip_items,))
    service._COMMANDS_TAKEN.clear()
    INFO["Skin.String(skip_command)"] = "rm -rf"
    before = list(helper._skip_items or [])
    helper.update_skip_command()
    if helper._skip_items != before or len(spawned) != 1:
        fail("an unknown command did something")


def test_check(service):
    """<summary>The switch on check shows the right words for an administrator with a plugin and no markers, a viewer with markers, and no server.</summary>"""
    print("running test_check")
    original = service._jellyfin_get
    try:
        reset_world()
        helper = make_helper(service)
        helper._skip_servers = lambda: [(ADDRESS, TOKEN, "u1")]
        asked = []

        def admin(server, path):
            asked.append(path)
            if path == "/Plugins":
                return 200, [{"Name": "Intro Skipper"}, {"Name": "Playback Reporting"}]
            if path.startswith("/Items?"):
                return 200, {"Items": [{"Id": ITEM}]}
            return 200, {"Items": []}

        service._jellyfin_get = admin
        helper._skip_check()
        if DIALOGS != [("ok", "S31865", "Intro Skipper is installed")]:
            fail("an administrator with Intro Skipper and no markers saw %s" % DIALOGS)
        if not any("userId=u1" in p and "Random" in p for p in asked):
            fail("the sample did not ask for random items as the add-on's user: %s" % asked)
        reset_world()

        def viewer(server, path):
            if path == "/Plugins":
                return 403, None
            if path.startswith("/Items?"):
                return 200, {"Items": [{"Id": ITEM}]}
            return 200, {"Items": [segment("Intro", 1, 30)]}

        service._jellyfin_get = viewer
        helper._skip_check()
        if DIALOGS != [("toast", "S31865", "S31870")]:
            fail("a viewer with markers saw %s" % DIALOGS)
        for label, answer in (("a refused sign in", lambda server, path: (401, None)),
                              ("a server without media segments",
                               lambda server, path: (403, None) if path == "/Plugins" else
                               (200, {"Items": [{"Id": ITEM}]}) if path.startswith("/Items?") else (404, None)),
                              ("an unreachable server", lambda server, path: (0, None))):
            reset_world()
            service._jellyfin_get = answer
            helper._skip_check()
            if DIALOGS != [("ok", "S31865", "S31867")]:
                fail("%s should say the markers could not be checked, saw %s" % (label, DIALOGS))
        reset_world()
        helper._skip_servers = lambda: []
        helper._skip_check()
        if DIALOGS != [("ok", "S31865", "S31866")]:
            fail("no Jellyfin server saw %s" % DIALOGS)
        for line in LOGS:
            if TOKEN in line or ADDRESS in line:
                fail("the check logged the server or token: %s" % line)
    finally:
        service._jellyfin_get = original


def test_init_and_wiring():
    """<summary>__init__ sets every pill attribute the tests set, the notification flags a start, and both handlers are on the fast ticker.</summary>"""
    print("running test_init_and_wiring")
    with open(SERVICE, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    helper_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FunctionalHelper")
    init = next(n for n in helper_class.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    stored = {n.attr for n in ast.walk(init) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)}
    for attr in ("_skip_pending", "_skip_lock", "_skip_gen", "_skip_items", "_skip_hidden",
                 "_skip_dialog", "_skip_shown", "_skip_opening", "_skip_hold_until"):
        if attr not in stored:
            fail("__init__ does not set %s" % attr)
    notify = next(n for n in helper_class.body if isinstance(n, ast.FunctionDef) and n.name == "onNotification")
    if "self._skip_pending = True" not in ast.get_source_segment(source, notify):
        fail("onNotification does not flag a start for the pill")
    fast = re.search(r"fast = \((.*?)\n    \)", source, re.S)
    if not fast or "helper.update_skip_pill," not in fast.group(1) or "helper.update_skip_command," not in fast.group(1):
        fail("update_skip_pill and update_skip_command must be on the fast ticker")


def test_request(service):
    """
    <summary>The request carries the token alone, goes to the add-on's address with
    the timeout, follows no redirect, and gives up on a huge or dripping answer.</summary>
    """
    print("running test_request")
    if service.jellyfin_auth_header(TOKEN) != 'MediaBrowser Token="%s"' % TOKEN:
        fail("the Authorization header is %r" % service.jellyfin_auth_header(TOKEN))
    handler = service._NoRedirect()
    request = service.urllib.request.Request(ADDRESS + "/x", headers={"Authorization": "secret"})
    if handler.redirect_request(request, None, 302, "Found", {}, "http://elsewhere.invalid/") is not None:
        fail("a redirect would be followed, carrying the token")
    if not any(isinstance(h, service._NoRedirect) for h in service._JELLYFIN_OPENER.handlers):
        fail("the opener does not use the redirect refusal")
    sent = []

    class Response:
        """<summary>A response that hands out its body in chunks.</summary>"""

        def __init__(self, chunks, status=200):
            self.chunks, self.status = list(chunks), status

        def read(self, _size=-1):
            return self.chunks.pop(0) if self.chunks else b""

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class Opener:
        """<summary>Records what would be sent and answers with the next response.</summary>"""

        def __init__(self, response):
            self.response = response

        def open(self, req, timeout=None):
            sent.append((req.full_url, req.get_header("Authorization"), timeout))
            return self.response

    original = service._JELLYFIN_OPENER
    try:
        service._JELLYFIN_OPENER = Opener(Response([b'{"Items": ', b"[]}"]))
        got = service._jellyfin_get((ADDRESS, TOKEN, "u"), "/MediaSegments/" + ITEM)
        if got != (200, {"Items": []}):
            fail("a plain answer read as %r" % (got,))
        if sent != [(ADDRESS + "/MediaSegments/" + ITEM, 'MediaBrowser Token="%s"' % TOKEN, service.SKIP_HTTP_TIMEOUT)]:
            fail("the request sent was %s" % sent)
        big = b"x" * 65536
        huge = Response([big] * (service.SKIP_MAX_BYTES // 65536 + 50))
        service._JELLYFIN_OPENER = Opener(huge)
        if service._jellyfin_get((ADDRESS, TOKEN, "u"), "/x") != (0, None):
            fail("an answer over SKIP_MAX_BYTES was read")
        if len(huge.chunks) < 40:
            fail("reading went on past SKIP_MAX_BYTES (%d chunks left of 50 over)" % len(huge.chunks))
        clock = [1000.0]
        real = service.time.monotonic

        class Drip(Response):
            """<summary>Each chunk arrives a second after the last.</summary>"""

            def read(self, _size=-1):
                clock[0] += 1.0
                return b" "

        service.time.monotonic = lambda: clock[0]
        try:
            service._JELLYFIN_OPENER = Opener(Drip([]))
            if service._jellyfin_get((ADDRESS, TOKEN, "u"), "/x") != (0, None):
                fail("a server dripping bytes was waited on past the deadline")
            if clock[0] - 1000.0 > service.SKIP_HTTP_TIMEOUT + 2:
                fail("a dripping server was read for %d s, the limit is %d s" % (clock[0] - 1000.0, service.SKIP_HTTP_TIMEOUT))
        finally:
            service.time.monotonic = real
    finally:
        service._JELLYFIN_OPENER = original


def test_finite_and_seek(service):
    """<summary>Infinite or NaN times are dropped; OK seeks to the part's end, kept just inside the file.</summary>"""
    print("running test_finite_and_seek")
    bad = json.loads('[{"Type": "Intro", "StartTicks": 0, "EndTicks": Infinity},'
                     ' {"Type": "Intro", "StartTicks": NaN, "EndTicks": 900000000}]')
    if service.skip_segments(bad, True) != []:
        fail("infinite or NaN times were kept: %r" % (service.skip_segments(bad, True),))
    for part, total, want in (((60.0, 100.0, "intro"), 1380.0, 100.0), ((1300.0, 1400.0, "credits"), 1380.0, 1379.5),
                              ((1300.0, 1380.0, "credits"), 1380.0, 1379.5), ((60.0, 100.0, "intro"), 0.0, 100.0),
                              ((1379.8, 1390.0, "credits"), 1380.0, 1379.8)):
        got = service.skip_seek_target(part, total)
        if got != want:
            fail("skip_seek_target(%r, %r) is %r, expected %r" % (part, total, got, want))
    reset_world()
    helper = make_helper(service)
    TOTAL_TIME[0] = 1380.0
    _WindowXMLDialog.next_choice = "skip"
    helper._skip_run(0, (1300.0, 1400.0, "credits"), 1310.0)
    if SEEKS != [1379.5]:
        fail("OK on credits past the end seeked %s, expected 1379.5" % SEEKS)


def test_video_changed_under_pill(service):
    """<summary>A different video playing by the time OK is pressed is never seeked.</summary>"""
    print("running test_video_changed_under_pill")
    reset_world()
    helper = make_helper(service)
    _WindowXMLDialog.next_choice = "skip"
    _WindowXMLDialog.during_modal = lambda: INFO.__setitem__("Player.FilenameAndPath", PATH.replace("x.mkv", "y.mkv"))
    helper._skip_run(0, (60.0, 100.0, "intro"), 80.0)
    if SEEKS:
        fail("OK seeked a video that replaced the one the pill was for")


def test_pill_lifecycle(service):
    """
    <summary>A pill whose parts were cleared is closed by the next tick; _skip_reset
    bumps the start, forgets the parts and closes the pill; a pill for an old
    start never opens.</summary>
    """
    print("running test_pill_lifecycle")
    reset_world()
    helper = make_helper(service)
    dialog = _WindowXMLDialog()
    helper._skip_dialog, helper._skip_items = dialog, None
    helper.update_skip_pill()
    if not dialog.closed:
        fail("a pill left up after its parts were cleared was not closed")
    reset_world()
    helper = make_helper(service)
    dialog = _WindowXMLDialog()
    helper._skip_dialog, helper._skip_items = dialog, [segment("Intro", 1, 30)]
    helper._skip_hidden = {(1.0, 30.0)}
    helper._skip_reset()
    if helper._skip_gen != 1 or helper._skip_items is not None or helper._skip_hidden or not dialog.closed:
        fail("_skip_reset left gen %d, items %r, hidden %s, closed %s" % (
            helper._skip_gen, helper._skip_items, helper._skip_hidden, dialog.closed))
    reset_world()
    helper = make_helper(service)
    helper._skip_gen = 2
    helper._skip_opening = True
    helper._skip_run(1, (60.0, 100.0, "intro"), 80.0)
    if MODALS:
        fail("a pill for an older start was opened")
    if helper._skip_opening:
        fail("a dropped pill left the opening flag set")


def test_check_bounds(service):
    """<summary>The check reads at most SKIP_SAMPLE items, stops at its time budget, and a check looks up the video already playing.</summary>"""
    print("running test_check_bounds")
    original = service._jellyfin_get
    real = service.time.monotonic
    try:
        reset_world()
        helper = make_helper(service)
        helper._skip_servers = lambda: [(ADDRESS, TOKEN, "u1")]
        asked = []

        def many(server, path):
            asked.append(path)
            if path.startswith("/Items?"):
                return 200, {"Items": [{"Id": "%032x" % n} for n in range(500)]}
            return 200, {"Items": []} if path.startswith("/MediaSegments/") else (403, None)

        service._jellyfin_get = many
        helper._skip_check()
        segments = [p for p in asked if p.startswith("/MediaSegments/")]
        if len(segments) != service.SKIP_SAMPLE:
            fail("the check asked about %d items, expected SKIP_SAMPLE (%d)" % (len(segments), service.SKIP_SAMPLE))
        if not 1 <= service.SKIP_SAMPLE <= 50:
            fail("SKIP_SAMPLE is %d" % service.SKIP_SAMPLE)
        reset_world()
        del asked[:]
        clock = [0.0]

        def slow(server, path):
            clock[0] += service.SKIP_HTTP_TIMEOUT
            return many(server, path)

        service._jellyfin_get = slow
        service.time.monotonic = lambda: clock[0]
        helper._skip_servers = lambda: [(ADDRESS, TOKEN, "u1"), ("http://two.invalid", "t2", ""), ("http://three.invalid", "t3", "")]
        helper._skip_check()
        if clock[0] > service.SKIP_CHECK_SECS + 2 * service.SKIP_HTTP_TIMEOUT:
            fail("a slow server held the check for %d s, the budget is %d s" % (clock[0], service.SKIP_CHECK_SECS))
        if len(DIALOGS) != 1:
            fail("a check stopped by its budget still has to answer, saw %s" % DIALOGS)
        service.time.monotonic = real
        reset_world()
        helper = make_helper(service)
        helper._spawn_dialog = lambda worker: None
        service._COMMANDS_TAKEN.clear()
        INFO["Skin.String(skip_command)"] = "check"
        helper.update_skip_command()
        if not helper._skip_pending:
            fail("switching the pill on did not look up the video already playing")
    finally:
        service._jellyfin_get = original
        service.time.monotonic = real


class _Jellyfin:
    """<summary>Stand in for the Jellyfin add-on's settings, as xbmcaddon.Addon gives them.</summary>"""

    def __init__(self, enabled=True, modes=None):
        """<summary>Its switch and its mode per setting name.</summary>"""
        self.enabled = enabled
        self.modes = dict(modes or {})
        self.writes = []

    def getSettingBool(self, key):  # noqa: N802 (Kodi API)
        """<summary>Only the segment switch is a bool here.</summary>"""
        assert key == "mediaSegmentsEnabled", key
        return self.enabled

    def getSettingInt(self, key):  # noqa: N802 (Kodi API)
        """<summary>A mode, 0 when never set.</summary>"""
        return self.modes.get(key, 0)

    def setSettingInt(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Records and applies a write.</summary>"""
        self.writes.append((key, value))
        self.modes[key] = value


def with_jellyfin(service, jellyfin):
    """
    <summary>Makes xbmcaddon.Addon("plugin.video.jellyfin") answer with the stand in, and System.HasAddon say so.</summary>
    <param name="service">The imported service module.</param>
    <param name="jellyfin">A _Jellyfin, or None for "not installed".</param>
    <returns>A function that puts things back.</returns>
    """
    original = service.xbmcaddon.Addon

    def addon(*args):
        if args and args[0] == "plugin.video.jellyfin":
            if jellyfin is None:
                raise RuntimeError("not installed")
            return jellyfin
        return original(*args)

    service.xbmcaddon.Addon = addon
    COND["System.HasAddon(plugin.video.jellyfin)"] = jellyfin is not None
    return lambda: setattr(service.xbmcaddon, "Addon", original)


def test_jellyfin_modes(service):
    """<summary>Which settings put a button over the pill, and which types Jellyfin skips itself.</summary>"""
    print("running test_jellyfin_modes")
    modes = {"skipIntroductionMode": 2, "skipRecapMode": 1, "skipCreditsMode": 2, "skipPreviewMode": 2}
    if service.jellyfin_button_modes(True, modes) != ["skipCreditsMode", "skipIntroductionMode"]:
        fail("button modes were %r" % service.jellyfin_button_modes(True, modes))
    if service.jellyfin_button_modes(False, modes) != []:
        fail("button modes were offered with Jellyfin's skipping switched off")
    if service.jellyfin_auto_types(True, modes) != {"Recap"}:
        fail("automatic types were %r" % service.jellyfin_auto_types(True, modes))
    if service.jellyfin_auto_types(False, modes) != set():
        fail("automatic types were read with Jellyfin's skipping switched off")


def test_offer_and_release(service):
    """
    <summary>Switching on offers to turn Jellyfin's buttons off and changes only those on a
    yes; switching off offers back only those still off; no Jellyfin, no button, or a no,
    changes nothing.</summary>
    """
    print("running test_offer_and_release")
    helper = make_helper(service)
    cases = (("not installed", None, True), ("no buttons", _Jellyfin(True, {"skipIntroductionMode": 1}), True),
             ("its skipping off", _Jellyfin(False, {"skipIntroductionMode": 2}), True),
             ("a no", _Jellyfin(True, {"skipIntroductionMode": 2}), False))
    for label, jellyfin, answer in cases:
        reset_world()
        YESNO[0] = answer
        undo = with_jellyfin(service, jellyfin)
        try:
            helper._skip_offer()
        finally:
            undo()
        asked = [d for d in DIALOGS if d[0] == "yesno"]
        if (jellyfin is not None and jellyfin.writes) or any("skip_jellyfin_modes" in b for b in BUILTINS):
            fail("%s: the offer changed something" % label)
        if label != "a no" and asked:
            fail("%s: the offer was made" % label)
        if label == "a no" and len(asked) != 1:
            fail("a no: the offer was not made once")
    reset_world()
    jellyfin = _Jellyfin(True, {"skipIntroductionMode": 2, "skipRecapMode": 1, "skipCreditsMode": 2})
    undo = with_jellyfin(service, jellyfin)
    try:
        helper._skip_offer()
        if sorted(jellyfin.writes) != [("skipCreditsMode", 0), ("skipIntroductionMode", 0)]:
            fail("a yes changed %s" % jellyfin.writes)
        if 'Skin.SetString(skip_jellyfin_modes,"skipCreditsMode,skipIntroductionMode")' not in BUILTINS:
            fail("the changed settings were not recorded: %s" % BUILTINS)
        # switching off: the viewer has since set credits to automatic, so only the intro is offered back
        reset_world()
        COND["System.HasAddon(plugin.video.jellyfin)"] = True
        jellyfin.writes, jellyfin.modes["skipCreditsMode"] = [], 1
        INFO["Skin.String(skip_jellyfin_modes)"] = "skipCreditsMode,skipIntroductionMode"
        helper._skip_release()
        if jellyfin.writes != [("skipIntroductionMode", 2)]:
            fail("the give-back changed %s" % jellyfin.writes)
        if "Skin.Reset(skip_jellyfin_modes)" not in BUILTINS:
            fail("the record was not cleared after the give-back")
        # a no on the way out changes nothing, and still clears the record
        reset_world()
        COND["System.HasAddon(plugin.video.jellyfin)"] = True
        YESNO[0] = False
        jellyfin.writes, jellyfin.modes["skipIntroductionMode"] = [], 0
        INFO["Skin.String(skip_jellyfin_modes)"] = "skipIntroductionMode"
        helper._skip_release()
        if jellyfin.writes or "Skin.Reset(skip_jellyfin_modes)" not in BUILTINS:
            fail("a no on the way out changed %s or kept the record" % jellyfin.writes)
        # nothing recorded: no question
        reset_world()
        COND["System.HasAddon(plugin.video.jellyfin)"] = True
        helper._skip_release()
        if DIALOGS:
            fail("switching off asked with nothing recorded")
        # a recorded name that is not one of the pill's settings is never written
        reset_world()
        COND["System.HasAddon(plugin.video.jellyfin)"] = True
        INFO["Skin.String(skip_jellyfin_modes)"] = "mediaSegmentsEnabled,somethingElse"
        helper._skip_release()
        if jellyfin.writes or DIALOGS:
            fail("a stray recorded name was acted on")
    finally:
        undo()
    # the check runs the offer first
    reset_world()
    helper._skip_servers = lambda: []
    jellyfin = _Jellyfin(True, {"skipIntroductionMode": 2})
    undo = with_jellyfin(service, jellyfin)
    try:
        helper._skip_check()
    finally:
        undo()
    if [d[0] for d in DIALOGS] != ["yesno", "ok"]:
        fail("the switch on check should offer first, then report, saw %s" % [d[0] for d in DIALOGS])
    reset_world()
    helper._spawn_dialog = lambda worker: DIALOGS.append(("spawned", getattr(worker, "__name__", "")))
    service._COMMANDS_TAKEN.clear()
    INFO["Skin.String(skip_command)"] = "release"
    helper.update_skip_command()
    if DIALOGS != [("spawned", "_skip_release")]:
        fail("release spawned %s" % DIALOGS)


def test_auto_and_give_way(service):
    """<summary>Parts Jellyfin skips by itself are left out; Jellyfin's prompt up for a part makes the pill give way for it.</summary>"""
    print("running test_auto_and_give_way")
    original = service._jellyfin_get
    try:
        reset_world()
        helper = make_helper(service)
        helper._skip_servers = lambda: [(ADDRESS, TOKEN, "u")]
        service._jellyfin_get = lambda server, path: (200, {"Items": [segment("Intro", 10, 40), segment("Recap", 0, 8)]})
        undo = with_jellyfin(service, _Jellyfin(True, {"skipIntroductionMode": 1}))
        try:
            helper._skip_lookup(0, ITEM)
        finally:
            undo()
        if helper._skip_items != [segment("Recap", 0, 8)]:
            fail("an intro Jellyfin skips by itself was kept: %r" % (helper._skip_items,))
    finally:
        service._jellyfin_get = original
    reset_world()
    helper = make_helper(service)
    helper._skip_items = [segment("Intro", 60, 100)]
    COND["Skin.HasSetting(skip_pill) + Player.HasVideo"] = True
    COND[("Window.IsActive(fullscreenvideo) + !System.HasActiveModalDialog + !Window.IsActive(videoosd)"
          " + !Window.IsActive(seekbar) + !Window.IsActive(fullscreeninfo)")] = True
    COND["Window.IsVisible(script-jellyfin-skip.xml)"] = True
    PLAY_TIME[0] = 70.0
    helper.update_skip_pill()
    if THREADS or helper._skip_hidden != {(60.0, 100.0)}:
        fail("the pill did not give way to Jellyfin's prompt: started %s, hidden %s" % (THREADS, helper._skip_hidden))
    dialog = _WindowXMLDialog()
    helper._skip_hidden = set()
    helper._skip_dialog, helper._skip_shown = dialog, (60.0, 100.0, "intro")
    helper.update_skip_pill()
    if not dialog.closed or helper._skip_hidden != {(60.0, 100.0)}:
        fail("an open pill stayed under Jellyfin's prompt")


def test_pass_keys(service):
    """
    <summary>The OSD, menu, context and info keys close the pill without hiding its part,
    are passed on to the player, and the pill stays down a moment; arrows do nothing.</summary>
    """
    print("running test_pass_keys")
    part = (60.0, 100.0, "intro")
    for action_id, builtin in ((24, "Action(OSD)"), (163, "Action(OSD)"), (117, "Action(OSD)"),
                               (243, "Action(OSD)"), (11, "Action(Info)")):
        reset_world()
        helper = make_helper(service)
        _WindowXMLDialog.next_choice = action_id
        helper._skip_run(0, part, 80.0)
        if builtin not in BUILTINS:
            fail("key %d did not pass on as %s: %s" % (action_id, builtin, BUILTINS))
        if helper._skip_hidden or SEEKS:
            fail("key %d hid the part or seeked" % action_id)
        if helper._skip_hold_until <= service.time.monotonic():
            fail("key %d set no hold, so the pill could reopen over the OSD" % action_id)
    # the key waits out the pill's fade, which Kodi would otherwise drop it into
    reset_world()
    helper = make_helper(service)
    waits = []
    helper.waitForAbort = lambda secs=0: waits.append(secs) or False
    _WindowXMLDialog.next_choice = 24
    helper._skip_run(0, part, 80.0)
    if waits != [service.FunctionalHelper.SKIP_PASS_WAIT] or service.FunctionalHelper.SKIP_PASS_WAIT < 0.25:
        fail("a passed key should wait out the 200 ms fade once, waited %s" % waits)
    reset_world()
    helper = make_helper(service)
    helper.waitForAbort = lambda secs=0: True
    _WindowXMLDialog.next_choice = 24
    helper._skip_run(0, part, 80.0)
    if BUILTINS:
        fail("a key was passed on while Kodi was closing down")
    for action_id in (1, 2, 3, 4):
        reset_world()
        helper = make_helper(service)
        _WindowXMLDialog.next_choice = action_id
        helper._skip_run(0, part, 80.0)
        if any(b.startswith("Action(") for b in BUILTINS) or helper._skip_hidden:
            fail("arrow %d did something: %s" % (action_id, BUILTINS))
    # the tick keeps the pill down while the hold lasts, then opens it again
    reset_world()
    helper = make_helper(service)
    helper._skip_items = [segment("Intro", 60, 100)]
    COND["Skin.HasSetting(skip_pill) + Player.HasVideo"] = True
    COND[("Window.IsActive(fullscreenvideo) + !System.HasActiveModalDialog + !Window.IsActive(videoosd)"
          " + !Window.IsActive(seekbar) + !Window.IsActive(fullscreeninfo)")] = True
    PLAY_TIME[0] = 70.0
    helper._skip_hold_until = service.time.monotonic() + 60
    helper.update_skip_pill()
    if THREADS:
        fail("the pill reopened during the hold")
    helper._skip_hold_until = 0.0
    helper.update_skip_pill()
    if not THREADS:
        fail("the pill did not come back after the hold")


# ---- the XML ----------------------------------------------------------------

def parse(name):
    """
    <summary>Parses one XML file from the skin's xml folder.</summary>
    <param name="name">The file name.</param>
    <returns>Its root element.</returns>
    """
    return ET.parse(os.path.join(XML, name)).getroot()


def text(el, tag):
    """
    <summary>A child element's text, stripped, or "".</summary>
    <param name="el">The parent.</param>
    <param name="tag">The child's tag.</param>
    <returns>The text.</returns>
    """
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def test_dialog_xml(service):
    """<summary>The dialog has the button and bar the service drives, focused, labelled from its property.</summary>"""
    print("running test_dialog_xml")
    root = parse(DIALOG_XML)
    if service.FunctionalHelper.SKIP_PILL_XML != DIALOG_XML:
        fail("the service opens %s" % service.FunctionalHelper.SKIP_PILL_XML)
    if text(root, "defaultcontrol") != str(service.FunctionalHelper.SKIP_BUTTON_ID):
        fail("the pill's button is not its default control")
    controls = {c.get("id"): c for c in root.iter("control") if c.get("id")}
    button = controls.get(str(service.FunctionalHelper.SKIP_BUTTON_ID))
    bar = controls.get(str(service.FunctionalHelper.SKIP_PROGRESS_ID))
    if button is None or button.get("type") != "button":
        fail("the pill has no button %s" % service.FunctionalHelper.SKIP_BUTTON_ID)
    elif text(button, "label") != "$INFO[Window.Property(SkipPill.Label)]":
        fail("the button's label is %r" % text(button, "label"))
    if bar is None or bar.get("type") != "progress":
        fail("the pill has no progress bar %s" % service.FunctionalHelper.SKIP_PROGRESS_ID)
    for tex in ("texturefocus", "texturenofocus"):
        el = button.find(tex) if button is not None else None
        if (el is None or (el.text or "").strip() != "white.png"
                or el.get("colordiffuse") != "$VAR[AccentColor]" or el.get("border")):
            fail("the button's %s is not the accent plate the OSD buttons use" % tex)
    if button is not None and (text(button, "height") != "56" or text(button, "focusedcolor") != "$VAR[AccentTextColor]"):
        fail("the button is not drawn as an OSD button (56 tall, Text on Accent's colour)")


def test_rows():
    """<summary>The two Playback rows: labels, switches, the check on switch on, the sub switch hidden while off, focus links, no overlap.</summary>"""
    print("running test_rows")
    settings = parse("SkinSettings.xml")
    parent = {c: p for p in settings.iter() for c in p}
    controls = {c.get("id"): c for c in settings.iter("control") if c.get("id")}
    row, sub = controls.get(ROW), controls.get(CREDITS_ROW)
    if row is None or sub is None:
        fail("SkinSettings.xml lacks %s or %s" % (ROW, CREDITS_ROW))
        return
    if parent[row] is not parent[controls["7302"]] or parent[sub] is not parent[row]:
        fail("the rows are not on the Playback page")
    if text(row, "label") != "31858" or text(sub, "label") != "31860":
        fail("row labels are %r and %r" % (text(row, "label"), text(sub, "label")))
    if text(row, "selected") != "Skin.HasSetting(%s)" % SWITCH or text(sub, "selected") != "Skin.HasSetting(%s)" % CREDITS:
        fail("the rows do not reflect their switches")
    clicks = [(c.get("condition") or "", (c.text or "").strip()) for c in row.findall("onclick")]
    if clicks != [("!Skin.HasSetting(%s)" % SWITCH, "Skin.SetString(%s,check)" % CHANNEL),
                  ("Skin.HasSetting(%s)" % SWITCH, "Skin.SetString(%s,release)" % CHANNEL),
                  ("", "Skin.ToggleSetting(%s)" % SWITCH)]:
        fail("row %s clicks are %s" % (ROW, clicks))
    if [(c.text or "").strip() for c in sub.findall("onclick")] != ["Skin.ToggleSetting(%s)" % CREDITS]:
        fail("row %s should only toggle its switch" % CREDITS_ROW)
    if text(sub, "visible") != "Skin.HasSetting(%s)" % SWITCH:
        fail("Skip Credits Too must hide while the pill is off")
    links = {(ROW, "onright"): CREDITS_ROW, (ROW, "onup"): "7309", (ROW, "ondown"): "7302",
             (CREDITS_ROW, "onleft"): ROW, (CREDITS_ROW, "onup"): "7309", (CREDITS_ROW, "ondown"): "7302",
             ("7309", "ondown"): ROW, ("7302", "onup"): ROW}
    for (cid, direction), want in links.items():
        if text(controls[cid], direction) != want:
            fail("%s %s is %r, expected %s" % (cid, direction, text(controls[cid], direction), want))
    boxes = []
    for c in parent[row]:
        if c.tag != "control" or not c.get("id"):
            continue
        try:
            left, top, width, height = (int(text(c, t)) for t in ("left", "top", "width", "height"))
        except ValueError:
            continue
        boxes.append((left, top, left + width, top + height, c.get("id")))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if ROW in (a[4], b[4]) or CREDITS_ROW in (a[4], b[4]):
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    fail("Playback page: %s overlaps %s" % (a[4], b[4]))
    if any(b[3] > 1080 for b in boxes if b[4] in (ROW, CREDITS_ROW)):
        fail("a pill row runs off the bottom of the screen")


def test_only_the_rows_write():
    """<summary>Nothing but the rows' own clicks sets either switch or sends the check, and the service never sets a switch.</summary>"""
    print("running test_only_the_rows_write")
    writers = {}
    for name in sorted(os.listdir(XML)):
        if not name.endswith(".xml"):
            continue
        with open(os.path.join(XML, name), encoding="utf-8") as fh:
            for line in fh:
                for key in (SWITCH, CREDITS, CHANNEL):
                    if re.search(r"Skin\.(SetBool|ToggleSetting|Reset|SetString)\(%s[,)]" % key, line):
                        writers.setdefault(key, set()).add(name)
    for key in (SWITCH, CREDITS, CHANNEL):
        if writers.get(key) != {"SkinSettings.xml"}:
            fail("%s is written by %s, expected the Playback row alone" % (key, writers.get(key)))
    with open(SERVICE, encoding="utf-8") as fh:
        source = fh.read()
    for key in (SWITCH, CREDITS):
        if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s\)" % key, source) or re.search(
                r"_set_skin_string\(\"%s\"" % key, source):
            fail("service.py sets %s" % key)


def test_help_strings_preview():
    """<summary>Both rows have help with a Where line, every string exists, and both are picture toggles with all four pictures named.</summary>"""
    print("running test_help_strings_preview")
    help_root = parse("Includes_SettingsHelp.xml")
    shown = next((e.text or "" for e in help_root.iter("expression") if e.get("name") == "settings_help_shown"), "")
    with open(PO, encoding="utf-8") as fh:
        po = fh.read()
    for sid in STRINGS:
        if 'msgctxt "#%s"' % sid not in po:
            fail("strings.po has no string %s" % sid)
    for cid, sid in HELP.items():
        if "Control.HasFocus(%s)" % cid not in shown:
            fail("settings_help_shown does not list %s" % cid)
        if not any(v.get("condition") == "Control.HasFocus(%s)" % cid and (v.text or "").strip() == "$LOCALIZE[%s]" % sid
                   for v in help_root.iter("value")):
            fail("no help line for %s" % cid)
        m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % sid, po)
        if not m or "[CR]Where:" not in m.group(1):
            fail("help string %s has no Where line" % sid)
    m = re.search(r'msgctxt "#31868"\nmsgid "([^"]*)"', po)
    if not m or m.group(1).count("%s") != 1:
        fail("string 31868 must hold exactly one %s for the plugin's name")
    preview = parse("Includes_SettingsPreview.xml")
    exprs = {e.get("name"): e.text or "" for e in preview.iter("expression")}
    for cid, setting in ((ROW, SWITCH), (CREDITS_ROW, CREDITS)):
        for name in ("settings_preview_image", "settings_preview_image_toggle"):
            if "Control.HasFocus(%s)" % cid not in exprs.get(name, ""):
                fail("%s is not in %s" % (cid, name))
        for var in ("SettingsPreviewPicture", "SettingsPreviewPictureNow"):
            node = next((v for v in preview.iter("variable") if v.get("name") == var), None)
            pics = {(v.text or "").strip() for v in node.findall("value")
                    if "Control.HasFocus(%s)" % cid in (v.get("condition") or "")} if node is not None else set()
            if pics != {"preview/%s_on.png" % setting, "preview/%s_off.png" % setting}:
                fail("%s names %s for %s" % (var, sorted(pics), cid))
    with open(GENERATOR, encoding="utf-8") as fh:
        gen = ast.parse(fh.read())
    table = next((n.value for n in gen.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "PICTURES" for t in n.targets)), None)
    rows = {}
    for entry in (table.elts if table is not None else []):
        try:
            value = ast.literal_eval(entry)
        except ValueError:
            continue
        rows[value.get("row")] = value
    if rows.get(ROW, {}).get("setting") != SWITCH or rows.get(CREDITS_ROW, {}).get("setting") != CREDITS:
        fail("the picture table lacks the pill rows")
    shows = rows.get(CREDITS_ROW, {}).get("shows", {})
    if shows.get("off") != [(SWITCH, "true", "bool")] or shows.get("on") != [(SWITCH, "true", "bool")]:
        fail("Skip Credits Too's pictures must have the pill itself on, found %s" % shows)


if __name__ == "__main__":
    SERVICE_MODULE = _stub_kodi()
    test_item_id(SERVICE_MODULE)
    test_servers(SERVICE_MODULE)
    test_segments(SERVICE_MODULE)
    test_segment_at(SERVICE_MODULE)
    test_left_percent(SERVICE_MODULE)
    test_setup_message(SERVICE_MODULE)
    test_off_by_default(SERVICE_MODULE)
    test_lookup(SERVICE_MODULE)
    test_show_rule(SERVICE_MODULE)
    test_show_lookup(SERVICE_MODULE)
    test_pill_on_time(SERVICE_MODULE)
    test_ok_and_back(SERVICE_MODULE)
    test_commands(SERVICE_MODULE)
    test_check(SERVICE_MODULE)
    test_request(SERVICE_MODULE)
    test_finite_and_seek(SERVICE_MODULE)
    test_video_changed_under_pill(SERVICE_MODULE)
    test_pill_lifecycle(SERVICE_MODULE)
    test_check_bounds(SERVICE_MODULE)
    test_jellyfin_modes(SERVICE_MODULE)
    test_offer_and_release(SERVICE_MODULE)
    test_auto_and_give_way(SERVICE_MODULE)
    test_pass_keys(SERVICE_MODULE)
    test_init_and_wiring()
    test_dialog_xml(SERVICE_MODULE)
    test_rows()
    test_only_the_rows_write()
    test_help_strings_preview()
    if FAILURES:
        print("test_skip_pill: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_skip_pill: all checks passed")
