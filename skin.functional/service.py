"""
<summary>
Functional skin, helper service.
</summary>
<remarks>
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

update_focused_age()
    Same cadence and window gate as update_focused_eta(), for the focused
    item's age in whole years ("31 years old") while Skin.HasSetting(show_age)
    is on:
        focused_age_label
    Reuses _age_label / _year_of from the info screen ages. Only recomputed
    when the year sources change, and cleared outside the videos window.

update_layout_command()
    Watches Skin.String(layout_command); when the side-menu +/- buttons set it
    (e.g. "top_inc", "bottom_dec"), bumps the corresponding clearance Skin.String
    by ±10 px (clamped 0-LAYOUT_MAX_PX). Drag-to-adjust sliders aren't reliable
    for this because Kodi's skin-XML sliders don't expose state to Python on
    every build, explicit increment buttons go through Skin.String which IS
    universally readable.

update_home_bg()
    Slideshow of library fanart on the Home background. Skin.String(bg_mode)
    picks the source: "recent" (recently watched movies), "random" (anything
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

update_buffer_stats()
    While a video is playing, publishes what is actually sitting in the
    playback buffer as a Home window property the OSD renders next to the
    cache-level percentage:
        buffer_detail   e.g. "39 MB, ~52s ahead"
    MB is Player.CacheLevel x filecache.memorysize (the level is the fill %
    of that memory buffer); the runway is (cachepercentage - percentage) of
    the file duration via Player.GetProperties. Skin XML can't do arithmetic,
    hence Python. Runs on the slow (~1s) tick.

update_cache_command() -> "fullfile" / "normalbuffer" / _fullfile_worker()
    The OSD's BUFFER ALL button: per-movie unlimited buffering. Remembers
    the current memorysize in Skin.String(cache_mem_restore), switches Kodi
    to the uncapped disk cache (memorysize 0), restarts the stream at the
    same position, and restores the previous size when playback ends.
    Window(home).Property(buffer_fullfile) tells the OSD the mode is active.
    Clicking the button again sends "normalbuffer", which is the same switch
    in reverse: back to the remembered size (or Kodi's default if nothing was
    remembered) and another restart at the same position.

update_cache_command()
    Playback-buffer presets. Kodi 21 exposes the old advancedsettings <cache>
    block as real settings (filecache.buffermode / .memorysize / .readfactor)
    but hides them at the Advanced settings level; the skin's buffer buttons
    set Skin.String(cache_command) and this handler cycles the corresponding
    setting through sensible presets via JSON-RPC. Current values are
    mirrored into cache_mem_label / cache_rf_label / cache_mode_label skin
    strings for the button captions. Changes apply from the next playback
    start (the cache is built per stream), so no restart. NOTE: these are
    Kodi-wide settings, not skin settings; they persist across skins.

update_video_nav_state()
    Keeps the library side menu honest about what is actually on screen.
    Derives the genre filter from Container.FolderPath every tick and
    publishes it as Home property genre_active (the skin used to remember
    what had been CLICKED, which went stale the moment you navigated), and
    applies the user's per-content default sort
    (Skin.String(default_sort_movies) / (default_sort_tvshows), plus the
    matching _dir strings) whenever the container moves to a new node.

update_queue_eta()
    While a queue window is open, publishes when the WHOLE queue finishes as
    Home window properties:
        queue_finish_time   e.g. "23:42"
        queue_remaining     e.g. "3h 12m"
    Counts what is left of the item playing now plus the full length of
    everything after it.

update_settings_backup() / update_settings_command()
    Rolling backup of the skin's own settings.xml, refreshed whenever Kodi
    writes that file, plus the "backup" / "restore" commands behind the
    buttons in skin settings. Restore re-applies each setting through the
    Skin.SetString / SetBool builtins rather than swapping the file, because
    the running skin holds its settings in memory and would overwrite a
    swapped file on its next save.

update_lists()
    Named media lists (Skin.String(list_command) channel). Items come from
    the two static buttons at the top of the press-and-hold actions menu,
    the Lists screen (custom window 1151) and the queue windows' "Save as
    List". Stored in addon_data/skin.functional/lists.json; published as
    Lists.N.* / LI.N.* Home properties for the screen's static lists.
    "Porting" copies a list into the video and/or music queue, in order
    or shuffled, and starts it playing.

Future handlers
---------------
- update_focused_filesize() , see PROJECT_NOTES "Focused-item file size"
- anything else that needs Python; add a method here and trigger it from
  onNotification or the polling loop in run().
</remarks>
"""

import json
import os
import urllib.parse
import random
import re
import threading
import time
import traceback
import xml.etree.ElementTree as ET
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

HOME_WINDOW_ID = 10000

# ---- Localised strings ----------------------------------------------------
# Every string the user can see comes from the skin's strings.po, so the
# service can be translated along with the rest of the skin. Kodi's own
# strings stay with Kodi: xbmc.getLocalizedString() for those.
_ADDON = xbmcaddon.Addon()


def _L(string_id):
    """
    <summary>One of this add-on's own localised strings.</summary>
    <param name="string_id">Numeric id as it appears in strings.po.</param>
    <returns>The translated text, or the English source when untranslated.</returns>
    <remarks>
    Two lookups, because this add-on is the running skin. Kodi loads the
    active skin's strings into its main table, which is what $LOCALIZE in
    the XML reads and what xbmc.getLocalizedString() sees; the per-add-on
    lookup comes back empty for them. The add-on lookup is tried first so
    this keeps working unchanged if the service is ever split out into a
    script add-on of its own, where only that call resolves.

    Returning the id rather than "" on a miss matters: several of these
    strings are format templates, and "" % (1,) raises TypeError, which
    turns a missing translation into a broken feature.
    </remarks>
    """
    return (_ADDON.getLocalizedString(string_id)
            or xbmc.getLocalizedString(string_id)
            or str(string_id))

# ---- Debug logging --------------------------------------------------------
# When Skin.HasSetting(debug_logging) is on, _dlog() appends timestamped
# lines to a file so behaviour can be inspected on machines we can't reach
# (e.g. the lounge box). The folder is Skin.String(debug_log_path) or, if
# unset, Kodi's temp dir. Everything also goes to the normal kodi.log.
DEFAULT_LOG_DIR = "special://temp/"
LOG_FILE_NAME = "skin.functional-debug.log"


def _log_path():
    """
    <summary>
    Full local path of the debug log file.
    </summary>
    <returns>
    Skin.String(debug_log_path), or Kodi's temp folder when unset, joined
    with LOG_FILE_NAME and translated out of special:// form.
    </returns>
    """
    folder = xbmc.getInfoLabel("Skin.String(debug_log_path)") or DEFAULT_LOG_DIR
    if not folder.endswith(("/", "\\")):
        folder += "/"
    return xbmcvfs.translatePath(folder + LOG_FILE_NAME)


def _dlog(msg, level=xbmc.LOGINFO):
    """
    <summary>
    Always write to kodi.log; also append to the debug file when enabled.
    </summary>
    """
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

def _set_skin_string(key, value):
    """
    <summary>
    Write a string into the active skin's persistent string store.
    </summary>
    <remarks>
    The value is double-quoted because Kodi splits builtin arguments on
    commas: an unquoted value containing one (a genre like "Sci-Fi, Fantasy",
    a folder path with a comma in it) would be truncated at the first comma.
    Kodi strips the surrounding quotes. Embedded double quotes are dropped:
    Kodi's escape convention for them is murky and no genre/path/stat value
    legitimately contains one.
    </remarks>
    """
    xbmc.executebuiltin('Skin.SetString({0},"{1}")'.format(
        key, str(value).replace('"', '')))


def _set_home_property(key, value):
    """
    <summary>
    Set a property on the Home window so $INFO[Window(home).Property()] sees it.
    </summary>
    """
    xbmcgui.Window(HOME_WINDOW_ID).setProperty(key, value)


def _basename_no_ext(path):
    """
    <summary>
    Filename without directory or extension, used for image captions.
    </summary>
    """
    if not path:
        return ""
    name = path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tbn")


def _derive_folder(path):
    """
    <summary>
    If *path* is an image file (the settings screen's image browser returns
    one), return its containing folder; otherwise the path itself. Always ends
    with a separator unless empty.
    </summary>
    """
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
    """
    <summary>
    Call Kodi's JSON-RPC API and decode the reply.
    </summary>
    <param name="method">RPC method name.</param>
    <param name="params">Parameter dict; empty when omitted.</param>
    <returns>The decoded reply, or an empty dict after logging a warning when the call or the decode fails.</returns>
    """
    payload = {"jsonrpc": "2.0", "method": method, "id": 1, "params": params or {}}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except Exception as exc:  # noqa: BLE001
        xbmc.log("[functional/helper] jsonrpc failed: {0}".format(exc), xbmc.LOGWARNING)
        return {}


