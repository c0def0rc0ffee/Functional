# -*- coding: utf-8 -*-
"""
<summary>
The skin's add-on API: a small HTTP server on 127.0.0.1 through which the JellyStat
dashboard lists, creates, edits and deletes the skin's named lists, and backs them up
and restores them.
</summary>
<remarks>
This implements version 1 of the shared add-on API spec (ADDON-API-SPEC.md, kept
beside the Kodi projects), the same contract Engage and JellyRate follow:

- It binds to 127.0.0.1 on a port the OS picks, never to the LAN. JellyStat, in the
  same Kodi, proxies to it behind its own password.
- It announces itself in the Home window property AddonApi.skin.functional as JSON
  holding the port and a token made fresh each start, never written to disk or
  logged. Every request must carry the token as X-Addon-Api-Token.
- Every write carries If-Match with the ETag of the whole set of lists. One ETag for
  the collection, because a new list has no record of its own to carry one, and
  because the lists live in one file that is written whole.

The lists stay the service's. Nothing here reads or writes lists.json directly: every
change goes through the FunctionalHelper the service runs, under its own locks, and
is saved by its own _lists_save, so the Lists screen redraws at once, the copy kept
as lists.json.previous is made as usual, and a save refused because the file on disk
could not be read is reported rather than claimed as done. The running service holds
the lists in memory and would write over a file changed behind its back, which is
why the API has to live inside it.

Items are never taken from the browser as given. An item already on the list is
matched by its key to the stored record and kept exactly as stored, so music, plugin
streams and a whole show's Remove Watched skips survive an edit untouched. A new item
must name a film, an episode, a show or a season in this box's library; its record
is built afresh from the library, a show or season through the same fill the Lists
screen uses.

Left alone on purpose: which list Remove from Radarr acts on (it deletes files, so it
is chosen on the TV), each list's Port by Time length, the order the lists are kept
in, and the list Add To List goes to.

The service calls sync() from its slow tick and stop() on the way out. handle()
routes without a socket, which is what tests/test_lists_api.py drives.
</remarks>
"""
import copy
import hashlib
import hmac
import json
import re
import secrets
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import xbmc
import xbmcgui

ADDON_ID = "skin.functional"
API_VERSION = 1
HOME_WINDOW_ID = 10000
DISCOVERY_PROPERTY = "AddonApi." + ADDON_ID
TOKEN_HEADER = "X-Addon-Api-Token"

# Larger bodies are refused before they are read. The same limit JellyStat's proxy
# applies, so a backup over it cannot be restored through the dashboard either.
MAX_BODY = 2 ** 20

# Longest list name the API accepts. Kodi's keyboard has no limit, but the Lists
# screen shows about this much.
NAME_MAX = 100

# Most results one search returns, the spec's ceiling (7.3).
OPTIONS_MAX = 200

# The kinds of library entry a new item may name, and how each is looked up.
LIBRARY_KEY = re.compile(r"^(movie|episode|tvshow|season):([1-9][0-9]*)$")

# The type tag a backup carries, so a restore cannot be fed some other JSON file.
BACKUP_TYPE = "functional-lists-backup"

_LIST_PATH = re.compile(r"^/lists/([0-9]+)$")
_OPTION_PATH = re.compile(r"^/options/([a-z_]+)$")

_server = None
_state_lock = threading.Lock()
# One API write at a time, from the ETag check to the save.
_write_lock = threading.Lock()


class ApiError(Exception):
    """
    <summary>
    An error response in the spec's shape: a status, a code and a message for the user.
    </summary>
    """

    def __init__(self, status, code, message, field=None, headers=None):
        """
        <summary>
        Keep everything the error response needs.
        </summary>
        <param name="status">The HTTP status.</param>
        <param name="code">The spec's error code, such as 'stale'.</param>
        <param name="message">Plain UK English, shown to the user unchanged.</param>
        <param name="field">The field at fault, for a validation error.</param>
        <param name="headers">Extra response headers, such as Allow on a 405.</param>
        """
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field
        self.headers = headers or {}


def _log(message, level=xbmc.LOGINFO):
    """
    <summary>
    Write one line to Kodi's log under the skin's API tag.
    </summary>
    <param name="message">Text to log. Never the token.</param>
    <param name="level">Kodi log level, info by default.</param>
    """
    xbmc.log("[functional/lists_api] %s" % message, level)


