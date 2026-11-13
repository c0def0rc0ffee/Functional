#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 39, Hide from Continue Watching, written from the
spec: the pure functions that read and write continue_hidden.json and build
the filtered smart playlists, the XML the switch gates (it must draw nothing
and change nothing while off), the strings, and the helper's own path from
the press and hold command to the playlist files, the Home properties and
the return of a title once it is played again.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py, whose temporary profile holds the files these tests
write. The library is a small fake answering JSON-RPC. How the row looks on
a TV is the live check's job. Exits non zero when a check fails.

Usage:
    python3 tests/test_hide_continue.py
</remarks>
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)

service = T.service
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")
XML = os.path.join(SKIN, "xml")
STRINGS = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
FAILURES = []
DATA = os.path.join(T.PROFILE, "addon_data", "skin.functional")
STORE = os.path.join(DATA, "continue_hidden.json")
SPECIAL = "special://profile/addon_data/skin.functional/continue/"


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def read(path):
    """
    <summary>Reads a text file.</summary>
    <param name="path">The path.</param>
    <returns>The text.</returns>
    """
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def raises_value_error(text):
    """
    <summary>Whether parse_hidden_doc refuses the text with ValueError.</summary>
    <param name="text">The file's text.</param>
    <returns>True when it raised ValueError.</returns>
    """
    try:
        service.parse_hidden_doc(text)
    except ValueError:
        return True
    return False


def test_parse():
    """
    <summary>parse_hidden_doc: files and shows always present, a byte order
    mark allowed, a missing member added empty, and ValueError for a top
    level or a member that is not an object, or text that is not JSON.</summary>
    """
    print("running test_parse")
    doc = service.parse_hidden_doc('{"files": {"/a.mkv": {"type": "movie", "at": 1}}, "shows": {}}')
    if doc["files"] != {"/a.mkv": {"type": "movie", "at": 1}} or doc["shows"] != {}:
        fail("a complete document should come back as written, got %r" % doc)
    doc = service.parse_hidden_doc("{}")
    if doc.get("files") != {} or doc.get("shows") != {}:
        fail("an empty object should gain empty files and shows, got %r" % doc)
    doc = service.parse_hidden_doc('{"shows": {"tvdb:1": {}}}')
    if doc.get("files") != {} or "tvdb:1" not in doc["shows"]:
        fail("a missing files member should be added empty and shows kept, got %r" % doc)
    doc = service.parse_hidden_doc('{"files": {"x": {}}}')
    if doc.get("shows") != {} or "x" not in doc["files"]:
        fail("a missing shows member should be added empty and files kept, got %r" % doc)
    doc = service.parse_hidden_doc('﻿{"files": {}, "shows": {}}')
    if doc.get("files") != {}:
        fail("a byte order mark should be allowed")
    doc = service.parse_hidden_doc('{"version": 2, "files": {}}')
    if doc.get("version") != 2:
        fail("other top level keys should be kept")
    for bad in ("[]", '"text"', "3", "null", '{"files": []}', '{"shows": []}',
                '{"files": {}, "shows": "x"}', '{"files": null}', "not json", ""):
        if not raises_value_error(bad):
            fail("%r should be refused with ValueError" % bad)


def test_file_values():
    """
    <summary>hidden_file_values: the whole path plus the last part when
    different, only the whole path for plugin:// paths, nothing for an empty
    or blank path.</summary>
    """
    print("running test_file_values")
    f = service.hidden_file_values
    if f("/media/films/Metropolis.mkv") != ["/media/films/Metropolis.mkv", "Metropolis.mkv"]:
        fail("a local path should give itself and its file name, got %r" % f("/media/films/Metropolis.mkv"))
    if f("smb://host/share/a/b.mkv") != ["smb://host/share/a/b.mkv", "b.mkv"]:
        fail("a network path should give itself and its file name, got %r" % f("smb://host/share/a/b.mkv"))
    if f("name.mkv") != ["name.mkv"]:
        fail("a bare name equals its last part, so it should be given once, got %r" % f("name.mkv"))
    if f("plugin://plugin.video.example/play/?id=7/x") != ["plugin://plugin.video.example/play/?id=7/x"]:
        fail("a plugin:// path should give only the whole path")
    for blank in ("", "   ", None):
        if f(blank) != []:
            fail("%r should give no values, got %r" % (blank, f(blank)))


