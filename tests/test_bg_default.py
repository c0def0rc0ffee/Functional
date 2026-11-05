"""
<summary>
Checks for the background default of a fresh install (BG-DEFAULT): the
Recently Watched slideshow shows the library at random while nothing has
been watched, and a fresh install is seeded to Recently Watched only once
this skin is the live one, only when nothing was chosen already, and
only on a store the helper has never run on (its clearance string empty).
</summary>
<remarks>
No Kodi is needed. The xbmc modules are stubbed in sys.modules before the
real service.py is imported, as tests/test_lists_api.py does it, and the
helper is built without its constructor so only the slideshow state under
test exists. A standalone script: build_zip.py runs it and stops on a
non zero exit.
</remarks>
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "skin.functional")

# What the stubs answer and record: Skin.String values by their full info
# label, every builtin the service sends, and the live skin's folder name.
LABELS = {}
CALLS = []
SKIN_DIR = ["skin.functional"]


class _Window:
    """<summary>xbmcgui.Window with a property store and nothing else.</summary>"""
    _props = {}

    def __init__(self, *_a):
        """<summary>Every window shares the one store.</summary>"""

    def getProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>The stored value or the empty string.</summary>"""
        return self._props.get(key, "")

    def setProperty(self, key, value):  # noqa: N802 (Kodi API)
        """<summary>Store the value.</summary>"""
        self._props[key] = value

    def clearProperty(self, key):  # noqa: N802 (Kodi API)
        """<summary>Forget the value.</summary>"""
        self._props.pop(key, None)


class _Dialog:
    """<summary>xbmcgui.Dialog whose every question is declined.</summary>"""
    def __getattr__(self, _name):
        """<summary>Any method: no, nothing, cancelled.</summary>"""
        return lambda *a, **k: None


class _Monitor:
    """<summary>xbmc.Monitor, as FunctionalHelper's base class.</summary>"""
    def abortRequested(self):  # noqa: N802 (Kodi API)
        """<summary>Kodi is never shutting down here.</summary>"""
        return False

    def waitForAbort(self, _timeout=0):  # noqa: N802 (Kodi API)
        """<summary>Never aborted, and no waiting either.</summary>"""
        return False


xbmc = types.ModuleType("xbmc")
xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 4
xbmc.log = lambda *a, **k: None
xbmc.executeJSONRPC = lambda _text: "{}"
xbmc.getCondVisibility = lambda _text: False
xbmc.getInfoLabel = lambda label: LABELS.get(label, "")
xbmc.getLocalizedString = lambda _sid: ""
xbmc.executebuiltin = lambda text, *a, **k: CALLS.append(text)
xbmc.getSkinDir = lambda: SKIN_DIR[0]
xbmc.Monitor = _Monitor
xbmc.Player = type("Player", (), {"isPlaying": lambda self: False})
xbmcgui = types.ModuleType("xbmcgui")
xbmcgui.Window = _Window
xbmcgui.Dialog = _Dialog
xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = (
    "info", "warning", "error")
xbmcgui.INPUT_ALPHANUM = 0
xbmcaddon = types.ModuleType("xbmcaddon")
xbmcaddon.Addon = lambda *_a: types.SimpleNamespace(
    getLocalizedString=lambda _sid: "", getAddonInfo=lambda _k: "")
xbmcvfs = types.ModuleType("xbmcvfs")
xbmcvfs.translatePath = lambda p: p
xbmcvfs.exists = lambda _p: False
xbmcvfs.mkdirs = lambda _p: True
for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon),
                  ("xbmcvfs", xbmcvfs)):
    sys.modules[name] = mod
sys.path.insert(0, SKIN)
import service  # noqa: E402

RECENT = [{"fanart": "recent-1", "title": "Watched One"}]
RANDOM = [{"fanart": "random-1", "title": "Any One"}, {"fanart": "random-2", "title": "Any Two"}]
FAILURES = []


def check(cond, what):
    """<summary>Record a failed expectation instead of stopping at it.</summary>
    <param name="cond">The expectation.</param>
    <param name="what">What was expected, for the report.</param>"""
    if not cond:
        FAILURES.append(what)
        print("  FAILED: " + what)


