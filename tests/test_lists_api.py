#!/usr/bin/env python3
"""
<summary>
Tests for lists_api.py, the add-on API through which the JellyStat dashboard manages
the skin's named lists.
</summary>
<remarks>
No Kodi is needed. The xbmc modules are stubbed in sys.modules before the real
service.py is imported, so every write goes through the service's own list code,
locks and save, exactly as on a TV. The profile folder is a temporary directory and
the library is a small fake answering the JSON-RPC calls the code makes. The last
test starts the real HTTP server on a loopback port and checks the Host, token and
size gates and the discovery property. Exits non zero when a check fails.

Usage:
    python3 tests/test_lists_api.py
</remarks>
"""

import io
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
PROFILE = tempfile.mkdtemp(prefix="functional-lists-api-")

# ---- the fake library -------------------------------------------------------

MOVIES = {12: {"movieid": 12, "title": "Metropolis", "year": 1927, "runtime": 9180,
               "file": "/media/films/Metropolis.mkv", "art": {"poster": "poster12"}},
          13: {"movieid": 13, "title": "Metropolitan", "year": 1990, "runtime": 5880,
               "file": "/media/films/Metropolitan.mkv", "art": {}}}
SHOWS = {5: {"tvshowid": 5, "title": "Metro Line", "year": 2020, "episode": 2,
             "art": {"poster": "show5"}}}
EPISODES = {34: {"episodeid": 34, "tvshowid": 5, "title": "Pilot", "showtitle": "Metro Line",
                 "season": 1, "episode": 1, "runtime": 2520, "file": "/media/tv/ml/s01e01.mkv"},
            35: {"episodeid": 35, "tvshowid": 5, "title": "Second", "showtitle": "Metro Line",
                 "season": 1, "episode": 2, "runtime": 2580, "file": "/media/tv/ml/s01e02.mkv"},
            # Specials: season 0, which a whole show row leaves out.
            36: {"episodeid": 36, "tvshowid": 5, "title": "Special", "showtitle": "Metro Line",
                 "season": 0, "episode": 1, "runtime": 600, "file": "/media/tv/ml/s00e01.mkv"}}


def _contains(value, q):
    """<summary>The library's case insensitive "contains" filter.</summary>
    <param name="value">The field's text, or None.</param>
    <param name="q">The search text.</param>
    <returns>True when q is inside value, ignoring case.</returns>"""
    return q.lower() in (value or "").lower()


def fake_jsonrpc(text):
    """
    <summary>
    Answer one JSON-RPC request from the fake library, as xbmc.executeJSONRPC would.
    </summary>
    <param name="text">The request as JSON text.</param>
    <returns>The reply as JSON text.</returns>
    """
    req = json.loads(text)
    method, p = req["method"], req.get("params") or {}
    result = {}
    if method == "VideoLibrary.GetMovieDetails" and p["movieid"] in MOVIES:
        result = {"moviedetails": dict(MOVIES[p["movieid"]], label=MOVIES[p["movieid"]]["title"])}
    elif method == "VideoLibrary.GetEpisodeDetails" and p["episodeid"] in EPISODES:
        result = {"episodedetails": EPISODES[p["episodeid"]]}
    elif method == "VideoLibrary.GetTVShowDetails" and p["tvshowid"] in SHOWS:
        result = {"tvshowdetails": SHOWS[p["tvshowid"]]}
    elif method == "VideoLibrary.GetEpisodes" and "tvshowid" in p:
        result = {"episodes": [e for e in EPISODES.values() if e["tvshowid"] == p["tvshowid"]]}
    elif method == "VideoLibrary.GetMovies":
        q = p["filter"]["value"]
        result = {"movies": [m for m in MOVIES.values() if _contains(m["title"], q)]}
    elif method == "VideoLibrary.GetTVShows":
        q = p["filter"]["value"]
        result = {"tvshows": [s for s in SHOWS.values() if _contains(s["title"], q)]}
    elif method == "VideoLibrary.GetEpisodes":
        q = p["filter"]["value"]
        result = {"episodes": [e for e in EPISODES.values() if _contains(e["showtitle"], q)]}
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})


