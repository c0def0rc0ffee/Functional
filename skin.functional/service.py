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
    Slideshow of library fanart on the Home background. Skin.String(bg_mode)
    picks the source - "recent" (recently watched movies), "random" (anything
    in the library), "genre" (one genre only, see below). Pulls up to 30 items
    via JSON-RPC, then rotates URL + caption on Home as window properties:
        home_bg_fanart        e.g. "image://https%3a%2f%2f...fanart.jpg"
        home_bg_label         e.g. "The Mysterious Dr. Fu Manchu (1929)"
    Cadence is read from Skin.String(bg_slideshow_interval), defaults to
    BG_INTERVAL seconds when unset. The list itself is re-fetched every
    BG_LIST_REFRESH seconds (or on VideoLibrary.OnUpdate).

update_bg_command()
    Watches Skin.String(bg_command). "pick_genre" opens a select dialog of the
    library's real genres (VideoLibrary.GetGenres, scoped by
    Skin.String(bg_genre_type) = movies / tvshows / both) and stores the answer
    in Skin.String(bg_genre) for the genre slideshow mode. Lives here because
    skin XML has no way to enumerate genres. "pick_time" opens a numeric time
    dialog for the currently-edited schedule slot's start time. Both run on a
    daemon thread so the blocking dialog doesn't stall the polling loop.