def _jsonrpc(method, params):
    """
    <summary>
    Call Kodi's JSON-RPC API and return its result.
    </summary>
    <param name="method">RPC method name.</param>
    <param name="params">Parameter dict.</param>
    <returns>The result object, or an empty dict when the call fails.</returns>
    <remarks>
    The same call the service makes through its own _jsonrpc. This module cannot
    import the service to share it: Kodi runs service.py as __main__, so an import
    would load a second copy of it.
    </remarks>
    """
    payload = {"jsonrpc": "2.0", "method": method, "id": 1, "params": params}
    try:
        reply = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception as exc:  # noqa: BLE001
        _log("jsonrpc %s failed: %s" % (method, exc), xbmc.LOGWARNING)
        return {}
    return reply.get("result") or {}


# ---- starting and stopping ------------------------------------------------

def sync(helper, enabled):
    """
    <summary>
    Start or stop the server to match the skin's switch.
    </summary>
    <param name="helper">The service's FunctionalHelper, which owns the lists.</param>
    <param name="enabled">True when "Let JellyStat manage the lists" is on.</param>
    <remarks>
    Called once a second from the service's slow tick, so it must cost nothing when
    nothing has changed. A server that fails to start is logged and tried again on
    the next tick.
    </remarks>
    """
    if not enabled:
        stop()
        return
    if _server is not None:
        return
    try:
        start(helper)
    except Exception:  # noqa: BLE001
        _log("could not start:\n%s" % traceback.format_exc(), xbmc.LOGERROR)


def start(helper):
    """
    <summary>
    Bind the server on a free loopback port, serve on a daemon thread and announce it.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <remarks>
    The announcement goes up only after the bind succeeds, so the property never
    names a port nobody is listening on.
    </remarks>
    """
    global _server
    with _state_lock:
        if _server is not None:
            return
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        server.api_token = secrets.token_urlsafe(32)
        server.helper = helper
        threading.Thread(target=server.serve_forever, name="FunctionalListsApi",
                         daemon=True).start()
        _server = server
        port = server.server_address[1]
        xbmcgui.Window(HOME_WINDOW_ID).setProperty(DISCOVERY_PROPERTY, json.dumps({
            "api": API_VERSION,
            "port": port,
            "token": server.api_token,
            "version": _skin_version(),
        }))
        _log("listening on 127.0.0.1:%d" % port)


def stop():
    """
    <summary>
    Withdraw the announcement and shut the server down.
    </summary>
    <remarks>
    The property is cleared first, so JellyStat stops sending before the socket
    closes. shutdown() waits for the serve loop, at most half a second.
    </remarks>
    """
    global _server
    with _state_lock:
        if _server is None:
            return
        server, _server = _server, None
        try:
            xbmcgui.Window(HOME_WINDOW_ID).clearProperty(DISCOVERY_PROPERTY)
        except Exception as exc:  # noqa: BLE001
            _log("could not clear %s: %s" % (DISCOVERY_PROPERTY, exc), xbmc.LOGWARNING)
        server.shutdown()
        server.server_close()
        _log("stopped")


def _skin_version():
    """
    <summary>
    The running skin's version, or '' when Kodi will not say.
    </summary>
    """
    try:
        return xbmc.getInfoLabel("System.AddonVersion(%s)" % ADDON_ID) or ""
    except Exception:  # noqa: BLE001
        return ""


# ---- shared helpers -------------------------------------------------------

def etag_of(value):
    """
    <summary>
    An ETag for any JSON value: a short hash of it, in quotes.
    </summary>
    <param name="value">The state a write must have been made against.</param>
    <returns>The ETag header value.</returns>
    """
    blob = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return '"%s"' % hashlib.sha256(blob).hexdigest()[:20]


def _check_match(current, if_match):
    """
    <summary>
    Refuse a write that does not carry the ETag of the state it would change.
    </summary>
    <param name="current">The ETag as things stand now.</param>
    <param name="if_match">The request's If-Match header, or None.</param>
    <exception cref="ApiError">428 when it is missing, 412 when it is stale.</exception>
    """
    if not if_match:
        raise ApiError(428, "precondition_required",
                       "This change has to say which version it was made against.")
    if if_match.strip() != current:
        raise ApiError(412, "stale", "The lists were changed somewhere else. "
                                     "Reload and try again.")


def _allow(method, allowed):
    """
    <summary>
    Refuse a method the path does not offer.
    </summary>
    <param name="method">The request method.</param>
    <param name="allowed">The methods the path offers.</param>
    <exception cref="ApiError">405, with an Allow header.</exception>
    """
    if method not in allowed:
        raise ApiError(405, "method_not_allowed", "%s is not offered here." % method,
                       headers={"Allow": ", ".join(allowed)})


