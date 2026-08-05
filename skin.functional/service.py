"""
Functional skin, helper service.

Single long-running service that does jobs the skin XML can't do on its own:
arithmetic on infolabels, async DB queries, time formatting, etc.

Architecture rule (see PROJECT_NOTES.md): keep this as ONE service that handles
multiple concerns rather than spawning a new add-on per feature. New helpers go
in as methods on FunctionalHelper.

Current handlers
----------------
update_library_stats()
    Counts movies, TV shows, episodes (and watched / unwatched splits) via
    JSON-RPC and writes them to skin strings:
        stat_movies_total
        stat_movies_watched
        stat_movies_unwatched
        stat_tvshows_total
        stat_tvshows_unwatched
        stat_episodes_total
    Re-runs on VideoLibrary.OnUpdate, OnScanFinished, OnRemove.

update_focused_eta()
    Polls the currently focused video-library list item every ~1s while a video
    window is active. Reads its duration, adds it to "now", and writes the
    formatted finish time as a window property on Home (id 10000):
        focused_finish_time   e.g. "22:47"
    Skin reads it via $INFO[Window(home).Property(focused_finish_time)].
    Property is cleared when nothing useful is focused.

update_filter_command()
    Watches Skin.String(filter_command); when the side-menu filter buttons set
    it (e.g. "episodes_watched"), strips any existing `xsp=` query param from
    the current Container.FolderPath and appends a fresh one. Solves the
    "stacked xsp=" bug where Kodi's URL parser keeps the FIRST xsp= and
    silently ignores subsequent ones, so chained filter clicks did nothing.

update_layout_command()
    Watches Skin.String(layout_command); when the side-menu +/- buttons set it
    (e.g. "top_inc", "bottom_dec"), bumps the corresponding clearance Skin.String
    by ±10 px (clamped 0-LAYOUT_MAX_PX). Drag-to-adjust sliders aren't reliable
    for this because Kodi's skin-XML sliders don't expose state to Python on
    every build, explicit increment buttons go through Skin.String which IS
    universally readable.

update_home_bg()
    Slideshow of recently watched movie fanart on the Home background.
    When Skin.HasSetting(bg_slideshow), pulls up to 30 recently watched movies
    via JSON-RPC, then rotates URL + caption on Home as window properties:
        home_bg_fanart        e.g. "image://https%3a%2f%2f...fanart.jpg"
        home_bg_label         e.g. "The Mysterious Dr. Fu Manchu (1929)"
    Cadence is read from Skin.String(bg_slideshow_interval), defaults to
    BG_INTERVAL seconds when unset. The list itself is re-fetched every
    BG_LIST_REFRESH seconds (or on VideoLibrary.OnUpdate).

Future handlers
---------------
- update_queue_eta() , see PROJECT_NOTES "Queue ETA helper"
- update_focused_filesize() , see PROJECT_NOTES "Focused-item file size"
- anything else that needs Python; add a method here and trigger it from
  onNotification or the polling loop in run().
"""

import json
import os
import random
import re
import threading
import time
import traceback
import xml.etree.ElementTree as ET
import xbmc
import xbmcgui
import xbmcvfs

try:
    from urllib.parse import quote  # Python 3
except ImportError:  # pragma: no cover
    from urllib import quote


HOME_WINDOW_ID = 10000

# ---- Debug logging --------------------------------------------------------
# When Skin.HasSetting(debug_logging) is on, _dlog() appends timestamped
# lines to a file so behaviour can be inspected on machines we can't reach
# (e.g. the lounge box). The folder is Skin.String(debug_log_path) or, if
# unset, Kodi's temp dir. Everything also goes to the normal kodi.log.
DEFAULT_LOG_DIR = "special://temp/"
LOG_FILE_NAME = "skin.functional-debug.log"


def _log_path():
    folder = xbmc.getInfoLabel("Skin.String(debug_log_path)") or DEFAULT_LOG_DIR
    if not folder.endswith(("/", "\\")):
        folder += "/"
    return xbmcvfs.translatePath(folder + LOG_FILE_NAME)