# ---- Kodi stubs --------------------------------------------------------------

PROPS = {}
SKIN_SETTINGS = set()
# Conditions other than Skin.HasSetting that read as true, such as
# "Window.IsActive(startup)" while a test pretends the splash is up.
CONDS = set()


class _Window:
    """<summary>A Home window whose properties live in PROPS.</summary>"""

    def __init__(self, _wid=None):
        """<summary>Any window id maps to the one property store.</summary>
        <param name="_wid">The window id, ignored.</param>"""

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Store a property.</summary>
        <param name="key">Property name.</param>
        <param name="value">Its text.</param>"""
        PROPS[key] = value

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Read a property, '' when unset.</summary>
        <param name="key">Property name.</param>
        <returns>The stored text, or ''.</returns>"""
        return PROPS.get(key, "")

    def clearProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Remove a property.</summary>
        <param name="key">Property name.</param>"""
        PROPS.pop(key, None)


class _Dialog:
    """<summary>A dialog that records toasts and answers nothing.</summary>"""

    toasts = []

    def notification(self, *args, **_kw):
        """<summary>Record a toast.</summary>"""
        _Dialog.toasts.append(args)

    def yesno(self, *_a, **_kw):
        """<summary>Never confirms.</summary>"""
        return False


class _Monitor:
    """<summary>xbmc.Monitor, as FunctionalHelper's base class.</summary>"""

    def abortRequested(self):  # noqa: N802 (Kodi API)
        """<summary>Kodi is never shutting down here.</summary>"""
        return False


def _cond(text):
    """<summary>getCondVisibility for Skin.HasSetting and the CONDS set; everything
    else is false.</summary>
    <param name="text">The condition as the service writes it.</param>
    <returns>True for a skin setting in SKIN_SETTINGS or a condition in CONDS.</returns>"""
    if text.startswith("Skin.HasSetting(") and text.endswith(")"):
        return text[len("Skin.HasSetting("):-1] in SKIN_SETTINGS
    return text in CONDS


def _load_strings():
    """
    <summary>
    The skin's English strings from strings.po, as Kodi's string table holds them.
    </summary>
    <returns>A dict of string id to text.</returns>
    <remarks>
    Several are format templates the service fills in, so a stub returning
    nothing would break them rather than test them.
    </remarks>
    """
    table, sid = {}, None
    path = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith('msgctxt "#'):
                sid = int(line.split("#", 1)[1].split('"', 1)[0])
            elif line.startswith("msgid ") and sid is not None:
                table[sid] = json.loads(line[len("msgid "):])
                sid = None
    return table


STRINGS = _load_strings()


def _translate(path):
    """<summary>special:// paths into the temporary profile.</summary>
    <param name="path">A special:// or plain path.</param>
    <returns>The local path under PROFILE, or the path unchanged.</returns>"""
    for prefix in ("special://profile/", "special://temp/"):
        if path.startswith(prefix):
            return os.path.join(PROFILE, path[len(prefix):])
    return path


xbmc = types.ModuleType("xbmc")
xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
xbmc.log = lambda *a, **k: None
xbmc.executeJSONRPC = fake_jsonrpc
xbmc.getCondVisibility = _cond
xbmc.getInfoLabel = lambda label: "0.23.0" if label.startswith("System.AddonVersion") else ""
xbmc.getLocalizedString = lambda sid: STRINGS.get(sid, "")
xbmc.executebuiltin = lambda *a, **k: None
xbmc.Monitor = _Monitor
xbmc.Player = type("Player", (), {"isPlaying": lambda self: False})

xbmcgui = types.ModuleType("xbmcgui")
xbmcgui.Window = _Window
xbmcgui.Dialog = _Dialog
xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = (
    "info", "warning", "error")
xbmcgui.INPUT_ALPHANUM = 0

xbmcaddon = types.ModuleType("xbmcaddon")
xbmcaddon.Addon = lambda *_a: types.SimpleNamespace(
    getLocalizedString=lambda _sid: "", getAddonInfo=lambda _k: "")