def test_files_of():
    """
    <summary>hidden_files_of: only the asked type, oldest first by the
    record's at, and nothing from an empty document.</summary>
    """
    print("running test_files_of")
    doc = {"files": {
        "/m/new.mkv": {"type": "movie", "at": 300},
        "/m/old.mkv": {"type": "movie", "at": 100},
        "/m/mid.mkv": {"type": "movie", "at": 200},
        "/t/e1.mkv": {"type": "episode", "at": 50},
        "/t/e2.mkv": {"type": "episode", "at": 40},
    }, "shows": {}}
    if service.hidden_files_of(doc, "movie") != ["/m/old.mkv", "/m/mid.mkv", "/m/new.mkv"]:
        fail("movies should come oldest first, got %r" % service.hidden_files_of(doc, "movie"))
    if service.hidden_files_of(doc, "episode") != ["/t/e2.mkv", "/t/e1.mkv"]:
        fail("episodes should come oldest first, got %r" % service.hidden_files_of(doc, "episode"))
    if service.hidden_files_of({"files": {}, "shows": {}}, "movie") != []:
        fail("an empty document should give nothing")
    if service.hidden_files_of(doc, "tvshow") != []:
        fail("a type nothing was hidden under should give nothing")


def rules_of(root):
    """
    <summary>The rules of a smart playlist as comparable tuples.</summary>
    <param name="root">The smartplaylist element.</param>
    <returns>A list of (field, operator, value) in file order.</returns>
    """
    return [(r.get("field"), r.get("operator"), (r.findtext("value") or "")) for r in root.findall("rule")]


def test_xsp():
    """
    <summary>hidden_xsp: the type, match all, the in progress rule, one
    filename isnot rule per value, escaping, and agreement with the skin's own
    playlists in type, match, order and limit.</summary>
    """
    print("running test_xsp")
    for dbtype, kind, name in (("movie", "movies", "continue_movies.xsp"),
                               ("episode", "episodes", "continue_episodes.xsp")):
        own = ET.fromstring(read(os.path.join(SKIN, "playlists", name)).encode("utf-8"))
        mine = ET.fromstring(service.hidden_xsp(dbtype, ["/a/b & c.mkv", "/x/y.mkv"]).encode("utf-8"))
        if mine.tag != "smartplaylist" or mine.get("type") != kind:
            fail("the %s playlist should be a smartplaylist of type %s" % (dbtype, kind))
        if own.get("type") != mine.get("type"):
            fail("type differs from the skin's own %s" % name)
        if mine.findtext("match") != "all" or mine.findtext("match") != own.findtext("match"):
            fail("match should be all, as in the skin's own %s" % name)
        order, own_order = mine.find("order"), own.find("order")
        if order is None or order.text != "lastplayed" or order.get("direction") != "descending":
            fail("order should be descending by lastplayed")
        elif own_order is None or (order.text, order.get("direction")) != (own_order.text, own_order.get("direction")):
            fail("order differs from the skin's own %s" % name)
        if mine.findtext("limit") != "12" or mine.findtext("limit") != own.findtext("limit"):
            fail("limit should be 12, as in the skin's own %s" % name)
        got = rules_of(mine)
        want_first = rules_of(own)
        if got[:len(want_first)] != want_first:
            fail("the skin's own rules should come first and unchanged, got %r" % got)
        extra = got[len(want_first):]
        if extra != [("filename", "isnot", "/a/b & c.mkv"), ("filename", "isnot", "b & c.mkv"),
                     ("filename", "isnot", "/x/y.mkv"), ("filename", "isnot", "y.mkv")]:
            fail("each file should give one isnot rule per value, got %r" % extra)
        if not any(r[0] == "inprogress" and r[1] == "true" for r in got):
            fail("the inprogress true rule is missing")
    text = service.hidden_xsp("movie", ["/a/b & c.mkv"])
    if "&amp;" not in text or re.search(r"&(?!amp;|lt;|gt;|quot;|apos;)", text):
        fail("an ampersand should be XML escaped")
    text = service.hidden_xsp("movie", ["/a/<b>.mkv"])
    try:
        ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        fail("angle brackets in a path should still give well formed XML")
    plain = ET.fromstring(service.hidden_xsp("episode", []).encode("utf-8"))
    if [r for r in plain.findall("rule") if r.get("field") == "filename"]:
        fail("with nothing hidden there should be no filename rules")
    plug = ET.fromstring(service.hidden_xsp("movie", ["plugin://p.example/a/b"]).encode("utf-8"))
    vals = [r.findtext("value") for r in plug.findall("rule") if r.get("field") == "filename"]
    if vals != ["plugin://p.example/a/b"]:
        fail("a plugin path should give one rule with the whole path, got %r" % vals)


