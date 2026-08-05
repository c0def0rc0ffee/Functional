#!/usr/bin/env bash
#
# start-kodi.sh, launcher that updates the Functional skin THEN starts Kodi.
#
# Point your autostart / session at THIS script instead of Kodi directly. That
# guarantees the skin update happens while Kodi is not running, so the new skin
# loads fresh on launch (no in-place reload, no black screen).
#
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1) apply any newer skin zip sitting in this folder
"$HERE/update-functional-skin.sh" || true

# 2) launch Kodi (Flatpak). Change this line if you use the native/snap build:
#      native: exec kodi
#      snap:   exec snap run kodi
exec flatpak run tv.kodi.Kodi
