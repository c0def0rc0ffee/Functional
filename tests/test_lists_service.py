#!/usr/bin/env python3
"""
<summary>
Tests for the service's own list handling in service.py: the parts the Lists
screen, the queue windows and Import Lists reach without the add-on API.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs, the fake library and the temporary profile are
the ones tests/test_lists_api.py sets up at import, so the two files share one
picture of a box and both can be run on their own. Each test seeds a lists.json,
builds a real FunctionalHelper and drives one of its list methods, with the fake
library widened where a method asks it something the API tests never do (the
queue's items, a season's details). Exits non zero when a check fails.

Usage:
    python3 tests/test_lists_service.py
</remarks>
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service

# A season each of the fake show, as VideoLibrary.GetSeasonDetails answers.
SEASONS = {9: {"seasonid": 9, "tvshowid": 5, "season": 1, "label": "Season 1",
               "showtitle": "Metro Line", "art": {}},
           10: {"seasonid": 10, "tvshowid": 5, "season": 0, "label": "Specials",
                "showtitle": "Metro Line", "art": {}}}

# What the queue window holds when Save as List is pressed: one Specials episode.
QUEUE = [{"id": 36, "type": "episode", "title": "Special", "file": "/media/tv/ml/s00e01.mkv",
          "showtitle": "Metro Line", "season": 0, "episode": 1, "runtime": 600}]


def wider_jsonrpc(text):
    """
    <summary>
    The API tests' fake library, plus seasons and the queue's items.
    </summary>
    <param name="text">The request as JSON text.</param>
    <returns>The reply as JSON text.</returns>
    """
    req = json.loads(text)
    method, p = req["method"], req.get("params") or {}
    if method == "VideoLibrary.GetSeasonDetails" and p.get("seasonid") in SEASONS:
        return json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": {"seasondetails": SEASONS[p["seasonid"]]}})
    if method == "VideoLibrary.GetEpisodes" and "tvshowid" in p and "season" in p:
        rows = [e for e in T.EPISODES.values()
                if e["tvshowid"] == p["tvshowid"] and e["season"] == p["season"]]
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"episodes": rows}})
    if method == "Playlist.GetItems":
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"items": QUEUE}})
    return T.fake_jsonrpc(text)


T.xbmc.executeJSONRPC = wider_jsonrpc


class _File:
    """<summary>xbmcvfs.File over a local path, enough for Import Lists to read.</summary>"""

    def __init__(self, path, _mode="r"):
        """<summary>Open the file for reading.</summary>
        <param name="path">A local path; special:// paths are translated first.</param>
        <param name="_mode">Ignored, reading only.</param>"""
        self._fh = open(T._translate(path), encoding="utf-8")

    def read(self):
        """<summary>The whole file as text.</summary>"""
        return self._fh.read()

    def close(self):
        """<summary>Close the file.</summary>"""
        self._fh.close()

    def __enter__(self):
        """<summary>Context manager entry, as xbmcvfs.File offers.</summary>"""
        return self

    def __exit__(self, *_exc):
        """<summary>Context manager exit: close.</summary>
        <param name="_exc">Exception details, ignored.</param>"""
        self.close()


T.xbmcvfs.File = _File

check = T.check


def test_queue_save_keeps_season_zero():
    """<summary>Save as List on a queue holding a Specials episode stores season "0"
    and the Lists screen's second line shows S00E01.</summary>"""
    helper = T.seed([])
    helper._lists_ask_name = lambda heading, default="": "From queue"
    helper._lists_save_queue()
    saved = T.on_disk()["lists"]
    check(len(saved) == 1 and saved[0]["items"][0]["season"] == "0",
          "queue save keeps season 0 as the text 0")
    with helper._lists_lock:
        item = helper._lists[0]["items"][0]
    check("S00E01" in helper._list_item_sub(item), "queue saved Specials episode reads S00E01")


def test_expand_keeps_season_zero():
    """<summary>A Specials season row expands to episodes that still carry season "0".</summary>"""
    helper = T.seed([])
    row = helper._list_item_clean({"dbtype": "season", "dbid": 10, "label": "x"})
    row = helper._list_group_fill(row)
    check(row is not None and row["season"] == "0" and row["count"] == 1,
          "a Specials season row fills with season 0 and one episode")
    episodes = helper._lists_expand([row])
    check([(e["dbid"], e["season"], e["episode"]) for e in episodes] == [(36, "0", "1")],
          "expanding a Specials season keeps season 0 on its episodes")


def test_parse_renames_case_duplicates():
    """<summary>A lists file naming two lists alike, ignoring case, reads with the
    second renamed rather than dropped or kept as a pair.</summary>"""
    helper = T.seed([])
    text = json.dumps({"lists": [{"name": "Films", "items": []}, {"name": "films", "items": []},
                                 {"name": "FILMS", "items": []}, {"name": "Other", "items": []}]})
    lists, _last, _sort = helper._lists_parse(text)
    check([l["name"] for l in lists] == ["Films", "films (2)", "FILMS (3)", "Other"],
          "case duplicates renamed in file order, nothing dropped")
    lists, _last, _sort = helper._lists_parse(json.dumps({"lists": [
        {"name": "A", "items": []}, {"name": "B", "items": []}]}))
    check([l["name"] for l in lists] == ["A", "B"], "distinct names untouched")


def test_import_skips_case_clash():
    """<summary>Import Lists adds a new list but skips one whose name is here under
    another case, leaving the box's list as it was, with a toast saying so.</summary>
    <remarks>A clash inside the file itself cannot reach here: _lists_parse renames
    it on the way in, which test_parse_renames_case_duplicates covers.</remarks>"""
    helper = T.seed([{"name": "Films", "items": [], "seq": 1}])
    path = os.path.join(T.PROFILE, "incoming.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "lists": [
            {"name": "films", "items": [{"label": "Metropolis", "dbtype": "movie", "dbid": 12,
                                         "file": "/media/films/Metropolis.mkv"}]},
            {"name": "New", "items": [{"label": "Metropolitan", "dbtype": "movie", "dbid": 13,
                                       "file": "/media/films/Metropolitan.mkv"}]}]}, fh)
    T._Dialog.toasts.clear()
    helper._lists_import(path)
    saved = T.on_disk()["lists"]
    check([l["name"] for l in saved] == ["Films", "New"], "clash skipped, new list added")
    check(saved[0]["items"] == [] and [it["dbid"] for it in saved[1]["items"]] == [13],
          "the box's list untouched, the new list took its items")
    texts = [t[1] for t in T._Dialog.toasts]
    check(any(t.startswith("1 list(s) not imported") for t in texts),
          "a toast counts the skipped list")
    check(any(t.startswith("Imported 1 new list(s) and 1 new item(s)") for t in texts),
          "the usual toast still shows")


def main():
    """<summary>Run every test, clean up, and exit non zero on any failure.</summary>"""
    tests = [test_queue_save_keeps_season_zero, test_expand_keeps_season_zero,
             test_parse_renames_case_duplicates, test_import_skips_case_clash]
    try:
        for test in tests:
            print("running " + test.__name__)
            test()
    finally:
        T.lists_api.stop()
        shutil.rmtree(T.PROFILE, ignore_errors=True)
    if T.FAILURES:
        print("test_lists_service: %d check(s) failed" % len(T.FAILURES))
        sys.exit(1)
    print("test_lists_service: all checks passed")


if __name__ == "__main__":
    main()
