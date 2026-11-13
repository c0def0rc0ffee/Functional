#!/usr/bin/env python3
"""
<summary>
Tests for roadmap item 34, the studio or network logo on the information screens.
</summary>
<remarks>
No Kodi is needed. The strings, the settings row, the help and preview wiring, the
information dialog's image control and the off state are read from the XML and the
string table. The service half drives the real fast ticker method
<c>update_info_studio</c> with stubbed labels, conditions, dialogs, builtins and
JSON-RPC, and checks the property it publishes and every branch of the install,
enable, leave, disable and uninstall offer. The rule behind the offer is that nothing
ever installs or enables the pack unless the viewer said yes. Written from the
specification alone. Exits non zero when a check fails.

Usage:
    python3 tests/test_studio_logo.py
</remarks>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_lists_api as T  # noqa: E402  (installs the Kodi stubs, imports service)
import test_watchlist as W  # noqa: E402  (the Rig and the condition evaluator)

service = T.service
XML = W.XML
ADDON = "resource.images.studios.white"
SWITCH = "show_studio_logo"
FAILURES = W.FAILURES
CHECKS = W.CHECKS
check = W.check
fail = W.fail


def text_of(sid):
    """
    <summary>The English text of a string id.</summary>
    <param name="sid">The string id.</param>
    <returns>The text, or an empty string when it is missing.</returns>
    """
    return T.STRINGS.get(sid, "")


# ---- Strings, XML wiring and the off state -----------------------------------

def test_strings():
    """
    <summary>Strings 31922 to 31932 exist once each and are not empty, and the
    help string 31932 carries a Where: line.</summary>
    """
    print("running test_strings")
    po = W.read(W.STRINGS)
    for sid in range(31922, 31933):
        check(bool(text_of(sid)), "string %d is missing or empty" % sid)
        check(po.count('msgctxt "#%d"' % sid) == 1, "string %d should be defined exactly once" % sid)
    check("Where:" in text_of(31932), "the help string 31932 should carry a Where: line")
    check(text_of(31928) == "Leave it", "31928 should read Leave it, got %r" % text_of(31928))
    check(text_of(31929) == "Disable it", "31929 should read Disable it, got %r" % text_of(31929))
    check(text_of(31930) == "Uninstall it", "31930 should read Uninstall it, got %r" % text_of(31930))


def test_settings_row():
    """
    <summary>Radiobutton 7213 on the Library page: label 31922, selected by the
    setting, and the two onclicks in the stated order.</summary>
    """
    print("running test_settings_row")
    root = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    row = W.find_control(root, "7213")
    if not check(row is not None, "SkinSettings.xml should hold control 7213"):
        return
    check(row.get("type") == "radiobutton", "7213 should be a radiobutton, got %r" % row.get("type"))
    check(row.findtext("label") == "31922", "7213 label should be 31922, got %r" % row.findtext("label"))
    check(row.findtext("selected") == "Skin.HasSetting(%s)" % SWITCH,
          "7213 should be selected by the setting, got %r" % row.findtext("selected"))
    clicks = [o.text for o in row.findall("onclick")]
    # STUDIO-LOGO-FIX (review of 13/11/2026): the press names the state it
    # leads to, each line read before the toggle runs, then toggles.
    conds = [(o.get("condition"), o.text) for o in row.findall("onclick")]
    check(conds == [("Skin.HasSetting(%s)" % SWITCH, "Skin.SetString(studio_command,off)"),
                    ("!Skin.HasSetting(%s)" % SWITCH, "Skin.SetString(studio_command,on)"),
                    (None, "Skin.ToggleSetting(%s)" % SWITCH)],
          "7213 onclicks should send off or on for the state it leads to, then toggle, got %r" % conds)
    parents = {child: parent for parent in root.iter() for child in parent}
    node, page = row, None
    while node in parents:
        node = parents[node]
        if node.tag == "control" and node.findtext("visible"):
            page = node.findtext("visible")
            break
    check(page == "String.IsEqual(Skin.String(settings_category),media)",
          "7213 should sit on the Library page (category media), got %r" % page)
    count = sum(1 for c in root.iter("control") if c.get("id") == "7213")
    check(count == 1, "control id 7213 should be used once, found %d" % count)


def test_settings_row_usable():
    """
    <summary>Beyond the letter of the spec but needed for the row to work: it has
    its own position, as its neighbours in the page group do, and some control
    leads focus to it.</summary>
    """
    print("running test_settings_row_usable")
    root = ET.parse(os.path.join(XML, "SkinSettings.xml")).getroot()
    row = W.find_control(root, "7213")
    if row is None:
        return
    parents = {child: parent for parent in root.iter() for child in parent}
    in_list = parents.get(row) is not None and parents[row].get("type") == "grouplist"
    check(in_list or (bool(row.findtext("left")) and bool(row.findtext("top"))),
          "7213 is neither in a grouplist nor placed, so it would draw at the corner of its group "
          "(left=%r top=%r)" % (row.findtext("left"), row.findtext("top")))
    reached = in_list  # a grouplist moves the focus between its own rows
    for control in root.iter("control"):
        for tag in ("onup", "ondown", "onleft", "onright"):
            if control.get("id") != "7213" and control.findtext(tag) == "7213":
                reached = True
    check(reached, "no control moves focus to 7213 with up, down, left or right, so the row cannot be reached")


def test_help_and_preview():
    """
    <summary>The help string is mapped for 7213 and the id is in
    settings_help_shown; the preview form is None, so 7213 is in
    settings_preview_none only.</summary>
    """
    print("running test_help_and_preview")
    help_root = ET.parse(os.path.join(XML, "Includes_SettingsHelp.xml")).getroot()
    values = [v for v in help_root.iter("value") if v.get("condition") == "Control.HasFocus(7213)"]
    check(len(values) == 1 and (values[0].text or "").strip() == "$LOCALIZE[31932]",
          "the help map should map 7213 to $LOCALIZE[31932] exactly once")
    shown = W.EXPRESSIONS.get("settings_help_shown", "")
    check(re.search(r"Control\.HasFocus\(7213\)", shown) is not None, "7213 should be in settings_help_shown")
    for name in ("settings_preview_none", "settings_preview_image", "settings_preview_image_toggle"):
        has = re.search(r"Control\.HasFocus\(7213\)", W.EXPRESSIONS.get(name, "")) is not None
        check(has == (name == "settings_preview_none"),
              "7213 should %sbe in %s" % ("" if name == "settings_preview_none" else "not ", name))
    for name, body in W.EXPRESSIONS.items():
        if name.startswith("settings_preview") and name not in (
                "settings_preview_none", "settings_preview_image", "settings_preview_image_toggle"):
            check("Control.HasFocus(7213)" not in body, "7213 should not be in %s" % name)


def info_image():
    """
    <summary>The studio image control in the information dialog.</summary>
    <returns>The element, or None.</returns>
    """
    root = ET.parse(os.path.join(XML, "DialogVideoInfo.xml")).getroot()
    found = [c for c in root.iter("control") if "InfoStudio" in ET.tostring(c, encoding="unicode")
             and c.get("type") == "image"]
    return found, root


def pack_env_true(term, switch, installed, enabled, prop):
    """
    <summary>Evaluates one term of the image's visible condition.</summary>
    <param name="term">One term, without a leading bang.</param>
    <param name="switch">Whether the switch is on.</param>
    <param name="installed">Whether the pack is installed.</param>
    <param name="enabled">Whether the pack is enabled.</param>
    <param name="prop">The InfoStudio property text.</param>
    <returns>True or False.</returns>
    <exception cref="ValueError">When the term is not one the spec names.</exception>
    """
    if term == "Skin.HasSetting(%s)" % SWITCH:
        return switch
    if term == "System.HasAddon(%s)" % ADDON:
        return installed
    if term == "System.AddonIsEnabled(%s)" % ADDON:
        return enabled
    if term == "String.IsEmpty(Window(home).Property(InfoStudio))":
        return not prop
    raise ValueError("term not understood: " + term)


def visible_now(cond, switch, installed, enabled, prop):
    """
    <summary>Evaluates a visible condition made only of plus joined terms.</summary>
    <param name="cond">The condition.</param>
    <param name="switch">Whether the switch is on.</param>
    <param name="installed">Whether the pack is installed.</param>
    <param name="enabled">Whether the pack is enabled.</param>
    <param name="prop">The InfoStudio property text.</param>
    <returns>True or False.</returns>
    """
    result = True
    for part in cond.split("+"):
        part = part.strip()
        negate = part.startswith("!")
        value = pack_env_true(part.lstrip("!").strip(), switch, installed, enabled, prop)
        result = result and (not value if negate else value)
    return result


def test_info_image():
    """
    <summary>One image control draws the pack's picture for the property, at left
    1640, top 70, 240 by 100, clear of the title, visible only with the switch,
    the add-on installed and enabled, and a non empty property.</summary>
    """
    print("running test_info_image")
    found, root = info_image()
    if not check(len(found) == 1, "DialogVideoInfo.xml should hold exactly one studio image control, found %d" % len(found)):
        return
    img = found[0]
    texture = (img.findtext("texture") or "").strip()
    check(texture == "resource://%s/$INFO[Window(home).Property(InfoStudio)].png" % ADDON,
          "texture should come from the pack for the property, got %r" % texture)
    for tag, want in (("left", "1640"), ("top", "70"), ("width", "240"), ("height", "100")):
        check(img.findtext(tag) == want, "%s should be %s, got %r" % (tag, want, img.findtext(tag)))
    cond = img.findtext("visible") or ""
    for needle in ("Skin.HasSetting(%s)" % SWITCH, "System.HasAddon(%s)" % ADDON,
                   "System.AddonIsEnabled(%s)" % ADDON, "Window(home).Property(InfoStudio)"):
        check(needle in cond, "the visible condition should name %s" % needle)
    try:
        for switch in (False, True):
            for installed in (False, True):
                for enabled in (False, True):
                    for prop in ("", "A24"):
                        want = switch and installed and enabled and bool(prop)
                        got = visible_now(cond, switch, installed, enabled, prop)
                        check(got == want, "visible with switch=%s installed=%s enabled=%s property=%r should be %s"
                              % (switch, installed, enabled, prop, want))
    except ValueError as exc:
        fail("visible condition: %s" % exc)
    # The title stops at 1620: the image must start at or after that.
    check(int(img.findtext("left") or "0") >= 1620, "the image should start clear of the title, which stops at 1620")


def test_off_state():
    """
    <summary>With the switch off nothing new draws and nothing else switches the
    setting on: the only studio image needs the switch, and no file but the
    settings row sets it.</summary>
    """
    print("running test_off_state")
    found, _root = info_image()
    for img in found:
        check(not visible_now(img.findtext("visible") or "", False, True, True, "A24"),
              "the studio image should never draw with the switch off")
    skin = os.path.dirname(XML)
    for folder, _dirs, files in os.walk(skin):
        for name in files:
            if name.endswith((".xml", ".py", ".po")):
                body = W.read(os.path.join(folder, name))
                check("SetBool(%s" % SWITCH not in body, "%s should not switch the studio logo on" % name)
                if name not in ("SkinSettings.xml", "service.py", "DialogVideoInfo.xml",
                                "Includes_SettingsHelp.xml", "Includes_SettingsPreview.xml"):
                    check("ToggleSetting(%s" % SWITCH not in body, "%s should not toggle the studio logo" % name)
    check(SWITCH not in W.read(os.path.join(skin, "addon.xml")), "addon.xml should not name the switch")


# ---- The service ---------------------------------------------------------------

class StudioRig(W.Rig):
    """<summary>The shared rig with the pack, the information window and the dialogs added.</summary>"""

    def __init__(self):
        """<summary>Install the stubs and the extra state.</summary>"""
        super().__init__()
        self.installed = False
        self.enabled = False
        self.active = True
        self.yes = False
        self.yesnos = []
        self.selects = []
        self.old_yesno = T._Dialog.yesno
        self.writes = []
        self.old_set = T._Window.setProperty
        self.old_clear = T._Window.clearProperty
        rig = self

        def set_prop(win, key, value):
            """<summary>Count a write of the studio property.</summary><param name="win">The window.</param>
            <param name="key">Property name.</param><param name="value">Its text.</param>"""
            if key == "InfoStudio":
                rig.writes.append(("set", value))
            rig.old_set(win, key, value)

        def clear_prop(win, key):
            """<summary>Count a clear of the studio property.</summary><param name="win">The window.</param>
            <param name="key">Property name.</param>"""
            if key == "InfoStudio":
                rig.writes.append(("clear", ""))
            rig.old_clear(win, key)

        def yesno(_self, *args, **kwargs):
            """<summary>Record the question and answer as the viewer would.</summary>
            <returns>The rig's answer.</returns>"""
            rig.yesnos.append(args + tuple(kwargs.values()))
            return rig.yes

        T._Dialog.yesno = yesno
        T._Window.setProperty = set_prop
        T._Window.clearProperty = clear_prop

    def restore(self):
        """<summary>Put every stub back.</summary>"""
        T._Dialog.yesno = self.old_yesno
        T._Window.setProperty = self.old_set
        T._Window.clearProperty = self.old_clear
        super().restore()

    def cond(self, text):
        """
        <summary>getCondVisibility with the pack and the information window added.</summary>
        <param name="text">The condition.</param>
        <returns>True when it holds in the rig's state.</returns>
        """
        if text == "System.HasAddon(%s)" % ADDON:
            return self.installed
        if text == "System.AddonIsEnabled(%s)" % ADDON:
            return self.installed and self.enabled
        if text == "Window.IsActive(movieinformation)":
            return self.active
        return super().cond(text)

    def select(self, heading, items, *_a, **_kw):
        """
        <summary>Record the select dialog and answer with the rig's pick.</summary>
        <param name="heading">The dialog title.</param>
        <param name="items">The lines offered.</param>
        <returns>The chosen index, or minus one for a cancel.</returns>
        """
        self.selects.append((heading, list(items)))
        return self.pick

    def jsonrpc(self, method, params=None):
        """
        <summary>Record the call and answer an add-on detail query from the rig's state.</summary>
        <param name="method">JSON-RPC method.</param>
        <param name="params">Its parameters.</param>
        <returns>A reply shaped as Kodi's.</returns>
        """
        if method == "Addons.GetAddonDetails":
            self.rpc.append((method, params or {}))
            if not self.installed:
                return {"error": {"code": -32602, "message": "Invalid params."}}
            return {"result": {"addon": {"addonid": ADDON, "enabled": self.enabled, "installed": True}}}
        return super().jsonrpc(method, params)

    def tick(self, helper):
        """
        <summary>Run one fast ticker pass with the clock moved on.</summary>
        <param name="helper">The FunctionalHelper.</param>
        """
        self.clock.now += 11
        helper.update_info_studio()

    def offer(self, helper, switch, installed, enabled, yes=False, pick=-1):
        """
        <summary>Press the row once: set the switch and the pack, send the command and tick.</summary>
        <param name="helper">The FunctionalHelper.</param>
        <param name="switch">The switch state after the press.</param>
        <param name="installed">Whether the pack is installed.</param>
        <param name="enabled">Whether it is enabled.</param>
        <param name="yes">The answer to any yes or no.</param>
        <param name="pick">The index chosen in any select, minus one to cancel.</param>
        """
        self.builtins.clear()
        self.rpc.clear()
        self.yesnos.clear()
        self.selects.clear()
        T._Dialog.toasts = []
        T.SKIN_SETTINGS.discard(SWITCH)
        if switch:
            T.SKIN_SETTINGS.add(SWITCH)
        self.installed, self.enabled, self.yes, self.pick = installed, enabled, yes, pick
        self.set_skin("studio_command", "")
        self.tick(helper)
        self.set_skin("studio_command", "on" if switch else "off")
        self.tick(helper)

    def installs(self):
        """<summary>The InstallAddon builtins so far.</summary><returns>A list.</returns>"""
        return [b for b in self.builtins if b.startswith("InstallAddon(")]

    def enables(self):
        """<summary>The SetAddonEnabled calls so far.</summary><returns>A list of parameter dicts.</returns>"""
        return [p for m, p in self.rpc if m == "Addons.SetAddonEnabled"]

    def mentions(self, args, sid):
        """
        <summary>Whether recorded dialog arguments carry a string, as its id or its text.</summary>
        <param name="args">The arguments of one call.</param>
        <param name="sid">The string id.</param>
        <returns>True when it is present.</returns>
        """
        flat = list(args) if isinstance(args, (list, tuple)) else [args]
        return any(a == sid or a == str(sid) or a == text_of(sid) for a in flat)


