#!/usr/bin/env python3
"""
<summary>
Makes the settings preview pictures (roadmap item 47, sub item 4): for every
Skin Settings row whose effect is on a screen the live stage cannot draw, one
picture per value the setting can hold, taken from the local Kodi with the
value set, cropped to the part of the screen the setting changes, and
scaled to the 360 by 203 preview panel. Written under
skin.functional/media/preview/ as <setting>_<value>.png.
</summary>
<remarks>
Drives Kodi through its event server on loopback UDP 9777 (builtins and
keypresses; no web server needed) and reads nothing back except the
screenshots TakeScreenshot writes. Needs Kodi running on this machine with
skin.functional live, a library with movies in it for the gallery and info
screen pictures, and ffmpeg for a silent test clip the player pictures play,
so no real film is ever played or marked.

Every setting the table touches is read from the helper's own settings
backup (special://profile/addon_data/skin.functional/backups/settings-backup.xml,
kept up to date by the helper) before the run and put back afterwards, so
the user's choices survive. The background is set to a backdrop drawn in
the skin's own style for the run, never library art (Rob's rule: the
pictures ship and must be fit for everyone). Nothing is deleted: a picture
that already exists is overwritten only by its own new version.

PICTURES is the one table of picture rows, shared with
tests/test_settings_preview.py, which checks every row in the preview map
has its pictures and every picture a row.

Usage:
    python3 build_preview_art.py            make every picture
    python3 build_preview_art.py 7303 7305  only these rows
    python3 build_preview_art.py --list     print the table and stop
</remarks>
"""

import glob
import json
import os
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # pragma: no cover
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
SKIN = os.path.join(HERE, "skin.functional")
OUT = os.path.join(SKIN, "media", "preview")
KODI_HOME = os.path.expanduser("~/.kodi")
BACKUP = os.path.join(KODI_HOME, "userdata", "addon_data", "skin.functional", "backups", "settings-backup.xml")
PANEL = (360, 203)
HOST, PORT = "127.0.0.1", 9777
MOVIES = "videodb://movies/titles/"