def test_show_and_unhide():
    """
    <summary>hidden_show and unhide_played: any key matches, none does not,
    the file and every listed key are removed in place, and the result is
    True only when something was removed.</summary>
    """
    print("running test_show_and_unhide")
    doc = {"files": {"/a.mkv": {"type": "movie", "at": 1}, "/b.mkv": {"type": "episode", "at": 2}},
           "shows": {"tvdb:1": {"at": 1}, "tmdb:2": {"at": 2}, "tvdb:9": {"at": 3}}}
    if not service.hidden_show(doc, ["tvdb:0", "tmdb:2"]):
        fail("any matching key should hide the show")
    if service.hidden_show(doc, ["tvdb:0", "imdb:tt1"]) or service.hidden_show(doc, []):
        fail("no matching key, or no keys, should not hide the show")
    if service.hidden_show({"files": {}, "shows": {}}, ["tvdb:1"]):
        fail("an empty document hides nothing")
    if not service.unhide_played(doc, "/a.mkv", []) or "/a.mkv" in doc["files"] or "/b.mkv" not in doc["files"]:
        fail("playing a hidden file should remove just that file and report True")
    if not service.unhide_played(doc, "/none.mkv", ["tvdb:1", "tmdb:2"]):
        fail("removing shows should report True")
    if "tvdb:1" in doc["shows"] or "tmdb:2" in doc["shows"] or "tvdb:9" not in doc["shows"]:
        fail("every listed key should go and the others stay, got %r" % doc["shows"])
    before = json.dumps(doc, sort_keys=True)
    if service.unhide_played(doc, "/nothing.mkv", ["tvdb:404"]) or json.dumps(doc, sort_keys=True) != before:
        fail("nothing to remove should report False and change nothing")
    if service.unhide_played(doc, "", []):
        fail("an empty path and no keys should report False")


# ---- XML wiring and the off by default proof ---------------------------------

def find_control(root, cid):
    """
    <summary>The control with an id.</summary>
    <param name="root">An XML root.</param>
    <param name="cid">The id as text.</param>
    <returns>The element or None.</returns>
    """
    return next((c for c in root.iter("control") if c.get("id") == cid), None)


def test_settings_wiring():
    """
    <summary>The switch's row, its labels, its help entry and its preview
    form are all in place, and it is off by default.</summary>
    """
    print("running test_settings_wiring")
    row = find_control(ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot(), "7182")
    if row is None or row.get("type") != "radiobutton":
        fail("row 7182 should be a radiobutton in SkinSettings.xml")
    else:
        if row.findtext("label") != "31888":
            fail("the row's label should be string 31888")
        if row.findtext("selected") != "Skin.HasSetting(continue_hide)":
            fail("the row should show the continue_hide setting")
        if row.findtext("onclick") != "Skin.ToggleSetting(continue_hide)":
            fail("the row should toggle continue_hide")
        if row.findtext("enable") != "!Skin.HasSetting(hide_continue)":
            fail("the row's enable should follow !Skin.HasSetting(hide_continue), got %r" % row.findtext("enable"))
    for path in (XML,):
        for name in os.listdir(path):
            if name.endswith(".xml") and "SetBool(continue_hide" in read(os.path.join(path, name)):
                fail("%s switches continue_hide on by default" % name)
    for name in ("addon.xml",):
        if "continue_hide" in read(os.path.join(SKIN, name)):
            fail("the switch should not be named in addon.xml")
    help_text = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    shown = re.search(r'<expression name="settings_help_shown">(.*?)</expression>', help_text, re.S)
    if not shown or "Control.HasFocus(7182)" not in shown.group(1):
        fail("7182 should be in settings_help_shown")
    if '<value condition="Control.HasFocus(7182)">$LOCALIZE[31889]</value>' not in help_text:
        fail("the help map should give 7182 string 31889")
    prev = read(os.path.join(XML, "Includes_SettingsPreview.xml"))
    none = re.search(r'<expression name="settings_preview_none">(.*?)</expression>', prev, re.S)
    if not none or "Control.HasFocus(7182)" not in none.group(1):
        fail("7182 should be in settings_preview_none")
    for m in re.finditer(r'<expression name="(settings_preview_[a-z_0-9]+)">(.*?)</expression>', prev, re.S):
        if m.group(1) != "settings_preview_none" and "Control.HasFocus(7182)" in m.group(2):
            fail("7182 should be in no other preview expression, found in %s" % m.group(1))