def _dlog(msg, level=xbmc.LOGINFO):
    """Always write to kodi.log; also append to the debug file when enabled."""
    xbmc.log("[functional/helper] {0}".format(msg), level)
    try:
        if not xbmc.getCondVisibility("Skin.HasSetting(debug_logging)"):
            return
        with open(_log_path(), "a", encoding="utf-8") as fh:
            fh.write("{0}  {1}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception as exc:  # noqa: BLE001, logging must never raise
        xbmc.log("[functional/helper] debug-log write failed: {0}".format(exc),
                 xbmc.LOGWARNING)

SKIN_STRINGS = (
    "stat_movies_total",
    "stat_movies_watched",
    "stat_movies_unwatched",
    "stat_tvshows_total",
    "stat_tvshows_unwatched",
    "stat_episodes_total",
)


def _set_skin_string(key, value):
    """Write a string into the active skin's persistent string store."""
    xbmc.executebuiltin("Skin.SetString({0},{1})".format(key, value))


def _set_home_property(key, value):
    """Set a property on the Home window so $INFO[Window(home).Property()] sees it."""
    xbmcgui.Window(HOME_WINDOW_ID).setProperty(key, value)


def _basename_no_ext(path):
    """Filename without directory or extension, used for image captions."""
    if not path:
        return ""
    name = path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tbn")


def _derive_folder(path):
    """If *path* is an image file (the settings screen's image browser returns
    one), return its containing folder; otherwise the path itself. Always ends
    with a separator unless empty."""
    if not path:
        return ""
    p = path
    if p.lower().endswith(IMAGE_EXTS):
        cut = max(p.rfind("/"), p.rfind("\\"))
        if cut >= 0:
            p = p[:cut + 1]
    if p and not p.endswith(("/", "\\")):
        p += "/"
    return p


def _jsonrpc(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1, "params": params or {}}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception as exc:  # noqa: BLE001
        xbmc.log("[functional/helper] jsonrpc failed: {0}".format(exc), xbmc.LOGWARNING)
        return {}


def _count(method, extra_params=None):
    """Return the total row count for a VideoLibrary.GetXxx query, ignoring rows."""
    params = {"limits": {"start": 0, "end": 1}}
    if extra_params:
        params.update(extra_params)
    resp = _jsonrpc(method, params)
    # `or {}` at each level: a JSON-RPC error reply carries "result": null,
    # and .get() on None would raise.
    limits = ((resp or {}).get("result") or {}).get("limits") or {}
    try:
        return int(limits.get("total", 0))
    except (TypeError, ValueError):
        return 0


def _parse_duration_to_seconds(text):
    """
    Parse Kodi's ListItem.Duration string into total seconds.
    Common formats: 'H:MM:SS', 'H:MM', 'MM:SS', plain minutes ('123').

    For video-library items we always treat 2-part values as 'H:MM' (movies)
    rather than 'MM:SS' (which would only show up for very short clips).
    """
    if not text:
        return 0
    text = text.strip()
    try:
        if ":" in text:
            parts = [int(p) for p in text.split(":")]
            if len(parts) == 3:
                h, m, s = parts
                return h * 3600 + m * 60 + s
            if len(parts) == 2:
                # Heuristic: treat as H:MM unless first part is clearly minutes (>=60)
                a, b = parts
                if a >= 60:
                    return a * 60 + b
                return a * 3600 + b * 60
            return 0
        return int(text) * 60  # bare number = minutes
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------


class FunctionalHelper(xbmc.Monitor):
    LIB_EVENTS = (
        "VideoLibrary.OnUpdate",
        "VideoLibrary.OnScanFinished",
        "VideoLibrary.OnRemove",
        "VideoLibrary.OnCleanFinished",
    )

    POLL_SECS = 0.25  # tight loop so filter clicks land within a quarter-second
    STATS_REFRESH_SECS = 30  # re-run library stats every 30s as a safety net
    # (in case the initial SetString missed because the skin wasn't active yet)
    BG_INTERVAL = 20  # default seconds between background rotations (overridable via Skin.String(bg_slideshow_interval))
    BG_LIST_REFRESH = 600  # seconds before re-fetching the recent-watched list
    BG_EMPTY_RETRY = 15  # retry cadence when the last fetch returned nothing
    BG_COUNT = 30  # how many recent movies to cycle through

    # Live-tunable info-bar clearance via +/− buttons in MyVideoNav's side menu
    LAYOUT_MAX_PX = 250
    LAYOUT_DEFAULT_PX = 140
    LAYOUT_STEP_PX = 10

    FAV_MAX = 150  # how many favourites the custom favourites screen can show

    def __init__(self):
        super().__init__()
        _dlog("helper initialising")
        # Set ALL state up front and do NOTHING blocking here. Library
        # queries used to run in the constructor; on a box whose video DB
        # is slow/unreachable (shared MySQL with the server off, etc.)
        # executeJSONRPC blocks and the service freezes before it ever
        # reaches its loop, killing background, ETA and everything else.
        self._last_eta = None
        self._last_dur_dbg = None
        self._bg_items = []        # list of (fanart_url, label_string)
        self._bg_idx = -1
        self._bg_last_change = 0.0
        self._bg_last_fetch = 0.0
        self._bg_source = ""
        self._bg_folder = ""
        self._stats_last_refresh = 0.0   # 0 => loop refreshes on first tick
        self._stats_thread = None
        # Favourites (categorised, filterable) state
        self._fav_all = []          # [{name, thumb, action, cat}, ...]
        self._fav_current = []      # currently-filtered slice shown in the UI
        self._fav_mtime = -1.0      # favourites.xml mtime, to detect edits
        self._fav_loaded = False    # have we read favourites.xml at least once?
        self._fav_last_cat = None   # last category we populated properties for
        self._bootstrap_layout_defaults()
        self._migrate_bg_mode()
        _dlog("helper ready")

    def _migrate_bg_mode(self):
        """One-time migration to the unified bg_mode selector. Older setups
        had separate bg_slideshow_source + home_background which could clash;
        seed bg_mode from whichever was active so nothing changes for them."""
        if xbmc.getInfoLabel("Skin.String(bg_mode)"):
            return  # already on the new setting
        old_source = xbmc.getInfoLabel("Skin.String(bg_slideshow_source)")
        if old_source in ("recent", "random", "folder"):
            xbmc.executebuiltin("Skin.SetString(bg_mode,{0})".format(old_source))
            _dlog("migrated bg_mode <- slideshow source '{0}'".format(old_source))
        elif xbmc.getInfoLabel("Skin.String(home_background)"):
            xbmc.executebuiltin("Skin.SetString(bg_mode,image)")
            _dlog("migrated bg_mode <- static image")

    def _bootstrap_layout_defaults(self):
        """Seed clearance Skin.Strings to a sane default if empty.
        Without this, $INFO[Skin.String(infobar_clearance_top)] in <top>/<bottom>
        substitutes to the empty string and Kodi rejects the panel layout."""
        for key in ("infobar_clearance_top", "infobar_clearance_bottom"):
            if not xbmc.getInfoLabel("Skin.String({0})".format(key)):
                xbmc.executebuiltin("Skin.SetString({0},{1})".format(
                    key, self.LAYOUT_DEFAULT_PX))

    # -- Kodi event hooks ---------------------------------------------------

    def onNotification(self, sender, method, data):  # noqa: N802 (Kodi API)
        if method in self.LIB_EVENTS:
            # Don't query here (this runs on Kodi's notification thread and
            # could block it). Just flag a refresh for the loop to pick up.
            self._stats_last_refresh = 0.0
            self._bg_last_fetch = 0.0

    # -- Handlers -----------------------------------------------------------

    def maybe_refresh_stats(self):
        """
        Self-heal for the case where Skin.SetString didn't take on initial
        boot (e.g. service ran before skin finished activating). Called every
        loop tick, fast no-op when strings are populated and recent.

        The actual library queries run on a daemon thread so that a slow or
        unreachable video DB can never stall the main loop (which is what
        kept background/ETA dead on the lounge box).
        """
        # A refresh is already in flight, leave it be.
        if self._stats_thread is not None and self._stats_thread.is_alive():
            return

        now = time.time()
        need = (not xbmc.getInfoLabel("Skin.String(stat_movies_total)")
                or (now - self._stats_last_refresh) >= self.STATS_REFRESH_SECS)
        if not need:
            return

        self._stats_last_refresh = now
        self._stats_thread = threading.Thread(
            target=self._stats_worker, name="functional-stats", daemon=True)
        self._stats_thread.start()

    def _stats_worker(self):
        try:
            self.update_library_stats()
        except Exception:  # noqa: BLE001
            _dlog("stats worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    def update_library_stats(self):
        """Count movies / TV shows / episodes and store into skin strings."""
        _dlog("stats: querying library…")
        unwatched_filter = {
            "filter": {"field": "playcount", "operator": "is", "value": "0"}
        }

        movies_total = _count("VideoLibrary.GetMovies")
        movies_unwatched = _count("VideoLibrary.GetMovies", unwatched_filter)
        movies_watched = max(0, movies_total - movies_unwatched)

        tvshows_total = _count("VideoLibrary.GetTVShows")
        tvshows_unwatched = _count("VideoLibrary.GetTVShows", unwatched_filter)
        episodes_total = _count("VideoLibrary.GetEpisodes")

        _set_skin_string("stat_movies_total", str(movies_total))
        _set_skin_string("stat_movies_watched", str(movies_watched))
        _set_skin_string("stat_movies_unwatched", str(movies_unwatched))
        _set_skin_string("stat_tvshows_total", str(tvshows_total))
        _set_skin_string("stat_tvshows_unwatched", str(tvshows_unwatched))
        _set_skin_string("stat_episodes_total", str(episodes_total))

        _dlog(
            "stats: movies={0} ({1} unwatched) tvshows={2} ({3} unwatched) "
            "episodes={4}".format(
                movies_total, movies_unwatched,
                tvshows_total, tvshows_unwatched, episodes_total,
            )
        )

    def update_focused_eta(self):
        """
        If a video-library window is active and the focused item has a duration,
        compute the wall-clock finish time and stash it as a Home window property.
        Otherwise clear the property.
        """
        # Only meaningful when in a video window with a list (library or files)
        in_video_window = xbmc.getCondVisibility(
            "Window.IsActive(videos) | Window.IsActive(videolibrary)"
        )
        if not in_video_window:
            self._set_eta("")
            return

        duration_str = xbmc.getInfoLabel("ListItem.Duration")
        seconds = _parse_duration_to_seconds(duration_str)
        if seconds <= 0:
            # Log the raw duration once per distinct value so we can see why
            # an item yields no end time (empty? unexpected format?).
            if duration_str != getattr(self, "_last_dur_dbg", None):
                self._last_dur_dbg = duration_str
                _dlog("eta: no end time, ListItem.Duration={0!r} parsed={1}s".format(
                    duration_str, seconds))
            self._set_eta("")
            return

        finish_str = time.strftime("%H:%M", time.localtime(time.time() + seconds))
        self._set_eta(finish_str)

    def _set_eta(self, value):
        if value == self._last_eta:
            return
        self._last_eta = value
        _set_home_property("focused_finish_time", value)
        if value:
            _dlog("eta set: ends at {0}".format(value))

    def update_home_bg(self):
        """
        Rotate Home's background through the configured slideshow source on a
        user-configurable timer. Source is Skin.String(bg_slideshow_source) -
        one of "recent" (recently watched movies), "random" (random library
        fanart), "folder" (images from Skin.String(bg_slideshow_folder)).
        Empty/unset = off. Cadence: Skin.String(bg_slideshow_interval) in
        seconds, falling back to BG_INTERVAL when empty/unset.
        """
        # Unified selector: bg_mode is one of off(empty)/image/recent/
        # random/folder. Only the three slideshow modes drive this handler;
        # for image/off we clear the fanart property so the static image (or
        # nothing) shows with no conflict.
        mode = xbmc.getInfoLabel("Skin.String(bg_mode)")

        # FOLDER mode is rendered natively by a <multiimage> in Home.xml, far
        # more reliable for local/sandboxed paths than fetching the listing
        # ourselves. We only resolve the picked picture to its folder and
        # publish it as Skin.String(bg_slideshow_dir) for that control.
        if mode == "folder":
            folder = _derive_folder(xbmc.getInfoLabel("Skin.String(bg_slideshow_folder)"))
            if folder != xbmc.getInfoLabel("Skin.String(bg_slideshow_dir)"):
                _set_skin_string("bg_slideshow_dir", folder)
                _dlog("folder slideshow dir -> {0!r}".format(folder))
            # Make sure the service-driven slideshow image isn't also showing.
            if self._bg_source or xbmcgui.Window(HOME_WINDOW_ID).getProperty("home_bg_fanart"):
                self._bg_source = ""
                self._bg_idx = -1
                _set_home_property("home_bg_fanart", "")
                _set_home_property("home_bg_label", "")
            return

        source = mode if mode in ("recent", "random") else None

        if source is None:
            # image or off, never any slideshow fanart here. Always clear it
            # so a previous slideshow's backdrop can't linger.
            self._bg_idx = -1
            self._bg_source = ""
            _set_home_property("home_bg_fanart", "")
            # In image mode, surface the chosen file's name as the caption
            # (same as folder/library captions). Off = no caption.
            if mode == "image":
                _set_home_property("home_bg_label",
                                   _basename_no_ext(xbmc.getInfoLabel(
                                       "Skin.String(home_background)")))
            else:
                _set_home_property("home_bg_label", "")
            return

        now = time.time()

        # If the user switched source, force a re-fetch AND drop the current
        # backdrop immediately so the previous mode's image doesn't linger
        # while the new list is fetched (this was the "folder still shows
        # movies" bug).
        if getattr(self, "_bg_source", "") != source:
            self._bg_source = source
            self._bg_items = []
            self._bg_last_fetch = 0.0
            self._bg_idx = -1
            self._bg_last_change = 0.0
            _set_home_property("home_bg_fanart", "")
            _set_home_property("home_bg_label", "")

        # Refresh the items list periodically or when invalidated. An empty
        # result (server unreachable at boot, library mid-scan) retries on a
        # short backoff, NOT every tick, which hammered the source.
        refresh_after = self.BG_LIST_REFRESH if self._bg_items else self.BG_EMPTY_RETRY
        if (now - self._bg_last_fetch) > refresh_after:
            if source == "recent":
                self._bg_items = self._fetch_recent_movies()
            else:  # random
                self._bg_items = self._fetch_random_library()
            self._bg_last_fetch = now
            _dlog("bg slideshow ({0}): {1} items".format(source, len(self._bg_items)))
            # Force a change on the next tick
            self._bg_last_change = 0.0
            self._bg_idx = -1

        if not self._bg_items:
            # Nothing to show (e.g. folder empty or unreadable), clear so a
            # previous mode's backdrop doesn't stay on screen.
            _set_home_property("home_bg_fanart", "")
            _set_home_property("home_bg_label", "")
            return

        # Read the user's chosen interval each tick (so changes apply immediately)
        try:
            interval = int(xbmc.getInfoLabel("Skin.String(bg_slideshow_interval)"))
            if interval < 5:
                interval = self.BG_INTERVAL
        except (TypeError, ValueError):
            interval = self.BG_INTERVAL

        if (now - self._bg_last_change) >= interval:
            self._bg_idx = (self._bg_idx + 1) % len(self._bg_items)
            self._bg_last_change = now
            url, label = self._bg_items[self._bg_idx]
            _set_home_property("home_bg_fanart", url)
            _set_home_property("home_bg_label", label)
            _dlog("bg rotate -> {0} | {1}".format(label, url[:120]))

    # ---- Filter command handler ----------------------------------------

    # Map filter command keys → (item type, JSON XSP rules) or None for "all"
    _FILTER_RULES = {
        "movies_unwatched":   ("movies",   {"field": "playcount", "operator": "is",          "value": ["0"]}),
        "movies_watched":     ("movies",   {"field": "playcount", "operator": "greaterthan", "value": ["0"]}),
        "episodes_unwatched": ("episodes", {"field": "playcount", "operator": "is",          "value": ["0"]}),
        "episodes_watched":   ("episodes", {"field": "playcount", "operator": "greaterthan", "value": ["0"]}),
        "tvshows_unwatched":  ("tvshows",  {"field": "numwatched", "operator": "is",          "value": ["0"]}),
        "tvshows_watched":    ("tvshows",  {"field": "numwatched", "operator": "greaterthan", "value": ["0"]}),
        # From a show's SEASONS list we can't filter the seasons themselves
        # (no seasons xsp type exists), instead jump into the all-seasons
        # episode node filtered by watched state. Same rules as episodes_*.
        "seasons_unwatched":  ("episodes", {"field": "playcount", "operator": "is",          "value": ["0"]}),
        "seasons_watched":    ("episodes", {"field": "playcount", "operator": "greaterthan", "value": ["0"]}),
        # Local Only, exclude plugin/streaming paths (kept items only).
        "movies_local":       ("movies",   {"field": "path", "operator": "doesnotcontain", "value": ["plugin"]}),
        "episodes_local":     ("episodes", {"field": "path", "operator": "doesnotcontain", "value": ["plugin"]}),
        "tvshows_local":      ("tvshows",  {"field": "path", "operator": "doesnotcontain", "value": ["plugin"]}),
        # "<type>_all" / "local_off" => no rules, just strips the existing xsp
    }

    @staticmethod
    def _strip_xsp(url):
        """Remove any ?xsp=... or &xsp=... params, leaving the rest of the URL intact."""
        cleaned = re.sub(r"[?&]xsp=[^&]*", "", url)
        # If we just removed the only query param the URL might end with `?`; trim it.
        return cleaned.rstrip("?&")

    @classmethod
    def _build_xsp_url(cls, base_url, command):
        """Return (base, xsp_param_or_None). xsp_param is the encoded query suffix."""
        if command.endswith("_all") or command not in cls._FILTER_RULES:
            return base_url, None
        item_type, rule = cls._FILTER_RULES[command]
        xsp_dict = {"rules": {"and": [rule]}, "type": item_type}
        encoded = quote(json.dumps(xsp_dict, separators=(",", ":")))
        sep = "&" if "?" in base_url else "?"
        return base_url, sep + "xsp=" + encoded

    # ----- Favourites (categorised, filterable) ----------------------------
    # Ordered list of filter categories shown on the custom Favourites screen.
    FAV_CATS = ("all", "movies", "tvshows", "music", "apps", "other")

    @staticmethod
    def _fav_category(action):
        """Classify a favourite by its action string into one of FAV_CATS
        (never 'all', 'all' is the no-filter pseudo-category)."""
        a = (action or "").lower()
        if "videodb://movies" in a:
            return "movies"
        if "videodb://tvshows" in a or "/episode" in a or "episodeid" in a:
            return "tvshows"
        if "musicdb://" in a or "library://music" in a or "playercontrol(partymode(music" in a:
            return "music"
        # Program add-ons / scripts / launchers.
        if ("runaddon" in a or "runscript" in a
                or "plugin://plugin.program" in a
                or "activatewindow(programs" in a
                or "activatewindow(10001" in a):   # WINDOW_PROGRAMS
            return "apps"
        return "other"

    @staticmethod
    def _favourites_path():
        return xbmcvfs.translatePath("special://profile/favourites.xml")

    def _read_favourites(self):
        """Parse favourites.xml into self._fav_all. Returns True on (re)load."""
        path = self._favourites_path()
        try:
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
        except OSError:
            mtime = 0.0
        if self._fav_loaded and mtime == self._fav_mtime:
            return False  # unchanged since last read
        self._fav_loaded = True
        self._fav_mtime = mtime
        items = []
        if mtime:
            try:
                with xbmcvfs.File(path) as fh:
                    data = fh.read()
                root = ET.fromstring(data)
                for node in root.findall("favourite"):
                    action = (node.text or "").strip()
                    if not action:
                        continue
                    name = node.get("name") or ""
                    thumb = node.get("thumb") or ""
                    items.append({
                        "name": name,
                        "thumb": thumb,
                        "action": action,
                        "cat": self._fav_category(action),
                    })
            except Exception:
                _dlog("favourites parse failed:\n" + traceback.format_exc())
                items = []
        self._fav_all = items
        _dlog("favourites loaded: %d items" % len(items))
        return True

    def _fav_counts(self):
        counts = {c: 0 for c in self.FAV_CATS}
        counts["all"] = len(self._fav_all)
        for it in self._fav_all:
            counts[it["cat"]] = counts.get(it["cat"], 0) + 1
        return counts

    def _populate_favourites(self, category):
        """Write Fav.* window properties for the given category."""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        if category == "all" or category not in self.FAV_CATS:
            shown = list(self._fav_all)
        else:
            shown = [it for it in self._fav_all if it["cat"] == category]
        self._fav_current = shown
        win.setProperty("Fav.Count", str(len(shown)))
        win.setProperty("Fav.Category", category)
        counts = self._fav_counts()
        for c in self.FAV_CATS:
            win.setProperty("Fav.CatCount.%s" % c, str(counts.get(c, 0)))
        for i in range(self.FAV_MAX):
            n = i + 1
            if i < len(shown):
                it = shown[i]
                win.setProperty("Fav.%d.Label" % n, it["name"])
                win.setProperty("Fav.%d.Thumb" % n, it["thumb"])
                win.setProperty("Fav.%d.Cat" % n, it["cat"])
            else:
                win.clearProperty("Fav.%d.Label" % n)
                win.clearProperty("Fav.%d.Thumb" % n)
                win.clearProperty("Fav.%d.Cat" % n)
        self._fav_last_cat = category

    def update_favourites(self):
        """Keep the custom Favourites screen fed. Handles:
          - loading/reloading favourites.xml when it changes on disk
          - reacting to the selected category (Skin.String(fav_category))
          - running a favourite when Skin.String(fav_run) is set to its index
        Cheap enough to call every tick."""
        # Run a chosen favourite (set by the UI as a 1-based index into the
        # currently-shown, filtered list) then clear the request.
        run = xbmc.getInfoLabel("Skin.String(fav_run)")
        if run:
            xbmc.executebuiltin("Skin.Reset(fav_run)")
            try:
                idx = int(run) - 1
            except ValueError:
                idx = -1
            if 0 <= idx < len(self._fav_current):
                action = self._fav_current[idx]["action"]
                _dlog("favourite run #%d: %s" % (idx + 1, action))
                xbmc.executebuiltin(action)
            return

        reloaded = self._read_favourites()

        # Resolve the desired category: explicit selection, else configured
        # default, else 'all'.
        category = xbmc.getInfoLabel("Skin.String(fav_category)").strip().lower()
        if not category:
            category = xbmc.getInfoLabel("Skin.String(fav_default_category)").strip().lower()
        if category not in self.FAV_CATS:
            category = "all"

        if reloaded or category != self._fav_last_cat:
            self._populate_favourites(category)

    def update_sort_direction(self):
        """Apply a deferred sort-direction request from the library side menu.

        The menu buttons can't reliably force a direction inline: reading
        Container.SortDirection in the same click as SetSortMethod sees stale
        state, so a conditional toggle sometimes lands the wrong way (e.g.
        switching from Date Added back to Title left it Z->A). Instead the
        button sets Skin.String(sort_want)=asc|desc and we honour it here, a
        tick later, once the container's new sort has settled, so the
        direction read is accurate."""
        want = xbmc.getInfoLabel("Skin.String(sort_want)").strip().lower()
        if not want:
            return
        # Only meddle while the video library window is up, so we never nudge
        # some other window's container.
        if not xbmc.getCondVisibility("Window.IsVisible(myvideonav)"):
            xbmc.executebuiltin("Skin.Reset(sort_want)")
            return
        if want == "desc" and xbmc.getCondVisibility("Container.SortDirection(ascending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        elif want == "asc" and xbmc.getCondVisibility("Container.SortDirection(descending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        xbmc.executebuiltin("Skin.Reset(sort_want)")

    def update_filter_command(self):
        """Apply or clear an XSP filter on the current container, replacing any existing xsp."""
        cmd = xbmc.getInfoLabel("Skin.String(filter_command)")
        if not cmd:
            return
        # Clear immediately so we don't re-trigger
        xbmc.executebuiltin("Skin.Reset(filter_command)")

        current = xbmc.getInfoLabel("Container.FolderPath")
        if not current:
            return

        base = self._strip_xsp(current)

        # Show-root paths (videodb://tvshows/titles/<id>/) are SEASONS nodes
        # and silently ignore episode xsp filters, this hits both flattened
        # single-season shows (content=episodes) and real season lists
        # (content=seasons). The all-seasons node (<id>/-1/) lists every
        # episode of the show and applies the filter correctly.
        if cmd.startswith(("episodes_", "seasons_")) and not cmd.endswith("_all"):
            m = re.match(r"^(videodb://tvshows/titles/\d+)/?$", base)
            if m:
                base = m.group(1) + "/-1/"

        base, suffix = self._build_xsp_url(base, cmd)
        new_url = base + (suffix or "")

        # seasons_* navigates from the seasons list INTO the episode node -
        # push it onto history (no replace) so Back returns to the seasons.
        replace = "" if cmd.startswith("seasons_") else ",replace"

        _dlog("filter '{0}': {1} -> {2}".format(cmd, current, new_url))

        # When filter_debug is on, surface the resolved URL via Notification so
        # the user can verify the service is doing its job.
        if xbmc.getCondVisibility("Skin.HasSetting(filter_debug)"):
            # Notification builtin uses , as separator → escape any in our string
            preview = new_url.replace(",", " ")
            xbmc.executebuiltin(
                "Notification(filter applied,{0},5000)".format(preview)
            )

        xbmc.executebuiltin("Container.Update({0}{1})".format(new_url, replace))

    # ---- Layout command handler ----------------------------------------

    @staticmethod
    def _safe_int(text, default):
        try:
            return int(str(text).strip())
        except (TypeError, ValueError):
            return default

    _LAYOUT_COMMAND_KEY = {
        "top_inc":    ("infobar_clearance_top",    +1),
        "top_dec":    ("infobar_clearance_top",    -1),
        "bottom_inc": ("infobar_clearance_bottom", +1),
        "bottom_dec": ("infobar_clearance_bottom", -1),
    }

    def update_layout_command(self):
        """Apply ± LAYOUT_STEP_PX to whichever clearance string the +/- buttons
        flagged via Skin.String(layout_command). Clamped to 0..LAYOUT_MAX_PX."""
        cmd = xbmc.getInfoLabel("Skin.String(layout_command)")
        if not cmd:
            return
        # Clear immediately so we don't re-trigger
        xbmc.executebuiltin("Skin.Reset(layout_command)")

        if cmd not in self._LAYOUT_COMMAND_KEY:
            return
        key, sign = self._LAYOUT_COMMAND_KEY[cmd]

        current = self._safe_int(
            xbmc.getInfoLabel("Skin.String({0})".format(key)),
            self.LAYOUT_DEFAULT_PX,
        )
        new_val = current + sign * self.LAYOUT_STEP_PX
        new_val = max(0, min(self.LAYOUT_MAX_PX, new_val))

        if new_val != current:
            xbmc.executebuiltin("Skin.SetString({0},{1})".format(key, new_val))
            # Panel position picks up the change live via the
            # ClearanceAnimations include applied to the wrapping group -
            # one conditional slide animation per discrete value activates
            # as soon as String.IsEqual matches. No window reload needed.

    def _fetch_recent_movies(self):
        """Up to BG_COUNT recently watched movies; returns (fanart_url, 'Title (year)') tuples."""
        params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "descending", "method": "lastplayed"},
            "filter": {"field": "playcount", "operator": "greaterthan", "value": "0"},
            "properties": ["art", "title", "year"],
        }
        resp = _jsonrpc("VideoLibrary.GetMovies", params)
        movies = (resp.get("result", {}) or {}).get("movies", []) if resp else []
        items = []
        for m in movies:
            fanart = (m.get("art", {}) or {}).get("fanart", "")
            if not fanart:
                continue
            title = m.get("title", "") or ""
            year = m.get("year", 0)
            label = "{0} ({1})".format(title, year) if year else title
            items.append((fanart, label))
        return items

    def _fetch_random_library(self):
        """Up to BG_COUNT random fanart entries from the movie + TV-show library."""
        items = []
        movie_params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "properties": ["art", "title", "year"],
        }
        resp = _jsonrpc("VideoLibrary.GetMovies", movie_params)
        for m in (resp.get("result", {}) or {}).get("movies", []) if resp else []:
            fanart = (m.get("art", {}) or {}).get("fanart", "")
            if not fanart:
                continue
            title = m.get("title", "") or ""
            year = m.get("year", 0)
            label = "{0} ({1})".format(title, year) if year else title
            items.append((fanart, label))
        show_params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "properties": ["art", "title", "year"],
        }
        resp = _jsonrpc("VideoLibrary.GetTVShows", show_params)
        for s in (resp.get("result", {}) or {}).get("tvshows", []) if resp else []:
            fanart = (s.get("art", {}) or {}).get("fanart", "")
            if not fanart:
                continue
            label = s.get("title", "") or ""
            items.append((fanart, label))
        # Shuffle so movies and shows interleave.
        random.shuffle(items)
        return items[:self.BG_COUNT]