xbmcvfs = types.ModuleType("xbmcvfs")
xbmcvfs.translatePath = _translate
xbmcvfs.exists = lambda p: os.path.exists(_translate(p))
xbmcvfs.mkdirs = lambda p: os.makedirs(_translate(p), exist_ok=True) or True

for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon),
                  ("xbmcvfs", xbmcvfs)):
    sys.modules[name] = mod
sys.path.insert(0, SKIN)

import lists_api  # noqa: E402
import service  # noqa: E402

LISTS_FILE = os.path.join(PROFILE, "addon_data", "skin.functional", "lists.json")

# ---- harness -------------------------------------------------------------------

FAILURES = []


def check(cond, what):
    """
    <summary>
    Record one check, printing it when it fails.
    </summary>
    <param name="cond">True when the check passes.</param>
    <param name="what">What was being checked.</param>
    """
    if not cond:
        FAILURES.append(what)
        print("FAIL: " + what)


def seed(lists, last="", sort=""):
    """
    <summary>
    Write a lists.json and return a fresh helper that has loaded it.
    </summary>
    <param name="lists">The list dicts to write.</param>
    <param name="last">The Add To List target.</param>
    <param name="sort">The kept order.</param>
    <returns>A FunctionalHelper.</returns>
    """
    os.makedirs(os.path.dirname(LISTS_FILE), exist_ok=True)
    for suffix in ("", ".previous"):
        if os.path.exists(LISTS_FILE + suffix):
            os.remove(LISTS_FILE + suffix)
    with open(LISTS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "last": last, "sort": sort, "lists": lists}, fh)
    helper = service.FunctionalHelper()
    helper._lists_load()
    return helper


def call(helper, method, path, body=None, if_match=None, query=None):
    """
    <summary>
    Route one request through lists_api.handle and return what it answered.
    </summary>
    <param name="helper">The FunctionalHelper from seed().</param>
    <param name="method">GET, POST, PUT or DELETE.</param>
    <param name="path">The URL path.</param>
    <param name="body">The parsed JSON body, or None.</param>
    <param name="if_match">The If-Match header value, or None.</param>
    <param name="query">The parsed query as parse_qs gives it, or None for none.</param>
    <returns>(status, payload, headers); an ApiError becomes its status and body.</returns>
    """
    try:
        return lists_api.handle(helper, method, path, query or {}, body, if_match)
    except lists_api.ApiError as err:
        return err.status, {"error": {"code": err.code, "message": err.message,
                                      "field": err.field}}, err.headers


def on_disk():
    """<summary>lists.json as saved.</summary>"""
    with open(LISTS_FILE, encoding="utf-8") as fh:
        return json.load(fh)


SONG = {"label": "A Song", "file": "plugin://music/track?token=abc", "dbtype": "",
        "kind": "music", "duration": 200}
GROUP = {"label": "Metro Line", "dbtype": "tvshow", "dbid": 5, "show": "Metro Line",
         "count": 2, "skip": ["1x1"]}

# ---- tests ---------------------------------------------------------------------


def test_info_and_schema():
    """<summary>/info and /schema describe one resource, lists, with its fields.</summary>"""
    helper = seed([])
    status, body, _h = call(helper, "GET", "/info")
    check(status == 200 and body["id"] == "skin.functional", "info answers")
    check(body["resources"][0]["name"] == "lists" and body["backup"] and body["restore"],
          "info lists the resource and backup")
    status, body, _h = call(helper, "GET", "/schema")
    keys = [f["key"] for f in body["resources"]["lists"]["fields"]]
    check(keys == ["name", "autoremove", "items", "summary", "radarr"], "schema fields")
    status, _b, headers = call(helper, "POST", "/info")
    check(status == 405 and headers.get("Allow") == "GET", "info refuses POST")
    status, _b, _h = call(helper, "GET", "/nothing")
    check(status == 404, "unknown path is 404")


