#!/usr/bin/env python3
"""
<summary>
Tests for the start of film badge (roadmap item 18): the service raises
Window(home).Property(start_badge) only for a video start with the switch
on and outside live TV, keeps it up for START_BADGE_SECS from the latest
start and takes it down then, or at once when playback stops, the switch
goes off or a start is turned away, and clears a stale one at start up; the
notification thread only sets a flag; the badge dialog
(Custom_1155_StartBadge.xml) opens only in fullscreen video with the switch
on and the property up, stands down under the OSD, the seek bar and the
info card, takes no focus, and reads the display mode, resolution and age
rating from VideoPlayer.*; the settings row toggles its own switch, has its label and
help line, and leads to and from the row above.
</summary>
<remarks>
No Kodi is needed. The Kodi stubs and the real service.py come from
tests/test_lists_api.py, as in test_lists_service.py; getCondVisibility and
the clock are replaced per test so the timing can be driven. How the badge
looks, and that Kodi sends Player.OnAVStart where this assumes, is the live
check's job. The preview wiring of the row is covered by
test_settings_preview.py with every other row. Exits non zero when a check
fails.

Usage:
    python3 tests/test_start_badge.py
</remarks>
"""

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
GATE = "show_start_badge"
PROP = "start_badge"
FAILURES = []


def fail(msg):
    """
    <summary>Records one failed check and prints it.</summary>
    <param name="msg">What went wrong.</param>
    """
    FAILURES.append(msg)
    print("FAIL: " + msg)


def read(name):
    """
    <summary>Reads one skin XML file as text.</summary>
    <param name="name">The file name under xml/.</param>
    <returns>The text.</returns>
    """
    with open(os.path.join(XML, name), encoding="utf-8") as handle:
        return handle.read()


class Box:
    """
    <summary>The state of a pretend box, as the badge's conditions see it.</summary>
    <remarks>Answers the service's compound conditions term by term, so the
    test fails if a term it relies on is dropped from the code.</remarks>
    """

    def __init__(self):
        """<summary>Switch off, nothing playing, clock at zero.</summary>"""
        self.switch = False
        self.video = False
        self.livetv = False
        self.now = 1000.0

    def cond(self, text):
        """
        <summary>getCondVisibility for "a + b + !c" conditions over the box.</summary>
        <param name="text">The condition.</param>
        <returns>Whether every term holds.</returns>
        """
        terms = {
            "Skin.HasSetting(%s)" % GATE: self.switch,
            "Player.HasVideo": self.video,
            "VideoPlayer.Content(livetv)": self.livetv,
        }
        result = True
        for term in (t.strip() for t in text.split("+")):
            neg = term.startswith("!")
            key = term[1:] if neg else term
            if key not in terms:
                raise AssertionError("the badge asked an unexpected condition: %r" % key)
            result = result and (terms[key] != neg)
        return result


def helper_with(box):
    """
    <summary>A real FunctionalHelper wired to the pretend box and its clock.</summary>
    <param name="box">The Box.</param>
    <returns>The helper.</returns>
    """
    service.xbmc.getCondVisibility = box.cond
    service.time.monotonic = lambda: box.now
    T.PROPS.pop(PROP, None)
    return service.FunctionalHelper()


def start(helper):
    """<summary>Delivers Player.OnAVStart the way Kodi does, then one tick.</summary>"""
    helper.onNotification("xbmc", "Player.OnAVStart", "{}")
    helper.update_start_badge()