def guarded(fn):
    """
    <summary>Runs one service test, reporting a crash as a finding and always restoring the stubs.</summary>
    <param name="fn">The test body, taking the rig and a helper.</param>
    """
    rig = StudioRig()
    try:
        fn(rig, service.FunctionalHelper())
    except Exception as exc:  # a crash is a finding, reported rather than hidden
        fail("%s raised %s: %s" % (fn.__name__, type(exc).__name__, exc))
    finally:
        rig.restore()


def nothing_installed_or_enabled(rig, what):
    """
    <summary>Checks that no install or enable call happened.</summary>
    <param name="rig">The rig.</param>
    <param name="what">The scenario, for the message.</param>
    """
    check(not rig.installs(), "%s: nothing should install, got %r" % (what, rig.installs()))
    check(not rig.enables(), "%s: nothing should be enabled or disabled, got %r" % (what, rig.enables()))


def body_property(rig, helper):
    """
    <summary>The property tests, sharing one rig.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The FunctionalHelper.</param>
    """
    T.SKIN_SETTINGS.add(SWITCH)
    rig.active = True
    rig.labels["ListItem.Studio"] = "Warner Bros. / Legendary Pictures"
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio") == "Warner Bros.",
          "several studios should publish the first, got %r" % T.PROPS.get("InfoStudio"))
    rig.writes.clear()
    rig.tick(helper)
    rig.tick(helper)
    check(rig.writes == [], "an unchanged studio should cause no writes, got %r" % rig.writes)
    rig.labels["ListItem.Studio"] = "  A24  "
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio") == "A24", "spaces should be stripped, got %r" % T.PROPS.get("InfoStudio"))
    check(len(rig.writes) == 1, "a change should write once, got %r" % rig.writes)
    rig.labels["ListItem.Studio"] = "HBO"
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio") == "HBO", "a new studio should replace the old, got %r" % T.PROPS.get("InfoStudio"))
    rig.labels["ListItem.Studio"] = "Pixar/Disney"
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio") in ("Pixar/Disney", "Pixar"),
          "a studio with no spaced separator should not be mangled, got %r" % T.PROPS.get("InfoStudio"))
    rig.labels["ListItem.Studio"] = "HBO"
    rig.tick(helper)
    # The information window closes.
    rig.active = False
    rig.writes.clear()
    rig.tick(helper)
    check("InfoStudio" not in T.PROPS or T.PROPS.get("InfoStudio") == "",
          "closing the window should clear the property, got %r" % T.PROPS.get("InfoStudio"))
    rig.writes.clear()
    rig.tick(helper)
    rig.tick(helper)
    check(rig.writes == [], "an already clear property should not be cleared again, got %r" % rig.writes)
    # Back in the window, then the switch goes off.
    rig.active = True
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio") == "HBO", "reopening the window should publish again, got %r" % T.PROPS.get("InfoStudio"))
    T.SKIN_SETTINGS.discard(SWITCH)
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio", "") == "", "switching off should clear the property, got %r" % T.PROPS.get("InfoStudio"))
    # Off from the start publishes nothing.
    rig.writes.clear()
    rig.labels["ListItem.Studio"] = "Sony"
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio", "") == "", "with the switch off nothing should publish, got %r" % T.PROPS.get("InfoStudio"))
    check(not [w for w in rig.writes if w[0] == "set"], "with the switch off nothing should be written, got %r" % rig.writes)
    # On, but the studio is empty.
    T.SKIN_SETTINGS.add(SWITCH)
    rig.labels["ListItem.Studio"] = ""
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio", "") == "", "an item with no studio should leave the property empty")
    rig.labels["ListItem.Studio"] = "Sony"
    rig.tick(helper)
    rig.labels["ListItem.Studio"] = ""
    rig.tick(helper)
    check(T.PROPS.get("InfoStudio", "") == "", "a studio that goes away should clear the property")
    nothing_installed_or_enabled(rig, "publishing the property")