# ---- the table --------------------------------------------------------------
# Each entry: the Skin Settings row, the setting it writes, its kind ("toggle"
# or "picker"), the values a picker holds ("" is the default, pictured as
# "default"), the screen to show, and the crop in 1920 by 1080 screen units.
# Toggles are pictured as "on" and "off", the state of the setting itself.
# Screens: "sample" is a folder of neutral sample films the run makes itself
# (the user's posters never ship); "library" is the user's movie library
# cropped to field text alone, and "libraryfilter" its side menu cropped to
# the filter rows. A "mask" lists areas painted over before the picture is
# scaled. Two rows have no picture and are named as having no preview in the
# map: show_lastplayed (7207), since nothing a run can set up has been
# played, and hide_media_age (7316), since the info screen always draws the
# focused film's own fanart behind the line and no picture of it can be
# taken that does not ship a slice of the user's library.
GALLERY, INFOBAR_LEFT, INFOBAR_RIGHT = (0, 0, 1920, 1080), (0, 960, 640, 120), (1120, 960, 800, 120)
# settings the pictured screens depend on without being pictured; reset to
# default for the run like the pictured ones (the small grid column count
# sets how many posters a gallery row holds)
BASELINE = ("small_cols",)
OSD = (0, 740, 1920, 340)
PICTURES = [
    # Library page
    {"row": "7220", "setting": "gallery_size", "kind": "picker", "values": ["", "small", "large", "xlarge"], "screen": "sample", "crop": GALLERY},
    {"row": "7222", "setting": "compact_posters", "kind": "toggle", "screen": "sample", "crop": GALLERY},
    {"row": "7318", "setting": "rounded_corners", "kind": "toggle", "screen": "sample", "crop": (0, 0, 960, 540)},
    {"row": "7223", "setting": "context_menu_pos", "kind": "picker", "values": ["", "left"], "screen": "samplecontext", "crop": GALLERY},
    {"row": "7224", "setting": "library_collections", "kind": "toggle", "screen": "libraryfilter", "crop": (0, 400, 420, 360)},
    {"row": "7200", "setting": "infobar_top", "kind": "toggle", "screen": "sample", "crop": GALLERY},
    {"row": "7201", "setting": "hide_genre", "kind": "toggle", "screen": "library", "crop": INFOBAR_RIGHT},
    {"row": "7202", "setting": "hide_duration", "kind": "toggle", "screen": "sample", "crop": INFOBAR_LEFT},
    {"row": "7203", "setting": "hide_rating", "kind": "toggle", "screen": "library", "crop": (0, 1027, 640, 53)},
    {"row": "7204", "setting": "hide_mpaa", "kind": "toggle", "screen": "library", "crop": INFOBAR_RIGHT},
    {"row": "7205", "setting": "hide_resolution", "kind": "toggle", "screen": "sample", "crop": INFOBAR_RIGHT},
    # "item" picks which title of the list is focused, counted from the top; the
    # age row needs one released over a year ago, since newer titles show no
    # age by design, and in this library the first two are this year's
    {"row": "7206", "setting": "show_age", "kind": "toggle", "screen": "library", "crop": (0, 1027, 700, 53), "settle": 4, "item": 3},
    {"row": "7209", "setting": "hide_endsat", "kind": "toggle", "screen": "sample", "crop": INFOBAR_LEFT},
    # Playback page
    {"row": "7302", "setting": "osd_position", "kind": "picker", "values": ["", "top"], "screen": "osd", "crop": GALLERY, "reload": True},
    {"row": "7303", "setting": "hide_osd_thumb", "kind": "toggle", "screen": "osd", "crop": OSD, "settle": 3},
    {"row": "7304", "setting": "video_dim", "kind": "picker", "values": ["", "0", "25", "50", "90"], "screen": "videosettings", "crop": GALLERY},
    {"row": "7305", "setting": "hide_osd_buffer", "kind": "toggle", "screen": "osd", "crop": OSD},
    {"row": "7313", "setting": "hide_osd_fullbuffer", "kind": "toggle", "screen": "osd", "crop": OSD},
    # Rows from the Home Screen, Background and Overall pages
    {"row": "7115", "setting": "hide_loading", "kind": "toggle", "screen": "startup", "crop": GALLERY},
    {"row": "7141", "setting": "hide_sleep_timer", "kind": "toggle", "screen": "powermenu", "crop": (560, 240, 800, 450)},
    {"row": "7142", "setting": "hide_sleep_countdown", "kind": "toggle", "screen": "osdsleep", "crop": (1340, 870, 580, 100)},
    {"row": "7133", "setting": "bg_all_windows", "kind": "toggle", "screen": "sample", "crop": GALLERY},
    # "alike" names value pairs known to look the same in the picture: the default
    # dim is 75%, and over the skin's dark backdrop the 50, 60, 75 and 90 steps
    # move a pixel a few levels at most, so the test does not demand those
    # pairs differ (each picture is still the true result of its value)
    {"row": "7134", "setting": "bg_windows_dim", "kind": "picker", "values": ["", "0", "25", "50", "60", "90"], "screen": "gallerybg", "crop": GALLERY, "alike": [("", "60"), ("", "90"), ("50", "60"), ("50", "90"), ("60", "90")]},
    {"row": "7135", "setting": "bg_video_behind", "kind": "toggle", "screen": "homevideo", "crop": GALLERY},
    {"row": "7330", "setting": "theme", "kind": "picker", "values": ["", "halloween", "devilsnight", "christmas", "christmaseve"], "screen": "home", "crop": GALLERY, "settle": 4},
    {"row": "7331", "setting": "theme_seasonal_off", "kind": "toggle", "screen": "home", "crop": GALLERY, "shows": {"off": [("theme", "halloween")], "on": [("theme", "")]}, "settle": 4},
    {"row": "7332", "setting": "theme_christmas_off", "kind": "toggle", "screen": "home", "crop": GALLERY, "shows": {"off": [("theme", "christmas")], "on": [("theme", "")]}, "settle": 4},
    {"row": "7208", "setting": "filter_debug", "kind": "toggle", "screen": "sample", "crop": GALLERY},
]


def picture_name(setting, value):
    """
    <summary>The file name a picture takes for a setting and value.</summary>
    <param name="setting">The skin setting.</param>
    <param name="value">"on", "off", a picker value, or "" for the default.</param>
    <returns>The file name under media/preview.</returns>
    """
    return "%s_%s.png" % (setting, value or "default")