def _snapshot(helper):
    """
    <summary>
    A private copy of the lists as they stand, and the ETag of that state.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <returns>(lists, etag). The copy can be read without holding any lock.</returns>
    <remarks>
    Loads the lists first when the service has not yet, which is what its own tick
    does on the first pass.
    </remarks>
    """
    helper._lists_load()
    with helper._lists_lock:
        lists = copy.deepcopy(helper._lists or [])
    return lists, etag_of(lists)


def _current_etag(helper):
    """
    <summary>
    The ETag of the lists as they stand. The caller holds helper._lists_lock.
    </summary>
    """
    return etag_of(helper._lists or [])


def _refuse_if_frozen(helper):
    """
    <summary>
    Refuse a write while the service will not save.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <exception cref="ApiError">503 when saving is paused.</exception>
    <remarks>
    The service pauses saving when lists.json could not be read and could not be
    moved aside either, so that nothing writes over it. A write accepted then would
    vanish at the next restart while the dashboard reported it saved.
    </remarks>
    """
    if helper._lists_frozen:
        raise ApiError(503, "unavailable", "The lists file on the TV could not be read, "
                                           "so saving is paused. See the Lists screen.")


def _find(lists, seq):
    """
    <summary>
    The list with this id, from a list of lists.
    </summary>
    <param name="lists">The lists to search.</param>
    <param name="seq">The id, which is the list's creation number.</param>
    <returns>The list dict.</returns>
    <exception cref="ApiError">404 when there is no such list.</exception>
    """
    for lst in lists:
        if lst.get("seq") == seq:
            return lst
    raise ApiError(404, "not_found", "There is no such list. It may have been deleted.")


# ---- records ---------------------------------------------------------------

def item_key(item):
    """
    <summary>
    The key that names one stored item: its library entry, or a hash of its path.
    </summary>
    <param name="item">A clean item record.</param>
    <returns>'movie:12', 'tvshow:5' and so on, or 'file:' and 16 hex digits.</returns>
    <remarks>
    The path is hashed rather than sent so that a plugin URL, which can carry a
    token, never reaches the browser. A path key can only ever name an item that is
    already on the list; a new item must come from the library.
    </remarks>
    """
    if item.get("dbid"):
        return "%s:%d" % (item["dbtype"], item["dbid"])
    digest = hashlib.sha256((item.get("file") or "").encode("utf-8")).hexdigest()
    return "file:" + digest[:16]


def _item_text(helper, item):
    """
    <summary>
    The line the dashboard shows for one item: its title and the Lists screen's own
    second line under it.
    </summary>
    <param name="helper">The service's FunctionalHelper, for its wording.</param>
    <param name="item">A clean item record.</param>
    <returns>Such as 'Metropolis · Movie (1927) · 2h 33m'.</returns>
    """
    sub = helper._list_item_sub(item)
    return item["label"] + (" · " + sub if sub else "")


def _pick(helper, item):
    """
    <summary>
    One item as a value of the items field.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="item">A clean item record.</param>
    <returns>{"key", "label"}. Only the key counts when it comes back.</returns>
    """
    return {"key": item_key(item), "label": _item_text(helper, item)}


def _list_record(helper, lst):
    """
    <summary>
    A list in its API shape.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="lst">A list dict as the service stores it.</param>
    <returns>id, name, autoremove and items, plus readonly summary and radarr.</returns>
    """
    items = lst.get("items") or []
    count = len(items)
    total = sum(it.get("duration") or 0 for it in items)
    holds = "%d item%s" % (count, "" if count == 1 else "s")
    if total:
        holds += " · " + helper._fmt_secs(total)
    return {
        "id": lst.get("seq"),
        "name": lst.get("name", ""),
        "autoremove": bool(lst.get("autoremove")),
        "items": [_pick(helper, it) for it in items],
        "summary": holds,
        "radarr": "Yes, Remove from Radarr acts on this list" if lst.get("radarr") else "No",
    }


def _blank_record():
    """
    <summary>
    The body of GET /lists/new: a list with nothing in it, not saved.
    </summary>
    """
    return {"name": "", "autoremove": False, "items": [], "summary": "Empty", "radarr": "No"}


# ---- checking what the dashboard sent ---------------------------------------