def test_strings():
    """
    <summary>Strings 31888, 31889 and 31890 exist, and the help line
    carries a Where: line.</summary>
    """
    print("running test_strings")
    table = T.STRINGS
    for sid in (31888, 31889, 31890):
        if not table.get(sid):
            fail("string %d is missing or empty" % sid)
    if "Where:" not in table.get(31889, ""):
        fail("the help string 31889 should carry a Where: line")
    po = read(STRINGS)
    for sid in (31888, 31889, 31890):
        if po.count('msgctxt "#%d"' % sid) != 1:
            fail("string %d should be defined exactly once" % sid)


def test_context_menu():
    """
    <summary>The fourth Continue row: id 963, label 31890, command hide,
    shown only with the switch, reached from row 962, and the other three
    rows drawn exactly as before.</summary>
    """
    print("running test_context_menu")
    root = ET.parse(os.path.join(XML, "DialogContextMenu.xml")).getroot()
    rows = {}
    for inc in root.iter("include"):
        if inc.get("content") == "ContinueContextButton":
            rows[next(p.get("value") for p in inc.findall("param") if p.get("name") == "id")] = {
                p.get("name"): p.get("value") for p in inc.findall("param")}
    if "963" not in rows:
        fail("row 963 is missing")
        return
    r = rows["963"]
    if r.get("label") != "$LOCALIZE[31890]" or r.get("command") != "hide":
        fail("row 963 should be labelled 31890 and send hide, got %r" % r)
    if r.get("shown") != "Skin.HasSetting(continue_hide)":
        fail("row 963 should be shown only with continue_hide, got %r" % r.get("shown"))
    if rows.get("962", {}).get("ondown") != "963":
        fail("row 962's down should go to 963")
    if r.get("onup") != "962":
        fail("row 963's up should go to 962")
    for rid in ("960", "961", "962"):
        if rid in rows and "shown" in rows[rid]:
            fail("row %s should not be gated by the switch" % rid)
    inc = read(os.path.join(XML, "Includes.xml"))
    if '<param name="shown" default="true" />' not in inc:
        fail("the row include should default shown to true so the old rows are unchanged")
    if inc.count("$EXP[continue_menu] + $PARAM[shown]") < 2:
        fail("the row's button and backing should both honour shown and continue_menu")


def test_home_paths():
    """
    <summary>Home's two containers read the path variables, and each
    variable gives the skin's own playlist unless the switch is on and the
    property is set, so Home is unchanged with the switch off.</summary>
    """
    print("running test_home_paths")
    home = ET.parse(os.path.join(XML, "Home.xml")).getroot()
    for cid, var in (("9201", "ContinueMoviesPath"), ("9203", "ContinueEpisodesPath")):
        ctl = find_control(home, cid)
        content = ctl.find("content") if ctl is not None else None
        if content is None or (content.text or "").strip() != "$VAR[%s]" % var:
            fail("container %s should take its content from $VAR[%s]" % (cid, var))
        elif content.get("limit") != "12" or content.get("target") != "videos":
            fail("container %s should keep target videos and limit 12" % cid)
    inc = ET.parse(os.path.join(XML, "Includes.xml")).getroot()
    for name, prop, own in (("ContinueMoviesPath", "continue_movies_xsp", "special://skin/playlists/continue_movies.xsp"),
                            ("ContinueEpisodesPath", "continue_episodes_xsp", "special://skin/playlists/continue_episodes.xsp")):
        var = next((v for v in inc.iter("variable") if v.get("name") == name), None)
        values = [(v.get("condition"), v.text) for v in var.findall("value")] if var is not None else []
        if len(values) != 2:
            fail("%s should have two values, got %r" % (name, values))
            continue
        cond, text = values[0]
        if "Skin.HasSetting(continue_hide)" not in (cond or "") or prop not in (cond or "") or prop not in (text or ""):
            fail("%s's first value should need the switch and the %s property, got %r" % (name, prop, values[0]))
        if values[1] != (None, own):
            fail("%s should end on the skin's own playlist %s, got %r" % (name, own, values[1]))
        if not os.path.isfile(os.path.join(SKIN, "playlists", os.path.basename(own))):
            fail("the skin's own playlist %s is missing" % own)
    # Nothing else may read the helper's properties or the hide command.
    for fname in os.listdir(XML):
        if not fname.endswith(".xml"):
            continue
        text = read(os.path.join(XML, fname))
        if fname not in ("Includes.xml",) and ("continue_movies_xsp" in text or "continue_episodes_xsp" in text):
            fail("%s reads the helper's playlist property directly" % fname)


