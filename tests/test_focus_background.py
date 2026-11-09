"""
<summary>
Tests for Follow Focused Tile (roadmap item 36, BG-FOLLOW): while the switch
is on and a Movies, TV Shows or Music tile has focus on Home, the background
shows fanart of that kind, and every other tile keeps the chosen mode. With
the switch off nothing changes. Also the XML that stands down while it
follows, and its Skin Settings row.
</summary>
<remarks>
No Kodi is needed. The xbmc modules are stubbed in sys.modules before the
real service.py is imported, as tests/test_bg_default.py does it, and the
helper is built without its constructor so only the slideshow state exists.
Fetches are never started on a thread here: the helper's fetch thread is a
stand in that is always busy, and the worker is called directly. Whether it
looks right on the TV is the live check's job. A standalone script:
build_zip.py runs it and stops on a non zero exit.
</remarks>
"""
import json
import os
import re
import sys
import types
import xml.etree.ElementTree as ET
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
PO = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")

# What the stubs answer: info labels by their full text, conditions that
# hold, and the JSON-RPC replies by method.
LABELS = {}
TRUE = set()
RPC = {}


class _Window:
    """<summary>xbmcgui.Window with a property store and nothing else.</summary>"""
    _props = {}

    def __init__(self, *_a):
        """<summary>Every window shares the one store.</summary>"""

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>The stored value or the empty string.</summary>"""
        return self._props.get(key, "")

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Store the value.</summary>"""
        self._props[key] = value

    def clearProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Forget the value.</summary>"""
        self._props.pop(key, None)


class _Monitor:
    """<summary>xbmc.Monitor, as FunctionalHelper's base class.</summary>"""
    def abortRequested(self):  # noqa: N802 (Kodi API)
        """<summary>Kodi is never shutting down here.</summary>"""
        return False

    def waitForAbort(self, _timeout=0):  # noqa: N802 (Kodi API)
        """<summary>Never aborted, and no waiting either.</summary>"""
        return False


SENT = []


def _rpc(text):
    """<summary>Answer one JSON-RPC request from RPC by its method, and keep the request.</summary>
    <param name="text">The request as the service sends it.</param>
    <returns>The reply as text; an empty object for a method not set up.</returns>"""
    SENT.append(json.loads(text))
    return json.dumps(RPC.get(SENT[-1].get("method"), {}))


xbmc = types.ModuleType("xbmc")
xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
xbmc.log = lambda *a, **k: None
xbmc.executeJSONRPC = _rpc
xbmc.getCondVisibility = lambda text: text in TRUE
xbmc.getInfoLabel = lambda label: LABELS.get(label, "")
xbmc.getLocalizedString = lambda _sid: ""
xbmc.executebuiltin = lambda *a, **k: None
xbmc.getSkinDir = lambda: "skin.functional"
xbmc.Monitor = _Monitor
xbmc.Player = type("Player", (), {"isPlaying": lambda self: False})
xbmcgui = types.ModuleType("xbmcgui")
xbmcgui.Window = _Window
xbmcgui.Dialog = type("Dialog", (), {"__getattr__": lambda self, _n: (lambda *a, **k: None)})
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

SWITCH = "Skin.HasSetting(bg_follow_tile)"
HOME = "Window.IsActive(home)"
FOLLOW = "String.IsEmpty(Window(home).Property(home_bg_follow))"
STAND_DOWN = " + [" + FOLLOW + " | String.IsEmpty(Window(home).Property(home_bg_fanart))]"
ROW_ID, LABEL, HELP = "7121", "31878", "31879"
RECENT = [{"fanart": "recent-%d" % i, "label": "Recent %d" % i} for i in range(3)]
MOVIES = [{"fanart": "movie-%d" % i, "label": "Movie %d" % i} for i in range(3)]
FAILURES = []


def check(cond, what):
    """<summary>Record a failed expectation instead of stopping at it.</summary>
    <param name="cond">The expectation.</param>
    <param name="what">What was expected, for the report.</param>"""
    if not cond:
        FAILURES.append(what)
        print("  FAILED: " + what)


class _Busy:
    """<summary>A fetch thread that is always running, so update_home_bg never starts one.</summary>"""
    def is_alive(self):  # noqa: D401 (threading API)
        """<summary>Always busy.</summary>"""
        return True