# ---------------------------------------------------------------------------


def run():
    version = xbmc.getInfoLabel("System.AddonVersion(skin.functional)")
    _dlog("==================================================")
    _dlog("service start, skin.functional {0}, Python {1}".format(
        version, ".".join(str(n) for n in __import__("sys").version_info[:3])))
    if xbmc.getCondVisibility("Skin.HasSetting(debug_logging)"):
        _dlog("debug log file: {0}".format(_log_path()))
    try:
        helper = FunctionalHelper()
    except Exception:  # noqa: BLE001
        # If construction throws, nothing works, make that loud.
        _dlog("FATAL: helper construction failed:\n{0}".format(
            traceback.format_exc()), xbmc.LOGERROR)
        return
    # Polling loop for things Kodi doesn't notify on (focused item changes etc.).
    # waitForAbort returns True if Kodi is shutting down.
    # Fast-tickers (filter command, focused ETA) run every loop.
    # Slow-tickers (home background slideshow) only every Nth loop.
    SLOW_EVERY = int(1.0 / FunctionalHelper.POLL_SECS) or 1  # ~once per second
    tick = 0
    while not helper.abortRequested():
        # One bad tick must never kill the service, without this guard a
        # single transient error (JSON-RPC hiccup during a library scan,
        # window churn at shutdown) silently stopped the slideshow and
        # every other handler until Kodi was restarted.
        try:
            helper.update_filter_command()
            helper.update_sort_direction()
            helper.update_focused_eta()
            helper.update_layout_command()
            helper.update_favourites()
            if tick == 0:
                helper.update_home_bg()
                helper.maybe_refresh_stats()
        except Exception:  # noqa: BLE001
            _dlog("tick failed (continuing):\n{0}".format(
                traceback.format_exc()), xbmc.LOGERROR)
        tick = (tick + 1) % SLOW_EVERY
        if helper.waitForAbort(FunctionalHelper.POLL_SECS):
            break
    _dlog("service shutting down")


if __name__ == "__main__":
    run()