def test_service():
    """
    <summary>Drives update_start_badge through a start, the six seconds, a
    stop, the switch going off, a start with the switch off, live TV on its
    own and inside a film's six seconds, a second start re-arming the timer,
    and other player notifications; and checks run() clears a stale badge
    after its start grace.</summary>
    """
    print("running test_service")
    real_cond, real_mono = service.xbmc.getCondVisibility, service.time.monotonic
    try:
        box = Box()
        box.switch, box.video = True, True
        h = helper_with(box)
        h.onNotification("xbmc", "Player.OnAVStart", "{}")
        if T.PROPS.get(PROP):
            fail("the notification thread raised the badge itself")
        h.update_start_badge()
        if T.PROPS.get(PROP) != "1":
            fail("a video start with the switch on did not raise the badge")
        box.now += h.START_BADGE_SECS - 0.25
        h.update_start_badge()
        if T.PROPS.get(PROP) != "1":
            fail("the badge came down before START_BADGE_SECS")
        box.now += 0.5
        h.update_start_badge()
        if T.PROPS.get(PROP):
            fail("the badge stayed up past START_BADGE_SECS")
        if h.START_BADGE_SECS != 6.0:
            fail("START_BADGE_SECS is %r, the help line says a few seconds and the pictures six" % h.START_BADGE_SECS)

        start(h)
        box.video = False
        box.now += 1
        h.update_start_badge()
        if T.PROPS.get(PROP):
            fail("the badge stayed up after playback stopped")

        box.video = True
        start(h)
        box.switch = False
        h.update_start_badge()
        if T.PROPS.get(PROP):
            fail("the badge stayed up after the switch went off")

        start(h)
        if T.PROPS.get(PROP):
            fail("a start with the switch off raised the badge")

        box.switch, box.livetv = True, True
        start(h)
        if T.PROPS.get(PROP):
            fail("a live TV start raised the badge")

        # a film's badge is up, then playback moves to live TV inside the six seconds
        box.livetv = False
        start(h)
        box.livetv = True
        box.now += 1
        start(h)
        if T.PROPS.get(PROP):
            fail("a live TV start inside the six seconds left the film's badge up")

        # a second start inside the six seconds gives a full six from the second
        box.livetv = False
        start(h)
        box.now += 4
        start(h)
        box.now += h.START_BADGE_SECS - 0.5
        h.update_start_badge()
        if T.PROPS.get(PROP) != "1":
            fail("a second start did not re-arm the full six seconds")
        box.now += 1
        h.update_start_badge()
        if T.PROPS.get(PROP):
            fail("the re-armed badge stayed up past its six seconds")

        # with nothing up and the switch on, only Player.OnAVStart raises it
        for method in ("Player.OnStop", "Player.OnPlay", "Player.OnResume", "Player.OnAVChange"):
            h.onNotification("xbmc", method, "{}")
            h.update_start_badge()
            if T.PROPS.get(PROP):
                fail("%s raised the badge" % method)
    finally:
        service.xbmc.getCondVisibility, service.time.monotonic = real_cond, real_mono
    with open(os.path.join(SKIN, "service.py"), encoding="utf-8") as handle:
        src = handle.read()
    if not re.search(r"fast = \((?:.|\n)*?helper\.update_start_badge,(?:.|\n)*?\n    \)\n    slow", src):
        fail("update_start_badge is not in the fast handler list")
    grace = src.index("helper.write_dedication()")
    clear = src.find('getProperty("start_badge")', grace)
    loop = src.index("while not helper.abortRequested():")
    if not grace < clear < loop or '_set_home_property("start_badge", "")' not in src[clear:loop]:
        fail("run() does not clear a badge left up by an earlier service, after the start grace")