def test_create():
    """<summary>POST /lists: ETag rules, names, library items, caps and side effects.</summary>"""
    helper = seed([{"name": "Old", "items": [], "seq": 1}], last="Old")
    _s, listing, headers = call(helper, "GET", "/lists")
    etag = headers["ETag"]
    check(len(listing["items"]) == 1 and listing["items"][0]["id"] == 1, "list carries seq id")
    status, _b, _h = call(helper, "POST", "/lists", {"name": "New"})
    check(status == 428, "create without If-Match is 428")
    status, _b, _h = call(helper, "POST", "/lists", {"name": "New"}, '"stale"')
    check(status == 412, "create with a stale ETag is 412")
    status, body, _h = call(helper, "POST", "/lists", {"name": " old "}, etag)
    check(status == 422 and body["error"]["field"] == "name", "duplicate name refused")
    status, body, _h = call(helper, "POST", "/lists", {"name": ""}, etag)
    check(status == 422, "empty name refused")
    status, body, _h = call(helper, "POST", "/lists", {"name": "x" * 101}, etag)
    check(status == 422, "long name refused")
    status, body, _h = call(helper, "POST", "/lists", {"name": "Films", "items": [
        {"key": "movie:99"}]}, etag)
    check(status == 422 and body["error"]["field"] == "items", "missing film refused")
    status, body, _h = call(helper, "POST", "/lists", {"name": "Films", "items": [
        {"key": "file:0123456789abcdef"}]}, etag)
    check(status == 422, "a path key not on the list is refused")
    status, body, _h = call(helper, "POST", "/lists", {"name": "Films", "items": [
        "movie:12"]}, etag)
    check(status == 422, "a bare string pick is refused")
    status, body, headers = call(helper, "POST", "/lists", {
        "name": "Films", "autoremove": True,
        "items": [{"key": "movie:12", "label": "ignored"}, {"key": "tvshow:5"},
                  {"key": "episode:34"}, {"key": "movie:12"}]}, etag)
    check(status == 201, "create answers 201")
    check(body["name"] == "Films" and body["autoremove"] is True, "created fields")
    keys = [p["key"] for p in body["items"]]
    check(keys == ["movie:12", "tvshow:5", "episode:34"], "items kept in order, duplicate dropped")
    check(body["items"][0]["label"].startswith("Metropolis"), "label from the library, not the browser")
    check(headers["ETag"] != etag, "create returns a new ETag")
    saved = on_disk()
    films = next(l for l in saved["lists"] if l["name"] == "Films")
    check(films["seq"] == 2 and films["radarr"] is False and films["fill"] == 0, "stored shape")
    check(films["items"][0]["file"] == "/media/films/Metropolis.mkv", "film record from library")
    check(films["items"][1]["count"] == 2 and films["items"][1]["label"] == "Metro Line",
          "show filled by the service's group fill")
    check(saved["last"] == "Old", "Add To List target untouched by create")
    check(os.path.exists(LISTS_FILE + ".previous"), "previous copy kept")


def test_cap():
    """<summary>A 61st list is refused.</summary>"""
    helper = seed([{"name": "L%d" % i, "items": [], "seq": i}
                   for i in range(1, helper_max() + 1)])
    _s, _b, headers = call(helper, "GET", "/lists")
    status, body, _h = call(helper, "POST", "/lists", {"name": "One more"}, headers["ETag"])
    check(status == 422 and "room for" in body["error"]["message"], "list cap holds")


def helper_max():
    """<summary>The service's own list cap.</summary>"""
    return service.FunctionalHelper.LISTS_MAX