def _check_name(body, lists, own=None):
    """
    <summary>
    The name a write asks for, checked as the Lists screen checks a typed one.
    </summary>
    <param name="body">The parsed JSON body.</param>
    <param name="lists">The lists as they stand.</param>
    <param name="own">The list being edited, so it may keep its own name.</param>
    <returns>The trimmed name.</returns>
    <exception cref="ApiError">422 when it is missing, too long or already taken,
    ignoring case.</exception>
    """
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(422, "validation", "Give the list a name.", "name")
    name = name.strip()
    if len(name) > NAME_MAX:
        raise ApiError(422, "validation",
                       "A list name can be at most %d characters." % NAME_MAX, "name")
    for lst in lists:
        if lst is own or (own is not None and lst.get("seq") == own.get("seq")):
            continue
        if lst["name"].lower() == name.lower():
            raise ApiError(422, "validation", "There is already a list called %s." % name,
                           "name")
    return name


def _check_autoremove(body, default):
    """
    <summary>
    The Remove Watched switch a write asks for.
    </summary>
    <param name="body">The parsed JSON body.</param>
    <param name="default">The value to keep when the body does not say.</param>
    <exception cref="ApiError">422 when it is not true or false.</exception>
    """
    if "autoremove" not in body:
        return default
    value = body["autoremove"]
    if not isinstance(value, bool):
        raise ApiError(422, "validation", "Remove watched must be on or off.", "autoremove")
    return value


def _num_text(value):
    """
    <summary>
    A season or episode number from the library as the text a captured item holds.
    </summary>
    <param name="value">The number Kodi returned, or None.</param>
    <returns>'0' for season 0, '' when there is none.</returns>
    <remarks>
    The service's _list_item_clean reads every field as text through "or", so the
    number 0 itself became '' and a Specials episode lost its season.
    </remarks>
    """
    return "" if value is None else str(value)


def _library_item(helper, dbtype, dbid):
    """
    <summary>
    A new item's record, built from this box's library.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="dbtype">'movie', 'episode', 'tvshow' or 'season'.</param>
    <param name="dbid">The library id.</param>
    <returns>A clean record, or None when the library has no such entry, or a show
    or season with no episodes left to play.</returns>
    <remarks>
    Fields mirror what the press and hold menu captures from a library listing, so
    an item added here behaves exactly like one added on the TV. One library query
    per item, and a show or season makes two, so this runs outside every lock.
    </remarks>
    """
    if dbtype in ("tvshow", "season"):
        item = helper._list_item_clean({"dbtype": dbtype, "dbid": dbid})
        return helper._list_group_fill(item) if item else None
    if dbtype == "movie":
        res = _jsonrpc("VideoLibrary.GetMovieDetails", {
            "movieid": dbid,
            "properties": ["title", "year", "file", "runtime", "thumbnail", "art"]})
        det = res.get("moviedetails") or {}
        raw = {"label": det.get("title"), "year": det.get("year") or ""}
    else:
        res = _jsonrpc("VideoLibrary.GetEpisodeDetails", {
            "episodeid": dbid,
            "properties": ["title", "file", "runtime", "thumbnail", "art",
                           "showtitle", "season", "episode"]})
        det = res.get("episodedetails") or {}
        raw = {"label": det.get("title"), "show": det.get("showtitle"),
               "season": _num_text(det.get("season")),
               "episode": _num_text(det.get("episode"))}
    if not det.get("file"):
        return None
    art = det.get("art") or {}
    raw.update({"dbtype": dbtype, "dbid": dbid, "file": det["file"],
                "duration": det.get("runtime") or 0,
                "thumb": art.get("poster") or art.get("thumb") or det.get("thumbnail") or ""})
    return helper._list_item_clean(raw)


def _check_items(helper, body, kept):
    """
    <summary>
    The items a write asks for, in order, as stored records.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="body">The parsed JSON body.</param>
    <param name="kept">The list's items as they stand (empty for a new list), the
    only records a sent key may keep.</param>
    <returns>Clean item records, duplicates left out.</returns>
    <exception cref="ApiError">422 when items is not an array of picks, holds more
    than the Lists screen can show, or names something neither on the list nor in
    the library.</exception>
    <remarks>
    A key matching an item already on the list keeps that stored record, deep
    copied, untouched. Any other key must be a library entry. A duplicate is
    dropped, as Add To List drops one, rather than refused.
    </remarks>
    """
    values = body.get("items", [])
    if not isinstance(values, list):
        raise ApiError(422, "validation", "Items must be a list.", "items")
    if len(values) > helper.LIST_ITEMS_MAX:
        raise ApiError(422, "validation", "A list can hold at most %d items."
                       % helper.LIST_ITEMS_MAX, "items")
    stored = {}
    for item in kept:
        stored.setdefault(item_key(item), item)
    out = []
    for value in values:
        key = value.get("key") if isinstance(value, dict) else None
        if not isinstance(key, str):
            raise ApiError(422, "validation", "One of the items is not one this list knows.",
                           "items")
        if key in stored:
            item = copy.deepcopy(stored[key])
        else:
            match = LIBRARY_KEY.match(key)
            if not match:
                raise ApiError(422, "validation",
                               "One of the items is not on this list and not in the library.",
                               "items")
            item = _library_item(helper, match.group(1), int(match.group(2)))
            if item is None:
                raise ApiError(422, "validation", "%s is not in this library any more, "
                               "or has nothing left to play." % (value.get("label") or key),
                               "items")
        if any(helper._list_item_same(item, it) for it in out):
            continue
        out.append(item)
    return out


