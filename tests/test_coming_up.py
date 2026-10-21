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


if __name__ == "__main__":
    for test in (test_one_slot_per_day, test_several_slots_in_a_day,
                 test_dated_day_and_even_group, test_every_day_starts_on_an_odd_line,
                 test_overflow_and_empty, test_shared_days_use_the_spare_lines):
        print("running " + test.__name__)
        test()
    if FAILURES:
        print("\n".join(FAILURES))
        sys.exit(1)
    print("test_coming_up: all checks passed")