def test_replace():
    """<summary>PUT keeps stored items by key, untouched, and what the API does not own.</summary>"""
    helper = seed([{"name": "Mixed", "seq": 7, "fill": 90, "radarr": True, "autoremove": False,
                    "items": [SONG, GROUP, {"label": "Metropolis", "dbtype": "movie",
                                            "dbid": 12, "file": "/media/films/Metropolis.mkv"}]}],
                  last="Mixed")
    status, rec, headers = call(helper, "GET", "/lists/7")
    check(status == 200 and len(rec["items"]) == 3, "get one list")
    song_key = rec["items"][0]["key"]
    check(song_key.startswith("file:") and "token" not in json.dumps(rec),
          "a path never reaches the browser")
    check(rec["radarr"].startswith("Yes"), "radarr tie shown read only")
    status, _b, _h = call(helper, "GET", "/lists/8")
    check(status == 404, "unknown list is 404")
    status, rec2, headers2 = call(helper, "PUT", "/lists/7", {
        "name": "Renamed", "autoremove": True, "radarr": "No",
        "items": [{"key": "movie:13"}, {"key": song_key}, {"key": "tvshow:5"}]},
        headers["ETag"])
    check(status == 200 and rec2["name"] == "Renamed", "rename")
    check([p["key"] for p in rec2["items"]] == ["movie:13", song_key, "tvshow:5"],
          "reorder, remove and add in one PUT")
    saved = on_disk()
    lst = saved["lists"][0]
    check(lst["seq"] == 7 and lst["fill"] == 90 and lst["radarr"] is True,
          "seq, fill and radarr tie kept")
    check(lst["items"][1]["file"] == SONG["file"], "stored song kept as it was")
    check(lst["items"][2]["skip"] == ["1x1"], "kept show keeps its Remove Watched skips")
    check(saved["last"] == "Renamed", "Add To List target follows the rename")
    status, _b, _h = call(helper, "PUT", "/lists/7", {"name": "Again"}, headers["ETag"])
    check(status == 412, "old ETag refused after a change")
    status, rec3, _h = call(helper, "PUT", "/lists/7", {"autoremove": False}, headers2["ETag"])
    check(status == 200 and rec3["name"] == "Renamed" and len(rec3["items"]) == 3,
          "fields left out are kept")


def test_kodi_side_change_is_stale():
    """<summary>A change made on the TV after a read makes the dashboard's write stale.</summary>"""
    helper = seed([{"name": "A", "items": [], "seq": 1}])
    _s, _b, headers = call(helper, "GET", "/lists/1")
    with helper._lists_lock:
        helper._lists[0]["autoremove"] = True
    helper._lists_save()
    status, _b, _h = call(helper, "PUT", "/lists/1", {"name": "B"}, headers["ETag"])
    check(status == 412, "a TV side change is detected")


def test_delete():
    """<summary>DELETE removes the list and clears the Add To List target.</summary>"""
    helper = seed([{"name": "A", "items": [], "seq": 1}, {"name": "B", "items": [], "seq": 2}],
                  last="B")
    _s, _b, headers = call(helper, "GET", "/lists")
    status, body, _h = call(helper, "DELETE", "/lists/2", None, headers["ETag"])
    check(status == 204 and body is None, "delete answers 204")
    saved = on_disk()
    check([l["name"] for l in saved["lists"]] == ["A"] and saved["last"] == "",
          "deleted and target cleared")
    status, _b, _h = call(helper, "DELETE", "/lists/2", None, headers["ETag"])
    check(status == 404, "deleting it again is 404")


def test_new_and_sort():
    """<summary>/lists/new is blank, and a kept sort moves lists without changing ids.</summary>"""
    helper = seed([{"name": "Zed", "items": [], "seq": 1}], sort="name")
    status, blank, _h = call(helper, "GET", "/lists/new")
    check(status == 200 and blank["name"] == "" and blank["items"] == [], "blank record")
    _s, _b, headers = call(helper, "GET", "/lists")
    status, rec, _h = call(helper, "POST", "/lists", {"name": "Alpha"}, headers["ETag"])
    _s, listing, _h = call(helper, "GET", "/lists")
    check([(l["name"], l["id"]) for l in listing["items"]] == [("Alpha", 2), ("Zed", 1)],
          "kept name order applied, ids stable")


