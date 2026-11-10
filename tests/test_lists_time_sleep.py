#!/usr/bin/env python3
"""
<summary>
Tests for LISTS-TIME-SLEEP (07/11/2026): with Offer to Power Down After Port
by Time on, Port by Time asks whether to power the box down when the queue
finishes, and a yes arms the sleep timer's queue mode.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs come from tests/test_lists_api.py, the same
ones the other list tests use, with a pretend playlist (Player) answering
Playlist.Position and Playlist.Length as Kodi 21 did live. The service half
drives a real FunctionalHelper: the question is asked only with the switch
on and only when the queue went in, and No calls off a queue armed earlier;
the queue mode powers down only after the queue's last item ends by itself
and the ten second warning passes with no key pressed and nothing playing;
an end between items never starts it; a key, the last item stopped by hand,
something else played or the playlist replaced call it off; the readout is
put back after a skin reload; an end after a cancel leaves nothing pending;
and the clock and episode modes replace it. The XML half reads the settings
row, its help and preview entries, its focus order and its place on the
Lists page, and proves nothing but the row's own toggle writes the switch.
Whether Kodi really leaves the player empty after the last item of a
queue is the live check's job. Exits non zero when a check fails.

Usage:
    python3 tests/test_lists_time_sleep.py
</remarks>
"""

import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service
check = T.check

GATE = "lists_time_sleep"
ROW = "7239"
XML = os.path.join(T.SKIN, "xml")
STRINGS = os.path.join(T.SKIN, "language", "resource.language.en_gb", "strings.po")

# Builtins the service ran, newest last.
BUILTINS = []
T.xbmc.executebuiltin = lambda cmd, *a, **k: BUILTINS.append(cmd)


def read(name):
    """
    <summary>Reads one skin XML file as text.</summary>
    <param name="name">The file name under xml/.</param>
    <returns>The text.</returns>
    """
    with open(os.path.join(XML, name), encoding="utf-8") as handle:
        return handle.read()


def fresh():
    """
    <summary>A helper with one list selected and an idle sleep timer.</summary>
    <returns>A FunctionalHelper.</returns>
    """
    item = {"label": "A Song", "file": "/music/a.flac", "dbtype": "", "kind": "music",
            "duration": 3 * 3600}
    helper = T.seed([{"name": "Evening", "items": [item], "seq": 1}])
    helper._lists_sel = 1
    T.PROPS.pop("sleep_remaining", None)
    BUILTINS.clear()
    T._Dialog.toasts.clear()
    return helper


def port_time(helper, queued, answer):
    """
    <summary>Runs Port by Time with the dialogs and the queue faked.</summary>
    <param name="helper">The helper from fresh().</param>
    <param name="queued">What _lists_queue reports: True when the items went in.</param>
    <param name="answer">The yes or no the power down question gets.</param>
    <returns>How many times the power down question was asked.</returns>
    """
    asked = []
    T._Dialog.numeric = lambda self, *a, **k: "03:00"
    T._Dialog.yesno = lambda self, *a, **k: asked.append(a) or answer
    helper._lists_verify = lambda items: None
    helper._lists_queue = lambda *a, **k: queued
    try:
        helper._lists_port_time()
    finally:
        del T._Dialog.numeric
        T._Dialog.yesno = lambda self, *a, **k: False
    return len(asked)


def test_question():
    """
    <summary>The question is asked only with the switch on and the queue
    filled, and only a yes arms the queue mode.</summary>
    """
    print("running test_question")
    T.SKIN_SETTINGS.discard(GATE)
    helper = fresh()
    check(port_time(helper, True, True) == 0, "with the switch off Port by Time asks nothing")
    check(not helper._sleep_queue, "and arms nothing")
    T.SKIN_SETTINGS.add(GATE)
    player = Player(2)
    player.play(1)
    try:
        helper = fresh()
        check(port_time(helper, False, True) == 0, "a cancelled queue is not followed by the question")
        check(not helper._sleep_queue, "and arms nothing")
        helper = fresh()
        check(port_time(helper, True, False) == 1, "with the switch on the question is asked once")
        check(not helper._sleep_queue and not T.PROPS.get("sleep_remaining"), "no leaves the timer idle")
        helper = fresh()
        check(port_time(helper, True, True) == 1, "the question is asked again on the next port")
        check(helper._sleep_queue, "yes arms the queue mode")
        check(T.PROPS.get("sleep_remaining") == T.STRINGS[31836], "and the countdown reads Queue")
        check(any(T.STRINGS[31835] in t for t in T._Dialog.toasts), "and a toast says so")
    finally:
        T.SKIN_SETTINGS.discard(GATE)
        player.close()