def setup(mode="recent", on=True, focus="9001", tiles=("movies", "tvshows", "music", "pictures")):
    """
    <summary>Reset the stubs and build a helper with only the slideshow state.</summary>
    <param name="mode">Skin.String(bg_mode).</param>
    <param name="on">Whether the follow switch is on.</param>
    <param name="focus">System.CurrentControlId, as Kodi gives it.</param>
    <param name="tiles">Tile.N.Kind for slots 1 onwards.</param>
    <returns>The helper; its fetchers give RECENT and MOVIES, music nothing.</returns>
    """
    LABELS.clear()
    TRUE.clear()
    _Window._props.clear()
    LABELS["Skin.String(bg_mode)"] = mode
    LABELS["Skin.String(bg_slideshow_interval)"] = "999"
    LABELS["System.CurrentControlId"] = focus
    TRUE.add(HOME)
    if on:
        TRUE.add(SWITCH)
    for n, kind in enumerate(tiles, 1):
        _Window._props["Tile.%d.Kind" % n] = kind
    h = object.__new__(service.FunctionalHelper)
    h._bg_seed_pending = False
    h._bg_source = ""
    h._bg_items = []
    h._bg_idx = -1
    h._bg_last_change = 0.0
    h._bg_last_fetch = 0.0
    h._bg_recent_fallback = False
    h._bg_history = deque(maxlen=service.FunctionalHelper.BG_HISTORY)
    h._bg_hist_pos = 0
    h._bg_thread = _Busy()
    h._bg_cache = {}
    h._bg_follow_empty = {}
    h._bg_follow_last = ""
    h._fetch_recent_movies = lambda: list(RECENT)
    h._fetch_follow_library = lambda kind: list(MOVIES) if kind == "movies" else []
    return h


def tick(h):
    """
    <summary>One slow tick; when the source has no list yet, fetch it in line
    and tick again, as the real thread and the next tick would.</summary>
    <param name="h">The helper.</param>
    """
    h.update_home_bg()
    if h._bg_source and not h._bg_items:
        h._bg_last_fetch = service.time.time()  # as update_home_bg stamps a fetch it starts
        h._bg_fetch_worker(h._bg_source)
        h.update_home_bg()


def prop(name):
    """<summary>A Home property as the skin would read it.</summary>
    <param name="name">The property name.</param>
    <returns>Its value or the empty string.</returns>"""
    return _Window._props.get(name, "")


def test_tile_ids_match_home():
    """<summary>The service's tile id map is exactly the ids HomeMenu gives each slot on Home.</summary>"""
    print("running test_tile_ids_match_home")
    root = ET.parse(os.path.join(XML, "Includes_Home.xml")).getroot()
    menu = next(i for i in root.findall("include") if i.get("name") == "HomeMenu")
    prefix = {p.get("name"): p.get("default") for p in menu.findall("param")}["p"]
    drawn = {}
    for inc in menu.iter("include"):
        if inc.get("content") == "HomeTile":
            params = {p.get("name"): p.get("value") for p in inc.findall("param")}
            drawn[params["id"].replace("$PARAM[p]", prefix)] = int(params["n"])
    check(drawn == service.FunctionalHelper.BG_FOLLOW_TILE_IDS,
          "BG_FOLLOW_TILE_IDS matches HomeMenu's 24 tile ids (diff %s)"
          % sorted(set(drawn.items()) ^ set(service.FunctionalHelper.BG_FOLLOW_TILE_IDS.items())))
    home = open(os.path.join(XML, "Home.xml"), encoding="utf-8").read()
    check('<include content="HomeMenu"/>' in home, "Home draws HomeMenu with its default ids")