def test_search():
    """<summary>/options/media searches films, shows and episodes.</summary>"""
    helper = seed([])
    status, body, _h = call(helper, "GET", "/options/media", query={"q": [""]})
    check(status == 200 and body == {"items": [], "more": True}, "no search, no list")
    status, body, _h = call(helper, "GET", "/options/media", query={"q": ["metro"]})
    keys = [o["value"]["key"] for o in body["items"]]
    check(keys == ["movie:12", "movie:13", "tvshow:5", "episode:34", "episode:35", "episode:36"],
          "films, shows, then episodes")
    check(all(o["label"] == o["value"]["label"] for o in body["items"]), "labels agree")
    labels = {o["value"]["key"]: o["label"] for o in body["items"]}
    check("S00E01" in labels["episode:36"], "a Specials episode keeps season 0 in search")
    check("episode" not in labels["tvshow:5"], "a show in search claims no episode count")
    _s, _b, headers = call(helper, "GET", "/lists")
    status, made, _h = call(helper, "POST", "/lists", {"name": "Specials", "items": [
        {"key": "episode:36"}]}, headers["ETag"])
    check(status == 201 and "S00E01" in made["items"][0]["label"],
          "a Specials episode keeps season 0 once added")
    check(on_disk()["lists"][0]["items"][0]["season"] == "0", "season 0 stored as '0'")
    status, _b, _h = call(helper, "GET", "/options/other")
    check(status == 404, "unknown option source is 404")


def test_backup_restore():
    """<summary>A backup restores, replaces everything, and keeps this box's choices.</summary>"""
    helper = seed([{"name": "Tied", "items": [], "seq": 1, "radarr": True},
                   {"name": "Other", "items": [], "seq": 2}], last="Other", sort="name")
    status, doc, headers = call(helper, "GET", "/backup")
    check(status == 200 and doc["type"] == lists_api.BACKUP_TYPE, "backup document")
    check("attachment" in headers.get("Content-Disposition", ""), "backup downloads")
    check(len(helper._lists_parse(json.dumps(doc))[0]) == 2, "backup reads as a lists.json")
    doc["lists"] = [{"name": "Tied", "items": [], "seq": 4, "radarr": False},
                    {"name": "Fresh", "items": [], "seq": 5, "radarr": True}]
    status, _b, _h = call(helper, "POST", "/restore", doc, '"stale"')
    check(status == 412, "restore checks If-Match")
    status, _b, _h = call(helper, "POST", "/restore", {"lists": []}, headers["ETag"])
    check(status == 422, "restore refuses a document without the type")
    status, body, _h = call(helper, "POST", "/restore", doc, headers["ETag"])
    check(status == 200 and body["restored"] == 2, "restore answers")
    saved = on_disk()
    by_name = {l["name"]: l for l in saved["lists"]}
    check(set(by_name) == {"Tied", "Fresh"}, "restore replaces every list")
    check(by_name["Tied"]["radarr"] and not by_name["Fresh"]["radarr"],
          "radarr tie stays with this box's choice, never the file's")
    check(saved["last"] == "" and saved["sort"] == "name", "target cleared, sort kept")
    check(os.path.exists(LISTS_FILE + ".previous"), "the replaced file is kept as previous")


def test_restore_repeated_names():
    """<summary>A backup naming a list twice, ignoring case, is refused, and the
    Radarr tie is only ever put on one restored list.</summary>"""
    helper = seed([{"name": "Tied", "items": [], "seq": 1, "radarr": True}])
    status, doc, headers = call(helper, "GET", "/backup")
    doc["lists"] = [{"name": "Tied", "items": [], "seq": 1},
                    {"name": "tied", "items": [], "seq": 2}]
    status, body, _h = call(helper, "POST", "/restore", doc, headers["ETag"])
    check(status == 422 and body["error"]["code"] == "validation"
          and "tied" in body["error"]["message"].lower(),
          "a backup with a repeated name is refused, naming it")
    with helper._lists_lock:
        names = [l["name"] for l in helper._lists]
    check(names == ["Tied"], "nothing changed by the refused restore")
    # The tie belt below that check: with the check stood down, a document
    # naming the tied list twice still restores with exactly one list tied.
    doc["lists"] = [{"name": "Tied", "items": [], "seq": 1, "radarr": True},
                    {"name": "Tied", "items": [], "seq": 2, "radarr": True}]
    real_check = lists_api._check_backup_names
    lists_api._check_backup_names = lambda body: None
    try:
        status, body, _h = call(helper, "POST", "/restore", doc, headers["ETag"])
    finally:
        lists_api._check_backup_names = real_check
    saved = on_disk()["lists"]
    check(status == 200 and [l["name"] for l in saved] == ["Tied", "Tied (2)"],
          "the parser renames the repeat rather than keeping a pair")
    check([l["name"] for l in saved if l["radarr"]] == ["Tied"], "the tie lands on one list only")