# ---- searching the library -------------------------------------------------

def _search(helper, query):
    """
    <summary>
    GET /options/media: films, shows and episodes matching a search, to add to a list.
    </summary>
    <param name="helper">The service's FunctionalHelper, for its wording.</param>
    <param name="query">The parsed query; 'q' is the search.</param>
    <returns>{"items": [...], "more": bool} in the spec's options shape (7.3).</returns>
    <remarks>
    Films by title, shows by title (each offered whole, as one row, the way the
    Lists screen adds a show), then episodes of shows whose title matches. With no
    search there is no list at all: the library is too big to send whole.
    </remarks>
    """
    q = ((query.get("q") or [""])[0] or "").strip()
    if not q:
        return {"items": [], "more": True}
    limits = {"start": 0, "end": OPTIONS_MAX + 1}
    rows = []
    films = _jsonrpc("VideoLibrary.GetMovies", {
        "properties": ["title", "year", "runtime"], "limits": limits,
        "sort": {"method": "title", "ignorearticle": True},
        "filter": {"field": "title", "operator": "contains", "value": q}})
    for f in films.get("movies") or []:
        rows.append({"dbtype": "movie", "dbid": f.get("movieid"), "label": f.get("title"),
                     "year": f.get("year") or "", "duration": f.get("runtime") or 0})
    # No episode count on a show here: Kodi's counts Specials, which a whole
    # show row leaves out, so it would disagree with the row once added.
    shows = _jsonrpc("VideoLibrary.GetTVShows", {
        "properties": ["title", "year"], "limits": limits,
        "sort": {"method": "title", "ignorearticle": True},
        "filter": {"field": "title", "operator": "contains", "value": q}})
    for s in shows.get("tvshows") or []:
        rows.append({"dbtype": "tvshow", "dbid": s.get("tvshowid"), "label": s.get("title")})
    episodes = _jsonrpc("VideoLibrary.GetEpisodes", {
        "properties": ["title", "showtitle", "season", "episode", "runtime"],
        "limits": limits,
        "sort": {"method": "episode"},
        "filter": {"field": "tvshow", "operator": "contains", "value": q}})
    for e in episodes.get("episodes") or []:
        rows.append({"dbtype": "episode", "dbid": e.get("episodeid"), "label": e.get("title"),
                     "show": e.get("showtitle"), "season": _num_text(e.get("season")),
                     "episode": _num_text(e.get("episode")),
                     "duration": e.get("runtime") or 0})
    items = []
    for raw in rows:
        item = helper._list_item_clean(raw)
        if not item or not item["dbid"]:
            continue
        items.append({"value": _pick(helper, item), "label": _item_text(helper, item)})
    more = len(items) > OPTIONS_MAX
    return {"items": items[:OPTIONS_MAX], "more": more}


# ---- writes ------------------------------------------------------------------

def _save(helper):
    """
    <summary>
    Save the lists through the service and confirm it took.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <exception cref="ApiError">503 when the service refused the save.</exception>
    <remarks>
    _lists_save must be called without helper._lists_lock held. It puts the kept
    order back, writes the file with its previous copy beside it and redraws the
    Lists screen.
    </remarks>
    """
    helper._lists_save()
    _refuse_if_frozen(helper)