# ---- the helper end to end ----------------------------------------------------

class Lib:
    """
    <summary>A fake library of two movies, two episodes of one show, and the
    calls made to it.</summary>
    """

    FILES = {("movie", 12): "/media/films/Metropolis.mkv", ("movie", 13): "/media/films/Other.mkv",
             ("episode", 101): "/media/tv/show/s01e01.mkv", ("episode", 102): "/media/tv/show/s01e02.mkv"}

    def __init__(self):
        """<summary>Start with no calls.</summary>"""
        self.rpc = []

    def jsonrpc(self, method, params=None):
        """
        <summary>Answer the calls the helper may make about an item or a show.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        params = params or {}
        self.rpc.append((method, params))
        if method == "VideoLibrary.GetMovieDetails":
            mid = params.get("movieid")
            return {"result": {"moviedetails": {"movieid": mid, "title": "Film %s" % mid, "label": "Film %s" % mid,
                                                "file": self.FILES.get(("movie", mid), ""), "resume": {"position": 5.0}}}}
        if method == "VideoLibrary.GetEpisodeDetails":
            eid = params.get("episodeid")
            return {"result": {"episodedetails": {"episodeid": eid, "title": "Ep %s" % eid, "label": "Ep %s" % eid,
                                                  "tvshowid": 31, "showtitle": "Show", "season": 1,
                                                  "episode": eid - 100, "file": self.FILES.get(("episode", eid), ""),
                                                  "resume": {"position": 5.0}}}}
        if method == "VideoLibrary.GetTVShowDetails":
            return {"result": {"tvshowdetails": {"tvshowid": 31, "title": "Show", "label": "Show", "year": 2024,
                                                 "uniqueid": {"tvdb": "31031"}}}}
        return {"result": "OK"}


class Quick:
    """<summary>A thread that runs its target as soon as it is started.</summary>"""

    def __init__(self, target=None, args=(), **_kw):
        """<summary>Keep the target.</summary>"""
        self.target, self.args = target, args

    def start(self):
        """<summary>Run the target now.</summary>"""
        self.target(*self.args)

    def is_alive(self):
        """<summary>Never still running.</summary><returns>False.</returns>"""
        return False

    def join(self, *_a, **_kw):
        """<summary>Nothing to wait for.</summary>"""


def clear_store():
    """
    <summary>Start with no store, no published playlists, no properties and the
    switch off.</summary>
    <remarks>Only the test profile's own files are touched.</remarks>
    """
    for folder in (DATA, os.path.join(DATA, "continue")):
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    os.remove(path)  # the test profile's own files, made by these tests
    T.PROPS.clear()
    T.SKIN_SETTINGS.discard("continue_hide")


def aside_files():
    """<summary>The set aside copies of a damaged store.</summary><returns>Sorted names.</returns>"""
    if not os.path.isdir(DATA):
        return []
    return sorted(n for n in os.listdir(DATA) if n.startswith("continue_hidden.json.bad-"))


def stored():
    """<summary>The store as written.</summary><returns>The parsed document.</returns>"""
    with open(STORE, encoding="utf-8") as handle:
        return json.load(handle)


def make_helper(lib):
    """
    <summary>A real helper wired to the library, with threads that run at once.</summary>
    <param name="lib">The fake library.</param>
    <returns>A fresh FunctionalHelper.</returns>
    """
    service._jsonrpc = lib.jsonrpc
    service.threading.Thread = Quick
    return service.FunctionalHelper()


def special_to_local(path):
    """
    <summary>A special:// path as a file in the test profile.</summary>
    <param name="path">The special:// path.</param>
    <returns>The local path.</returns>
    """
    return T._translate(path)


def xsp_values(prop):
    """
    <summary>The filename values refused by the playlist a Home property names.</summary>
    <param name="prop">The Home property name.</param>
    <returns>The list of values, or None when the property is empty or the file is missing.</returns>
    """
    path = T.PROPS.get(prop, "")
    if not path:
        return None
    local = special_to_local(path)
    if not os.path.isfile(local):
        return None
    root = ET.fromstring(read(local).encode("utf-8"))
    return [r.findtext("value") for r in root.findall("rule") if r.get("field") == "filename"]


def run_service_checks():
    """
    <summary>Hide a movie, then an episode, then a show from Next Up through
    the helper; check the store, the alternating playlist files and the Home
    properties; then bring each back by playing it.</summary>
    """
    print("running test_service")
    clear_store()
    lib = Lib()
    h = make_helper(lib)
    T.SKIN_SETTINGS.add("continue_hide")

    h._continue_hide("movie", 12, False)
    if not os.path.isfile(STORE):
        fail("hiding a movie should write continue_hidden.json under the profile")
        return
    doc = stored()
    rec = doc.get("files", {}).get("/media/films/Metropolis.mkv")
    if not rec or rec.get("type") != "movie" or "at" not in rec:
        fail("the movie should be kept under its file with type movie and an at, got %r" % doc)
    first = T.PROPS.get("continue_movies_xsp", "")
    if not first.startswith(SPECIAL + "continue_movies_") or not first.endswith(".xsp"):
        fail("the movies property should name a special:// continue_movies_a or _b file, got %r" % first)
    if "/media/films/Metropolis.mkv" not in (xsp_values("continue_movies_xsp") or []):
        fail("the published movies playlist should refuse the hidden file")
    if T.PROPS.get("continue_episodes_xsp"):
        fail("with no episode hidden the episodes property should be clear")

    h._continue_hide("movie", 13, False)
    second = T.PROPS.get("continue_movies_xsp", "")
    if second == first or not second:
        fail("each publish should alternate files so the container path changes, got %r then %r" % (first, second))
    if {os.path.basename(first), os.path.basename(second)} != {"continue_movies_a.xsp", "continue_movies_b.xsp"}:
        fail("the two files should be continue_movies_a.xsp and continue_movies_b.xsp, got %r and %r" % (first, second))
    vals = xsp_values("continue_movies_xsp") or []
    if "/media/films/Other.mkv" not in vals or "/media/films/Metropolis.mkv" not in vals:
        fail("the newer playlist should refuse both hidden movies, got %r" % vals)

    h._continue_hide("episode", 101, False)
    ep = T.PROPS.get("continue_episodes_xsp", "")
    if not os.path.basename(ep).startswith("continue_episodes_") or not ep.startswith(SPECIAL):
        fail("the episodes property should name a continue_episodes_ file, got %r" % ep)
    if "/media/tv/show/s01e01.mkv" not in (xsp_values("continue_episodes_xsp") or []):
        fail("the episodes playlist should refuse the hidden episode")
    if "/media/tv/show/s01e01.mkv" in (xsp_values("continue_movies_xsp") or []):
        fail("an episode must not appear in the movies playlist")

    # From Next Up the show goes, not the file.
    before_files = set(stored()["files"])
    h._continue_hide("episode", 102, True)
    doc = stored()
    if "tvdb:31031" not in doc.get("shows", {}):
        fail("hiding from Next Up should keep the show under tvdb:31031, got %r" % doc.get("shows"))
    if set(doc["files"]) != before_files:
        fail("hiding from Next Up should not add a file, got %r" % set(doc["files"]))
    if not service.hidden_show(doc, ["tvdb:31031"]):
        fail("the stored show should read as hidden")

    # Playing a hidden movie brings it back; the other stays hidden.
    h.onNotification("xbmc", "Player.OnAVStart", json.dumps({"item": {"type": "movie", "id": 12}}))
    h.update_continue_watching()
    doc = stored()
    if "/media/films/Metropolis.mkv" in doc["files"] or "/media/films/Other.mkv" not in doc["files"]:
        fail("playing a hidden movie should bring back just that movie, got %r" % list(doc["files"]))
    vals = xsp_values("continue_movies_xsp") or []
    if "/media/films/Metropolis.mkv" in vals or "/media/films/Other.mkv" not in vals:
        fail("the republished movies playlist should let the played movie back, got %r" % vals)

    # Playing a hidden episode brings back the episode and its hidden show.
    h.onNotification("xbmc", "Player.OnAVStart", json.dumps({"item": {"type": "episode", "id": 101}}))
    h.update_continue_watching()
    doc = stored()
    if "/media/tv/show/s01e01.mkv" in doc["files"]:
        fail("playing a hidden episode should bring it back")
    if "tvdb:31031" in doc["shows"]:
        fail("playing an episode should bring back its hidden show")

    # Last hidden movie returns: the kind has nothing hidden, so its property clears.
    h.onNotification("xbmc", "Player.OnAVStart", json.dumps({"item": {"type": "movie", "id": 13}}))
    h.update_continue_watching()
    if T.PROPS.get("continue_movies_xsp"):
        fail("a kind with nothing hidden should clear its property, got %r" % T.PROPS.get("continue_movies_xsp"))
    if T.PROPS.get("continue_episodes_xsp"):
        fail("the episodes property should also be clear with nothing hidden, got %r" % T.PROPS.get("continue_episodes_xsp"))


def test_service():
    """
    <summary>Runs the end to end helper checks, putting the stubs back after.</summary>
    """
    saved = (service._jsonrpc, service.threading.Thread)
    try:
        run_service_checks()
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the helper path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        service._jsonrpc, service.threading.Thread = saved
        clear_store()


def test_damaged_store():
    """
    <summary>A store that cannot be read is renamed aside with a .bad-
    YYYYMMDD-HHMMSS suffix, its text kept, never deleted or overwritten, and
    hiding then starts a fresh store.</summary>
    """
    print("running test_damaged_store")
    saved = (service._jsonrpc, service.threading.Thread)
    try:
        clear_store()
        os.makedirs(DATA, exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as handle:
            handle.write("{ damaged")
        lib = Lib()
        h = make_helper(lib)
        T.SKIN_SETTINGS.add("continue_hide")
        h._continue_hide("movie", 12, False)
        aside = aside_files()
        if len(aside) != 1:
            fail("a damaged store should be set aside once, got %r" % aside)
        else:
            if not re.fullmatch(r"continue_hidden\.json\.bad-\d{8}-\d{6}", aside[0]):
                fail("the set aside name should end .bad-YYYYMMDD-HHMMSS, got %r" % aside[0])
            if read(os.path.join(DATA, aside[0])) != "{ damaged":
                fail("the set aside copy should hold the damaged text unchanged")
        try:
            doc = stored()
            if "/media/films/Metropolis.mkv" not in doc.get("files", {}):
                fail("after setting the damaged file aside, a fresh store should hold the new hide")
        except (OSError, ValueError):
            fail("a fresh, readable store should follow the damaged one")
        # A store with a bad member is also unreadable: set aside, not written over.
        clear_store()
        with open(STORE, "w", encoding="utf-8") as handle:
            handle.write('{"files": []}')
        h2 = make_helper(lib)
        h2._continue_hide("movie", 13, False)
        if len(aside_files()) != 1:
            fail("a store with files not an object should be set aside too, got %r" % aside_files())
    except Exception as exc:
        fail("the damaged store path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        service._jsonrpc, service.threading.Thread = saved
        clear_store()


class NextUpLib:
    """
    <summary>A fake library for the Next Up lookup: three shows in progress,
    each with one unwatched episode, the second show the one to hide.</summary>
    """

    SHOWS = [{"tvshowid": 1, "title": "Alpha", "year": 2001, "uniqueid": {"tvdb": "111"}},
             {"tvshowid": 2, "title": "Bravo", "year": 2002, "uniqueid": {"tvdb": "222"}},
             {"tvshowid": 3, "title": "Charlie", "year": 2003, "uniqueid": {}}]

    def jsonrpc(self, method, params=None):
        """
        <summary>Answer the two calls _nextup_worker makes.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        params = params or {}
        if method == "VideoLibrary.GetTVShows":
            return {"result": {"tvshows": [dict(s) for s in self.SHOWS]}}
        if method == "VideoLibrary.GetEpisodes":
            sid = params.get("tvshowid")
            path = "plugin://plugin.video.jellyfin/x/?id=%d&mode=play" % sid if sid == 1 else "/media/tv/show%d/e1.mkv" % sid
            return {"result": {"episodes": [{"episodeid": 500 + sid, "title": "E", "season": 1, "episode": 1,
                                             "showtitle": "S", "resume": {"position": 0}, "file": path}]}}
        return {"result": "OK"}