def picture_values(entry):
    """
    <summary>The values an entry is pictured at.</summary>
    <param name="entry">A row of PICTURES.</param>
    <returns>["off", "on"] for a toggle, the picker's values otherwise.</returns>
    """
    return ["off", "on"] if entry["kind"] == "toggle" else list(entry["values"])


# ---- the event server client -------------------------------------------------
PT_HELO, PT_BYE, PT_ACTION = 0x01, 0x02, 0x0A
ACTION_EXECBUILTIN, ACTION_BUTTON = 0x01, 0x02


class Kodi:
    """
    <summary>One session with the event server: a socket greeted once, builtins
    and actions sent one at a time with a moment for Kodi to act.</summary>
    """

    def __init__(self):
        """<summary>Opens the socket and greets Kodi.</summary>"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send(PT_HELO, b"preview-art\0" + bytes([0]) + b"\0" * 8 + b"\0")

    def _send(self, kind, payload):
        """<summary>Sends one packet in the event server's 2.0 format.</summary>"""
        header = b"XBMC" + struct.pack(">BBHLLHL", 2, 0, kind, 1, 1, len(payload), 0x00C0FFEE)
        self.sock.sendto(header + b"\0" * 10 + payload, (HOST, PORT))
        time.sleep(0.08)

    def builtin(self, text):
        """
        <summary>Runs one Kodi builtin, as a keymap would.</summary>
        <param name="text">The builtin with its arguments.</param>
        """
        self._send(PT_ACTION, bytes([ACTION_EXECBUILTIN]) + text.encode("utf-8") + b"\0")

    def action(self, name):
        """
        <summary>Sends one keymap action by name.</summary>
        <param name="name">The action name, such as back or info.</param>
        """
        self._send(PT_ACTION, bytes([ACTION_BUTTON]) + name.encode("utf-8") + b"\0")

    def close(self):
        """<summary>Says goodbye and closes the socket.</summary>"""
        self._send(PT_BYE, b"")
        self.sock.close()

    def screenshot(self, path, timeout=8.0):
        """
        <summary>Asks Kodi for a screenshot and waits for the file to settle.</summary>
        <param name="path">Where TakeScreenshot writes it.</param>
        <param name="timeout">Seconds to wait before giving up.</param>
        <returns>True when the file arrived and stopped growing.</returns>
        """
        if os.path.exists(path):
            os.remove(path)  # the previous attempt's file of the same name, ours
        self.builtin("TakeScreenshot(%s)" % path)
        deadline = time.time() + timeout
        last = -1
        while time.time() < deadline:
            time.sleep(0.3)
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size and size == last:
                    return True
                last = size
        return False


# ---- settings in and out -----------------------------------------------------
def read_backup():
    """
    <summary>Reads the helper's settings backup: every skin setting's current value.</summary>
    <returns>A dict of setting id to (type, value), type "bool" or "string".</returns>
    """
    if not os.path.isfile(BACKUP):
        sys.exit("No settings backup at %s: the helper writes it while the skin is live, so "
                 "open Skin Settings once (Back Up Now) and run again. Not changing any setting blind." % BACKUP)
    root = ET.parse(BACKUP).getroot()
    return {s.get("id"): (s.get("type"), (s.text or "").strip()) for s in root.iter("setting")}


def apply_setting(kodi, setting, kind, value):
    """
    <summary>Sets one skin setting through builtins.</summary>
    <param name="kodi">The session.</param>
    <param name="setting">The setting id.</param>
    <param name="kind">"bool" or "string".</param>
    <param name="value">"true"/"false" for a bool, text for a string ("" resets it).</param>
    """
    if kind == "bool":
        kodi.builtin("Skin.SetBool(%s)" % setting if value == "true" else "Skin.Reset(%s)" % setting)
    elif value:
        kodi.builtin("Skin.SetString(%s,%s)" % (setting, value))
    else:
        kodi.builtin("Skin.Reset(%s)" % setting)


def restore_setting(kodi, snapshot, setting):
    """
    <summary>Puts one setting back as the backup had it, or clears it when the
    backup never held it.</summary>
    <param name="kodi">The session.</param>
    <param name="snapshot">The backup as read_backup() returns it.</param>
    <param name="setting">The setting id.</param>
    """
    kind, value = snapshot.get(setting, ("string", ""))
    apply_setting(kodi, setting, kind, value)