def test_follow_kind():
    """<summary>Which focus follows: the switch, Home, a tile of the three kinds, and an empty kind.</summary>"""
    print("running test_follow_kind")
    h = setup()
    check(h._bg_follow_kind("recent") == "movies", "slot 1 wide (9001) on Movies follows")
    for cid, slot in (("9007", 6), ("9013", 3), ("9028", 8)):
        LABELS["System.CurrentControlId"] = cid
        _Window._props["Tile.%d.Kind" % slot] = "tvshows"
        check(h._bg_follow_kind("recent") == "tvshows", "id %s reads slot %d" % (cid, slot))
    LABELS["System.CurrentControlId"] = "9006"
    check(h._bg_follow_kind("recent") == "", "9006, the weather widget, is no tile")
    LABELS["System.CurrentControlId"] = "9004"
    check(h._bg_follow_kind("recent") == "", "a Pictures tile does not follow")
    LABELS["System.CurrentControlId"] = "9001"
    check(h._bg_follow_kind("") == "", "Off mode never follows")
    TRUE.discard(HOME)
    check(h._bg_follow_kind("recent") == "", "no following off Home")
    TRUE.add(HOME)
    TRUE.discard(SWITCH)
    check(h._bg_follow_kind("recent") == "", "no following with the switch off")
    TRUE.add(SWITCH)
    h._bg_follow_empty["movies"] = service.time.time()
    check(h._bg_follow_kind("recent") == "", "a kind just found empty gives way to the mode")
    h._bg_follow_empty["movies"] = service.time.time() - service.FunctionalHelper.BG_LIST_REFRESH - 1
    check(h._bg_follow_kind("recent") == "movies", "an empty kind is asked again after the refresh")


def test_switch_off_changes_nothing():
    """<summary>With the switch off, focus on Movies leaves the mode in charge and no property is set.</summary>"""
    print("running test_switch_off_changes_nothing")
    h = setup(on=False)
    tick(h)
    check(h._bg_source == "recent", "the source stays recent, got %r" % h._bg_source)
    check(prop("home_bg_fanart") == "recent-0", "the recent picture shows")
    check(prop("home_bg_follow") == "", "home_bg_follow is never set")
    LABELS["System.CurrentControlId"] = "9004"
    tick(h)
    check(h._bg_cache == {}, "nothing is cached with the switch off")


def test_follow_and_return():
    """<summary>Movies focused paints a film; another tile brings back the same recent picture
    with no blank in between; back on Movies the same film comes back at once.</summary>"""
    print("running test_follow_and_return")
    h = setup(focus="9004")
    tick(h)
    h._bg_last_change = 0.0
    h.update_home_bg()
    shown = prop("home_bg_fanart")
    check(shown == "recent-1", "the recent slideshow moved on to recent-1, got %r" % shown)
    LABELS["System.CurrentControlId"] = "9001"
    tick(h)
    check(h._bg_source == "follow:movies", "Movies focused: source follow:movies")
    check(prop("home_bg_fanart") == "movie-0", "a film's fanart shows")
    check(prop("home_bg_follow") == "1", "home_bg_follow is 1 while following")
    LABELS["System.CurrentControlId"] = "9004"
    h.update_home_bg()
    check(prop("home_bg_fanart") == shown, "back on Pictures the same recent picture returns at once, got %r"
          % prop("home_bg_fanart"))
    check(prop("home_bg_follow") == "", "home_bg_follow clears")
    LABELS["System.CurrentControlId"] = "9001"
    h.update_home_bg()
    check(prop("home_bg_fanart") == "movie-0", "back on Movies the film returns without a fetch, got %r"
          % prop("home_bg_fanart"))


def test_static_image_mode():
    """<summary>Static Image mode: the film shows while Movies has focus, then the slideshow
    picture clears so the static image comes back.</summary>"""
    print("running test_static_image_mode")
    h = setup(mode="image")
    LABELS["Skin.String(home_background)"] = "special://skin/backdrop.jpg"
    tick(h)
    check(prop("home_bg_fanart") == "movie-0" and prop("home_bg_follow") == "1",
          "the film shows over the static image's place")
    LABELS["System.CurrentControlId"] = "9004"
    h.update_home_bg()
    check(prop("home_bg_fanart") == "" and prop("home_bg_follow") == "",
          "leaving Movies clears the picture and the property")
    check(prop("home_bg_label") == "backdrop", "the static image's caption is back")


def test_empty_kind_gives_way():
    """<summary>No music library: Music focused falls back to the mode after one empty fetch.</summary>"""
    print("running test_empty_kind_gives_way")
    h = setup(focus="9003")
    tick(h)
    check("music" in h._bg_follow_empty, "the empty music fetch is remembered")
    h.update_home_bg()
    check(h._bg_source == "recent", "Music gives way to the mode, got %r" % h._bg_source)
    check(prop("home_bg_follow") == "", "home_bg_follow clears for an empty kind")


