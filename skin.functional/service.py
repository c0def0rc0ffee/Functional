"""
<summary>
Functional skin, helper service.
</summary>
<remarks>
Single long-running service that does jobs the skin XML can't do on its own:
arithmetic on infolabels, async DB queries, time formatting, etc.

Architecture rule: keep this as ONE service that handles multiple concerns
rather than spawning a new add-on per feature. New helpers go in as methods on
FunctionalHelper.

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
    Re-runs after VideoLibrary.OnUpdate, OnScanFinished, OnRemove and
    OnCleanFinished (a burst of events is answered once, see
    apply_library_events) and on a thirty second timer.

update_focused_eta()
    Polls the currently focused video-library list item on the fast tick (four
    times a second) while a video window is active. Reads its duration, adds it to "now", and writes the
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
    in the library), "genre" (one genre only, see below), and "folder" while
    the step buttons are on (otherwise the skin's own multiimage draws the
    folder). Pulls up to 30 items via JSON-RPC, then rotates URL + caption
    on Home as window properties:
        home_bg_fanart        e.g. "image://https%3a%2f%2f...fanart.jpg"
        home_bg_label         e.g. "The Mysterious Dr. Fu Manchu (1929)"
        home_bg_watched       e.g. "Last watched 12/09/2026", empty when
                              the item has never been played
        home_bg_title, home_bg_year, home_bg_dbtype, home_bg_dbid,
        home_bg_file, home_bg_thumb, home_bg_duration
                              the library item behind the picture, empty
                              for a folder picture; the Add To List button
                              on the caption copies them into list_item_*
    Skin.String(bg_lastplayed) adds home_bg_watched to the caption, and
    Skin.String(bg_unwatched) narrows "random" to films never watched.
    Cadence is read from Skin.String(bg_slideshow_interval), defaults to
    BG_INTERVAL seconds when unset. The list itself is re-fetched every
    BG_LIST_REFRESH seconds (or on VideoLibrary.OnUpdate). Every picture
    shown goes into a history so the edge buttons can step back and forth
    (bg_command bg_prev / bg_next, see _bg_step).

update_bg_command()
    Watches Skin.String(bg_command). "pick_genre" opens a select dialog of the
    library's real genres (VideoLibrary.GetGenres, scoped by
    Skin.String(bg_genre_type) = movies / tvshows / both) and stores the answer
    in Skin.String(bg_genre) for the genre slideshow mode. Lives here because
    skin XML has no way to enumerate genres. "pick_time" opens a numeric time
    dialog for the currently-edited schedule slot's start time. Both run on a
    daemon thread so the blocking dialog doesn't stall the polling loop.
    "bg_prev" and "bg_next" step the slideshow (BG-STEP) and run inline.

update_collections_command()
    LIB-COLLECTIONS. Watches Skin.String(collections_command): "cycle" moves
    the collections node on screen through Show: All, Unfinished (some films
    watched, some not) and Not started (none watched). Kodi's sets node
    ignores every play count rule, so the names of the collections in a
    state are worked out here from one VideoLibrary.GetMovies call and
    named in a "set is" rule on a playlist grouped by sets, which the node
    does honour. The search row at that level puts a "set contains" rule
    beside it (_search_apply). The state on screen is read back from the
    playlist's name into Skin.String(collections_state), and the text into
    search_active, the same way the age and search rows are kept honest.

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
    One list can be tied to a Radarr server (the Radarr settings page);
    its Remove from Radarr button asks Radarr to remove the list's films,
    delete their files and block them from being added again, after a
    confirm, in dry run until that is switched off. Settings in
    addon_data/skin.functional/radarr.json, every outcome appended to
    radarr-log.txt beside it. See the RADARR-REMOVE block.

update_coming_up_lines()
    Publishes the Coming up list as ComingUp.L.Kind, .Label, .When and .Sep
    for 22 lines: a day with one slot keeps its two line row, a day with
    several gets a heading and one line per slot (see coming_up_lines).

update_theme()
    Seasonal themes. Picks Halloween from 29 to 31 October (Devil's Night
    on the 30th) and Christmas from the first Saturday of December to
    Boxing Day (Christmas Eve on the 24th), each unless switched off,
    otherwise the theme chosen in Skin Settings; publishes theme_name and theme_seasonal on Home, switches
    Kodi's skin colour setting to colors/halloween.xml and back, and steps
    the crow, the creatures and Santa's sleigh (theme_crow, theme_bats and
    the rest; see _theme_motion).

Future handlers
---------------
- update_focused_filesize(), tried twice and withdrawn: nothing inside Kodi
  can stat a plugin path, and the values for local files were unreliable.
- anything else that needs Python; add a method here and trigger it from
  onNotification or the polling loop in run().
</remarks>
"""

import datetime
import json
from collections import deque
import os
import urllib.error
import urllib.parse
import urllib.request
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

# The add-on API JellyStat's dashboard manages the lists through (LISTS-API).
# Kodi puts the add-on's own folder on sys.path, so it imports beside this file.
import lists_api

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

# Last value this service sent for each skin string, see _set_skin_string.
_SKIN_STRING_SENT = {}

# Command channel -> (value, time taken) for the value most recently handed
# out and not yet seen cleared, see FunctionalHelper._take_command.
_COMMANDS_TAKEN = {}
COMMAND_REPEAT_SECS = 1.0


def _set_skin_string(key, value):
    """
    <summary>
    Write a string into the active skin's persistent string store, unless
    it already holds that value.
    </summary>
    <param name="key">Skin string name.</param>
    <param name="value">New value; anything is turned into text.</param>
    <remarks>
    The value is double-quoted because Kodi splits builtin arguments on
    commas: an unquoted value containing one (a genre like "Sci-Fi, Fantasy",
    a folder path with a comma in it) would be truncated at the first comma.
    Kodi strips the surrounding quotes. Embedded double quotes are dropped:
    Kodi's escape convention for them is murky and no genre/path/stat value
    legitimately contains one.

    Kodi rewrites the skin's settings.xml on every Skin.SetString, even one
    that changes nothing. The thirty second stats refresh and the settings
    snapshot both used to trigger that rewrite for ever on an idle box, so an
    unchanged value is now skipped. Skipping needs two things to agree: the
    store reads back the value, and the last value this service sent (if it
    ever sent one) is the same. The second test matters because the builtin
    is posted, not applied at once: straight after sending A the store can
    still read the older B, and a request to go back to B must not be
    mistaken for "already there".
    </remarks>
    """
    text = str(value).replace('"', '')
    current = xbmc.getInfoLabel("Skin.String({0})".format(key))
    if current == text and _SKIN_STRING_SENT.get(key, text) == text:
        return
    _SKIN_STRING_SENT[key] = text
    xbmc.executebuiltin('Skin.SetString({0},"{1}")'.format(key, text))


def _reset_skin_string(key):
    """
    <summary>
    Clear a skin string with Skin.Reset, and remember having done so.
    </summary>
    <param name="key">Skin string name.</param>
    <remarks>
    Every reset in this service goes through here, never straight to the
    builtin. The reset is posted, not applied at once, so for a moment the
    store still reads the old value. _set_skin_string skips a write when the
    store already reads the wanted value and nothing else has been sent
    since; recording the reset as "sent empty" is what stops a write of that
    same old value, made in that moment, from being skipped and then wiped
    out by the reset landing after it.
    </remarks>
    """
    _SKIN_STRING_SENT[key] = ""
    xbmc.executebuiltin("Skin.Reset({0})".format(key))


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


def _result_rows(resp, key):
    """
    <summary>
    The list stored under *key* in a JSON-RPC reply's result.
    </summary>
    <param name="resp">The decoded reply from _jsonrpc.</param>
    <param name="key">Name of the list inside result, such as "movies".</param>
    <returns>The rows; an empty list when the query ran and matched nothing.</returns>
    <exception cref="LookupError">
    The reply carries no result at all, which is what a failed call or an
    error reply looks like. Kodi leaves the key out of a successful but
    empty answer, so without this test "the database did not answer" and
    "nothing matched" were the same empty list, and callers replaced good
    rows on screen with nothing.
    </exception>
    """
    result = (resp or {}).get("result")
    if not isinstance(result, dict):
        raise LookupError("no result for {0}".format(key))
    return result.get(key) or []


def _count(method, extra_params=None):
    """
    <summary>
    Return the total row count for a VideoLibrary.GetXxx query, ignoring rows.
    </summary>
    <param name="method">The VideoLibrary.GetXxx method to call.</param>
    <param name="extra_params">Extra parameters such as a filter, merged over the one row limit.</param>
    <returns>
    The total, or None when the call failed or the reply carried no usable
    total. None and 0 are different answers: an empty library is 0, a
    database hiccup is None, and the caller must not show the second as the
    first.
    </returns>
    """
    params = {"limits": {"start": 0, "end": 1}}
    if extra_params:
        params.update(extra_params)
    resp = _jsonrpc(method, params)
    # `or {}` at each level: a JSON-RPC error reply carries "result": null,
    # and .get() on None would raise.
    result = (resp or {}).get("result")
    if not isinstance(result, dict):
        return None
    limits = result.get("limits") or {}
    try:
        return int(limits["total"])
    except (KeyError, TypeError, ValueError):
        return None


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


def _num_text(value):
    """
    <summary>
    A season or episode number from a JSON-RPC row as the text a list item holds.
    </summary>
    <param name="value">The number Kodi returned, or None when the row has none.</param>
    <returns>'0' for season 0, '' when there is none.</returns>
    <remarks>
    _list_item_clean reads every field as text, so a row's number has to be made
    text before it. Reading it through "or" turned the number 0 into '' and a
    Specials episode lost its season (c26ab7c fixed the API side; this is the
    same rule for the service's own rows). The same helper lives in lists_api.py,
    which cannot import this module.
    </remarks>
    """
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------


# COMING-UP-LINES: the Coming up list is drawn as 40 pixel lines, two per row
# of the old 80 pixel list, so the cut rules that hide whole rows still apply.
COMING_UP_SLOTS = 50  # Engage.Next.1.* to .50.*, what Engage publishes (COMING-UP-SCROLL)
COMING_UP_LINES = 22  # ComingUp.1.* to .22.*, the lines Home.xml draws
# COMING-UP-SCROLL, 22/10/2026: the controls the scroll watches (Home.xml). Each
# line L has a tall button 9340+L, a short one 9370+L and an invisible marker
# 9470+L that shows while the layout leaves that line room; 9395 and 9396 are
# the catches below the last line and above the first.
COMING_UP_TALL = 9340
COMING_UP_SHORT = 9370
COMING_UP_MARKER = 9470
COMING_UP_CATCH_DOWN = 9395
COMING_UP_CATCH_UP = 9396
COMING_UP_MENU = 9000


# COMING-UP-ESTIMATE, 22/10/2026: the day words Engage's when_label uses, so an
# estimated start reads exactly like a time Engage published.
COMING_UP_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                       "Saturday", "Sunday")


def coming_up_when(start, now):
    """
    <summary>
    Say when a Coming up slot starts in Engage's words.
    </summary>
    <param name="start">The start as a datetime.datetime.</param>
    <param name="now">The current time; only its date matters.</param>
    <returns>"Yesterday HH:MM", "Tonight HH:MM", "Tomorrow HH:MM", "Weekday
    HH:MM" within the week, then "Weekday dd/mm/yyyy HH:MM".</returns>
    <remarks>
    A copy of when_label in Engage's scheduler.py, which is where the words are
    decided; keep the two the same, or an estimated time would group under a
    different day heading from a published one.
    </remarks>
    """
    time_text = "{:02d}:{:02d}".format(start.hour, start.minute)
    days_ahead = (start.date() - now.date()).days
    if days_ahead < 0:
        return "Yesterday " + time_text
    if days_ahead == 0:
        return "Tonight " + time_text
    if days_ahead == 1:
        return "Tomorrow " + time_text
    weekday = COMING_UP_DAY_NAMES[start.weekday()]
    if days_ahead < 7:
        return "{} {}".format(weekday, time_text)
    return "{} {:02d}/{:02d}/{:04d} {}".format(weekday, start.day, start.month,
                                              start.year, time_text)