BEFORE = os.path.expanduser("~/.kodi/userdata/addon_data/skin.functional/preview-art-before.json")
TEMP_MARK = "functional-preview-art-"


def read_view_mode(path):
    """
    <summary>The view Kodi has saved for a list path under this skin.</summary>
    <param name="path">The list path as Kodi stores it, with its trailing slash.</param>
    <returns>The view id, or None when Kodi has none saved or the database
    cannot be read.</returns>
    <remarks>
    Container.SetViewMode(51) puts the movie list in the gallery for the
    library pictures, and Kodi saves that choice per path in ViewModes.db,
    so the user's own view would be replaced for good. The id is read here
    before the run (the high bit Kodi adds to a user chosen view masked off)
    and put back at the end with the same builtin.
    </remarks>
    """
    databases = sorted(glob.glob(os.path.expanduser("~/.kodi/userdata/Database/ViewModes*.db")))
    if not databases:
        return None
    try:
        connection = sqlite3.connect("file:%s?mode=ro" % databases[-1], uri=True)
        row = connection.execute("select viewMode from view where path = ? and skin = ?", (path, "skin.functional")).fetchone()
        connection.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    view = row[0] & 0xFFFF
    return view or None  # Kodi's automatic view masks to 0 and has nothing to put back


SETTLED = 120  # seconds after a run's end before the helper's backup is trusted again


def clean_snapshot():
    """
    <summary>The settings to restore at the end of the run: the helper's backup,
    unless that backup was written while a run was under way.</summary>
    <returns>A dict of setting id to (kind, value), as read_backup() gives.</returns>
    <remarks>
    The helper backs up the settings on its own clock, so a backup taken in
    the middle of a run holds the run's values, not the user's: the temporary
    backdrop as the Home background, or, when the backup lands part way
    through the restores at the end, the settings restored so far right and
    the rest still at default (one run put three settings back wrong that
    way). So a backup is trusted only when home_background does not point
    into a run's work folder and it was written SETTLED seconds or more
    after the last run ended; otherwise the copy saved in BEFORE by the
    last trusted read is used. With no copy the run stops rather than
    restore the wrong thing. The one cost: a setting the user changes in
    the two minutes after a run is put back by the next run.
    </remarks>
    """
    snapshot = read_backup()
    before = None
    if os.path.isfile(BEFORE):
        with open(BEFORE, encoding="utf-8") as handle:
            saved = json.load(handle)
        settings = saved.get("settings", saved)  # a copy from before run_ended was recorded is bare
        before = {key: tuple(value) for key, value in settings.items()}
        too_soon = os.path.getmtime(BACKUP) < saved.get("run_ended", 0) + SETTLED
    else:
        too_soon = False
    polluted = TEMP_MARK in snapshot.get("home_background", ("string", ""))[1]
    if not polluted and not too_soon:
        save_before(snapshot, 0)
        return snapshot
    if before is None:
        sys.exit("the settings backup holds a run's values and no copy from before that run is "
                 "saved: set the skin settings right in Skin Settings, wait for the helper's next "
                 "backup, and run again")
    print("settings backup was written %s; restoring from the copy saved before it"
          % ("during a run" if polluted else "too soon after the last run"))
    return before


def save_before(snapshot, run_ended):
    """
    <summary>Writes the copy of the user's settings that a later run may need.</summary>
    <param name="snapshot">The settings as read_backup() gives them.</param>
    <param name="run_ended">When the run that wrote this ended, or 0 at a trusted read.</param>
    """
    with open(BEFORE, "w", encoding="utf-8") as handle:
        json.dump({"settings": snapshot, "run_ended": run_ended}, handle, indent=1)