def test_etag_is_the_view():
    """<summary>The ETag follows what the dashboard can see: unchanged by a no op
    write, by an equivalent save and by a TV only setting, changed by anything
    shown.</summary>"""
    helper = seed([{"name": "A", "items": [GROUP], "seq": 1, "fill": 0},
                   {"name": "B", "items": [], "seq": 2}], sort="name")
    _s, _b, headers = call(helper, "GET", "/lists")
    first = headers["ETag"]
    status, _b, headers2 = call(helper, "PUT", "/lists/1", {"name": "A"}, first)
    check(status == 200 and headers2["ETag"] == first, "a no op PUT keeps the ETag")
    helper._lists_save()
    _s, _b, headers3 = call(helper, "GET", "/lists")
    check(headers3["ETag"] == first, "an equivalent TV side save keeps the ETag")
    with helper._lists_lock:
        helper._lists[0]["fill"] = 120
    helper._lists_save()
    _s, _b, headers4 = call(helper, "GET", "/lists")
    check(headers4["ETag"] == first, "Port by Time set on the TV keeps the ETag")
    with helper._lists_lock:
        helper._lists[0]["items"][0]["skip"] = ["1x1", "1x2"]
        helper._lists[0]["items"][0]["count"] = 0
    helper._lists_save()
    _s, _b, headers5 = call(helper, "GET", "/lists")
    check(headers5["ETag"] != first, "a Remove Watched skip that changes a row's count changes it")
    before = headers5["ETag"]
    with helper._lists_lock:
        helper._lists_sort_mode = "newest"
    helper._lists_save()
    _s, listing, headers6 = call(helper, "GET", "/lists")
    check([l["name"] for l in listing["items"]] == ["B", "A"] and headers6["ETag"] != before,
          "a new kept order changes it")
    status, _b, _h = call(helper, "PUT", "/lists/2", {"autoremove": True}, first)
    check(status == 412, "the first ETag is stale after a real change")


def test_frozen():
    """<summary>Writes are refused while the service will not save.</summary>"""
    helper = seed([{"name": "A", "items": [], "seq": 1}])
    _s, _b, headers = call(helper, "GET", "/lists")
    helper._lists_frozen = True
    status, body, _h = call(helper, "POST", "/lists", {"name": "B"}, headers["ETag"])
    check(status == 503 and body["error"]["code"] == "unavailable", "frozen save refused")


