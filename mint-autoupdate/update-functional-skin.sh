#!/usr/bin/env bash
#
# update-functional-skin.sh
#
# Looks for skin.functional-<version>.zip in this script's folder (the "drop
# folder"). If the newest one found is a higher version than the skin currently
# installed in Kodi's addons directory, it replaces the installed skin with it.
#
# Run this at boot BEFORE Kodi starts (see start-kodi.sh / README). Doing the
# swap on disk while Kodi is NOT running avoids Kodi's in-place skin reinstall,
# which black-screens the Flatpak build (GL context teardown on live reload).
#
# Drop folder can be overridden with:  SKIN_DROP_DIR=/path ./update-functional-skin.sh
#
set -uo pipefail

ADDON_ID="skin.functional"
HERE="$(cd "$(dirname "$0")" && pwd)"
DROP_DIR="${SKIN_DROP_DIR:-$HERE}"
LOG="$HERE/skin-autoupdate.log"

log() { printf '%s  %s\n' "$(date '+%F %T')" "$*" >> "$LOG"; }

# Print the <addon> tag's version from an addon.xml ($1 may be /dev/stdin).
ver() {
    grep -m1 "id=\"$ADDON_ID\"" "$1" 2>/dev/null \
        | sed -n 's/.*version="\([^"]*\)".*/\1/p'
}

# ver_gt A B  -> success (0) if A is strictly greater than B (version sort).
ver_gt() {
    [ "$1" != "$2" ] && \
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

# --- locate Kodi's addons directory (Flatpak / Snap / native) ---
ADDONS=""
for d in \
    "$HOME/.var/app/tv.kodi.Kodi/data/.kodi/addons" \
    "$HOME/.var/app/tv.kodi.Kodi/.kodi/addons" \
    "$HOME/snap/kodi/common/.kodi/addons" \
    "$HOME/.kodi/addons" ; do
    [ -d "$d" ] && ADDONS="$d" && break
done
if [ -z "$ADDONS" ]; then
    log "Kodi addons dir not found, nothing to do"
    exit 0
fi

# --- installed version ---
inst="0"
[ -f "$ADDONS/$ADDON_ID/addon.xml" ] && inst="$(ver "$ADDONS/$ADDON_ID/addon.xml")"
inst="${inst:-0}"

# --- newest zip in the drop folder ---
best=""; bestv="0"
shopt -s nullglob
for z in "$DROP_DIR/$ADDON_ID-"*.zip; do
    v="$(unzip -p "$z" "$ADDON_ID/addon.xml" 2>/dev/null | ver /dev/stdin)"
    [ -n "$v" ] || continue
    if ver_gt "$v" "$bestv"; then bestv="$v"; best="$z"; fi
done

if [ -z "$best" ]; then
    log "no $ADDON_ID-*.zip in $DROP_DIR (installed $inst), nothing to do"
    exit 0
fi

if ! ver_gt "$bestv" "$inst"; then
    log "up to date (installed $inst, available $bestv)"
    exit 0
fi

# --- update ---
log "updating $inst -> $bestv from $(basename "$best")"
tmp="$(mktemp -d)"
if unzip -q -o "$best" "$ADDON_ID/*" -d "$tmp" && [ -d "$tmp/$ADDON_ID" ]; then
    rm -rf "$ADDONS/$ADDON_ID"
    mv "$tmp/$ADDON_ID" "$ADDONS/$ADDON_ID"
    log "done, now at $bestv"
else
    log "ERROR: failed to extract $best"
fi
rm -rf "$tmp"