def estimate_coming_up(slots, now, playing_ends=None):
    """
    <summary>
    Work out when each Coming up slot will really start, when the ones before it
    run on past its set time and it waits its turn in Engage's queue.
    </summary>
    <param name="slots">(label, when, due, runtime) tuples in Engage's order: when
    is Engage.Next.N.When, due its Engage.Next.N.Due ("2026-10-22T18:05") and
    runtime its Engage.Next.N.Runtime in whole seconds, either of the last two
    possibly empty.</param>
    <param name="now">The current time as a datetime.datetime.</param>
    <param name="playing_ends">When whatever is playing now will end, or None when
    nothing is playing or its end cannot be known.</param>
    <returns>(label, when) pairs, when replaced by the estimated start wherever
    that is later than the set time.</returns>
    <remarks>
    Asked for on 22/10/2026: slots set five minutes apart only to order them,
    18:00 then 18:05, queue behind each other, so the second really starts when
    the first ends. Each slot starts at its set time or when the one before it
    ends, whichever is later; the one before ends its start plus its runtime. The
    chain begins at playing_ends. A start is rounded up to the whole minute, since
    nothing starts before the one ahead of it has finished. Where a runtime is
    unknown, the slots after it are held to no earlier than that slot's start,
    which is certain, rather than a guessed end; so the list never runs out of
    order. A slot with no due time (an Engage older than 1.11.7) keeps its words
    and breaks the chain.
    </remarks>
    """
    cursor = playing_ends
    result = []
    for label, when, due, runtime in slots:
        try:
            due_at = datetime.datetime.strptime((due or "").strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            result.append((label, when))
            cursor = None
            continue
        start = due_at
        if cursor is not None and cursor > due_at:
            start = cursor
            if start.second or start.microsecond:
                start = start.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        result.append((label, when if start == due_at else coming_up_when(start, now)))
        try:
            seconds = int(runtime or 0)
        except ValueError:
            seconds = 0
        cursor = start + datetime.timedelta(seconds=seconds) if seconds > 0 else start
    return result


def coming_up_run_ends(slots, now, playing_ends=None):
    """
    <summary>
    Find where each run of back to back Coming up slots ends.
    </summary>
    <param name="slots">(label, when, due, runtime, ends_at) tuples in Engage's
    order: due is Engage.Next.N.Due, runtime its .Runtime in whole seconds and
    ends_at its .EndsAt ("1" when the slot has its Ends At switch on), any of
    them possibly empty.</param>
    <param name="now">The current time as a datetime.datetime; unused, kept so
    the call reads like estimate_coming_up's.</param>
    <param name="playing_ends">When whatever is playing now will end, or None.</param>
    <returns>{index: end} for each slot that ends a run and has its switch on,
    end being a datetime.datetime.</returns>
    <remarks>
    COMING-UP-ENDS, 22/10/2026. A run is slots each of which would start while
    the one before it is still playing, so queues behind it; whatever is playing
    now counts as the start of the first run. Start times follow the same rules as
    estimate_coming_up. A run whose last slot has an unknown running time has an
    unknown end and gets no line, and the next slot then starts a run of its own,
    since whether it would queue cannot be known. A slot with no due time breaks
    the chain the same way. Only the run's last slot's switch counts, as asked
    for on 22/10/2026.
    </remarks>
    """
    result = {}
    cursor = playing_ends
    cursor_known = playing_ends is not None
    last = None

    def close(run_last):
        """<summary>Record a finished run's end when known and wanted.</summary>"""
        if run_last is not None and run_last[1] is not None and run_last[2]:
            result[run_last[0]] = run_last[1]

    for index, (_label, _when, due, runtime, ends_at) in enumerate(slots):
        try:
            due_at = datetime.datetime.strptime((due or "").strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            close(last)
            last, cursor, cursor_known = None, None, False
            continue
        joins = cursor_known and cursor is not None and cursor > due_at
        if not joins:
            close(last)
        start = due_at
        if cursor is not None and cursor > due_at:
            start = cursor
            if start.second or start.microsecond:
                start = start.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        try:
            seconds = int(runtime or 0)
        except ValueError:
            seconds = 0
        end = start + datetime.timedelta(seconds=seconds) if seconds > 0 else None
        last = (index, end, (ends_at or "").strip() == "1")
        cursor, cursor_known = (end, True) if end is not None else (start, False)
    close(last)
    return result


def coming_up_window(lines, offset):
    """
    <summary>
    The COMING_UP_LINES lines of the Coming up list that show from a scroll offset.
    </summary>
    <param name="lines">Every line, as coming_up_lines(..., every=True) gives them.</param>
    <param name="offset">How many lines are scrolled past; made even and kept within
    the list, so a two line row is never split.</param>
    <returns>(window, offset): exactly COMING_UP_LINES line dicts, padded with empty
    ones, and the offset actually used.</returns>
    <remarks>
    COMING-UP-SCROLL, 22/10/2026. The first line shown keeps no day rule: it is the
    top of the list, whatever it was in the whole.
    </remarks>
    """
    last = max(0, len(lines) - 2)
    offset = max(0, min(int(offset) - int(offset) % 2, last - last % 2))
    window = [dict(line) for line in lines[offset:offset + COMING_UP_LINES]]
    if window:
        window[0]["sep"] = ""
    while len(window) < COMING_UP_LINES:
        window.append({"kind": "", "label": "", "when": "", "sep": ""})
    return window, offset


def coming_up_stops(lines, room):
    """
    <summary>
    The scroll offsets the Coming up list may stop at.
    </summary>
    <param name="lines">Every line, as coming_up_lines(..., every=True) gives them.</param>
    <param name="room">How many lines the layout shows.</param>
    <returns>Ascending line offsets, 0 first: the first line of every day, and, for
    a day too long to show whole, each row inside it as well.</returns>
    <remarks>
    COMING-UP-SCROLL, 22/10/2026. Scrolling a day at a time keeps its heading (or
    its one slot) on the top line, so a slot is never shown without its day; asked
    for after the first try, which went a row at a time and could leave "Late Film"
    at the top with no day above it. A day longer than the room still has to be
    walked through, so its rows are stops too. Every day starts on an even offset,
    so whole rows are kept.
    </remarks>
    """
    starts = [i for i, line in enumerate(lines) if line["kind"] in ("heading", "item")]
    stops = set(starts) | {0}
    ends = starts[1:] + [len(lines)]
    for start, end in zip(starts, ends):
        if end - start > room:
            stops.update(range(start, end, 2))
    return sorted(stops)


def coming_up_lines(slots, every=False):
    """
    <summary>
    Lay Engage's upcoming slots out as the lines of the Coming up list.
    </summary>
    <param name="slots">(label, when) pairs in Engage's order, where `when` is
    Engage.Next.N.When: "Tonight 19:00", "Tomorrow 20:00", "Wednesday 19:30"
    or "Wednesday 21/10/2026 19:30". COMING-UP-ENDS, 22/10/2026: an entry may
    instead be (label, time, "ends"), an Ends At line, which joins the day of
    the slot before it whatever its time and is drawn as an "ends" line.</param>
    <returns>COMING_UP_LINES dicts of kind, label, when and sep, one per line,
    empty strings where a line has nothing.</returns>
    <remarks>
    Asked for on 20/10/2026. A day with one slot keeps the original two line
    row: kind "item" with the label and the whole `when`, then an "item2"
    line the item draws over. A day with several slots gets a "heading" line
    holding the day, then one "slot" line each with the label and only the
    time. Everything before the last space of `when` is the day, the last
    word the time, as the old day separators read it. A group of
    odd length is followed by a "pad" line, so every day starts on an odd
    line: the first half of an old row. That keeps a two line item inside
    one row and a heading in the same row as its first slot, so a row the
    layout cuts takes whole items with it and never leaves a heading alone.
    sep is "day" on the first line of every day but the first. With every set
    (COMING-UP-SCROLL), the whole list comes back, uncut and unpadded, for
    coming_up_window to show a part of.
    </remarks>
    """
    groups = []
    for entry in slots:
        if len(entry) > 2 and entry[2] == "ends":
            if groups:
                groups[-1][1].append((entry[0], entry[1], entry[1], "ends"))
            continue
        label, when = entry[0], (entry[1] or "").strip()
        day, _, time = when.rpartition(" ")
        if not day:
            day, time = when, ""
        if groups and groups[-1][0] == day:
            groups[-1][1].append((label, when, time, "slot"))
        else:
            groups.append((day, [(label, when, time, "slot")]))
    lines = []
    for day, members in groups:
        sep = "day" if lines else ""
        if sum(1 for member in members if member[3] == "slot") == 1:
            label, when, _, _ = members[0]
            lines.append({"kind": "item", "label": label, "when": when, "sep": sep})
            lines.append({"kind": "item2", "label": "", "when": "", "sep": ""})
            members = members[1:]
        else:
            lines.append({"kind": "heading", "label": day, "when": "", "sep": sep})
        for label, _, time, kind in members:
            lines.append({"kind": kind, "label": label, "when": time, "sep": ""})
        if len(lines) % 2:
            lines.append({"kind": "pad", "label": "", "when": "", "sep": ""})
    if every:
        return lines
    lines = lines[:COMING_UP_LINES]
    while len(lines) < COMING_UP_LINES:
        lines.append({"kind": "", "label": "", "when": "", "sep": ""})
    return lines


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
    BG_HISTORY = 50  # pictures the previous button can walk back through
    BG_FOLDER_MAX = 500  # most pictures taken from a folder per listing
    # Fields of a slideshow item published beside the picture as
    # home_bg_<name>, in this order. dbtype is "movie" or "tvshow" for a
    # library picture and empty for one from a folder.
    BG_ITEM_PROPS = ("title", "year", "dbtype", "dbid", "file", "thumb",
                     "duration")

    # Live-tunable info-bar clearance via +/− buttons in MyVideoNav's side menu
    # 140 is the most the library views have room for: the list groups are
    # 940 tall on a 1080 canvas, so a slide of 140 puts their foot exactly
    # on the bottom edge. The limit used to be 250, and anything above 140
    # pushed the last rows off the screen. Stored values above the limit are
    # brought back by normalize_clearance.
    LAYOUT_MAX_PX = 140
    LAYOUT_DEFAULT_PX = 140
    LAYOUT_STEP_PX = 10

    FAV_MAX = 150  # how many favourites the custom favourites screen can show

    # Continue Watching pop-up on Home (see update_continue_watching)
    CONTINUE_LISTS = ("9201", "9203", "9205")  # Home.xml container ids: movies, episodes, next up
    NEXTUP_LIST = "9205"           # the Next Up row, static slots (see update_next_up)
    NEXTUP_MAX = 12                # slots the NextUpRows include provides
    NEXTUP_REFRESH_SECS = 300      # safety net; library events and a stop force it sooner

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
        # COMING-UP-SCROLL: lines of the Coming up list scrolled past, and how many
        # lines the whole list has; see update_coming_up_lines.
        self.coming_up_offset = 0
        self.coming_up_total = 0
        self.coming_up_every = []
        # Age labels on the two info screens (see update_media_age), keyed by
        # Home property name so an unchanged label is never rewritten.
        self._age_last = {}
        # Year sources of the focused list item as last seen by
        # update_focused_age, so the label is only rebuilt on a real change.
        self._focused_age_key = None
        self._bg_items = []        # list of item dicts, see _fanart_items
        self._bg_idx = -1
        # BG-STEP: what has been shown, oldest first, and how far back the
        # previous button has walked (0 = the live picture). See _bg_step.
        self._bg_history = deque(maxlen=self.BG_HISTORY)
        self._bg_hist_pos = 0
        self._bg_last_change = 0.0
        self._bg_last_fetch = 0.0
        self._bg_source = ""
        self._bg_folder = ""
        self._bg_thread = None     # library fetches, off the main loop
        self._stats_last_refresh = 0.0   # 0 => loop refreshes on first tick
        self._stats_thread = None
        # Library event debounce (see apply_library_events). Written on Kodi's
        # notification thread, read on the loop; plain floats, no lock needed.
        self._lib_event_first = 0.0  # first event of the burst, 0 = none pending
        self._lib_event_last = 0.0   # most recent event of the burst
        self._dialog_thread = None  # blocking pickers (genre/time), off the main loop
        # Scheduled-background state (see update_bg_schedule)
        self._sched_applied = 0      # slot currently copied into the live keys (0 = none)
        self._sched_edit_last = None  # bg_edit_slot value we last synced with
        self._sched_settings_open = False
        self._bg_pending = {}        # skin string -> (value, expiry), see _bg_get
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
        # Next Up row in the Continue Watching pop-up (see update_next_up).
        self._nextup_lock = threading.Lock()
        self._nextup_last = 0.0          # when the last lookup started, 0 forces one
        self._nextup_thread = None
        self._nextup_items = []          # [{dbid, label, sub, thumb}] as published
        self._nextup_slots_used = 0
        # Age filter (see update_age_command)
        self._accent_custom_seen = None  # last accent_custom value turned into a highlight
        self._tiles_seen = None          # last (toggles, addon, slots) the tiles were published from
        self._tiles_shown = 0            # tiles Home is showing, from the last publish
        self._home_focus_checks = 0      # ticks update_home_focus still has to look
        self._startup_watch = self.STARTUP_WATCH_TICKS  # ticks update_startup_fallback still watches
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
        self._restore_tries = {}      # restore skin key -> failed attempts so far
        self._fullbuffer_ui_last = None  # last seen state of the OSD button setting
        # Video-nav state (see update_video_nav_state)
        self._nav_path = None        # last Container.FolderPath we acted on
        self._nav_genre = None       # last genre name published
        self._nav_sort_due = 0.0     # when to force the default sort (0 = idle)
        self._sort_want_ticks = 0    # ticks update_sort_direction has waited for a new method
        self._genre_names = {}       # (dbtype, genreid) -> genre label
        self._genre_fetched = set()  # dbtypes whose genre list we already pulled
        self._genre_thread = None
        self._genre_retry_at = 0.0   # no genre fetch before this time, set after a failure
        self._random_thread = None   # random pick worker (see update_random_command)
        # Queue end time (see update_queue_eta)
        self._queue_last = None      # last (finish, remaining) pair published
        # Settings backup (see update_settings_backup)
        self._backup_last_check = 0.0
        self._backup_mtime = -1.0    # settings.xml mtime at the last snapshot
        self._backup_age_published = False  # snapshot age shown since this start
        self._backup_thread = None
        # Lists (see update_lists): lists.json is read on first use
        self._lists_lock = threading.Lock()
        self._lists_io_lock = threading.Lock()   # one writer of lists.json at a time
        # The Lists screen's properties are written from the loop and from
        # the dialog thread; re-entrant because publishing the lists also
        # publishes the selected list's items.
        self._lists_pub_lock = threading.RLock()
        self._lists = None           # [{name, items:[record]}], None = not loaded
        self._lists_last = ""        # name of the list an item last went into
        self._lists_sel = 1          # 1-based list the Lists screen has selected
        # LISTS-SORT: the kept order, a LISTS_SORTS mode, "" = file order
        self._lists_sort_mode = ""
        # (row, monotonic deadline) while the Lists screen's cursor is being
        # moved after its list changed place, see _lists_follow
        self._lists_sel_hold = None
        self._lists_frozen = False   # saving refused, see _lists_set_aside
        self._lists_sel_pub = None   # selection the right column currently shows
        self._lists_slots_used = 0   # Lists.N.* slots written last publish
        # Remove Watched (see _lists_track_playback, _lists_drain_watched)
        self._lists_autoremove_any = False  # some list has the switch on
        self._lists_watched_q = deque()  # records seen watched, drained by the loop
        self._lists_playing = None   # what the tracker saw playing last tick
        self._lists_watch_ignore = {}  # (dbtype, dbid) -> expiry, service's own writes
        # Radarr (RADARR-REMOVE, see _radarr_remove_list): radarr.json is
        # read on first use
        self._radarr = None          # {url, key, dry_run}, None = not loaded
        # Sleep timer (see update_sleep_timer). Deliberately not persisted:
        # a timer has nothing to say once the box it was going to switch off
        # has been switched off.
        # time.monotonic() seconds, None = not armed. Monotonic because a box
        # with no clock battery steps its wall clock when the network time
        # arrives, and a deadline in wall clock time then fired at once or
        # ran late by the size of the step.
        self._sleep_deadline = None
        self._sleep_episodes = 0      # natural playback ends still to wait for, 0 = not in that mode
        self._sleep_fire_pending = False  # the last end arrived on the notification thread
        self._sleep_warned = False    # the one-minute toast has been shown
        self._sleep_published = ""    # countdown label currently on screen
        self._list_item_slots_used = 0  # LI.N.* slots written last publish
        # Seasonal themes (THEME-SEASON, see update_theme)
        self._theme_seen = None          # theme last logged
        self._theme_colours_ok = None    # colour set last confirmed in Kodi's setting
        self._theme_colours_at = 0.0     # monotonic time of that read
        self._theme_motion_live = False  # bat and lightning timers are running
        self._crow_state = None          # None = no crow; else as in _crow_set
        self._crow_until = 0.0
        self._crow_leave_at = 0.0
        # Creatures (THEME-CREATURES, see _theme_motion): property name ->
        # (value, monotonic time it is done); next due time per kind.
        self._creatures = {}
        self._theme_next = {}
        self._intro_start = None         # monotonic start of the yearly build-up, None = not running
        self._intro_step = 0
        self._intro_level = 0
        self._season_seen = False        # this run has already met the season
        # Santa's sleigh (THEME-CHRISTMAS, see _theme_sleigh)
        self._sleigh = ("", 0.0)         # (state, monotonic time it ends)
        self._sleigh_next = 0.0          # next crossing due; 0 = not scheduled yet
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
            # could block it), and don't even reset the timers here: a scan
            # announces one event per item, and acting on each one restarted
            # five stats queries, a background refetch and a next up lookup
            # per item. Note the time and let apply_library_events() act once
            # the burst has gone quiet.
            now = time.time()
            if not self._lib_event_first:
                self._lib_event_first = now
            self._lib_event_last = now
        if method == "VideoLibrary.OnUpdate" and self._lists_autoremove_any:
            self._lists_on_update(data)
        if method == "Player.OnStop":
            # Finishing an episode is exactly what moves a show along.
            self._nextup_last = 0.0
            self._sleep_on_stop(data)

    # -- Handlers -----------------------------------------------------------

    LIB_EVENT_QUIET_SECS = 2.0   # act this long after the last library event
    LIB_EVENT_MAX_HOLD = 15.0    # but never hold a burst back longer than this

    def apply_library_events(self):
        """
        <summary>
        Turn a burst of library events into one refresh of everything that
        is derived from the library.
        </summary>
        <remarks>
        Fast tick, and a no-op unless onNotification has noted an event. The
        refresh happens once the events have been quiet for
        LIB_EVENT_QUIET_SECS, or LIB_EVENT_MAX_HOLD after the first one, so a
        long scan still moves the figures along instead of freezing them
        until it ends. Must run before the handlers whose timers it resets.
        </remarks>
        """
        first = self._lib_event_first
        if not first:
            return
        now = time.time()
        if ((now - self._lib_event_last) < self.LIB_EVENT_QUIET_SECS
                and (now - first) < self.LIB_EVENT_MAX_HOLD):
            return
        self._lib_event_first = 0.0
        self._stats_last_refresh = 0.0
        self._bg_last_fetch = 0.0
        self._nextup_last = 0.0
        # A scan can add or rename genres; let the next genre lookup re-pull
        # the list rather than label a node from a stale cache.
        self._genre_fetched = set()

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
        movies_watched = max(0, (movies_total or 0) - (movies_unwatched or 0))

        tvshows_total = _count("VideoLibrary.GetTVShows")
        # tvshows have no per-show playcount filter semantics worth using:
        # numwatched=0 ("no episode watched") matches the side-menu filters.
        tvshows_unwatched = _count("VideoLibrary.GetTVShows", {
            "filter": {"field": "numwatched", "operator": "is", "value": "0"}
        })
        episodes_total = _count("VideoLibrary.GetEpisodes")

        if None in (movies_total, movies_unwatched, tvshows_total,
                    tvshows_unwatched, episodes_total):
            # A failed query must not put zeros on Home. Keep what is shown
            # and let the thirty second timer try again.
            _dlog("stats: a library query failed, keeping the last figures",
                  xbmc.LOGWARNING)
            return

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
        # Kodi reports the music player's type as "audio", not "music". The
        # old test compared against "music", never matched, and counted the
        # whole queue from the top however far through it playback was.
        player_type = "audio" if kind == "music" else kind
        players = (_jsonrpc("Player.GetActivePlayers").get("result") or [])
        pid = next((p.get("playerid") for p in players
                    if p.get("type") == player_type), None)
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
        # Percent encoded, as the age and search filters do: a raw JSON
        # value containing an ampersand ("Ant & Dec") cut the URL's options
        # short and opened the unfiltered library, and a name with a double
        # quote in it broke the builtin's own quoting.
        url = base + "?xsp=" + urllib.parse.quote(
            json.dumps(rule, separators=(",", ":")))
        command = 'ActivateWindow(Videos,"{0}",return)'.format(url)
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
        <returns>
        True when Kodi accepted the value. A value outside the setting's own
        options list is refused, and callers that remember "the old value"
        somewhere must not forget it on a refusal.
        </returns>
        """
        resp = _jsonrpc("Settings.SetSettingValue",
                        {"setting": setting_id, "value": value})
        ok = (resp or {}).get("result") is True
        if not ok:
            _dlog("setting {0} = {1!r} was not accepted: {2}".format(
                setting_id, value, (resp or {}).get("error")),
                xbmc.LOGWARNING)
        return ok

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
        <param name="secs">Whole seconds, zero or more.</param>
        <returns>The duration in its two largest units, from strings.po so the unit letters can be translated.</returns>
        """
        if secs >= 3600:
            return _L(31571).format(secs // 3600, (secs % 3600) // 60)
        if secs >= 60:
            return _L(31572).format(secs // 60, secs % 60)
        return _L(31573).format(secs)

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

        # One read for the rest of this call: the full file worker sets the
        # attribute back to None from its own thread, and reading it twice
        # in one expression further down could multiply by None.
        memsize = self._buffer_memsize
        if memsize is None:
            return

        # Tells the OSD its "BUFFER ALL" button is already satisfied
        # (memorysize 0 = Kodi's uncapped disk cache).
        fullfile = "1" if memsize == 0 else ""
        if fullfile != self._buffer_fullfile_last:
            self._buffer_fullfile_last = fullfile
            _set_home_property("buffer_fullfile", fullfile)

        if xbmc.getCondVisibility("Skin.HasSetting(hide_osd_buffer)"):
            # Every readout this feeds is switched off (Show Buffer Level on
            # OSD), so the two player queries a second below would be work
            # for nothing. The BUFFER ALL flag above needs no query.
            if self._buffer_last:
                self._buffer_last = ""
                _set_home_property("buffer_detail", "")
            if self._buffer_pct_last:
                self._buffer_pct_last = ""
                _set_home_property("buffer_pct_label", "")
            return

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
            if memsize and level > 0:
                mb = level * memsize / 100.0
        if mb >= 1000:
            parts.append(_L(31452).format("{0:.1f}".format(mb / 1024.0)))
        elif mb >= 10:
            parts.append(_L(31453).format("{0:.0f}".format(mb)))
        elif mb > 0:
            parts.append(_L(31453).format("{0:.1f}".format(mb)))
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
                self._reset_buffering_to_defaults(_L(31570))

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
            if self._set_setting(sid, nxt):
                _dlog("cache: {0} {1} -> {2}".format(sid, current, nxt))
                # A choice made here during a BUFFER ALL session is the
                # user's newest word on this setting. Drop the remembered
                # value for it, or the end of playback would quietly put the
                # older one back over the top.
                for restore_sid, skin_key in self.FULLFILE_RESTORE_KEYS:
                    if restore_sid == sid:
                        _reset_skin_string(skin_key)
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
            _reset_skin_string(skin_key)
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
    # Attempts at putting a remembered value back before falling back to
    # Kodi's default for that setting, see _maybe_restore_cache.
    RESTORE_MAX_TRIES = 3

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
            value = self._safe_int(prior, None)
            if value is None:
                _reset_skin_string(skin_key)
                continue
            if not self._set_setting(setting_id, value):
                # Refused or failed: keep the remembered value so the next
                # idle tick tries again, rather than leaving the uncapped
                # cache on for good with nothing left to restore from. Only
                # a few times, though: a value Kodi will never accept (one
                # that fell off its options list) would otherwise be retried
                # and logged once a second for as long as nothing played.
                tries = self._restore_tries.get(skin_key, 0) + 1
                self._restore_tries[skin_key] = tries
                if tries >= self.RESTORE_MAX_TRIES:
                    _reset_skin_string(skin_key)
                    self._restore_tries.pop(skin_key, None)
                    default = self.CACHE_DEFAULTS.get(setting_id)
                    if default is not None:
                        self._set_setting(setting_id, default)
                        restored[setting_id] = default
                continue
            self._restore_tries.pop(skin_key, None)
            _reset_skin_string(skin_key)
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
        Sets _fullfile_busy for the duration, which is what stops
        _maybe_restore_cache undoing the switch during the moment the player
        is stopped, and always clears it, even when the switch raises.
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
        props = (_jsonrpc("Player.GetProperties",
                          {"playerid": pid,
                           "properties": ["time", "playlistid", "position"]})
                 .get("result") or {})
        t = props.get("time") or {}
        secs = (t.get("hours", 0) * 3600 + t.get("minutes", 0) * 60
                + t.get("seconds", 0))
        secs = max(0, secs - self.FULLFILE_SEEK_BACK)
        # Where in the queue this is playing from, if it is. Reopening the
        # item on its own (the old behaviour) took it out of the queue, so
        # nothing followed it: episode two of a queued run was the last.
        playlist_id = props.get("playlistid")
        position = props.get("position")
        if not isinstance(position, int) or position < 0:
            playlist_id = None

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
                _reset_skin_string(skin_key)
            _reset_skin_string("cache_mem_restore")
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
        # waitForAbort rather than xbmc.sleep for every wait below: this
        # thread used to carry on for half a minute after Kodi was told to
        # quit, and could issue Player.Open into a shutdown.
        if self.waitForAbort(1.5):
            return
        if playlist_id is not None:
            # Still the same item at that position? Then open it through the
            # queue so playback runs on into the next one. Anything else
            # (the queue was cleared, or changed under us) falls back to the
            # item on its own.
            queued = ((_jsonrpc("Playlist.GetItems", {
                "playlistid": playlist_id, "properties": ["file"],
                "limits": {"start": position, "end": position + 1}})
                .get("result") or {}).get("items") or [])
            same = bool(queued) and (
                (item.get("id") and queued[0].get("id") == item.get("id")
                 and queued[0].get("type") == item.get("type"))
                or (item.get("file") and queued[0].get("file") == item.get("file")))
            if same:
                target = {"playlistid": playlist_id, "position": position}
        _jsonrpc("Player.Open", {"item": target})
        for _ in range(self.FULLFILE_REOPEN_WAIT * 2):
            if xbmc.getCondVisibility("Player.HasVideo"):
                break
            if self.waitForAbort(0.5):
                return
        else:
            _dlog("fullfile: stream did not come back within {0}s".format(
                self.FULLFILE_REOPEN_WAIT), xbmc.LOGWARNING)
            return
        if self.waitForAbort(2.0):  # let the demuxer settle before seeking
            return
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
        <remarks>
        BG-STEP: folder mode is normally a native multiimage in the skin,
        which cannot be stepped, so while Skin.HasSetting(bg_step_buttons)
        is on the folder is listed here instead and rotated like the
        library modes. An empty listing publishes nothing, and the skin's
        multiimage shows whenever home_bg_fanart is empty, so a folder
        Python cannot read still gets its slideshow, just without buttons.
        </remarks>
        """
        # Unified selector: bg_mode is one of off(empty)/image/recent/
        # random/genre/folder. Only the slideshow modes drive this handler;
        # for image/off we clear the fanart property so the static image (or
        # nothing) shows with no conflict.
        mode = xbmc.getInfoLabel("Skin.String(bg_mode)")

        source = None
        if mode == "folder":
            # FOLDER mode is rendered natively by a <multiimage> in Home.xml,
            # far more reliable for local/sandboxed paths than fetching the
            # listing ourselves. We resolve the picked picture to its folder
            # and publish it as Skin.String(bg_slideshow_dir) for that
            # control, and only list it ourselves when the step buttons
            # need to know what is on screen.
            folder = _derive_folder(xbmc.getInfoLabel("Skin.String(bg_slideshow_folder)"))
            if folder != xbmc.getInfoLabel("Skin.String(bg_slideshow_dir)"):
                _set_skin_string("bg_slideshow_dir", folder)
                _dlog("folder slideshow dir -> {0!r}".format(folder))
            if folder and xbmc.getCondVisibility("Skin.HasSetting(bg_step_buttons)"):
                source = "folder:" + folder
            else:
                # Make sure the service-driven slideshow image isn't also
                # showing.
                self._bg_reset_source()
                self._set_bg_props("", "")
                return
        elif mode == "genre":
            # GENRE mode keys its source on the genre + media type as well
            # as the mode, so changing either forces a re-fetch through the
            # same source-changed path the other modes use.
            genre = xbmc.getInfoLabel("Skin.String(bg_genre)")
            if not genre:
                # Mode selected but no genre picked yet: show nothing rather
                # than silently falling back to the whole library.
                self._bg_reset_source()
                self._set_bg_props("", "")
                return
            source = "genre:{0}:{1}".format(
                xbmc.getInfoLabel("Skin.String(bg_genre_type)") or "movies", genre)
        elif mode == "random":
            # BG-UNWATCHED: the filter is part of the key, so switching it
            # refetches through the source changed path below.
            source = ("random:unwatched"
                      if xbmc.getInfoLabel("Skin.String(bg_unwatched)")
                      else "random")
        elif mode == "recent":
            source = "recent"

        if source is None:
            # image or off, never any slideshow fanart here. Always clear it
            # so a previous slideshow's backdrop can't linger.
            self._bg_reset_source()
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
        # movies" bug). The history goes too: Back must never resurrect a
        # picture from the mode that was just left.
        if getattr(self, "_bg_source", "") != source:
            self._bg_reset_source()
            self._bg_source = source
            self._bg_items = []
            self._bg_last_fetch = 0.0
            self._bg_last_change = 0.0
            self._set_bg_props("", "")

        # Refresh the items list periodically or when invalidated. An empty
        # result (server unreachable at boot, library mid-scan) retries on a
        # short backoff, NOT every tick, which hammered the source. The
        # fetch itself runs on a daemon thread: executeJSONRPC against a
        # slow/unreachable video DB blocks, and blocking here stalls ETA,
        # every command channel and the rest of the loop (the same failure
        # the stats and cast lookups were moved off-loop for).
        # One read of the list for this call: the fetch worker swaps it from
        # its own thread, and indexing a list that had just been replaced by
        # a shorter one raised IndexError, which cost the rest of the tick.
        bg_items = self._bg_items
        refresh_after = self.BG_LIST_REFRESH if bg_items else self.BG_EMPTY_RETRY
        if ((now - self._bg_last_fetch) > refresh_after
                and (self._bg_thread is None or not self._bg_thread.is_alive())):
            self._bg_last_fetch = now
            self._bg_thread = threading.Thread(
                target=self._bg_fetch_worker, args=(source,),
                name="functional-bg", daemon=True)
            self._bg_thread.start()

        if not bg_items:
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
            self._bg_advance(bg_items, now)

    def _bg_reset_source(self):
        """
        <summary>
        Forget the slideshow source, its position and the shown history,
        the state every "nothing to rotate" path and a source change share.
        </summary>
        """
        self._bg_source = ""
        self._bg_idx = -1
        self._bg_history.clear()
        self._bg_hist_pos = 0

    def _bg_advance(self, bg_items, now):
        """
        <summary>
        Move the slideshow one picture forward: through the shown history
        while the previous button has walked back, else on to the next item
        of the list, which is then recorded in the history.
        </summary>
        <param name="bg_items">The current list, read once by the caller;
        must be non empty unless the history is being walked.</param>
        <param name="now">time.time() of this tick; restarts the interval.</param>
        <remarks>
        Called by the timer and by bg_next, so a manual step and a timed
        one are the same move and the clock restarts either way.
        </remarks>
        """
        self._bg_last_change = now
        if self._bg_hist_pos > 0:
            self._bg_hist_pos -= 1
            self._bg_show(self._bg_history[-1 - self._bg_hist_pos])
            return
        self._bg_idx = (self._bg_idx + 1) % len(bg_items)
        item = bg_items[self._bg_idx]
        self._bg_history.append(item)
        self._bg_show(item)
        _dlog("bg rotate -> {0} | {1}".format(item["label"], item["fanart"][:120]),
              xbmc.LOGDEBUG)

    def _bg_step(self, cmd):
        """
        <summary>
        BG-STEP: the edge buttons. "bg_prev" shows the picture before the
        one on screen, as far back as the history goes; "bg_next" walks
        forward through the history or, at the live end, advances the
        list exactly as the timer would.
        </summary>
        <param name="cmd">"bg_prev" or "bg_next".</param>
        <remarks>
        Ignored while no service driven slideshow is up (image or off, or
        folder mode with the buttons off), and at the oldest picture. The
        history holds what was shown, not list positions, so a list
        refresh that reshuffles the items cannot change what Back returns
        to. Runs on the loop thread: property writes only, nothing that
        blocks.
        </remarks>
        """
        if not self._bg_source:
            return
        now = time.time()
        if cmd == "bg_prev":
            if self._bg_hist_pos + 1 >= len(self._bg_history):
                _dlog("bg step: nothing earlier to show", xbmc.LOGDEBUG)
                return
            self._bg_hist_pos += 1
            self._bg_last_change = now
            self._bg_show(self._bg_history[-1 - self._bg_hist_pos])
            return
        bg_items = self._bg_items
        if self._bg_hist_pos == 0 and not bg_items:
            return
        self._bg_advance(bg_items, now)

    def _bg_show(self, item):
        """
        <summary>
        Put one slideshow item on Home: picture, caption, last watched
        text and the library fields behind the Add To List button.
        </summary>
        <param name="item">A dict from _fanart_items or _fetch_folder_images.</param>
        """
        self._set_bg_props(item["fanart"], item["label"], item.get("watched", ""), item)

    @staticmethod
    def _set_bg_props(fanart, label, watched="", item=None):
        """
        <summary>
        Write the Home background properties, skipping writes that
        wouldn't change anything: several callers run once per slow tick
        forever, and bursts of redundant Window(home) writes are implicated
        in the startup SIGABRT (see run()).
        </summary>
        <param name="fanart">Image URL, empty for none.</param>
        <param name="label">Caption, empty for none.</param>
        <param name="watched">"Last watched" text for the caption, empty
        when the item was never played or the mode has no library item.
        BgCaptionText in Includes.xml only shows it while
        Skin.String(bg_lastplayed) is set.</param>
        <param name="item">The slideshow item, whose BG_ITEM_PROPS fields
        are published as home_bg_&lt;name&gt;; None clears them all, which
        is what every "nothing to show" path passes. A dbid of 0 is
        written as empty so the XML's String.IsEmpty test reads it as no
        library item.</param>
        """
        win = xbmcgui.Window(HOME_WINDOW_ID)
        if win.getProperty("home_bg_fanart") != fanart:
            win.setProperty("home_bg_fanart", fanart)
        if win.getProperty("home_bg_label") != label:
            win.setProperty("home_bg_label", label)
        if win.getProperty("home_bg_watched") != watched:
            win.setProperty("home_bg_watched", watched)
        for key in FunctionalHelper.BG_ITEM_PROPS:
            value = (item or {}).get(key, "")
            value = "" if value in (0, None) else str(value)
            prop = "home_bg_{0}".format(key)
            if win.getProperty(prop) != value:
                win.setProperty(prop, value)

    def _bg_fetch_worker(self, source):
        """
        <summary>
        Resolve the slideshow item list for *source* (daemon thread).
        </summary>
        <remarks>
        Sources: "recent", "random", "random:unwatched", "genre:type:name"
        and "folder:path" (BG-STEP, the path as _derive_folder left it,
        separator and all, so a path with a colon in it is safe because
        only the first seven characters are the tag).
        </remarks>
        """
        try:
            if source == "recent":
                items = self._fetch_recent_movies()
            elif source.startswith("genre:"):
                _, gtype, gname = source.split(":", 2)
                items = self._fetch_genre_library(gname, gtype)
            elif source.startswith("folder:"):
                items = self._fetch_folder_images(source[7:])
            else:  # random or random:unwatched
                items = self._fetch_random_library(
                    unwatched=source == "random:unwatched")
        except LookupError as exc:
            # The library did not answer. Keep whatever list is showing; an
            # empty one retries on the short backoff, a full one on the
            # normal refresh.
            _dlog("bg fetch: {0}, keeping the current list".format(exc),
                  xbmc.LOGWARNING)
            return
        except Exception:  # noqa: BLE001
            _dlog("bg fetch worker failed:\n{0}".format(traceback.format_exc()),
                  xbmc.LOGERROR)
            return  # empty-retry backoff will schedule another attempt
        # The user may have switched source while we were querying; don't
        # install a stale list over the new source's (same idea as the cast
        # workers' staleness guard).
        if source != self._bg_source:
            return
        had_items = bool(self._bg_items)
        unchanged = items == self._bg_items
        self._bg_items = items
        _dlog("bg slideshow ({0}): {1} items".format(source, len(items)))
        if unchanged:
            return  # same list: leave the picture and its timer alone
        self._bg_idx = -1
        if not had_items:
            # First list for this source: show something on the next slow
            # tick. A refresh of a list that was already rotating keeps its
            # rhythm instead; every library event (a stop that saved a
            # resume point, a watched toggle, each item of a scan) used to
            # snap Home to a new picture whatever the interval said.
            self._bg_last_change = 0.0

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
        explicit = xbmc.getInfoLabel("Skin.String(fav_category)").strip().lower()
        category = explicit or xbmc.getInfoLabel(
            "Skin.String(fav_default_category)").strip().lower()
        if category not in self.FAV_CATS:
            category = "all"
        if (not explicit and category != "all"
                and not any(it["cat"] == category for it in self._fav_all)):
            # The configured default filter has nothing in it. Opening on an
            # empty grid left the screen with no focusable control at all,
            # so the default quietly becomes All until that category has
            # something. A chip the viewer picks by hand is left alone.
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
        if xbmc.getInfoLabel("System.CurrentControlId") == self.NEXTUP_LIST:
            # The Next Up rows are static items, so the library id rides on
            # an item property rather than ListItem.DBID (see NextUpRow).
            dbtype = "episode"
            dbid = self._safe_int(xbmc.getInfoLabel("ListItem.Property(dbid)"), 0)
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
        <param name="cmd">continue_command value: resume, watched, unwatched, play, or nextup:N for a click on Next Up slot N.</param>
        <param name="dbtype">"movie" or "episode" of the row the menu was opened on.</param>
        <param name="dbid">Library id of that row.</param>
        <remarks>
        A nextup:N click resolves the slot to the episode the service last
        published there and plays it from the start; the row is static, so
        the id cannot come from ListItem.DBID. "watched" bumps the play count and clears the resume point, which is
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
        if cmd.startswith("nextup:"):
            with self._nextup_lock:
                items = list(self._nextup_items)
            slot = self._safe_int(cmd[7:], 0) - 1
            if not 0 <= slot < len(items):
                _dlog("next up: slot %r is empty, ignored" % cmd)
                return
            dbtype, dbid, cmd = "episode", items[slot]["dbid"], "play"
        if dbtype not in ("movie", "episode") or dbid <= 0:
            _dlog("continue watching: %s ignored, no item captured" % cmd)
            return
        kind = "Movie" if dbtype == "movie" else "Episode"
        idkey = dbtype + "id"
        _dlog("continue watching: %s %s %d" % (cmd, dbtype, dbid))
        if cmd == "resume":
            _jsonrpc("Player.Open", {"item": {idkey: dbid}, "options": {"resume": True}})
        elif cmd == "play":
            _jsonrpc("Player.Open", {"item": {idkey: dbid}})
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
                # That count of one is not a watch, so Remove Watched lists
                # are told to let its announcement pass.
                self._lists_watch_ignore[(dbtype, dbid)] = time.time() + 10
                params["playcount"] = 1
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, params)
                _jsonrpc("VideoLibrary.Set%sDetails" % kind, {idkey: dbid, "playcount": 0})
        else:
            _dlog("continue command ignored: %r" % cmd)

    # ---- Colophon (the hidden screen, custom window 1154) --------------------

    DEDICATION_FILE = "special://profile/addon_data/skin.functional/colophon/dedication.jpg"

    def write_dedication(self):
        """
        <summary>
        Write the Colophon screen's dedication photo out of the skin's code
        into the skin's data folder, and tell the screen where it is.
        </summary>
        <returns>True when the photo is in place.</returns>
        <remarks>
        The photo ships as base64 text in colophon_art.py rather than as an
        image file (COLOPHON, 21/10/2026). Run once at start up. The file is
        rewritten only when its SHA-256 differs from the one the module
        carries, so a normal start reads it and writes nothing. It is written
        beside itself and renamed into place, so the screen never shows half
        a picture. Window(home).Property(colophon_photo) holds its path once
        it is there; the screen shows the photo only while that is set. Any
        failure is logged and leaves the screen with the words alone.
        </remarks>
        """
        import base64
        import hashlib
        home = xbmcgui.Window(HOME_WINDOW_ID)
        try:
            import colophon_art
            path = xbmcvfs.translatePath(self.DEDICATION_FILE)
            current = None
            if os.path.isfile(path):
                with open(path, "rb") as handle:
                    current = hashlib.sha256(handle.read()).hexdigest()
            if current != colophon_art.DEDICATION_SHA256:
                data = base64.b64decode(colophon_art.DEDICATION_JPEG)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".part", "wb") as handle:
                    handle.write(data)
                os.replace(path + ".part", path)
                _dlog("colophon: dedication photo written")
            home.setProperty("colophon_photo", self.DEDICATION_FILE)
            return True
        except Exception as err:  # noqa: BLE001
            _dlog("colophon: could not write the dedication photo: %s" % err,
                  xbmc.LOGWARNING)
            home.clearProperty("colophon_photo")
            return False

    # ---- Coming up (Engage's next slots, the list on the left of Home) ----

    def update_coming_up_lines(self):
        """
        <summary>
        Publish the Coming up list as lines: one two line row for a day with
        one slot, a day heading and a line per slot for a day with several.
        </summary>
        <remarks>
        Slow tick. Reads Engage.Next.1 to 50 (Label and When) from Home, stops
        at the first empty label, lays them out with coming_up_lines and
        publishes Window(home).Property(ComingUp.L.Kind), .Label, .When and
        .Sep for L 1 to 22, which Home.xml's ComingUpLine include draws.
        Written only on a change, and an empty value is cleared rather than
        set. This replaced update_coming_up_days and its ComingUp.N.Sep
        (COMING-UP-SEP, 12/10/2026) on 20/10/2026; the heavier rule where
        the day changes is the "day" sep here. COMING-UP-MORE, 21/10/2026:
        reads 22 slots, up from 11, because days that share a heading take
        fewer than two lines a slot and the 22 lines had room to spare;
        coming_up_lines still cuts whatever does not fit.
        COMING-UP-ESTIMATE, 22/10/2026: with Skin.HasSetting(coming_up_estimate)
        on, the times are first replaced by estimate_coming_up's, using each
        slot's Engage.Next.N.Due and .Runtime and the end of whatever is
        playing; with it off, or with an Engage that publishes neither, the
        list is exactly as Engage sent it. COMING-UP-ENDS, 22/10/2026: with
        Skin.HasSetting(coming_up_ends) on, whichever the estimate is, an
        "Ends At" line follows each run's last slot where coming_up_run_ends
        finds one, its time as HH:MM. COMING-UP-SCROLL, 22/10/2026: reads up to
        50 slots, and shows the 22 lines from coming_up_offset on
        (coming_up_window); ComingUp.Scrolled is "1" while that is not the top.
        The offset only moves while Skin.HasSetting(coming_up_scroll) is on.
        </remarks>
        """
        home = xbmcgui.Window(HOME_WINDOW_ID)
        slots = []
        for n in range(1, COMING_UP_SLOTS + 1):
            label = home.getProperty("Engage.Next.{0}.Label".format(n)).strip()
            if not label:
                break
            slots.append((label, home.getProperty("Engage.Next.{0}.When".format(n)),
                          home.getProperty("Engage.Next.{0}.Due".format(n)),
                          home.getProperty("Engage.Next.{0}.Runtime".format(n)),
                          home.getProperty("Engage.Next.{0}.EndsAt".format(n))))
        estimate = xbmc.getCondVisibility("Skin.HasSetting(coming_up_estimate)")
        ends = {}
        if estimate or xbmc.getCondVisibility("Skin.HasSetting(coming_up_ends)"):
            now = datetime.datetime.now()
            playing_ends = self.coming_up_playing_ends(now)
            if xbmc.getCondVisibility("Skin.HasSetting(coming_up_ends)"):
                ends = coming_up_run_ends(slots, now, playing_ends)
        if estimate:
            shown = estimate_coming_up([row[:4] for row in slots], now, playing_ends)
        else:
            shown = [(row[0], row[1]) for row in slots]
        entries = []
        for index, entry in enumerate(shown):
            entries.append(entry)
            if index in ends:
                entries.append(("Ends At", "{:02d}:{:02d}".format(ends[index].hour,
                                                                  ends[index].minute), "ends"))
        if not xbmc.getCondVisibility("Skin.HasSetting(coming_up_scroll)"):
            self.coming_up_offset = 0
        every = coming_up_lines(entries, every=True)
        self.coming_up_every = every
        self.coming_up_total = len(every)
        window, self.coming_up_offset = coming_up_window(every, self.coming_up_offset)
        scrolled = "1" if self.coming_up_offset else ""
        if home.getProperty("ComingUp.Scrolled") != scrolled:
            if scrolled:
                home.setProperty("ComingUp.Scrolled", scrolled)
            else:
                home.clearProperty("ComingUp.Scrolled")
        for number, line in enumerate(window, 1):
            for field in ("kind", "label", "when", "sep"):
                key = "ComingUp.{0}.{1}".format(number, field.capitalize())
                value = line[field]
                if home.getProperty(key) != value:
                    if value:
                        home.setProperty(key, value)
                    else:
                        home.clearProperty(key)

    def coming_up_playing_ends(self, now):
        """
        <summary>
        When whatever is playing now will end, for the Coming up estimate.
        </summary>
        <param name="now">The current time as a datetime.datetime.</param>
        <returns>A datetime.datetime, or None when nothing is playing or the end
        cannot be known (a live stream or anything else with no total time).</returns>
        <remarks>
        COMING-UP-ESTIMATE. Anything playing counts, not only what Engage started,
        because Engage queues a slot behind any playback. A paused item keeps
        moving its end later, one tick at a time.
        </remarks>
        """
        try:
            player = xbmc.Player()
            if not player.isPlaying():
                return None
            total = player.getTotalTime()
            if total <= 0:
                return None
            left = max(0.0, total - player.getTime())
        except Exception:  # noqa: BLE001 - playback can stop between the calls
            return None
        return now + datetime.timedelta(seconds=left)

    def coming_up_scroll_tick(self):
        """
        <summary>
        Scroll the Coming up list when focus reaches a catch below or above it, and
        put it back to the top once focus leaves it.
        </summary>
        <remarks>
        COMING-UP-SCROLL, 22/10/2026. Fast tick. Home.xml sends Down from the list's
        last line to the catch 9395 and Up from its first line, while scrolled, to
        9396; both are invisible one pixel buttons. On 9395 the list moves down to
        the next day and focus goes to the last line it now shows that has
        something to choose, or on to the menu row when nothing is left below. On
        9396 it moves up to the day before and focus goes to the first such line,
        or on to the menu row at the top. A move goes to the next or previous stop from
        coming_up_stops, which is a whole day unless the day is too long to fit. Focus anywhere but the list and its catches puts the
        list back to the top. How many lines the layout leaves room for is read
        from the markers 9471 to 9492, so every cut rule in Home.xml still holds.
        With the setting off the catches are hidden and this does nothing.
        </remarks>
        """
        if not xbmc.getCondVisibility("Skin.HasSetting(coming_up_scroll)"):
            return
        on_home = xbmc.getCondVisibility("Window.IsActive(home)")
        try:
            focus = int(xbmc.getInfoLabel("System.CurrentControlId") or 0) if on_home else 0
        except ValueError:
            focus = 0
        lines = range(1, COMING_UP_LINES + 1)
        ours = {COMING_UP_CATCH_DOWN, COMING_UP_CATCH_UP}
        ours.update(COMING_UP_TALL + n for n in lines)
        ours.update(COMING_UP_SHORT + n for n in lines)
        if focus not in ours:
            if self.coming_up_offset:
                self.coming_up_offset = 0
                self.update_coming_up_lines()
            return
        if focus not in (COMING_UP_CATCH_DOWN, COMING_UP_CATCH_UP):
            return
        room = sum(1 for n in lines
                   if xbmc.getCondVisibility("Control.IsVisible({0})".format(COMING_UP_MARKER + n)))
        stops = coming_up_stops(self.coming_up_every, room) if room else [0]
        if focus == COMING_UP_CATCH_DOWN:
            later = [stop for stop in stops if stop > self.coming_up_offset]
            if room and later and self.coming_up_offset + room < self.coming_up_total:
                self.coming_up_offset = later[0]
                self.update_coming_up_lines()
                self.coming_up_focus_line(range(room, 0, -1))
            else:
                xbmc.executebuiltin("SetFocus({0})".format(COMING_UP_MENU))
        else:
            earlier = [stop for stop in stops if stop < self.coming_up_offset]
            if self.coming_up_offset:
                self.coming_up_offset = earlier[-1] if earlier else 0
                self.update_coming_up_lines()
                self.coming_up_focus_line(range(1, room + 1))
            else:
                xbmc.executebuiltin("SetFocus({0})".format(COMING_UP_MENU))

    def coming_up_focus_line(self, order):
        """
        <summary>
        Put focus on the first line, in the order given, that has something to choose.
        </summary>
        <param name="order">Line numbers to try, first choice first.</param>
        <remarks>
        COMING-UP-SCROLL. An item line takes its tall button and a slot line its
        short one; headings, Ends At lines and padding have none. Falls back to the
        menu row when no line has one.
        </remarks>
        """
        home = xbmcgui.Window(HOME_WINDOW_ID)
        for number in order:
            kind = home.getProperty("ComingUp.{0}.Kind".format(number))
            if kind == "item":
                xbmc.executebuiltin("SetFocus({0})".format(COMING_UP_TALL + number))
                return
            if kind == "slot":
                xbmc.executebuiltin("SetFocus({0})".format(COMING_UP_SHORT + number))
                return
        xbmc.executebuiltin("SetFocus({0})".format(COMING_UP_MENU))

    # ---- Next Up (the next unwatched episode per show in progress) --------

    def update_next_up(self):
        """
        <summary>
        Keep the Next Up row of the Continue Watching pop-up current: the
        next unwatched episode of each show the viewer is part way through,
        most recently played show first, as NextUp.N.* Home properties.
        </summary>
        <remarks>
        Fast ticker, cheap when nothing is due. A lookup runs on a daemon
        thread every NEXTUP_REFRESH_SECS, and sooner after a library event or a stopped
        playback because onNotification zeroes the timer: finishing an
        episode is exactly what moves a show along. Hidden by hide_continue
        or hide_nextup, in which case the slots are cleared once and nothing
        is queried until the row is shown again. Kodi has no library node for
        "next unwatched per show", so this is the one Continue row served as
        fixed slots rather than as a smart playlist container; a click and
        the press and hold menu go through continue_command like the other
        two rows. NextUp.Count follows the convention _publish_cast documents:
        cleared means not looked up, "0" means looked up and empty.
        </remarks>
        """
        hidden = (xbmc.getCondVisibility("Skin.HasSetting(hide_continue)")
                  or xbmc.getCondVisibility("Skin.HasSetting(hide_nextup)"))
        if hidden:
            if self._nextup_slots_used or self._nextup_items:
                self._nextup_publish([], looked_up=False)
            self._nextup_last = 0.0
            return
        if time.time() - self._nextup_last < self.NEXTUP_REFRESH_SECS:
            return
        if self._nextup_thread is not None and self._nextup_thread.is_alive():
            return
        self._nextup_last = time.time()
        self._nextup_thread = threading.Thread(
            target=self._nextup_worker, name="functional-nextup", daemon=True)
        self._nextup_thread.start()

    def _nextup_worker(self):
        """
        <summary>
        Daemon thread body: find the next unwatched episode of each show in
        progress and publish the slots.
        </summary>
        <remarks>
        One query for the shows (Kodi's own "inprogress" filter: some
        episodes watched, some not, newest played first) and one per show for
        its first unwatched episode, so at most NEXTUP_MAX * 2 + 1 calls. A
        show whose first unwatched episode carries a resume point is skipped:
        that episode already sits in the Continue episodes row, and "next up"
        for it would be the very same episode. Specials never count as next.
        A failed lookup is logged and retried half a minute later rather than
        on the next tick, so a sleeping database is not hammered.
        </remarks>
        """
        try:
            resp = _jsonrpc("VideoLibrary.GetTVShows", {
                "filter": {"field": "inprogress", "operator": "true", "value": ""},
                "sort": {"method": "lastplayed", "order": "descending"},
                "limits": {"start": 0, "end": self.NEXTUP_MAX * 2},
                "properties": ["title", "art"]})
            shows = _result_rows(resp, "tvshows")
            items = []
            for show in shows:
                if len(items) >= self.NEXTUP_MAX:
                    break
                episode = self._nextup_episode(show.get("tvshowid"))
                if episode is None:
                    continue
                art = episode.get("art") or {}
                items.append({
                    "dbid": self._safe_int(episode.get("episodeid"), 0),
                    "label": episode.get("title") or "",
                    # Marker first: the caption box is 140 wide, and with
                    # the show name leading, "Breaking Bad S5E14" was cut to
                    # "Breaking Ba..." so the row never said which episode.
                    "sub": "S{1}E{2} \u00b7 {0}".format(
                        show.get("title") or episode.get("showtitle") or "",
                        self._safe_int(episode.get("season"), 0),
                        self._safe_int(episode.get("episode"), 0)),
                    "thumb": (art.get("tvshow.poster") or art.get("season.poster")
                              or (show.get("art") or {}).get("poster")
                              or art.get("thumb") or ""),
                })
            self._nextup_publish(items)
            _dlog("next up: {0} row(s) from {1} show(s) in progress".format(
                len(items), len(shows)))
        except LookupError as exc:
            # The library did not answer: leave the row as it is and look
            # again in half a minute. Before _result_rows a failed query read
            # as "no shows in progress" and emptied the row for five minutes.
            _dlog("next up: {0}, keeping the current row".format(exc),
                  xbmc.LOGWARNING)
            self._nextup_last = time.time() - self.NEXTUP_REFRESH_SECS + 30
        except Exception:  # noqa: BLE001
            _dlog("next up lookup failed:\n" + traceback.format_exc(), xbmc.LOGERROR)
            self._nextup_last = time.time() - self.NEXTUP_REFRESH_SECS + 30

    def _nextup_episode(self, tvshowid):
        """
        <summary>
        The first unwatched regular episode of one show, or None.
        </summary>
        <param name="tvshowid">Library id of the show.</param>
        <returns>The episode record, or None when the show has no unwatched
        regular episode or its first one is already part way through.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        """
        if not tvshowid:
            return None
        resp = _jsonrpc("VideoLibrary.GetEpisodes", {
            "tvshowid": tvshowid,
            "filter": {"and": [
                {"field": "playcount", "operator": "is", "value": "0"},
                {"field": "season", "operator": "greaterthan", "value": "0"}]},
            "sort": {"method": "episode", "order": "ascending"},
            "limits": {"start": 0, "end": 1},
            "properties": ["title", "season", "episode", "showtitle", "art", "resume"]})
        episodes = _result_rows(resp, "episodes")
        if not episodes:
            return None
        try:
            position = float((episodes[0].get("resume") or {}).get("position") or 0)
        except (TypeError, ValueError):
            position = 0.0
        return None if position > 0 else episodes[0]

    def _nextup_publish(self, items, looked_up=True):
        """
        <summary>
        Write the NextUp.N.* slots and NextUp.Count, clearing slots that
        were used last time and are empty now.
        </summary>
        <param name="items">Records from _nextup_worker, in row order.</param>
        <param name="looked_up">False clears NextUp.Count (row hidden, nothing known) instead of writing "0".</param>
        """
        win = xbmcgui.Window(HOME_WINDOW_ID)
        with self._nextup_lock:
            self._nextup_items = list(items)
            used_before = self._nextup_slots_used
            for i in range(max(len(items), used_before)):
                n = i + 1
                if i < len(items):
                    it = items[i]
                    win.setProperty("NextUp.%d.Label" % n, it["label"])
                    win.setProperty("NextUp.%d.Sub" % n, it["sub"])
                    win.setProperty("NextUp.%d.Thumb" % n, it["thumb"])
                    win.setProperty("NextUp.%d.DBID" % n, str(it["dbid"]))
                else:
                    for key in ("Label", "Sub", "Thumb", "DBID"):
                        win.clearProperty("NextUp.%d.%s" % (n, key))
            self._nextup_slots_used = len(items)
            if looked_up:
                win.setProperty("NextUp.Count", str(len(items)))
            else:
                win.clearProperty("NextUp.Count")

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
    # Appended to the lists file's path for the copy of it as it stood before
    # the most recent save, see _lists_save and _lists_load.
    LISTS_PREVIOUS_SUFFIX = ".previous"
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
    # LISTS-GROUPS: a whole show or season kept as one row. It is stored by
    # library id alone (a videodb:// path names nothing on another box) and
    # stands for its episodes, which are fetched afresh whenever the list is
    # ported, so episodes added to the library later are included.
    LIST_GROUP_TYPES = ("tvshow", "season")
    LIST_ITEM_PROPS = ("label", "file", "dbtype", "dbid", "thumb", "duration",
                       "show", "season", "episode", "artist", "year", "kind",
                       "count")

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
        the feature must degrade to "no lists yet". An unreadable or empty
        file is set aside first so that the next save cannot write over it,
        see _lists_set_aside, and the session then starts from the previous
        copy kept beside it (LISTS_PREVIOUS_SUFFIX) when that one reads, or
        from an empty set when it does not.
        </remarks>"""
        with self._lists_lock:
            if self._lists is not None and not force:
                return self._lists
            lists, last, sort = [], "", ""
            broken = False
            path = self._lists_path()
            # Plain open(), not xbmcvfs.File: the profile folder is always a
            # local path, and xbmcvfs.File().read() answers a failed open
            # with an empty string instead of raising. That empty string then
            # parsed as "no lists", nothing was set aside, and the next save
            # wrote the emptiness over the real file. A file that exists but
            # is empty (a power cut mid write on some filesystems) is treated
            # the same way: unreadable, never "no lists".
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        lists, last, sort = self._lists_parse(fh.read())
                except Exception:  # noqa: BLE001
                    _dlog("lists.json unreadable:\n" + traceback.format_exc(),
                          xbmc.LOGWARNING)
                    lists, last, sort = [], "", ""
                    broken = True
            previous = path + self.LISTS_PREVIOUS_SUFFIX
            if broken or (not os.path.exists(path) and os.path.exists(previous)):
                # The copy _lists_save keeps of the file as it was before the
                # last write. Losing one edit beats losing every list. The
                # second case is a save interrupted between its two renames:
                # the main file is gone for a moment and only this one exists.
                try:
                    with open(previous, "r", encoding="utf-8") as fh:
                        lists, last, sort = self._lists_parse(fh.read())
                    _dlog("lists: using the previous copy, %d lists" % len(lists),
                          xbmc.LOGWARNING)
                except Exception:  # noqa: BLE001
                    lists, last, sort = [], "", ""
            self._lists = lists
            self._lists_sort_mode = sort
            self._lists_order_locked()
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

    def _lists_parse(self, text):
        """
        <summary>
        Parse the text of a lists.json into clean list records.
        </summary>
        <param name="text">The file's contents.</param>
        <returns>(lists, last, sort): the list dicts, the remembered last
        list name and the kept order (a LISTS_SORTS mode, "" for none).</returns>
        <exception cref="ValueError">On anything that is not the expected JSON shape; callers decide what an unreadable file means.</exception>
        <remarks>
        Shared by the loader and the importer, so a file exported from
        another box is read exactly as this box's own. "fill" is the Port by
        Time length in minutes, remembered per list; 0 means never set, so
        the dialog opens on LIST_FILL_DEFAULT, and it is clamped because
        _parse_hhmm tops out at 23:59. "autoremove" is the per list Remove
        Watched switch; a file written before it existed reads as off.
        "radarr" marks the one list whose films Remove from Radarr acts on,
        see _radarr_pick_list; it also reads as off when missing, and only
        the first list carrying it keeps it. "seq" is the list's creation
        number on this box, what Sort Lists orders by for newest and oldest
        (LISTS-SORT). A file written before it existed has none; its lists
        are numbered in file order, which was creation order, because
        nothing could reorder lists until Sort Lists arrived. "sort" is the
        order Sort Lists keeps the lists in; an unknown or missing one reads
        as none, which leaves them in file order. A name already used by an
        earlier list, ignoring case, is renamed with a number in brackets
        and logged: the TV's name prompt and the API both refuse such a
        name, but an import used to create one, and dropping the list on
        the way in would lose its items.
        </remarks>
        """
        if not (text or "").strip():
            raise ValueError("lists.json is empty")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("lists.json is not an object")
        if not isinstance(data.get("lists"), list):
            # Every file this skin writes has the key, even with no lists in
            # it. Its absence means some other JSON file, or a damaged one;
            # reading that as "no lists" is how an import of the wrong file
            # used to report success.
            raise ValueError("lists.json has no lists array")
        lists = []
        for entry in data.get("lists", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            items = [self._list_item_clean(it) for it in entry.get("items", []) or []]
            try:
                fill = int(entry.get("fill") or 0)
            except (TypeError, ValueError):
                fill = 0
            radarr = bool(entry.get("radarr")) and not any(
                l["radarr"] for l in lists)
            try:
                seq = max(int(entry.get("seq") or 0), 0)
            except (TypeError, ValueError):
                seq = 0
            wanted, number = name, 2
            while any(l["name"].lower() == name.lower() for l in lists):
                name = "%s (%d)" % (wanted, number)
                number += 1
            if name != wanted:
                _dlog("lists: %r is already a list's name ignoring case, read as %r"
                      % (wanted, name), xbmc.LOGWARNING)
            lists.append({"name": name,
                          "items": [it for it in items if it],
                          "fill": min(max(fill, 0), 23 * 60 + 59),
                          "autoremove": bool(entry.get("autoremove")),
                          "radarr": radarr,
                          "seq": seq})
        # Unnumbered lists (an older file) follow the numbered ones in file
        # order, and a repeated number is renumbered, so every list has its
        # own and the newest and oldest sorts are never left to chance.
        seen = set()
        top = max([l["seq"] for l in lists] or [0])
        for lst in lists:
            if not lst["seq"] or lst["seq"] in seen:
                top += 1
                lst["seq"] = top
            seen.add(lst["seq"])
        sort = str(data.get("sort", "") or "")
        if sort not in self.LISTS_SORT_MODES:
            sort = ""
        return lists, str(data.get("last", "") or ""), sort

    def _lists_export(self, folder=""):
        """
        <summary>
        Copy lists.json to a folder of the user's choosing, so another box
        can import it.
        </summary>
        <param name="folder">Destination folder; empty asks with Kodi's folder browser.</param>
        <remarks>Dialog thread. The file is saved first so the copy carries
        the in-memory state, then copied with xbmcvfs so any share Kodi can
        write to is a valid destination.</remarks>
        """
        if not folder:
            folder = xbmcgui.Dialog().browse(3, _L(31483), "files")
        if not folder:
            return
        if not folder.endswith(("/", "\\")):
            folder += "/"
        self._lists_save()
        if self._lists_frozen:
            # The save was refused because the file on disk is unreadable
            # and could not be moved aside. Copying that file out and
            # announcing an export would hand over the damaged one.
            self._lists_notify(_L(31487), True)
            return
        dest = folder + "lists.json"
        if xbmcvfs.copy(self._lists_path(), dest):
            _dlog("lists exported to %s" % dest)
            self._lists_notify(_L(31485) % folder)
        else:
            _dlog("lists export to %s failed" % dest, xbmc.LOGERROR)
            self._lists_notify(_L(31487), True)

    def _lists_import(self, path=""):
        """
        <summary>
        Merge another box's lists.json into this one: lists are matched by
        name, new lists are added, and items already in a list are skipped.
        </summary>
        <param name="path">The file to read; empty asks with Kodi's file browser.</param>
        <remarks>Dialog thread. Nothing here is ever removed, so importing
        twice is harmless, and the caps LISTS_MAX and LIST_ITEMS_MAX hold.
        Each incoming item's library id is checked against this box first,
        see _list_item_localise: the file may come from a box with its own
        video database, where id 12 is a different film. An incoming list
        whose name is here already under another case ("films" against
        "Films") is skipped, counted in a second toast and logged, since
        the name prompt and the API both refuse a name taken ignoring case
        and this used to be the one way to make such a pair.</remarks>
        """
        if not path:
            path = xbmcgui.Dialog().browse(1, _L(31484), "files", ".json")
        if not path:
            return
        try:
            with xbmcvfs.File(path) as fh:
                # The kept order belongs to this box, not to the file.
                incoming, _last, _sort = self._lists_parse(fh.read())
        except Exception:  # noqa: BLE001
            _dlog("lists import of %s failed:\n%s" % (path, traceback.format_exc()),
                  xbmc.LOGWARNING)
            self._lists_notify(_L(31488), True)
            return
        # Library ids belong to the box that wrote the file. Check each one
        # against this box's library before anything is merged, off the lock
        # because it is one query per item.
        dropped = 0
        for entry in incoming:
            checked = []
            for item in entry["items"]:
                item = self._list_item_localise(item)
                if item is None:
                    dropped += 1
                else:
                    checked.append(item)
            entry["items"] = checked
        new_lists = new_items = clashed = 0
        with self._lists_lock:
            lists = self._lists if self._lists is not None else []
            for entry in incoming:
                target = next((l for l in lists if l["name"] == entry["name"]), None)
                if target is None and any(l["name"].lower() == entry["name"].lower()
                                          for l in lists):
                    clashed += 1
                    _dlog("lists import: %r skipped, a list of that name is here "
                          "under another case" % entry["name"], xbmc.LOGWARNING)
                    continue
                if target is None:
                    if len(lists) >= self.LISTS_MAX:
                        continue
                    # "radarr" is never carried over: which list sends
                    # films to be deleted is chosen on this box, not by a file.
                    # Its number on the other box means nothing here: an
                    # imported list is new to this box, so it sorts newest.
                    target = {"name": entry["name"], "items": [], "fill": entry["fill"],
                              "autoremove": entry["autoremove"], "radarr": False,
                              "seq": self._lists_next_seq(lists)}
                    lists.append(target)
                    new_lists += 1
                for item in entry["items"]:
                    if len(target["items"]) >= self.LIST_ITEMS_MAX:
                        break
                    if any(self._list_item_same(item, it) for it in target["items"]):
                        continue
                    target["items"].append(item)
                    new_items += 1
            self._lists = lists
        self._lists_save()
        _dlog("lists imported from %s: %d new list(s), %d new item(s), "
              "%d item(s) this library does not have, %d list(s) skipped" % (
                  path, new_lists, new_items, dropped, clashed))
        self._lists_notify(_L(31486) % (new_lists, new_items))
        if clashed:
            self._lists_notify(_L(31665) % clashed, True)

    # dbtype -> (JSON-RPC details method, its id parameter, the key the
    # record comes back under), for _list_item_localise.
    LIST_DETAIL_CALLS = {
        "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"),
        "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"),
        "musicvideo": ("VideoLibrary.GetMusicVideoDetails", "musicvideoid",
                       "musicvideodetails"),
        "song": ("AudioLibrary.GetSongDetails", "songid", "songdetails"),
    }

    def _list_group_localise(self, item):
        """<summary>Find an imported show or season row in this box's
        library by title, since its ids belong to the box that wrote it
        (LISTS-GROUPS).</summary>
        <param name="item">A clean tvshow or season record. Modified in place.</param>
        <returns>The record carrying this box's id, or None when this box
        has no show of that title, or not that season of it.</returns>
        <remarks>A group row has no path to fall back on, so the show title
        stored with it is the match: the id it came with is kept when it
        names a show of the same title here, otherwise the first show of
        that exact title is used.</remarks>"""
        title = item["show"] or (item["label"] if item["dbtype"] == "tvshow" else "")
        if not title:
            return None
        if item["dbtype"] == "tvshow":
            resp = _jsonrpc("VideoLibrary.GetTVShowDetails", {
                "tvshowid": item["dbid"], "properties": ["title"]})
            det = ((resp or {}).get("result") or {}).get("tvshowdetails") or {}
            if det.get("title") == title:
                return item
        else:
            resp = _jsonrpc("VideoLibrary.GetSeasonDetails", {
                "seasonid": item["dbid"], "properties": ["showtitle", "season"]})
            det = ((resp or {}).get("result") or {}).get("seasondetails") or {}
            if (det.get("showtitle") == title
                    and str(det.get("season")) == item["season"]):
                return item
        resp = _jsonrpc("VideoLibrary.GetTVShows", {
            "properties": ["title"],
            "filter": {"field": "title", "operator": "is", "value": title}})
        shows = ((resp or {}).get("result") or {}).get("tvshows") or []
        showid = next((int(sh["tvshowid"]) for sh in shows
                       if sh.get("title") == title), 0)
        if not showid:
            return None
        if item["dbtype"] == "tvshow":
            item["dbid"] = showid
            return item
        resp = _jsonrpc("VideoLibrary.GetSeasons", {
            "tvshowid": showid, "properties": ["season"]})
        seasons = ((resp or {}).get("result") or {}).get("seasons") or []
        match = next((int(se["seasonid"]) for se in seasons
                      if str(se.get("season")) == item["season"]), 0)
        if not match:
            return None
        item["dbid"] = match
        return item

    def _list_item_localise(self, item):
        """
        <summary>
        Make an imported item safe to use on this box: keep its library id
        only when this box's library has the same file under that id.
        </summary>
        <param name="item">A clean record from _lists_parse. Modified in place.</param>
        <returns>
        The record, with its id cleared when it does not belong here, or
        None when it has neither a usable id nor a path and so cannot be
        played or identified at all.
        </returns>
        <remarks>
        A record is played, compared for duplicates and matched by Remove
        Watched through its id whenever it has one. Carried over unchecked
        from another box, id 12 queued whatever film is 12 here under the
        original title and poster, was skipped as "already present" when a
        different film happened to share the number, and could take the
        wrong row off a list. A record whose id does not check out falls
        back to its path, which every captured item carries. One query per
        item with an id, which is why import runs on the dialog thread.
        </remarks>
        """
        if item["dbtype"] in self.LIST_GROUP_TYPES:
            return self._list_group_localise(item)
        call = self.LIST_DETAIL_CALLS.get(item["dbtype"])
        if not item["dbid"] or call is None:
            return item if item["file"] else None
        method, id_key, result_key = call
        resp = _jsonrpc(method, {id_key: item["dbid"], "properties": ["file"]})
        details = ((resp or {}).get("result") or {}).get(result_key) or {}
        here = details.get("file") or ""
        if item["file"]:
            if here == item["file"]:
                return item
        elif here and (details.get("label") or "") == item["label"]:
            # No path was stored, so the title is the only thing to go on.
            return item
        item["dbid"] = 0
        return item if item["file"] else None

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
        <remarks>Writes go to a temp file first, are flushed to disk and
        are renamed over the real one, so a crash mid-write cannot leave a
        truncated file. The file being replaced is kept beside it under
        LISTS_PREVIOUS_SUFFIX. Refused while _lists_frozen is set: the file
        on disk could not be read and could not be moved aside, so writing
        would destroy it; each call tries the move again first. The kept
        order (LISTS-SORT) is applied first, even when the save is refused,
        so the screen always shows it. Must not be called with _lists_lock
        held.</remarks>"""
        path = self._lists_path()
        # One writer at a time, from building the text to the rename. The
        # loop (a watched removal) and the dialog thread (any edit) can both
        # be here; with the text built under one lock and written outside
        # it, the older text could land last, and two writers sharing one
        # temp name could have the second rename fail and toast a save
        # error for a save that had worked.
        with self._lists_io_lock:
            with self._lists_lock:
                if self._lists_frozen:
                    # Try again to move the unreadable file aside (or notice
                    # that it has gone). Only then is it safe to write; this
                    # is the "later" the freeze was waiting for, which used
                    # never to come short of restarting Kodi.
                    if os.path.exists(path):
                        self._lists_set_aside(path)
                    else:
                        self._lists_frozen = False
                frozen = self._lists_frozen
                # LISTS-SORT: every change lands here, so this is where the
                # kept order is put back, and the moved selection noted.
                moved = self._lists_order_locked()
                payload = json.dumps({"version": 1, "last": self._lists_last,
                                      "sort": self._lists_sort_mode,
                                      "lists": self._lists or []},
                                     ensure_ascii=False, indent=1)
            if frozen:
                _dlog("lists.json save refused: the file on disk is unreadable "
                      "and could not be set aside", xbmc.LOGERROR)
                return
            tmp = path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                if os.path.exists(path):
                    # Keep the file as it stood before this write. A rename,
                    # so it costs nothing and cannot be half done; _lists_load
                    # falls back to it when the main file will not read.
                    os.replace(path, path + self.LISTS_PREVIOUS_SUFFIX)
                os.replace(tmp, path)
            except OSError:
                _dlog("lists.json write failed:\n" + traceback.format_exc(),
                      xbmc.LOGERROR)
                xbmcgui.Dialog().notification(
                    _L(31024), _L(31333),
                    xbmcgui.NOTIFICATION_ERROR, 4000)
        self._set_or_reset("lists_last", self._lists_last)
        self._lists_publish()
        if moved:
            self._lists_follow(*moved)

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
        if it["dbtype"] in cls.LIST_GROUP_TYPES:
            # LISTS-GROUPS: no id, nothing to stand for ("All seasons" is -1).
            if it["dbid"] <= 0:
                return None
            it["file"] = ""
            it["kind"] = "video"
        elif it["dbtype"] not in cls.LIST_DBID_KEYS:
            it["dbid"] = 0
        try:
            it["duration"] = int(it["duration"] or 0)
        except ValueError:
            it["duration"] = _parse_duration_to_seconds(it["duration"])
        try:
            it["count"] = int(it["count"] or 0)
        except ValueError:
            it["count"] = 0
        if it["dbtype"] in cls.LIST_GROUP_TYPES:
            # Episodes Remove Watched has taken out of this show or season,
            # as "season x episode" keys, which mean the same on any box.
            skip = raw.get("skip") or []
            it["skip"] = sorted({str(k) for k in skip if isinstance(k, str)
                                 and re.match(r"^\d+x\d+$", k)}) \
                if isinstance(skip, list) else []
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
        if it["dbtype"] in cls.LIST_GROUP_TYPES:
            # LISTS-GROUPS: "Whole show · 62 episodes · 46h 10m".
            bits.append(_L(31647) if it["dbtype"] == "tvshow" else _L(31648))
            if it["count"]:
                bits.append((_L(31649) if it["count"] == 1
                             else _L(31650)) % it["count"])
        elif it["dbtype"] == "episode" or (it["show"] and it["episode"]):
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
        for the left column, and refresh the selected list's items.</summary>
        <remarks>Holds _lists_pub_lock throughout: the loop and the dialog
        thread both publish, and interleaved they could leave the right
        column showing rows from two different states, with item:N then
        acting on a row other than the one on screen.</remarks>"""
        with self._lists_pub_lock:
            self._lists_publish_locked()

    def _lists_publish_locked(self):
        """<summary>Body of _lists_publish; the caller holds
        _lists_pub_lock.</summary>"""
        win = xbmcgui.Window(HOME_WINDOW_ID)
        with self._lists_lock:
            lists = list(self._lists or [])
        shown = lists[:self.LISTS_MAX]
        win.setProperty("Lists.Count", str(len(shown)))
        # LISTS-SORT: the kept order, shown on the Sort Lists button.
        sid = self.LISTS_SORT_MODES.get(self._lists_sort_mode, (0, 0))[1]
        win.setProperty("Lists.SortLabel", _L(sid) if sid else "")
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
                if lst.get("autoremove"):
                    sub += " · " + _L(31505)
                if lst.get("radarr"):
                    sub += " · " + _L(31581)
                win.setProperty("Lists.%d.Name" % n, lst["name"])
                win.setProperty("Lists.%d.Sub" % n, sub)
            else:
                win.clearProperty("Lists.%d.Name" % n)
                win.clearProperty("Lists.%d.Sub" % n)
        self._lists_slots_used = len(shown)
        # Every change to the lists ends up here, so this is where the
        # playback tracker learns whether it has anything to watch for.
        self._lists_autoremove_any = any(l.get("autoremove") for l in lists)
        # The Radarr settings page shows the tied list by name, and a rename
        # or a removal lands here like every other change.
        self._radarr_publish(lists)
        # The selection may now point past the end (a delete) or at a
        # different list (an insert), so redo the right column regardless.
        self._lists_sel_pub = None
        self._list_items_publish(self._lists_sel)

    def _list_items_publish(self, idx):
        """<summary>Fill the right column (LI.N.*) with list number idx's
        items and the Lists.Sel.* heading.</summary>
        <param name="idx">1-based index into the lists, 0 or out of range clears.</param>"""
        with self._lists_pub_lock:
            self._list_items_publish_locked(idx)

    def _list_items_publish_locked(self, idx):
        """<summary>Body of _list_items_publish; the caller holds
        _lists_pub_lock.</summary>
        <param name="idx">1-based index into the lists, 0 or out of range clears.</param>
        <remarks>Records the index it was ASKED for as published, even when
        that index names no list. Recording 0 instead made an empty Lists
        screen look permanently out of date to update_lists, which then
        rewrote seven properties on every tick for as long as it was open.</remarks>"""
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
        # On / Off for the Remove Watched button's label.
        win.setProperty("Lists.Sel.AutoRemove",
                        (_L(31503) if lst.get("autoremove") else _L(31504))
                        if lst else "")
        # "1" on the list tied to Radarr: its List Options drop down
        # gains Remove from Radarr.
        win.setProperty("Lists.Sel.Radarr",
                        "1" if lst and lst.get("radarr") else "")
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
        self._lists_sel_pub = idx

    def update_lists(self):
        """<summary>Fast-tick handler for the Lists feature: runs queued
        list_command values on the dialog thread and keeps the Lists
        screen's right column following the focused list.</summary>
        <remarks>Commands: add_last, add_pick (item in list_item_* Home
        properties); new, rename, delete, port, port_shuffle, port_time
        (act on the selected list); autoremove (flip the selected list's
        Remove Watched switch); radarr_remove (send the selected list's
        films to Radarr to be removed) and the Radarr settings page's
        radarr_url, radarr_key, radarr_list, radarr_dryrun, radarr_test and
        radarr_log; item:N (action menu for row N of the
        selected list); item_up:N, item_down:N and item_del:N (the row's
        quick buttons, LISTS-QUICK in Custom_1151_Lists.xml; remove asks
        first); shuffle (put the selected list in a random order, after a
        confirm); sort (pick the order the lists are kept in,
        LISTS-SORT); save_queue (the open queue window becomes a new
        list). Each tick also runs the Remove Watched tracker, whatever
        window is up, because watching happens away from this screen.
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
        self._lists_track_playback()
        self._lists_drain_watched()
        if not xbmc.getCondVisibility(
                "Window.IsActive(%d)" % self.LISTS_WINDOW_ID):
            return
        try:
            sel = int(xbmc.getInfoLabel(
                "Container(50).ListItem.Property(idx)") or 0)
        except ValueError:
            sel = 0
        hold = self._lists_sel_hold
        if hold and (sel == hold[0] or time.monotonic() > hold[1]):
            self._lists_sel_hold = hold = None
        # While the cursor is on its way to a list's new row, the row it
        # is leaving holds another list now; following it would fill the
        # right column with that one for a tick.
        if sel and not hold:
            self._lists_sel = sel
        if self._lists_sel != self._lists_sel_pub:
            self._list_items_publish(self._lists_sel)

    def update_lists_api(self):
        """
        <summary>
        Slow tick handler for LISTS-API: keep the lists' add-on API running
        while Skin Settings, Lists, "Let JellyStat manage the lists" is on.
        </summary>
        <remarks>
        The switch is stored inverted, as lists_api_off, so that it reads as
        on before anyone has touched it: the spec's default, and safe because
        the server only listens on the box itself and JellyStat's password is
        the real gate. lists_api.sync costs nothing when nothing has changed.
        The server's threads call back into this helper's list methods under
        its own locks; see lists_api.py. Nothing is started while the
        startup splash is still up: announcing the server writes a Home
        window property, which is the write the crash dumps on record
        implicate during the Startup to Home transition, so this waits for
        the splash to go as a belt beside the three second grace in run().
        </remarks>
        """
        if xbmc.getCondVisibility("Window.IsActive(startup)"):
            return
        lists_api.sync(self, not xbmc.getCondVisibility("Skin.HasSetting(lists_api_off)"))

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
        elif cmd == "autoremove":
            self._lists_toggle_autoremove()
        elif cmd == "radarr_remove":
            self._radarr_remove_list()
        elif cmd == "radarr_url":
            self._radarr_ask_url()
        elif cmd == "radarr_key":
            self._radarr_ask_key()
        elif cmd == "radarr_list":
            self._radarr_pick_list()
        elif cmd == "radarr_dryrun":
            self._radarr_toggle_dry_run()
        elif cmd == "radarr_test":
            self._radarr_test()
        elif cmd == "radarr_log":
            self._radarr_view_log()
        elif cmd.startswith("item:"):
            self._lists_item_menu(cmd[5:])
        elif cmd.startswith(("item_up:", "item_down:", "item_del:")):
            self._lists_item_quick(*cmd.split(":", 1))
        elif cmd == "shuffle":
            self._lists_shuffle()
        elif cmd == "sort":
            self._lists_sort()
        elif cmd == "save_queue":
            self._lists_save_queue()
        elif cmd == "export":
            self._lists_export()
        elif cmd.startswith("export:"):
            self._lists_export(cmd[7:])
        elif cmd == "import":
            self._lists_import()
        elif cmd.startswith("import:"):
            self._lists_import(cmd[7:])
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

    @staticmethod
    def _lists_next_seq(lists):
        """<summary>The creation number for a list about to be added
        (LISTS-SORT).</summary>
        <param name="lists">The lists it is joining.</param>
        <returns>One more than the highest number in use, 1 for the first.</returns>
        <remarks>The highest rather than the count, so a list removed
        earlier never lets a new one share a number with an old one.</remarks>"""
        return max([l.get("seq") or 0 for l in lists] or [0]) + 1

    def _lists_create(self, name, items=None):
        """<summary>Append a new list and save.</summary>
        <param name="name">The new list's name, already checked as unused.</param>
        <param name="items">Records to start it with; none when omitted.</param>
        <returns>Non zero when the list was made, 0 when there is no room.
        Not its place: a kept sort (LISTS-SORT) moves it on save.</returns>
        <remarks>LISTS_MAX is the number of rows the Lists screen has. A
        list beyond it would be saved and become the quick add target with
        no row to show it on, so it could never be ported, renamed or
        removed. Callers must check for 0.</remarks>"""
        with self._lists_lock:
            if len(self._lists) >= self.LISTS_MAX:
                idx = 0
            else:
                self._lists.append({"name": name, "items": list(items or []),
                                    "fill": 0, "autoremove": False,
                                    "radarr": False,
                                    "seq": self._lists_next_seq(self._lists)})
                idx = len(self._lists)
                self._lists_last = name
        if not idx:
            self._lists_notify(_L(31574) % self.LISTS_MAX, True)
            return 0
        self._lists_save()
        return idx

    def _lists_add(self, pick):
        """<summary>Add the captured item to the last-used list, or to a
        list the user picks (with "New list" as the final choice).</summary>
        <param name="pick">True to always show the picker.</param>"""
        item = self._lists_capture_item()
        if item is not None and item["dbtype"] in self.LIST_GROUP_TYPES:
            item = self._list_group_fill(item)
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
            # 31049 is "Add To List". This used to pass 31050, which is the
            # on-screen keyboard's Shift key, so the picker was titled Shift.
            choice = xbmcgui.Dialog().select(_L(31049), names)
            if choice < 0:
                return
            if choice == len(lists):
                name = self._lists_ask_name(_L(31338))
                if not name:
                    return
                if not self._lists_create(name):
                    return
                # By name, not as the last list: a kept sort (LISTS-SORT)
                # has already put the new one in its place.
                with self._lists_lock:
                    target = next(l for l in self._lists if l["name"] == name)
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
        count = len(lst["items"])
        question = (_L(31575) % lst["name"] if count == 1
                    else _L(31344) % (lst["name"], count))
        if not xbmcgui.Dialog().yesno(_L(31343), question):
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

    # ---- Lists: whole shows and seasons (LISTS-GROUPS) ----------------------
    #
    # <summary>
    # A show or season added from the library is one row on its list and
    # plays as if every one of its episodes were listed in its place, in
    # season and episode order.
    # </summary>
    # <remarks>
    # The row is expanded at the moment it is used, never when it is added,
    # so the list stays short and a show that gains episodes plays them
    # too. Port and Play now queue every episode in order. The random ports
    # (Port Shuffled, Port by Time) treat the row as ONE item, as asked on
    # 13/10/2026: it is drawn like any other row and puts in one random
    # episode, so a show added whole gives one episode and the same show
    # added as two seasons gives two. A whole show leaves out season 0
    # (Specials), as Kodi's own listing does; a Specials season added on
    # its own plays in full.
    #
    # On a Remove Watched list an episode watched after the row was added
    # leaves the row exactly as a single item would leave the list: its
    # "season x episode" key goes into the row's "skip" and it is never
    # queued again. The row itself goes once nothing is left in it.
    # Episodes watched before the row was added are not touched.
    # </remarks>
    LIST_EPISODE_PROPS = ["title", "file", "runtime", "season", "episode",
                          "showtitle", "thumbnail", "art", "playcount"]

    @staticmethod
    def _list_group_where(it):
        """<summary>Which show, and which season of it, a group row names.</summary>
        <param name="it">A stored tvshow or season record.</param>
        <returns>(tvshowid, season number or None for the whole show), or
        (0, None) when the library no longer has it.</returns>"""
        if it["dbtype"] == "tvshow":
            return it["dbid"], None
        resp = _jsonrpc("VideoLibrary.GetSeasonDetails", {
            "seasonid": it["dbid"], "properties": ["tvshowid", "season"]})
        det = ((resp or {}).get("result") or {}).get("seasondetails") or {}
        showid = det.get("tvshowid") or 0
        if not showid or det.get("season") is None:
            return 0, None
        return int(showid), int(det["season"])

    def _list_group_episodes(self, it):
        """<summary>The episodes a show or season row stands for, in order.</summary>
        <param name="it">A stored tvshow or season record.</param>
        <returns>Episode rows from VideoLibrary.GetEpisodes, sorted by season
        then episode, less any Remove Watched has taken out of the row;
        empty when the show or season has gone.</returns>"""
        showid, season = self._list_group_where(it)
        if not showid:
            return []
        params = {"tvshowid": showid, "properties": self.LIST_EPISODE_PROPS}
        if season is not None:
            params["season"] = season
        resp = _jsonrpc("VideoLibrary.GetEpisodes", params)
        rows = ((resp or {}).get("result") or {}).get("episodes") or []
        if season is None:
            rows = [r for r in rows if self._safe_int(r.get("season"), 0) > 0]
        skip = set(it.get("skip") or [])
        if skip:
            rows = [r for r in rows if self._list_episode_key(r) not in skip]
        rows.sort(key=lambda r: (self._safe_int(r.get("season"), 0),
                                 self._safe_int(r.get("episode"), 0)))
        return rows

    def _list_episode_key(self, row):
        """<summary>The "season x episode" key a group row's skip uses.</summary>
        <param name="row">An episode row from the library.</param>"""
        return "%dx%d" % (self._safe_int(row.get("season"), 0),
                          self._safe_int(row.get("episode"), 0))

    def _list_group_fill(self, item):
        """<summary>Complete a just captured show or season row from the
        library: a label that says which show, the poster, and the episode
        count and running time shown under it.</summary>
        <param name="item">A clean tvshow or season record.</param>
        <returns>The record, or None when it has no episodes to play.</returns>
        <remarks>The count and time are a snapshot for the Lists screen
        only; what gets played is worked out again at port time.</remarks>"""
        if item["dbtype"] == "tvshow":
            resp = _jsonrpc("VideoLibrary.GetTVShowDetails", {
                "tvshowid": item["dbid"], "properties": ["title", "art", "year"]})
            det = ((resp or {}).get("result") or {}).get("tvshowdetails") or {}
            title = det.get("title") or item["show"] or item["label"]
            item["show"] = title
            item["label"] = title
            item["year"] = str(det.get("year") or item["year"] or "")
        else:
            resp = _jsonrpc("VideoLibrary.GetSeasonDetails", {
                "seasonid": item["dbid"],
                "properties": ["showtitle", "season", "art"]})
            det = ((resp or {}).get("result") or {}).get("seasondetails") or {}
            item["show"] = det.get("showtitle") or item["show"]
            if det.get("season") is not None:
                item["season"] = str(det["season"])
            name = det.get("label") or item["label"]
            item["label"] = (item["show"] + ", " + name) if item["show"] else name
        art = det.get("art") or {}
        item["thumb"] = (art.get("poster") or art.get("tvshow.poster")
                         or art.get("thumb") or item["thumb"])
        rows = self._list_group_episodes(item)
        if not rows:
            return None
        self._list_group_tally(item, rows)
        return item

    def _list_group_tally(self, item, rows):
        """<summary>Set the episode count and running time shown under a
        group row from the episodes it still stands for.</summary>
        <param name="item">The tvshow or season record. Modified in place.</param>
        <param name="rows">Its episodes, as _list_group_episodes returns them.</param>"""
        item["count"] = len(rows)
        item["duration"] = sum(self._safe_int(r.get("runtime"), 0) for r in rows)

    def _lists_expand(self, items, one_each=False):
        """<summary>Swap each show or season row for its episodes.</summary>
        <param name="items">Rows in list order, not modified.</param>
        <param name="one_each">Put in one random episode per show or season
        row instead of all of them: the random ports treat a row as one
        item.</param>
        <returns>Playable records in the same order, with an episode that is
        also listed elsewhere on the list kept only the first time, as
        adding it twice by hand would have been refused.</returns>"""
        out = []
        for it in items:
            if it["dbtype"] not in self.LIST_GROUP_TYPES:
                expanded = [it]
            else:
                expanded = []
                rows = self._list_group_episodes(it)
                if one_each and rows:
                    # Prefer an episode not already drawn from another row.
                    fresh = [r for r in rows if not any(
                        x["dbtype"] == "episode"
                        and x["dbid"] == self._safe_int(r.get("episodeid"), 0)
                        for x in out)]
                    rows = [random.choice(fresh or rows)]
                for r in rows:
                    art = r.get("art") or {}
                    ep = self._list_item_clean({
                        "label": r.get("title") or r.get("label") or "",
                        "file": r.get("file") or "",
                        "dbtype": "episode",
                        "dbid": r.get("episodeid") or 0,
                        "thumb": r.get("thumbnail") or art.get("thumb") or "",
                        "duration": r.get("runtime") or 0,
                        "show": r.get("showtitle") or it["show"],
                        "season": _num_text(r.get("season")),
                        "episode": _num_text(r.get("episode")),
                        "kind": "video",
                    })
                    if ep:
                        expanded.append(ep)
            for ep in expanded:
                if not any(self._list_item_same(ep, x) for x in out):
                    out.append(ep)
        return out

    def _lists_port(self, shuffle):
        """<summary>Copy the whole selected list into Kodi's queue(s) and
        start it playing.</summary>
        <param name="shuffle">Randomise the order before queueing, with
        each show or season row putting in one random episode rather than
        all of them (LISTS-GROUPS).</param>"""
        idx, lst = self._lists_selected()
        if not lst:
            return
        with self._lists_lock:
            items = list(lst["items"])
        if not items:
            self._lists_notify(_L(31345) % lst["name"], True)
            return
        items = self._lists_expand(items, one_each=shuffle)
        if not items:
            self._lists_notify(_L(31651) % lst["name"], True)
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
        # Each show or season row counts once, as the one random episode
        # it gives, and that is what the time is filled from.
        items = self._lists_expand(items, one_each=True)
        if not items:
            self._lists_notify(_L(31651) % lst["name"], True)
            return
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
            if it["dbtype"] in self.LIST_GROUP_TYPES:
                # LISTS-GROUPS: a show or season is many items, so it goes
                # through the queue like a port, clear or keep as set.
                eps = self._lists_expand([it])
                if not eps:
                    self._lists_notify(_L(31651) % it["label"], True)
                    return
                self._lists_queue(lst, eps, _L(31356))
                return
            _jsonrpc("Player.Open", {"item": self._list_item_spec(it)})
            return
        if choice < 0:
            return
        self._lists_item_apply(lst, pos, it, {1: "up", 2: "down", 3: "del"}[choice])

    def _lists_item_quick(self, cmd, row):
        """<summary>One of a row's quick buttons (LISTS-QUICK): move it up,
        move it down, or remove it once the user has said yes.</summary>
        <param name="cmd">item_up, item_down or item_del.</param>
        <param name="row">1-based row number as a string.</param>"""
        try:
            pos = int(row) - 1
        except ValueError:
            return
        idx, lst = self._lists_selected()
        if not lst or not (0 <= pos < len(lst["items"])):
            return
        it = lst["items"][pos]
        action = cmd[5:]
        if action == "del" and not xbmcgui.Dialog().yesno(
                lst["name"], _L(31623) % it.get("label", "")):
            return
        _dlog("list quick %s: row %d of %s" % (action, pos + 1, lst["name"]))
        self._lists_item_apply(lst, pos, it, action)

    def _lists_item_apply(self, lst, pos, it, action):
        """<summary>Move a row up or down, or remove it, save, and put the
        cursor where the user will want it next.</summary>
        <param name="lst">The list the row belongs to.</param>
        <param name="pos">0-based row index the caller saw.</param>
        <param name="it">The item the caller saw at pos; nothing happens
        when the row no longer holds it.</param>
        <param name="action">up, down or del.</param>
        <remarks>The cursor follows a moved row, and after a removal stays
        where the next item slid in. Shared by the action menu and the
        quick buttons.</remarks>"""
        with self._lists_lock:
            items = lst["items"]
            # Remove Watched can take a row out while a menu or confirm is
            # open, which would leave pos pointing at a neighbour.
            if pos >= len(items) or items[pos] is not it:
                return
            if action == "up" and pos > 0:
                items[pos - 1], items[pos] = items[pos], items[pos - 1]
            elif action == "down" and pos < len(items) - 1:
                items[pos + 1], items[pos] = items[pos], items[pos + 1]
            elif action == "del":
                items.pop(pos)
            else:
                return
        self._lists_save()
        # Keep the cursor on the row the item moved to; a removal leaves it
        # where the next item slid into.
        target = {"up": pos, "down": pos + 2, "del": pos + 1}[action]
        remaining = len(lst["items"])
        if not remaining:
            # The last item has gone. List 51 is empty and cannot take
            # focus (Kodi logs "has been asked to focus, but it can't" and
            # leaves the screen with nothing lit), so go back to the lists.
            xbmc.executebuiltin("SetFocus(50)")
            return
        target = max(1, min(target, remaining))
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
                "season": _num_text(row.get("season")),
                "episode": _num_text(row.get("episode")),
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
        stored = items[:self.LIST_ITEMS_MAX]
        if not self._lists_create(name, stored):
            return
        # Count what went in, not what the queue held: a 250 item queue is
        # cut to LIST_ITEMS_MAX and used to be announced as 250 saved.
        self._lists_notify((_L(31364) if len(stored) == 1 else _L(31365)) % (
            len(stored), name))

    # ---- Lists: Remove Watched ---------------------------------------------
    #
    # <summary>
    # A per list switch ("autoremove" in lists.json): once an item on such a
    # list has been watched it leaves the list, with a toast naming it.
    # </summary>
    # <remarks>
    # Two detectors feed one queue, because no single signal covers every
    # kind of item a list can hold. Library items (movie, episode, music
    # video) come from VideoLibrary.OnUpdate carrying a play count above
    # zero, which Kodi announces when a play finishes and also when the
    # item is marked watched by hand; both count. Plugin streams and loose
    # files have no play count, so the loop also follows what is playing
    # and counts anything that got to LIST_WATCHED_PCT before it stopped or
    # the queue moved on, matched by path. An item seen by both is simply
    # found gone the second time. Nothing runs on the notification thread
    # beyond parsing the payload; the loop does the removing and saving.
    # </remarks>
    LIST_WATCHED_PCT = 90
    LIST_WATCH_TYPES = ("movie", "episode", "musicvideo")

    def _lists_shuffle(self):
        """<summary>Put the selected list's items in a random order for
        good, after a yes/no, since the order it had cannot be got back.</summary>
        <remarks>Unlike Port Shuffled, which jumbles only the copy sent to
        the queue, this rewrites lists.json. The cursor goes back to the
        first row.</remarks>"""
        idx, lst = self._lists_selected()
        if not lst or len(lst["items"]) < 2:
            return
        if not xbmcgui.Dialog().yesno(_L(31621), _L(31622) % lst["name"]):
            return
        with self._lists_lock:
            random.shuffle(lst["items"])
        self._lists_save()
        _dlog("list %s: shuffled %d items" % (lst["name"], len(lst["items"])))
        self._lists_notify(_L(31624) % lst["name"])
        xbmc.executebuiltin("SetFocus(51,0,absolute)")

    # LISTS-SORT: mode -> (picker string, button string, key, largest
    # first). Ties fall back to the name, so the order never wobbles.
    LISTS_SORT_MODES = {"name": (31653, 31653, "name", False),
                        "newest": (31654, 31659, "seq", True),
                        "oldest": (31655, 31660, "seq", False),
                        "most": (31656, 31661, "size", True),
                        "fewest": (31657, 31662, "size", False)}
    LISTS_SORT_ORDER = ("name", "newest", "oldest", "most", "fewest")
    # Seconds the Lists screen waits for its cursor to reach a moved list.
    LISTS_FOLLOW_SECS = 2.0

    def _lists_order_locked(self):
        """<summary>Put self._lists in the kept order and keep the same
        list selected (LISTS-SORT). The caller holds _lists_lock.</summary>
        <returns>(old row, new row) when the selected list changed place,
        otherwise None.</returns>
        <remarks>Name first, then a stable sort on the key, so lists that
        tie keep name order whichever way the key runs. With no kept order
        the lists stay as they are.</remarks>"""
        mode = self.LISTS_SORT_MODES.get(self._lists_sort_mode)
        lists = self._lists
        if not mode or not lists:
            return None
        old = self._lists_sel
        picked = lists[old - 1] if 0 < old <= len(lists) else None
        lists.sort(key=lambda l: l["name"].casefold())
        if mode[2] == "seq":
            lists.sort(key=lambda l: l.get("seq") or 0, reverse=mode[3])
        elif mode[2] == "size":
            lists.sort(key=lambda l: len(l["items"]), reverse=mode[3])
        if picked is None:
            return None
        new = next(i for i, l in enumerate(lists) if l is picked) + 1
        if new == old:
            return None
        self._lists_sel = new
        return old, new

    def _lists_follow(self, old, new):
        """<summary>Move the Lists screen's cursor after the selected list,
        which a kept sort has just moved from row old to row new
        (LISTS-SORT).</summary>
        <param name="old">Its row before the change, 1-based.</param>
        <param name="new">Its row now, 1-based.</param>
        <remarks>Control.Move rather than SetFocus: it moves the list of
        lists' cursor without taking focus, so someone working in the items
        column or on the buttons stays where they are. update_lists holds
        the selection at new until the cursor gets there, or for
        LISTS_FOLLOW_SECS at most.</remarks>"""
        if not xbmc.getCondVisibility(
                "Window.IsActive(%d)" % self.LISTS_WINDOW_ID):
            return
        self._lists_sel_hold = (new, time.monotonic() + self.LISTS_FOLLOW_SECS)
        xbmc.executebuiltin("Control.Move(50,%d)" % (new - old))

    def _lists_sort(self):
        """<summary>Pick the order the lists are kept in: by name, newest
        or oldest first, or most or fewest items first (LISTS-SORT).</summary>
        <remarks>Kept in lists.json and applied on every save, so a new
        list, an item added or taken away, or a rename puts the lists back
        in that order straight away. The selected list stays selected
        wherever it moves to. Oldest first is the order lists are made in,
        so it is also the way back to how lists stood before a sort.
        Newest and oldest go by the creation number, see _lists_parse.</remarks>"""
        with self._lists_lock:
            if len(self._lists or []) < 2:
                return
            current = self._lists_sort_mode
        rows = self.LISTS_SORT_ORDER
        choice = xbmcgui.Dialog().select(
            _L(31652), [_L(self.LISTS_SORT_MODES[m][0]) for m in rows],
            preselect=rows.index(current) if current in rows else -1)
        if choice < 0:
            return
        mode = rows[choice]
        with self._lists_lock:
            self._lists_sort_mode = mode
        self._lists_save()
        sid = self.LISTS_SORT_MODES[mode][0]
        _dlog("lists kept sorted: %s" % mode)
        self._lists_notify(_L(31658) % _L(sid))

    def _lists_toggle_autoremove(self):
        """<summary>Flip Remove Watched on the selected list and say which
        way it went.</summary>"""
        idx, lst = self._lists_selected()
        if not lst:
            return
        with self._lists_lock:
            lst["autoremove"] = not lst.get("autoremove")
            on = lst["autoremove"]
        self._lists_save()
        _dlog("list %s: remove watched %s" % (lst["name"], "on" if on else "off"))
        self._lists_notify((_L(31506) if on else _L(31507)) % lst["name"])

    def _lists_on_update(self, data):
        """
        <summary>
        VideoLibrary.OnUpdate handler: queue a library item whose play count
        went above zero.
        </summary>
        <param name="data">The event's JSON payload, {"item": {"id", "type"}, "playcount"}.</param>
        <remarks>
        Notification thread, so it only parses and appends; deque appends
        are safe against the loop's pops. An update with no play count in
        it (a resume point, an artwork change) is not a watch, and nor is a
        count going back to zero. The service's own write that clears a
        resume point through a count of one is skipped via
        _lists_watch_ignore, see _continue_action.
        </remarks>
        """
        try:
            payload = json.loads(data or "{}") or {}
        except (TypeError, ValueError):
            return
        item = payload.get("item") or payload
        dbtype = str(item.get("type") or "")
        dbid = self._safe_int(item.get("id"), 0)
        if (dbtype not in self.LIST_WATCH_TYPES or dbid <= 0
                or self._safe_int(payload.get("playcount"), 0) <= 0):
            return
        if self._lists_watch_ignore.get((dbtype, dbid), 0) > time.time():
            return
        self._lists_watched_q.append({"dbtype": dbtype, "dbid": dbid, "file": ""})

    def _lists_track_playback(self):
        """
        <summary>
        Follow what is playing and queue it as watched once it stops, or the
        queue moves on, past LIST_WATCHED_PCT.
        </summary>
        <remarks>
        Only runs while some list has Remove Watched on. The percentage is
        the last one seen before the change, so a quarter second tick loses
        nothing that matters at the end of a film. Anything with no length
        (a live stream) never gets past zero and is never counted.
        </remarks>
        """
        if not self._lists_autoremove_any:
            self._lists_playing = None
            return
        now = None
        if xbmc.getCondVisibility("Player.HasMedia"):
            path = xbmc.getInfoLabel("Player.Filenameandpath")
            if path:
                now = {"file": path,
                       "pct": self._safe_int(xbmc.getInfoLabel("Player.Progress"), 0)}
        last = self._lists_playing
        if last and (now is None or now["file"] != last["file"]):
            if last["pct"] >= self.LIST_WATCHED_PCT:
                _dlog("lists: %s ended at %d%%" % (last["file"], last["pct"]))
                self._lists_watched_q.append({"dbtype": "", "dbid": 0,
                                              "file": last["file"]})
        self._lists_playing = now

    def _lists_drain_watched(self):
        """
        <summary>
        Take everything the detectors queued out of every Remove Watched
        list, save once, and toast each item that went.
        </summary>
        <remarks>
        A library record matches by type and id, a played path matches an
        item stored with that path. Lists without the switch are left
        alone even when they hold the same item.
        </remarks>
        """
        if not self._lists_watched_q:
            return
        seen = []
        while self._lists_watched_q:
            seen.append(self._lists_watched_q.popleft())
        now = time.time()
        # Expire through a snapshot and delete key by key. Rebuilding the
        # dict here raced the continue action thread, which adds to it: an
        # entry added mid rebuild was lost, and iterating while it grew
        # raised and cost the records already popped above.
        for key, expiry in list(self._lists_watch_ignore.items()):
            if expiry <= now:
                self._lists_watch_ignore.pop(key, None)
        updates = self._list_groups_watched(seen)
        removed = []  # (label, list name)
        with self._lists_lock:
            for lst in self._lists or []:
                if not lst.get("autoremove"):
                    continue
                keep = []
                for it in lst["items"]:
                    upd = next((u for u in updates if u[0] is it), None)
                    if upd:
                        # LISTS-GROUPS: the watched episodes leave the row.
                        _row, keys, titles, rows = upd
                        it["skip"] = sorted(set(it.get("skip") or []) | keys)
                        self._list_group_tally(it, rows)
                        removed.extend((titles[k], lst["name"]) for k in sorted(keys))
                        if not rows:
                            removed.append((it["label"], lst["name"]))
                            continue
                        keep.append(it)
                    elif any(self._list_item_watched(it, rec) for rec in seen):
                        removed.append((it["label"], lst["name"]))
                    else:
                        keep.append(it)
                lst["items"] = keep
        if not removed:
            return
        self._lists_save()
        for label, name in removed:
            _dlog("lists: removed watched %s from %s" % (label, name))
            xbmcgui.Dialog().notification(label, _L(31508) % name,
                                          xbmcgui.NOTIFICATION_INFO, 5000)

    def _list_groups_watched(self, seen):
        """<summary>Work out which episodes just watched belong to show and
        season rows on Remove Watched lists (LISTS-GROUPS).</summary>
        <param name="seen">Records drained from _lists_watched_q.</param>
        <returns>One (row, new skip keys, {key: episode title}, episodes
        left after them) per row that loses an episode; the row is the
        stored dict itself, matched by identity under the lock.</returns>
        <remarks>Runs before the lists lock is taken, since it queries the
        library: one lookup per watched episode, and one episode listing
        per row those episodes belong to. An episode the row had already
        dropped, or a special against a whole show row, changes nothing.</remarks>"""
        eps = [rec["dbid"] for rec in seen
               if rec["dbtype"] == "episode" and rec["dbid"]]
        if not eps:
            return []
        with self._lists_lock:
            rows = [it for lst in self._lists or [] if lst.get("autoremove")
                    for it in lst["items"]
                    if it["dbtype"] in self.LIST_GROUP_TYPES]
        if not rows:
            return []
        watched = []  # (tvshowid, season, key, title)
        for epid in eps:
            resp = _jsonrpc("VideoLibrary.GetEpisodeDetails", {
                "episodeid": epid,
                "properties": ["tvshowid", "season", "episode", "title"]})
            det = ((resp or {}).get("result") or {}).get("episodedetails") or {}
            if det.get("tvshowid"):
                watched.append((int(det["tvshowid"]),
                                self._safe_int(det.get("season"), 0),
                                self._list_episode_key(det),
                                det.get("title") or det.get("label") or ""))
        updates = []
        for it in rows:
            showid, season = self._list_group_where(it)
            mine = [w for w in watched if w[0] == showid
                    and (w[1] == season if season is not None else w[1] > 0)
                    and w[2] not in (it.get("skip") or [])]
            if not mine:
                continue
            keys = {w[2] for w in mine}
            titles = {w[2]: w[3] or it["label"] for w in mine}
            left = [r for r in self._list_group_episodes(it)
                    if self._list_episode_key(r) not in keys]
            updates.append((it, keys, titles, left))
        return updates

    @staticmethod
    def _list_item_watched(it, rec):
        """<summary>True when a watched record names this list item.</summary>
        <param name="it">A stored list item.</param>
        <param name="rec">A queued record: dbtype and dbid, or file.</param>"""
        if rec["dbid"]:
            return it["dbtype"] == rec["dbtype"] and it["dbid"] == rec["dbid"]
        return bool(it["file"]) and it["file"] == rec["file"]

    # ---- Radarr: remove a list's films from Radarr (RADARR-REMOVE) ---------
    #
    # <summary>
    # One list can be tied to a Radarr server. Its Remove from Radarr
    # button asks Radarr to remove every film on it, delete the files and
    # add an import exclusion so Radarr never fetches the film again, then
    # takes the films Radarr confirmed gone off the list.
    # </summary>
    # <remarks>
    # Nothing here runs on its own: the only trigger is the button, and the
    # button always asks first. The intent is spelt out at every level (the
    # command is radarr_remove, the functions say remove, each log line
    # carries "intent: remove") because other Radarr requests may be added
    # later and a removal must never be mistaken for one of them.
    #
    # Dry run is on until it is switched off on the settings page, and an
    # unreadable radarr.json reads as dry run too: the whole flow runs,
    # the log says what would have been removed, and no DELETE is sent.
    #
    # A film is only ever matched by id. Kodi's library gives the TMDB and
    # IMDb ids, Radarr's own film list is searched for exactly those, and a
    # list item whose library id no longer names the file it was captured
    # with is skipped: after a library rebuild id 12 can be another film.
    # Anything that cannot be matched that way stays on the list and the
    # log says why. Title matching is deliberately absent.
    #
    # The address and API key live in radarr.json in this skin's add-on
    # data folder, never in a skin string: skin strings are copied into the
    # settings backup and shown by the skin, and the key is full control of
    # the Radarr server. The key is never logged and never published.
    # </remarks>
    RADARR_FILE = "special://profile/addon_data/skin.functional/radarr.json"
    # Append only, one line per film per run, see _radarr_log.
    RADARR_LOG_FILE = "special://profile/addon_data/skin.functional/radarr-log.txt"
    RADARR_TIMEOUT = 20          # seconds per request
    RADARR_LOG_VIEW_LINES = 300  # newest lines shown by View Log
    RADARR_CONFIRM_TITLES = 8    # titles named in the confirm before "and N more"

    def _radarr_config(self, force=False):
        """
        <summary>
        The Radarr settings, read from radarr.json once.
        </summary>
        <param name="force">Re-read even if already loaded.</param>
        <returns>A dict with url (no trailing slash), key and dry_run.</returns>
        <remarks>
        A missing or unreadable file is "not set up, dry run on", the safe
        reading. dry_run is only False when the file says exactly false.
        </remarks>
        """
        if self._radarr is not None and not force:
            return self._radarr
        cfg = {"url": "", "key": "", "dry_run": True}
        path = xbmcvfs.translatePath(self.RADARR_FILE)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    cfg["url"] = str(data.get("url") or "").strip().rstrip("/")
                    cfg["key"] = str(data.get("key") or "").strip()
                    cfg["dry_run"] = data.get("dry_run") is not False
            except Exception:  # noqa: BLE001
                _dlog("radarr.json unreadable:\n" + traceback.format_exc(),
                      xbmc.LOGWARNING)
        self._radarr = cfg
        return cfg

    def _radarr_save(self):
        """
        <summary>
        Write the Radarr settings back to radarr.json and republish them.
        </summary>
        <returns>True when the file was written.</returns>
        <remarks>
        Created readable by its owner only where the platform honours
        that, because it holds the API key. Temp file then rename, as
        lists.json is written.
        </remarks>
        """
        cfg = self._radarr_config()
        self._lists_path()  # creates the add-on data folder when missing
        path = xbmcvfs.translatePath(self.RADARR_FILE)
        tmp = path + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "url": cfg["url"], "key": cfg["key"],
                           "dry_run": bool(cfg["dry_run"])}, fh, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError:
            _dlog("radarr.json write failed:\n" + traceback.format_exc(),
                  xbmc.LOGERROR)
            self._lists_notify(_L(31616), True)
            return False
        self._radarr_publish()
        return True

    def _radarr_publish(self, lists=None):
        """
        <summary>
        Publish the Radarr settings page's readouts as Home properties.
        </summary>
        <param name="lists">The lists to find the tied one in; read under the lock when omitted.</param>
        <remarks>
        Radarr.Url, Radarr.Key (the words Set or Not set, never the key),
        Radarr.List (the tied list's name, or None) and Radarr.DryRun
        (On or Off).
        </remarks>
        """
        cfg = self._radarr_config()
        if lists is None:
            with self._lists_lock:
                lists = list(self._lists or [])
        tied = next((l["name"] for l in lists if l.get("radarr")), "")
        win = xbmcgui.Window(HOME_WINDOW_ID)
        win.setProperty("Radarr.Url", cfg["url"] or _L(31586))
        win.setProperty("Radarr.Key", _L(31585) if cfg["key"] else _L(31586))
        win.setProperty("Radarr.List", tied or _L(31588))
        win.setProperty("Radarr.DryRun",
                        _L(31503) if cfg["dry_run"] else _L(31504))

    def _radarr_log(self, cfg, list_name, title, result, ids=""):
        """
        <summary>
        Append one line to the Radarr log, the record of every removal
        asked for, made, skipped or failed.
        </summary>
        <param name="cfg">The settings in force, for the DRY RUN or LIVE tag.</param>
        <param name="list_name">The list the request came from.</param>
        <param name="title">The film, or "" for a line about the whole run.</param>
        <param name="result">What happened, in plain words.</param>
        <param name="ids">The ids the match was made on, when there are any.</param>
        <remarks>
        Plain text, one line per film per run, never trimmed or rewritten.
        The date is day first because this file is for reading. A line
        that cannot be written is still in the debug log.
        </remarks>
        """
        fields = [time.strftime("%d/%m/%Y %H:%M:%S"),
                  xbmc.getInfoLabel("System.FriendlyName") or "Kodi",
                  "DRY RUN" if cfg["dry_run"] else "LIVE",
                  "intent: remove",
                  "list: " + list_name]
        if title:
            fields.append(title)
        if ids:
            fields.append(ids)
        fields.append("result: " + result)
        line = " | ".join(fields)
        _dlog("radarr: " + line)
        self._lists_path()  # creates the add-on data folder when missing
        try:
            with open(xbmcvfs.translatePath(self.RADARR_LOG_FILE), "a",
                      encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            _dlog("radarr log write failed:\n" + traceback.format_exc(),
                  xbmc.LOGERROR)

    def _radarr_request(self, cfg, method, path, query=None):
        """
        <summary>
        One call to Radarr's v3 API.
        </summary>
        <param name="cfg">The settings: url and key.</param>
        <param name="method">GET or DELETE.</param>
        <param name="path">Path under /api/v3/, such as "movie" or "movie/12".</param>
        <param name="query">Query parameters as a dict, or None.</param>
        <returns>The decoded JSON reply, or None for an empty body.</returns>
        <exception cref="RuntimeError">
        Anything other than a clean answer: no connection, a timeout, an
        HTTP error, a reply that is not JSON (a proxy's login page). The
        message is safe to show and to log; the key travels in a header
        and is in neither the address nor the message.
        </exception>
        <remarks>
        This is transport only and knows nothing about intent. Callers
        such as _radarr_remove_movie say what the request is for.
        </remarks>
        """
        if not cfg["url"].lower().startswith(("http://", "https://")):
            raise RuntimeError("the address is not http or https")
        url = cfg["url"] + "/api/v3/" + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(
            url, method=method,
            headers={"X-Api-Key": cfg["key"], "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.RADARR_TIMEOUT) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError("HTTP %d%s" % (
                exc.code, ", API key refused" if exc.code == 401 else ""))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                str(getattr(exc, "reason", "") or exc) or exc.__class__.__name__)
        if not body.strip():
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            raise RuntimeError("the reply was not JSON, is the address right?")

    def _radarr_movies(self, cfg):
        """
        <summary>
        Every film Radarr manages, indexed by the ids a match is made on.
        </summary>
        <param name="cfg">The settings: url and key.</param>
        <returns>(by_tmdb, by_imdb): Radarr film records keyed by TMDB id (int) and by IMDb id (str).</returns>
        <exception cref="RuntimeError">The request failed or did not return a list of films.</exception>
        <remarks>One request for the whole run rather than one per film.</remarks>
        """
        rows = self._radarr_request(cfg, "GET", "movie")
        if not isinstance(rows, list):
            raise RuntimeError("the reply was not a list of films")
        by_tmdb, by_imdb = {}, {}
        for row in rows:
            if not isinstance(row, dict) or self._safe_int(row.get("id"), 0) <= 0:
                continue
            tmdb = self._safe_int(row.get("tmdbId"), 0)
            if tmdb > 0:
                by_tmdb[tmdb] = row
            imdb = str(row.get("imdbId") or "")
            if imdb.startswith("tt"):
                by_imdb[imdb] = row
        return by_tmdb, by_imdb

    def _radarr_remove_movie(self, cfg, movie):
        """
        <summary>
        Ask Radarr to remove one film, delete its files and exclude it
        from being added again, then check that it has gone.
        </summary>
        <param name="cfg">The settings: url and key.</param>
        <param name="movie">The film's record from _radarr_movies.</param>
        <returns>True when Radarr no longer lists the film afterwards.</returns>
        <exception cref="RuntimeError">The removal or the check after it failed.</exception>
        <remarks>
        Irreversible: the files are deleted from disk by Radarr. Never
        called in dry run, see _radarr_remove_list, and refuses on its own
        account as a second guard.
        </remarks>
        """
        if cfg["dry_run"]:
            raise RuntimeError("dry run is on, no removal is sent")
        rid = self._safe_int(movie.get("id"), 0)
        self._radarr_request(cfg, "DELETE", "movie/%d" % rid,
                             {"deleteFiles": "true",
                              "addImportExclusion": "true"})
        left = self._radarr_request(cfg, "GET", "movie",
                                    {"tmdbId": movie.get("tmdbId")})
        return not any(isinstance(row, dict)
                       and self._safe_int(row.get("id"), 0) == rid
                       for row in left or [])

    def _radarr_identify(self, it):
        """
        <summary>
        Work out which film a list item is, from Kodi's library, in a form
        Radarr can be searched for.
        </summary>
        <param name="it">A stored list item.</param>
        <returns>
        (film, reason): film is a dict with title (with its year), tmdb
        (int, 0 when unknown) and imdb ("" when unknown); when the item
        cannot be identified safely film is None and reason says why.
        </returns>
        <remarks>
        The item's library id is only trusted when the library still has
        the same file under it (or, for an item stored with no path, the
        same title), the test _list_item_localise applies to an import.
        imdbnumber is used only when it is an IMDb id; with a TMDB scraper
        it holds a bare number that could be either.
        </remarks>
        """
        if it["dbtype"] != "movie" or not it["dbid"]:
            return None, "skipped, not a film from the library"
        resp = _jsonrpc("VideoLibrary.GetMovieDetails", {
            "movieid": it["dbid"],
            "properties": ["title", "year", "file", "uniqueid", "imdbnumber"]})
        details = ((resp or {}).get("result") or {}).get("moviedetails") or {}
        if not details:
            return None, "skipped, the library no longer has this film"
        if it["file"]:
            if (details.get("file") or "") != it["file"]:
                return None, ("skipped, the library id now names a "
                              "different file")
        elif (details.get("label") or details.get("title") or "") != it["label"]:
            return None, "skipped, the library id now names a different film"
        unique = details.get("uniqueid") or {}
        tmdb = self._safe_int(unique.get("tmdb"), 0)
        imdb = str(unique.get("imdb") or "")
        if not imdb.startswith("tt"):
            imdb = str(details.get("imdbnumber") or "")
        if not imdb.startswith("tt"):
            imdb = ""
        if tmdb <= 0 and not imdb:
            return None, "skipped, the library has no TMDB or IMDb id for it"
        title = details.get("title") or it["label"]
        if details.get("year"):
            title += " (%s)" % details["year"]
        return {"title": title, "tmdb": max(tmdb, 0), "imdb": imdb}, ""

    def _radarr_remove_list(self):
        """
        <summary>
        The Remove from Radarr button: after a confirm, send every film on
        the selected list to Radarr to be removed, log each outcome and
        take the removed films off the list.
        </summary>
        <remarks>
        Dialog thread. Only acts on the list tied to Radarr, and only on
        items that were on it when the button was pressed. In dry run the
        same lookups are made and logged but nothing is removed anywhere.
        A film leaves the list only once Radarr has been seen to no longer
        hold it; skipped and failed films stay where they are. Kodi's own
        library is not touched: the entry goes at the next library clean.
        </remarks>
        """
        idx, lst = self._lists_selected()
        if not lst or not lst.get("radarr"):
            return
        cfg = dict(self._radarr_config())
        name = lst["name"]
        dry = cfg["dry_run"]
        heading = _L(31609) if dry else _L(31582)
        if not cfg["url"] or not cfg["key"]:
            self._lists_notify(_L(31598), True)
            return
        with self._lists_lock:
            items = list(lst["items"])
        films, skips = [], []   # (list item, identity), (label, reason)
        for it in items:
            film, reason = self._radarr_identify(it)
            if film is None:
                skips.append((it["label"], reason))
            else:
                films.append((it, film))
        skipped = len(skips)
        if not films:
            for label, reason in skips:
                self._radarr_log(cfg, name, label, reason)
            xbmcgui.Dialog().ok(heading, _L(31608) % name)
            return
        titles = [film["title"] for _it, film in films]
        shown = titles[:self.RADARR_CONFIRM_TITLES]
        if len(titles) > len(shown):
            shown.append(_L(31605) % (len(titles) - len(shown)))
        if dry:
            question = _L(31604) % "[CR]".join(shown)
        elif len(films) == 1:
            question = _L(31603) % "[CR]".join(shown)
        else:
            question = _L(31602) % (len(films), "[CR]".join(shown))
        if not xbmcgui.Dialog().yesno(heading, question):
            self._radarr_log(cfg, name, "", "cancelled at the confirm, "
                             "%d film(s) left alone" % len(films))
            return
        for label, reason in skips:
            self._radarr_log(cfg, name, label, reason)
        try:
            by_tmdb, by_imdb = self._radarr_movies(cfg)
        except RuntimeError as exc:
            self._radarr_log(cfg, name, "",
                             "failed, Radarr's film list could not be read: %s" % exc)
            self._lists_notify(_L(31597) % exc, True)
            return
        removed, failed, gone = 0, 0, []
        progress = xbmcgui.DialogProgress()
        progress.create(heading, "")
        try:
            for n, (it, film) in enumerate(films):
                if progress.iscanceled():
                    self._radarr_log(cfg, name, "", "stopped by hand, "
                                     "%d film(s) not reached" % (len(films) - n))
                    skipped += len(films) - n
                    break
                progress.update(int(100 * n / len(films)), film["title"])
                movie = by_tmdb.get(film["tmdb"]) if film["tmdb"] else None
                if movie is None and film["imdb"]:
                    movie = by_imdb.get(film["imdb"])
                ids = "tmdb %s, imdb %s" % (film["tmdb"] or "none",
                                            film["imdb"] or "none")
                if movie is None:
                    skipped += 1
                    self._radarr_log(cfg, name, film["title"],
                                     "skipped, Radarr does not have this film", ids)
                    continue
                ids += ", radarr id %s, %.1f GB on disk" % (
                    movie.get("id"),
                    self._safe_int(movie.get("sizeOnDisk"), 0) / 1073741824.0)
                if dry:
                    removed += 1
                    self._radarr_log(cfg, name, film["title"],
                                     "would be removed, files deleted and "
                                     "blocked from being added again", ids)
                    continue
                try:
                    confirmed = self._radarr_remove_movie(cfg, movie)
                except RuntimeError as exc:
                    failed += 1
                    self._radarr_log(cfg, name, film["title"],
                                     "failed: %s" % exc, ids)
                    continue
                if confirmed:
                    removed += 1
                    gone.append(it)
                    self._radarr_log(cfg, name, film["title"],
                                     "removed, files deleted and blocked "
                                     "from being added again", ids)
                else:
                    failed += 1
                    self._radarr_log(cfg, name, film["title"],
                                     "failed, Radarr accepted the removal "
                                     "but still lists the film", ids)
        finally:
            progress.close()
        if gone:
            with self._lists_lock:
                lst["items"] = [it for it in lst["items"]
                                if not any(it is done for done in gone)]
            self._lists_save()
        if dry:
            xbmcgui.Dialog().ok(heading, _L(31607) % (removed, skipped))
        else:
            xbmcgui.Dialog().ok(heading, _L(31606) % (removed, skipped, failed))

    def _radarr_ask_url(self):
        """<summary>Settings page: keyboard prompt for Radarr's address.</summary>
        <remarks>An empty answer leaves the address as it was; anything
        that is not http or https is refused with a toast.</remarks>"""
        cfg = self._radarr_config()
        url = xbmcgui.Dialog().input(_L(31593), cfg["url"],
                                     type=xbmcgui.INPUT_ALPHANUM).strip().rstrip("/")
        if not url or url == cfg["url"]:
            return
        if not url.lower().startswith(("http://", "https://")):
            self._lists_notify(_L(31595), True)
            return
        cfg["url"] = url
        self._radarr_save()

    def _radarr_ask_key(self):
        """<summary>Settings page: hidden keyboard prompt for Radarr's API
        key.</summary>
        <remarks>The stored key is never offered back as the default, so
        it cannot be read off the screen; an empty answer keeps it.</remarks>"""
        cfg = self._radarr_config()
        key = xbmcgui.Dialog().input(_L(31594), "", type=xbmcgui.INPUT_ALPHANUM,
                                     option=xbmcgui.ALPHANUM_HIDE_INPUT).strip()
        if not key:
            return
        cfg["key"] = key
        self._radarr_save()

    def _radarr_pick_list(self):
        """
        <summary>
        Settings page: choose which one list Remove from Radarr acts on,
        or none.
        </summary>
        <remarks>
        Exactly one list carries the flag. Its Remove Watched switch is
        left as it is: with that on, a film watched before the button is
        pressed has already left the list and is not removed.
        </remarks>
        """
        with self._lists_lock:
            names = [l["name"] for l in self._lists or []]
            current = next((i for i, l in enumerate(self._lists or [])
                            if l.get("radarr")), -1)
        choice = xbmcgui.Dialog().select(_L(31615), [_L(31588)] + names,
                                         preselect=current + 1)
        if choice < 0 or choice - 1 == current:
            return
        tied = ""
        with self._lists_lock:
            for i, l in enumerate(self._lists or []):
                # By name as well as position: the lists can change while
                # the picker is open.
                l["radarr"] = (i == choice - 1 and l["name"] == names[i])
                if l["radarr"]:
                    tied = l["name"]
        self._lists_save()
        _dlog("radarr: list tied: %s" % (tied or "none"))
        self._lists_notify(_L(31611) % tied if tied else _L(31612))

    def _radarr_toggle_dry_run(self):
        """<summary>Settings page: flip dry run, asking first before
        turning it off since removals are then real.</summary>"""
        cfg = self._radarr_config()
        if cfg["dry_run"] and not xbmcgui.Dialog().yesno(_L(31580), _L(31601)):
            return
        cfg["dry_run"] = not cfg["dry_run"]
        if self._radarr_save():
            self._lists_notify(_L(31613) if cfg["dry_run"] else _L(31614))

    def _radarr_test(self):
        """<summary>Settings page: ask Radarr for its status and say whether
        the address and key work. Reads only.</summary>"""
        cfg = dict(self._radarr_config())
        if not cfg["url"] or not cfg["key"]:
            self._lists_notify(_L(31598), True)
            return
        try:
            status = self._radarr_request(cfg, "GET", "system/status")
            if not isinstance(status, dict) or not status.get("version"):
                raise RuntimeError("the reply was not Radarr's status")
        except RuntimeError as exc:
            self._lists_notify(_L(31597) % exc, True)
            return
        self._lists_notify(_L(31596) % status["version"])

    def _radarr_view_log(self):
        """<summary>Settings page: show the newest lines of the Radarr log,
        newest first.</summary>"""
        lines = []
        try:
            with open(xbmcvfs.translatePath(self.RADARR_LOG_FILE), "r",
                      encoding="utf-8") as fh:
                lines = [line.rstrip("\n") for line in fh if line.strip()]
        except OSError:
            lines = []
        if not lines:
            self._lists_notify(_L(31599))
            return
        lines = lines[-self.RADARR_LOG_VIEW_LINES:]
        lines.reverse()
        xbmcgui.Dialog().textviewer(_L(31600), "[CR][CR]".join(lines))

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
            if not self._apply_default_sort():
                # No default to force here, so report the sort Kodi itself
                # remembered for this node instead of the last button pressed.
                self._sync_sort_active()

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
        # Ask for the list first, whether or not a name is already cached:
        # _start_genre_fetch is a no-op once the type has been pulled, and a
        # library event clears that mark so a renamed genre is picked up.
        # Returning early on a cached name meant the list was never pulled
        # again for an id it already knew.
        self._start_genre_fetch(dbtype)
        name = self._genre_names.get((dbtype, genre_id))
        if name:
            return name
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
        if time.time() < self._genre_retry_at:
            return  # the last fetch failed; do not ask a sleeping database every tick
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
            # _result_rows raises when the call itself failed. _jsonrpc
            # swallows its own errors, so without that the except below
            # could never run and one failed fetch stuck the label on the
            # folder name until the next library event.
            rows = _result_rows(
                _jsonrpc("VideoLibrary.GetGenres", {"type": dbtype}), "genres")
            for row in rows:
                gid = row.get("genreid")
                label = (row.get("label") or "").strip()
                if gid is not None and label:
                    self._genre_names[(dbtype, int(gid))] = label
            _dlog("genres: cached {0} {1} genres".format(len(rows), dbtype))
        except Exception:  # noqa: BLE001
            # Allow a later retry rather than being stuck on FolderName.
            self._genre_fetched.discard(dbtype)
            self._genre_retry_at = time.time() + 30
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
        <returns>True when a default sort was applied, False when there was none to apply.</returns>
        """
        if xbmc.getCondVisibility("Container.Content(movies)"):
            key = "movies"
        elif xbmc.getCondVisibility("Container.Content(tvshows)"):
            key = "tvshows"
        else:
            return False
        want = xbmc.getInfoLabel(
            "Skin.String(default_sort_{0})".format(key)).strip().lower()
        if want not in self.SORT_METHOD_IDS:
            return False  # unset or "kodi" = leave Kodi's own remembered sort alone
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
        return True

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
        Slow tick. Stats the file at most every BACKUP_CHECK_SECS and looks
        at it only when the mtime has moved; the copy itself happens only
        when the content differs from the snapshot (see _backup_worker), so
        a quiet box does one stat every twenty seconds and nothing else.
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
        if not self._backup_age_published:
            # Once per service start: tell the settings page a snapshot
            # exists. The Restore button is enabled by this string alone,
            # and it used to be written only after a successful copy, so
            # after a settings reset (which blanks it with everything else)
            # Restore stayed greyed out exactly when it was needed.
            self._backup_age_published = True
            self._publish_backup_age()
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
        One copy at a time: a request made while a copy is still running is
        dropped, and the next change of settings.xml asks again.
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
            target = self._backup_path()
            wiped = self._looks_like_a_wipe(data)
            if not announce and wiped:
                # One rolling snapshot is only a backup if the event it
                # protects against can't overwrite it. A settings reset
                # rewrites settings.xml, and the automatic snapshot would
                # cheerfully copy the wreckage over the good copy seconds
                # later. "Back Up Now" is never blocked, so a deliberate
                # cull is still one button away.
                _dlog("backup: settings.xml lost most of its choices, "
                      "keeping the previous snapshot", xbmc.LOGWARNING)
                # The reset blanked the string that enables Restore too.
                self._publish_backup_age()
                return
            if not announce and self._same_settings(data, target):
                # Nothing but the snapshot's own timestamp has changed.
                # Every snapshot used to end by writing that timestamp into
                # a skin string, which made Kodi rewrite settings.xml, which
                # moved its mtime, which triggered the next snapshot: two
                # files rewritten every twenty seconds for ever on an idle
                # box.
                return
            folder = xbmcvfs.translatePath(self.BACKUP_DIR)
            if not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            if announce and wiped and os.path.isfile(target):
                # Back Up Now over a snapshot that holds far more than the
                # live settings do. The button is allowed to do that, but
                # the fuller snapshot is the only copy of those choices, so
                # it is kept under another name rather than destroyed.
                os.replace(target, target + self.BACKUP_KEPT_SUFFIX)
                _dlog("backup: the fuller snapshot was kept as {0}".format(
                    os.path.basename(target + self.BACKUP_KEPT_SUFFIX)),
                    xbmc.LOGWARNING)
            # Write beside the target and rename: a snapshot interrupted
            # half-written is worse than no snapshot at all.
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

    # Below this many stored choices there is nothing worth protecting, and
    # the ratio test would fire on a brand-new profile legitimately growing.
    WIPE_GUARD_MIN = 4
    # Appended to the snapshot's name for the copy kept when Back Up Now
    # replaces a snapshot that held far more, see _backup_worker.
    BACKUP_KEPT_SUFFIX = ".before-reset"
    # Seeded by the service itself at start, so present again straight after
    # a reset and no evidence of anything the user chose.
    WIPE_IGNORE_KEYS = frozenset(("infobar_clearance_top", "infobar_clearance_bottom"))
    _BACKUP_WHEN_RE = re.compile(
        rb'<setting id="settings_backup_when"[^>]*?(?:/>|>[^<]*</setting>)')

    @classmethod
    def _count_choices(cls, data):
        """
        <summary>
        How many settings in a settings.xml hold something the user chose.
        </summary>
        <param name="data">The file's raw bytes.</param>
        <returns>The count, or None when the bytes do not parse as XML.</returns>
        <remarks>
        A choice is a string with text in it or a bool that is true, on a
        key that a restore would put back (the same skip lists as
        _read_backup, plus WIPE_IGNORE_KEYS). Counting entries, as this used
        to, cannot see a reset at all: Kodi blanks every value in place and
        keeps every entry, so a wiped file has exactly as many entries as a
        full one. Readouts the service republishes within seconds of a reset
        (the library figures, the cache labels) are left out for the same
        reason; they would make a wiped file look lived in.
        </remarks>
        """
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return None
        count = 0
        for node in root.findall("setting"):
            key = (node.get("id") or "").strip()
            if (not key or key in cls.BACKUP_SKIP_KEYS
                    or key in cls.WIPE_IGNORE_KEYS
                    or key.startswith(cls.BACKUP_SKIP_PREFIXES)
                    or key.endswith(cls.BACKUP_SKIP_SUFFIXES)):
                continue
            value = (node.text or "").strip()
            if (node.get("type") or "").strip() == "bool":
                count += value.lower() == "true"
            else:
                count += bool(value)
        return count

    def _looks_like_a_wipe(self, data):
        """
        <summary>
        True if *data* has lost most of the choices the snapshot holds.
        </summary>
        <param name="data">the raw bytes just read from settings.xml.</param>
        <returns>True when the snapshot should not be replaced automatically.</returns>
        <remarks>
        The signature of a reset is "held 40 choices, now holds 2", not "held
        40, now holds 38". A settings file that does not parse is treated as
        a wipe as well: Kodi may be part way through writing it, and the
        next change of mtime gives another chance.
        </remarks>
        """
        try:
            with open(self._backup_path(), "rb") as fh:
                stored = self._count_choices(fh.read())
        except OSError:
            return False  # no snapshot yet: anything is an improvement
        if stored is None or stored < self.WIPE_GUARD_MIN:
            return False
        live = self._count_choices(data)
        return live is None or live * 2 < stored

    @classmethod
    def _same_settings(cls, data, snapshot_path):
        """
        <summary>
        True when settings.xml matches the snapshot apart from the entry
        that records when the snapshot was taken.
        </summary>
        <param name="data">The raw bytes just read from settings.xml.</param>
        <param name="snapshot_path">Filesystem path of the snapshot.</param>
        <returns>False when they differ or there is no snapshot to compare with.</returns>
        """
        try:
            with open(snapshot_path, "rb") as fh:
                stored = fh.read()
        except OSError:
            return False
        return (cls._BACKUP_WHEN_RE.sub(b"", data)
                == cls._BACKUP_WHEN_RE.sub(b"", stored))

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
                    _reset_skin_string(key)
            elif value:
                _set_skin_string(key, value)
            else:
                _reset_skin_string(key)
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
            self._sort_want_ticks = 0
            return
        # Only meddle while the video library window is up, so we never nudge
        # some other window's container.
        if not xbmc.getCondVisibility("Window.IsVisible(videos)"):
            _reset_skin_string("sort_want")
            return
        # Did the node take the sort the button asked for? Not every node
        # offers every method (a season list has one), and Kodi ignores a
        # SetSortMethod it does not offer. The direction used to be applied
        # regardless, so choosing Year in a season left the order as it was
        # and silently reversed it. Give the container a few ticks to settle
        # before deciding, then put sort_active back to the truth and leave
        # the direction alone.
        active = xbmc.getInfoLabel("Skin.String(sort_active)").strip().lower()
        expected = self.SORT_METHOD_IDS.get(active)
        if expected is not None and not xbmc.getCondVisibility(
                "Container.SortMethod({0})".format(expected)):
            self._sort_want_ticks += 1
            if self._sort_want_ticks < self.SORT_SETTLE_TICKS:
                return
            self._sort_want_ticks = 0
            _dlog("sort: this node did not take {0!r}, direction left alone".format(active))
            self._sync_sort_active()
            _reset_skin_string("sort_want")
            return
        self._sort_want_ticks = 0
        if want == "desc" and xbmc.getCondVisibility("Container.SortDirection(ascending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        elif want == "asc" and xbmc.getCondVisibility("Container.SortDirection(descending)"):
            xbmc.executebuiltin("Container.SetSortDirection")
        _reset_skin_string("sort_want")

    SORT_SETTLE_TICKS = 3  # fast ticks to wait for a new sort method to show

    def _sync_sort_active(self):
        """
        <summary>
        Make Skin.String(sort_active) name the sort the container on screen
        is really using.
        </summary>
        <remarks>
        sort_active is one string for every node, written by the Sort
        buttons, while Kodi remembers a sort per node. Sort Movies by Year,
        open TV Shows (still by title) and the fast scroll badge showed
        years over an A to Z list. Called after every path change and after
        a rejected sort. When the container uses a method the side menu has
        no button for, the string is left as it is.
        </remarks>
        """
        for name, method_id in self.SORT_METHOD_IDS.items():
            if xbmc.getCondVisibility("Container.SortMethod({0})".format(method_id)):
                if xbmc.getInfoLabel("Skin.String(sort_active)").strip().lower() != name:
                    _set_skin_string("sort_active", name)
                return

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
    SLEEP_EPISODES_DEFAULT = 2
    # How long before power off the one warning toast appears.
    SLEEP_WARN_SECS = 60

    def update_sleep_timer(self):
        """
        <summary>
        Run the sleep timer: take commands from the power menu, republish the
        countdown, and power the box down when it reaches zero.
        </summary>
        <remarks>
        Skin.String(sleep_command) is the channel, cleared the moment it is
        read so a command cannot fire twice: "set" (hours and minutes
        prompt), "cancel", "episode" (power down when whatever is playing
        finishes), "episodes" (prompt for how many, counting the current
        one) or "episodes:N" with the count baked in. The prompts are
        blocking Python dialogs and go through _spawn_dialog, or they would
        stall every other handler for as long as they are open.

        Two modes, never both: a clock deadline, or a count of natural
        playback ends. The count is driven by Player.OnStop with "end" true
        (Kodi's own flag for "reached the end", a manual stop leaves the
        count alone), decremented on the notification thread and acted on
        here, on the loop, through _sleep_fire_pending. In episode mode the
        countdown label is "1 ep" or "N eps", and the one minute warning
        comes from Player.TimeRemaining of the last episode.

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
            elif cmd == "episode":
                self._sleep_arm_episodes(1)
            elif cmd == "episodes":
                self._spawn_dialog(self._sleep_pick_episodes)
            elif cmd.startswith("episodes:"):
                self._sleep_arm_episodes(self._safe_int(cmd[9:], 0))

        if self._sleep_fire_pending:
            self._sleep_fire_pending = False
            self._sleep_fire()
            return

        if self._sleep_episodes > 0:
            count = self._sleep_episodes
            label = (_L(31475) if count == 1 else _L(31476)).format(count)
            if label != self._sleep_published:
                self._sleep_published = label
                _set_home_property("sleep_remaining", label)
            if count == 1 and not self._sleep_warned and xbmc.getCondVisibility("Player.HasMedia"):
                left = _parse_duration_to_seconds(xbmc.getInfoLabel("Player.TimeRemaining"))
                if 0 < left <= self.SLEEP_WARN_SECS:
                    self._sleep_warned = True
                    self._sleep_notify(_L(31429))
            return

        if self._sleep_deadline is None:
            return

        remaining = int(round(self._sleep_deadline - time.monotonic()))
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
        # Two modes, never both. An episode count left armed took priority
        # in update_sleep_timer, so a clock timer set over it was confirmed
        # with a toast and then ignored: the label flipped back to the
        # episode count and the box never powered down on the clock.
        self._sleep_episodes = 0
        self._sleep_fire_pending = False
        self._sleep_warned = minutes * 60 <= self.SLEEP_WARN_SECS
        self._sleep_published = self._fmt_countdown(minutes * 60)
        _set_home_property("sleep_remaining", self._sleep_published)
        self._sleep_deadline = time.monotonic() + minutes * 60
        _dlog("sleep timer: armed for {0}".format(self._fmt_hhmm(minutes)))
        self._sleep_notify(_L(31427).format(self._fmt_hhmm(minutes)))

    def _sleep_on_stop(self, data):
        """
        <summary>
        Player.OnStop handler for episode mode: count a natural end, and ask
        the loop to fire when the count reaches zero.
        </summary>
        <param name="data">The event's JSON payload; "end" is Kodi's flag for playback having reached the end.</param>
        <remarks>
        Runs on Kodi's notification thread, so it only moves a counter and
        sets a flag; the loop republishes the label and does the powering
        down. A stop the viewer made is not an end: the count waits for the
        next episode to finish instead.
        </remarks>
        """
        if self._sleep_episodes <= 0:
            return
        try:
            ended = bool((json.loads(data or "{}") or {}).get("end"))
        except (TypeError, ValueError):
            ended = False
        if not ended:
            return
        self._sleep_episodes -= 1
        _dlog("sleep timer: playback ended, {0} to go".format(self._sleep_episodes))
        if self._sleep_episodes <= 0:
            self._sleep_fire_pending = True

    def _sleep_arm_episodes(self, count):
        """
        <summary>
        Arm the timer to power down after the given number of playbacks
        have finished, counting the one playing now.
        </summary>
        <param name="count">Episodes to wait for; anything below one cancels instead.</param>
        """
        if count <= 0:
            self._sleep_disarm(announce=True)
            return
        self._sleep_disarm()
        self._sleep_episodes = count
        self._sleep_published = (_L(31475) if count == 1 else _L(31476)).format(count)
        _set_home_property("sleep_remaining", self._sleep_published)
        _dlog("sleep timer: armed for {0} episode(s)".format(count))
        self._sleep_notify(_L(31473) if count == 1 else _L(31474).format(count))

    def _sleep_pick_episodes(self):
        """
        <summary>
        Ask how many episodes to sit through, seeded with the last answer,
        and arm the timer.
        </summary>
        <remarks>
        Dialog thread. The answer is remembered in Skin.String(
        sleep_episodes_default) so the prompt opens on it next time. Zero
        cancels, for the same reason 00:00 cancels the clock prompt.
        </remarks>
        """
        current = self._safe_int(self._get_skin("sleep_episodes_default"), 0)
        if current <= 0:
            current = self.SLEEP_EPISODES_DEFAULT
        result = xbmcgui.Dialog().numeric(0, _L(31472), str(current))
        if result is None or result == "":
            return  # cancelled: leave any running timer alone
        count = self._safe_int(result, 0)
        if count > 0:
            _set_skin_string("sleep_episodes_default", str(count))
        self._sleep_arm_episodes(count)

    def _sleep_disarm(self, announce=False):
        """
        <summary>
        Stop any running timer, in either mode, and clear the countdown.
        </summary>
        <param name="announce">True to toast, but only if a timer was actually
        running, so "cancel" on an idle skin stays silent.</param>
        """
        was_armed = self._sleep_deadline is not None or self._sleep_episodes > 0
        self._sleep_deadline = None
        self._sleep_episodes = 0
        self._sleep_fire_pending = False
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
        The timer has run out, or the last episode has ended: stop
        playback, then power the box down.
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
        schedule slot's start time), plus "bg_prev" and "bg_next" from the
        edge buttons on Home (BG-STEP, see _bg_step).
        </summary>
        """
        cmd = self._take_command("bg_command")
        if not cmd:
            return
        if cmd in ("bg_prev", "bg_next"):
            # BG-STEP: property writes only, so no dialog thread.
            self._bg_step(cmd)
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
            text = self._age_rule_from_path(path, "title")
            target = self._age_node(kind, years, genre, text)
            _dlog("age filter: {0} older than {1}y genre {2!r} search {3!r} -> {4}".format(
                kind, years, genre, text, target[:80]))
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
        # Below a show (its seasons and episodes) Kodi keeps the parent
        # node's query string, so a season opened from a searched or age
        # filtered TV titles node still carries that tvshows playlist. Kodi
        # ignores it there; reading it back made the side menu claim a
        # search over a list that was not filtered. Only an episodes
        # playlist counts at that depth.
        kinds = ("episodes",) if self.SHOW_CHILD_RE.match(path) else None
        cutoff = self._safe_int(self._age_rule_from_path(path, "year", kinds), 0)
        want = str(time.localtime().tm_year - cutoff) if cutoff else ""
        if xbmc.getInfoLabel("Skin.String(age_filter)").strip() != want:
            _set_skin_string("age_filter", want)
        # Same idea for the search text: the menu row shows what the node on
        # screen is actually filtered by, not what was last typed. At the
        # collections level the text is the "set contains" rule and the Show
        # state is the playlist's name (LIB-COLLECTIONS).
        text = self._age_rule_from_path(path, "title", kinds)
        state = ""
        if path.startswith(self.SETS_NODE):
            text, state = self._sets_filter_from_path(path)
        if xbmc.getInfoLabel("Skin.String(search_active)").strip() != text:
            _set_skin_string("search_active", text)
        if xbmc.getInfoLabel("Skin.String(collections_state)").strip() != state:
            _set_skin_string("collections_state", state)

    # ---- Collections (LIB-COLLECTIONS) ------------------------------------
    SETS_NODE = "videodb://movies/sets/"
    # Show states in cycle order; "" is All.
    COLLECTION_STATES = ("", "unfinished", "notstarted")

    @staticmethod
    def _xsp_from_path(path):
        """
        <summary>
        The playlist dict a videodb URL carries in its xsp parameter.
        </summary>
        <param name="path">Container.FolderPath.</param>
        <returns>The decoded playlist, or an empty dict when there is none or it does not parse.</returns>
        """
        if "xsp=" not in (path or ""):
            return {}
        try:
            raw = urllib.parse.parse_qs(urllib.parse.urlparse(path).query).get("xsp", [""])[0]
            playlist = json.loads(raw)
        except (ValueError, TypeError, AttributeError):
            return {}
        return playlist if isinstance(playlist, dict) else {}

    @classmethod
    def _sets_filter_from_path(cls, path):
        """
        <summary>
        What the collections node on screen is filtered by.
        </summary>
        <param name="path">Container.FolderPath.</param>
        <returns>(text, state): the "set contains" text and the Show state,
        each "" when absent. The state is the playlist's name, which
        _sets_node writes for exactly this purpose; the "set is" names
        rule is not read back, the names would be stale by then.</returns>
        """
        if not (path or "").startswith(cls.SETS_NODE):
            return "", ""
        playlist = cls._xsp_from_path(path)
        state = playlist.get("name", "")
        if state not in cls.COLLECTION_STATES:
            state = ""
        text = ""
        for rule in (playlist.get("rules") or {}).get("and") or []:
            if (isinstance(rule, dict) and rule.get("field") == "set"
                    and rule.get("operator") == "contains"):
                values = rule.get("value") or []
                text = str(values[0]) if values else ""
        return text, state

    @classmethod
    def _at_collections(cls, path):
        """
        <summary>
        True on the collections node itself, filtered or not, and not
        inside a collection, whose content is plain movies.
        </summary>
        """
        return path.startswith(cls.SETS_NODE) and xbmc.getCondVisibility("Container.Content(sets)")

    def _collection_names(self, state):
        """
        <summary>
        Names of the collections in a Show state.
        </summary>
        <param name="state">"unfinished" (some films watched, some not) or
        "notstarted" (none watched); anything else gives no names.</param>
        <returns>Sorted names; empty when no collection is in that state.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        <remarks>
        One VideoLibrary.GetMovies over the whole library with two
        properties, which is cheap even for thousands of films and avoids
        a call per collection. Films in no collection are skipped.
        </remarks>
        """
        rows = _result_rows(_jsonrpc("VideoLibrary.GetMovies", {
            "properties": ["set", "playcount"]}), "movies")
        counts = {}
        for row in rows:
            name = row.get("set") or ""
            if not name:
                continue
            total, watched = counts.get(name, (0, 0))
            counts[name] = (total + 1, watched + (1 if (row.get("playcount") or 0) > 0 else 0))
        if state == "unfinished":
            return sorted(n for n, (t, w) in counts.items() if 0 < w < t)
        if state == "notstarted":
            return sorted(n for n, (t, w) in counts.items() if w == 0)
        return []

    def _sets_node(self, text, state):
        """
        <summary>
        The collections node filtered by a name search and a Show state.
        </summary>
        <param name="text">Text the collection name must contain, "" for none.</param>
        <param name="state">A COLLECTION_STATES value, "" for All.</param>
        <returns>The plain sets node with neither, else the node with a
        playlist grouped by sets: Kodi only applies a playlist to the sets
        node when its group is sets (as an object with a type, the JSON
        form its loader reads), and even then ignores play count rules,
        hence the state as a list of names. A state with no collection in
        it names one that cannot exist, so the screen shows an empty list
        rather than everything.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        """
        rules = []
        if text:
            rules.append({"field": "set", "operator": "contains", "value": [text]})
        if state:
            rules.append({"field": "set", "operator": "is",
                          "value": self._collection_names(state) or ["\u0001"]})
        if not rules:
            return self.SETS_NODE
        xsp = {"name": state or "search", "type": "movies",
               "group": {"type": "sets", "mixed": False}, "rules": {"and": rules}}
        return self.SETS_NODE + "?xsp=" + urllib.parse.quote(
            json.dumps(xsp, separators=(",", ":")))

    def update_collections_command(self):
        """
        <summary>
        Watch Skin.String(collections_command): "cycle" steps the Show
        state of the collections node on screen (see the module notes).
        </summary>
        <remarks>
        Runs through _spawn_dialog although it opens no dialog: the names
        come from the library, which must never be queried on the loop.
        </remarks>
        """
        cmd = self._take_command("collections_command", lower=True)
        if cmd == "cycle":
            self._spawn_dialog(self._collections_cycle)

    def _collections_cycle(self):
        """
        <summary>
        Worker: reload the collections node with the next Show state,
        keeping any name search in force. Ignored off that node.
        </summary>
        """
        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        if not self._at_collections(path):
            return
        text, state = self._sets_filter_from_path(path)
        state = self.COLLECTION_STATES[
            (self.COLLECTION_STATES.index(state) + 1) % len(self.COLLECTION_STATES)]
        try:
            target = self._sets_node(text, state)
        except LookupError as exc:
            _dlog("collections: {0}".format(exc), xbmc.LOGWARNING)
            return
        _dlog("collections: show {0!r} search {1!r} -> {2}".format(state or "all", text, target[:100]))
        xbmc.executebuiltin("Container.Update({0})".format(target))
        self._age_last_path = None

    # ---- Home tiles (the main menu, eight configurable slots) --------------
    TILE_SLOTS = 8
    TILE_DEFAULTS = ("movies", "tvshows", "music", "pictures", "weather", "lists", "stats", "none")
    TILE_NAMES = {"movies": 31009, "tvshows": 31093, "music": 31011, "pictures": 31094, "weather": 31095, "lists": 31024, "stats": 31406, "favourites": 31007, "addons": 31005, "settings": 31218}
    TILE_LEGACY_HIDE = {"movies": "hide_movies", "tvshows": "hide_tvshows", "music": "hide_music",
                        "pictures": "hide_pictures", "lists": "hide_lists", "stats": "hide_stats_menu"}

    def update_tiles(self):
        """
        <summary>
        Resolve the eight main menu slots and publish Tile.N.Kind, Label
        and KindLabel Home properties for Home.xml and the settings page.
        </summary>
        <remarks>
        Fast ticker: some thirty cheap infolabel reads, and a write only
        when any of them changed. A slot's kind is Skin.String(tileN); empty
        means the slot's built in default (the menu as it was before tiles),
        which still honours the old show and hide toggles so nobody's setup
        changes on upgrade. An explicit kind ignores those toggles. Kind is
        published empty when the slot is hidden: Off, Stats without
        JellyStat, or a favourite slot with no favourite chosen yet. The
        label is the user's own text if set, else the favourite's name, else
        the kind's name.
        </remarks>
        """
        toggles = tuple(xbmc.getCondVisibility("Skin.HasSetting({0})".format(k))
                        for k in ("hide_movies", "hide_tvshows", "hide_music", "hide_pictures",
                                  "show_weather", "hide_lists", "hide_stats_menu"))
        has_stats = xbmc.getCondVisibility("System.HasAddon(script.jellystat)")
        raw = []
        for n in range(1, self.TILE_SLOTS + 1):
            raw.append((xbmc.getInfoLabel("Skin.String(tile{0})".format(n)).strip().lower(),
                        xbmc.getInfoLabel("Skin.String(tile{0}_label)".format(n)).strip(),
                        xbmc.getInfoLabel("Skin.String(tile{0}_fav)".format(n)).strip()))
        signature = (toggles, has_stats, tuple(raw))
        if signature == self._tiles_seen:
            return
        self._tiles_seen = signature
        hide_movies, hide_tv, hide_music, hide_pics, show_weather, hide_lists, hide_stats = toggles
        legacy_hidden = {"movies": hide_movies, "tvshows": hide_tv, "music": hide_music,
                         "pictures": hide_pics, "weather": not show_weather, "lists": hide_lists,
                         "stats": hide_stats or not has_stats, "none": True}
        win = xbmcgui.Window(HOME_WINDOW_ID)
        shown = 0
        for n, (kind, label, fav) in enumerate(raw, 1):
            default = self.TILE_DEFAULTS[n - 1]
            using_default = kind not in self.TILE_NAMES and kind not in ("fav", "none")
            effective = default if using_default else kind
            if using_default:
                hidden = legacy_hidden.get(default, True)
            else:
                hidden = (kind == "none" or (kind == "stats" and not has_stats)
                          or (kind == "fav" and not fav))
            if effective == "fav":
                kind_label = "{0}: {1}".format(_L(31495), fav or _L(31501))
                name = fav or _L(31501)
            elif effective == "none":
                kind_label = _L(31494)
                name = ""
            else:
                name = _L(self.TILE_NAMES[effective])
                if using_default and hidden:
                    # The slot's default is switched off for this box (the
                    # Weather default without the old show weather toggle,
                    # the Stats default without its add-on). The settings
                    # row used to read "Weather (default)" beside a Home
                    # screen with no Weather tile; say what Home shows.
                    kind_label = _L(31494) + " " + _L(31500)
                else:
                    kind_label = name + (" " + _L(31500) if using_default else "")
            win.setProperty("Tile.%d.Kind" % n, "" if hidden else effective)
            win.setProperty("Tile.%d.Label" % n, label or name)
            win.setProperty("Tile.%d.KindLabel" % n, kind_label)
            shown += 0 if hidden else 1
        win.setProperty("Tile.Count", str(shown))
        self._tiles_shown = shown
        # Home's tiles are gated on the properties just written, so on a
        # cold start the menu did not exist when Kodi placed its default
        # focus; see update_home_focus.
        self._home_focus_checks = self.HOME_FOCUS_TICKS
        _dlog("tiles: " + ", ".join(
            "{0}={1}".format(n, win.getProperty("Tile.%d.Kind" % n) or "off")
            for n in range(1, self.TILE_SLOTS + 1)))

    HOME_FOCUS_TICKS = 12      # fast ticks update_home_focus keeps looking, about three seconds
    HOME_MENU_ID = 9000        # Home.xml: the tile row
    HOME_CORNER_BAR_ID = 9190  # Home.xml: the group holding the corner bar

    def update_home_focus(self):
        """
        <summary>
        Give Home a focused control when it has none after the tiles were
        published.
        </summary>
        <remarks>
        Fast tick, and idle except for a few ticks after update_tiles has
        written. Every tile is visible only once its Tile.N.Kind property
        exists, and those are first written three seconds after the service
        starts, by which time Home has already tried to focus an empty menu
        and given up; Kodi does not try again when the menu fills. Home then
        sat with nothing lit and swallowed the first key press. With every
        tile set to Off there is no menu to focus at all, so the corner bar
        is focused instead, which is the only way left to reach Settings.
        Does nothing while another window or a dialog is in front, or once
        anything on Home has focus.
        </remarks>
        """
        if self._home_focus_checks <= 0:
            return
        self._home_focus_checks -= 1
        if (not xbmc.getCondVisibility("Window.IsActive(home)")
                or xbmc.getCondVisibility("System.HasActiveModalDialog")):
            return
        if xbmc.getInfoLabel("System.CurrentControlID").strip():
            self._home_focus_checks = 0
            return
        target = self.HOME_MENU_ID if self._tiles_shown else self.HOME_CORNER_BAR_ID
        xbmc.executebuiltin("SetFocus({0})".format(target))

    STARTUP_WATCH_TICKS = 240  # fast ticks update_startup_fallback keeps watching, about a minute

    def update_startup_fallback(self):
        """
        <summary>
        Leave the startup splash if its own one shot alarm did not manage to.
        </summary>
        <remarks>
        Fast tick, for the first minute after the service starts and only
        until the splash has been seen to go. Startup.xml hands over to the
        configured startup window from an alarm that fires once, a second
        after it loads. Kodi refuses ReplaceWindow while a modal dialog is
        up (an add-on's first run prompt, say), and nothing tried again, so
        the splash could be left on screen with no controls once the dialog
        closed. This is that second try: the same ReplaceWindow, as soon as
        the splash is in front with no dialog over it.
        </remarks>
        """
        if self._startup_watch <= 0:
            return
        self._startup_watch -= 1
        if not xbmc.getCondVisibility("Window.IsActive(startup)"):
            if self._startup_watch < self.STARTUP_WATCH_TICKS - 8:
                # Gone, and has been for a couple of seconds: the hand over
                # worked, nothing more to watch for.
                self._startup_watch = 0
            return
        if xbmc.getCondVisibility("System.HasActiveModalDialog"):
            return
        target = xbmc.getInfoLabel("System.StartupWindow").strip()
        if target:
            _dlog("startup: the splash was still up, handing over to {0}".format(target))
            xbmc.executebuiltin("ReplaceWindow({0})".format(target))
            # Give it time to act before trying again.
            self._startup_watch = min(self._startup_watch, self.STARTUP_WATCH_TICKS) - 8

    def update_tile_command(self):
        """
        <summary>
        Watch Skin.String(tile_command): run:N opens the favourite behind
        tile N, pick:N asks which favourite that tile should hold.
        </summary>
        <remarks>Cheap enough to call every tick. The pick is a blocking
        select dialog, so it goes through _spawn_dialog.</remarks>
        """
        cmd = self._take_command("tile_command", lower=True)
        if not cmd or ":" not in cmd:
            return
        verb, _sep, number = cmd.partition(":")
        n = self._safe_int(number, 0)
        if not 1 <= n <= self.TILE_SLOTS:
            return
        if verb == "run":
            self._tile_run(n)
        elif verb == "pick":
            self._spawn_dialog(lambda: self._tile_pick(n))

    def _tile_run(self, n):
        """
        <summary>
        Execute the favourite named in Skin.String(tileN_fav).
        </summary>
        <param name="n">1-based slot number.</param>
        <remarks>Favourites are matched by name against the parsed
        favourites.xml, which is reloaded when it changed on disk, so a
        favourite renamed in Kodi simply stops matching until the tile is
        picked again.</remarks>
        """
        name = xbmc.getInfoLabel("Skin.String(tile{0}_fav)".format(n)).strip()
        self._read_favourites()
        for item in self._fav_all:
            # Compared the way _set_skin_string stored it: double quotes
            # dropped, edges trimmed. A favourite named with either could be
            # picked for a tile and then never ran.
            if name and item["name"].replace('"', '').strip() == name:
                _dlog("tile %d runs favourite %r: %s" % (n, name, item["action"]))
                xbmc.executebuiltin(item["action"])
                return
        _dlog("tile %d: favourite %r not found" % (n, name), xbmc.LOGWARNING)
        # "Not chosen yet" only when that is true; a name that no longer
        # matches anything means the favourite was renamed or removed.
        xbmcgui.Dialog().notification(
            _L(31000), _L(31576) if name else _L(31501),
            xbmcgui.NOTIFICATION_INFO, 3500)

    def _tile_pick(self, n):
        """
        <summary>
        Dialog thread: choose a favourite for tile N from Kodi's list and
        make the tile a favourite tile.
        </summary>
        <param name="n">1-based slot number.</param>
        """
        self._read_favourites()
        names = [item["name"] for item in self._fav_all if item["name"]]
        if not names:
            xbmcgui.Dialog().notification(_L(31000), _L(31499), xbmcgui.NOTIFICATION_INFO, 3500)
            return
        current = xbmc.getInfoLabel("Skin.String(tile{0}_fav)".format(n)).strip()
        preselect = names.index(current) if current in names else -1
        choice = xbmcgui.Dialog().select(_L(31498).format(n), names, preselect=preselect)
        if choice < 0:
            return
        _set_skin_string("tile{0}_fav".format(n), names[choice])
        _set_skin_string("tile{0}".format(n), "fav")
        _dlog("tile %d set to favourite %r" % (n, names[choice]))

    def update_accent(self):
        """
        <summary>
        Keep Skin.String(accent_custom_hi) as a lighter shade of the custom
        accent the colour picker stored in Skin.String(accent_custom).
        </summary>
        <remarks>
        Fast ticker, one infolabel read a tick, a write only when the picked
        value changes. The shade is the accent blended a third of the way to
        white, channel by channel, alpha kept, which is roughly the step
        between the preset accents and their preset highlights in
        Includes.xml. A value that is not eight hex digits leaves the
        highlight alone rather than publishing rubbish.
        </remarks>
        """
        value = xbmc.getInfoLabel("Skin.String(accent_custom)").strip().upper()
        if value == self._accent_custom_seen:
            return
        self._accent_custom_seen = value
        if not re.fullmatch(r"[0-9A-F]{8}", value):
            _set_skin_string("accent_custom_hi", "")
            return
        channels = [int(value[i:i + 2], 16) for i in (2, 4, 6)]
        lighter = "".join("{0:02X}".format(c + (255 - c) // 3) for c in channels)
        _set_skin_string("accent_custom_hi", value[:2] + lighter)
        _dlog("accent: custom {0} -> highlight {1}".format(value, value[:2] + lighter))

    # THEME-SEASON. Seasonal themes: see update_theme.
    THEME_NAMES = ("halloween", "devilsnight", "christmas", "christmaseve")
    HALLOWEEN_THEMES = ("halloween", "devilsnight")
    CHRISTMAS_THEMES = ("christmas", "christmaseve")
    # colors/<name>.xml for each theme, by Kodi's name for the set
    THEME_COLOURS = {"halloween": "halloween", "devilsnight": "halloween",
                     "christmas": "christmas", "christmaseve": "christmas"}
    THEME_COLOURS_DEFAULT = "SKINDEFAULT"
    SLEIGH_SECS = 16.5                 # XmasSleigh's crossing is 16 s
    SLEIGH_LAND_SECS = 20.5            # and the landing 20 s
    THEME_LOOK_EVERY = 30.0            # seconds between reads of Kodi's colour setting
    CROW_LAND_SECS = 6.5               # ThemeCrow's landing slide is 6 s
    CROW_LEAVE_SECS = 5.5              # and its take off 5 s

    @classmethod
    def _season_theme(cls, now, halloween=True, christmas=True):
        """
        <summary>
        The theme the calendar asks for at the given local time, or "".
        </summary>
        <param name="now">A time.struct_time in local time.</param>
        <param name="halloween">Let the Halloween season count.</param>
        <param name="christmas">Let the Christmas season count.</param>
        <returns>"devilsnight" on 30 October, "halloween" on 29 and 31
        October; "christmaseve" on 24 December, "christmas" from the first
        Saturday of December to the end of 26 December; otherwise "".</returns>
        <remarks>
        Local time on purpose: a season starts and ends at the box's own
        midnight. One exception: Christmas Eve runs on until ten past
        midnight, so Santa's sleigh, which sets off at 23:59:40, finishes
        landing on the roof before the theme turns to Christmas Day. The
        two flags are the two "every year" switches in Skin Settings.
        </remarks>
        """
        if halloween and now.tm_mon == 10 and now.tm_mday >= 29:
            return "devilsnight" if now.tm_mday == 30 else "halloween"
        if christmas and now.tm_mon == 12:
            first_saturday = 1 + (5 - datetime.date(now.tm_year, 12, 1).weekday()) % 7
            if now.tm_mday == 24 or (now.tm_mday == 25 and now.tm_hour == 0 and now.tm_min < 10):
                return "christmaseve"
            if first_saturday <= now.tm_mday <= 26:
                return "christmas"
        return ""

    @staticmethod
    def _theme_prop(key, value):
        """
        <summary>
        Write a Home property only when it differs from what is there.
        </summary>
        <param name="key">Property name.</param>
        <param name="value">New value; "" clears it.</param>
        <remarks>
        Compared against the window rather than a cached copy, so a property
        lost to a skin reload (the colour switch causes one) is put back on
        the next tick instead of waiting for the theme to change.
        </remarks>
        """
        home = xbmcgui.Window(HOME_WINDOW_ID)
        if home.getProperty(key) == value:
            return
        if value:
            home.setProperty(key, value)
        else:
            home.clearProperty(key)

    def update_theme(self):
        """
        <summary>
        Work out the theme in force, publish it for the XML, keep Kodi's
        colour set in step with it, and drive the theme's moving parts.
        </summary>
        <remarks>
        Slow tick. The pick in Skin Settings is Skin.String(theme): empty,
        halloween, devilsnight, christmas or christmaseve. In season the
        calendar wins over the pick: from 29 to 31 October (Halloween, and
        Devil's Night on the 30th) unless Skin.HasSetting(theme_seasonal_off)
        is on, and from the first Saturday of December to the end of Boxing
        Day (Christmas, and Christmas Eve on the 24th) unless
        Skin.HasSetting(theme_christmas_off) is on. The result goes out as
        Home properties:
            theme_name      halloween, devilsnight, christmas, christmaseve or empty
            theme_seasonal  halloween or christmas while the calendar is the reason
            theme_level     0 to 3, the yearly build-up, see _theme_intro_check
            theme_crow, theme_spider1/2, theme_witch, theme_ghosts,
            theme_bats      see _theme_motion
            theme_sleigh    see _theme_sleigh
        The colours are Kodi's own lookandfeel.skincolors setting, see
        _theme_colours. Everything else is the XML reading theme_name.
        </remarks>
        """
        manual = xbmc.getInfoLabel("Skin.String(theme)").strip()
        if manual not in self.THEME_NAMES:
            manual = ""
        seasonal = self._season_theme(
            time.localtime(),
            halloween=not xbmc.getCondVisibility("Skin.HasSetting(theme_seasonal_off)"),
            christmas=not xbmc.getCondVisibility("Skin.HasSetting(theme_christmas_off)"))
        want = seasonal or manual
        # The yearly build-up is Halloween's alone (THEME-CHRISTMAS).
        self._theme_intro_check(seasonal if seasonal in self.HALLOWEEN_THEMES else "", manual)
        if want != self._theme_seen:
            _dlog("theme: {0} (season {1}, pick {2})".format(
                want or "none", seasonal or "none", manual or "none"))
            self._theme_seen = want
        self._theme_prop("theme_name", want)
        season = ""
        if seasonal:
            season = "halloween" if seasonal in self.HALLOWEEN_THEMES else "christmas"
        self._theme_prop("theme_seasonal", season)
        self._theme_colours(self.THEME_COLOURS.get(want, self.THEME_COLOURS_DEFAULT))
        self._theme_motion(want)

    def _theme_intro_check(self, seasonal, manual):
        """
        <summary>
        Start the yearly build-up when the season switches Halloween on by
        itself for the first time this year.
        </summary>
        <param name="seasonal">The theme the calendar asks for, or "".</param>
        <param name="manual">The theme picked in Skin Settings, or "".</param>
        <remarks>
        Asked for on 12/10/2026: the first time each year, Halloween starts
        with the red tint alone and builds up over half an hour (INTRO);
        every other start, a restart of Kodi or a theme picked by hand,
        has everything at once. The year is kept in
        Skin.String(theme_intro_year) and written the moment the season is
        first met, so a restart part way through comes back at full
        strength rather than starting over. When that first meeting is on
        Devil's Night, or Halloween is already picked by hand, the year is
        spent without a build-up.
        </remarks>
        """
        if not seasonal:
            self._season_seen = False
            return
        if self._season_seen:
            return
        self._season_seen = True
        year = str(time.localtime().tm_year)
        if xbmc.getInfoLabel("Skin.String(theme_intro_year)").strip() == year:
            return
        _set_skin_string("theme_intro_year", year)
        if seasonal == "halloween" and manual != "halloween":
            self._intro_start = time.monotonic()
            self._intro_step = 0
            self._intro_level = 0
            _dlog("theme: first Halloween of {0}, starting the build-up".format(year))
        else:
            _dlog("theme: first season of {0} met as {1}, no build-up this year".format(year, seasonal))

    def _theme_colours(self, colours):
        """
        <summary>
        Bring Kodi's skin colour setting to the given colour set when it is
        safe to reload the skin.
        </summary>
        <param name="colours">A value of THEME_COLOURS, or THEME_COLOURS_DEFAULT.</param>
        <remarks>
        Changing lookandfeel.skincolors makes Kodi reload the skin, which
        flashes the screen and drops focus to the window's default, so the
        change waits while anything is playing, a modal dialog is up or
        Skin Settings is open; it lands the first quiet second after. The
        setting is read at most every THEME_LOOK_EVERY seconds once it
        matches. Going back to the default only happens from our own set:
        a colour set somebody picked by hand in Kodi's settings is left be.
        A failed read or write is logged and tried again on the next round.
        </remarks>
        """
        now = time.monotonic()
        if colours == self._theme_colours_ok and now - self._theme_colours_at < self.THEME_LOOK_EVERY:
            return
        reply = _jsonrpc("Settings.GetSettingValue", {"setting": "lookandfeel.skincolors"})
        current = ((reply or {}).get("result") or {}).get("value")
        if current is None:
            self._theme_colours_at = now
            return
        ours = set(self.THEME_COLOURS.values())
        if current == colours or (colours == self.THEME_COLOURS_DEFAULT and current not in ours):
            self._theme_colours_ok = colours
            self._theme_colours_at = now
            return
        if xbmc.getCondVisibility(
                "Player.HasMedia | System.HasModalDialog | Window.IsActive(skinsettings) | Window.IsActive(startup)"):
            return
        _dlog("theme: skin colours {0} -> {1}, Kodi reloads the skin".format(current, colours))
        reply = _jsonrpc("Settings.SetSettingValue", {"setting": "lookandfeel.skincolors", "value": colours})
        if (reply or {}).get("result") is not True:
            _dlog("theme: setting the skin colours failed: {0}".format(reply), xbmc.LOGWARNING)
        self._theme_colours_ok = None
        self._theme_colours_at = now

    # THEME-CREATURES. How long each creature is out, in seconds: the
    # animation time in Includes.xml plus a little, so the property is
    # never cleared while it is still on screen.
    SPIDER_SECS = {
        "a_fast": 3.5, "a_slow": 14.5, "b_fast": 3.5, "b_slow": 14.5,
        "c_fast": 3.1, "c_slow": 12.5, "d_fast": 3.1, "d_slow": 12.5,
        "drop_fast": 3.7, "drop_slow": 12.5,
    }
    WITCH_SECS = 11.5
    GHOST_SECS = 19.0                  # set b's second ghost starts 2.5 s late
    BATS_SECS = 9.0
    CREATURE_KEYS = ("theme_spider1", "theme_spider2", "theme_witch", "theme_ghosts", "theme_bats")
    # The yearly build-up: (seconds from the start, what, which). It runs
    # once a year, the first time the season switches Halloween on by
    # itself; see _theme_intro. "level" moves Window(home).Property
    # (theme_level): 0 the red tint and nothing else, 1 the fog and dark
    # corners roll in, 3 everything at random. Nine minutes of nothing
    # first, then it gathers pace over about half an hour. Level 2 used to
    # start the lightning; no theme has had any since it was asked to go
    # on 12/10/2026, so the build-up steps from 1 to 3.
    INTRO = (
        (0, "level", 0),
        (540, "spider", "a_fast"),
        (600, "spider", "b_fast"),
        (780, "witch", "rtl"),
        (960, "spider", "c_slow"),
        (1000, "spider", "d_fast"),
        (1140, "level", 1),
        (1230, "ghosts", "a"),
        (1350, "spider", "drop_slow"),
        (1360, "spider", "a_fast"),
        (1470, "bats", "1"),
        (1590, "witch", "ltr"),
        (1680, "spider", "b_slow"),
        (1690, "spider", "c_fast"),
        (1700, "spider", "d_fast"),
        (1800, "ghosts", "b"),
        (1920, "level", 3),
    )

    def _theme_motion(self, theme):
        """
        <summary>
        Step the crow, the creatures and the sleigh for the theme in force.
        </summary>
        <param name="theme">The theme update_theme settled on.</param>
        <remarks>
        Called once a second. The crow only exists on Devil's Night: it
        lands on Eric's stone, sits, now and then taps the stone or caws,
        and every four to seven minutes flies off and comes back a little
        later. Spiders, the witch, ghosts and bats are Halloween only:
        scripted by INTRO during the yearly build-up, at random after it
        (_theme_creatures_random). No theme has lightning: it was taken
        out of all of them when asked on 12/10/2026. Outside a Halloween theme every property
        is cleared and the timers start over, so the crow lands afresh
        when Devil's Night begins. Monotonic time throughout, so a clock
        step does not freeze or rush a state.
        </remarks>
        """
        now = time.monotonic()
        if theme not in self.THEME_NAMES:
            if self._crow_state is not None or self._theme_motion_live:
                self._crow_state = None
                self._theme_motion_live = False
                self._intro_start = None
                self._creatures = {}
                self._sleigh = ("", 0.0)
                for key in ("theme_crow", "theme_level", "theme_sleigh") + self.CREATURE_KEYS:
                    self._theme_prop(key, "")
            return
        if not self._theme_motion_live:
            self._theme_motion_live = True
            self._theme_next = {
                "spider": now + random.uniform(10, 30),
                "witch": now + random.uniform(60, 120),
                "ghosts": now + random.uniform(40, 90),
                "bats": now + random.uniform(20, 60),
            }

        level = 3
        if theme != "halloween":
            self._intro_start = None   # Devil's Night ends a build-up still running
        if self._intro_start is not None:
            level = self._theme_intro(now)
        elif theme == "halloween":
            self._theme_creatures_random(now)
        self._theme_prop("theme_level", str(level))

        if theme == "devilsnight":
            self._theme_crow(now)
        elif self._crow_state is not None:
            self._crow_state = None
            self._theme_prop("theme_crow", "")

        for key in self.CREATURE_KEYS:
            value, until = self._creatures.get(key, ("", 0.0))
            self._theme_prop(key, value if theme == "halloween" and now < until else "")

        self._theme_sleigh(theme, now)

    def _theme_sleigh(self, theme, now):
        """
        <summary>
        Step Santa's sleigh for the Christmas themes and publish it.
        </summary>
        <param name="theme">The theme in force.</param>
        <param name="now">time.monotonic() of this tick.</param>
        <remarks>
        THEME-CHRISTMAS. Window(home).Property(theme_sleigh) is rtl or ltr
        while it crosses the sky, landing while it comes down on the long
        roof, parked once it is there. It crosses every six to twelve
        minutes at Christmas and every one to two and a half minutes on
        Christmas Eve. At 23:59:40 on 24 December it sets off to land, so
        it touches down at midnight, and on Christmas Day it stays parked
        on the roof all day (Santa is down the chimney); on Boxing Day it
        crosses again. The landing goes by the wall clock, so it only
        happens on the real night, never for a Christmas Eve picked by hand.
        </remarks>
        """
        if theme not in self.CHRISTMAS_THEMES:
            self._sleigh_next = 0.0
            if self._sleigh[0]:
                self._sleigh = ("", 0.0)
                self._theme_prop("theme_sleigh", "")
            return
        state, until = self._sleigh
        lt = time.localtime()
        christmas_day = lt.tm_mon == 12 and lt.tm_mday == 25
        touchdown = (lt.tm_mon == 12 and lt.tm_mday == 24 and lt.tm_hour == 23
                     and lt.tm_min == 59 and lt.tm_sec >= 40)
        # No crossing may start in the last twenty seconds before touchdown:
        # one started at 23:59:38 was cut short by the landing and the
        # sleigh jumped. A crossing takes SLEIGH_SECS, so one started by
        # 23:59:20 is gone before 23:59:40.
        quiet = (lt.tm_mon == 12 and lt.tm_mday == 24 and lt.tm_hour == 23
                 and lt.tm_min == 59 and lt.tm_sec >= 20)
        if touchdown and state not in ("landing", "parked"):
            self._sleigh = ("landing", now + self.SLEIGH_LAND_SECS)
            _dlog("theme: Santa is landing")
        elif state == "landing" and now < until:
            pass  # still coming down; it lands just after midnight
        elif christmas_day:
            self._sleigh = ("parked", now + 3600)
        elif state in ("landing", "parked"):
            self._sleigh = ("", 0.0)
        elif not state or now >= until:
            if not state and self._sleigh_next == 0.0:
                self._sleigh_next = now + random.uniform(20, 60)
            if now >= until + 1.0 and now >= self._sleigh_next and not quiet:
                self._sleigh = (random.choice(("rtl", "ltr")), now + self.SLEIGH_SECS)
                gap = (60, 150) if theme == "christmaseve" else (360, 720)
                self._sleigh_next = now + self.SLEIGH_SECS + random.uniform(*gap)
        state, until = self._sleigh
        shown = state if state in ("landing", "parked") or now < until else ""
        self._theme_prop("theme_sleigh", shown)

    def _theme_intro(self, now):
        """
        <summary>
        Play the yearly build-up up to now and say what level it has reached.
        </summary>
        <param name="now">time.monotonic() of this tick.</param>
        <returns>The theme level, 0 to 3.</returns>
        <remarks>
        Steps fire in order as their time comes, each once; a spider goes
        to whichever slot is free, and is dropped if both are busy, which
        the timings in INTRO are spaced to avoid. When the last step has
        fired the build-up is over and the random scheduler takes over
        from the next tick, with its first creatures due straight away.
        </remarks>
        """
        elapsed = now - self._intro_start
        while self._intro_step < len(self.INTRO) and self.INTRO[self._intro_step][0] <= elapsed:
            _secs, what, which = self.INTRO[self._intro_step]
            self._intro_step += 1
            if what == "level":
                self._intro_level = which
                _dlog("theme: build-up level {0} at {1:.0f} s".format(which, elapsed))
            else:
                self._creature_start(what, which, now)
        if self._intro_step >= len(self.INTRO):
            self._intro_start = None
            for kind in self._theme_next:
                self._theme_next[kind] = now + random.uniform(5, 30)
            _dlog("theme: build-up over, everything at random from here")
        return self._intro_level

    def _theme_creatures_random(self, now):
        """
        <summary>
        Send the next creature out when it is due, at full strength.
        </summary>
        <param name="now">time.monotonic() of this tick.</param>
        <remarks>
        A spider every 40 seconds to two minutes, on a random path, fast
        a little over half the time; the witch every four to seven
        minutes; ghosts every two and a half to five and a half; bats
        every one to three. A creature that is due while its slot is
        still busy simply waits for the next tick.
        </remarks>
        """
        due = self._theme_next
        if now >= due["spider"]:
            path = random.choice(("a", "b", "c", "d", "drop"))
            speed = "fast" if random.random() < 0.55 else "slow"
            if self._creature_start("spider", "{0}_{1}".format(path, speed), now):
                due["spider"] = now + random.uniform(40, 120)
        if now >= due["witch"] and self._creature_start("witch", random.choice(("rtl", "ltr")), now):
            due["witch"] = now + random.uniform(240, 420)
        if now >= due["ghosts"] and self._creature_start("ghosts", random.choice(("a", "b")), now):
            due["ghosts"] = now + random.uniform(150, 330)
        if now >= due["bats"] and self._creature_start("bats", "1", now):
            due["bats"] = now + random.uniform(60, 180)

    def _creature_start(self, kind, value, now):
        """
        <summary>
        Put a creature out for as long as its animation runs.
        </summary>
        <param name="kind">spider, witch, ghosts or bats.</param>
        <param name="value">The property value its controls show on.</param>
        <param name="now">time.monotonic() of this tick.</param>
        <returns>True when it went out; False when its slot is busy.</returns>
        <remarks>
        A slot counts as busy for one second after its creature is done,
        so the property is cleared for at least a tick and the same
        creature twice in a row starts its animation from the beginning:
        Kodi only replays a Visible animation on a change of visibility.
        </remarks>
        """
        if kind == "spider":
            keys = ("theme_spider1", "theme_spider2")
            secs = self.SPIDER_SECS[value]
        else:
            keys = ("theme_" + kind,)
            secs = {"witch": self.WITCH_SECS, "ghosts": self.GHOST_SECS, "bats": self.BATS_SECS}[kind]
        for key in keys:
            _value, until = self._creatures.get(key, ("", 0.0))
            if now >= until + 1.0:
                self._creatures[key] = (value, now + secs)
                return True
        return False

    def _theme_crow(self, now):
        """
        <summary>
        Step the Devil's Night crow and publish its state.
        </summary>
        <param name="now">time.monotonic() of this tick.</param>
        """
        if self._crow_state is None:
            self._crow_set("landing", now, self.CROW_LAND_SECS)
            self._crow_leave_at = now + random.uniform(240, 420)
        elif now >= self._crow_until:
            state = self._crow_state
            if state == "landing" or state in ("tap", "caw"):
                self._crow_set("perched", now, random.uniform(6, 15))
            elif state == "perched":
                if now >= self._crow_leave_at:
                    self._crow_set("leaving", now, self.CROW_LEAVE_SECS)
                else:
                    roll = random.random()
                    if roll < 0.45:
                        self._crow_set("tap", now, 1.6)
                    elif roll < 0.8:
                        self._crow_set("caw", now, 1.4)
                    else:
                        self._crow_set("perched", now, random.uniform(5, 12))
            elif state == "leaving":
                self._crow_set("away", now, random.uniform(20, 45))
            else:
                self._crow_set("landing", now, self.CROW_LAND_SECS)
                self._crow_leave_at = now + random.uniform(240, 420)
        # Every tick, not only on a change: a skin reload can drop it.
        self._theme_prop("theme_crow", self._crow_state)

    def _crow_set(self, state, now, secs):
        """
        <summary>
        Move the crow to a state for a number of seconds and publish it.
        </summary>
        <param name="state">landing, perched, tap, caw, leaving or away.</param>
        <param name="now">time.monotonic() of this tick.</param>
        <param name="secs">How long the state lasts.</param>
        """
        self._crow_state = state
        self._crow_until = now + secs
        self._theme_prop("theme_crow", state)

    GENRE_ALL = "__all__"  # genre_command value for the picker's "All" row

    def update_genre_command(self):
        """
        <summary>
        Watch Skin.String(genre_command) and open the node for the genre the
        picker row asked for, keeping the age and search filters in force.
        </summary>
        <remarks>
        Fast tick. The value is the genre's name, or GENRE_ALL for the row
        that removes the genre. The picker used to load the genre's own
        library node directly, which threw away an age threshold or a search
        the list was already narrowed by; the other two filters stacked on a
        genre, but only in that order. Going through _age_node makes all
        three stack whichever is chosen last. With no age and no search the
        result is still the genre's own node, so nothing changes for a plain
        genre pick.
        </remarks>
        """
        value = self._take_command("genre_command")
        if not value:
            return
        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        if not path.lower().startswith("videodb://"):
            _dlog("genre: not a library node, ignored: {0}".format(path[:80]))
            return
        kind = "tvshows" if path.lower().startswith("videodb://tvshows") else "movies"
        genre = "" if value == self.GENRE_ALL else value
        years = self._safe_int(xbmc.getInfoLabel("Skin.String(age_filter)"), 0)
        text = self._age_rule_from_path(path, "title")
        target = self._age_node(kind, years, genre, text)
        _dlog("genre: {0} {1!r} older than {2}y search {3!r} -> {4}".format(
            kind, genre, years, text, target[:100]))
        xbmc.executebuiltin("Container.Update({0})".format(target))
        self._age_last_path = None

    def update_search_command(self):
        """
        <summary>
        Watch Skin.String(search_command): "prompt" asks for text and
        reloads the node on screen filtered to titles containing it,
        "clear" reloads it without that rule. Cheap enough to call every tick.
        </summary>
        <remarks>
        The prompt is a blocking keyboard dialog, so it runs through
        _spawn_dialog. Movies and TV show nodes go through _age_node, so the
        search stacks on the genre and age the screen already shows; an
        episode list keeps its own path and gains an episodes playlist with
        the title rule appended as a further query parameter, which is the
        form Kodi honours on a path that already carries tvshowid. Kodi's
        own Filter action was tried first and rejected: on library nodes it
        opens the advanced media filter dialog rather than a keyboard.
        </remarks>
        """
        cmd = self._take_command("search_command", lower=True)
        if cmd == "prompt":
            self._spawn_dialog(self._search_prompt)
        elif cmd == "clear":
            # Off the loop as well: at the collections level a clear can
            # need the library (the names of the state still in force).
            self._spawn_dialog(lambda: self._search_apply(""))

    def _search_prompt(self):
        """
        <summary>
        Dialog thread: ask for the search text, seeded with the text in
        force, and apply it. An empty answer clears the search.
        </summary>
        <remarks>
        xbmc.Keyboard rather than Dialog().input, because input() returns
        the same empty string for Back as for an emptied field. Backing out
        of the keyboard used to clear a search that was in force, and on a
        set, actor or year node with no search it sent the viewer to the
        plain titles node. Only a confirmed answer is applied now.
        </remarks>
        """
        current = xbmc.getInfoLabel("Skin.String(search_active)").strip()
        keyboard = xbmc.Keyboard(current, _L(31479))
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return
        text = (keyboard.getText() or "").strip()
        if not text and not current:
            return  # nothing in force and nothing asked for: leave the node alone
        self._search_apply(text)

    def _search_apply(self, text):
        """
        <summary>
        Reload the node on screen with a title rule for text, or without
        one when text is empty.
        </summary>
        <param name="text">Text the title must contain, "" to clear.</param>
        <remarks>
        Container.Update rather than ActivateWindow for the reason given in
        update_age_command: it swaps the directory in place and reloads the
        plain node even when the screen shows that node's filtered form.
        </remarks>
        """
        path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
        if not path.startswith("videodb://"):
            _dlog("search: not a library node, ignored: {0}".format(path[:80]))
            return
        if self._at_collections(path):
            # LIB-COLLECTIONS: a "set contains" rule, keeping the Show state.
            _, state = self._sets_filter_from_path(path)
            target = self._sets_node(text, state)
        elif xbmc.getCondVisibility("Container.Content(episodes)"):
            parts = urllib.parse.urlsplit(path)
            query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                     if k != "xsp"]
            if text:
                xsp = {"name": "search", "type": "episodes", "rules": {"and": [
                    {"field": "title", "operator": "contains", "value": [text]}]}}
                query.append(("xsp", json.dumps(xsp, separators=(",", ":"))))
            target = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))
        else:
            kind = "tvshows" if xbmc.getCondVisibility("Container.Content(tvshows)") else "movies"
            years = self._safe_int(xbmc.getInfoLabel("Skin.String(age_filter)"), 0)
            target = self._age_node(kind, years, self._genre_for_path(path), text)
        _dlog("search: {0!r} -> {1}".format(text, target[:100]))
        xbmc.executebuiltin("Container.Update({0})".format(target))
        self._age_last_path = None

    def _age_node(self, kind, years, genre, text=""):
        """
        <summary>
        Build the node to open for an age threshold, an optional genre and
        an optional search text.
        </summary>
        <param name="kind">"movies" or "tvshows".</param>
        <param name="years">Threshold in years, 0 for none.</param>
        <param name="genre">Genre name to keep, "" for none.</param>
        <param name="text">Text the title must contain, "" for none.</param>
        <returns>A videodb smart playlist URL; with no rule at all, the plain titles node, or the genre's own node when only the genre is known so the normal Genre controls take over again.</returns>
        <remarks>
        "Older than N years" is a year strictly below the current year
        minus N, so on 2026 a threshold of 20 shows titles up to 2005. The
        three rules stack, which is what lets a search stay inside the genre
        and age the screen already shows.
        </remarks>
        """
        if years <= 0 and genre and not text:
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
        if text:
            rules.append({"field": "title", "operator": "contains", "value": [text]})
        if not rules:
            return self.AGE_NODES[kind]
        xsp = {"name": "age", "type": kind, "rules": {"and": rules}}
        return self.AGE_NODES[kind] + "?xsp=" + urllib.parse.quote(
            json.dumps(xsp, separators=(",", ":")))

    # A node below one show: its seasons, or a season's episodes.
    SHOW_CHILD_RE = re.compile(r"^videodb://tvshows/titles/-?\d+/", re.IGNORECASE)

    @staticmethod
    def _age_rule_from_path(path, field, kinds=None):
        """
        <summary>
        First value of one rule inside the xsp playlist a videodb URL carries.
        </summary>
        <param name="path">Container.FolderPath.</param>
        <param name="field">Rule field to look for, such as "year" or "genre".</param>
        <param name="kinds">Playlist types that count, such as ("episodes",); None accepts any.</param>
        <returns>The rule's first value, or "" when the path carries no such rule or its playlist is of another type.</returns>
        """
        if "xsp=" not in (path or ""):
            return ""
        try:
            query = urllib.parse.urlparse(path).query
            raw = urllib.parse.parse_qs(query).get("xsp", [""])[0]
            playlist = json.loads(raw)
            if kinds is not None and playlist.get("type") not in kinds:
                return ""
            rules = (playlist.get("rules") or {}).get("and") or []
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
        "unwatched": "bg_unwatched",
        "lastplayed": "bg_lastplayed",
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
        The clear is requested before the value is handed back, and the same
        value is not handed back again until the clear has been seen to
        land, so a command cannot fire twice however long the handler takes
        or Kodi takes to apply the reset. Every channel ends in _command or _run, which
        BACKUP_SKIP_SUFFIXES relies on to keep them out of a restore. This
        used to be written out at every site; one helper means one place to
        log or validate when the next channel arrives.
        </remarks>
        """
        value = xbmc.getInfoLabel("Skin.String({0})".format(key)).strip()
        if not value:
            _COMMANDS_TAKEN.pop(key, None)
            return ""
        # The Skin.Reset below is posted to Kodi's main thread, not applied
        # here. If that thread is busy for longer than one tick the string
        # still reads the same next time round, and without this test the
        # one click was taken twice: a layout step of 10 became 20, a cache
        # preset was skipped, a favourite ran twice. A value identical to
        # the one just taken is therefore ignored until the string has been
        # seen empty, or COMMAND_REPEAT_SECS have passed, after which it is
        # treated as a fresh click (and reset again).
        taken = _COMMANDS_TAKEN.get(key)
        now = time.time()
        if taken and taken[0] == value and (now - taken[1]) < COMMAND_REPEAT_SECS:
            return ""
        _COMMANDS_TAKEN[key] = (value, now)
        _reset_skin_string(key)
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
            _reset_skin_string(key)

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

    BG_PENDING_SECS = 2.0  # how long a value this service wrote outranks what the store reads

    def _bg_get(self, key):
        """
        <summary>
        Read a background skin string, seeing this service's own recent
        writes even before Kodi has applied them.
        </summary>
        <param name="key">Skin string name, a live key or a slot key.</param>
        <returns>The value last written through _bg_put if that write may not have landed yet, otherwise what the store holds.</returns>
        <remarks>
        Skin.SetString and Skin.Reset are posted to Kodi's main thread and
        applied later, while a read is answered at once. The schedule code
        copies slot to live and live to slot within one call, and reading
        back the value it had only just asked for returned the old one:
        enabling the schedule for the first time inside skin settings
        emptied the live background settings, and an edit made in the last
        second before closing settings was overwritten by the older value.
        A pending value is dropped as soon as the store agrees with it, or
        after BG_PENDING_SECS, so a change made by the user through the
        settings page wins from then on.
        </remarks>
        """
        actual = xbmc.getInfoLabel("Skin.String({0})".format(key))
        pending = self._bg_pending.get(key)
        if pending is None:
            return actual
        value, expires = pending
        if actual == value or time.time() >= expires:
            self._bg_pending.pop(key, None)
            return actual
        return value

    def _bg_put(self, key, value):
        """
        <summary>
        Write a background skin string, or clear it when the value is empty,
        unless it already holds that value.
        </summary>
        <param name="key">Skin string name, a live key or a slot key.</param>
        <param name="value">Text to store; empty clears the string so String.IsEmpty conditions keep working.</param>
        <remarks>
        "Already holds" is judged through _bg_get, so a write still in
        flight counts. The value is remembered as pending for the same
        reason, see _bg_get.
        </remarks>
        """
        if value == self._bg_get(key):
            return
        if value:
            _set_skin_string(key, value)
        else:
            _reset_skin_string(key)
        self._bg_pending[key] = (value, time.time() + self.BG_PENDING_SECS)

    def _bg_slot_store(self, slot):
        """
        <summary>
        Copy the live background settings into slot *slot*'s storage.
        </summary>
        """
        for key, live in self.BG_SCHED_LIVE.items():
            self._bg_put("bg_slot{0}_{1}".format(slot, key), self._bg_get(live))

    def _bg_slot_load(self, slot):
        """
        <summary>
        Copy slot *slot*'s stored settings into the live background keys.
        </summary>
        """
        for key, live in self.BG_SCHED_LIVE.items():
            self._bg_put(live, self._bg_get("bg_slot{0}_{1}".format(slot, key)))

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
            if self._bg_get("bg_slot{0}_seeded".format(n)):
                continue
            self._bg_put("bg_slot{0}_seeded".format(n), "1")
            if not self._bg_get("bg_slot{0}_start".format(n)):
                self._bg_put("bg_slot{0}_start".format(n),
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
            start = self._parse_hhmm(self._bg_get("bg_slot{0}_start".format(n)))
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

    # What the library is asked for per slideshow row. Movies carry the
    # fields the Add To List button needs (BG-ADD); a show only needs what
    # the caption shows, there is no button for one.
    BG_MOVIE_PROPS = ["art", "title", "year", "lastplayed", "file", "runtime"]
    BG_SHOW_PROPS = ["art", "title", "year", "lastplayed", "file"]

    def _fetch_recent_movies(self):
        """
        <summary>
        Up to BG_COUNT recently watched movies as slideshow item dicts.
        </summary>
        <returns>The items, newest played first; empty when nothing has been watched.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        """
        params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "descending", "method": "lastplayed"},
            "filter": {"field": "playcount", "operator": "greaterthan", "value": "0"},
            "properties": self.BG_MOVIE_PROPS,
        }
        return self._fanart_items(_result_rows(
            _jsonrpc("VideoLibrary.GetMovies", params), "movies"), "movie")

    def _fetch_folder_images(self, folder):
        """
        <summary>
        BG-STEP: the pictures in a folder as slideshow item dicts, shuffled
        and capped at BG_FOLDER_MAX, for the service driven folder mode.
        </summary>
        <param name="folder">The folder as _derive_folder returns it, ending
        in its separator, so the file name is appended straight on.</param>
        <returns>Items with the file name as the caption and no library
        fields; empty when the folder holds no picture.</returns>
        <exception cref="LookupError">The folder could not be listed, which
        the worker treats like a library that did not answer: the empty
        list stays and is retried on the short backoff.</exception>
        <remarks>
        Not recursive, matching the multiimage it stands in for. The
        listing goes through xbmcvfs so special:// and network paths work
        the same as the picker that chose them.
        </remarks>
        """
        try:
            _dirs, files = xbmcvfs.listdir(folder)
        except Exception as exc:  # noqa: BLE001
            raise LookupError("could not list {0!r}: {1}".format(folder, exc))
        items = []
        for name in files:
            if not name.lower().endswith(IMAGE_EXTS):
                continue
            items.append({
                "fanart": folder + name,
                "label": _basename_no_ext(name),
                "watched": "",
                "title": "", "year": "", "dbtype": "", "dbid": 0,
                "file": "", "thumb": "", "duration": 0,
            })
        random.shuffle(items)
        return items[:self.BG_FOLDER_MAX]

    @staticmethod
    def _watched_text(lastplayed):
        """
        <summary>
        Turn a library lastplayed stamp into the caption's "Last watched"
        text, en-GB date order.
        </summary>
        <param name="lastplayed">Kodi's "YYYY-MM-DD HH:MM:SS", or empty.</param>
        <returns>"Last watched 12/09/2026", or "" when never played or the
        stamp does not parse.</returns>
        """
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", lastplayed or "")
        if not m or m.group(1) == "0000":
            return ""
        return _L(31620) % "{0}/{1}/{2}".format(m.group(3), m.group(2), m.group(1))

    @staticmethod
    def _fanart_items(rows, kind):
        """
        <summary>
        Slideshow item dicts from JSON-RPC rows carrying art, title, year,
        lastplayed and (movies) file and runtime. Rows with no fanart are
        skipped, they would render as a blank background.
        </summary>
        <param name="rows">The movies or tvshows list from the reply.</param>
        <param name="kind">"movie" or "tvshow": picks the id field and
        becomes the item's dbtype, the value the Add To List button stores
        as list_item_dbtype. A show's year is left out of the caption.</param>
        <returns>Dicts with fanart, label, watched and the BG_ITEM_PROPS
        fields; duration is the runtime in seconds, thumb the poster.</returns>
        """
        items = []
        for row in rows:
            art = row.get("art", {}) or {}
            fanart = art.get("fanart", "")
            if not fanart:
                continue
            title = row.get("title", "") or ""
            year = (row.get("year", 0) or 0) if kind == "movie" else 0
            items.append({
                "fanart": fanart,
                "label": "{0} ({1})".format(title, year) if year else title,
                "watched": FunctionalHelper._watched_text(row.get("lastplayed")),
                "title": title,
                "year": year or "",
                "dbtype": kind,
                "dbid": row.get("movieid" if kind == "movie" else "tvshowid", 0) or 0,
                "file": row.get("file", "") or "",
                "thumb": art.get("poster") or art.get("thumb") or "",
                "duration": row.get("runtime", 0) or 0,
            })
        return items

    def _fetch_genre_library(self, genre, gtype):
        """
        <summary>
        Up to BG_COUNT random fanart entries restricted to a single genre.
        </summary>
        <param name="genre">Genre name exactly as the library holds it.</param>
        <param name="gtype">movies, tvshows or both; anything else falls back to movies.</param>
        <returns>Slideshow item dicts, shuffled.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        """
        if gtype not in ("movies", "tvshows", "both"):
            gtype = "movies"
        params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "filter": {"field": "genre", "operator": "is", "value": genre},
        }
        items = []
        if gtype in ("movies", "both"):
            items += self._fanart_items(_result_rows(_jsonrpc(
                "VideoLibrary.GetMovies",
                dict(params, properties=self.BG_MOVIE_PROPS)), "movies"), "movie")
        if gtype in ("tvshows", "both"):
            items += self._fanart_items(_result_rows(_jsonrpc(
                "VideoLibrary.GetTVShows",
                dict(params, properties=self.BG_SHOW_PROPS)), "tvshows"), "tvshow")
        # Interleave movies and shows in "both" mode.
        random.shuffle(items)
        return items[:self.BG_COUNT]

    def _fetch_random_library(self, unwatched=False):
        """
        <summary>
        Up to BG_COUNT random fanart entries from the movie + TV-show library.
        </summary>
        <param name="unwatched">Films never watched only, and no TV shows
        (BG-UNWATCHED, Skin.String(bg_unwatched)). Asked for as "only films
        I have not seen", so a show is left out rather than judged by its
        episodes.</param>
        <returns>Slideshow item dicts, shuffled so films and shows interleave.</returns>
        <exception cref="LookupError">The library did not answer, see _result_rows.</exception>
        """
        movie_params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "properties": self.BG_MOVIE_PROPS,
        }
        if unwatched:
            movie_params["filter"] = {
                "field": "playcount", "operator": "is", "value": "0"}
        items = self._fanart_items(_result_rows(
            _jsonrpc("VideoLibrary.GetMovies", movie_params), "movies"), "movie")
        if unwatched:
            random.shuffle(items)
            return items[:self.BG_COUNT]
        show_params = {
            "limits": {"start": 0, "end": self.BG_COUNT},
            "sort": {"order": "ascending", "method": "random"},
            "properties": self.BG_SHOW_PROPS,
        }
        items += self._fanart_items(_result_rows(
            _jsonrpc("VideoLibrary.GetTVShows", show_params), "tvshows"), "tvshow")
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
    Fast tickers run every loop and slow ones every SLOW_EVERY loops, each
    handler under its own guard, see _run_handlers.
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
    # Once, after the grace: a file write and one Home property.
    helper.write_dedication()

    # Polling loop for things Kodi doesn't notify on (focused item changes etc.).
    # waitForAbort returns True if Kodi is shutting down.
    # Fast-tickers (focused ETA, command channels) run every loop.
    # Slow-tickers (home background slideshow) only every Nth loop.
    SLOW_EVERY = int(1.0 / FunctionalHelper.POLL_SECS) or 1  # ~once per second
    # The handlers, as bound methods. Naming them here rather than calling
    # them inline does two things. A name that no longer exists fails right
    # here at start, loudly, instead of raising on every tick inside a guard
    # that swallowed it. And each handler gets its own guard below.
    fast = (
        # First, so the timers it resets are seen by this same tick.
        helper.apply_library_events,
        # Order matters: update_video_nav_state can ask for a sort
        # direction, and update_sort_direction must not try to honour it in
        # the same tick, that is the stale-state race its whole deferral
        # exists to avoid. Running it first means the request lands a tick
        # later, once the new sort method has settled.
        helper.update_sort_direction,
        helper.update_video_nav_state,
        helper.update_focused_eta,
        helper.update_media_age,
        helper.update_focused_age,
        helper.update_settings_command,
        helper.update_layout_command,
        helper.update_bg_command,
        helper.update_random_command,
        helper.update_age_command,
        helper.update_genre_command,
        helper.update_search_command,
        helper.update_collections_command,
        helper.update_accent,
        helper.update_startup_fallback,
        helper.update_tiles,
        helper.update_home_focus,
        helper.update_tile_command,
        helper.update_favourites,
        helper.update_continue_watching,
        helper.update_lists,
        helper.update_playing_cast,
        helper.update_info_cast,
        helper.update_cast_command,
        helper.update_cache_command,
        # Fast ticker: the countdown has to move once a second, and the
        # power menu's command must be picked up while the menu is still in
        # front of the user.
        helper.update_sleep_timer,
        # Fast as well: it only compares a timestamp unless a refresh is
        # due, and a toggled hide_nextup should refill the row at once.
        helper.update_next_up,
        # COMING-UP-SCROLL: a catch has to be answered while the key is fresh.
        helper.coming_up_scroll_tick,
    )
    slow = (
        helper.update_queue_eta,
        helper.update_settings_backup,
        helper.update_buffer_stats,
        helper.update_bg_schedule,
        helper.update_home_bg,
        # Once a second is plenty: the date, a reload of the skin colours
        # held back until nothing is playing, and the crow's next move.
        helper.update_theme,
        helper.maybe_refresh_stats,
        # Once a second: Engage rewrites its rows on its own schedule.
        helper.update_coming_up_lines,
        helper.normalize_clearance,
        # Once a second: follows the "Let JellyStat manage the lists" switch.
        helper.update_lists_api,
    )
    failures = {}
    tick = 0
    while not helper.abortRequested():
        _run_handlers(fast, failures)
        if tick == 0:
            _run_handlers(slow, failures)
        tick = (tick + 1) % SLOW_EVERY
        if helper.waitForAbort(FunctionalHelper.POLL_SECS):
            break
    # The discovery property goes first inside stop(), so JellyStat stops
    # sending before the socket closes.
    lists_api.stop()
    _dlog("service shutting down")


# A handler that keeps failing is logged on its first failure and then once
# in this many, about once a minute for a fast handler.
HANDLER_LOG_EVERY = 240


def _run_handlers(handlers, failures):
    """
    <summary>
    Call each handler in turn, each under its own guard.
    </summary>
    <param name="handlers">Bound methods taking no arguments, in call order.</param>
    <param name="failures">Dict of handler name to consecutive failure count, kept by the caller across ticks.</param>
    <remarks>
    One bad handler must never kill the service, and must not take the
    others down with it either. The whole tick used to sit under a single
    guard, so a handler that raised every time skipped everything after it
    on every tick: the sleep timer, second from last, would never have
    fired, and the slow block (backup, schedule, background, stats) never
    ran. It also wrote a full traceback four times a second. Failures are
    now counted per handler and logged on the first and then every
    HANDLER_LOG_EVERY, and the count is cleared by a clean run.
    </remarks>
    """
    for handler in handlers:
        name = handler.__name__
        try:
            handler()
        except Exception:  # noqa: BLE001
            count = failures.get(name, 0) + 1
            failures[name] = count
            if count == 1 or count % HANDLER_LOG_EVERY == 0:
                _dlog("{0} failed, {1} time(s) running (continuing):\n{2}".format(
                    name, count, traceback.format_exc()), xbmc.LOGERROR)
        else:
            if name in failures:
                del failures[name]


if __name__ == "__main__":
    run()