def test_http():
    """<summary>The real server: discovery, Host, token, size and a round trip.</summary>"""
    helper = seed([{"name": "A", "items": [], "seq": 1}])
    SKIN_SETTINGS.add("lists_api_off")
    helper.update_lists_api()
    check(lists_api.DISCOVERY_PROPERTY not in PROPS, "switched off, not announced")
    SKIN_SETTINGS.discard("lists_api_off")
    CONDS.add("Window.IsActive(startup)")
    helper.update_lists_api()
    check(lists_api.DISCOVERY_PROPERTY not in PROPS, "nothing starts while the splash is up")
    CONDS.discard("Window.IsActive(startup)")
    helper.update_lists_api()
    announce = json.loads(PROPS[lists_api.DISCOVERY_PROPERTY])
    port, token = announce["port"], announce["token"]
    check(announce["api"] == 1 and announce["version"] == "0.23.0", "announced")
    base = "http://127.0.0.1:%d" % port

    def get(path, headers):
        """<summary>One GET; returns (status, body).</summary>
        <param name="path">The URL path.</param>
        <param name="headers">Request headers; urllib adds Host itself.</param>
        <returns>(status, parsed JSON body).</returns>"""
        req = urllib.request.Request(base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"null")

    def raw(request, timeout=3):
        """<summary>One request written straight to the socket, for what urllib
        will not send.</summary>
        <param name="request">The whole request text, headers and blank line included.</param>
        <param name="timeout">Seconds to wait for the server's answer.</param>
        <returns>(status line, header lines, body text), or ('', [], '') on a timeout.</returns>"""
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        sock.sendall(request.encode("utf-8"))
        data = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            return "", [], ""
        finally:
            sock.close()
        head, _sep, body = data.decode("utf-8", "replace").partition("\r\n\r\n")
        lines = head.split("\r\n")
        return lines[0], lines[1:], body

    status, _b = get("/info", {"Host": "evil.example"})
    check(status == 400, "wrong Host refused")
    status, _b = get("/info", {})
    check(status == 401, "missing token refused")
    status, body = get("/lists", {lists_api.TOKEN_HEADER: token})
    check(status == 200 and body["items"][0]["name"] == "A", "round trip")
    # A client that stops reading before the answer must not print a
    # traceback to stderr: the server logs it at debug and moves on.
    captured, real_stderr = io.StringIO(), sys.stderr
    sys.stderr = captured
    try:
        req = urllib.request.Request(base + "/lists", method="POST", data=b"x" * 10,
                                     headers={lists_api.TOKEN_HEADER: token,
                                              "Content-Length": str(lists_api.MAX_BODY + 1)})
        try:
            urllib.request.urlopen(req, timeout=5)
            status = 200
        except urllib.error.HTTPError as err:
            status = err.code
        except (urllib.error.URLError, ConnectionError):
            status = 413  # the server answered and closed before the client finished
        check(status == 413, "oversized body refused")
        time.sleep(0.3)
    finally:
        sys.stderr = real_stderr
    check("Traceback" not in captured.getvalue(), "a client going away leaves stderr alone")
    host = "Host: 127.0.0.1:%d\r\n" % port
    auth = "%s: %s\r\n" % (lists_api.TOKEN_HEADER, token)
    line, headers, body = raw("POST /lists HTTP/1.0\r\n" + host + auth + "Content-Length: -1\r\n\r\n")
    check(line.startswith("HTTP/1.0 400") and "negative" in body, "a negative Content-Length is 400")
    line, headers, body = raw("HEAD /info HTTP/1.0\r\n" + host + auth + "\r\n")
    check(line.startswith("HTTP/1.0 405") and "Allow: GET" in headers and body == "",
          "HEAD is 405 with Allow and no body")
    line, headers, body = raw("PATCH /lists/1 HTTP/1.0\r\n" + host + auth + "\r\n")
    check(line.startswith("HTTP/1.0 405") and "Allow: GET, PUT, DELETE" in headers
          and json.loads(body)["error"]["code"] == "method_not_allowed",
          "PATCH is the spec's 405")
    line, headers, body = raw("OPTIONS /lists HTTP/1.0\r\n" + host + auth + "\r\n")
    check(line.startswith("HTTP/1.0 405") and "Allow: GET, POST" in headers, "OPTIONS is 405")
    line, headers, body = raw("OPTIONS /lists HTTP/1.0\r\n" + host + "\r\n")
    check(line.startswith("HTTP/1.0 401"), "OPTIONS still needs the token")
    SKIN_SETTINGS.add("lists_api_off")
    helper.update_lists_api()
    check(lists_api.DISCOVERY_PROPERTY not in PROPS, "switched off again, withdrawn")
    SKIN_SETTINGS.discard("lists_api_off")


def main():
    """<summary>Run every test, clean up, and exit non zero on any failure.</summary>"""
    tests = [test_info_and_schema, test_create, test_cap, test_replace,
             test_kodi_side_change_is_stale, test_delete, test_new_and_sort, test_search,
             test_backup_restore, test_restore_repeated_names, test_etag_is_the_view,
             test_frozen, test_http]
    try:
        for test in tests:
            print("running " + test.__name__)
            test()
    finally:
        lists_api.stop()
        shutil.rmtree(PROFILE, ignore_errors=True)
    if FAILURES:
        print("test_lists_api: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_lists_api: all checks passed")


if __name__ == "__main__":
    main()