update_bg_schedule()
    Time-of-day background schedule. When Skin.String(bg_schedule_slots) is
    2-4, every background option also exists per slot (bg_slot{n}_mode etc.,
    each slot starting at bg_slot{n}_start "HH:MM"). The scheduler copies the
    clock-active slot's settings into the live bg_* strings, so the whole
    render path (Home.xml, variables, this service's slideshow) is untouched.
    While skin settings is open, the Background controls instead edit the
    slot picked by Skin.String(bg_edit_slot): live keys act as the edit
    buffer and are mirrored back into the slot's storage each tick.

update_playing_cast()
    Resolves the cast of the currently playing video (JSON-RPC Player.GetItem)
    and publishes it as Home window properties for the full-screen info card:
        Cast.Count
        Cast.<n>.Name / .Role / .Thumb   for n = 1..CAST_MAX
    The playing item has no cast list at all, only the flat, thumb-less
    VideoPlayer.Cast string. See also update_info_cast(), the same idea for
    the video info dialog's item (InfoCast.* properties).

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
    """Write a string into the active skin's persistent string store.

    The value is double-quoted because Kodi splits builtin arguments on
    commas: an unquoted value containing one (a genre like "Sci-Fi, Fantasy",
    a folder path with a comma in it) would be truncated at the first comma.
    Kodi strips the surrounding quotes. Embedded double quotes are dropped:
    Kodi's escape convention for them is murky and no genre/path/stat value
    legitimately contains one.
    """
    xbmc.executebuiltin('Skin.SetString({0},"{1}")'.format(
        key, str(value).replace('"', '')))


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
    Common formats: 'H:MM:SS', 'MM:SS', plain minutes ('123').

    Kodi formats durations >= 1 hour with three parts, so a 2-part value is
    always 'MM:SS' (sub-hour items), never 'H:MM'.
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
                m, s = parts
                return m * 60 + s
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

    CAST_MAX = 8  # portraits the full-screen info card has room for

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
        self._dialog_thread = None  # blocking pickers (genre/time), off the main loop
        # Scheduled-background state (see update_bg_schedule)
        self._sched_applied = 0      # slot currently copied into the live keys (0 = none)
        self._sched_edit_last = None  # bg_edit_slot value we last synced with
        self._sched_settings_open = False
        # Favourites (categorised, filterable) state
        self._fav_all = []          # [{name, thumb, action, cat}, ...]
        self._fav_current = []      # currently-filtered slice shown in the UI
        self._fav_mtime = -1.0      # favourites.xml mtime, to detect edits
        self._fav_loaded = False    # have we read favourites.xml at least once?
        self._fav_last_cat = None   # last category we populated properties for
        # Cast strip on the full-screen info card (see update_playing_cast)
        self._cast_key = None       # identity of the item we last published cast for
        self._cast_thread = None
        self._info_cast_key = None  # same, for the video info dialog
        self._info_cast_thread = None
        self._info_cast_names = []  # slot order, for cast_run clicks
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

        # Duration(secs) is unambiguous; the bare label formats sub-hour items
        # as MM:SS, which is indistinguishable from H:MM after the fact.
        duration_str = xbmc.getInfoLabel("ListItem.Duration(secs)")
        try:
            seconds = int(duration_str)
        except (ValueError, TypeError):
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

    def update_playing_cast(self):
        """Publish the playing item's cast as Home properties for the
        full-screen info card (the "i" screen during playback):
            Cast.Count
            Cast.<n>.Name / .Role / .Thumb   for n = 1..CAST_MAX

        There is no cast list for the *playing* item: VideoPlayer.Cast is a
        flat comma-joined string with no portraits. So resolve it ourselves.
        (The info dialog nominally has one, control 50, but we don't use it
        there either — see update_info_cast.)

        The lookup only runs when the playing item changes, and on a daemon
        thread, so a slow video DB can't stall the main loop.
        """
        if not xbmc.getCondVisibility("Player.HasVideo"):
            if self._cast_key is not None:
                self._cast_key = None
                self._publish_cast([])
            return

        if self._cast_thread is not None and self._cast_thread.is_alive():
            return

        # Path alone isn't enough: a stacked/playlist item can keep the same
        # path across parts, and PVR channels reuse one path for every show.
        key = "{0}|{1}".format(xbmc.getInfoLabel("Player.FilenameAndPath"),
                               xbmc.getInfoLabel("VideoPlayer.Title"))
        if key == self._cast_key:
            return
        self._cast_key = key
        self._cast_thread = threading.Thread(
            target=self._cast_worker, args=(key,),
            name="functional-cast", daemon=True)
        self._cast_thread.start()

    def _cast_worker(self, key):
        try:
            cast = self._fetch_playing_cast()
        except Exception:  # noqa: BLE001
            _dlog("cast worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            # Un-latch so the next tick retries; leaving the key set would
            # turn one transient JSON-RPC hiccup into "no cast until the
            # item changes".
            if key == self._cast_key:
                self._cast_key = None
            return
        # The item may have moved on while we were querying; don't stamp
        # stale actors over the new one's.
        if key != self._cast_key:
            return
        self._publish_cast(cast)

    @staticmethod
    def _fetch_playing_cast():
        """[{name, role, thumbnail}, ...] for the active video player."""
        players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
        pid = None
        for p in players:
            if p.get("type") == "video":
                pid = p.get("playerid")
                break
        if pid is None:
            return []
        resp = _jsonrpc("Player.GetItem",
                        {"playerid": pid, "properties": ["cast"]})
        item = ((resp or {}).get("result") or {}).get("item") or {}
        return item.get("cast") or []

    def _publish_cast(self, cast, prefix="Cast", reset=False):
        """Write <prefix>.Count and <prefix>.<n>.Name/.Role/.Thumb on Home.
        Two namespaces share this: "Cast" for the playing item (full-screen
        info card) and "InfoCast" for the video info dialog's item.

        reset=True clears Count instead of writing "0". The distinction
        matters to the skin: Count=="0" means "lookup finished, genuinely no
        cast" (show the no-cast label), empty means "no lookup yet / in
        flight" (show nothing). Gating the label on a Name property instead
        made it flash on every dialog open until the worker had published."""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        shown = cast[:self.CAST_MAX]
        if reset:
            win.clearProperty("%s.Count" % prefix)
        else:
            win.setProperty("%s.Count" % prefix, str(len(shown)))
        for i in range(self.CAST_MAX):
            n = i + 1
            if i < len(shown):
                member = shown[i] or {}
                win.setProperty("%s.%d.Name" % (prefix, n), member.get("name") or "")
                win.setProperty("%s.%d.Role" % (prefix, n), member.get("role") or "")
                win.setProperty("%s.%d.Thumb" % (prefix, n), member.get("thumbnail") or "")
            else:
                win.clearProperty("%s.%d.Name" % (prefix, n))
                win.clearProperty("%s.%d.Role" % (prefix, n))
                win.clearProperty("%s.%d.Thumb" % (prefix, n))
        _dlog("{0}: published {1} actor(s)".format(prefix, len(shown)))

    # Kodi window name for DialogVideoInfo (window id 12003).
    INFO_DIALOG = "movieinformation"

    def update_info_cast(self):
        """Publish the info dialog's item cast as InfoCast.* Home properties.

        DialogVideoInfo does have a built-in cast list (control 50) and binding
        a skin list to it is the documented route, but it stayed stubbornly
        empty here across two attempts. Rather than keep guessing at why, this
        reuses the mechanism that demonstrably works for the playback card:
        resolve the cast ourselves and hand the skin plain properties, which
        the dialog renders as fixed slots. No container in that window also
        means no ambiguity about what a bare ListItem.* resolves against.
        """
        if not xbmc.getCondVisibility("Window.IsActive({0})".format(self.INFO_DIALOG)):
            if self._info_cast_key is not None:
                self._info_cast_key = None
                self._publish_cast([], prefix="InfoCast", reset=True)
            return

        if self._info_cast_thread is not None and self._info_cast_thread.is_alive():
            return

        dbtype = xbmc.getInfoLabel("ListItem.DBType")
        dbid = xbmc.getInfoLabel("ListItem.DBID")
        key = "{0}|{1}|{2}".format(dbtype, dbid, xbmc.getInfoLabel("ListItem.Title"))
        if key == self._info_cast_key:
            return
        self._info_cast_key = key
        self._publish_cast([], prefix="InfoCast", reset=True)
        cast_and_role = xbmc.getInfoLabel("ListItem.CastAndRole")
        self._info_cast_thread = threading.Thread(
            target=self._info_cast_worker, args=(key, dbtype, dbid, cast_and_role),
            name="functional-info-cast", daemon=True)
        self._info_cast_thread.start()

    def _info_cast_worker(self, key, dbtype, dbid, cast_and_role):
        try:
            cast = self._fetch_library_cast(dbtype, dbid)
            # Non-library items (plugin:// listings, PVR recordings) have no
            # DBID to look up, but the dialog's info tag still carries names:
            # ListItem.CastAndRole is "Name as Role" lines. No portraits that
            # way (DefaultActor.png fills in), but names beat a false
            # "no cast information".
            if not cast:
                cast = self._parse_cast_and_role(cast_and_role)
        except Exception:  # noqa: BLE001
            _dlog("info-cast worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            # Un-latch so the next tick retries (see _cast_worker).
            if key == self._info_cast_key:
                self._info_cast_key = None
            return
        if key != self._info_cast_key:
            return
        _dlog("info-cast: {0} {1} -> {2} actor(s)".format(dbtype, dbid, len(cast)))
        self._info_cast_names = [(m or {}).get("name") or ""
                                 for m in cast[:self.CAST_MAX]]
        self._publish_cast(cast, prefix="InfoCast")

    @staticmethod
    def _parse_cast_and_role(text):
        """ListItem.CastAndRole -> [{name, role}]. One actor per line,
        "Name as Role" (localised Kodi builds use the same 'as')."""
        cast = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            name, _, role = line.partition(" as ")
            cast.append({"name": name.strip(), "role": role.strip()})
        return cast

    # dbtype -> (JSON-RPC method, id parameter name)
    CAST_LOOKUPS = {
        "movie": ("VideoLibrary.GetMovieDetails", "movieid"),
        "tvshow": ("VideoLibrary.GetTVShowDetails", "tvshowid"),
        "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid"),
        # No musicvideo entry: cast isn't a Video.Fields.MusicVideo member
        # (music videos carry "artist"), so asking for it is Invalid params.
        # The CastAndRole fallback covers whatever their info tag holds.
    }

    @classmethod
    def _fetch_library_cast(cls, dbtype, dbid):
        """[{name, role, thumbnail}, ...] for a library item, or []."""
        lookup = cls.CAST_LOOKUPS.get((dbtype or "").lower())
        if not lookup:
            return []
        try:
            numeric_id = int(dbid)
        except (TypeError, ValueError):
            return []
        method, id_param = lookup
        resp = _jsonrpc(method, {id_param: numeric_id, "properties": ["cast"]})
        result = (resp or {}).get("result") or {}
        # The details key is the dbtype ("moviedetails", "episodedetails", ...).
        for value in result.values():
            if isinstance(value, dict) and "cast" in value:
                return value.get("cast") or []
        return []

    def update_cast_command(self):
        """Handle a click on a cast portrait in the video info dialog.

        The skin can't launch this itself: the target is a smart-playlist URL
        whose JSON is full of commas and double quotes, and Kodi splits
        builtin arguments on commas. So the skin just writes the slot number
        to Skin.String(cast_run) (same pattern as fav_run) and the escaping
        happens here.
        """
        run = xbmc.getInfoLabel("Skin.String(cast_run)")
        if not run:
            return
        xbmc.executebuiltin("Skin.Reset(cast_run)")
        try:
            idx = int(run) - 1
        except ValueError:
            return
        if not (0 <= idx < len(self._info_cast_names)):
            return
        name = self._info_cast_names[idx]
        if not name:
            return

        rule = {"type": "movies",
                "rules": {"and": [{"field": "actor", "operator": "is",
                                   "value": [name]}]}}
        url = "videodb://movies/titles/?xsp=" + json.dumps(rule, separators=(",", ":"))
        # Quote the whole path and backslash-escape the JSON's own quotes;
        # that is what Kodi's argument splitter understands.
        command = 'ActivateWindow(Videos,"{0}",return)'.format(url.replace('"', '\\"'))
        _dlog("cast: opening movies with {0} -> {1}".format(name, command))
        xbmc.executebuiltin("Dialog.Close({0},true)".format(self.INFO_DIALOG))
        xbmc.executebuiltin(command)

    def update_home_bg(self):
        """
        Rotate Home's background through the configured slideshow source on a
        user-configurable timer. Source is Skin.String(bg_mode) - one of
        "recent" (recently watched movies), "random" (random library fanart),
        "genre" (random fanart from Skin.String(bg_genre), restricted to
        Skin.String(bg_genre_type)), "folder" (images from
        Skin.String(bg_slideshow_folder)). Empty/unset = off. Cadence:
        Skin.String(bg_slideshow_interval) in seconds, falling back to
        BG_INTERVAL when empty/unset.
        """
        # Unified selector: bg_mode is one of off(empty)/image/recent/
        # random/genre/folder. Only the slideshow modes drive this handler;
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

        # GENRE mode keys its source on the genre + media type as well as the
        # mode, so changing either forces a re-fetch through the same
        # source-changed path the other modes use.
        if mode == "genre":
            genre = xbmc.getInfoLabel("Skin.String(bg_genre)")
            if not genre:
                # Mode selected but no genre picked yet: show nothing rather
                # than silently falling back to the whole library.
                self._bg_idx = -1
                self._bg_source = ""
                _set_home_property("home_bg_fanart", "")
                _set_home_property("home_bg_label", "")
                return
            source = "genre:{0}:{1}".format(
                xbmc.getInfoLabel("Skin.String(bg_genre_type)") or "movies", genre)
        else:
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
            elif source.startswith("genre:"):
                _, gtype, gname = source.split(":", 2)
                self._bg_items = self._fetch_genre_library(gname, gtype)
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

    # ---- Background command handler -------------------------------------

    # bg_genre_type → the media types VideoLibrary.GetGenres understands
    _GENRE_QUERY_TYPES = {
        "movies": ("movie",),
        "tvshows": ("tvshow",),
        "both": ("movie", "tvshow"),
    }

    def update_bg_command(self):
        """Watch Skin.String(bg_command). Commands set by the Background
        section of skin settings that need Python: "pick_genre" (skins can't
        enumerate library genres) and "pick_time" (numeric time dialog for a
        schedule slot's start time)."""
        cmd = xbmc.getInfoLabel("Skin.String(bg_command)")
        if not cmd:
            return
        # Clear immediately so we don't re-trigger
        xbmc.executebuiltin("Skin.Reset(bg_command)")

        worker = {"pick_genre": self._pick_genre,
                  "pick_time": self._pick_time}.get(cmd)
        if worker is None:
            return
        # These dialogs block until dismissed, so they run off the polling
        # loop — otherwise the slideshow, stats and ETA handlers would all
        # stall for as long as the picker is open.
        if self._dialog_thread is not None and self._dialog_thread.is_alive():
            return
        self._dialog_thread = threading.Thread(
            target=self._dialog_worker, args=(worker,),
            name="functional-dialog", daemon=True)
        self._dialog_thread.start()

    @staticmethod
    def _dialog_worker(worker):
        try:
            worker()
        except Exception:  # noqa: BLE001
            _dlog("picker dialog failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    def _pick_genre(self):
        """Ask the library for its genres and let the user choose one."""
        gtype = xbmc.getInfoLabel("Skin.String(bg_genre_type)") or "movies"
        genres = []
        for kodi_type in self._GENRE_QUERY_TYPES.get(gtype, ("movie",)):
            resp = _jsonrpc("VideoLibrary.GetGenres", {"type": kodi_type})
            for row in (resp.get("result", {}) or {}).get("genres", []) if resp else []:
                label = (row.get("label", "") or "").strip()
                # "both" queries two types, which overlap heavily (Drama,
                # Comedy, …) — de-dupe so the list isn't full of pairs.
                if label and label not in genres:
                    genres.append(label)
        genres.sort(key=lambda s: s.lower())

        if not genres:
            _dlog("genre picker: no genres for type {0!r}".format(gtype))
            xbmcgui.Dialog().notification(
                "Functional", "No genres found in the library",
                xbmcgui.NOTIFICATION_INFO, 4000)
            return

        idx = xbmcgui.Dialog().select("Background genre", genres)
        if idx < 0:
            return  # cancelled, keep whatever was set before
        _set_skin_string("bg_genre", genres[idx])
        # Drop the cached list so the new genre shows on the next tick rather
        # than after the normal BG_LIST_REFRESH window.
        self._bg_last_fetch = 0.0
        _dlog("genre picker: bg_genre -> {0!r}".format(genres[idx]))

    # ---- Time-scheduled backgrounds --------------------------------------
    # Every background option exists once as a "live" skin string (what the
    # skin XML renders right now) and once per schedule slot as
    # bg_slot{n}_{key}. The scheduler copies slot -> live when the clock
    # enters a slot; the settings editor works the other way round (live ->
    # slot) so the existing Background controls edit whichever slot is
    # selected without any per-slot duplication in the XML.

    # per-slot key -> live skin-string name
    BG_SCHED_LIVE = {
        "mode": "bg_mode",
        "image": "home_background",
        "folder": "bg_slideshow_folder",
        "genre": "bg_genre",
        "genre_type": "bg_genre_type",
        "dim": "bg_dim",
        "interval": "bg_slideshow_interval",
        "label_position": "bg_label_position",
    }
    BG_SCHED_MAX_SLOTS = 4
    # Start times seeded when a slot first comes into existence.
    BG_SCHED_DEFAULT_STARTS = ("06:00", "18:00", "22:00", "00:00")

    @staticmethod
    def _get_skin(key):
        return xbmc.getInfoLabel("Skin.String({0})".format(key))

    @staticmethod
    def _set_or_reset(key, value):
        """Write *value* into a skin string, using Skin.Reset for empties so
        String.IsEmpty() conditions keep working. No-op when unchanged, so
        the mirror loop doesn't dirty Kodi's settings store every tick."""
        if value == xbmc.getInfoLabel("Skin.String({0})".format(key)):
            return
        if value:
            _set_skin_string(key, value)
        else:
            xbmc.executebuiltin("Skin.Reset({0})".format(key))

    @staticmethod
    def _parse_hhmm(text):
        """'HH:MM' -> minutes since midnight, or None if unparsable."""
        m = re.match(r"^\s*(\d{1,2}):(\d{1,2})\s*$", text or "")
        if not m:
            return None
        hours, minutes = int(m.group(1)), int(m.group(2))
        if hours > 23 or minutes > 59:
            return None
        return hours * 60 + minutes

    def _bg_slot_store(self, slot):
        """Copy the live background settings into slot *slot*'s storage."""
        for key, live in self.BG_SCHED_LIVE.items():
            self._set_or_reset("bg_slot{0}_{1}".format(slot, key),
                               self._get_skin(live))

    def _bg_slot_load(self, slot):
        """Copy slot *slot*'s stored settings into the live background keys."""
        for key, live in self.BG_SCHED_LIVE.items():
            self._set_or_reset(live,
                               self._get_skin("bg_slot{0}_{1}".format(slot, key)))

    def _bg_sched_slot_count(self):
        """Configured slot count (2..BG_SCHED_MAX_SLOTS), 0 = schedule off."""
        count = self._safe_int(self._get_skin("bg_schedule_slots"), 0)
        if count < 2:
            return 0
        return min(count, self.BG_SCHED_MAX_SLOTS)

    def _bg_sched_seed(self, count):
        """First time a slot exists, give it a default start time and a copy
        of the current live settings, so enabling the schedule (or raising
        the slot count) changes nothing visibly until the user edits."""
        for n in range(1, count + 1):
            if self._get_skin("bg_slot{0}_seeded".format(n)):
                continue
            _set_skin_string("bg_slot{0}_seeded".format(n), "1")
            if not self._get_skin("bg_slot{0}_start".format(n)):
                _set_skin_string("bg_slot{0}_start".format(n),
                                 self.BG_SCHED_DEFAULT_STARTS[n - 1])
            self._bg_slot_store(n)
            _dlog("bg schedule: seeded slot {0} from live settings".format(n))

    def _bg_active_slot(self, count):
        """The slot the clock says should be showing: latest start <= now,
        wrapping to the overall latest start when now is before all of them
        (i.e. that slot has been running since yesterday). Slots with no
        valid start time are ignored."""
        now = time.localtime()
        now_min = now.tm_hour * 60 + now.tm_min
        best = best_start = None       # latest start <= now
        latest = latest_start = None   # latest start overall (for wrap)
        for n in range(1, count + 1):
            start = self._parse_hhmm(self._get_skin("bg_slot{0}_start".format(n)))
            if start is None:
                continue
            if latest_start is None or start > latest_start:
                latest, latest_start = n, start
            if start <= now_min and (best_start is None or start > best_start):
                best, best_start = n, start
        return best if best is not None else latest

    def update_bg_schedule(self):
        """Time-of-day background schedule. Off (bg_schedule_slots empty/<2):
        nothing here runs and the live keys behave exactly as before. On:
        while skin settings is open the Background controls edit the slot in
        Skin.String(bg_edit_slot) (live keys double as an edit/preview
        buffer, mirrored into the slot's storage every tick); once settings
        closes, the slot whose start time the clock is inside is copied into
        the live keys, and again at every slot boundary."""
        count = self._bg_sched_slot_count()
        if not count:
            # Schedule off: forget state so re-enabling starts clean. Live
            # keys keep whatever they last held.
            self._sched_applied = 0
            self._sched_edit_last = None
            self._sched_settings_open = False
            return

        self._bg_sched_seed(count)

        if xbmc.getCondVisibility("Window.IsActive(skinsettings)"):
            if not self._sched_settings_open:
                # Settings just opened: edit the slot that's on screen so the
                # controls reflect what the user is looking at.
                self._sched_settings_open = True
                slot = self._sched_applied or self._bg_active_slot(count) or 1
                self._set_or_reset("bg_edit_slot", str(slot))
                self._sched_edit_last = slot
                self._bg_slot_store(slot)  # sync storage before mirroring
                return
            edit = self._safe_int(self._get_skin("bg_edit_slot"), 0)
            if not 1 <= edit <= count:
                edit = 1
                self._set_or_reset("bg_edit_slot", "1")
            if edit != self._sched_edit_last:
                # User switched slots: save the outgoing slot first (live
                # still holds its values, and the last mirror may be up to a
                # tick stale), then pull the new slot's settings up for
                # editing (which also previews it on Home behind the dialog).
                if self._sched_edit_last:
                    self._bg_slot_store(self._sched_edit_last)
                self._sched_edit_last = edit
                self._bg_slot_load(edit)
                _dlog("bg schedule: editing slot {0}".format(edit))
            else:
                # Mirror ongoing edits into the slot's storage.
                self._bg_slot_store(edit)
            return

        if self._sched_settings_open:
            # Settings closed. Capture any last-second edits the mirror
            # hasn't caught yet, then force a re-apply of whichever slot the
            # clock says (the live keys may hold a previewed slot).
            self._sched_settings_open = False
            if self._sched_edit_last:
                self._bg_slot_store(self._sched_edit_last)
            self._sched_applied = 0

        active = self._bg_active_slot(count)
        if not active or active == self._sched_applied:
            return
        self._bg_slot_load(active)
        self._sched_applied = active
        _dlog("bg schedule: slot {0} now active".format(active))

    def _pick_time(self):
        """Numeric time dialog for the currently-edited slot's start time."""
        slot = self._safe_int(self._get_skin("bg_edit_slot"), 1)
        slot = min(max(slot, 1), self.BG_SCHED_MAX_SLOTS)
        key = "bg_slot{0}_start".format(slot)
        current = self._get_skin(key) or "00:00"
        result = xbmcgui.Dialog().numeric(2, "Slot {0} start time".format(slot),
                                          current)
        minutes = self._parse_hhmm(result)
        if minutes is None:
            return  # cancelled or garbage: keep the previous start
        _set_skin_string(key, "{0:02d}:{1:02d}".format(minutes // 60,
                                                       minutes % 60))
        _dlog("bg schedule: slot {0} start -> {1:02d}:{2:02d}".format(
            slot, minutes // 60, minutes % 60))

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

    @staticmethod
    def _fanart_items(rows, with_year=True):
        """(fanart_url, label) pairs from JSON-RPC rows carrying art/title/year.
        Rows with no fanart are skipped — they'd render as a blank background."""
        items = []
        for row in rows:
            fanart = (row.get("art", {}) or {}).get("fanart", "")
            if not fanart:
                continue
            title = row.get("title", "") or ""
            year = row.get("year", 0) if with_year else 0
            items.append((fanart, "{0} ({1})".format(title, year) if year else title))
        return items

    def _fetch_genre_library(self, genre, gtype):
        """Up to BG_COUNT random fanart entries restricted to a single genre.

        gtype is movies / tvshows / both; anything else falls back to movies.
        """
        if gtype not in ("movies", "tvshows", "both"):
            gtype = "movies"
        params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "properties": ["art", "title", "year"],
            "filter": {"field": "genre", "operator": "is", "value": genre},
        }
        items = []
        if gtype in ("movies", "both"):
            resp = _jsonrpc("VideoLibrary.GetMovies", params)
            items += self._fanart_items(
                (resp.get("result", {}) or {}).get("movies", []) if resp else [])
        if gtype in ("tvshows", "both"):
            resp = _jsonrpc("VideoLibrary.GetTVShows", params)
            items += self._fanart_items(
                (resp.get("result", {}) or {}).get("tvshows", []) if resp else [],
                with_year=False)
        # Interleave movies and shows in "both" mode.
        random.shuffle(items)
        return items[:self.BG_COUNT]

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
            helper.update_bg_command()
            helper.update_favourites()
            helper.update_playing_cast()
            helper.update_info_cast()
            helper.update_cast_command()
            if tick == 0:
                helper.update_bg_schedule()
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