# ---- the backdrop and the clip -----------------------------------------------
def make_backdrop(path):
    """
    <summary>Draws the capture backdrop in the skin's own style: its background
    colour, a faint accent glow, the lambda mark ghosted on the left, no text.</summary>
    <param name="path">Where to write the JPEG.</param>
    """
    colours = dict(re.findall(r'<color name="(\w+)">([0-9A-Fa-f]{8})',
                              open(os.path.join(SKIN, "colors", "defaults.xml"), encoding="utf-8").read()))
    def rgb(name):
        v = colours[name]
        return tuple(int(v[i:i + 2], 16) for i in (2, 4, 6))
    bg, accent = rgb("bg"), rgb("accent")
    im = Image.new("RGB", (1920, 1080), bg)
    glow = Image.new("RGB", (1920, 1080), bg)
    ImageDraw.Draw(glow).ellipse((1100, 300, 2300, 1500), fill=tuple(int(b * 0.72 + a * 0.28) for a, b in zip(accent, bg)))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(220)), 0.9)
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, 1920, 120):
        d.line((x, 0, x, 1080), fill=accent + (10,), width=1)
    for y in range(0, 1080, 120):
        d.line((0, y, 1920, y), fill=accent + (10,), width=1)
    logo = Image.open(os.path.join(SKIN, "media", "logo.png")).convert("L")
    logo = logo.resize((720, int(logo.height * 720 / logo.width)))
    im.paste(Image.new("RGB", logo.size, (255, 255, 255)), (120, 540 - logo.height // 2),
             logo.point(lambda v: int(max(0, v - 40) * 0.18)))
    im.save(path, quality=92)


SAMPLE = {"path": ""}


def make_sample_folder(folder, clip):
    """
    <summary>Makes a folder of neutral sample films for the gallery pictures: twelve
    links to the test clip, each with a plain coloured poster, so no poster from
    the user's library ever ships.</summary>
    <param name="folder">Where to make it.</param>
    <param name="clip">The test clip the links point at.</param>
    """
    os.makedirs(folder, exist_ok=True)
    palette = [(30, 136, 229), (67, 160, 71), (251, 140, 0), (142, 36, 170), (0, 137, 123), (229, 57, 53), (94, 53, 177), (0, 172, 193)]
    for n in range(1, 13):
        name = "Sample Film %d" % n
        link = os.path.join(folder, name + ".mp4")
        if not os.path.exists(link):
            os.symlink(clip, link)
        im = Image.new("RGB", (400, 600), palette[n % len(palette)])
        d = ImageDraw.Draw(im)
        d.rectangle((30, 30, 370, 570), outline=(255, 255, 255), width=4)
        im.save(os.path.join(folder, name + "-poster.jpg"), quality=88)
    SAMPLE["path"] = folder + "/"


def make_clip(path):
    """
    <summary>Makes a silent 90 second test pattern clip with ffmpeg for the player pictures.</summary>
    <param name="path">Where to write the MP4.</param>
    <returns>True when ffmpeg made it.</returns>
    """
    if not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=25:duration=90",
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "90", "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path]
    return subprocess.run(cmd).returncode == 0 and os.path.isfile(path)


# ---- the screens -------------------------------------------------------------
def show(kodi, screen, clip, settle, item=1):
    """
    <summary>Puts the named screen up, ready for a screenshot.</summary>
    <param name="kodi">The session.</param>
    <param name="screen">A screen name from the table.</param>
    <param name="clip">The test clip path, for the player screens.</param>
    <param name="settle">Seconds to wait once the screen is up.</param>
    <param name="item">For the list screens, which title to focus, counted
    from the top of the list.</param>
    """
    if screen in ("sample", "gallerybg", "samplecontext", "library", "libraryfilter"):
        path = MOVIES if screen.startswith("library") else SAMPLE["path"]
        kodi.builtin("ActivateWindow(Videos,%s,return)" % path)
        time.sleep(3)
        kodi.builtin("Container.SetViewMode(51)")
        time.sleep(2)
        # Kodi remembers the list position per path, so a plain "down" lands
        # one item further on every visit and a pair would differ by the film,
        # not the setting: go to the top and count to the same item every time.
        # The count starts at the ".." parent row, so it assumes Kodi's "show
        # parent folder items" is on, as it is by default
        kodi.action("firstpage")
        time.sleep(0.5)
        for _ in range(item):
            kodi.action("right")
            time.sleep(0.3)
        time.sleep(1.2)
        if screen == "samplecontext":
            kodi.action("contextmenu")
            time.sleep(2)
        elif screen == "libraryfilter":
            kodi.builtin("Skin.SetBool(left_menu_open)")
            kodi.builtin("Skin.SetBool(filter_menu_open)")
            time.sleep(2)
    elif screen in ("osd", "osdsleep"):
        kodi.builtin("PlayMedia(%s)" % clip)
        time.sleep(4)
        if screen == "osdsleep":
            kodi.builtin("Skin.SetString(sleep_command,episode)")
            time.sleep(1.5)
        kodi.action("osd")
        time.sleep(2)
    elif screen == "videosettings":
        kodi.builtin("PlayMedia(%s)" % clip)
        time.sleep(4)
        kodi.builtin("ActivateWindow(OSDVideoSettings)")
        time.sleep(2)
    elif screen == "homevideo":
        kodi.builtin("PlayMedia(%s)" % clip)
        time.sleep(4)
        kodi.builtin("ActivateWindow(Home)")
        time.sleep(2)
    elif screen == "powermenu":
        kodi.builtin("ActivateWindow(Home)")
        time.sleep(1)
        kodi.builtin("ActivateWindow(ShutdownMenu)")
        time.sleep(2)
    elif screen == "startup":
        kodi.builtin("ActivateWindow(startup)")
        time.sleep(0.5)
        return  # the splash hands over after a second: no settle
    elif screen == "home":
        kodi.builtin("ActivateWindow(Home)")
        time.sleep(2)
    time.sleep(settle)


def leave(kodi, screen):
    """
    <summary>Takes the named screen down again.</summary>
    <param name="kodi">The session.</param>
    <param name="screen">The screen name that was shown.</param>
    """
    if screen in ("samplecontext", "videosettings"):
        kodi.action("back")
        time.sleep(1)
    if screen == "libraryfilter":
        kodi.builtin("Skin.Reset(filter_menu_open)")
        kodi.builtin("Skin.Reset(left_menu_open)")
    if screen in ("osd", "osdsleep", "homevideo", "videosettings"):
        if screen == "osdsleep":
            kodi.builtin("Skin.SetString(sleep_command,cancel)")
        kodi.action("back")
        kodi.builtin("PlayerControl(Stop)")
        time.sleep(1.5)
    if screen == "powermenu":
        kodi.action("back")
        time.sleep(1)
    kodi.builtin("ActivateWindow(Home)")
    time.sleep(1)


def crop_to_panel(src, crop, dst, masks=()):
    """
    <summary>Crops a screenshot to a region and fits it on the panel, letterboxed
    on the skin's panel colour when the region is not 16 by 9, after painting
    over any area that must not ship.</summary>
    <param name="src">The screenshot path.</param>
    <param name="crop">(left, top, width, height) in screen units.</param>
    <param name="dst">The picture to write.</param>
    <param name="masks">(left, top, width, height) areas to paint over first.</param>
    """
    im = Image.open(src).convert("RGB")
    sx, sy = im.width / 1920.0, im.height / 1080.0
    paint = ImageDraw.Draw(im)
    for ml, mt, mw, mh in masks:
        paint.rectangle((int(ml * sx), int(mt * sy), int((ml + mw) * sx), int((mt + mh) * sy)), fill=(24, 28, 34))
    l, t, w, h = crop
    region = im.crop((int(l * sx), int(t * sy), int((l + w) * sx), int((t + h) * sy)))
    scale = min(PANEL[0] / region.width, PANEL[1] / region.height)
    fitted = region.resize((max(1, int(region.width * scale)), max(1, int(region.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", PANEL, (24, 28, 34))
    canvas.paste(fitted, ((PANEL[0] - fitted.width) // 2, (PANEL[1] - fitted.height) // 2))
    canvas.save(dst, optimize=True)


# ---- the run ----------------------------------------------------------------
def main(argv):
    """
    <summary>Makes the pictures for every row, or the rows named on the command line.</summary>
    <param name="argv">Command line arguments after the script name.</param>
    """
    if "--list" in argv:
        for e in PICTURES:
            print(e["row"], e["setting"], e["kind"], ", ".join(picture_values(e)), e["screen"])
        return
    if Image is None:
        sys.exit("Pillow is needed (python3 -m pip install pillow)")
    wanted = [e for e in PICTURES if not argv or e["row"] in argv]
    snapshot = clean_snapshot()
    work = tempfile.mkdtemp(prefix="functional-preview-art-")
    backdrop = os.path.join(work, "backdrop.jpg")
    make_backdrop(backdrop)
    clip = os.path.join(work, "clip.mp4")
    if not make_clip(clip):
        sys.exit("ffmpeg is needed for the test clip the pictures use; install it and run again")
    make_sample_folder(os.path.join(work, "sample"), clip)
    os.makedirs(OUT, exist_ok=True)
    touched = {"bg_mode", "home_background", "bg_all_windows", "bg_video_behind", "theme", "left_menu_open", "filter_menu_open"}
    # every pictured setting at the skin's default for the whole run, whatever
    # this machine has it set to: a shipped picture shows the setting against
    # the skin as installed, and a user's own bar at the top or gallery at
    # extra large would otherwise sit in every picture of every other row
    pictured = sorted({e["setting"] for e in PICTURES} | {o for e in PICTURES for shown in e.get("shows", {}).values() for o, _ in shown} | set(BASELINE))
    touched.update(pictured)
    movie_view = read_view_mode(MOVIES)
    uses_library = any(e["screen"].startswith("library") for e in wanted)
    kodi = Kodi()
    try:
        for setting in pictured:
            kodi.builtin("Skin.Reset(%s)" % setting)
        kodi.builtin("Skin.SetString(home_background,%s)" % backdrop)
        kodi.builtin("Skin.SetString(bg_mode,image)")
        time.sleep(2)
        for entry in wanted:
            setting, kind = entry["setting"], "bool" if entry["kind"] == "toggle" else "string"
            touched.add(setting)
            for value in picture_values(entry):
                shows = entry.get("shows", {}).get(value, [])
                for other, other_value in shows:
                    touched.add(other)
                    apply_setting(kodi, other, "string", other_value)
                if entry["kind"] == "toggle":
                    apply_setting(kodi, setting, "bool", "true" if value == "on" else "false")
                else:
                    apply_setting(kodi, setting, "string", value)
                if entry["screen"] == "gallerybg":
                    kodi.builtin("Skin.SetBool(bg_all_windows)")
                if entry.get("reload"):
                    kodi.builtin("ReloadSkin()")
                    time.sleep(4)
                show(kodi, entry["screen"], clip, entry.get("settle", 1.5), entry.get("item", 1))
                shot = os.path.join(work, "shot.png")
                if not kodi.screenshot(shot):
                    print("  no screenshot for %s %s, skipped" % (setting, value))
                    leave(kodi, entry["screen"])
                    continue
                dst = os.path.join(OUT, picture_name(setting, value))
                crop_to_panel(shot, entry["crop"], dst, entry.get("mask", ()))
                print("  %s" % os.path.relpath(dst, HERE))
                leave(kodi, entry["screen"])
                if entry["screen"] == "gallerybg":
                    kodi.builtin("Skin.Reset(bg_all_windows)")
            # this row's own settings back to default at once, not at the end
            # of the run: a value left behind leaks into every row after it (a
            # gallery size, the info bar at the top, the OSD at the top) and the
            # later pictures then show the wrong thing or nothing at all
            for other in [setting] + [o for shown in entry.get("shows", {}).values() for o, _ in shown]:
                kodi.builtin("Skin.Reset(%s)" % other)
    finally:
        # the sleep timer disarmed and the player stopped first, so a failure
        # in the restores cannot leave either running; then every touched
        # setting back as the backup had it, and the skin reloaded once
        kodi.builtin("Skin.SetString(sleep_command,cancel)")
        kodi.builtin("PlayerControl(Stop)")
        for setting in sorted(touched):
            restore_setting(kodi, snapshot, setting)
        if uses_library:
            if movie_view is None:
                print("Kodi had no saved view for the movie list; it keeps the gallery view the run chose")
            elif movie_view != 51:
                kodi.builtin("ActivateWindow(Videos,%s,return)" % MOVIES)
                time.sleep(3)
                kodi.builtin("Container.SetViewMode(%d)" % movie_view)
                time.sleep(1)
        kodi.builtin("ReloadSkin()")
        time.sleep(2)
        kodi.builtin("ActivateWindow(Home)")
        kodi.close()
        save_before(snapshot, time.time())
    print("done: %d rows, settings restored" % len(wanted))
    print("work folder left for inspection, not removed: %s" % work)


if __name__ == "__main__":
    main(sys.argv[1:])