def _create(helper, body, if_match):
    """
    <summary>
    POST /lists: make a new list.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="body">The parsed JSON body: name, and optionally autoremove and items.</param>
    <param name="if_match">The If-Match header, or None.</param>
    <returns>201 with the stored list, and the new ETag.</returns>
    <remarks>
    Unlike New List on the TV, the new list does not become the one Add To List goes
    to: that choice belongs to whoever is holding the remote.
    </remarks>
    """
    if not isinstance(body, dict):
        raise ApiError(422, "validation", "A list must be a JSON object.")
    lists, etag = _snapshot(helper)
    _check_match(etag, if_match)
    _refuse_if_frozen(helper)
    name = _check_name(body, lists)
    autoremove = _check_autoremove(body, False)
    items = _check_items(helper, body, [])
    with _write_lock:
        with helper._lists_lock:
            _check_match(_current_etag(helper), if_match)
            if len(helper._lists) >= helper.LISTS_MAX:
                raise ApiError(422, "validation", "There is room for %d lists. Delete one "
                               "first." % helper.LISTS_MAX)
            if any(l["name"].lower() == name.lower() for l in helper._lists):
                raise ApiError(422, "validation", "There is already a list called %s." % name,
                               "name")
            seq = helper._lists_next_seq(helper._lists)
            helper._lists.append({"name": name, "items": items, "fill": 0,
                                  "autoremove": autoremove, "radarr": False, "seq": seq})
        _save(helper)
        lists, etag = _snapshot(helper)
    _log("list %d made over the API, %d item(s)" % (seq, len(items)))
    return 201, _list_record(helper, _find(lists, seq)), {"ETag": etag}


def _replace(helper, seq, body, if_match):
    """
    <summary>
    PUT /lists/{id}: change a list's name, Remove Watched switch and items.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="seq">The list's id from the path.</param>
    <param name="body">The parsed JSON body. A field it leaves out is kept.</param>
    <param name="if_match">The If-Match header, or None.</param>
    <returns>200 with the stored list, and the new ETag.</returns>
    <remarks>
    The list's Radarr tie, Port by Time length and creation number are kept. A
    rename carries the Add To List target with it, as Rename on the TV does.
    </remarks>
    """
    if not isinstance(body, dict):
        raise ApiError(422, "validation", "A list must be a JSON object.")
    lists, etag = _snapshot(helper)
    old = _find(lists, seq)
    _check_match(etag, if_match)
    _refuse_if_frozen(helper)
    name = _check_name(body, lists, old) if "name" in body else old["name"]
    autoremove = _check_autoremove(body, bool(old.get("autoremove")))
    items = _check_items(helper, body, old["items"]) if "items" in body else None
    with _write_lock:
        with helper._lists_lock:
            _check_match(_current_etag(helper), if_match)
            lst = _find(helper._lists, seq)
            if helper._lists_last == lst["name"]:
                helper._lists_last = name
            lst["name"] = name
            lst["autoremove"] = autoremove
            if items is not None:
                lst["items"] = items
        _save(helper)
        lists, etag = _snapshot(helper)
    _log("list %d changed over the API" % seq)
    return 200, _list_record(helper, _find(lists, seq)), {"ETag": etag}


def _delete(helper, seq, if_match):
    """
    <summary>
    DELETE /lists/{id}: remove a list and everything on it.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="seq">The list's id from the path.</param>
    <param name="if_match">The If-Match header, or None.</param>
    <returns>204 with no body, and the new ETag.</returns>
    <remarks>
    As Delete on the TV: the Add To List target is cleared when it was this list,
    and a Radarr tie goes with the list. The dashboard asks before it sends this.
    </remarks>
    """
    lists, etag = _snapshot(helper)
    _find(lists, seq)
    _check_match(etag, if_match)
    _refuse_if_frozen(helper)
    with _write_lock:
        with helper._lists_lock:
            _check_match(_current_etag(helper), if_match)
            lst = _find(helper._lists, seq)
            helper._lists.remove(lst)
            if helper._lists_last == lst["name"]:
                helper._lists_last = ""
            helper._lists_sel = min(helper._lists_sel, len(helper._lists))
        _save(helper)
        _lists, etag = _snapshot(helper)
    _log("list %d deleted over the API" % seq)
    return 204, None, {"ETag": etag}


def _backup(helper):
    """
    <summary>
    GET /backup: every list, as a document that is also a valid lists.json.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <returns>200 with the document, its ETag, and a download file name.</returns>
    <remarks>
    The document carries the "lists" array lists.json does, so Import Lists on any
    box reads it as well as a restore here does.
    </remarks>
    """
    lists, etag = _snapshot(helper)
    doc = {"type": BACKUP_TYPE, "format": 1, "version": 1, "lists": lists}
    name = "functional-lists-%s.json" % datetime.now().strftime("%Y%m%d-%H%M%S")
    return 200, doc, {"ETag": etag,
                      "Content-Disposition": 'attachment; filename="%s"' % name}