class Player:
    """
    <summary>A pretend video player and playlist, as the queue mode reads them.</summary>
    <remarks>Answers Playlist.Position(video) and Playlist.Length(video) the
    way Kodi 21 did live (07/11/2026): the position counts from 1 and is
    blank while nothing plays. Player.HasMedia, System.IdleTime(1) and the
    repeat conditions go through the CONDS set the stubs already read; the
    box starts idle.</remarks>
    """

    def __init__(self, length):
        """
        <summary>A queue of length items, nothing playing yet, nobody at the box.</summary>
        <param name="length">Items in the video playlist.</param>
        """
        self.length = length
        self.pos = 0
        self.real = T.xbmc.getInfoLabel
        T.xbmc.getInfoLabel = self.label
        T.CONDS.add(IDLE)

    def label(self, name):
        """
        <summary>getInfoLabel over the pretend playlist.</summary>
        <param name="name">The infolabel asked for.</param>
        <returns>Its text.</returns>
        """
        if name == "Playlist.Position(video)":
            return str(self.pos) if self.pos else ""
        if name == "Playlist.Length(video)":
            return str(self.length)
        return self.real(name)

    def play(self, pos, length=None):
        """
        <summary>Item pos of the playlist plays.</summary>
        <param name="pos">Position, from 1; 0 for something outside the playlist.</param>
        <param name="length">A new length when the playlist is replaced.</param>
        """
        self.pos = pos
        if length is not None:
            self.length = length
        T.CONDS.add("Player.HasMedia")

    def empty(self):
        """<summary>Nothing plays.</summary>"""
        self.pos = 0
        T.CONDS.discard("Player.HasMedia")

    def close(self):
        """<summary>Puts the stubs back.</summary>"""
        T.xbmc.getInfoLabel = self.real
        for cond in ("Player.HasMedia", IDLE, REPEAT):
            T.CONDS.discard(cond)


IDLE = "System.IdleTime(1)"
REPEAT = "Playlist.IsRepeat | Playlist.IsRepeatOne"


def end(helper, natural):
    """
    <summary>Kodi's Player.OnStop, as the notification thread delivers it.</summary>
    <param name="helper">The helper.</param>
    <param name="natural">Kodi's "end" flag: True when playback reached the end.</param>
    """
    helper.onNotification("xbmc", "Player.OnStop", json.dumps({"end": natural}))


def armed_on(length):
    """
    <summary>A helper with the queue mode armed over a queue, the first item
    playing and seen by one tick.</summary>
    <param name="length">Items in the queue.</param>
    <returns>(helper, Player).</returns>
    """
    helper = fresh()
    player = Player(length)
    player.play(1)
    helper._sleep_arm_queue()
    helper.update_sleep_timer()
    return helper, player


def last_ends(helper, player):
    """
    <summary>The queue's last item plays, is seen, and ends by itself; one tick
    of the warning follows.</summary>
    <param name="helper">The helper.</param>
    <param name="player">The Player.</param>
    """
    player.play(player.length)
    helper.update_sleep_timer()
    end(helper, True)
    player.empty()
    helper.update_sleep_timer()