def test_fetch_follow_library():
    """<summary>The fetch asks for the right kind and builds artist items without the Add To List type.</summary>"""
    print("running test_fetch_follow_library")
    h = object.__new__(service.FunctionalHelper)
    RPC.clear()
    RPC["AudioLibrary.GetArtists"] = {"result": {"artists": [
        {"artistid": 4, "artist": "Band", "fanart": "fan-band", "thumbnail": "th"},
        {"artistid": 5, "artist": "No Art", "fanart": ""}]}}
    RPC["VideoLibrary.GetTVShows"] = {"result": {"tvshows": [
        {"tvshowid": 7, "title": "Show", "art": {"fanart": "fan-show"}}]}}
    SENT.clear()
    music = h._fetch_follow_library("music")
    check([i["fanart"] for i in music] == ["fan-band"], "an artist without fanart is skipped")
    check(SENT[-1]["params"]["limits"]["end"] == service.FunctionalHelper.BG_FOLLOW_MUSIC_ASK,
          "music asks for BG_FOLLOW_MUSIC_ASK artists to find enough with fanart")
    RPC["AudioLibrary.GetArtists"] = {"result": {"artists": [
        {"artistid": i, "artist": "A%d" % i, "fanart": "f%d" % i} for i in range(45)]}}
    check(len(h._fetch_follow_library("music")) == service.FunctionalHelper.BG_COUNT,
          "music keeps at most BG_COUNT artists")
    check(music and music[0]["dbtype"] == "artist" and music[0]["label"] == "Band",
          "an artist item is labelled by name with dbtype artist")
    shows = h._fetch_follow_library("tvshows")
    check([i["dbtype"] for i in shows] == ["tvshow"], "TV Shows fetches shows")
    RPC.clear()
    try:
        h._fetch_follow_library("movies")
        check(False, "a library that does not answer raises LookupError")
    except LookupError:
        pass


def test_edge_buttons_keep_follow():
    """<summary>The edge buttons keep the kind followed when focus reached them, and follow
    nothing when reached from a tile that was not followed.</summary>"""
    print("running test_edge_buttons_keep_follow")
    h = setup()
    tick(h)
    for button in ("9310", "9311"):
        LABELS["System.CurrentControlId"] = button
        h.update_home_bg()
        check(h._bg_source == "follow:movies" and prop("home_bg_follow") == "1",
              "edge button %s keeps following Movies, got %r" % (button, h._bg_source))
        check(prop("home_bg_fanart") == "movie-0", "the film stays up on %s" % button)
    LABELS["System.CurrentControlId"] = "9004"
    tick(h)
    LABELS["System.CurrentControlId"] = "9311"
    h.update_home_bg()
    check(h._bg_source == "recent" and prop("home_bg_follow") == "",
          "from Pictures the edge button follows nothing, got %r" % h._bg_source)


def test_no_blank_while_fetching():
    """<summary>With the switch on, a source with no list yet keeps the picture on screen
    while it is fetched; with it off, the old blank is unchanged.</summary>"""
    print("running test_no_blank_while_fetching")
    h = setup(focus="9004")
    tick(h)
    shown = prop("home_bg_fanart")
    LABELS["System.CurrentControlId"] = "9002"
    h.update_home_bg()  # TV Shows has no list yet and the fetch is in flight
    check(h._bg_source == "follow:tvshows", "the source moves to TV Shows")
    check(prop("home_bg_fanart") == shown, "the recent picture stays while TV Shows is fetched, got %r"
          % prop("home_bg_fanart"))
    h = setup(on=False, focus="9004")
    tick(h)
    LABELS["Skin.String(bg_mode)"] = "random"
    h.update_home_bg()
    check(prop("home_bg_fanart") == "", "switch off: a mode change still blanks while fetching, as before")


def test_library_event_clears_cache():
    """<summary>A library refresh empties the kept lists as well as the current one.</summary>"""
    print("running test_library_event_clears_cache")
    h = setup()
    h._bg_cache = {"recent": (list(RECENT), service.time.time(), 1)}
    h._lib_event_first = 1.0
    h._lib_event_last = 0.0
    h.apply_library_events()
    check(h._bg_cache == {}, "the cache is empty after a library event")