def test_property():
    """
    <summary>The property: first studio, spaces stripped, only with the switch on
    and the information window up, cleared otherwise, written only on a change.</summary>
    """
    print("running test_property")
    guarded(body_property)


def body_not_installed(rig, helper):
    """
    <summary>Switch on, pack not installed: ask, install only on yes.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    rig.offer(helper, True, False, False, yes=True)
    check(len(rig.yesnos) == 1, "a yes/no should be asked once, got %d" % len(rig.yesnos))
    if rig.yesnos:
        check(rig.mentions(rig.yesnos[0], 31923), "the heading should be string 31923, got %r" % (rig.yesnos[0],))
        check(rig.mentions(rig.yesnos[0], 31924), "the text should be string 31924, got %r" % (rig.yesnos[0],))
    check(rig.installs() == ["InstallAddon(%s)" % ADDON], "yes should run InstallAddon for the pack, got %r" % rig.installs())
    check(not rig.enables(), "yes to an install should not call SetAddonEnabled, got %r" % rig.enables())
    check(not rig.windows(), "yes to an install should open no window, got %r" % rig.windows())
    rig.offer(helper, True, False, False, yes=False)
    check(len(rig.yesnos) == 1, "a no run should still ask once, got %d" % len(rig.yesnos))
    nothing_installed_or_enabled(rig, "no to the install")
    check(any(rig.mentions(t, 31925) for t in T._Dialog.toasts),
          "no should show the notification 31925, got %r" % (T._Dialog.toasts,))


def test_offer_install():
    """
    <summary>Switch on, pack not installed: a yes/no with 31923 and 31924; yes
    runs InstallAddon; no shows 31925 and installs nothing.</summary>
    """
    print("running test_offer_install")
    guarded(body_not_installed)


def body_disabled(rig, helper):
    """
    <summary>Switch on, pack installed but disabled: ask, enable only on yes.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    rig.offer(helper, True, True, False, yes=True)
    check(len(rig.yesnos) == 1, "a yes/no should be asked once, got %d" % len(rig.yesnos))
    if rig.yesnos:
        check(rig.mentions(rig.yesnos[0], 31926), "the text should be string 31926, got %r" % (rig.yesnos[0],))
    check(rig.enables() == [{"addonid": ADDON, "enabled": True}],
          "yes should enable the pack by JSON-RPC, got %r" % rig.enables())
    check(not rig.installs(), "enabling should not install, got %r" % rig.installs())
    rig.offer(helper, True, True, False, yes=False)
    check(len(rig.yesnos) == 1, "a no run should still ask once, got %d" % len(rig.yesnos))
    nothing_installed_or_enabled(rig, "no to the enable")