def test_queue_mode():
    """
    <summary>The queue mode powers down only after the queue's last item ends
    by itself and the ten second warning runs out with no key, no new start
    and nothing playing; an end between items never starts it, however long
    the next item takes; the player still showing for a moment after the end
    does not cancel the warning.</summary>
    """
    print("running test_queue_mode")
    helper, player = armed_on(3)
    try:
        check(helper._sleep_queue_len == 3, "the queue is known by its length")
        end(helper, True)
        player.empty()
        for _ in range(3):
            helper.update_sleep_timer()
        check(helper._sleep_queue_check is None and "Powerdown" not in BUILTINS,
              "an end between items starts nothing, however long the next item takes")
        player.play(2)
        helper.update_sleep_timer()
        end(helper, False)
        player.empty()
        helper.update_sleep_timer()
        check(helper._sleep_queue, "a stop by hand between items leaves the timer armed")
        player.play(3)
        helper.update_sleep_timer()
        check(helper._sleep_queue_on_last, "the last item is seen as the last")
        T._Dialog.toasts.clear()
        end(helper, True)
        check(helper._sleep_queue_check is not None, "the last item ending starts the warning")
        helper.update_sleep_timer()
        check(helper._sleep_queue and helper._sleep_queue_check is not None,
              "the player still showing for a tick after the end does not cancel the warning")
        player.empty()
        helper.update_sleep_timer()
        check(any(T.STRINGS[31837] in t for t in T._Dialog.toasts), "the warning is a toast")
        warn = [t for t in T._Dialog.toasts if T.STRINGS[31837] in t]
        check(bool(warn) and warn[-1][3] == 10000, "which stays up for the ten seconds")
        check("Powerdown" not in BUILTINS, "nothing happens while the warning runs")
        helper._sleep_queue_check = 0
        helper.update_sleep_timer()
        check(BUILTINS.count("Powerdown") == 1, "an undisturbed warning running out powers down")
        check(not helper._sleep_queue and not T.PROPS.get("sleep_remaining"), "and the timer is disarmed first")
    finally:
        player.close()

    helper, player = armed_on(1)
    try:
        end(helper, True)
        player.empty()
        helper.update_sleep_timer()
        helper._sleep_queue_check = 0
        helper.update_sleep_timer()
        check(BUILTINS.count("Powerdown") == 1, "a queue of one film powers down after it")
    finally:
        player.close()


def test_queue_mode_stands_down():
    """
    <summary>Each way the queue mode is called off without powering down: a key
    in the first tick of the warning or at its end, a start Kodi announces
    during the warning (a film picked from the library, even one making a
    playlist of the same length), something still playing at its end, the
    last item stopped by hand, something else played or the playlist
    replaced before the end; and repeat, which starts no warning.</summary>
    """
    print("running test_queue_mode_stands_down")
    for case in ("key_early", "key_late", "new_start", "same_length", "still_playing",
                 "stop_last", "other", "replaced", "repeat"):
        helper, player = armed_on(2)
        try:
            if case == "key_early":
                player.play(2)
                helper.update_sleep_timer()
                end(helper, True)
                player.empty()
                T.CONDS.discard(IDLE)
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "a key in the first moment of the warning calls it off")
            elif case == "key_late":
                last_ends(helper, player)
                helper._sleep_queue_check = 0
                T.CONDS.discard(IDLE)
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "a key at the end of the warning calls it off")
            elif case in ("new_start", "same_length"):
                last_ends(helper, player)
                helper.onNotification("xbmc", "Player.OnPlay", "{}")
                player.play(1, length=2 if case == "same_length" else 1)
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "%s: a start during the warning calls it off" % case)
            elif case == "still_playing":
                last_ends(helper, player)
                player.play(0)
                helper._sleep_queue_check = 0
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "something playing at the end of the warning calls it off")
            elif case == "stop_last":
                player.play(2)
                helper.update_sleep_timer()
                end(helper, False)
                player.empty()
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "stopping the last item by hand calls it off")
            elif case == "other":
                player.play(0)
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "something playing outside the playlist calls it off")
            elif case == "replaced":
                player.play(1, length=1)
                helper.update_sleep_timer()
                check(not helper._sleep_queue, "a film played over the queue (a playlist of one) calls it off")
            elif case == "repeat":
                T.CONDS.add(REPEAT)
                last_ends(helper, player)
                check(helper._sleep_queue and helper._sleep_queue_check is None,
                      "under repeat the last item's end starts no warning")
            check("Powerdown" not in BUILTINS, "%s: never powers down" % case)
        finally:
            player.close()


