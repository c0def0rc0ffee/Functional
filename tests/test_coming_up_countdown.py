#!/usr/bin/env python3
"""
<summary>
Spec tests for service.coming_up_next_line, which names the Coming up line
holding the next slot so the countdown can be drawn on it.
</summary>
<remarks>
Written from the brief. The Kodi stubs are the ones tests/test_lists_api.py
installs at import. A day with one slot is an item on line 1; a day with
several is a heading line then slot lines. Exits non zero when a check fails.

Usage:
    python3 tests/test_coming_up_countdown.py
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
    <summary>Record a failure when got differs from want.</summary>
    <param name="got">The value produced.</param>
    <param name="want">The value expected.</param>
    <param name="what">The requirement being checked.</param>
    """
    if got != want:
        FAILURES.append('{}: got {!r}, want {!r}'.format(what, got, want))
        print('FAIL: {}'.format(FAILURES[-1]))


def test_single_slot_day_is_line_one():
    """<summary>A first day with one slot is an item, so the next slot is line 1, as a string.</summary>"""
    lines = service.coming_up_lines([('Film', 'Tonight 19:00'), ('Show', 'Tomorrow 20:00')], every=True)
    equal(lines[0]['kind'], 'item', 'the first day is drawn as an item')
    equal(service.coming_up_next_line(lines, 0), '1', 'line 1')
    equal(isinstance(service.coming_up_next_line(lines, 0), str), True, 'a string')


def test_only_one_slot():
    """<summary>A list of just one slot gives line 1.</summary>"""
    lines = service.coming_up_lines([('Film', 'Tonight 19:00')], every=True)
    equal(service.coming_up_next_line(lines, 0), '1', 'one slot in all')


def test_several_slot_day_is_line_two():
    """<summary>Under a heading the first slot is line 2.</summary>"""
    lines = service.coming_up_lines([('A', 'Tonight 19:00'), ('B', 'Tonight 20:00'),
                                     ('C', 'Tomorrow 20:00')], every=True)
    equal(lines[0]['kind'], 'heading', 'the first day has a heading')
    equal(service.coming_up_next_line(lines, 0), '2', 'line 2')


def test_scrolled_past():
    """<summary>Scrolled past the next slot gives an empty string.</summary>"""
    lines = service.coming_up_lines([('A', 'Tonight 19:00'), ('B', 'Tonight 20:00'),
                                     ('C', 'Tomorrow 20:00')], every=True)
    equal(service.coming_up_next_line(lines, 4), '', 'offset beyond the slot')
    single = service.coming_up_lines([('Film', 'Tonight 19:00'), ('Show', 'Tomorrow 20:00')], every=True)
    equal(service.coming_up_next_line(single, 2), '', 'item day scrolled off')


def test_empty():
    """<summary>No lines gives an empty string.</summary>"""
    equal(service.coming_up_next_line([], 0), '', 'empty list')
    equal(service.coming_up_next_line(service.coming_up_lines([], every=True), 0), '', 'no slots drawn')


if __name__ == '__main__':
    for test in (test_single_slot_day_is_line_one, test_only_one_slot, test_several_slot_day_is_line_two,
                 test_scrolled_past, test_empty):
        print('running ' + test.__name__)
        test()
    if FAILURES:
        print('{} check(s) failed'.format(len(FAILURES)))
        sys.exit(1)
    print('test_coming_up_countdown: all checks passed')