def test_badge():
    """
    <summary>Checks the badge dialog, Custom_1155_StartBadge.xml: a dialog
    Kodi opens only in fullscreen video with the switch on and the property
    up, and closes under the OSD, the seek bar and the info card; it has
    nothing that can take focus; it reads the display mode, resolution and
    age rating from VideoPlayer.*; and nothing but the row writes the switch,
    nor anything in the XML the service's property.</summary>
    """
    print("running test_badge")
    root = ET.fromstring(read("Custom_1155_StartBadge.xml"))
    if root.get("id") != "1155" or root.get("type") != "dialog":
        fail("the badge window is not dialog 1155")
    visibles = [v.text for v in root.findall("visible")]
    want = ["Window.IsActive(fullscreenvideo)",
            "Skin.HasSetting(%s) + !String.IsEmpty(Window(home).Property(%s))" % (GATE, PROP),
            "!Window.IsActive(videoosd) + !Window.IsActive(seekbar) + !Window.IsActive(fullscreeninfo)"]
    if visibles != want:
        fail("the badge dialog opens on %s" % visibles)
    kinds = {n.get("type") for n in root.iter("control")}
    if kinds - {"group", "image", "label"}:
        fail("the badge dialog has controls that could take focus: %s" % sorted(kinds - {"group", "image", "label"}))
    labels = [n.findtext("label") for n in root.iter("control") if n.get("type") == "label"]
    for need in ("$VAR[StartBadgeModeLabel]", "$VAR[OsdResolutionLabel]", "$INFO[VideoPlayer.MPAA]"):
        if need not in labels:
            fail("the badge does not show %s" % need)
    modes = [n for n in root.iter("control") if n.get("type") == "group"
             and any(c.findtext("label") == "$VAR[StartBadgeModeLabel]" for c in n.findall("control"))]
    if sorted(m.findtext("visible") for m in modes) != ["!String.IsEmpty(VideoPlayer.VideoResolution)",
                                                        "String.IsEmpty(VideoPlayer.VideoResolution)"]:
        fail("the mode pill should have one place with a resolution and one without")
    for anim in root.findall("animation"):
        if anim.get("condition") != "!Skin.HasSetting(reduce_motion)":
            fail("a badge animation ignores Reduce Motion")
    var = re.search(r'<variable name="StartBadgeModeLabel">(.*?)</variable>', read("Includes.xml"), re.S)
    pairs = var and re.findall(r'<value(?: condition="([^"]*)")?>([^<]*)</value>', var.group(1))
    expected = [("String.IsEqual(VideoPlayer.HdrType,dolbyvision)", "Dolby Vision"),
                ("String.IsEqual(VideoPlayer.HdrType,hdr10)", "HDR10"),
                ("String.IsEqual(VideoPlayer.HdrType,hlg)", "HLG"),
                ("!String.IsEmpty(VideoPlayer.HdrType)", "HDR"),
                ("", "SDR")]
    if pairs != expected:
        fail("StartBadgeModeLabel reads %s" % pairs)
    if PROP in read("VideoFullScreen.xml"):
        fail("VideoFullScreen.xml mentions the badge; it lives in its own dialog")
    for name in sorted(os.listdir(XML)):
        if name.endswith(".xml") and name != "SkinSettings.xml" and \
                re.search(r"Skin\.(SetBool|ToggleSetting|Reset)\(%s[,)]" % GATE, read(name)):
            fail("%s writes %s" % (name, GATE))
        if name.endswith(".xml") and re.search(r"(Set|Clear)Property\(%s\b" % PROP, read(name)):
            fail("%s writes the %s property, which is the service's" % (name, PROP))


def test_row():
    """
    <summary>Checks row 7327 toggles its own switch, has its label and a help
    line with a Where line, sits straight under row 7326 clear of the text
    below, and that the two lead to each other.</summary>
    """
    print("running test_row")
    settings = {n.get("id"): n for n in ET.fromstring(read("SkinSettings.xml")).iter("control") if n.get("id")}
    row, above = settings.get("7327"), settings.get("7326")
    if row is None or above is None:
        fail("row 7326 or 7327 is missing")
        return
    if row.findtext("selected") != "Skin.HasSetting(%s)" % GATE or row.findtext("onclick") != "Skin.ToggleSetting(%s)" % GATE:
        fail("row 7327 does not show and toggle %s" % GATE)
    with open(STRINGS, encoding="utf-8") as handle:
        strings = handle.read()
    if 'msgctxt "#%s"' % row.findtext("label") not in strings:
        fail("row 7327 has no label string")
    help_text = read("Includes_SettingsHelp.xml")
    shown = re.search(r'name="settings_help_shown">(.*)</expression>', help_text)
    if not shown or "Control.HasFocus(7327)" not in shown.group(1):
        fail("settings_help_shown does not list row 7327")
    entry = re.search(r'Control\.HasFocus\(7327\)">\$LOCALIZE\[(\d+)\]', help_text)
    line = entry and re.search(r'msgctxt "#%s"\nmsgid "(.*)"' % entry.group(1), strings)
    if not line or "[CR]Where: " not in line.group(1):
        fail("row 7327 has no help with a Where line")
    if row.findtext("left") != above.findtext("left") or int(row.findtext("top")) != int(above.findtext("top")) + 80:
        fail("row 7327 is not straight under row 7326")
    if int(row.findtext("top")) + int(row.findtext("height")) > 640:
        fail("row 7327 runs into the Playback Buffer heading at y 640")
    if above.findtext("ondown") != "7327" or row.findtext("onup") != "7326":
        fail("rows 7326 and 7327 do not lead to each other")
    if row.findtext("onleft") != "7313" or row.find("onright") is not None or row.find("ondown") is not None:
        fail("row 7327 should go left to 7313 and nowhere right or down")


if __name__ == "__main__":
    test_service()
    test_badge()
    test_row()
    if FAILURES:
        print("test_start_badge: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_start_badge: all checks passed")