def test_queue_mode_arming():
    """
    <summary>Arming needs an item of a video queue playing: nothing playing, a
    queue already finished or music refuses with a toast; the question is not
    asked when the video playlist got nothing; the "Queue" readout is put
    back after a skin reload; No to a later Port by Time calls an armed queue
    off but leaves the clock and an episode count alone; an end after a
    cancel leaves nothing pending.</summary>
    <remarks>The lock itself, against a Cancel on another thread landing
    inside the stop handler, is not proved here: these tests run on one
    thread.</remarks>
    """
    print("running test_queue_mode_arming")
    helper = fresh()
    player = Player(3)
    try:
        T._Dialog.toasts.clear()
        helper._sleep_arm_queue()
        check(not helper._sleep_queue, "nothing playing: arming is refused")
        check(any(T.STRINGS[31838] in t for t in T._Dialog.toasts), "with a toast saying why")
        player.play(0)
        helper._sleep_arm_queue()
        check(not helper._sleep_queue, "music or anything outside the video playlist: refused")
        player.play(1)
        helper._sleep_arm_queue()
        helper.update_sleep_timer()
        check(helper._sleep_queue and helper._sleep_queue_len == 3, "an item of the queue playing: armed")
        T.PROPS["sleep_remaining"] = ""
        helper.update_sleep_timer()
        check(T.PROPS.get("sleep_remaining") == T.STRINGS[31836], "a dropped readout is put back")
    finally:
        player.close()
    # LISTS-TIME-SLEEP-WAIT: a yes before the first item has started waits for it.
    helper = fresh()
    player = Player(9)
    waits = []

    def first_item_starts(timeout=None):
        """<summary>The queue's first item starts on the fourth look.</summary>
        <param name="timeout">Ignored.</param>
        <returns>False, never aborting.</returns>"""
        waits.append(timeout)
        if len(waits) == 4:
            player.play(1)
        return False

    helper.waitForAbort = first_item_starts
    try:
        helper._sleep_arm_queue()
        check(helper._sleep_queue and helper._sleep_queue_len == 9,
              "a queue that starts during the wait is armed")
        check(len(waits) == 4, "it stops looking once the queue plays")
        check(not any(T.STRINGS[31838] in t for t in T._Dialog.toasts), "and nothing says it was refused")
    finally:
        player.close()
    helper = fresh()
    player = Player(9)
    waits.clear()
    helper.waitForAbort = lambda timeout=None: waits.append(timeout) or False
    try:
        helper._sleep_arm_queue()
        check(not helper._sleep_queue, "a queue that never starts is still refused")
        check(len(waits) == int(helper.SLEEP_QUEUE_START_SECS / helper.SLEEP_QUEUE_START_STEP),
              "after the whole wait, not before")
    finally:
        player.close()
    T.SKIN_SETTINGS.add(GATE)
    player = Player(0)
    try:
        helper = fresh()
        check(port_time(helper, True, True) == 0, "no video in the playlist: the question is not asked")
        player.play(1, length=2)
        check(port_time(helper, True, True) == 1, "videos in the playlist: it is")
        check(helper._sleep_queue, "and yes arms the queue mode")
        port_time(helper, True, False)
        check(not helper._sleep_queue, "no to a later Port by Time calls the earlier queue off")
        helper._sleep_arm_episodes(2)
        port_time(helper, True, False)
        check(helper._sleep_episodes == 2, "but leaves an episode count alone")
        T._Dialog.numeric = lambda self, *a, **k: "01:00"
        try:
            helper._sleep_pick()
        finally:
            del T._Dialog.numeric
        port_time(helper, True, False)
        check(helper._sleep_deadline is not None, "and the clock")
    finally:
        T.SKIN_SETTINGS.discard(GATE)
        player.close()
    helper = fresh()
    helper._sleep_arm_episodes(1)
    helper._sleep_disarm()
    end(helper, True)
    check(not helper._sleep_fire_pending, "an end after a cancel leaves no power down pending")


def test_modes_replace_each_other():
    """
    <summary>Arming the clock or an episode count drops the queue mode, and
    cancelling clears it with a toast.</summary>
    """
    print("running test_modes_replace_each_other")
    player = Player(2)
    player.play(1)
    try:
        helper = fresh()
        helper._sleep_arm_queue()
        T._Dialog.numeric = lambda self, *a, **k: "01:00"
        try:
            helper._sleep_pick()
        finally:
            del T._Dialog.numeric
        check(not helper._sleep_queue and helper._sleep_deadline is not None, "the clock replaces the queue mode")
        helper._sleep_arm_queue()
        check(helper._sleep_deadline is None, "the queue mode replaces the clock")
        helper._sleep_arm_episodes(2)
        check(not helper._sleep_queue and helper._sleep_episodes == 2, "an episode count replaces the queue mode")
        helper._sleep_arm_queue()
        T._Dialog.toasts.clear()
        helper._sleep_disarm(announce=True)
        check(not helper._sleep_queue and not T.PROPS.get("sleep_remaining"), "cancel clears the queue mode")
        check(any(T.STRINGS[31428] in t for t in T._Dialog.toasts), "and says the timer was cancelled")
    finally:
        player.close()