def _count(method, extra_params=None):
    """
    <summary>
    Return the total row count for a VideoLibrary.GetXxx query, ignoring rows.
    </summary>
    """
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
    <summary>
    Parse Kodi's ListItem.Duration string into total seconds.
    Common formats: 'H:MM:SS', 'MM:SS', plain minutes ('123').
    </summary>
    <remarks>
    Kodi formats durations >= 1 hour with three parts, so a 2-part value is
    always 'MM:SS' (sub-hour items), never 'H:MM'.
    </remarks>
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
    """
    <summary>
    The skin's background service: a Kodi Monitor that keeps the skin's
    window properties and skin strings fed.
    </summary>
    <remarks>
    Library events only flag a refresh. Every query runs off the
    notification thread, either on the polling loop in run() or on a daemon
    thread, so a slow or unreachable video database can never stall Kodi.
    </remarks>
    """
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

    # Continue Watching pop-up on Home (see update_continue_watching)
    CONTINUE_LISTS = ("9201", "9203")  # Home.xml container ids: movies, episodes

    CAST_MAX = 8  # portraits the full-screen info card has room for

    # ---- Video-nav state (genre label + default sort) ---------------------
    # A videodb genre node, e.g. "videodb://movies/genres/12/". The trailing
    # slash is optional because Container.FolderPath has been seen both ways.
    GENRE_PATH_RE = re.compile(
        r"^videodb://(movies|tvshows)/genres/(\d+)/?$", re.IGNORECASE)
    # Sort ids as used by Container.SetSortMethod, matching the Sort buttons
    # in MyVideoNav's side menu. Kodi ignores ids that aren't registered for
    # the current node, so an unusable choice is a harmless no-op.
    SORT_METHOD_IDS = {"title": 29, "year": 16, "rating": 17,
                       "dateadded": 40, "lastplayed": 41}
    # Direction each sort is most useful in when the user hasn't said.
    SORT_NATURAL_DIR = {"title": "asc", "year": "desc", "rating": "desc",
                        "dateadded": "desc", "lastplayed": "desc"}
    # Wait after a container path change before forcing the default sort.
    # Container.Content() is not settled the instant FolderPath changes, and
    # a sort applied against the previous content type is silently dropped.
    NAV_SORT_DELAY = 0.6

    QUEUE_MAX_ITEMS = 500  # cap on the queue we'll add up (guards silly playlists)

    # ---- Settings backup --------------------------------------------------
    SETTINGS_FILE = "special://profile/addon_data/skin.functional/settings.xml"
    BACKUP_DIR = "special://profile/addon_data/skin.functional/backups/"
    BACKUP_NAME = "settings-backup.xml"
    BACKUP_CHECK_SECS = 20  # how often the auto-snapshot looks at the mtime

    def __init__(self):
        """
        <summary>
        Set every piece of state up front and do nothing blocking.
        </summary>
        <remarks>
        Library queries used to run here. On a box whose video database is slow
        or unreachable, executeJSONRPC blocked and the service froze before it
        reached its loop. Everything is now lazy and picked up by the first tick.
        </remarks>
        """
        super().__init__()
        _dlog("helper initialising")
        # Set ALL state up front and do NOTHING blocking here. Library
        # queries used to run in the constructor; on a box whose video DB
        # is slow/unreachable (shared MySQL with the server off, etc.)
        # executeJSONRPC blocks and the service freezes before it ever
        # reaches its loop, killing background, ETA and everything else.
        self._last_eta = None
        self._last_dur_dbg = None
        # Age labels on the two info screens (see update_media_age), keyed by
        # Home property name so an unchanged label is never rewritten.
        self._age_last = {}
        # Year sources of the focused list item as last seen by
        # update_focused_age, so the label is only rebuilt on a real change.
        self._focused_age_key = None
        self._bg_items = []        # list of (fanart_url, label_string)
        self._bg_idx = -1
        self._bg_last_change = 0.0
        self._bg_last_fetch = 0.0
        self._bg_source = ""
        self._bg_folder = ""
        self._bg_thread = None     # library fetches, off the main loop
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
        # Continue Watching pop-up on Home (see update_continue_watching).
        # The lock and key play the same role as the cast strip's: a resume
        # lookup that finished after a newer row was focused must not publish.
        self._continue_lock = threading.Lock()
        self._continue_key = 0          # generation of the latest lookup
        self._continue_focus_key = None  # (dbtype, dbid) of the row described
        self._continue_focused = False   # continue_focus property is "1"
        self._continue_action_thread = None  # press and hold action worker
        # Age filter (see update_age_command)
        self._age_last_path = None       # Container.FolderPath last derived from
        # Cast strip on the full-screen info card (see update_playing_cast)
        # The lock makes "is this key still current?" + publish atomic, so a
        # worker that passed its staleness check can't interleave its slot
        # writes with the main loop blanking the strip.
        self._cast_lock = threading.Lock()
        self._cast_key = None       # identity of the item we last published cast for
        self._cast_thread = None
        self._cast_owed = False       # a lookup for _cast_key has not started yet
        self._info_cast_key = None  # same, for the video info dialog
        self._info_cast_thread = None
        self._info_cast_owed = False  # same, for the info dialog's item
        self._info_cast_names = []  # slot order, for cast_run clicks
        self._info_cast_dbtype = ""  # media type behind those slots, ditto
        # Playback-buffer labels: re-read once per skin-settings open
        self._cache_labels_fresh = False
        # OSD buffer readout (see update_buffer_stats)
        self._buffer_last = None      # last published buffer_detail string
        self._buffer_memsize = None   # filecache.memorysize, lazily re-read
        self._buffer_fullfile_last = None  # last published buffer_fullfile flag
        self._buffer_filesize = None  # (path, bytes) fetched off-loop, 0=unknown
        self._buffer_size_thread = None
        self._buffer_pct_last = None  # last published buffer_pct_label string
        # Per-movie "buffer entire file" switch (see _fullfile_worker)
        self._fullfile_thread = None
        self._fullfile_busy = False   # suppresses restore during the restart gap
        self._fullbuffer_ui_last = None  # last seen state of the OSD button setting
        # Video-nav state (see update_video_nav_state)
        self._nav_path = None        # last Container.FolderPath we acted on
        self._nav_genre = None       # last genre name published
        self._nav_sort_due = 0.0     # when to force the default sort (0 = idle)
        self._genre_names = {}       # (dbtype, genreid) -> genre label
        self._genre_fetched = set()  # dbtypes whose genre list we already pulled
        self._genre_thread = None
        self._random_thread = None   # random pick worker (see update_random_command)
        # Queue end time (see update_queue_eta)
        self._queue_last = None      # last (finish, remaining) pair published
        # Settings backup (see update_settings_backup)
        self._backup_last_check = 0.0
        self._backup_mtime = -1.0    # settings.xml mtime at the last snapshot
        self._backup_thread = None
        # Lists (see update_lists): lists.json is read on first use
        self._lists_lock = threading.Lock()
        self._lists = None           # [{name, items:[record]}], None = not loaded
        self._lists_last = ""        # name of the list an item last went into
        self._lists_sel = 1          # 1-based list the Lists screen has selected
        self._lists_frozen = False   # saving refused, see _lists_set_aside
        self._lists_sel_pub = None   # selection the right column currently shows
        self._lists_slots_used = 0   # Lists.N.* slots written last publish
        # Sleep timer (see update_sleep_timer). Deliberately not persisted:
        # a timer has nothing to say once the box it was going to switch off
        # has been switched off.
        self._sleep_deadline = None   # epoch seconds, None = not armed
        self._sleep_warned = False    # the one-minute toast has been shown
        self._sleep_published = ""    # countdown label currently on screen
        self._list_item_slots_used = 0  # LI.N.* slots written last publish
        self._bootstrap_layout_defaults()
        self._migrate_bg_mode()
        _dlog("helper ready")

    def _migrate_bg_mode(self):
        """
        <summary>
        One-time migration to the unified bg_mode selector. Older setups
        had separate bg_slideshow_source + home_background which could clash;
        seed bg_mode from whichever was active so nothing changes for them.
        </summary>
        """
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
        """
        <summary>
        Seed clearance Skin.Strings to a sane default if empty.
        Without this, $INFO[Skin.String(infobar_clearance_top)] in <top>/<bottom>
        substitutes to the empty string and Kodi rejects the panel layout.
        </summary>
        """
        for key in ("infobar_clearance_top", "infobar_clearance_bottom"):
            if not xbmc.getInfoLabel("Skin.String({0})".format(key)):
                xbmc.executebuiltin("Skin.SetString({0},{1})".format(
                    key, self.LAYOUT_DEFAULT_PX))

    # -- Kodi event hooks ---------------------------------------------------

    def onNotification(self, sender, method, data):  # noqa: N802 (Kodi API)
        """
        <summary>
        Kodi event hook: flag a refresh on library events, never query.
        </summary>
        <param name="sender">Event source, unused.</param>
        <param name="method">Event name, matched against LIB_EVENTS.</param>
        <param name="data">Event payload, unused.</param>
        <remarks>
        Runs on Kodi's notification thread, so it only resets the refresh
        timers and the genre cache and lets the loop do the work.
        </remarks>
        """
        if method in self.LIB_EVENTS:
            # Don't query here (this runs on Kodi's notification thread and
            # could block it). Just flag a refresh for the loop to pick up.
            self._stats_last_refresh = 0.0
            self._bg_last_fetch = 0.0
            # A scan can add or rename genres; let the next genre lookup
            # re-pull the list rather than label a node from a stale cache.
            self._genre_fetched = set()

    # -- Handlers -----------------------------------------------------------

    def maybe_refresh_stats(self):
        """
        <summary>
        Self-heal for the case where Skin.SetString didn't take on initial
        boot (e.g. service ran before skin finished activating). Called every
        loop tick, fast no-op when strings are populated and recent.
        </summary>
        <remarks>
        The actual library queries run on a daemon thread so that a slow or
        unreachable video DB can never stall the main loop (which is what
        kept background/ETA dead on the lounge box).
        </remarks>
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
        """
        <summary>
        Daemon thread body: refresh the library statistics, logging any failure instead of dying.
        </summary>
        """
        try:
            self.update_library_stats()
        except Exception:  # noqa: BLE001
            _dlog("stats worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    def update_library_stats(self):
        """
        <summary>
        Count movies / TV shows / episodes and store into skin strings.
        </summary>
        """
        _dlog("stats: querying library…")
        unwatched_filter = {
            "filter": {"field": "playcount", "operator": "is", "value": "0"}
        }

        movies_total = _count("VideoLibrary.GetMovies")
        movies_unwatched = _count("VideoLibrary.GetMovies", unwatched_filter)
        movies_watched = max(0, movies_total - movies_unwatched)

        tvshows_total = _count("VideoLibrary.GetTVShows")
        # tvshows have no per-show playcount filter semantics worth using:
        # numwatched=0 ("no episode watched") matches the side-menu filters.
        tvshows_unwatched = _count("VideoLibrary.GetTVShows", {
            "filter": {"field": "numwatched", "operator": "is", "value": "0"}
        })
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
        <summary>
        If a video-library window is active and the focused item has a duration,
        compute the wall-clock finish time and stash it as a Home window property.
        Otherwise clear the property.
        </summary>
        """
        # Only meaningful when in a video window with a list (library or files)
        in_video_window = xbmc.getCondVisibility(
            "Window.IsActive(videos)"
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
        """
        <summary>
        Publish the focused item's finish time as a Home property, skipping unchanged values.
        </summary>
        <param name="value">Clock string such as 23:42, or empty to clear.</param>
        """
        if value == self._last_eta:
            return
        self._last_eta = value
        _set_home_property("focused_finish_time", value)
        if value:
            _dlog("eta set: ends at {0}".format(value), xbmc.LOGDEBUG)

    # ---- Media age --------------------------------------------------------
    # "31 years old" alongside the release year on the two info screens.
    # Kodi's XML has no arithmetic, so the subtraction happens here and the
    # skin is handed a finished label it can drop straight into a row.

    # Kodi window name for DialogFullScreenInfo (window id 12006), the card
    # the info key raises during playback.
    FS_INFO_DIALOG = "fullscreeninfo"

    # A four-digit year standing on its own, so it also survives being dug
    # out of a formatted date. Premiered/FirstAired come back through the
    # user's regional date format ("02/03/2014" on en_GB, "3/2/2014" on
    # en_US), which is why only the year is taken from them and the age is
    # a plain year difference rather than exact-date arithmetic: month and
    # day cannot be told apart reliably across those formats.
    YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
    YEAR_MIN = 1870  # pre-cinema, so anything below it is junk, not a film
    YEAR_MAX = 2200

    def update_media_age(self):
        """
        <summary>
        Publish info_age_label and playing_age_label on Home: how old the
        video info dialog's item and the playing item are, in whole years.
        </summary>
        <remarks>
        Both are empty unless the screen that uses them is actually open, so
        a stale age can never surface on a later item, and empty throughout
        when Skin.HasSetting(hide_media_age) is on. Gating here rather than
        in the XML keeps it one switch: the skin's rows use the plain
        "prefix only when non-empty" $INFO form and need no extra condition.
        </remarks>
        """
        if xbmc.getCondVisibility("Skin.HasSetting(hide_media_age)"):
            self._set_age("info_age_label", "")
            self._set_age("playing_age_label", "")
            return

        if xbmc.getCondVisibility("Window.IsActive({0})".format(self.INFO_DIALOG)):
            # Year first: it is already a bare number. The dates are the
            # fallback for episodes, whose year Kodi fills from first aired
            # but which plugin listings sometimes leave unset.
            self._set_age("info_age_label", self._age_label(
                xbmc.getInfoLabel("ListItem.Year"),
                xbmc.getInfoLabel("ListItem.Premiered"),
                xbmc.getInfoLabel("ListItem.FirstAired")))
        else:
            self._set_age("info_age_label", "")

        if xbmc.getCondVisibility("Window.IsActive({0})".format(self.FS_INFO_DIALOG)):
            self._set_age("playing_age_label", self._age_label(
                xbmc.getInfoLabel("VideoPlayer.Year"),
                xbmc.getInfoLabel("VideoPlayer.Premiered")))
        else:
            self._set_age("playing_age_label", "")

    def _set_age(self, key, value):
        """
        <summary>Publish an age label, skipping unchanged values.</summary>
        <param name="key">Home property name.</param>
        <param name="value">Finished label, or empty to clear.</param>
        <remarks>
        This runs every tick while a card is open, and redundant
        Window(home) writes are implicated in the crashes behind
        _set_bg_props, so nothing is written unless it actually changed.
        </remarks>
        """
        if self._age_last.get(key) == value:
            return
        self._age_last[key] = value
        _set_home_property(key, value)
        if value:
            _dlog("age: {0} = {1}".format(key, value), xbmc.LOGDEBUG)

    @classmethod
    def _age_label(cls, *sources):
        """
        <summary>
        "31 years old" for the first source that carries a usable year.
        </summary>
        <param name="sources">Infolabel values to try, best first.</param>
        <returns>The label, or empty when the age is unknown or under a year.</returns>
        <remarks>
        Under a year is deliberately empty rather than "0 years old": a row
        that says nothing about this year's releases stays clean, and that
        is the whole point of the feature.
        </remarks>
        """
        year = cls._year_of(*sources)
        if year is None:
            return ""
        years = time.localtime().tm_year - year
        if years < 1:
            return ""
        if years == 1:
            return _L(31382)
        return _L(31381).format(years)

    @classmethod
    def _year_of(cls, *sources):
        """
        <summary>First plausible four-digit year across the given strings.</summary>
        <param name="sources">Infolabel values to try, best first.</param>
        <returns>The year as an int, or None when none of them held one.</returns>
        """
        for text in sources:
            for match in cls.YEAR_RE.finditer(text or ""):
                year = int(match.group(1))
                if cls.YEAR_MIN <= year <= cls.YEAR_MAX:
                    return year
        return None

    def update_focused_age(self):
        """
        <summary>
        Publish focused_age_label on Home: how old the focused list item is,
        in whole years, for the info bar of the video windows.
        </summary>
        <remarks>
        The third age after the two in update_media_age, and the one that
        runs on every focus change rather than while a card is open, so it
        is kept cheap: nothing is computed unless the item's year sources
        differ from the last tick, and the label is built from the same
        _age_label and _year_of helpers so the three ages can never
        disagree. The latch key also carries the current year, so a title
        that stays focused across midnight on New Year's Eve re-ages.

        Gated on Skin.HasSetting(show_age), the toggle in the info bar's
        visible fields, and on Window.IsActive(videos) like the finish time.
        It deliberately ignores hide_media_age: that switch belongs to the
        info screens, and a list field that silently obeyed it too would
        look broken from the visible fields page. Cleared, not left stale,
        whenever either gate closes.

        The year sources are the same three as the info dialog, in the same
        order, for the same reason: Year is a bare number, and the dates are
        only a fallback because they arrive in the user's regional format
        and only their four digit year can be trusted (see YEAR_RE).
        </remarks>
        """
        if (not xbmc.getCondVisibility("Skin.HasSetting(show_age)")
                or not xbmc.getCondVisibility("Window.IsActive(videos)")):
            self._focused_age_key = None
            self._set_age("focused_age_label", "")
            return

        sources = (
            xbmc.getInfoLabel("ListItem.Year"),
            xbmc.getInfoLabel("ListItem.Premiered"),
            xbmc.getInfoLabel("ListItem.FirstAired"),
        )
        key = sources + (time.localtime().tm_year,)
        if key == self._focused_age_key:
            return
        self._focused_age_key = key
        self._set_age("focused_age_label", self._age_label(*sources))

    # ---- Queue end time ---------------------------------------------------
    # The queue header could already show the total running time, which is a
    # duration, not an answer: "5h 40m" still needs the clock and some mental
    # arithmetic. These publish the answer itself, the wall-clock time the
    # LAST item in the queue finishes, counting only what is left of the item
    # playing now.

    QUEUE_IDS = {"video": 1, "music": 0}  # JSON-RPC playlist ids

    def update_queue_eta(self):
        """
        <summary>
        Publish Home properties queue_finish_time ("23:42") and
        queue_remaining ("3h 12m") for the queue window's header.
        </summary>
        <remarks>
        Only runs while a playlist window is up, so the Playlist.GetItems
        query costs nothing the rest of the time. Cleared on the way out so a
        stale end time can never outlive the screen that shows it.
        </remarks>
        """
        if xbmc.getCondVisibility("Window.IsActive(videoplaylist)"):
            kind = "video"
        elif xbmc.getCondVisibility("Window.IsActive(musicplaylist)"):
            kind = "music"
        else:
            if self._queue_last is not None:
                self._queue_last = None
                _set_home_property("queue_finish_time", "")
                _set_home_property("queue_remaining", "")
            return

        remaining = self._queue_remaining_secs(kind)
        if remaining <= 0:
            published = ("", "")
        else:
            published = (
                time.strftime("%H:%M", time.localtime(time.time() + remaining)),
                self._fmt_secs(remaining))
        if published != self._queue_last:
            self._queue_last = published
            _set_home_property("queue_finish_time", published[0])
            _set_home_property("queue_remaining", published[1])

    def _queue_remaining_secs(self, kind):
        """
        <summary>
        Seconds of playback left in the whole queue, 0 if that's unknowable.
        </summary>
        <param name="kind">"video" or "music", picking the playlist and the length field (video items carry runtime, music items duration).</param>
        <remarks>
        What's left of the item playing now plus the full length of every
        item after it. With nothing playing the queue hasn't started, so the
        whole list counts. Items with no known length (a stream, an unscraped
        file) contribute nothing rather than blocking the total: an end time
        that is slightly early beats no end time at all.
        </remarks>
        """
        playlist_id = self.QUEUE_IDS[kind]
        field = "runtime" if kind == "video" else "duration"
        resp = _jsonrpc("Playlist.GetItems", {
            "playlistid": playlist_id,
            "properties": [field],
            "limits": {"start": 0, "end": self.QUEUE_MAX_ITEMS}})
        items = ((resp or {}).get("result") or {}).get("items") or []
        if not items:
            return 0

        # Where we are, and how much of the current item is left.
        position, current_left = -1, 0
        players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
        pid = next((p.get("playerid") for p in players
                    if p.get("type") == kind), None)
        if pid is not None:
            props = ((_jsonrpc("Player.GetProperties", {
                "playerid": pid,
                "properties": ["position", "time", "totaltime"]})
                .get("result")) or {})
            # position is 0-based here; -1 means the player isn't running the
            # playlist (a one-off play), in which case treat the queue as
            # not yet started.
            position = props.get("position", -1)
            if position is None:
                position = -1
            current_left = max(0, self._hms(props.get("totaltime"))
                               - self._hms(props.get("time")))

        total = current_left if position >= 0 else 0
        for item in items[position + 1:]:
            try:
                total += max(0, int(item.get(field) or 0))
            except (TypeError, ValueError):
                continue
        return total

    @staticmethod
    def _hms(block):
        """
        <summary>
        Seconds from a JSON-RPC {hours, minutes, seconds} time block.
        </summary>
        """
        block = block or {}
        return (int(block.get("hours") or 0) * 3600
                + int(block.get("minutes") or 0) * 60
                + int(block.get("seconds") or 0))

    def update_playing_cast(self):
        """
        <summary>
        Publish the playing item's cast as Home properties for the
        full-screen info card (the "i" screen during playback):
            Cast.Count
            Cast.<n>.Name / .Role / .Thumb   for n = 1..CAST_MAX
        </summary>
        <remarks>
        There is no cast list for the *playing* item: VideoPlayer.Cast is a
        flat comma-joined string with no portraits. So resolve it ourselves.
        (The info dialog nominally has one, control 50, but we don't use it
        there either, see update_info_cast.)

        The lookup only runs when the playing item changes, and on a daemon
        thread, so a slow video DB can't stall the main loop.
        </remarks>
        """
        if not xbmc.getCondVisibility("Player.HasVideo"):
            if self._cast_key is not None:
                with self._cast_lock:
                    self._cast_key = None
                    self._cast_owed = False
                    self._publish_cast([])
            return

        # Path alone isn't enough: a stacked/playlist item can keep the same
        # path across parts, and PVR channels reuse one path for every show.
        key = "{0}|{1}".format(xbmc.getInfoLabel("Player.FilenameAndPath"),
                               xbmc.getInfoLabel("VideoPlayer.Title"))
        if key != self._cast_key:
            with self._cast_lock:
                self._cast_key = key
                # Blank the strip immediately so the previous item's actors
                # don't linger on the info card while the new lookup runs.
                self._publish_cast([])
            self._cast_owed = True
        if not self._cast_owed:
            return
        # The key is advanced BEFORE this check, not after it. A worker still
        # blocked on the previous item then fails its own staleness check
        # and drops its late result instead of painting the old actors over
        # the new title; the lookup this item is owed starts on the first
        # tick after that worker has finished.
        if self._cast_thread is not None and self._cast_thread.is_alive():
            return
        self._cast_owed = False
        self._cast_thread = threading.Thread(
            target=self._cast_worker, args=(key,),
            name="functional-cast", daemon=True)
        self._cast_thread.start()

    def _cast_worker(self, key):
        """
        <summary>
        Daemon thread body: fetch the playing item's cast and publish it if the item is still current.
        </summary>
        <param name="key">Identity of the item this fetch was started for.</param>
        <remarks>
        On failure the key is cleared under the lock so the next tick retries
        rather than leaving the strip blank until the item changes. A key that
        no longer matches means the item moved on, so nothing is published.
        </remarks>
        """
        try:
            cast = self._fetch_playing_cast()
        except Exception:  # noqa: BLE001
            _dlog("cast worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            # Un-latch so the next tick retries; leaving the key set would
            # turn one transient JSON-RPC hiccup into "no cast until the
            # item changes". Under the lock like every other key write.
            with self._cast_lock:
                if key == self._cast_key:
                    self._cast_key = None
            return
        # The item may have moved on while we were querying; don't stamp
        # stale actors over the new one's.
        with self._cast_lock:
            if key != self._cast_key:
                return
            self._publish_cast(cast)

    @staticmethod
    def _fetch_playing_cast():
        """
        <summary>
        [{name, role, thumbnail}, ...] for the active video player.
        </summary>
        """
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
        """
        <summary>
        Write <prefix>.Count and <prefix>.<n>.Name/.Role/.Thumb on Home.
        Two namespaces share this: "Cast" for the playing item (full-screen
        info card) and "InfoCast" for the video info dialog's item.
        </summary>
        <remarks>
        reset=True clears Count instead of writing "0". The distinction
        matters to the skin: Count=="0" means "lookup finished, genuinely no
        cast" (show the no-cast label), empty means "no lookup yet / in
        flight" (show nothing). Gating the label on a Name property instead
        made it flash on every dialog open until the worker had published.

        Callers must hold self._cast_lock: the ~25 property writes here are
        not atomic, so unsynchronised worker/main-loop publishes interleave.
        </remarks>
        """
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
        """
        <summary>
        Publish the info dialog's item cast as InfoCast.* Home properties.
        </summary>
        <remarks>
        DialogVideoInfo does have a built-in cast list (control 50) and binding
        a skin list to it is the documented route, but it stayed stubbornly
        empty here across two attempts. Rather than keep guessing at why, this
        reuses the mechanism that demonstrably works for the playback card:
        resolve the cast ourselves and hand the skin plain properties, which
        the dialog renders as fixed slots. No container in that window also
        means no ambiguity about what a bare ListItem.* resolves against.
        </remarks>
        """
        if not xbmc.getCondVisibility("Window.IsActive({0})".format(self.INFO_DIALOG)):
            if self._info_cast_key is not None:
                with self._cast_lock:
                    self._info_cast_key = None
                    self._info_cast_owed = False
                    self._info_cast_names = []
                    self._info_cast_dbtype = ""
                    self._publish_cast([], prefix="InfoCast", reset=True)
            return

        dbtype = xbmc.getInfoLabel("ListItem.DBType")
        dbid = xbmc.getInfoLabel("ListItem.DBID")
        key = "{0}|{1}|{2}".format(dbtype, dbid, xbmc.getInfoLabel("ListItem.Title"))
        if key != self._info_cast_key:
            with self._cast_lock:
                self._info_cast_key = key
                self._publish_cast([], prefix="InfoCast", reset=True)
            self._info_cast_owed = True
        if not self._info_cast_owed:
            return
        # Key first, busy check second, for the reason given in
        # update_playing_cast: a late worker must lose its staleness check.
        if self._info_cast_thread is not None and self._info_cast_thread.is_alive():
            return
        self._info_cast_owed = False
        cast_and_role = xbmc.getInfoLabel("ListItem.CastAndRole")
        self._info_cast_thread = threading.Thread(
            target=self._info_cast_worker, args=(key, dbtype, dbid, cast_and_role),
            name="functional-info-cast", daemon=True)
        self._info_cast_thread.start()

    def _info_cast_worker(self, key, dbtype, dbid, cast_and_role):
        """
        <summary>
        Daemon thread body: fetch the info dialog's cast and publish it as
        InfoCast properties if the dialog's item is still current.
        </summary>
        <param name="key">Identity of the item this fetch was started for.</param>
        <param name="dbtype">Media type behind the dialog, such as movie.</param>
        <param name="dbid">Library id, or nothing for a non-library item.</param>
        <param name="cast_and_role">ListItem.CastAndRole text, the fallback when the library returns no cast.</param>
        <remarks>
        Also records the slot order and media type so a click on a portrait can
        be resolved. Failure clears the key under the lock so the next tick retries.
        </remarks>
        """
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
            with self._cast_lock:
                if key == self._info_cast_key:
                    self._info_cast_key = None
            return
        with self._cast_lock:
            if key != self._info_cast_key:
                return
            _dlog("info-cast: {0} {1} -> {2} actor(s)".format(dbtype, dbid, len(cast)))
            self._info_cast_names = [(m or {}).get("name") or ""
                                     for m in cast[:self.CAST_MAX]]
            self._info_cast_dbtype = (dbtype or "").lower()
            self._publish_cast(cast, prefix="InfoCast")

    @staticmethod
    def _parse_cast_and_role(text):
        """
        <summary>
        ListItem.CastAndRole -> [{name, role}]. One actor per line,
        "Name as Role", where 'as' is Kodi's localised string 20347 ("als",
        "como", ... on non-English UIs), so split on that, not a literal.
        </summary>
        """
        separator = " {0} ".format(xbmc.getLocalizedString(20347) or "as")
        cast = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            name, _, role = line.partition(separator)
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
        """
        <summary>
        [{name, role, thumbnail}, ...] for a library item, or [].
        </summary>
        """
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
        """
        <summary>
        Handle a click on a cast portrait in the video info dialog.
        </summary>
        <remarks>
        The skin can't launch this itself: the target is a smart-playlist URL
        whose JSON is full of commas and double quotes, and Kodi splits
        builtin arguments on commas. So the skin just writes the slot number
        to Skin.String(cast_run) (same pattern as fav_run) and the escaping
        happens here.
        </remarks>
        """
        run = self._take_command("cast_run")
        if not run:
            return
        try:
            idx = int(run) - 1
        except ValueError:
            return
        if not (0 <= idx < len(self._info_cast_names)):
            return
        name = self._info_cast_names[idx]
        if not name:
            return

        # Match the list to where the click came from: an actor opened from a
        # TV show or episode gets their shows, anything else their movies.
        if self._info_cast_dbtype in ("tvshow", "season", "episode"):
            rule_type, base = "tvshows", "videodb://tvshows/titles/"
        else:
            rule_type, base = "movies", "videodb://movies/titles/"
        rule = {"type": rule_type,
                "rules": {"and": [{"field": "actor", "operator": "is",
                                   "value": [name]}]}}
        url = base + "?xsp=" + json.dumps(rule, separators=(",", ":"))
        # Quote the whole path and backslash-escape the JSON's own quotes;
        # that is what Kodi's argument splitter understands.
        command = 'ActivateWindow(Videos,"{0}",return)'.format(url.replace('"', '\\"'))
        _dlog("cast: opening {0} with {1} -> {2}".format(rule_type, name, command))
        xbmc.executebuiltin("Dialog.Close({0},true)".format(self.INFO_DIALOG))
        xbmc.executebuiltin(command)

    # ---- Playback buffer (Kodi filecache.* settings) ----------------------
    # Preset values below were read back from a live Kodi 21.3 via
    # Settings.GetSettings: they must be members of Kodi's own options lists
    # (memorysize in MB, readfactor x100 with 0 = adaptive) or SetSettingValue
    # rejects them.

    # 0 = Kodi's "cache entire file on disk storage": no size cap, so pausing
    # can buffer a whole 80 GB remux over a slow link. Needs the file's size
    # free on disk and hammers SSDs, hence last in the cycle, opt-in.
    CACHE_MEM_PRESETS = (20, 64, 128, 256, 512, 1024, 0)   # MB
    CACHE_RF_PRESETS = (0, 200, 400, 1000, 2000, 5000)  # x100, 0 = adaptive
    CACHE_MODE_PRESETS = (4, 2, 0, 1, 3)
    CACHE_DEFAULTS = {"filecache.buffermode": 4,
                      "filecache.memorysize": 20,
                      "filecache.readfactor": 400}
    # filecache.buffermode value to its strings.po id; resolved at use, not
    # here, because strings are only readable once the skin is loaded.
    CACHE_MODE_LABELS = {4: 31445, 2: 31446, 0: 31447, 1: 31448, 3: 31449}

    @staticmethod
    def _get_setting(setting_id):
        """
        <summary>
        Read one Kodi setting by id over JSON-RPC.
        </summary>
        <param name="setting_id">Kodi setting id, such as filecache.memorysize.</param>
        <returns>The setting's value, or None on any error.</returns>
        """
        resp = _jsonrpc("Settings.GetSettingValue", {"setting": setting_id})
        return ((resp or {}).get("result") or {}).get("value")

    @staticmethod
    def _set_setting(setting_id, value):
        """
        <summary>
        Write one Kodi setting by id over JSON-RPC.
        </summary>
        <param name="setting_id">Kodi setting id.</param>
        <param name="value">New value, in the type the setting expects.</param>
        """
        _jsonrpc("Settings.SetSettingValue",
                 {"setting": setting_id, "value": value})

    @staticmethod
    def _cache_mem_label(value):
        """
        <summary>
        Human readable label for a filecache.memorysize value.
        </summary>
        <param name="value">Megabytes; 0 means the entire file is cached on disk.</param>
        <returns>Text such as 20 MB (Kodi default) or 1 GB.</returns>
        """
        if value == 0:
            return _L(31451)
        if value >= 1024 and value % 1024 == 0:
            text = _L(31452).format(value // 1024)
        else:
            text = _L(31453).format(value)
        return _L(31454).format(text) if value == 20 else text

    @staticmethod
    def _cache_rf_label(value):
        """
        <summary>
        Human readable label for a filecache.readfactor value.
        </summary>
        <param name="value">Percent; 0 means adaptive.</param>
        <returns>Text such as 4x (Kodi default).</returns>
        """
        if value == 0:
            return _L(31455)
        text = _L(31456).format("{0:g}".format(value / 100.0))
        return _L(31454).format(text) if value == 400 else text

    def _refresh_cache_labels(self):
        """
        <summary>
        Mirror the live filecache values into the skin strings the settings
        buttons render. Values changed behind our back (Kodi's own GUI) show
        as their real value, formatted the same way.
        </summary>
        """
        mem = self._get_setting("filecache.memorysize")
        rf = self._get_setting("filecache.readfactor")
        mode = self._get_setting("filecache.buffermode")
        if mem is None or rf is None or mode is None:
            return  # JSON-RPC hiccup: keep the stored labels, retry next open
        _set_skin_string("cache_mem_label", self._cache_mem_label(mem))
        _set_skin_string("cache_rf_label", self._cache_rf_label(rf))
        _set_skin_string("cache_mode_label",
                         _L(self.CACHE_MODE_LABELS[mode]) if mode in self.CACHE_MODE_LABELS
                         else _L(31450).format(mode))

    @staticmethod
    def _fmt_secs(secs):
        """
        <summary>
        45 -> '45s', 130 -> '2m 10s', 3900 -> '1h 5m'.
        </summary>
        """
        if secs >= 3600:
            return "{0}h {1}m".format(secs // 3600, (secs % 3600) // 60)
        if secs >= 60:
            return "{0}m {1}s".format(secs // 60, secs % 60)
        return "{0}s".format(secs)

    @staticmethod
    def _fetch_buffer_ahead():
        """
        <summary>
        (seconds, fraction, cached_pct) for the playing video.
        </summary>
        <remarks>
        seconds/fraction describe what is buffered PAST the playhead;
        cached_pct is how far into the whole file the cache reaches (0-100),
        which is the only meaningful "how full is it" number once unlimited
        buffering is on: Player.CacheLevel is the fill % of the memory buffer,
        and with memorysize 0 there is no memory buffer to be a percentage of,
        so the OSD showed no number at all. Returns (None, 0.0, None) when
        there is no video player.

        cachepercentage is where the cache ends as a fraction of
        the file (same scale as percentage/Player.Progress but float, so this
        stays smooth where whole-percent infolabels would jump in ~40s steps
        on a feature film). The fraction x the file size is also the truest
        byte count available: Player.CacheLevel is only the fill % of the
        memory buffer, which wildly overstates bytes when the file is smaller
        than the buffer.
        </remarks>
        """
        players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
        pid = next((p.get("playerid") for p in players
                    if p.get("type") == "video"), None)
        if pid is None:
            return None, 0.0, None
        resp = _jsonrpc("Player.GetProperties", {
            "playerid": pid,
            "properties": ["percentage", "cachepercentage", "totaltime"]})
        r = (resp or {}).get("result") or {}
        total = r.get("totaltime") or {}
        total_secs = (total.get("hours", 0) * 3600
                      + total.get("minutes", 0) * 60
                      + total.get("seconds", 0))
        cached_pct = float(r.get("cachepercentage") or 0)
        frac = max(0.0, (cached_pct - float(r.get("percentage") or 0)) / 100.0)
        cached = int(round(cached_pct)) if cached_pct > 0 else None
        if not total_secs:
            return None, frac, cached
        return int(round(frac * total_secs)), frac, cached

    # Never stat these: Files.GetFileDetails on a plugin-resolved http URL
    # was observed to hang for minutes inside Kodi (Jellyfin direct-play).
    # The worker thread survives that (daemon, off-loop) but gains nothing:
    # http streams are exactly where the file dwarfs the buffer and the
    # level x memorysize estimate is already accurate.
    _NO_STAT_PREFIXES = ("http://", "https://", "plugin://", "pvr://",
                         "rtsp://", "rtmp://", "udp://", "ftp://")

    def _buffer_size_worker(self, path):
        """
        <summary>
        Stat the playing file's size (daemon thread: an unreachable share
        must never stall the main loop).
        </summary>
        """
        try:
            resp = _jsonrpc("Files.GetFileDetails",
                            {"file": path, "media": "files",
                             "properties": ["size"]})
            size = ((((resp or {}).get("result") or {})
                     .get("filedetails") or {}).get("size")) or 0
        except Exception:  # noqa: BLE001
            size = 0
        self._buffer_filesize = (path, int(size))
        _dlog("buffer: file size = {0} for {1!r}".format(size, path[:100]))

    def update_buffer_stats(self):
        """
        <summary>
        Publish Home property buffer_detail ("39 MB, ~52s ahead") for the
        OSD's buffer readout. Cheap: two in-process player queries per slow
        tick, and only while a video is up. memorysize is re-read once per
        playback (and after our own cache commands change it).
        </summary>
        """
        if not xbmc.getCondVisibility("Player.HasVideo"):
            if self._buffer_last is not None:
                self._buffer_last = None
                self._buffer_memsize = None
                self._buffer_filesize = None
                _set_home_property("buffer_detail", "")
            if self._buffer_pct_last is not None:
                self._buffer_pct_last = None
                _set_home_property("buffer_pct_label", "")
            if self._buffer_fullfile_last is not None:
                self._buffer_fullfile_last = None
                _set_home_property("buffer_fullfile", "")
            self._maybe_restore_cache()
            return

        if self._buffer_memsize is None:
            mem = self._get_setting("filecache.memorysize")
            if mem is None:
                # JSON-RPC hiccup. Retry next tick: reading the failure as 0
                # would flag "full-file buffering" on the OSD for the rest of
                # this playback and skip the MB estimate.
                return
            self._buffer_memsize = int(mem)

        # Tells the OSD its "BUFFER ALL" button is already satisfied
        # (memorysize 0 = Kodi's uncapped disk cache).
        fullfile = "1" if self._buffer_memsize == 0 else ""
        if fullfile != self._buffer_fullfile_last:
            self._buffer_fullfile_last = fullfile
            _set_home_property("buffer_fullfile", fullfile)

        # File size, fetched once per playing path (worker thread). The path
        # check both triggers the first fetch and discards a stale size after
        # a track change.
        path = xbmc.getInfoLabel("Player.FilenameAndPath")
        size = 0
        if path and path.lower().startswith(self._NO_STAT_PREFIXES):
            path = ""  # streamed: no cheap stat, use the estimate below
        if path:
            if self._buffer_filesize and self._buffer_filesize[0] == path:
                size = self._buffer_filesize[1]
            elif (self._buffer_size_thread is None
                    or not self._buffer_size_thread.is_alive()):
                self._buffer_size_thread = threading.Thread(
                    target=self._buffer_size_worker, args=(path,),
                    name="functional-bufsize", daemon=True)
                self._buffer_size_thread.start()

        ahead, frac, cached_pct = self._fetch_buffer_ahead()

        # How much of the whole file is cached. Published pre-formatted (with
        # the % sign, or empty) so the OSD variable can render it through the
        # $INFO[x,prefix,suffix] form and show nothing at all when it's
        # unknown, rather than a bare "%".
        pct_label = "{0}%".format(cached_pct) if cached_pct else ""
        if pct_label != self._buffer_pct_last:
            self._buffer_pct_last = pct_label
            _set_home_property("buffer_pct_label", pct_label)

        parts = []
        mb = 0.0
        if size and frac > 0:
            # Real bytes: fraction of the file that's cached ahead.
            mb = frac * size / 1048576.0
        else:
            # Estimate from the memory buffer's fill level. Only sane when
            # the file is bigger than the buffer, but when the size is
            # unknown that is almost always the case (big remote streams).
            try:
                level = int(xbmc.getInfoLabel("Player.CacheLevel") or "0")
            except ValueError:
                level = 0
            if self._buffer_memsize and level > 0:
                mb = level * self._buffer_memsize / 100.0
        if mb >= 1000:
            parts.append("{0:.1f} GB".format(mb / 1024.0))
        elif mb >= 10:
            parts.append("{0:.0f} MB".format(mb))
        elif mb > 0:
            parts.append("{0:.1f} MB".format(mb))
        if ahead:
            parts.append(_L(31457).format(self._fmt_secs(ahead)))

        detail = ", ".join(parts)
        if detail != self._buffer_last:
            self._buffer_last = detail
            _set_home_property("buffer_detail", detail)

    _CACHE_CYCLES = {
        "mem": ("filecache.memorysize", CACHE_MEM_PRESETS),
        "readfactor": ("filecache.readfactor", CACHE_RF_PRESETS),
        "mode": ("filecache.buffermode", CACHE_MODE_PRESETS),
    }

    def update_cache_command(self):
        """
        <summary>
        Watch Skin.String(cache_command): mem / readfactor / mode cycle
        that setting to its next preset, reset restores Kodi's defaults.
        Labels are re-read every time skin settings opens, since the values
        can also change in Kodi's own Services > Caching page.
        </summary>
        """
        settings_open = xbmc.getCondVisibility("Window.IsActive(skinsettings)")
        if settings_open and not self._cache_labels_fresh:
            self._cache_labels_fresh = True
            self._refresh_cache_labels()
        elif not settings_open:
            self._cache_labels_fresh = False

        # The OSD's full-buffer button can be hidden entirely (Video OSD
        # settings > Show Full Buffer Button). Switching it off also puts
        # buffering back to Kodi's defaults: otherwise a box left mid-film
        # with unlimited buffering on would be stranded there with no visible
        # control to turn it off again.
        ui_off = xbmc.getCondVisibility("Skin.HasSetting(hide_osd_fullbuffer)")
        if self._fullbuffer_ui_last is None:
            self._fullbuffer_ui_last = ui_off  # first tick: observe, don't act
        elif ui_off != self._fullbuffer_ui_last:
            self._fullbuffer_ui_last = ui_off
            if ui_off:
                self._reset_buffering_to_defaults(
                    "Full buffer button hidden, buffering back to defaults")

        cmd = self._take_command("cache_command")
        if not cmd:
            return

        if cmd in ("fullfile", "normalbuffer"):
            # Per-movie unlimited buffering, on and off again (OSD "BUFFER
            # ALL" button). Runs off-loop: it stops and reopens the stream,
            # with waits.
            if self._fullfile_thread is None or not self._fullfile_thread.is_alive():
                self._fullfile_thread = threading.Thread(
                    target=self._fullfile_worker, args=(cmd,),
                    name="functional-fullfile", daemon=True)
                self._fullfile_thread.start()
            return

        if cmd == "reset":
            self._reset_buffering_to_defaults()
            return
        if cmd in self._CACHE_CYCLES:
            sid, presets = self._CACHE_CYCLES[cmd]
            current = self._get_setting(sid)
            try:
                nxt = presets[(presets.index(current) + 1) % len(presets)]
            except ValueError:
                # Off-list value (set in Kodi's GUI): restart the cycle.
                nxt = presets[0]
            self._set_setting(sid, nxt)
            _dlog("cache: {0} {1} -> {2}".format(sid, current, nxt))
        else:
            return
        self._refresh_cache_labels()
        # The OSD readout derives MB from memorysize; make it re-read.
        self._buffer_memsize = None

    def _reset_buffering_to_defaults(self, message=None):
        """
        <summary>
        Put all three filecache settings back to Kodi's defaults.
        </summary>
        <param name="message">optional notification text, for resets the user did not ask for directly (hiding the OSD button).</param>
        <remarks>
        Also drops the full-buffer restore strings: leaving them behind would
        have _maybe_restore_cache quietly undo this reset the moment playback
        ended.
        </remarks>
        """
        for _sid, skin_key in self.FULLFILE_RESTORE_KEYS:
            xbmc.executebuiltin("Skin.Reset({0})".format(skin_key))
        for sid, value in self.CACHE_DEFAULTS.items():
            self._set_setting(sid, value)
        self._refresh_cache_labels()
        self._buffer_memsize = None
        _dlog("cache: reset to Kodi defaults")
        if message:
            xbmcgui.Dialog().notification(
                _L(31000), message, xbmcgui.NOTIFICATION_INFO, 4000)

    # ---- Per-movie "buffer entire file" (OSD BUFFER ALL button) -----------
    # Kodi builds the cache when a stream opens, so changing memorysize does
    # nothing for the file already playing. The switch therefore: remembers
    # the current buffer size in Skin.String(cache_mem_restore) (a skin
    # string so it survives a Kodi restart mid-movie), sets memorysize 0
    # (= uncapped disk cache), stops the stream and reopens it at the same
    # position. When playback ends, _maybe_restore_cache puts the normal
    # size (and buffer mode, and read factor) back. Side effect worth
    # knowing: if another video starts before the restore fires (~1s after
    # stop), it also runs uncapped until ITS playback ends, which is
    # harmless, just surprising in a log.
    #
    # Clicking the button a second time ("normalbuffer") runs the same switch
    # in reverse without waiting for playback to end: restore value back into
    # memorysize, skin string cleared, stream reopened at the same position.

    FULLFILE_REOPEN_WAIT = 30  # seconds to wait for the stream to come back
    FULLFILE_SEEK_BACK = 5     # rejoin slightly early: lands near a keyframe
    # Buffer mode 1 = "everything, including local files". memorysize alone
    # was not enough: on the default mode 4 (network shares + internet) Kodi
    # runs no cache at all for some sources, so "buffer the entire file"
    # buffered nothing and the readout stayed blank.
    FULLFILE_MODE = 1
    # Read factor floor while full-buffering. The adaptive setting (0) only
    # reads a little ahead of the playhead by design, which is the other
    # reason the whole file never arrived. 1000 = 10x playback rate.
    FULLFILE_MIN_READFACTOR = 1000

    # The three filecache settings the full-buffer switch takes over, each
    # paired with the skin string that remembers the user's own value. Skin
    # strings (not instance state) so a Kodi restart mid-film can still put
    # things back.
    FULLFILE_RESTORE_KEYS = (
        ("filecache.memorysize", "cache_mem_restore"),
        ("filecache.buffermode", "cache_mode_restore"),
        ("filecache.readfactor", "cache_rf_restore"),
    )

    def _maybe_restore_cache(self):
        """
        <summary>
        Called when no video is playing: if a full-file run left restore
        values behind, put the user's own buffer settings back.
        </summary>
        <remarks>
        Covers all three filecache settings the switch takes over. Each is
        independent: a missing string just means that one wasn't changed.
        </remarks>
        """
        if self._fullfile_busy:
            return  # mid-switch: the player is only momentarily stopped
        restored = {}
        for setting_id, skin_key in self.FULLFILE_RESTORE_KEYS:
            prior = xbmc.getInfoLabel("Skin.String({0})".format(skin_key))
            if not prior:
                continue
            xbmc.executebuiltin("Skin.Reset({0})".format(skin_key))
            value = self._safe_int(prior, None)
            if value is None:
                continue
            self._set_setting(setting_id, value)
            restored[setting_id] = value
        if not restored:
            return
        self._refresh_cache_labels()
        self._buffer_memsize = None
        _dlog("fullfile: playback over, restored {0}".format(restored))

    def _fullfile_worker(self, mode="fullfile"):
        """
        <summary>
        Thread body for both directions of the switch.
        </summary>
        <param name="mode">"fullfile" to turn unlimited buffering on, "normalbuffer" to go back to the remembered buffer size.</param>
        <remarks>
        </remarks>
        """
        try:
            self._fullfile_busy = True
            self._do_fullfile_switch(mode)
        except Exception:  # noqa: BLE001
            _dlog("fullfile switch failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
        finally:
            self._fullfile_busy = False

    def _do_fullfile_switch(self, mode="fullfile"):
        """
        <summary>
        Set filecache.memorysize for this playback and reopen the stream at
        the same position, in whichever direction `mode` asks for.
        </summary>
        <param name="mode">"fullfile" (memorysize 0 = uncapped disk cache) or "normalbuffer" (back to Skin.String(cache_mem_restore), falling back to Kodi's default size if that is gone).</param>
        <remarks>
        Both directions are the same dance because Kodi sizes the cache when
        the stream opens: changing the setting alone does nothing until the
        file is reopened.
        </remarks>
        """
        current = self._get_setting("filecache.memorysize")
        if current is None:
            # Without the current size there is nothing to restore to after
            # playback, and the uncapped disk cache would stay on for good.
            _dlog("fullfile: could not read filecache.memorysize, not switching",
                  xbmc.LOGWARNING)
            xbmcgui.Dialog().notification(
                _L(31000), _L(31328),
                xbmcgui.NOTIFICATION_WARNING, 4000)
            return
        if mode == "fullfile":
            if current == 0:
                xbmcgui.Dialog().notification(
                    _L(31000), _L(31331),
                    xbmcgui.NOTIFICATION_INFO, 4000)
                return
            target_size = 0
            message = _L(31329)
        else:
            if current != 0:
                xbmcgui.Dialog().notification(
                    _L(31000), _L(31332),
                    xbmcgui.NOTIFICATION_INFO, 4000)
                return
            # Nothing remembered means the uncapped size was set somewhere
            # other than this button (Kodi's own Caching page, or a restart
            # that lost the skin string): Kodi's default is the safe landing.
            target_size = self._safe_int(
                xbmc.getInfoLabel("Skin.String(cache_mem_restore)"),
                self.CACHE_DEFAULTS["filecache.memorysize"])
            if target_size == 0:
                # A remembered 0 would restart straight back into unlimited
                # buffering, i.e. the button would do nothing.
                target_size = self.CACHE_DEFAULTS["filecache.memorysize"]
            message = _L(31330)
        players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
        pid = next((p.get("playerid") for p in players
                    if p.get("type") == "video"), None)
        if pid is None:
            return
        item = ((_jsonrpc("Player.GetItem",
                          {"playerid": pid, "properties": ["file"]})
                 .get("result") or {}).get("item")) or {}
        t = ((_jsonrpc("Player.GetProperties",
                       {"playerid": pid, "properties": ["time"]})
              .get("result") or {}).get("time")) or {}
        secs = (t.get("hours", 0) * 3600 + t.get("minutes", 0) * 60
                + t.get("seconds", 0))
        secs = max(0, secs - self.FULLFILE_SEEK_BACK)

        # Prefer the library id (survives path quirks); fall back to the file.
        if item.get("id") and item.get("type") in ("movie", "episode",
                                                   "musicvideo"):
            target = {"{0}id".format(item["type"]): item["id"]}
        else:
            if not item.get("file"):
                _dlog("fullfile: nothing identifiable to reopen", xbmc.LOGWARNING)
                return
            target = {"file": item["file"]}

        # Past here the switch is committed: the player exists and we know what
        # to reopen, so remembering the old values can't strand them.
        if mode == "fullfile":
            _set_skin_string("cache_mem_restore", current)
            # memorysize 0 on its own is not "buffer the whole file". The
            # buffer MODE decides whether this source is cached at all (on
            # Kodi's default, mode 4, plenty of sources get no cache, so the
            # button appeared to do nothing and the readout stayed blank), and
            # the READ FACTOR decides how far ahead Kodi bothers to read (the
            # adaptive setting reads barely past the playhead by design).
            # Take both over for the duration, remembering the user's values.
            mode_now = self._get_setting("filecache.buffermode")
            if mode_now is not None and mode_now != self.FULLFILE_MODE:
                _set_skin_string("cache_mode_restore", mode_now)
                self._set_setting("filecache.buffermode", self.FULLFILE_MODE)
            rf_now = self._get_setting("filecache.readfactor")
            if rf_now is not None and (rf_now == 0
                                       or rf_now < self.FULLFILE_MIN_READFACTOR):
                _set_skin_string("cache_rf_restore", rf_now)
                self._set_setting("filecache.readfactor",
                                  self.FULLFILE_MIN_READFACTOR)
        else:
            # Consumed: without this, _maybe_restore_cache would set the same
            # values again when playback ends, and any later read of the
            # strings would be stale. Mode and read factor go back here too,
            # otherwise "normal buffering" would keep caching local files at
            # 10x for the rest of the session.
            for setting_id, skin_key in self.FULLFILE_RESTORE_KEYS:
                if setting_id == "filecache.memorysize":
                    continue  # handled by target_size below
                prior = self._safe_int(
                    xbmc.getInfoLabel("Skin.String({0})".format(skin_key)), None)
                if prior is not None:
                    self._set_setting(setting_id, prior)
                xbmc.executebuiltin("Skin.Reset({0})".format(skin_key))
            xbmc.executebuiltin("Skin.Reset(cache_mem_restore)")
        self._set_setting("filecache.memorysize", target_size)
        self._refresh_cache_labels()
        # The OSD's MB estimate and its buffer_fullfile flag both derive from
        # memorysize; make update_buffer_stats() re-read it.
        self._buffer_memsize = None
        xbmcgui.Dialog().notification(
            _L(31000), message, xbmcgui.NOTIFICATION_INFO, 5000)
        _dlog("fullfile: reopening {0} at {1}s (memorysize {2} -> {3})".format(
            target, secs, current, target_size))
        _jsonrpc("Player.Stop", {"playerid": pid})
        xbmc.sleep(1500)
        _jsonrpc("Player.Open", {"item": target})
        for _ in range(self.FULLFILE_REOPEN_WAIT * 2):
            if xbmc.getCondVisibility("Player.HasVideo"):
                break
            xbmc.sleep(500)
        else:
            _dlog("fullfile: stream did not come back within {0}s".format(
                self.FULLFILE_REOPEN_WAIT), xbmc.LOGWARNING)
            return
        xbmc.sleep(2000)  # let the demuxer settle before seeking
        if secs > 10:
            players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
            pid = next((p.get("playerid") for p in players
                        if p.get("type") == "video"), None)
            if pid is not None:
                _jsonrpc("Player.Seek", {"playerid": pid, "value": {"time": {
                    "hours": secs // 3600, "minutes": (secs % 3600) // 60,
                    "seconds": secs % 60, "milliseconds": 0}}})
        _dlog("fullfile: switch complete")

    def update_home_bg(self):
        """
        <summary>
        Rotate Home's background through the configured slideshow source on a
        user-configurable timer. Source is Skin.String(bg_mode): one of
        "recent" (recently watched movies), "random" (random library fanart),
        "genre" (random fanart from Skin.String(bg_genre), restricted to
        Skin.String(bg_genre_type)), "folder" (images from
        Skin.String(bg_slideshow_folder)). Empty/unset = off. Cadence:
        Skin.String(bg_slideshow_interval) in seconds, falling back to
        BG_INTERVAL when empty/unset.
        </summary>
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
            if self._bg_source:
                self._bg_source = ""
                self._bg_idx = -1
            self._set_bg_props("", "")
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
                self._set_bg_props("", "")
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
            # In image mode, surface the chosen file's name as the caption
            # (same as folder/library captions). Off = no caption.
            label = (_basename_no_ext(xbmc.getInfoLabel(
                "Skin.String(home_background)")) if mode == "image" else "")
            self._set_bg_props("", label)
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
            self._set_bg_props("", "")

        # Refresh the items list periodically or when invalidated. An empty
        # result (server unreachable at boot, library mid-scan) retries on a
        # short backoff, NOT every tick, which hammered the source. The
        # fetch itself runs on a daemon thread: executeJSONRPC against a
        # slow/unreachable video DB blocks, and blocking here stalls ETA,
        # every command channel and the rest of the loop (the same failure
        # the stats and cast lookups were moved off-loop for).
        refresh_after = self.BG_LIST_REFRESH if self._bg_items else self.BG_EMPTY_RETRY
        if ((now - self._bg_last_fetch) > refresh_after
                and (self._bg_thread is None or not self._bg_thread.is_alive())):
            self._bg_last_fetch = now
            self._bg_thread = threading.Thread(
                target=self._bg_fetch_worker, args=(source,),
                name="functional-bg", daemon=True)
            self._bg_thread.start()

        if not self._bg_items:
            # Nothing to show (fetch still in flight, folder empty or
            # unreadable), clear so a previous mode's backdrop doesn't stay
            # on screen.
            self._set_bg_props("", "")
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
            self._set_bg_props(url, label)
            _dlog("bg rotate -> {0} | {1}".format(label, url[:120]), xbmc.LOGDEBUG)

    @staticmethod
    def _set_bg_props(fanart, label):
        """
        <summary>
        Write the two Home background properties, skipping writes that
        wouldn't change anything: several callers run once per slow tick
        forever, and bursts of redundant Window(home) writes are implicated
        in the startup SIGABRT (see run()).
        </summary>
        """
        win = xbmcgui.Window(HOME_WINDOW_ID)
        if win.getProperty("home_bg_fanart") != fanart:
            win.setProperty("home_bg_fanart", fanart)
        if win.getProperty("home_bg_label") != label:
            win.setProperty("home_bg_label", label)

    def _bg_fetch_worker(self, source):
        """
        <summary>
        Resolve the slideshow item list for *source* (daemon thread).
        </summary>
        """
        try:
            if source == "recent":
                items = self._fetch_recent_movies()
            elif source.startswith("genre:"):
                _, gtype, gname = source.split(":", 2)
                items = self._fetch_genre_library(gname, gtype)
            else:  # random
                items = self._fetch_random_library()
        except Exception:  # noqa: BLE001
            _dlog("bg fetch worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            return  # empty-retry backoff will schedule another attempt
        # The user may have switched source while we were querying; don't
        # install a stale list over the new source's (same idea as the cast
        # workers' staleness guard).
        if source != self._bg_source:
            return
        self._bg_items = items
        _dlog("bg slideshow ({0}): {1} items".format(source, len(items)))
        # Force a rotation on the next slow tick.
        self._bg_last_change = 0.0
        self._bg_idx = -1

    # ----- Favourites (categorised, filterable) ----------------------------
    # Ordered list of filter categories shown on the custom Favourites screen.
    FAV_CATS = ("all", "movies", "tvshows", "music", "apps", "other")

    @staticmethod
    def _fav_category(action):
        """
        <summary>
        Classify a favourite by its action string into one of FAV_CATS
        (never 'all', 'all' is the no-filter pseudo-category).
        </summary>
        """
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
        """
        <summary>
        Local path of the profile's favourites.xml.
        </summary>
        <returns>The special://profile path translated to a filesystem path.</returns>
        """
        return xbmcvfs.translatePath("special://profile/favourites.xml")

    def _read_favourites(self):
        """
        <summary>
        Parse favourites.xml into self._fav_all. Returns True on (re)load.
        </summary>
        """
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
        """
        <summary>
        Count the loaded favourites per category.
        </summary>
        <returns>Dict keyed by every FAV_CATS entry plus all, values are counts.</returns>
        """
        counts = {c: 0 for c in self.FAV_CATS}
        counts["all"] = len(self._fav_all)
        for it in self._fav_all:
            counts[it["cat"]] = counts.get(it["cat"], 0) + 1
        return counts

    def _populate_favourites(self, category):
        """
        <summary>
        Write Fav.* window properties for the given category.
        </summary>
        """
        win = xbmcgui.Window(HOME_WINDOW_ID)
        if category == "all" or category not in self.FAV_CATS:
            shown = list(self._fav_all)
        else:
            shown = [it for it in self._fav_all if it["cat"] == category]
        # The screen has exactly FAV_MAX slots; anything past that would be
        # invisible property writes (and Fav.Count would overstate what the
        # grid can show, breaking the 1-based fav_run indexing contract).
        shown = shown[:self.FAV_MAX]
        self._fav_current = shown
        win.setProperty("Fav.Count", str(len(shown)))
        win.setProperty("Fav.Category", category)
        counts = self._fav_counts()
        for c in self.FAV_CATS:
            win.setProperty("Fav.CatCount.%s" % c, str(counts.get(c, 0)))
        # Only touch slots in use (plus previously-used ones that need
        # clearing): with an empty favourites list the old loop fired 450
        # clear calls at the GUI in one burst on every publish.
        used_before = getattr(self, "_fav_slots_used", 0)
        for i in range(max(len(shown), used_before)):
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
        self._fav_slots_used = len(shown)
        self._fav_last_cat = category

    def update_favourites(self):
        """
        <summary>
        Keep the custom Favourites screen fed. Handles:
          - loading/reloading favourites.xml when it changes on disk
          - reacting to the selected category (Skin.String(fav_category))
          - running a favourite when Skin.String(fav_run) is set to its index
        Cheap enough to call every tick.
        </summary>
        """
        # Run a chosen favourite (set by the UI as a 1-based index into the
        # currently-shown, filtered list) then clear the request.
        run = self._take_command("fav_run")
        if run:
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

    # ---- Continue Watching (pop-up on Home) -------------------------------
    # <summary>
    # The pop-up's lists are live library containers fed by the skin's
    # continue_movies.xsp and continue_episodes.xsp, so Kodi owns the rows,
    # plays them and keeps them current from its own library events. The
    # service supplies the two things a skin cannot: the resume time of the
    # focused row, for the press-and-hold menu's "Resume from" entry, and the
    # three menu actions behind Skin.String(continue_command).
    # </summary>

    def update_continue_watching(self):
        """
        <summary>
        Serve the Continue Watching pop-up: run a press-and-hold menu action
        when Skin.String(continue_command) is set, publish continue_focus
        while one of the pop-up's lists has focus so DialogContextMenu can
        swap in the skin's own rows, and keep continue_resume describing the
        focused row. Cheap enough to call every tick.
        </summary>
        <remarks>
        The menu rows cannot capture the item themselves: inside a dialog
        opened over Home, ListItem is empty (Home has no current item the
        way a media window has), so the row acted on is the one this tick
        last saw focused, remembered in _continue_focus_key and mirrored to
        the continue_label property for the menu's heading. A press and
        hold takes longer than a tick, so that key is current by the time
        the menu opens. Nothing here changes while the context menu itself
        is open: the focused control is then the menu's, and clearing
        continue_focus at that moment would hide the rows the user is
        looking at. The resume lookup runs on a daemon thread with a key
        latch so a slow video database never stalls the loop and a late
        reply never describes the wrong row. The menu action itself runs
        on its own daemon thread for the same reason: it writes to the
        video database and a sleeping database would otherwise hold the
        whole loop, the sleep countdown and every command channel with
        it, until the call timed out. A second press while one action is
        still running is dropped and logged rather than queued.
        </remarks>
        """
        cmd = self._take_command("continue_command")
        if cmd:
            dbtype, dbid = self._continue_focus_key or ("", 0)
            # Dropped here, on the loop, so the next tick re-reads the
            # resume time of whatever row is focused now.
            self._continue_focus_key = None
            if (self._continue_action_thread is not None
                    and self._continue_action_thread.is_alive()):
                _dlog("continue watching: %s dropped, an action is still "
                      "running" % cmd)
                return
            self._continue_action_thread = threading.Thread(
                target=self._continue_action_worker,
                args=(cmd, dbtype, dbid),
                name="functional-continue-action", daemon=True)
            self._continue_action_thread.start()
            return

        if xbmc.getCondVisibility("Window.IsActive(contextmenu)"):
            return
        win = xbmcgui.Window(HOME_WINDOW_ID)
        focused = (xbmc.getCondVisibility("Window.IsActive(home)")
                   and not xbmc.getCondVisibility("Skin.HasSetting(hide_continue)")
                   and xbmc.getInfoLabel("System.CurrentControlId") in self.CONTINUE_LISTS)
        if focused != self._continue_focused:
            self._continue_focused = focused
            if focused:
                win.setProperty("continue_focus", "1")
            else:
                win.clearProperty("continue_focus")
        if not focused:
            if self._continue_focus_key is not None:
                self._continue_focus_key = None
                win.clearProperty("continue_resume")
            return

        dbtype = xbmc.getInfoLabel("ListItem.DBTYPE").strip().lower()
        dbid = self._safe_int(xbmc.getInfoLabel("ListItem.DBID"), 0)
        key = (dbtype, dbid)
        if key == self._continue_focus_key:
            return
        self._continue_focus_key = key
        win.clearProperty("continue_resume")
        win.setProperty("continue_label", xbmc.getInfoLabel("ListItem.Label"))
        if dbtype not in ("movie", "episode") or dbid <= 0:
            return
        with self._continue_lock:
            self._continue_key += 1
            gen = self._continue_key
        threading.Thread(
            target=self._continue_resume_worker, args=(gen, dbtype, dbid),
            name="functional-continue", daemon=True).start()

    def _continue_resume_worker(self, gen, dbtype, dbid):
        """
        <summary>
        Daemon thread body: look up one row's resume point and publish it as
        the continue_resume Home property (HH:MM:SS) if this lookup is still
        the latest.
        </summary>
        <param name="gen">Generation number taken when the lookup started.</param>
        <param name="dbtype">"movie" or "episode".</param>
        <param name="dbid">Library id of the row.</param>
        """
        kind = "Movie" if dbtype == "movie" else "Episode"
        resp = _jsonrpc("VideoLibrary.Get%sDetails" % kind,
                        {dbtype + "id": dbid, "properties": ["resume"]})
        details = (resp.get("result") or {}).get(dbtype + "details") or {}
        try:
            position = int(float((details.get("resume") or {}).get("position") or 0))
        except (TypeError, ValueError):
            position = 0
        label = ""
        if position > 0:
            label = "%02d:%02d:%02d" % (position // 3600, (position % 3600) // 60, position % 60)
        with self._continue_lock:
            if gen != self._continue_key:
                return
            xbmcgui.Window(HOME_WINDOW_ID).setProperty("continue_resume", label)

    def _continue_action_worker(self, cmd, dbtype, dbid):
        """
        <summary>
        Daemon thread body: run one press and hold menu action and log,
        never raise, when it fails.
        </summary>
        <param name="cmd">continue_command value: resume, watched or unwatched.</param>
        <param name="dbtype">"movie" or "episode" of the row the menu was opened on.</param>
        <param name="dbid">Library id of that row.</param>
        """
        try:
            self._continue_action(cmd, dbtype, dbid)
        except Exception:  # noqa: BLE001
            _dlog("continue watching: %s failed:\n%s"
                  % (cmd, traceback.format_exc()), xbmc.LOGERROR)

    def _continue_action(self, cmd, dbtype, dbid):
        """
        <summary>
        Run one entry of the pop-up's press-and-hold menu. Called on the
        action thread, never on the loop.
        </summary>
        <param name="cmd">continue_command value: resume, watched or unwatched.</param>
        <param name="dbtype">"movie" or "episode" of the row the menu was opened on.</param>
        <param name="dbid">Library id of that row.</param>
        <remarks>
        "watched" bumps the play count and clears the resume point, which is
        what Kodi's own "Mark as watched" does; "unwatched" zeroes both.
        The row leaves the pop-up through Kodi's own VideoLibrary.OnUpdate
        handling, which its directory provider honours within a second for
        a row it holds (verified on 21.3) as long as the container is being
        processed, which is why Home.xml parks the closed panel off screen
        instead of hiding it. That announcement is only raised for a play
        count change, see the unwatched branch. The caller drops the
        remembered focus key before starting this thread, so the next
        tick re-reads the resume time of whatever row is focused now.
        </remarks>
        """
        if dbtype not in ("movie", "episode") or dbid <= 0:
            _dlog("continue watching: %s ignored, no item captured" % cmd)
            return
        kind = "Movie" if dbtype == "movie" else "Episode"
        idkey = dbtype + "id"
        _dlog("continue watching: %s %s %d" % (cmd, dbtype, dbid))
        if cmd == "resume":
            _jsonrpc("Player.Open", {"item": {idkey: dbid}, "options": {"resume": True}})
        elif cmd in ("watched", "unwatched"):
            resp = _jsonrpc("VideoLibrary.Get%sDetails" % kind,
                            {idkey: dbid, "properties": ["playcount"]})
            details = (resp.get("result") or {}).get(dbtype + "details") or {}
            count = self._safe_int(details.get("playcount"), 0)
            params = {idkey: dbid, "resume": {"position": 0, "total": 0}}
            if cmd == "watched":
                params["playcount"] = count + 1
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, params)
            elif count > 0:
                params["playcount"] = 0
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, params)
            else:
                # Kodi announces VideoLibrary.OnUpdate only when the play
                # count actually changes, and the pop-up's containers reload
                # only on an announcement for a row they hold. Clearing the
                # resume point of a never-finished title changes no play
                # count, so it would stay in the row. Bump the count to one
                # in the same write that clears the bookmark (the row goes),
                # then back to zero (announced too, but the row no longer
                # holds the item, so Kodi ignores it). Verified on 21.3.
                params["playcount"] = 1
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, params)
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, {idkey: dbid, "playcount": 0})
        else:
            _dlog("continue command ignored: %r" % cmd)

    # ---- Lists (named media lists, ported into the queue) -----------------
    # <summary>
    # A list is a named, ordered set of playable items (movies, episodes,
    # songs, plugin streams) kept by the skin in lists.json. Items arrive
    # from the press-and-hold actions menu (DialogContextMenu's two static
    # buttons), from the Lists screen (custom window 1151) or from the queue
    # windows ("Save as List"). "Porting" copies a list into Kodi's video
    # and/or music queue, in order or shuffled, and starts it playing.
    # </summary>
    # <remarks>
    # Everything runs through Skin.String(list_command), the same channel
    # style as bg_command. Item identity captured by the skin at click time
    # sits in Home window properties (list_item_*), because the underlying
    # container can move on before the service's next tick. The Lists
    # screen binds static lists to Lists.N.* / LI.N.* Home properties and
    # the service follows the focused list to fill the right column.
    # </remarks>
    LISTS_FILE = "special://profile/addon_data/skin.functional/lists.json"
    LISTS_MAX = 60           # rows on the Lists screen's left column
    LIST_ITEMS_MAX = 200     # rows on its right column (and per-list cap)
    # Minutes offered by "Port by Time" for a list that has never been
    # filled before. Per-list once chosen, stored as "fill" in lists.json.
    LIST_FILL_DEFAULT = 180
    LISTS_WINDOW_ID = 1151
    LIST_PLAYLIST_IDS = {"music": 0, "video": 1}
    # ListItem.DBTYPE -> the JSON-RPC Playlist.Item key that plays it by id
    LIST_DBID_KEYS = {"movie": "movieid", "episode": "episodeid",
                      "musicvideo": "musicvideoid", "song": "songid"}
    LIST_MUSIC_TYPES = ("song",)
    LIST_ITEM_PROPS = ("label", "file", "dbtype", "dbid", "thumb", "duration",
                       "show", "season", "episode", "artist", "year", "kind")

    def _lists_path(self):
        """<summary>Absolute path of lists.json, creating its folder.</summary>
        <returns>Filesystem path as a string.</returns>"""
        folder = xbmcvfs.translatePath(
            "special://profile/addon_data/skin.functional/")
        if not xbmcvfs.exists(folder):
            xbmcvfs.mkdirs(folder)
        return xbmcvfs.translatePath(self.LISTS_FILE)

    def _lists_load(self, force=False):
        """<summary>Read lists.json into self._lists once (or again on
        request) and mirror its remembered last list into
        Skin.String(lists_last).</summary>
        <param name="force">Re-read even if already loaded.</param>
        <returns>The in-memory list of list dicts (never None).</returns>
        <remarks>A missing file is an empty set of lists, never an error:
        the feature must degrade to "no lists yet". An unreadable file is
        also an empty set for this session, but it is set aside first so
        that the next save cannot write over it, see _lists_set_aside.
        </remarks>"""
        with self._lists_lock:
            if self._lists is not None and not force:
                return self._lists
            lists, last = [], ""
            broken = False
            path = self._lists_path()
            if xbmcvfs.exists(path):
                try:
                    with xbmcvfs.File(path) as fh:
                        data = json.loads(fh.read() or "{}")
                    for entry in data.get("lists", []) or []:
                        name = str(entry.get("name", "")).strip()
                        if not name:
                            continue
                        items = [self._list_item_clean(it)
                                 for it in entry.get("items", []) or []]
                        # "fill" is the Port by Time length in minutes,
                        # remembered per list. 0 means never set, so the
                        # dialog opens on LIST_FILL_DEFAULT. Clamped
                        # because _parse_hhmm tops out at 23:59.
                        try:
                            fill = int(entry.get("fill") or 0)
                        except (TypeError, ValueError):
                            fill = 0
                        lists.append({"name": name,
                                      "items": [it for it in items if it],
                                      "fill": min(max(fill, 0), 23 * 60 + 59)})
                    last = str(data.get("last", "") or "")
                except Exception:  # noqa: BLE001
                    _dlog("lists.json unreadable:\n" + traceback.format_exc(),
                          xbmc.LOGWARNING)
                    lists, last = [], ""
                    broken = True
            self._lists = lists
            if broken:
                self._lists_set_aside(path)
            else:
                self._lists_frozen = False
            if last and not any(l["name"] == last for l in lists):
                last = ""
            self._lists_last = last
        self._set_or_reset("lists_last", last)
        self._lists_publish()
        _dlog("lists loaded: %d lists" % len(lists))
        return lists

    def _lists_set_aside(self, path):
        """
        <summary>
        Move an unreadable lists.json out of the way under a timestamped
        name, or freeze saving when even that fails.
        </summary>
        <param name="path">Filesystem path of the unreadable file.</param>
        <remarks>
        An unreadable file used to become an empty set of lists, and the
        next Add To List click then wrote that emptiness over the file:
        one transient read failure plus one click and every list was
        gone. Nothing is deleted here. The file is renamed to
        lists.json.broken-STAMP beside where the fresh one will go, so
        the lists can be recovered by hand, and a toast says so. If the
        rename itself fails the file stays put and _lists_save refuses
        to write until a later load succeeds, the only other way to be
        sure nothing is overwritten. Called with _lists_lock held.
        </remarks>
        """
        aside = "%s.broken-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
        try:
            os.replace(path, aside)
        except OSError:
            self._lists_frozen = True
            _dlog("lists.json could not be set aside, saving is frozen:\n"
                  + traceback.format_exc(), xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                _L(31024), _L(31442), xbmcgui.NOTIFICATION_ERROR, 6000)
            return
        self._lists_frozen = False
        _dlog("lists.json set aside as %s" % os.path.basename(aside),
              xbmc.LOGWARNING)
        xbmcgui.Dialog().notification(
            _L(31024), _L(31443), xbmcgui.NOTIFICATION_WARNING, 6000)

    def _lists_save(self):
        """<summary>Write self._lists and the last-used name to lists.json,
        then republish the screen properties.</summary>
        <remarks>Writes go to a temp file first and are renamed over the
        real one, so a crash mid-write cannot leave a truncated file that
        the next load would read as "no lists". Refused outright while
        _lists_frozen is set: the file on disk could not be read and could
        not be moved aside, so writing would destroy it.</remarks>"""
        with self._lists_lock:
            frozen = self._lists_frozen
            payload = json.dumps({"version": 1, "last": self._lists_last,
                                  "lists": self._lists or []},
                                 ensure_ascii=False, indent=1)
        if frozen:
            _dlog("lists.json save refused: the file on disk is unreadable "
                  "and could not be set aside", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                _L(31024), _L(31442), xbmcgui.NOTIFICATION_ERROR, 4000)
            return
        path = self._lists_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        except OSError:
            _dlog("lists.json write failed:\n" + traceback.format_exc(),
                  xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                _L(31024), _L(31333),
                xbmcgui.NOTIFICATION_ERROR, 4000)
        self._set_or_reset("lists_last", self._lists_last)
        self._lists_publish()

    @classmethod
    def _list_item_clean(cls, raw):
        """<summary>Normalise one stored or captured item record.</summary>
        <param name="raw">Dict with any of LIST_ITEM_PROPS.</param>
        <returns>A clean dict, or None when there is nothing playable in it.</returns>"""
        if not isinstance(raw, dict):
            return None
        it = {k: str(raw.get(k, "") or "").strip() for k in cls.LIST_ITEM_PROPS}
        try:
            it["dbid"] = int(it["dbid"] or 0)
        except ValueError:
            it["dbid"] = 0
        if it["dbtype"] not in cls.LIST_DBID_KEYS:
            it["dbid"] = 0
        try:
            it["duration"] = int(it["duration"] or 0)
        except ValueError:
            it["duration"] = _parse_duration_to_seconds(it["duration"])
        if it["dbtype"] in cls.LIST_MUSIC_TYPES:
            it["kind"] = "music"
        elif it["kind"] != "music":
            it["kind"] = "video"
        if not it["file"] and not it["dbid"]:
            return None
        if not it["label"]:
            it["label"] = _basename_no_ext(it["file"]) or _L(31458)
        return it

    @staticmethod
    def _list_item_same(a, b):
        """<summary>True when two records name the same media.</summary>
        <remarks>Library id wins when both carry one; otherwise the path.
        A library item captured from a plugin listing and the same item
        captured from the library compare by id, so they do not double up.</remarks>"""
        if a["dbid"] and b["dbid"]:
            return a["dbtype"] == b["dbtype"] and a["dbid"] == b["dbid"]
        return bool(a["file"]) and a["file"] == b["file"]

    @classmethod
    def _list_item_sub(cls, it):
        """<summary>The dim second line shown under an item on the Lists
        screen, e.g. "Movie (1927) · 2h 33m" or "Show S01E04 · 42m".</summary>"""
        bits = []
        if it["dbtype"] == "episode" or (it["show"] and it["episode"]):
            tag = ""
            if it["season"] and it["episode"]:
                try:
                    tag = "S%02dE%02d" % (int(it["season"]), int(it["episode"]))
                except ValueError:
                    tag = ""
            bits.append((it["show"] + " " + tag).strip() or _L(31459))
        elif it["kind"] == "music":
            bits.append(it["artist"] or _L(31460))
        elif it["dbtype"] == "musicvideo":
            bits.append(it["artist"] or _L(31461))
        else:
            bits.append(_L(31462) + (" (%s)" % it["year"] if it["year"] else "")
                        if it["dbtype"] == "movie" else _L(31463))
        if it["duration"]:
            bits.append(cls._fmt_secs(it["duration"]))
        return " · ".join(bits)

    def _lists_publish(self):
        """<summary>Push the list of lists into Lists.N.* Home properties
        for the left column, and refresh the selected list's items.</summary>"""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        with self._lists_lock:
            lists = list(self._lists or [])
        shown = lists[:self.LISTS_MAX]
        win.setProperty("Lists.Count", str(len(shown)))
        used_before = self._lists_slots_used
        for i in range(max(len(shown), used_before)):
            n = i + 1
            if i < len(shown):
                lst = shown[i]
                total = sum(it["duration"] for it in lst["items"])
                sub = (_L(31334) if len(lst["items"]) == 1
                       else _L(31335)) % len(lst["items"])
                if total:
                    sub += " · " + self._fmt_secs(total)
                win.setProperty("Lists.%d.Name" % n, lst["name"])
                win.setProperty("Lists.%d.Sub" % n, sub)
            else:
                win.clearProperty("Lists.%d.Name" % n)
                win.clearProperty("Lists.%d.Sub" % n)
        self._lists_slots_used = len(shown)
        # The selection may now point past the end (a delete) or at a
        # different list (an insert), so redo the right column regardless.
        self._lists_sel_pub = None
        self._list_items_publish(self._lists_sel)

    def _list_items_publish(self, idx):
        """<summary>Fill the right column (LI.N.*) with list number idx's
        items and the Lists.Sel.* heading.</summary>
        <param name="idx">1-based index into the lists, 0 or out of range clears.</param>"""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        with self._lists_lock:
            lists = list(self._lists or [])
        lst = lists[idx - 1] if 0 < idx <= len(lists) else None
        items = list(lst["items"])[:self.LIST_ITEMS_MAX] if lst else []
        win.setProperty("Lists.Sel.Idx", str(idx if lst else 0))
        win.setProperty("Lists.Sel.Name", lst["name"] if lst else "")
        win.setProperty("Lists.Sel.Count", str(len(items)))
        # Pre-formatted so the heading does not have to say "1 items".
        win.setProperty("Lists.Sel.CountLabel",
                        (_L(31334) if len(items) == 1
                         else _L(31335)) % len(items) if lst else "")
        total = sum(it["duration"] for it in items)
        win.setProperty("Lists.Sel.Duration",
                        self._fmt_secs(total) if total else "")
        # Shown on the Port by Time button, so the remembered length for
        # this list is visible before opening the dialog.
        win.setProperty("Lists.Sel.Fill",
                        self._fmt_hhmm(int((lst or {}).get("fill") or
                                           self.LIST_FILL_DEFAULT))
                        if lst else "")
        used_before = self._list_item_slots_used
        for i in range(max(len(items), used_before)):
            n = i + 1
            if i < len(items):
                it = items[i]
                win.setProperty("LI.%d.Label" % n, it["label"])
                win.setProperty("LI.%d.Sub" % n, self._list_item_sub(it))
                win.setProperty("LI.%d.Thumb" % n, it["thumb"])
                win.setProperty("LI.%d.Kind" % n, it["kind"])
            else:
                for key in ("Label", "Sub", "Thumb", "Kind"):
                    win.clearProperty("LI.%d.%s" % (n, key))
        self._list_item_slots_used = len(items)
        self._lists_sel_pub = idx if lst else 0

    def update_lists(self):
        """<summary>Fast-tick handler for the Lists feature: runs queued
        list_command values on the dialog thread and keeps the Lists
        screen's right column following the focused list.</summary>
        <remarks>Commands: add_last, add_pick (item in list_item_* Home
        properties); new, rename, delete, port, port_shuffle, port_time
        (act on the selected list); item:N (action menu for row N of the
        selected
        list); save_queue (the open queue window becomes a new list).
        A command arriving while another dialog is up is dropped, as with
        bg_command, rather than queued behind a picker nobody can see.</remarks>"""
        cmd = self._take_command("list_command")
        if cmd:
            _dlog("list command: %s" % cmd)
            self._spawn_dialog(lambda: self._lists_worker(cmd))
            return
        # Load once at startup, not on first use: the Lists screen's
        # default control is the list of lists, which has nothing to focus
        # until the properties exist, and the home menu opens it cold.
        if self._lists is None:
            self._lists_load()
        if not xbmc.getCondVisibility(
                "Window.IsActive(%d)" % self.LISTS_WINDOW_ID):
            return
        try:
            sel = int(xbmc.getInfoLabel(
                "Container(50).ListItem.Property(idx)") or 0)
        except ValueError:
            sel = 0
        if sel:
            self._lists_sel = sel
        if self._lists_sel != self._lists_sel_pub:
            self._list_items_publish(self._lists_sel)

    def _lists_worker(self, cmd):
        """<summary>Dispatch one list_command on the dialog thread.</summary>
        <param name="cmd">The command string, see update_lists.</param>"""
        self._lists_load()
        if cmd in ("add_last", "add_pick"):
            self._lists_add(pick=(cmd == "add_pick"))
        elif cmd == "new":
            self._lists_new()
        elif cmd == "rename":
            self._lists_rename()
        elif cmd == "delete":
            self._lists_delete()
        elif cmd in ("port", "port_shuffle"):
            self._lists_port(shuffle=(cmd == "port_shuffle"))
        elif cmd == "port_time":
            self._lists_port_time()
        elif cmd.startswith("item:"):
            self._lists_item_menu(cmd[5:])
        elif cmd == "save_queue":
            self._lists_save_queue()
        else:
            _dlog("list command ignored: %r" % cmd)

    def _lists_selected(self):
        """<summary>The list the Lists screen currently has selected.</summary>
        <returns>(index, list dict) with index 1-based, or (0, None).</returns>"""
        with self._lists_lock:
            lists = self._lists or []
            idx = self._lists_sel
            if 0 < idx <= len(lists):
                return idx, lists[idx - 1]
        return 0, None

    @staticmethod
    def _lists_notify(text, error=False):
        """
        <summary>
        Show a short toast from the Lists feature.
        </summary>
        <param name="text">Message.</param>
        <param name="error">True for the error icon, otherwise the info icon.</param>
        """
        xbmcgui.Dialog().notification(
            _L(31024), text,
            xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO,
            3500)

    def _lists_ask_name(self, heading, default=""):
        """<summary>Keyboard prompt for a list name that is not empty and not
        already taken.</summary>
        <returns>The trimmed name, or "" when cancelled or rejected.</returns>"""
        name = xbmcgui.Dialog().input(heading, default,
                                      type=xbmcgui.INPUT_ALPHANUM).strip()
        if not name:
            return ""
        with self._lists_lock:
            taken = any(l["name"].lower() == name.lower()
                        and l["name"] != default for l in self._lists or [])
        if taken:
            self._lists_notify(_L(31336) % name, True)
            return ""
        return name

    def _lists_capture_item(self):
        """<summary>Read and clear the list_item_* Home properties the
        context button wrote.</summary>
        <returns>A clean item record or None.</returns>"""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        raw = {}
        for key in self.LIST_ITEM_PROPS:
            prop = "list_item_" + key
            raw[key] = win.getProperty(prop)
            win.clearProperty(prop)
        return self._list_item_clean(raw)

    def _lists_create(self, name, items=None):
        """<summary>Append a new list and save.</summary>
        <returns>The new list's 1-based index.</returns>"""
        with self._lists_lock:
            self._lists.append({"name": name, "items": list(items or []),
                                "fill": 0})
            idx = len(self._lists)
            self._lists_last = name
        self._lists_save()
        return idx

    def _lists_add(self, pick):
        """<summary>Add the captured item to the last-used list, or to a
        list the user picks (with "New list" as the final choice).</summary>
        <param name="pick">True to always show the picker.</param>"""
        item = self._lists_capture_item()
        if item is None:
            self._lists_notify(_L(31337), True)
            return
        with self._lists_lock:
            lists = list(self._lists)
            last = self._lists_last
        target = None
        if not pick and last:
            target = next((l for l in lists if l["name"] == last), None)
        if target is None:
            names = [l["name"] for l in lists] + [_L(31464)]
            choice = xbmcgui.Dialog().select(_L(31050), names)
            if choice < 0:
                return
            if choice == len(lists):
                name = self._lists_ask_name(_L(31338))
                if not name:
                    return
                self._lists_create(name)
                with self._lists_lock:
                    target = self._lists[-1]
            else:
                target = lists[choice]
        with self._lists_lock:
            if any(self._list_item_same(item, it) for it in target["items"]):
                dup = True
            else:
                dup = False
                if len(target["items"]) >= self.LIST_ITEMS_MAX:
                    self._lists_notify(_L(31339) % (
                        target["name"], self.LIST_ITEMS_MAX), True)
                    return
                target["items"].append(item)
            self._lists_last = target["name"]
        self._lists_save()
        if dup:
            self._lists_notify(_L(31340) % (item["label"], target["name"]))
        else:
            self._lists_notify(_L(31341) % target["name"])

    def _lists_new(self):
        """
        <summary>
        Prompt for a name and create a new list.
        </summary>
        """
        name = self._lists_ask_name(_L(31338))
        if name:
            self._lists_create(name)

    def _lists_rename(self):
        """
        <summary>
        Prompt for a new name for the selected list and save it.
        </summary>
        <remarks>
        A cancelled prompt or an unchanged name is a no-op. The last used list
        name follows the rename so porting keeps targeting the same list.
        </remarks>
        """
        idx, lst = self._lists_selected()
        if not lst:
            return
        old = lst["name"]
        name = self._lists_ask_name(_L(31342), old)
        if not name or name == old:
            return
        with self._lists_lock:
            lst["name"] = name
            if self._lists_last == old:
                self._lists_last = name
        self._lists_save()

    def _lists_delete(self):
        """<summary>Remove the selected list after a yes/no confirm.</summary>"""
        idx, lst = self._lists_selected()
        if not lst:
            return
        if not xbmcgui.Dialog().yesno(
                _L(31343), _L(31344) % (
                    lst["name"], len(lst["items"]))):
            return
        with self._lists_lock:
            self._lists.pop(idx - 1)
            if self._lists_last == lst["name"]:
                self._lists_last = ""
            self._lists_sel = min(idx, len(self._lists))
        self._lists_save()

    @classmethod
    def _list_item_spec(cls, it):
        """<summary>The JSON-RPC Playlist.Item / Player.Open item for a
        record: by library id when it has one, else by path.</summary>"""
        key = cls.LIST_DBID_KEYS.get(it["dbtype"])
        if it["dbid"] and key:
            return {key: it["dbid"]}
        return {"file": it["file"]}

    def _lists_port(self, shuffle):
        """<summary>Copy the whole selected list into Kodi's queue(s) and
        start it playing.</summary>
        <param name="shuffle">Randomise the order before queueing.</param>"""
        idx, lst = self._lists_selected()
        if not lst:
            return
        with self._lists_lock:
            items = list(lst["items"])
        if not items:
            self._lists_notify(_L(31345) % lst["name"], True)
            return
        if shuffle:
            random.shuffle(items)
        self._lists_queue(lst, items, _L(31355) if shuffle else _L(31356))

    def _lists_port_time(self):
        """<summary>Queue a random pick from the selected list, enough of it
        to fill a length of time the user chooses.</summary>
        <remarks>The length is remembered per list (the "fill" key in
        lists.json) so the same list offers the same answer next time. It
        is asked as HH:MM through the same numeric dialog the background
        schedule uses, which gives half hours for free and is one keypad
        on a remote.

        "At least" is meant literally: the item that takes the running
        total past the target is included rather than dropped, so an
        evening set to three hours runs slightly over rather than short.
        A list whose whole content is shorter than the target is queued
        in full, and the notification reports what was actually
        achieved.</remarks>"""
        idx, lst = self._lists_selected()
        if not lst:
            return
        with self._lists_lock:
            items = list(lst["items"])
            current = int(lst.get("fill") or self.LIST_FILL_DEFAULT)
        if not items:
            self._lists_notify(_L(31345) % lst["name"], True)
            return
        answer = xbmcgui.Dialog().numeric(2, _L(31379),
                                          self._fmt_hhmm(current))
        minutes = self._parse_hhmm(answer)
        if not minutes:
            return  # cancelled, or 00:00 which would queue nothing
        with self._lists_lock:
            lst["fill"] = minutes
        self._lists_save()
        picked, total = self._lists_pick_for_duration(items, minutes * 60)
        _dlog("list fill: %s target %s picked %d of %d, total %s" % (
            lst["name"], self._fmt_hhmm(minutes), len(picked), len(items),
            self._fmt_secs(total)))
        self._lists_queue(lst, picked, _L(31380),
                          extra=[self._fmt_secs(total)] if total else None)

    @staticmethod
    def _lists_pick_for_duration(items, target_secs):
        """<summary>A random selection from *items* lasting at least
        *target_secs*, or all of them if the list is shorter.</summary>
        <param name="items">The list's items, not modified.</param>
        <param name="target_secs">Length to reach, in seconds.</param>
        <returns>(picked items, their total duration in seconds).</returns>
        <remarks>Items Kodi has no duration for count as zero. They are
        still queued when drawn, but they cannot advance the total, so a
        list made entirely of them ends up queued in full rather than
        spinning. The walk is over a finite shuffled copy either way.</remarks>"""
        pool = list(items)
        random.shuffle(pool)
        picked, total = [], 0
        for it in pool:
            if total >= target_secs:
                break
            picked.append(it)
            total += it["duration"]
        return picked, total

    def _lists_queue(self, lst, items, verb, extra=None):
        """<summary>Put *items* into Kodi's queue(s) and start playing.</summary>
        <param name="lst">The list they came from, for the notification.</param>
        <param name="items">Already ordered and filtered; queued as given.</param>
        <param name="verb">Localised word for what happened, e.g. Ported.</param>
        <param name="extra">Extra phrases to append to the notification.</param>
        <remarks>Skin.String(list_port_clear) = clear / keep decides whether
        the existing queue goes first; unset means ask, with a Cancel. Video
        items go to the video queue and songs to the music queue; the video
        queue starts if it got anything, else the music one. With "keep"
        and something already playing, the items are only appended.</remarks>"""
        if not items:
            return
        mode = xbmc.getInfoLabel("Skin.String(list_port_clear)")
        if mode not in ("clear", "keep"):
            answer = xbmcgui.Dialog().yesnocustom(
                _L(31346) % lst["name"],
                _L(31347),
                customlabel=_L(31348), nolabel=_L(31349), yeslabel=_L(31350))
            if answer in (-1, 2):
                return
            mode = "clear" if answer == 1 else "keep"
        groups = {"video": [it for it in items if it["kind"] == "video"],
                  "music": [it for it in items if it["kind"] == "music"]}
        was_playing = xbmc.getCondVisibility("Player.HasMedia")
        if mode == "clear":
            if was_playing:
                xbmc.executebuiltin("PlayerControl(Stop)")
                time.sleep(0.5)
                was_playing = False
            for kind, group in groups.items():
                if group:
                    _jsonrpc("Playlist.Clear",
                             {"playlistid": self.LIST_PLAYLIST_IDS[kind]})
        start = {}
        for kind, group in groups.items():
            if not group:
                continue
            pid = self.LIST_PLAYLIST_IDS[kind]
            resp = _jsonrpc("Playlist.GetProperties",
                            {"playlistid": pid, "properties": ["size"]})
            start[kind] = int(((resp.get("result") or {}).get("size")) or 0)
            specs = [self._list_item_spec(it) for it in group]
            for chunk in range(0, len(specs), 50):
                _jsonrpc("Playlist.Add",
                         {"playlistid": pid, "item": specs[chunk:chunk + 50]})
        if not was_playing:
            kind = "video" if groups["video"] else "music"
            _jsonrpc("Player.Open", {"item": {
                "playlistid": self.LIST_PLAYLIST_IDS[kind],
                "position": start.get(kind, 0)}})
        counts = []
        if groups["video"]:
            counts.append((_L(31351) if len(groups["video"]) == 1
                           else _L(31352)) % len(groups["video"]))
        if groups["music"]:
            counts.append((_L(31353) if len(groups["music"]) == 1
                           else _L(31354)) % len(groups["music"]))
        counts.extend(extra or [])
        self._lists_notify(_L(31357) % (verb, lst["name"], ", ".join(counts)))
        _dlog("list queued: %s mode=%s %s" % (lst["name"], mode, counts))

    def _lists_item_menu(self, row):
        """<summary>Action menu for one row of the selected list: play it
        now, move it up or down, or remove it.</summary>
        <param name="row">1-based row number as a string.</param>"""
        try:
            pos = int(row) - 1
        except ValueError:
            return
        idx, lst = self._lists_selected()
        if not lst or not (0 <= pos < len(lst["items"])):
            return
        it = lst["items"][pos]
        choice = xbmcgui.Dialog().contextmenu(
            [_L(31358), _L(31359), _L(31360), _L(31361)])
        _dlog("list item menu: row %d of %s -> choice %d" % (
            pos + 1, lst["name"], choice))
        if choice == 0:
            _jsonrpc("Player.Open", {"item": self._list_item_spec(it)})
            return
        if choice < 0:
            return
        with self._lists_lock:
            items = lst["items"]
            if choice == 1 and pos > 0:
                items[pos - 1], items[pos] = items[pos], items[pos - 1]
            elif choice == 2 and pos < len(items) - 1:
                items[pos + 1], items[pos] = items[pos], items[pos + 1]
            elif choice == 3:
                items.pop(pos)
            else:
                return
        self._lists_save()
        # Keep the cursor on the row the item moved to; a removal leaves it
        # where the next item slid into.
        target = {1: pos, 2: pos + 2, 3: pos + 1}[choice]
        target = max(1, min(target, len(lst["items"])))
        if target:
            xbmc.executebuiltin("SetFocus(51,%d,absolute)" % (target - 1))

    def _lists_save_queue(self):
        """<summary>Turn the queue behind the open queue window into a new
        list.</summary>
        <remarks>Kodi's Playlist.GetItems rows carry id/type for library
        items and file/label for everything else, which is all a record
        needs; runtime is seconds (video) or seconds (music duration).</remarks>"""
        if xbmc.getCondVisibility("Window.IsActive(musicplaylist)"):
            kind = "music"
        else:
            kind = "video"
        pid = self.LIST_PLAYLIST_IDS[kind]
        resp = _jsonrpc("Playlist.GetItems", {
            "playlistid": pid,
            "properties": ["file", "title", "thumbnail", "runtime", "duration",
                           "showtitle", "season", "episode", "artist", "year"]})
        rows = ((resp.get("result") or {}).get("items")) or []
        items = []
        for row in rows:
            artist = row.get("artist") or ""
            if isinstance(artist, list):
                artist = ", ".join(artist)
            it = self._list_item_clean({
                "label": row.get("title") or row.get("label") or "",
                "file": row.get("file") or "",
                "dbtype": row.get("type") or "",
                "dbid": row.get("id") or 0,
                "thumb": row.get("thumbnail") or "",
                "duration": row.get("runtime") or row.get("duration") or 0,
                "show": row.get("showtitle") or "",
                "season": row.get("season") or "",
                "episode": row.get("episode") or "",
                "artist": artist,
                "year": row.get("year") or "",
                "kind": kind,
            })
            if it and not any(self._list_item_same(it, x) for x in items):
                items.append(it)
        if not items:
            self._lists_notify(_L(31362), True)
            return
        name = self._lists_ask_name(_L(31363))
        if not name:
            return
        self._lists_create(name, items[:self.LIST_ITEMS_MAX])
        self._lists_notify((_L(31364) if len(items) == 1 else _L(31365)) % (
            len(items), name))

    # ---- Video nav: genre label + per-content default sort ----------------
    #
    # Both of these exist because the skin used to remember what the user
    # CLICKED rather than read what the container actually IS. Skin.String
    # (genre_active) was written by the genre picker and cleared on window
    # load, so any route that didn't go through those two points left the
    # label lying: navigate Movies -> pick a genre -> Back -> TV -> Movies
    # and the side menu still claimed a genre (or claimed "All" while the
    # list was still narrowed), because plain directory navigation is not
    # something the skin is ever told about.
    #
    # The fix is to stop storing an intention and start reporting the truth:
    # every tick, derive the genre from Container.FolderPath and publish it
    # as Window(home).Property(genre_active), which $VAR[GenreFilterLabel]
    # renders. Nothing can go stale because nothing is remembered.

    def update_video_nav_state(self):
        """
        <summary>
        Publish the real genre filter and apply the default sort.
        </summary>
        <remarks>
        Runs on the fast tick while a video window is up. Two jobs:

        * ``genre_active`` (Home window property) is recomputed from
          ``Container.FolderPath`` every tick, so the side menu's Genre label
          always matches the node actually on screen.
        * When the container moves to a new path, the user's default sort for
          that content type (Skin.String(default_sort_movies) /
          (default_sort_tvshows)) is applied a beat later, so landing on
          Movies or TV Shows always gives the same order however you got
          there.
        </remarks>
        """
        if not xbmc.getCondVisibility("Window.IsActive(videos)"):
            if self._nav_path is not None:
                self._nav_path = None
                self._nav_genre = None
                self._nav_sort_due = 0.0
                _set_home_property("genre_active", "")
            return

        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        genre = self._genre_for_path(path)
        if genre != self._nav_genre:
            self._nav_genre = genre
            _set_home_property("genre_active", genre)

        if path != self._nav_path:
            self._nav_path = path
            # Deferred: Container.Content() lags FolderPath by a frame or two
            # and a sort aimed at the wrong content type is silently dropped.
            self._nav_sort_due = time.time() + self.NAV_SORT_DELAY
        elif self._nav_sort_due and time.time() >= self._nav_sort_due:
            self._nav_sort_due = 0.0
            self._apply_default_sort()

    def _genre_for_path(self, path):
        """
        <summary>
        Genre name for a videodb genre node, "" for anything else.
        </summary>
        <remarks>
        The id -> name map comes from VideoLibrary.GetGenres (fetched once per
        media type on a daemon thread, because a sleeping MySQL box must not
        stall the loop). Until it lands, Container.FolderName is used: Kodi
        labels a genre node with the genre, so it is right in practice, and
        the next tick replaces it with the authoritative value anyway.
        </remarks>
        """
        match = self.GENRE_PATH_RE.match(path or "")
        if not match:
            # An age filtered node carries its genre inside the playlist.
            return self._age_rule_from_path(path, "genre")
        dbtype = "movie" if match.group(1).lower() == "movies" else "tvshow"
        genre_id = int(match.group(2))
        name = self._genre_names.get((dbtype, genre_id))
        if name:
            return name
        self._start_genre_fetch(dbtype)
        return (xbmc.getInfoLabel("Container.FolderName") or "").strip()

    def _start_genre_fetch(self, dbtype):
        """
        <summary>
        Pull the genre list for *dbtype* once, off the main loop.
        </summary>
        """
        if dbtype in self._genre_fetched:
            return
        if self._genre_thread is not None and self._genre_thread.is_alive():
            return
        self._genre_fetched.add(dbtype)
        self._genre_thread = threading.Thread(
            target=self._genre_fetch_worker, args=(dbtype,),
            name="functional-genres", daemon=True)
        self._genre_thread.start()

    def _genre_fetch_worker(self, dbtype):
        """
        <summary>
        Thread body: cache (dbtype, genreid) -> label for genre labelling.
        </summary>
        """
        try:
            resp = _jsonrpc("VideoLibrary.GetGenres", {"type": dbtype})
            rows = ((resp or {}).get("result") or {}).get("genres") or []
            for row in rows:
                gid = row.get("genreid")
                label = (row.get("label") or "").strip()
                if gid is not None and label:
                    self._genre_names[(dbtype, int(gid))] = label
            _dlog("genres: cached {0} {1} genres".format(len(rows), dbtype))
        except Exception:  # noqa: BLE001
            # Allow a later retry rather than being stuck on FolderName.
            self._genre_fetched.discard(dbtype)
            _dlog("genre fetch failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    def _apply_default_sort(self):
        """
        <summary>
        Force the user's default sort for the content now in the container.
        </summary>
        <remarks>
        No-op unless the container holds movies or TV shows and the matching
        Skin.String names a sort we know. Direction goes through the existing
        sort_want channel (see update_sort_direction) rather than being read
        and toggled here, for the same stale-state reason.
        </remarks>
        """
        if xbmc.getCondVisibility("Container.Content(movies)"):
            key = "movies"
        elif xbmc.getCondVisibility("Container.Content(tvshows)"):
            key = "tvshows"
        else:
            return
        want = xbmc.getInfoLabel(
            "Skin.String(default_sort_{0})".format(key)).strip().lower()
        if want not in self.SORT_METHOD_IDS:
            return  # unset or "kodi" = leave Kodi's own remembered sort alone
        direction = xbmc.getInfoLabel(
            "Skin.String(default_sort_{0}_dir)".format(key)).strip().lower()
        if direction not in ("asc", "desc"):
            direction = self.SORT_NATURAL_DIR[want]
        xbmc.executebuiltin("Container.SetSortMethod({0})".format(
            self.SORT_METHOD_IDS[want]))
        # Keep the fast-scroll badge's idea of the sort in step, it is the
        # other thing that used to drift once navigation got involved.
        _set_skin_string("sort_active", want)
        _set_skin_string("sort_want", direction)
        _dlog("nav: default sort for {0} = {1} {2}".format(key, want, direction))

    # ---- Settings backup and restore --------------------------------------
    #
    # Kodi keeps skin settings in one file, settings.xml in the skin's
    # addon_data folder, and nothing in Kodi backs it up: a profile wipe, a
    # bad restore or a fat-fingered "reset skin settings" takes the lot.
    #
    # The snapshot is a straight copy of that file, refreshed whenever Kodi
    # writes it, so the backup keeps itself current with no user action.
    # WORTH KNOWING: Kodi decides when settings.xml is flushed to disk (it is
    # written on skin unload, and on its own schedule), so a snapshot can be
    # a little behind the live values. "Back Up Now" copies whatever is on
    # disk at that moment, it cannot force Kodi to flush first.
    #
    # Restore does NOT copy the file back. Kodi holds skin settings in memory
    # and writes them out later, so an overwritten file would simply be
    # clobbered by the running skin. Instead the backup is parsed and each
    # setting re-applied through the Skin.SetString / Skin.SetBool builtins,
    # which is what the running skin actually reads.

    # Never restored: transient UI state (menus that happen to be open) and
    # the full-buffer restore strings, which describe a playback that ended
    # long ago and would have the service "restore" stale cache settings.
    BACKUP_SKIP_KEYS = frozenset((
        "settings_reload", "settings_category",
        "settings_backup_when",  # describes the snapshot, not the settings
        "filter_menu_open", "genre_menu_open", "sort_menu_open",
        "view_menu_open", "left_menu_open", "layout_adjust",
        "genre_active", "sort_active", "sort_want",
        "cache_mem_restore", "cache_mode_restore", "cache_rf_restore",
        # Readouts the service publishes, not choices the user made. Writing
        # a backup's library counts back would put last month's numbers on
        # the Home screen until the next stats refresh caught up.
        "cache_mem_label", "cache_rf_label", "cache_mode_label",
    ))
    # Same reasoning, by prefix: stat_movies_total, stat_episodes_total, ...
    BACKUP_SKIP_PREFIXES = ("stat_",)
    # Command channels, by suffix. Every channel the skin sets and this
    # service consumes ends in _command or _run (bg_command, cast_run,
    # sleep_command and so on). They were once listed by name above and
    # the list drifted: it named cast_command, which nothing reads, and
    # missed every channel added after it. Kodi flushes settings.xml on
    # its own schedule, so a snapshot can hold a channel set a moment
    # before the flush, and a restore that wrote it back would run that
    # command on the next tick. Matching the suffix also covers channels
    # that do not exist yet.
    BACKUP_SKIP_SUFFIXES = ("_command", "_run")

    def update_settings_backup(self):
        """
        <summary>
        Keep the rolling snapshot of settings.xml current.
        </summary>
        <remarks>
        Slow tick. Stats the file at most every BACKUP_CHECK_SECS and copies
        it only when the mtime has moved, so a quiet box does one stat every
        twenty seconds and nothing else.
        </remarks>
        """
        now = time.time()
        if (now - self._backup_last_check) < self.BACKUP_CHECK_SECS:
            return
        self._backup_last_check = now
        try:
            mtime = os.path.getmtime(xbmcvfs.translatePath(self.SETTINGS_FILE))
        except OSError:
            return  # no settings file yet: nothing to back up
        if mtime == self._backup_mtime:
            return
        self._backup_mtime = mtime
        self._start_backup(announce=False)

    def update_settings_command(self):
        """
        <summary>
        Watch Skin.String(settings_command): "backup" / "restore".
        </summary>
        <remarks>
        Both run on a daemon thread: restore puts a confirmation dialog up
        and a blocking dialog must never sit on the polling loop.
        </remarks>
        """
        cmd = self._take_command("settings_command", lower=True)
        if not cmd:
            return
        if cmd == "backup":
            self._backup_mtime = -1.0  # force the next auto-check to re-copy too
            self._start_backup(announce=True)
        elif cmd == "restore":
            self._spawn_dialog(self._restore_worker)

    def _start_backup(self, announce):
        """
        <summary>
        Copy settings.xml to the backup folder, off the main loop.
        </summary>
        <param name="announce">show a notification when done (the manual button).</param>
        <remarks>
        </remarks>
        """
        if self._backup_thread is not None and self._backup_thread.is_alive():
            return
        self._backup_thread = threading.Thread(
            target=self._backup_worker, args=(announce,),
            name="functional-backup", daemon=True)
        self._backup_thread.start()

    def _backup_path(self):
        """
        <summary>
        Full local path of the snapshot file.
        </summary>
        """
        return os.path.join(xbmcvfs.translatePath(self.BACKUP_DIR),
                            self.BACKUP_NAME)

    def _backup_worker(self, announce):
        """
        <summary>
        Thread body: copy the settings file and publish its age.
        </summary>
        """
        try:
            source = xbmcvfs.translatePath(self.SETTINGS_FILE)
            with open(source, "rb") as fh:
                data = fh.read()
            if not data.strip():
                _dlog("backup: settings.xml is empty, not overwriting the "
                      "snapshot", xbmc.LOGWARNING)
                return
            if not announce and self._looks_like_a_wipe(data):
                # One rolling snapshot is only a backup if the event it
                # protects against can't overwrite it. A settings reset
                # rewrites settings.xml, and the automatic snapshot would
                # cheerfully copy the wreckage over the good copy seconds
                # later. "Back Up Now" is never blocked, so a deliberate
                # cull is still one button away.
                _dlog("backup: settings.xml lost most of its entries, "
                      "keeping the previous snapshot", xbmc.LOGWARNING)
                return
            folder = xbmcvfs.translatePath(self.BACKUP_DIR)
            if not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            # Write beside the target and rename: a snapshot interrupted
            # half-written is worse than no snapshot at all.
            target = self._backup_path()
            temp = target + ".part"
            with open(temp, "wb") as fh:
                fh.write(data)
            os.replace(temp, target)
            self._publish_backup_age()
            _dlog("backup: snapshot written, {0} bytes".format(len(data)))
            if announce:
                xbmcgui.Dialog().notification(
                    _L(31000), _L(31366),
                    xbmcgui.NOTIFICATION_INFO, 3000)
        except Exception:  # noqa: BLE001
            _dlog("backup failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            if announce:
                xbmcgui.Dialog().notification(
                    _L(31000), _L(31367),
                    xbmcgui.NOTIFICATION_WARNING, 4000)

    # Below this many stored settings there is nothing worth protecting, and
    # the ratio test would fire on a brand-new profile legitimately growing.
    WIPE_GUARD_MIN = 8

    def _looks_like_a_wipe(self, data):
        """
        <summary>
        True if *data* has lost most of the settings the snapshot holds.
        </summary>
        <param name="data">the raw bytes just read from settings.xml.</param>
        <remarks>
        A crude count of <setting entries, which is all this needs to be: the
        signature of a reset is "was 60, is now 2", not "was 60, is now 58".
        </remarks>
        """
        try:
            with open(self._backup_path(), "rb") as fh:
                stored = fh.read().count(b"<setting ")
        except OSError:
            return False  # no snapshot yet: anything is an improvement
        if stored < self.WIPE_GUARD_MIN:
            return False
        return data.count(b"<setting ") * 2 < stored

    def _publish_backup_age(self):
        """
        <summary>
        Mirror the snapshot's timestamp into a skin string for the UI.
        </summary>
        """
        try:
            stamp = os.path.getmtime(self._backup_path())
        except OSError:
            _set_skin_string("settings_backup_when", "")
            return
        _set_skin_string("settings_backup_when",
                         time.strftime("%d/%m/%Y %H:%M", time.localtime(stamp)))

    @classmethod
    def _read_backup(cls, path):
        """
        <summary>
        Parse a snapshot into [(key, type, value), ...], skipping the
        transient keys in BACKUP_SKIP_KEYS, BACKUP_SKIP_PREFIXES and
        BACKUP_SKIP_SUFFIXES.
        </summary>
        """
        tree = ET.parse(path)
        out = []
        for node in tree.getroot().findall("setting"):
            key = (node.get("id") or "").strip()
            if (not key or key in cls.BACKUP_SKIP_KEYS
                    or key.startswith(cls.BACKUP_SKIP_PREFIXES)
                    or key.endswith(cls.BACKUP_SKIP_SUFFIXES)):
                continue
            out.append((key, (node.get("type") or "string").strip(),
                        node.text or ""))
        return out

    def _restore_worker(self):
        """
        <summary>
        Confirm, then re-apply every setting in the snapshot.
        </summary>
        <remarks>
        Applied through the builtins rather than by copying the file back:
        the running skin holds its settings in memory and would overwrite a
        swapped file on its next save.
        </remarks>
        """
        path = self._backup_path()
        if not os.path.isfile(path):
            xbmcgui.Dialog().ok(_L(31000),
                                _L(31368))
            return
        try:
            entries = self._read_backup(path)
        except Exception:  # noqa: BLE001
            _dlog("restore: unreadable backup:\n{0}".format(
                traceback.format_exc()), xbmc.LOGERROR)
            xbmcgui.Dialog().ok(_L(31000),
                                _L(31369))
            return
        if not entries:
            xbmcgui.Dialog().ok(_L(31000),
                                _L(31370))
            return
        when = xbmc.getInfoLabel("Skin.String(settings_backup_when)")
        if not xbmcgui.Dialog().yesno(
                _L(31371),
                _L(31372).format(
                    len(entries), when or _L(31373))):
            return
        for key, kind, value in entries:
            value = value.strip()
            if kind == "bool":
                if value.lower() == "true":
                    xbmc.executebuiltin("Skin.SetBool({0})".format(key))
                else:
                    xbmc.executebuiltin("Skin.Reset({0})".format(key))
            elif value:
                _set_skin_string(key, value)
            else:
                xbmc.executebuiltin("Skin.Reset({0})".format(key))
        _dlog("restore: re-applied {0} settings from {1}".format(
            len(entries), path))
        xbmcgui.Dialog().notification(
            _L(31000), _L(31374).format(len(entries)),
            xbmcgui.NOTIFICATION_INFO, 3000)
        # The reload is what makes load-time includes (OSD position, colours)
        # pick the restored values up.
        xbmc.sleep(500)
        xbmc.executebuiltin("ReloadSkin()")

    def update_sort_direction(self):
        """
        <summary>
        Apply a deferred sort-direction request from the library side menu.
        </summary>
        <remarks>
        The menu buttons can't reliably force a direction inline: reading
        Container.SortDirection in the same click as SetSortMethod sees stale
        state, so a conditional toggle sometimes lands the wrong way (e.g.
        switching from Date Added back to Title left it Z->A). Instead the
        button sets Skin.String(sort_want)=asc|desc and we honour it here, a
        tick later, once the container's new sort has settled, so the
        direction read is accurate.
        </remarks>
        """
        want = xbmc.getInfoLabel("Skin.String(sort_want)").strip().lower()
        if not want:
            return
        # Only meddle while the video library window is up, so we never nudge
        # some other window's container.
        if not xbmc.getCondVisibility("Window.IsVisible(videos)"):
            xbmc.executebuiltin("Skin.Reset(sort_want)")
            return
        if want == "desc" and xbmc.getCondVisibility("Container.SortDirection(ascending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        elif want == "asc" and xbmc.getCondVisibility("Container.SortDirection(descending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        xbmc.executebuiltin("Skin.Reset(sort_want)")

    # ---- Layout command handler ----------------------------------------

    @staticmethod
    def _safe_int(text, default):
        """
        <summary>
        Parse an integer leniently.
        </summary>
        <param name="text">Anything; it is stringified and stripped first.</param>
        <param name="default">Returned when text is not an integer.</param>
        <returns>The integer, or default.</returns>
        """
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

    def normalize_clearance(self):
        """
        <summary>
        Keep the clearance strings on the 10px grid, 0..LAYOUT_MAX_PX.
        The "tap to type" button (Skin.SetNumeric) accepts any integer, but
        ClearanceAnimations only has a slide per multiple of LAYOUT_STEP_PX:
        an off-grid value matches no animation and the panel snaps to 0, and
        the +/- buttons would then step 145 -> 155 -> ... forever. Runs on the
        slow tick; only writes when something actually needs changing.
        </summary>
        """
        for key in ("infobar_clearance_top", "infobar_clearance_bottom"):
            raw = xbmc.getInfoLabel("Skin.String({0})".format(key))
            if not raw:
                continue  # _bootstrap_layout_defaults seeds empties
            value = self._safe_int(raw, None)
            if value is None:
                fixed = self.LAYOUT_DEFAULT_PX
            else:
                step = self.LAYOUT_STEP_PX
                fixed = int(round(value / float(step))) * step
                fixed = max(0, min(self.LAYOUT_MAX_PX, fixed))
            if str(fixed) != raw.strip():
                xbmc.executebuiltin("Skin.SetString({0},{1})".format(key, fixed))
                _dlog("layout: {0} {1!r} -> {2}".format(key, raw, fixed))

    def update_layout_command(self):
        """
        <summary>
        Apply ± LAYOUT_STEP_PX to whichever clearance string the +/- buttons
        flagged via Skin.String(layout_command). Clamped to 0..LAYOUT_MAX_PX.
        </summary>
        """
        cmd = self._take_command("layout_command")
        if not cmd:
            return

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
            # ClearanceAnimations include applied to the wrapping group:
            # one conditional slide animation per discrete value activates
            # as soon as String.IsEqual matches. No window reload needed.

    # ---- Sleep timer ----------------------------------------------------

    # Seeded into the hours-and-minutes prompt until the user has set one.
    SLEEP_DEFAULT_HHMM = "01:00"
    # How long before power off the one warning toast appears.
    SLEEP_WARN_SECS = 60

    def update_sleep_timer(self):
        """
        <summary>
        Run the sleep timer: take commands from the power menu, republish the
        countdown, and power the box down when it reaches zero.
        </summary>
        <remarks>
        Skin.String(sleep_command) is the channel, "set" or "cancel", cleared
        the moment it is read so a command cannot fire twice. "set" opens a
        blocking hours-and-minutes prompt, which must go through
        _spawn_dialog or it stalls every other handler for as long as it is
        open.

        The deadline lives in memory, not in a skin string, on purpose. A
        sleep timer means "power this box down in a while", so it has nothing
        to say once the box is off or Kodi has been restarted, and persisting
        it would resurrect a timer the user has long forgotten. The countdown
        goes out as a Home window property rather than a skin string for the
        same reason plus one more: properties are in-memory, so a value that
        changes every second never touches Kodi's settings store. A ReloadSkin
        drops the property and the next tick puts it straight back.

        Window(home).Property(sleep_remaining) being non-empty is what every
        visibility condition in the XML reads as "a timer is armed", so the
        property and the deadline are cleared together and never separately.

        _sleep_deadline is written by the dialog thread and read here. A bare
        float assignment is atomic under the GIL, and a tick that reads the
        old value simply publishes one countdown that is a quarter-second
        stale, so no lock is warranted.
        </remarks>
        """
        cmd = self._take_command("sleep_command")
        if cmd:
            if cmd == "set":
                self._spawn_dialog(self._sleep_pick)
            elif cmd == "cancel":
                self._sleep_disarm(announce=True)

        if self._sleep_deadline is None:
            return

        remaining = int(round(self._sleep_deadline - time.time()))
        if remaining <= 0:
            self._sleep_fire()
            return
        if remaining <= self.SLEEP_WARN_SECS and not self._sleep_warned:
            self._sleep_warned = True
            self._sleep_notify(_L(31429))
        label = self._fmt_countdown(remaining)
        # Four ticks a second, one new label a second: only write on change.
        if label != self._sleep_published:
            self._sleep_published = label
            _set_home_property("sleep_remaining", label)

    @staticmethod
    def _fmt_countdown(secs):
        """
        <summary>
        Seconds remaining as "1:29:58", or "29:58" once under the hour.
        </summary>
        <remarks>
        Hours are unpadded and minutes are padded, so the field neither
        jitters in width within an hour nor reads as a clock time. Seconds
        are always shown: a sleep timer that ticks is a sleep timer the
        viewer can see is alive.
        </remarks>
        """
        secs = max(0, int(secs))
        hours, rest = divmod(secs, 3600)
        minutes, seconds = divmod(rest, 60)
        if hours:
            return "{0}:{1:02d}:{2:02d}".format(hours, minutes, seconds)
        return "{0}:{1:02d}".format(minutes, seconds)

    def _sleep_pick(self):
        """
        <summary>
        Ask for hours and minutes, seeded with the last value used, and arm
        the timer.
        </summary>
        <remarks>
        Kodi's numeric time dialog silently ignores a default it cannot parse
        and seeds itself from the clock instead, so the stored value is
        validated and re-padded before it goes in: "1:30" would otherwise turn
        a remembered hour and a half into whatever the time happened to be.
        The value is stored back on every accepted prompt, which is what makes
        the dialog come up on the last duration next time.

        00:00 is treated as "cancel" rather than "power down now", because
        clearing the field is the obvious way to try to call a timer off and
        an immediate shutdown would be a nasty answer to it.
        </remarks>
        """
        current = self._get_skin("sleep_default")
        if self._parse_hhmm(current) is None:
            current = self.SLEEP_DEFAULT_HHMM
        else:
            current = self._fmt_hhmm(self._parse_hhmm(current))
        result = xbmcgui.Dialog().numeric(2, _L(31426), current)
        minutes = self._parse_hhmm(result)
        if minutes is None:
            return  # cancelled or garbage: leave any running timer alone
        if minutes <= 0:
            self._sleep_disarm(announce=True)
            return
        _set_skin_string("sleep_default", self._fmt_hhmm(minutes))
        self._sleep_warned = minutes * 60 <= self.SLEEP_WARN_SECS
        self._sleep_published = self._fmt_countdown(minutes * 60)
        _set_home_property("sleep_remaining", self._sleep_published)
        self._sleep_deadline = time.time() + minutes * 60
        _dlog("sleep timer: armed for {0}".format(self._fmt_hhmm(minutes)))
        self._sleep_notify(_L(31427).format(self._fmt_hhmm(minutes)))

    def _sleep_disarm(self, announce=False):
        """
        <summary>
        Stop any running timer and clear the countdown.
        </summary>
        <param name="announce">True to toast, but only if a timer was actually
        running, so "cancel" on an idle skin stays silent.</param>
        """
        was_armed = self._sleep_deadline is not None
        self._sleep_deadline = None
        self._sleep_warned = False
        self._sleep_published = ""
        _set_home_property("sleep_remaining", "")
        if was_armed:
            _dlog("sleep timer: cancelled")
            if announce:
                self._sleep_notify(_L(31428))

    def _sleep_fire(self):
        """
        <summary>
        The timer has run out: stop playback, then power the box down.
        </summary>
        <remarks>
        Disarmed first, so a Powerdown that the platform refuses (no
        permission, an inhibitor holding it off) leaves a stopped player and
        an idle skin rather than a handler that tries again every quarter
        second. Playback is stopped before the shutdown builtin so the
        resume point is written while Kodi is still up.
        </remarks>
        """
        self._sleep_disarm()
        _dlog("sleep timer: elapsed, stopping playback and powering down")
        try:
            player = xbmc.Player()
            if player.isPlaying():
                player.stop()
        except Exception:  # noqa: BLE001
            _dlog("sleep timer: stopping playback failed:\n{0}".format(
                traceback.format_exc()), xbmc.LOGERROR)
        xbmc.executebuiltin("Powerdown")

    @staticmethod
    def _sleep_notify(text):
        """
        <summary>
        Short toast from the sleep timer, under the timer's own heading.
        </summary>
        """
        xbmcgui.Dialog().notification(_L(31424), text,
                                      xbmcgui.NOTIFICATION_INFO, 3500)

    # ---- Background command handler -------------------------------------

    # bg_genre_type → the media types VideoLibrary.GetGenres understands
    _GENRE_QUERY_TYPES = {
        "movies": ("movie",),
        "tvshows": ("tvshow",),
        "both": ("movie", "tvshow"),
    }

    def update_bg_command(self):
        """
        <summary>
        Watch Skin.String(bg_command). Commands set by the Background
        section of skin settings that need Python: "pick_genre" (skins can't
        enumerate library genres) and "pick_time" (numeric time dialog for a
        schedule slot's start time).
        </summary>
        """
        cmd = self._take_command("bg_command")
        if not cmd:
            return

        worker = {"pick_genre": self._pick_genre,
                  "pick_time": self._pick_time}.get(cmd)
        if worker is None:
            return
        self._spawn_dialog(worker)

    # ---- Random pick command --------------------------------------------

    # Container.Content values that mean "the TV side of the library".
    _RANDOM_TV_CONTENT = ("tvshows", "seasons", "episodes")

    def update_random_command(self):
        """
        <summary>
        Watch Skin.String(random_command): play one random title from the
        library node the video window is showing.
        </summary>
        <remarks>
        Values are "play_movies", "play_tvshows" (set by the side menu with
        mutually exclusive onclick conditions, so the content type is fixed
        at click time) or plain "play", which reads Container.Content on
        this tick instead. The genre comes from Container.FolderPath through
        the same _genre_for_path the Genre label uses, so the pick matches
        what the screen says; with no genre node the whole library type is
        the pool. The string is cleared before anything else so it cannot
        re-fire on the next tick, and the query runs on a daemon thread
        because a sleeping database must not stall the loop.
        </remarks>
        """
        cmd = self._take_command("random_command", lower=True)
        if not cmd:
            return
        if cmd not in ("play", "play_movies", "play_tvshows"):
            return
        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        if cmd == "play_tvshows":
            kind = "tvshows"
        elif cmd == "play_movies":
            kind = "movies"
        else:
            kind = self._random_kind(path)
        genre = self._genre_for_path(path)
        if self._random_thread is not None and self._random_thread.is_alive():
            return  # a pick is already on its way
        self._random_thread = threading.Thread(
            target=self._random_pick_worker, args=(kind, genre),
            name="functional-random", daemon=True)
        self._random_thread.start()

    def _random_kind(self, path):
        """
        <summary>
        "tvshows" or "movies" for the node the container is showing.
        </summary>
        <param name="path">Container.FolderPath, used when Container.Content is unset.</param>
        <returns>"tvshows" for a show, season or episode node, otherwise "movies".</returns>
        """
        for content in self._RANDOM_TV_CONTENT:
            if xbmc.getCondVisibility("Container.Content({0})".format(content)):
                return "tvshows"
        if path.lower().startswith("videodb://tvshows"):
            return "tvshows"
        return "movies"

    def _random_pick_worker(self, kind, genre):
        """
        <summary>
        Thread body: fetch one random title, start it, say what was picked.
        </summary>
        <param name="kind">"movies" or "tvshows".</param>
        <param name="genre">Genre name to restrict to, empty for the whole library type.</param>
        <remarks>
        The TV side picks a random episode rather than a random show, since
        a show is not something Kodi can play. Nothing found (an empty genre,
        a library with no episodes) is a toast, never an exception.
        </remarks>
        """
        try:
            pick = self._fetch_random_pick(kind, genre)
            if pick is None:
                _dlog("random pick: nothing for {0} genre {1!r}".format(kind, genre))
                xbmcgui.Dialog().notification(
                    _L(31000), _L(31396), xbmcgui.NOTIFICATION_INFO, 3500)
                return
            id_key, db_id, label = pick
            _dlog("random pick: {0} {1} -> {2!r}".format(id_key, db_id, label))
            _jsonrpc("Player.Open", {"item": {id_key: db_id}})
            xbmcgui.Dialog().notification(
                _L(31000), _L(31397).format(label),
                xbmcgui.NOTIFICATION_INFO, 3500)
        except Exception:  # noqa: BLE001
            _dlog("random pick failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    @staticmethod
    def _fetch_random_pick(kind, genre):
        """
        <summary>
        One random movie or episode, optionally restricted to a genre.
        </summary>
        <param name="kind">"movies" or "tvshows".</param>
        <param name="genre">Genre name for a "genre is" filter, empty for none.</param>
        <returns>(id key, database id, display label) or None when nothing matched.</returns>
        <remarks>
        Kept separate from _fetch_genre_library / _fetch_random_library on
        purpose: those return fanart tuples for the background slideshow
        and carry no database ids, and changing their shape would ripple
        through the slideshow. This asks for exactly one row. An episode's
        genre filter matches the parent show's genres, which is what a
        genre node in the TV library means.
        </remarks>
        """
        if kind == "tvshows":
            method, rows_key, id_key = "VideoLibrary.GetEpisodes", "episodes", "episodeid"
            props = ["title", "showtitle", "season", "episode"]
        else:
            method, rows_key, id_key = "VideoLibrary.GetMovies", "movies", "movieid"
            props = ["title", "year"]
        params = {
            "limits": {"start": 0, "end": 1},
            "sort": {"order": "ascending", "method": "random"},
            "properties": props,
        }
        if genre:
            params["filter"] = {"field": "genre", "operator": "is", "value": genre}
        resp = _jsonrpc(method, params)
        rows = ((resp or {}).get("result") or {}).get(rows_key) or []
        if not rows:
            return None
        row = rows[0]
        db_id = row.get(id_key)
        if db_id is None:
            return None
        title = (row.get("title") or "").strip()
        if kind == "tvshows":
            label = "{0} S{1:02d}E{2:02d} {3}".format(
                (row.get("showtitle") or "").strip(),
                int(row.get("season") or 0), int(row.get("episode") or 0), title).strip()
        else:
            year = row.get("year") or 0
            label = "{0} ({1})".format(title, year) if year else title
        return id_key, int(db_id), label

    # ---- Age filter (library filter menu, "Older than") ------------------
    # <summary>
    # Kodi gives a skin no way to filter a library node by a computed value
    # and has no relative year rule, so "older than 20 years" is a smart
    # playlist built here with the cutoff year worked out at click time and
    # opened as a videodb node URL (videodb://movies/titles/?xsp=...), the
    # same form the Continue Watching containers use. The genre of the node
    # on screen rides along as a second rule so the two filters stack.
    # </summary>

    AGE_NODES = {
        "movies": "videodb://movies/titles/",
        "tvshows": "videodb://tvshows/titles/",
    }

    def update_age_command(self):
        """
        <summary>
        Watch Skin.String(age_command) and open the node matching
        Skin.String(age_filter); between clicks, keep age_filter equal to
        the threshold the container on screen is actually filtered by.
        Cheap enough to call every tick.
        </summary>
        <remarks>
        Values are "apply_movies" and "apply_tvshows", set by the side menu
        with mutually exclusive onclick conditions after it has cycled
        age_filter. The string is cleared before anything else so it cannot
        re-fire. With no threshold the plain titles node, or the genre's own
        node, is loaded, so "Any" really does undo the filter. The path is only
        re-read when it changes, and age_filter is only written when it
        differs, so a normal tick costs one infolabel read.
        </remarks>
        """
        cmd = self._take_command("age_command", lower=True)
        if cmd:
            if cmd not in ("apply_movies", "apply_tvshows"):
                return
            kind = cmd[6:]
            years = self._safe_int(xbmc.getInfoLabel("Skin.String(age_filter)"), 0)
            path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
            genre = self._genre_for_path(path)
            target = self._age_node(kind, years, genre)
            _dlog("age filter: {0} older than {1}y genre {2!r} -> {3}".format(
                kind, years, genre, target[:80]))
            # Container.Update rather than ActivateWindow: the video window is
            # already open, so this swaps its directory in place, which keeps
            # the filter section open with the button focused and, unlike
            # ActivateWindow, reloads the plain titles node even when the
            # container is showing that node's own xsp filtered form (Kodi
            # treated those as the same place and did nothing, so "Any"
            # never undid the filter).
            xbmc.executebuiltin("Container.Update({0})".format(target))
            self._age_last_path = None  # re-derive on the new node
            return

        if not xbmc.getCondVisibility("Window.IsActive(videos)"):
            return
        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        if path == self._age_last_path:
            return
        self._age_last_path = path
        cutoff = self._safe_int(self._age_rule_from_path(path, "year"), 0)
        want = str(time.localtime().tm_year - cutoff) if cutoff else ""
        if xbmc.getInfoLabel("Skin.String(age_filter)").strip() != want:
            _set_skin_string("age_filter", want)

    def _age_node(self, kind, years, genre):
        """
        <summary>
        Build the node to open for an age threshold and optional genre.
        </summary>
        <param name="kind">"movies" or "tvshows".</param>
        <param name="years">Threshold in years, 0 for none.</param>
        <param name="genre">Genre name to keep, "" for none.</param>
        <returns>A videodb smart playlist URL; with no threshold, the plain titles node, or the genre's own node when the genre is known so the normal Genre controls take over again.</returns>
        <remarks>
        "Older than N years" is a year strictly below the current year
        minus N, so on 2026 a threshold of 20 shows titles up to 2005.
        </remarks>
        """
        if years <= 0 and genre:
            dbtype = "movie" if kind == "movies" else "tvshow"
            for (gtype, gid), name in self._genre_names.items():
                if gtype == dbtype and name == genre:
                    return "videodb://{0}/genres/{1}/".format(kind, gid)
        rules = []
        if years > 0:
            cutoff = time.localtime().tm_year - years
            rules.append({"field": "year", "operator": "lessthan", "value": [str(cutoff)]})
        if genre:
            rules.append({"field": "genre", "operator": "is", "value": [genre]})
        if not rules:
            return self.AGE_NODES[kind]
        xsp = {"name": "age", "type": kind, "rules": {"and": rules}}
        return self.AGE_NODES[kind] + "?xsp=" + urllib.parse.quote(
            json.dumps(xsp, separators=(",", ":")))

    @staticmethod
    def _age_rule_from_path(path, field):
        """
        <summary>
        First value of one rule inside the xsp playlist a videodb URL carries.
        </summary>
        <param name="path">Container.FolderPath.</param>
        <param name="field">Rule field to look for, such as "year" or "genre".</param>
        <returns>The rule's first value, or "" when the path carries no such rule.</returns>
        """
        if "xsp=" not in (path or ""):
            return ""
        try:
            query = urllib.parse.urlparse(path).query
            raw = urllib.parse.parse_qs(query).get("xsp", [""])[0]
            rules = (json.loads(raw).get("rules") or {}).get("and") or []
        except (ValueError, TypeError, AttributeError):
            return ""
        for rule in rules:
            if isinstance(rule, dict) and rule.get("field") == field:
                values = rule.get("value") or []
                return str(values[0]) if values else ""
        return ""

    def _spawn_dialog(self, worker):
        """
        <summary>
        Run a blocking dialog off the polling loop.
        </summary>
        <remarks>
        These dialogs block until dismissed, so they must never run on the
        main loop, otherwise the slideshow, stats and ETA handlers all stall
        for as long as the picker is open. One slot for all of them, so two
        dialogs can't be stacked on top of each other either.
        </remarks>
        """
        if self._dialog_thread is not None and self._dialog_thread.is_alive():
            return
        self._dialog_thread = threading.Thread(
            target=self._dialog_worker, args=(worker,),
            name="functional-dialog", daemon=True)
        self._dialog_thread.start()

    @staticmethod
    def _dialog_worker(worker):
        """
        <summary>
        Daemon thread body for a blocking picker: run it and log any failure instead of dying.
        </summary>
        <param name="worker">Callable that opens the dialog.</param>
        """
        try:
            worker()
        except Exception:  # noqa: BLE001
            _dlog("picker dialog failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)

    def _pick_genre(self):
        """
        <summary>
        Ask the library for its genres and let the user choose one.
        </summary>
        """
        gtype = xbmc.getInfoLabel("Skin.String(bg_genre_type)") or "movies"
        genres = []
        for kodi_type in self._GENRE_QUERY_TYPES.get(gtype, ("movie",)):
            resp = _jsonrpc("VideoLibrary.GetGenres", {"type": kodi_type})
            for row in (resp.get("result", {}) or {}).get("genres", []) if resp else []:
                label = (row.get("label", "") or "").strip()
                # "both" queries two types, which overlap heavily (Drama,
                # Comedy, …), so de-dupe so the list isn't full of pairs.
                if label and label not in genres:
                    genres.append(label)
        genres.sort(key=lambda s: s.lower())

        if not genres:
            _dlog("genre picker: no genres for type {0!r}".format(gtype))
            xbmcgui.Dialog().notification(
                _L(31000), _L(31375),
                xbmcgui.NOTIFICATION_INFO, 4000)
            return

        idx = xbmcgui.Dialog().select(_L(31376), genres)
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
    def _take_command(key, lower=False):
        """
        <summary>
        Read and clear one command channel: a skin string the XML sets and
        this service consumes exactly once.
        </summary>
        <param name="key">Skin string name, such as bg_command or fav_run.</param>
        <param name="lower">Lower case the value before returning it.</param>
        <returns>The stripped value, or "" when the channel was empty.</returns>
        <remarks>
        The string is cleared before the value is handed back, so a command
        can never fire twice however long the handler takes and whatever it
        does with the value. Every channel ends in _command or _run, which
        BACKUP_SKIP_SUFFIXES relies on to keep them out of a restore. This
        used to be written out at every site; one helper means one place to
        log or validate when the next channel arrives.
        </remarks>
        """
        value = xbmc.getInfoLabel("Skin.String({0})".format(key)).strip()
        if value:
            xbmc.executebuiltin("Skin.Reset({0})".format(key))
        return value.lower() if lower else value

    @staticmethod
    def _get_skin(key):
        """
        <summary>
        Read a skin string.
        </summary>
        <param name="key">Skin.String name.</param>
        <returns>Its value, empty when unset.</returns>
        """
        return xbmc.getInfoLabel("Skin.String({0})".format(key))

    @staticmethod
    def _set_or_reset(key, value):
        """
        <summary>
        Write *value* into a skin string, using Skin.Reset for empties so
        String.IsEmpty() conditions keep working. No-op when unchanged, so
        the mirror loop doesn't dirty Kodi's settings store every tick.
        </summary>
        """
        if value == xbmc.getInfoLabel("Skin.String({0})".format(key)):
            return
        if value:
            _set_skin_string(key, value)
        else:
            xbmc.executebuiltin("Skin.Reset({0})".format(key))

    @staticmethod
    def _parse_hhmm(text):
        """
        <summary>
        'HH:MM' -> minutes since midnight, or None if unparsable.
        </summary>
        """
        m = re.match(r"^\s*(\d{1,2}):(\d{1,2})\s*$", text or "")
        if not m:
            return None
        hours, minutes = int(m.group(1)), int(m.group(2))
        if hours > 23 or minutes > 59:
            return None
        return hours * 60 + minutes

    @staticmethod
    def _fmt_hhmm(minutes):
        """
        <summary>
        180 -> '03:00'. The inverse of _parse_hhmm, for seeding its dialog.
        </summary>
        <remarks>
        Both fields are zero padded. Kodi's numeric time dialog silently
        ignores a default it cannot parse and seeds itself from the clock
        instead, so "3:00" turned a three hour default into whatever the
        time happened to be.
        </remarks>
        """
        return "{0:02d}:{1:02d}".format(minutes // 60, minutes % 60)

    def _bg_slot_store(self, slot):
        """
        <summary>
        Copy the live background settings into slot *slot*'s storage.
        </summary>
        """
        for key, live in self.BG_SCHED_LIVE.items():
            self._set_or_reset("bg_slot{0}_{1}".format(slot, key),
                               self._get_skin(live))

    def _bg_slot_load(self, slot):
        """
        <summary>
        Copy slot *slot*'s stored settings into the live background keys.
        </summary>
        """
        for key, live in self.BG_SCHED_LIVE.items():
            self._set_or_reset(live,
                               self._get_skin("bg_slot{0}_{1}".format(slot, key)))

    def _bg_sched_slot_count(self):
        """
        <summary>
        Configured slot count (2..BG_SCHED_MAX_SLOTS), 0 = schedule off.
        </summary>
        """
        count = self._safe_int(self._get_skin("bg_schedule_slots"), 0)
        if count < 2:
            return 0
        return min(count, self.BG_SCHED_MAX_SLOTS)

    def _bg_sched_seed(self, count):
        """
        <summary>
        First time a slot exists, give it a default start time and a copy
        of the current live settings, so enabling the schedule (or raising
        the slot count) changes nothing visibly until the user edits.
        </summary>
        """
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
        """
        <summary>
        The slot the clock says should be showing: latest start <= now,
        wrapping to the overall latest start when now is before all of them
        (i.e. that slot has been running since yesterday). Slots with no
        valid start time are ignored.
        </summary>
        """
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
        """
        <summary>
        Time-of-day background schedule. Off (bg_schedule_slots empty/<2):
        nothing here runs and the live keys behave exactly as before. On:
        while skin settings is open the Background controls edit the slot in
        Skin.String(bg_edit_slot) (live keys double as an edit/preview
        buffer, mirrored into the slot's storage every tick); once settings
        closes, the slot whose start time the clock is inside is copied into
        the live keys, and again at every slot boundary.
        </summary>
        """
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
                if self._sched_applied:
                    self._bg_slot_store(slot)  # sync storage before mirroring
                else:
                    # Never applied yet (settings already open on the first
                    # tick after a service restart): the live keys still hold
                    # whichever slot was live before, so storing them here
                    # would overwrite this slot with another slot's settings.
                    # Pull the slot's stored values up for editing instead.
                    self._bg_slot_load(slot)
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
        """
        <summary>
        Numeric time dialog for the currently-edited slot's start time.
        </summary>
        """
        slot = self._safe_int(self._get_skin("bg_edit_slot"), 1)
        slot = min(max(slot, 1), self.BG_SCHED_MAX_SLOTS)
        key = "bg_slot{0}_start".format(slot)
        current = self._get_skin(key) or "00:00"
        result = xbmcgui.Dialog().numeric(2, _L(31377).format(slot),
                                          current)
        minutes = self._parse_hhmm(result)
        if minutes is None:
            return  # cancelled or garbage: keep the previous start
        _set_skin_string(key, "{0:02d}:{1:02d}".format(minutes // 60,
                                                       minutes % 60))
        _dlog("bg schedule: slot {0} start -> {1:02d}:{2:02d}".format(
            slot, minutes // 60, minutes % 60))

    def _fetch_recent_movies(self):
        """
        <summary>
        Up to BG_COUNT recently watched movies; returns (fanart_url, 'Title (year)') tuples.
        </summary>
        """
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
        """
        <summary>
        (fanart_url, label) pairs from JSON-RPC rows carrying art/title/year.
        Rows with no fanart are skipped, they would render as a blank background.
        </summary>
        """
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
        """
        <summary>
        Up to BG_COUNT random fanart entries restricted to a single genre.
        </summary>
        <remarks>
        gtype is movies / tvshows / both; anything else falls back to movies.
        </remarks>
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
        """
        <summary>
        Up to BG_COUNT random fanart entries from the movie + TV-show library.
        </summary>
        """
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
    """
    <summary>
    Service entry point: build the helper, let the GUI settle, then poll until Kodi shuts down.
    </summary>
    <remarks>
    A construction failure is logged as fatal and the service returns. The
    three second grace before the first property write follows two crash
    dumps that coincided with writes during the Startup to Home transition.
    Fast tickers run every loop and slow ones every SLOW_EVERY loops, and one
    bad tick is caught and logged so it cannot kill the service.
    </remarks>
    """
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
    # Startup grace: both crash dumps on record (0.7.64 and 0.8.2, SIGABRT
    # in a Python thread ~1s after service start) coincided with this
    # service's first burst of Window(home) property writes while Kodi was
    # still tearing through the Startup->Home transition. Let the GUI settle
    # before touching it.
    if helper.waitForAbort(3):
        return

    # Polling loop for things Kodi doesn't notify on (focused item changes etc.).
    # waitForAbort returns True if Kodi is shutting down.
    # Fast-tickers (focused ETA, command channels) run every loop.
    # Slow-tickers (home background slideshow) only every Nth loop.
    SLOW_EVERY = int(1.0 / FunctionalHelper.POLL_SECS) or 1  # ~once per second
    tick = 0
    while not helper.abortRequested():
        # One bad tick must never kill the service, without this guard a
        # single transient error (JSON-RPC hiccup during a library scan,
        # window churn at shutdown) silently stopped the slideshow and
        # every other handler until Kodi was restarted.
        try:
            # Order matters: update_video_nav_state can ask for a sort
            # direction, and update_sort_direction must not try to honour it
            # in the same tick, that is the stale-state race its whole
            # deferral exists to avoid. Running it first means the request
            # lands a tick later, once the new sort method has settled.
            helper.update_sort_direction()
            helper.update_video_nav_state()
            helper.update_focused_eta()
            helper.update_media_age()
            helper.update_focused_age()
            helper.update_settings_command()
            helper.update_layout_command()
            helper.update_bg_command()
            helper.update_random_command()
            helper.update_age_command()
            helper.update_favourites()
            helper.update_continue_watching()
            helper.update_lists()
            helper.update_playing_cast()
            helper.update_info_cast()
            helper.update_cast_command()
            helper.update_cache_command()
            # Fast ticker: the countdown has to move once a second, and the
            # power menu's command must be picked up while the menu is still
            # in front of the user.
            helper.update_sleep_timer()
            if tick == 0:
                helper.update_queue_eta()
                helper.update_settings_backup()
                helper.update_buffer_stats()
                helper.update_bg_schedule()
                helper.update_home_bg()
                helper.maybe_refresh_stats()
                helper.normalize_clearance()
        except Exception:  # noqa: BLE001
            _dlog("tick failed (continuing):\n{0}".format(
                traceback.format_exc()), xbmc.LOGERROR)
        tick = (tick + 1) % SLOW_EVERY
        if helper.waitForAbort(FunctionalHelper.POLL_SECS):
            break
    _dlog("service shutting down")


if __name__ == "__main__":
    run()