def _helper(recent, fresh=True, init_skin="skin.functional"):
    """
    <summary>
    A FunctionalHelper with only the slideshow and seeding state, its two
    library fetchers replaced.
    </summary>
    <param name="recent">What the Recently Watched fetch returns.</param>
    <param name="fresh">What __init__ read: the clearance string was empty.</param>
    <param name="init_skin">The skin that was live when __init__ ran.</param>
    <returns>The helper, on the "recent" source with an empty list.</returns>
    """
    h = object.__new__(service.FunctionalHelper)
    h._bg_source = "recent"
    h._bg_items = []
    h._bg_idx = -1
    h._bg_last_change = 1.0
    h._bg_recent_fallback = False
    h._bg_seed_pending = True
    h._bg_seed_fresh = fresh
    h._bg_seed_skin = init_skin
    h._fetch_recent_movies = lambda: list(recent)
    h._fetch_random_library = lambda unwatched=False: list(RANDOM)
    return h


def test_recent_empty_shows_random():
    """<summary>Nothing watched: the random library list stands in.</summary>"""
    h = _helper(recent=[])
    h._bg_fetch_worker("recent")
    check(h._bg_items == RANDOM, "random library shown while nothing is watched")
    check(h._bg_recent_fallback, "fallback flagged while it stands in")


def test_recent_items_win():
    """<summary>Something watched: the recent list is used and the fallback ends.</summary>"""
    h = _helper(recent=RECENT)
    h._bg_recent_fallback = True
    h._bg_fetch_worker("recent")
    check(h._bg_items == RECENT, "recent list shown once something is watched")
    check(not h._bg_recent_fallback, "fallback cleared once the recent list has items")


def test_seed_waits_for_live_skin():
    """<summary>Seeding does nothing under another skin and runs once under this one.</summary>"""
    del CALLS[:]
    LABELS.clear()
    h = _helper(recent=[])
    SKIN_DIR[0] = "skin.estuary"
    h._seed_bg_default()
    check(not CALLS, "no skin string written while another skin is live")
    check(h._bg_seed_pending, "seeding still pending under another skin")
    SKIN_DIR[0] = "skin.functional"
    h._seed_bg_default()
    check(any("Skin.SetString(bg_mode" in c and "recent" in c for c in CALLS),
          "bg_mode seeded to recent once this skin is live")
    check(not h._bg_seed_pending, "seeding done after the live tick")
    n = len(CALLS)
    h._seed_bg_default()
    check(len(CALLS) == n, "seeding runs once only")


def test_seed_keeps_an_existing_setup():
    """<summary>A mode already chosen, or a store the helper has run on before, is left alone.</summary>"""
    del CALLS[:]
    LABELS.clear()
    SKIN_DIR[0] = "skin.functional"
    LABELS["Skin.String(bg_mode)"] = "image"
    h = _helper(recent=[])
    h._seed_bg_default()
    check(not CALLS, "a chosen mode is kept on a fresh install")
    LABELS.clear()
    h = _helper(recent=[], fresh=False)
    h._seed_bg_default()
    check(not CALLS, "an existing setup with Off is left on Off")
    check(not h._bg_seed_pending, "an existing setup is settled on the first live tick")


def test_seed_after_init_under_another_skin():
    """<summary>__init__ under the previous skin read the wrong store: this one is read at the live tick.</summary>"""
    del CALLS[:]
    LABELS.clear()
    SKIN_DIR[0] = "skin.functional"
    # The read under Estuary said "not fresh", but this skin's store is empty.
    h = _helper(recent=[], fresh=False, init_skin="skin.estuary")
    h._seed_bg_default()
    check(any("Skin.SetString(bg_mode" in c for c in CALLS),
          "an untouched store is seeded although __init__ read another skin's")
    del CALLS[:]
    # The read under Estuary said "fresh", but this skin has run before.
    LABELS["Skin.String(infobar_clearance_top)"] = "140"
    h = _helper(recent=[], fresh=True, init_skin="skin.estuary")
    h._seed_bg_default()
    check(not CALLS, "a store the helper has run on before is kept although __init__ read another skin's")


def main():
    """<summary>Run every check and exit non zero on any failure.</summary>"""
    for test in (test_recent_empty_shows_random, test_recent_items_win,
                 test_seed_waits_for_live_skin, test_seed_keeps_an_existing_setup,
                 test_seed_after_init_under_another_skin):
        print("running " + test.__name__)
        test()
    if FAILURES:
        print("test_bg_default: %d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("test_bg_default: all checks passed")


if __name__ == "__main__":
    main()