def test_off_by_default():
    """
    <summary>Nothing in the skin writes the switch but its row's toggle, and
    the Python only reads it.</summary>
    """
    print("running test_off_by_default")
    writers = []
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml"):
            for number, line in enumerate(read(name).splitlines(), start=1):
                if re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s[,)]" % GATE, line):
                    writers.append((name, number, line.strip()))
    check(len(writers) == 1 and writers[0][0] == "SkinSettings.xml" and "ToggleSetting" in writers[0][2],
          "the only writer of %s is the toggle in SkinSettings.xml, found %s" % (GATE, writers))
    with open(os.path.join(T.SKIN, "service.py"), encoding="utf-8") as handle:
        uses = re.findall(r".*%s.*" % GATE, handle.read())
    check(uses and all("Skin.HasSetting(%s)" % GATE in u or u.strip().startswith(("#", "Skin.HasSetting"))
                       or "<" not in u and "Skin.HasSetting" in u for u in uses),
          "service.py only reads %s through Skin.HasSetting" % GATE)


def test_row():
    """
    <summary>Row 7239: label, toggle, help with a Where line, no preview,
    focus to and from the rows above and below, and the Lists page still
    clear of overlaps with the rows moved down under it.</summary>
    """
    print("running test_row")
    tree = ET.fromstring(read("SkinSettings.xml"))
    page = next(g for g in tree.iter("control") if g.get("id") == "9006")
    rows = {n.get("id"): n for n in page.iter("control") if n.get("id")}
    row = rows.get(ROW)
    if row is None:
        check(False, "row %s is missing from the Lists page" % ROW)
        return
    check(row.findtext("label") == "31832", "the row's label is 31832")
    check(row.findtext("selected") == "Skin.HasSetting(%s)" % GATE
          and row.findtext("onclick") == "Skin.ToggleSetting(%s)" % GATE, "the row shows and toggles its switch")
    with open(STRINGS, encoding="utf-8") as handle:
        strings = handle.read()
    help_text = read("Includes_SettingsHelp.xml")
    shown = re.search(r'name="settings_help_shown">(.*)</expression>', help_text)
    check(shown and "Control.HasFocus(%s)" % ROW in shown.group(1), "settings_help_shown lists the row")
    entry = re.search(r'Control\.HasFocus\(%s\)">\$LOCALIZE\[(\d+)\]' % ROW, help_text)
    line = entry and re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
    check(bool(line) and "[CR]Where: " in line.group(1), "the row has help with a Where line")
    none = re.search(r'name="settings_preview_none">(.*)</expression>',
                     read("Includes_SettingsPreview.xml"))
    check(none and "Control.HasFocus(%s)" % ROW in none.group(1), "the row is in settings_preview_none")
    check(rows["7238"].findtext("ondown") == ROW and row.findtext("onup") == "7238", "up and down reach 7238")
    check(row.findtext("ondown") == "7236" and rows["7236"].findtext("onup") == ROW
          and rows["7237"].findtext("onup") == ROW, "down reaches Export, and Export and Import lead back")
    check(row.findtext("onleft") == "7000", "left goes to the page menu")
    # Images are left out: the page heading's accent stripe is drawn into
    # the foot of the heading on purpose, as on every Skin Settings page.
    boxes = []
    for n in page:
        if n.tag == "control" and n.get("type") != "image" and n.findtext("top") and n.findtext("height"):
            left, top = int(n.findtext("left") or 0), int(n.findtext("top"))
            boxes.append((left, top, left + int(n.findtext("width") or 0), top + int(n.findtext("height")),
                          n.get("id") or n.findtext("label")))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                check(False, "%s and %s overlap on the Lists page" % (a[4], b[4]))
    check(max(b[3] for b in boxes) <= 1040, "the Lists page still ends above the foot of the screen")


def main():
    """<summary>Run every test, clean up, and exit non zero on any failure.</summary>"""
    try:
        for test in (test_question, test_queue_mode, test_queue_mode_stands_down,
                     test_queue_mode_arming, test_modes_replace_each_other,
                     test_off_by_default, test_row):
            test()
    finally:
        T.lists_api.stop()
        shutil.rmtree(T.PROFILE, ignore_errors=True)
    if T.FAILURES:
        print("test_lists_time_sleep: %d check(s) failed" % len(T.FAILURES))
        sys.exit(1)
    print("test_lists_time_sleep: all checks passed")


if __name__ == "__main__":
    main()