def _restore(helper, body, if_match):
    """
    <summary>
    POST /restore: replace every list with the ones in a backup.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="body">A document from GET /backup.</param>
    <param name="if_match">The ETag from a GET /backup made just before.</param>
    <returns>200 with how many lists were restored, and the new ETag.</returns>
    <remarks>
    Replaces, never merges: that is what Import Lists on the TV is for. The file as
    it stood is kept beside it as lists.json.previous by the save, so one restore can
    be undone by hand. The document is read by the service's own parser, so it is
    held to exactly the rules lists.json is. Library ids are not checked against this
    box, which would take one query per item: a backup is for the box it came from.
    The Radarr tie is never taken from a file; it stays on whichever restored list
    has the name of the list tied now. The kept order and the Add To List target
    belong to this box and are kept too, the target only while its list still exists.
    </remarks>
    """
    if not isinstance(body, dict) or body.get("type") != BACKUP_TYPE:
        raise ApiError(422, "validation", "That is not a backup of the Functional lists.")
    try:
        incoming, _last, _sort = helper._lists_parse(json.dumps(body))
    except ValueError as exc:
        raise ApiError(422, "validation", "That backup could not be read: %s." % exc)
    if len(incoming) > helper.LISTS_MAX:
        raise ApiError(422, "validation", "That backup holds more than %d lists."
                       % helper.LISTS_MAX)
    for lst in incoming:
        if len(lst["items"]) > helper.LIST_ITEMS_MAX:
            raise ApiError(422, "validation", "The list %s in that backup holds more than "
                           "%d items." % (lst["name"], helper.LIST_ITEMS_MAX))
    _lists, etag = _snapshot(helper)
    _check_match(etag, if_match)
    _refuse_if_frozen(helper)
    with _write_lock:
        with helper._lists_lock:
            _check_match(_current_etag(helper), if_match)
            tied = next((l["name"] for l in helper._lists if l.get("radarr")), None)
            for lst in incoming:
                lst["radarr"] = lst["name"] == tied
            helper._lists[:] = incoming
            if not any(l["name"] == helper._lists_last for l in incoming):
                helper._lists_last = ""
            helper._lists_sel = min(max(helper._lists_sel, 1), len(incoming))
        _save(helper)
        _lists, etag = _snapshot(helper)
    _log("restored %d list(s) over the API" % len(incoming))
    return 200, {"restored": len(incoming)}, {"ETag": etag}


# ---- routing ------------------------------------------------------------------

def info():
    """
    <summary>
    The body of GET /info.
    </summary>
    """
    return {
        "api": API_VERSION,
        "id": ADDON_ID,
        "name": "Functional",
        "version": _skin_version(),
        "resources": [
            {"name": "lists", "label": "Lists", "label_one": "List", "title_field": "name"},
        ],
        "backup": True,
        "restore": True,
    }


def schema():
    """
    <summary>
    The body of GET /schema.
    </summary>
    """
    return {"resources": {"lists": {"id_type": "integer", "fields": [
        {"key": "name", "label": "Name", "type": "string", "required": True, "max": NAME_MAX},
        {"key": "autoremove", "label": "Remove watched", "type": "boolean", "default": False,
         "help": "Takes a film or episode off this list once it has been watched."},
        {"key": "items", "label": "Items, in order", "type": "picks", "options_from": "media",
         "help": "Search for films, whole shows, or the episodes of a show."},
        {"key": "summary", "label": "Holds", "type": "readonly"},
        {"key": "radarr", "label": "Tied to Radarr", "type": "readonly",
         "help": "Chosen on the TV, in Skin Settings, Lists."},
    ]}}}


def handle(helper, method, path, query, body, if_match):
    """
    <summary>
    Route one request that has already passed the Host and token checks.
    </summary>
    <param name="helper">The service's FunctionalHelper.</param>
    <param name="method">'GET', 'POST', 'PUT' or 'DELETE'.</param>
    <param name="path">The URL path, without the query.</param>
    <param name="query">The parsed query, as parse_qs returns it.</param>
    <param name="body">The parsed JSON body, or None for GET and DELETE.</param>
    <param name="if_match">The If-Match header, or None.</param>
    <returns>(status, payload or None, extra headers).</returns>
    <exception cref="ApiError">For every error response.</exception>
    """
    if path == "/info":
        _allow(method, ["GET"])
        return 200, info(), {}
    if path == "/schema":
        _allow(method, ["GET"])
        return 200, schema(), {}
    if path == "/lists":
        _allow(method, ["GET", "POST"])
        if method == "POST":
            return _create(helper, body, if_match)
        lists, etag = _snapshot(helper)
        return 200, {"items": [_list_record(helper, l) for l in lists]}, {"ETag": etag}
    if path == "/lists/new":
        _allow(method, ["GET"])
        return 200, _blank_record(), {}
    match = _LIST_PATH.match(path)
    if match:
        _allow(method, ["GET", "PUT", "DELETE"])
        seq = int(match.group(1))
        if method == "PUT":
            return _replace(helper, seq, body, if_match)
        if method == "DELETE":
            return _delete(helper, seq, if_match)
        lists, etag = _snapshot(helper)
        return 200, _list_record(helper, _find(lists, seq)), {"ETag": etag}
    match = _OPTION_PATH.match(path)
    if match:
        _allow(method, ["GET"])
        if match.group(1) != "media":
            raise ApiError(404, "not_found", "There is no option source called %s."
                           % match.group(1))
        return 200, _search(helper, query), {}
    if path == "/backup":
        _allow(method, ["GET"])
        return _backup(helper)
    if path == "/restore":
        _allow(method, ["POST"])
        return _restore(helper, body, if_match)
    raise ApiError(404, "not_found", "Nothing is served at %s." % path)


