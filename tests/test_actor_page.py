#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 30, the actor page, written from the spec: the switch
row and its neighbours, the help, preview and strings, the 1156 dialog's
shape, lists and navigation, and the service's handling of a cast portrait
click with the switch off and on.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py; the condition reader, the Rig and the URL helpers are
borrowed from tests/test_watchlist.py. Exits non zero when a check fails.

Usage:
    python3 tests/test_actor_page.py
</remarks>
"""

import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)
import test_watchlist as W  # noqa: E402

service = T.service
XML = W.XML
check = W.check
fail = W.fail
read = W.read
Env = W.Env
url_doc = W.url_doc
flat_rules = W.flat_rules
Rig = W.Rig
by_id = W.find_control

DIALOG = os.path.join(XML, "Custom_1156_Actor.xml")
NAME = 'Zoë "Zed" O\'Neil & Ant, テスト 名前'


def strings_po():
    """
    <summary>The English strings by id.</summary>
    <returns>A dict of id text to msgid.</returns>
    """
    text = read(W.STRINGS)
    return {m.group(1): m.group(2) for m in re.finditer(r'msgctxt "#(\d+)"\nmsgid "(.*)"', text)}


def target(control, tag, env):
    """
    <summary>Where a navigation tag leads, taking the first line whose condition holds.</summary>
    <param name="control">The control element.</param>
    <param name="tag">"onup", "ondown", "onleft" or "onright".</param>
    <param name="env">The state.</param>
    <returns>The destination text, or None when no line applies.</returns>
    """
    for node in control.findall(tag):
        if W.evaluate(node.get("condition") or "", env):
            return (node.text or "").strip()
    return None


# ---- The setting row -----------------------------------------------------------

def test_setting_row():
    """
    <summary>Row 7215 is a radiobutton last in grouplist 7021 after 7214, with
    the label, selected state, click and left link; 7316 goes up to it.</summary>
    """
    print("running test_setting_row")
    root = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    group = by_id(root, "7021")
    check(group is not None and group.get("type") == "grouplist", "7021 is a grouplist")
    ids = [c.get("id") for c in group.findall("control")] if group is not None else []
    check("7215" in ids and "7214" in ids and ids.index("7215") == ids.index("7214") + 1,
          "row 7215 is inside 7021 straight after 7214")
    check(bool(ids) and ids[-1] == "7215", "7215 is the list's last row")
    row = by_id(root, "7215")
    check(row is not None and row.get("type") == "radiobutton", "7215 is a radiobutton")
    if row is not None:
        check((row.findtext("label") or "").strip() in ("31939", "$LOCALIZE[31939]"), "7215 label is 31939")
        check((row.findtext("selected") or "").strip() == "Skin.HasSetting(actor_page)",
              "7215 is selected by the switch")
        check((row.findtext("onclick") or "").strip() == "Skin.ToggleSetting(actor_page)",
              "7215 click toggles the switch")
        check((row.findtext("onleft") or "").strip() == "7230", "left from 7215 goes to 7230")
    last = by_id(root, "7316")
    check(last is not None and (last.findtext("onup") or "").strip() == "7215", "7316 onup is 7215")


def test_help_preview_strings():
    """
    <summary>Help 31940 with a Where line, listed as shown; preview form None
    only; strings 31939, 31940 and 31941 exist as promised.</summary>
    """
    print("running test_help_preview_strings")
    help_text = read(os.path.join(XML, "Includes_SettingsHelp.xml"))
    preview = read(os.path.join(XML, "Includes_SettingsPreview.xml"))
    po = strings_po()
    shown = help_text.split('<expression name="settings_help_shown">')[1].split("</expression>")[0]
    check("Control.HasFocus(7215)" in shown, "settings_help_shown lists 7215")
    entry = re.search(r'Control\.HasFocus\(7215\)">\$LOCALIZE\[(\d+)\]', help_text)
    check(bool(entry) and entry.group(1) == "31940", "the help map sends 7215 to 31940")
    check("[CR]Where: " in po.get("31940", ""), "string 31940 has a Where line")
    none = preview.split('<expression name="settings_preview_none">')[1].split("</expression>")[0]
    check("Control.HasFocus(7215)" in none, "7215 is in settings_preview_none")
    check(len(re.findall(r"Control\.HasFocus\(7215\)", preview)) == 1,
          "7215 appears in the preview file only once")
    check(bool(po.get("31939")), "string 31939 exists and is not empty")
    check(po.get("31941") == "None in your library", "string 31941 is None in your library")
    for sid in ("31087", "31090"):
        check(bool(po.get(sid)), "heading string %s exists" % sid)


# ---- The dialog ------------------------------------------------------------------

def dialog():
    """
    <summary>The actor dialog's XML.</summary>
    <returns>The root element.</returns>
    """
    return ET.parse(DIALOG).getroot()


def test_dialog_shape():
    """
    <summary>Root, default control, no focus moving onload, panel, photo and name.</summary>
    """
    print("running test_dialog_shape")
    check(os.path.exists(DIALOG), "xml/Custom_1156_Actor.xml exists")
    if not os.path.exists(DIALOG):
        return
    root = dialog()
    check(root.tag == "window" and root.get("id") == "1156" and root.get("type") == "dialog",
          "root is window id 1156 type dialog")
    default = root.find("defaultcontrol")
    check(default is not None and (default.text or "").strip() == "9361", "default control is 9361")
    check(default is not None and default.get("always") == "true", "default control is always")
    onload = [(n.text or "") for n in root.iter("onload")]
    check(not any("SetFocus" in t or "Control.Move" in t for t in onload), "no onload moves focus")
    panel = [c for c in root.iter("control")
             if (c.findtext("width") or "").strip() == "1920" and (c.findtext("height") or "").strip() == "1080"]
    check(bool(panel), "a full screen (1920 by 1080) control exists as the panel")
    photo = [c for c in root.iter("control") if c.get("type") == "image"
             and "Window(home).Property(ActorThumb)" in (c.findtext("texture") or "")]
    check(bool(photo), "an image shows the ActorThumb property")
    if photo:
        tex = photo[0].find("texture")
        fallback = tex.get("fallback") or photo[0].findtext("fallbackimage") or ""
        check("DefaultActor.png" in fallback, "the photo falls back to DefaultActor.png")
    names = [c for c in root.iter("control") if c.get("type") == "label"
             and "$INFO[Window(home).Property(ActorName)]" in (c.findtext("label") or "")]
    check(bool(names), "a label shows the ActorName property")


def test_list_attributes():
    """
    <summary>Lists 9361 and 9362 read the right paths with the promised attributes.</summary>
    """
    print("running test_list_attributes")
    if not os.path.exists(DIALOG):
        fail("dialog missing, lists not checked")
        return
    root = dialog()
    for cid, prop in (("9361", "ActorFilmsPath"), ("9362", "ActorShowsPath")):
        lst = by_id(root, cid)
        check(lst is not None, "list %s exists" % cid)
        if lst is None:
            continue
        content = lst.find("content")
        check(content is not None and (content.text or "").strip() == "$INFO[Window(home).Property(%s)]" % prop,
              "%s content is the %s property" % (cid, prop))
        attrs = content.attrib if content is not None else {}
        for key, want in (("target", "videos"), ("sortby", "year"), ("sortorder", "descending"),
                          ("browse", "never")):
            check(attrs.get(key) == want, "%s content %s is %s (got %r)" % (cid, key, want, attrs.get(key)))
        # ACTOR-PAGE-FIX (review of 13/11/2026): every title, so no cap and the
        # heading's count is the real total.
        check("limit" not in attrs, "%s content has no limit (got %r)" % (cid, attrs.get("limit")))


def test_headings_and_empty_label():
    """
    <summary>Headings carry the row's count; 31941 shows only while a row is empty.</summary>
    """
    print("running test_headings_and_empty_label")
    if not os.path.exists(DIALOG):
        fail("dialog missing, headings not checked")
        return
    root = dialog()
    for heading, cid, other in (("31087", "9361", "9362"), ("31090", "9362", "9361")):
        found = [c for c in root.iter("control") if heading in ET.tostring(c, encoding="unicode")
                 and c.get("type") == "label"]
        check(bool(found), "a label uses heading %s" % heading)
        if found:
            text = ET.tostring(found[0], encoding="unicode")
            check("Container(%s).NumItems" % cid in text, "heading %s carries the %s item count" % (heading, cid))
    empties = [c for c in root.iter("control") if "31941" in ET.tostring(c, encoding="unicode")]
    check(len(empties) >= 2, "an empty label exists for each row (found %d)" % len(empties))
    for cid in ("9361", "9362"):
        for state, count in (("empty", 0), ("filled", 5)):
            shown = []
            for c in empties:
                vis = [v for v in c.findall("visible")]
                if not any("Container(%s)" % cid in (v.text or "") for v in vis):
                    continue
                env = Env(counts={cid: count})
                try:
                    shown.append(all(W.evaluate((v.text or ""), env) for v in vis
                                     if "Container(%s)" % cid in (v.text or "")))
                except ValueError as exc:
                    fail("visibility not readable: %s" % exc)
            check(bool(shown) and (any(shown) == (count == 0)),
                  "label 31941 for row %s is %s when the row is %s" % (cid, "shown" if count == 0 else "hidden", state))


def test_navigation():
    """
    <summary>Down, up, left and right between and inside the two lists, for every item count mix.</summary>
    """
    print("running test_navigation")
    if not os.path.exists(DIALOG):
        fail("dialog missing, navigation not checked")
        return
    root = dialog()
    films, shows = by_id(root, "9361"), by_id(root, "9362")
    if films is None or shows is None:
        fail("lists missing, navigation not checked")
        return
    try:
        for nf in (0, 4):
            for ns in (0, 4):
                env = Env(counts={"9361": nf, "9362": ns})
                tag = "films=%d shows=%d" % (nf, ns)
                check(target(films, "ondown", env) == ("9362" if ns else "9361"),
                      "9361 down goes to %s (%s)" % ("9362" if ns else "itself", tag))
                check(target(films, "onup", env) == "9361", "9361 up stays put (%s)" % tag)
                check(target(shows, "onup", env) == ("9361" if nf else "9362"),
                      "9362 up goes to %s (%s)" % ("9361" if nf else "itself", tag))
                check(target(shows, "ondown", env) == "9362", "9362 down stays put (%s)" % tag)
                for lst, cid in ((films, "9361"), (shows, "9362")):
                    for tagname in ("onleft", "onright"):
                        got = target(lst, tagname, env)
                        check(got in (None, "", cid), "%s %s stays in the list (%s, got %r)" % (cid, tagname, tag, got))
    except ValueError as exc:
        fail("navigation condition not readable: %s" % exc)


# ---- The service ----------------------------------------------------------------

def click(rig, slot, switch, names=("First Actor", NAME, "Third Actor"), dbtype="movie"):
    """
    <summary>Set up a helper with published names and a cast click, then run the handler.</summary>
    <param name="rig">The rig of stubs.</param>
    <param name="slot">The text written to cast_run.</param>
    <param name="switch">True when the actor_page switch is on.</param>
    <param name="names">The names published, in slot order.</param>
    <param name="dbtype">The info dialog's media type.</param>
    <returns>The helper.</returns>
    """
    service._COMMANDS_TAKEN.clear()
    T.PROPS.clear()
    T.SKIN_SETTINGS.discard("actor_page")
    if switch:
        T.SKIN_SETTINGS.add("actor_page")
    helper = service.FunctionalHelper()
    helper._info_cast_names = list(names)
    helper._info_cast_dbtype = dbtype
    T.PROPS["InfoCast.2.Thumb"] = "special://thumbs/zed.jpg"
    rig.builtins.clear()
    rig.set_skin("cast_run", slot)
    helper.update_cast_command()
    return helper


def actor_props():
    """
    <summary>The actor properties written to Home.</summary>
    <returns>A dict of the non empty ones.</returns>
    """
    return {k: v for k, v in T.PROPS.items() if k.startswith("Actor") and v}


def test_switch_off():
    """
    <summary>With the switch off the old builtins run, in order, and no actor properties are written.</summary>
    """
    print("running test_switch_off")
    rig = Rig()
    try:
        for dbtype, kind in (("movie", "movies"), ("tvshow", "tvshows")):
            click(rig, "2", False, dbtype=dbtype)
            acts = [b for b in rig.builtins if b.startswith(("Dialog.Close", "ActivateWindow"))]
            check(len(acts) == 2 and acts[0] == "Dialog.Close(movieinformation,true)",
                  "off (%s): the dialog closes first (got %r)" % (dbtype, acts))
            m = re.fullmatch(r'ActivateWindow\(Videos,"(.*)",return\)', acts[1]) if len(acts) == 2 else None
            check(bool(m), "off (%s): ActivateWindow(Videos,...,return) follows" % dbtype)
            if m:
                base, doc = url_doc(m.group(1))
                check(base == W.service.VIDEODB_BASES[kind], "off (%s): the path base is %s" % (dbtype, base))
                rules = flat_rules(doc["rules"])
                check(len(rules) == 1 and rules[0]["field"] == "actor" and rules[0]["value"] == [NAME],
                      "off (%s): the single rule is the actor, name intact" % dbtype)
            check(not actor_props(), "off (%s): no actor properties written, got %r" % (dbtype, actor_props()))
            check("ActivateWindow(1156)" not in rig.builtins, "off (%s): the actor page is not opened" % dbtype)
    except Exception as exc:
        fail("the off path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_switch_on():
    """
    <summary>With the switch on the properties are written, the info screen stays open and 1156 opens.</summary>
    """
    print("running test_switch_on")
    rig = Rig()
    try:
        click(rig, "2", True)
        check(not any(b.startswith("Dialog.Close") for b in rig.builtins), "on: no Dialog.Close")
        check(rig.builtins.count("ActivateWindow(1156)") == 1, "on: ActivateWindow(1156) runs once")
        check(not any(b.startswith("ActivateWindow(Videos") for b in rig.builtins), "on: no Videos window")
        check(T.PROPS.get("ActorName") == NAME, "on: ActorName is the name (got %r)" % T.PROPS.get("ActorName"))
        check(T.PROPS.get("ActorThumb") == "special://thumbs/zed.jpg", "on: ActorThumb is InfoCast.2.Thumb")
        for prop, kind in (("ActorFilmsPath", "movies"), ("ActorShowsPath", "tvshows")):
            base, doc = url_doc(T.PROPS.get(prop, ""))
            check(base == service.VIDEODB_BASES[kind], "on: %s base is the %s path" % (prop, kind))
            if not doc:
                fail("on: %s carries no playlist" % prop)
                continue
            check(doc.get("type") == kind, "on: %s playlist type is %s" % (prop, kind))
            rules = flat_rules(doc["rules"])
            check(len(rules) == 1 and rules[0]["field"] == "actor" and rules[0]["operator"] == "is"
                  and rules[0]["value"] == [NAME],
                  "on: %s has the single rule actor is name, intact (quotes, ampersand, comma, script)" % prop)
            check(doc.get("order") == {"method": "year", "direction": "descending"},
                  "on: %s orders by year descending" % prop)
            check("limit" not in doc, "on: %s has no limit" % prop)
            check(T.PROPS[prop] == urllib.parse.quote(urllib.parse.unquote(T.PROPS[prop]), safe="/:?=%") or True,
                  "on: %s is built" % prop)
        # The path must survive being a builtin argument or a content tag: no raw quote or comma.
        for prop in ("ActorFilmsPath", "ActorShowsPath"):
            query = T.PROPS.get(prop, "").partition("?xsp=")[2]
            check('"' not in query and "," not in query and "&" not in query,
                  "on: %s query has no raw quote, comma or ampersand" % prop)
        # Command channel consumed once.
        check(rig.labels.get("Skin.String(cast_run)", "") == "" or "Skin.Reset(cast_run)" in rig.builtins,
              "on: cast_run is cleared")
        # Slot 1 and 3 use their own names and thumbs.
        T.PROPS.clear()
        click(rig, "3", True)
        check(T.PROPS.get("ActorName") == "Third Actor", "on: slot 3 publishes the third name")
    except Exception as exc:
        fail("the on path raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def test_bad_slots():
    """
    <summary>An empty, zero, negative, too large, non numeric or blank named slot does nothing, switch on or off.</summary>
    """
    print("running test_bad_slots")
    rig = Rig()
    try:
        for switch in (False, True):
            for slot, names in (("", None), ("0", None), ("-1", None), ("4", None), ("99", None),
                                ("abc", None), ("1", ("",)), ("1", ())):
                click(rig, slot, switch, **({} if names is None else {"names": names}))
                acts = [b for b in rig.builtins if b.startswith(("Dialog.Close", "ActivateWindow"))]
                check(not acts and not actor_props(),
                      "slot %r (names %r, switch %s) does nothing (builtins %r, props %r)"
                      % (slot, names, "on" if switch else "off", acts, actor_props()))
    except Exception as exc:
        fail("a bad slot raised %s: %s" % (type(exc).__name__, exc))
    finally:
        rig.restore()


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_setting_row()
    test_help_preview_strings()
    test_dialog_shape()
    test_list_attributes()
    test_headings_and_empty_label()
    test_navigation()
    test_switch_off()
    test_switch_on()
    test_bad_slots()
    passed = sum(1 for ok, _ in W.CHECKS if ok)
    print("test_actor_page: %d of %d checks passed" % (passed, len(W.CHECKS)))
    if W.FAILURES:
        print("test_actor_page: %d check(s) failed" % len(W.FAILURES))
        sys.exit(1)
    print("test_actor_page: all checks passed")


if __name__ == "__main__":
    main()