def test_xml_stands_down():
    """<summary>The static image and the folder slideshow stand down while following, once the
    followed fanart is up, the edge buttons are untouched, and nothing else reads the property.</summary>"""
    print("running test_xml_stands_down")
    inc = open(os.path.join(XML, "Includes.xml"), encoding="utf-8").read()
    home = open(os.path.join(XML, "Includes_Home.xml"), encoding="utf-8").read()
    static = re.search(r"<visible>(\[String\.IsEqual\(Skin\.String\(bg_mode\),image\) \+ !String\.IsEmpty\(Skin\.String\(home_background\)\)\][^<]*)</visible>", inc)
    check(static and static.group(1).endswith(STAND_DOWN), "the static image hides once the followed fanart is up")
    folder = re.search(r"<visible>(\[String\.IsEqual\(Skin\.String\(bg_mode\),folder\)[^<]*)</visible>", inc)
    check(folder and folder.group(1).endswith(STAND_DOWN), "the folder slideshow hides once the followed fanart is up")
    check("home_bg_follow" not in home, "the edge buttons do not read the property; they keep the follow going")
    users = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            users += [name] * open(os.path.join(XML, name), encoding="utf-8").read().count("home_bg_follow")
    check(users == ["Includes.xml", "Includes.xml"], "home_bg_follow is read in those two places only, found %s" % users)
    src = open(os.path.join(SKIN, "service.py"), encoding="utf-8").read()
    check(src.count('setProperty("home_bg_follow"') == 1, "only _set_follow_prop writes home_bg_follow")
    check(not re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(\s*bg_follow_tile", src),
          "the service never writes the switch")


def test_settings_row():
    """<summary>The row on the Background page, its only writer, strings, help and preview form None.</summary>"""
    print("running test_settings_row")
    settings = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    rows = [c for c in settings.iter("control") if c.get("id") == ROW_ID]
    check(len(rows) == 1, "one control %s" % ROW_ID)
    if rows:
        row = rows[0]
        page = next((g for g in settings.iter("control") if g.get("type") == "group"
                     and "settings_category),background)" in " ".join(v.text or "" for v in g.findall("visible"))
                     and row in list(g.iter("control"))), None)
        check(page is not None, "row %s is on the Background page" % ROW_ID)
        for tag, want in (("label", LABEL), ("selected", SWITCH),
                          ("onclick", "Skin.ToggleSetting(bg_follow_tile)"),
                          ("visible", "!String.IsEmpty(Skin.String(bg_mode))")):
            check((row.findtext(tag) or "").strip() == want, "row %s %s is %s" % (ROW_ID, tag, want))
    writers = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            text = open(os.path.join(XML, name), encoding="utf-8").read()
            writers += [name] * len(re.findall(r"Skin\.(?:SetBool|ToggleSetting|Reset)\(\s*bg_follow_tile\s*[,)]", text))
    check(writers == ["SkinSettings.xml"], "the row is the switch's only writer, found %s" % writers)
    po = open(PO, encoding="utf-8").read()
    for sid in (LABEL, HELP):
        check(po.count('msgctxt "#%s"' % sid) == 1, "strings.po defines #%s once" % sid)
    m = re.search(r'msgctxt "#%s"\nmsgid "([^"]*)"' % HELP, po)
    check(bool(m) and "[CR]Where: " in m.group(1), "the help string has a Where line")
    helpxml = open(os.path.join(XML, "Includes_SettingsHelp.xml"), encoding="utf-8").read()
    check('<value condition="Control.HasFocus(%s)">$LOCALIZE[%s]</value>' % (ROW_ID, HELP) in helpxml,
          "Includes_SettingsHelp maps the row to its help")
    preview = {e.get("name"): e.text or "" for e in
               ET.parse(os.path.join(XML, "Includes_SettingsPreview.xml")).getroot().iter("expression")}
    focus = "Control.HasFocus(%s)" % ROW_ID
    check(focus in preview.get("settings_preview_none", ""), "the row is in settings_preview_none")
    check(not any(focus in v for k, v in preview.items() if k != "settings_preview_none"),
          "the row is in no other preview list")


def main():
    """<summary>Runs every check and reports.</summary>
    <returns>0 when all pass, 1 otherwise.</returns>"""
    for test in (test_tile_ids_match_home, test_follow_kind, test_switch_off_changes_nothing,
                 test_follow_and_return, test_static_image_mode, test_empty_kind_gives_way,
                 test_edge_buttons_keep_follow, test_no_blank_while_fetching,
                 test_library_event_clears_cache, test_fetch_follow_library,
                 test_xml_stands_down, test_settings_row):
        test()
    if FAILURES:
        print("test_focus_background: %d check(s) failed" % len(FAILURES))
        return 1
    print("test_focus_background: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