def test_offer_enable():
    """
    <summary>Switch on, pack installed but disabled: a yes/no 31926; yes calls
    Addons.SetAddonEnabled true; no does nothing.</summary>
    """
    print("running test_offer_enable")
    guarded(body_disabled)


def body_quiet(rig, helper):
    """
    <summary>The two states that show no dialog.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    rig.offer(helper, True, True, True, yes=True, pick=2)
    check(not rig.yesnos and not rig.selects, "switch on with the pack enabled should show no dialog")
    nothing_installed_or_enabled(rig, "switch on, pack enabled")
    check(not rig.windows(), "switch on, pack enabled: no window should open")
    rig.offer(helper, False, False, False, yes=True, pick=2)
    check(not rig.yesnos and not rig.selects, "switch off with no pack should show no dialog")
    nothing_installed_or_enabled(rig, "switch off, pack not installed")
    check(not rig.windows(), "switch off, pack not installed: no window should open")
    check(not T._Dialog.toasts, "switch off, pack not installed: no notification, got %r" % (T._Dialog.toasts,))


def test_offer_no_dialog():
    """
    <summary>Switch on with the pack enabled, and switch off with the pack not
    installed, show no dialog and do nothing.</summary>
    """
    print("running test_offer_no_dialog")
    guarded(body_quiet)


def body_off_installed(rig, helper):
    """
    <summary>Switch off, pack installed: the three way select and each answer.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    for enabled in (True, False):
        state = "enabled" if enabled else "disabled"
        rig.offer(helper, False, True, enabled, yes=True, pick=0)
        check(len(rig.selects) == 1, "a select should open once with the pack %s, got %d" % (state, len(rig.selects)))
        check(not rig.yesnos, "switch off should use a select, not a yes/no")
        if rig.selects:
            heading, items = rig.selects[0]
            check(heading in (31927, str(31927), text_of(31927)), "the heading should be 31927, got %r" % (heading,))
            want = [text_of(31928), text_of(31929), text_of(31930)]
            ids = [31928, 31929, 31930]
            check(items == want or items == ids or items == [str(i) for i in ids],
                  "the lines should be Leave it, Disable it, Uninstall it, got %r" % (items,))
        nothing_installed_or_enabled(rig, "Leave it, pack %s" % state)
        check(not rig.windows(), "Leave it (%s) should open no window, got %r" % (state, rig.windows()))
        check(not T._Dialog.toasts, "Leave it (%s) should show no notification, got %r" % (state, T._Dialog.toasts))

        rig.offer(helper, False, True, enabled, yes=True, pick=1)
        check(rig.enables() == [{"addonid": ADDON, "enabled": False}],
              "Disable it (%s) should call SetAddonEnabled false, got %r" % (state, rig.enables()))
        check(not rig.installs() and not rig.windows(), "Disable it (%s) should do nothing else" % state)

        rig.offer(helper, False, True, enabled, yes=False, pick=2)
        want_window = "ActivateWindow(addonbrowser,addons://user/kodi.resource.images/,return)"
        check(want_window in rig.builtins, "Uninstall it (%s) should open the add-on browser, got %r" % (state, rig.builtins))
        check(any(rig.mentions(t, 31931) for t in T._Dialog.toasts),
              "Uninstall it (%s) should show notification 31931, got %r" % (state, T._Dialog.toasts))
        nothing_installed_or_enabled(rig, "Uninstall it, pack %s" % state)

        for cancel in (-1,):
            rig.offer(helper, False, True, enabled, yes=True, pick=cancel)
            check(len(rig.selects) == 1, "a cancel run should still open the select once")
            nothing_installed_or_enabled(rig, "cancel, pack %s" % state)
            check(not rig.windows(), "cancel (%s) should open no window, got %r" % (state, rig.windows()))
            check(not T._Dialog.toasts, "cancel (%s) should show no notification, got %r" % (state, T._Dialog.toasts))