def test_nextup():
    """
    <summary>NEXTUP-LIBRARY: the playlist text, the row's files alternating
    and staying put for an unchanged list, an empty list clearing the row,
    and a hidden show left out of Next Up only while the switch is on.</summary>
    """
    print("running test_nextup")
    root = ET.fromstring(service.nextup_xsp(["plugin://p/?a=1&b=2", "/media/tv/x.mkv"]).encode("utf-8"))
    if root.get("type") != "episodes" or root.findtext("match") != "one":
        fail("the Next Up playlist is not episodes matching any rule")
    values = [(r.get("field"), r.get("operator"), r.findtext("value")) for r in root.findall("rule")]
    if values != [("filename", "is", "plugin://p/?a=1&b=2"), ("filename", "is", "/media/tv/x.mkv"),
                  ("filename", "is", "x.mkv")]:
        fail("Next Up rules are %r" % values)
    if root.findtext("limit") != str(service.FunctionalHelper.NEXTUP_MAX):
        fail("the Next Up playlist limit is not NEXTUP_MAX")
    home = read(os.path.join(XML, "Home.xml"))
    if '<content target="videos" limit="12">$INFO[Window(home).Property(nextup_xsp)]</content>' not in home:
        fail("Home's Next Up row does not read the nextup_xsp playlist")
    if "NextUpRows" in home or "NextUpRow" in read(os.path.join(XML, "Includes.xml")):
        fail("the static Next Up slots are still there")

    saved = (service._jsonrpc, service.threading.Thread)
    try:
        clear_store()
        lib = NextUpLib()
        h = make_helper(lib)
        service._jsonrpc = lib.jsonrpc
        h._nextup_worker()
        first = T.PROPS.get("nextup_xsp", "")
        if not first.startswith(SPECIAL + "nextup_") or T.PROPS.get("NextUp.Count") != "3":
            fail("three shows gave property %r and count %r" % (first, T.PROPS.get("NextUp.Count")))
        h._nextup_worker()
        if T.PROPS.get("nextup_xsp") != first:
            fail("an unchanged Next Up list moved the row to another file")
        # Hide Bravo, as _continue_hide stores it, then look again.
        os.makedirs(DATA, exist_ok=True)
        with open(STORE, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "files": {}, "shows": {"tvdb:222": {"title": "Bravo"}}}, handle)
        h._nextup_worker()
        if T.PROPS.get("NextUp.Count") != "3":
            fail("a hidden show left Next Up with the switch off")
        T.SKIN_SETTINGS.add("continue_hide")
        h._nextup_worker()
        files = xsp_values("nextup_xsp") or []
        if T.PROPS.get("NextUp.Count") != "2" or any("show2" in f for f in files):
            fail("with the switch on the hidden show stayed in Next Up: %r" % files)
        if T.PROPS.get("nextup_xsp") == first:
            fail("a changed Next Up list kept the same file, so the row would not reload")
        h._nextup_publish([])
        if T.PROPS.get("nextup_xsp") or T.PROPS.get("NextUp.Count") != "0":
            fail("an empty Next Up list left the row pointing at a playlist")
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("the Next Up path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        service._jsonrpc, service.threading.Thread = saved
        clear_store()


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_parse()
    test_file_values()
    test_files_of()
    test_xsp()
    test_show_and_unhide()
    test_settings_wiring()
    test_strings()
    test_context_menu()
    test_home_paths()
    test_service()
    test_damaged_store()
    test_nextup()
    if FAILURES:
        print("test_hide_continue: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_hide_continue: all checks passed")


if __name__ == "__main__":
    main()