# ---- HTTP ---------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """
    <summary>
    One request: the Host and token checks, the body, then handle().
    </summary>
    <remarks>
    Responses are HTTP/1.0, one request per connection, so a refused request never
    leaves an unread body in a kept alive connection.
    </remarks>
    """

    server_version = "FunctionalListsApi"
    sys_version = ""

    def log_message(self, fmt, *args):
        """
        <summary>
        Send the standard access line to kodi.log at debug level instead of stderr.
        </summary>
        <param name="fmt">The format string BaseHTTPRequestHandler passes.</param>
        <param name="args">Its arguments. The request line carries no token.</param>
        """
        _log(fmt % args, xbmc.LOGDEBUG)

    def do_GET(self):
        """<summary>Serve a GET.</summary>"""
        self._serve("GET")

    def do_POST(self):
        """<summary>Serve a POST.</summary>"""
        self._serve("POST")

    def do_PUT(self):
        """<summary>Serve a PUT.</summary>"""
        self._serve("PUT")

    def do_DELETE(self):
        """<summary>Serve a DELETE.</summary>"""
        self._serve("DELETE")

    def _serve(self, method):
        """
        <summary>
        Check the request, route it and send the response or the error.
        </summary>
        <param name="method">The request method.</param>
        <remarks>
        The Host check comes first, then the token, both before any body is read. An
        unexpected exception is logged in full to kodi.log and answered with a bare
        500, so no internals reach the dashboard.
        </remarks>
        """
        try:
            expected_host = "127.0.0.1:%d" % self.server.server_address[1]
            if (self.headers.get("Host") or "").strip() != expected_host:
                raise ApiError(400, "bad_request",
                               "This server only answers to %s." % expected_host)
            sent = (self.headers.get(TOKEN_HEADER) or "").encode("utf-8")
            if not hmac.compare_digest(sent, self.server.api_token.encode("utf-8")):
                raise ApiError(401, "unauthorised", "Missing or wrong token.")
            route = urlparse(self.path)
            body = self._read_body() if method in ("POST", "PUT") else None
            status, payload, headers = handle(self.server.helper, method, route.path,
                                              parse_qs(route.query), body,
                                              self.headers.get("If-Match"))
            self._send(status, payload, headers)
        except ApiError as err:
            error = {"code": err.code, "message": err.message}
            if err.field:
                error["field"] = err.field
            self._send(err.status, {"error": error}, err.headers)
        except Exception:  # noqa: BLE001
            _log("request failed:\n%s" % traceback.format_exc(), xbmc.LOGERROR)
            self._send(500, {"error": {"code": "internal",
                                       "message": "The Functional skin hit an error; "
                                                  "kodi.log has the detail."}}, {})

    def _read_body(self):
        """
        <summary>
        Read and parse the JSON body.
        </summary>
        <returns>The parsed value.</returns>
        <exception cref="ApiError">413 when Content-Length is over MAX_BODY, 400 when it
        is missing, not a number, or the body is not JSON.</exception>
        """
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            raise ApiError(400, "bad_request", "The request needs a Content-Length.")
        if length > MAX_BODY:
            raise ApiError(413, "too_large", "The request is larger than %d bytes." % MAX_BODY)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "bad_request", "The request body is not JSON.")

    def _send(self, status, payload, headers):
        """
        <summary>
        Write the status, headers and JSON body.
        </summary>
        <param name="status">The HTTP status.</param>
        <param name="payload">The value to send as JSON, or None for no body.</param>
        <param name="headers">Extra headers, such as ETag.</param>
        """
        data = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        if data:
            self.wfile.write(data)
