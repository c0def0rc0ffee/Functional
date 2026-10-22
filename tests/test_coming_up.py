#!/usr/bin/env python3
"""
<summary>
Tests for service.coming_up_lines, the layout of the Coming up list on Home.
</summary>
<remarks>
No Kodi is needed: the Kodi stubs are the ones tests/test_lists_api.py installs
at import. A day with one slot must keep the two line row, a day with several
must get a heading and a line per slot, and every day must start on an odd
line so the row based cut rules in Home.xml never split one. Exits non zero
when a check fails.

Usage:
    python3 tests/test_coming_up.py
</remarks>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service
FAILURES = []


def equal(got, want, what):
    """
    <summary>Record a failure when got is not want.</summary>
    <param name="got">The value produced.</param>
    <param name="want">The value expected.</param>
    <param name="what">What is being checked, for the report.</param>
    """
    if got != want:
        FAILURES.append("{}: got {!r}, want {!r}".format(what, got, want))


def kinds(lines):
    """
    <summary>The kinds of the non empty lines, in order.</summary>
    <param name="lines">What coming_up_lines returned.</param>
    <returns>A list of kind strings.</returns>
    """
    return [line["kind"] for line in lines if line["kind"]]


def test_one_slot_per_day():
    """
    <summary>One slot a day keeps the original two line row, a day rule between days.</summary>
    """
    lines = service.coming_up_lines([("Voyager", "Tonight 19:00"),
                                     ("Dune", "Tomorrow 20:00")])
    equal(len(lines), service.COMING_UP_LINES, "always every line")
    equal(kinds(lines), ["item", "item2", "item", "item2"], "two items")
    equal((lines[0]["label"], lines[0]["when"], lines[0]["sep"]),
          ("Voyager", "Tonight 19:00", ""), "the first item keeps its whole when, no rule")
    equal((lines[2]["label"], lines[2]["when"], lines[2]["sep"]),
          ("Dune", "Tomorrow 20:00", "day"), "the second day gets the rule")


def test_several_slots_in_a_day():
    """
    <summary>A day with several slots gets a heading and one line per slot with only the time.</summary>
    """
    lines = service.coming_up_lines([("Voyager", "Tonight 19:00"),
                                     ("Dune", "Tonight 21:30"),
                                     ("Alien", "Tomorrow 20:00")])
    equal(kinds(lines), ["heading", "slot", "slot", "pad", "item", "item2"],
          "heading, slots, pad to an even length, then the single item")
    equal((lines[0]["label"], lines[0]["sep"]), ("Tonight", ""), "the heading is the day")
    equal((lines[1]["label"], lines[1]["when"]), ("Voyager", "19:00"), "a slot line shows the time only")
    equal((lines[2]["label"], lines[2]["when"]), ("Dune", "21:30"), "the second slot")
    equal((lines[4]["label"], lines[4]["when"], lines[4]["sep"]),
          ("Alien", "Tomorrow 20:00", "day"), "the next day starts on an odd line with the rule")


def test_dated_day_and_even_group():
    """
    <summary>A dated day groups on the whole day text, and an even sized group needs no pad.</summary>
    """
    lines = service.coming_up_lines([("A", "Wednesday 28/10/2026 19:30"),
                                     ("B", "Wednesday 28/10/2026 21:00"),
                                     ("C", "Wednesday 28/10/2026 22:00"),
                                     ("D", "Thursday 29/10/2026 19:00")])
    equal(kinds(lines), ["heading", "slot", "slot", "slot", "item", "item2"], "no pad after four lines")
    equal(lines[0]["label"], "Wednesday 28/10/2026", "the heading keeps the date")
    equal(lines[3]["when"], "22:00", "the time is the last word")


def test_every_day_starts_on_an_odd_line():
    """
    <summary>However the days fall, each day starts on an odd line, so it starts a row.</summary>
    """
    days = ["Tonight", "Tomorrow", "Friday", "Saturday", "Sunday"]
    slots = []
    for count, day in zip([3, 1, 2, 4, 1], days):
        slots += [("S{}{}".format(day, i), "{} 1{}:00".format(day, i)) for i in range(count)]
    lines = service.coming_up_lines(slots[:service.COMING_UP_SLOTS])
    for number, line in enumerate(lines, 1):
        if line["kind"] in ("item", "heading"):
            equal(number % 2, 1, "line {} ({}) starts a row".format(number, line["kind"]))


def test_overflow_and_empty():
    """
    <summary>More than fits is cut to the line count, and no slots gives empty lines.</summary>
    """
    slots = [("S{}".format(i), "Day{} 19:00".format(i)) for i in range(11)]
    lines = service.coming_up_lines(slots)
    equal(len(lines), service.COMING_UP_LINES, "eleven single days fill exactly 22 lines")
    equal(lines[-1]["kind"], "item2", "the last line is the second half of the last item")
    equal(kinds(service.coming_up_lines([])), [], "nothing published, nothing drawn")


def test_shared_days_use_the_spare_lines():
    """
    <summary>COMING-UP-MORE: days that share a heading fit more than eleven slots in the 22 lines.</summary>
    """
    slots = []
    for count, day in zip([6, 6, 5], ["Tonight", "Tomorrow", "Friday"]):
        slots += [("S{}{}".format(day, i), "{} 1{}:00".format(day, i)) for i in range(count)]
    equal(len(slots[:service.COMING_UP_SLOTS]), 17, "all seventeen slots are read")
    lines = service.coming_up_lines(slots[:service.COMING_UP_SLOTS])
    equal(sum(1 for line in lines if line["kind"] == "slot"), 17, "seventeen slots fill the 22 lines")


def test_estimate_chains_queued_slots():
    """
    <summary>COMING-UP-ESTIMATE: a slot set to start while the one before still runs starts when it ends.</summary>
    """
    dt = service.datetime.datetime
    now = dt(2026, 10, 22, 17, 0)
    got = service.estimate_coming_up([
        ("Voyager", "Tonight 18:00", "2026-10-22T18:00", "2640"),
        ("Dune", "Tonight 18:05", "2026-10-22T18:05", "9300"),
        ("Late", "Tonight 23:30", "2026-10-22T23:30", ""),
    ], now)
    equal(got, [("Voyager", "Tonight 18:00"), ("Dune", "Tonight 18:44"), ("Late", "Tonight 23:30")],
          "Dune waits for Voyager's 44 minutes; Late is clear of Dune's end at 21:19")


def test_estimate_playing_and_unknowns():
    """
    <summary>The chain starts at what is playing, rounds up, crosses midnight, and holds after an unknown.</summary>
    """
    dt = service.datetime.datetime
    now = dt(2026, 10, 22, 23, 0)
    got = service.estimate_coming_up([
        ("Film", "Tonight 23:10", "2026-10-22T23:10", "5400"),
        ("Random", "Tonight 23:15", "2026-10-22T23:15", ""),
        ("Next", "Tonight 23:20", "2026-10-22T23:20", "1800"),
        ("Old Engage", "Tomorrow 01:00", "", ""),
    ], now, playing_ends=dt(2026, 10, 22, 23, 40, 20))
    equal(got[0], ("Film", "Tonight 23:41"), "starts when playback ends, rounded up to the minute")
    equal(got[1], ("Random", "Tomorrow 01:11"), "past midnight the day word changes")
    equal(got[2], ("Next", "Tomorrow 01:11"), "after an unknown runtime, no earlier than that slot's start")
    equal(got[3], ("Old Engage", "Tomorrow 01:00"), "no Due from an older Engage, the set time")
    equal(service.estimate_coming_up([("A", "Tonight 18:00", "2026-10-22T18:00", "600")], now,
                                     playing_ends=dt(2026, 10, 22, 17, 30)),
          [("A", "Tonight 18:00")], "playback ending before the set time changes nothing")


def test_coming_up_when():
    """
    <summary>The estimate's words match Engage's when_label.</summary>
    """
    dt = service.datetime.datetime
    now = dt(2026, 10, 22, 12, 0)  # a Thursday
    equal(service.coming_up_when(dt(2026, 10, 21, 23, 50), now), "Yesterday 23:50", "yesterday")
    equal(service.coming_up_when(dt(2026, 10, 24, 9, 5), now), "Saturday 09:05", "within the week")
    equal(service.coming_up_when(dt(2026, 10, 29, 19, 0), now), "Thursday 29/10/2026 19:00",
          "a week ahead is dated")


def test_run_ends():
    """
    <summary>COMING-UP-ENDS: a run ends where the next slot is clear of it, and only a switched on last slot gets a line.</summary>
    """
    dt = service.datetime.datetime
    now = dt(2026, 10, 22, 17, 0)
    slots = [
        ("Voyager", "Tonight 18:00", "2026-10-22T18:00", "2640", "1"),
        ("Dune", "Tonight 18:05", "2026-10-22T18:05", "9300", "1"),
        ("Late", "Tonight 23:30", "2026-10-22T23:30", "1800", ""),
        ("Morning", "Tomorrow 07:00", "2026-10-23T07:00", "1800", "1"),
    ]
    ends = service.coming_up_run_ends(slots, now)
    equal(sorted(ends), [1, 3], "Voyager and Dune are one run ending with Dune; Late's switch is off")
    equal(ends[1], dt(2026, 10, 22, 21, 19), "the run ends when Dune does")
    equal(ends[3], dt(2026, 10, 23, 7, 30), "a slot on its own is a run of one")
    unknown = service.coming_up_run_ends([
        ("A", "Tonight 18:00", "2026-10-22T18:00", "", "1"),
        ("B", "Tonight 18:05", "2026-10-22T18:05", "600", "1"),
    ], now)
    equal(sorted(unknown), [1], "no line for an unknown end, and the slot after starts its own run")
    playing = service.coming_up_run_ends([("A", "Tonight 17:10", "2026-10-22T17:10", "600", "1")], now,
                                         playing_ends=dt(2026, 10, 22, 17, 30))
    equal(playing, {0: dt(2026, 10, 22, 17, 40)}, "queued behind what is playing")


def test_ends_lines():
    """
    <summary>An Ends At line stays in its run's day, in a two line item day and in a heading day.</summary>
    """
    lines = service.coming_up_lines([("Dune", "Tonight 21:30"), ("Ends At", "23:46", "ends"),
                                     ("Voyager", "Tomorrow 18:00"), ("Dune", "Tomorrow 18:05"),
                                     ("Ends At", "21:19", "ends")])
    equal(kinds(lines), ["item", "item2", "ends", "pad", "heading", "slot", "slot", "ends"],
          "a one slot day keeps its item, then the line, padded to whole rows")
    equal((lines[2]["label"], lines[2]["when"]), ("Ends At", "23:46"), "the line carries its time")
    equal(lines[4]["sep"], "day", "the next day still gets its rule")


def test_scroll_window():
    """
    <summary>COMING-UP-SCROLL: the window moves in whole rows, stops at the end, and drops the top rule.</summary>
    """
    days = ["Tonight", "Tomorrow", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday"]
    slots = []
    for day in days:
        slots += [("A " + day, day + " 18:00"), ("B " + day, day + " 20:00")]
    every = service.coming_up_lines(slots, every=True)
    equal(len(every), 28, "seven days of two slots: a heading, two slots and a pad each")
    equal(len(service.coming_up_lines(slots)), service.COMING_UP_LINES, "unscrolled, the usual 22 lines")
    window, offset = service.coming_up_window(every, 0)
    equal((offset, window[0]["label"]), (0, "Tonight"), "the top")
    window, offset = service.coming_up_window(every, 5)
    equal(offset, 4, "an odd offset rounds down to a whole row")
    equal((window[0]["label"], window[0]["sep"]), ("Tomorrow", ""), "the first line shown keeps no rule")
    window, offset = service.coming_up_window(every, 99)
    equal(offset, 26, "never past the last row")
    equal(len(window), service.COMING_UP_LINES, "always every line")
    equal(service.coming_up_stops(every, 6), [0, 4, 8, 12, 16, 20, 24],
          "a day at a time when each day fits")
    long_day = service.coming_up_lines([("S{}".format(i), "Tonight 1{}:00".format(i)) for i in range(7)]
                                       + [("X", "Tomorrow 18:00")], every=True)
    equal(service.coming_up_stops(long_day, 4), [0, 2, 4, 6, 8],
          "a day longer than the room is walked a row at a time, then the next day")


if __name__ == "__main__":
    for test in (test_one_slot_per_day, test_several_slots_in_a_day,
                 test_dated_day_and_even_group, test_every_day_starts_on_an_odd_line,
                 test_overflow_and_empty, test_shared_days_use_the_spare_lines,
                 test_estimate_chains_queued_slots, test_estimate_playing_and_unknowns,
                 test_coming_up_when, test_run_ends, test_ends_lines,
                 test_scroll_window):
        print("running " + test.__name__)
        test()
    if FAILURES:
        print("\n".join(FAILURES))
        sys.exit(1)
    print("test_coming_up: all checks passed")