def test_offer_leave_disable_uninstall():
    """
    <summary>Switch off, pack installed: select 31927 of Leave it, Disable it and
    Uninstall it; leave does nothing, disable calls SetAddonEnabled false,
    uninstall opens the add-on browser and notifies 31931, cancel does nothing.</summary>
    """
    print("running test_offer_leave_disable_uninstall")
    guarded(body_off_installed)


def body_command_once(rig, helper):
    """
    <summary>The command is taken once, and a command other than on or off does nothing.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    T.SKIN_SETTINGS.add(SWITCH)
    rig.installed = rig.enabled = False
    rig.yes = True
    rig.set_skin("studio_command", "on")
    rig.tick(helper)
    rig.tick(helper)
    check(len(rig.yesnos) == 1, "one press should ask once even over two ticks, got %d" % len(rig.yesnos))
    check(len(rig.installs()) <= 1, "one press should install at most once, got %r" % rig.installs())
    rig.yesnos.clear()
    rig.builtins.clear()
    rig.set_skin("studio_command", "")
    rig.tick(helper)
    rig.set_skin("studio_command", "somethingelse")
    rig.tick(helper)
    check(not rig.yesnos and not rig.installs(), "an unknown command value should do nothing")
    rig.set_skin("studio_command", "")
    rig.tick(helper)
    check(not rig.yesnos and not rig.installs(), "no command should mean no dialog")


def test_command_channel():
    """
    <summary>The on or off command runs the offer once, other values and an empty
    channel do nothing.</summary>
    """
    print("running test_command_channel")
    guarded(body_command_once)


class Busy:
    """<summary>A dialog thread that is still running.</summary>"""

    def is_alive(self):
        """<summary>Still running.</summary><returns>True.</returns>"""
        return True

    def join(self, *_a, **_kw):
        """<summary>Nothing to wait for.</summary>"""


def body_slot(rig, helper):
    """
    <summary>The offer uses the skin's single dialog slot.</summary>
    <param name="rig">The rig.</param>
    <param name="helper">The helper.</param>
    """
    helper._dialog_thread = Busy()
    rig.offer(helper, True, False, False, yes=True)
    check(not rig.yesnos and not rig.selects, "while another dialog is open the offer should not stack a second")
    nothing_installed_or_enabled(rig, "dialog slot busy")


def test_dialog_slot():
    """
    <summary>With the single dialog slot taken, the offer opens no second dialog
    and changes nothing.</summary>
    """
    print("running test_dialog_slot")
    guarded(body_slot)


def main():
    """<summary>Runs every test and exits non zero on a failure.</summary>"""
    test_strings()
    test_settings_row()
    test_settings_row_usable()
    test_help_and_preview()
    test_info_image()
    test_off_state()
    test_property()
    test_offer_install()
    test_offer_enable()
    test_offer_no_dialog()
    test_offer_leave_disable_uninstall()
    test_command_channel()
    test_dialog_slot()
    passed = sum(1 for ok, _ in CHECKS if ok)
    print("test_studio_logo: %d of %d checks passed" % (passed, len(CHECKS)))
    if FAILURES:
        print("test_studio_logo: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_studio_logo: all checks passed")


if __name__ == "__main__":
    main()
