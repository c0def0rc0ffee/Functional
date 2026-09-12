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

# --- required tools, checked up front ---
# Without unzip every zip silently reads as an empty version and the script
# would log "nothing to do" instead of the real problem. Same idea for the
# rest: a missing tool must fail loudly, not masquerade as an empty drop
# folder or a botched update.
missing=""
for cmd in unzip mktemp; do
    command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
done
sort --version-sort /dev/null >/dev/null 2>&1 || missing="$missing sort(-V)"
if [ -n "$missing" ]; then
    log "ERROR: missing required command(s):$missing - install them, no update attempted"
    exit 1
fi

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
# Flatpak builds differ: some keep the profile under data/.kodi, the current
# tv.kodi.Kodi keeps it directly under data/ (data/addons, data/userdata).
for d in \
    "$HOME/.var/app/tv.kodi.Kodi/data/.kodi/addons" \
    "$HOME/.var/app/tv.kodi.Kodi/data/addons" \
    "$HOME/.var/app/tv.kodi.Kodi/.kodi/addons" \
    "$HOME/snap/kodi/common/.kodi/addons" \
    "$HOME/.kodi/addons" ; do
    [ -d "$d" ] && ADDONS="$d" && break
done
if [ -z "$ADDONS" ]; then
    log "Kodi addons dir not found, nothing to do"
    exit 0
fi

# --- leftovers from an interrupted earlier run ---
# The swap below parks the old skin as .skin.functional.old.<pid> and stages
# into .skin.functional.staging.*; a run killed mid-way (power cut at boot)
# leaves those behind, and their names are unique so no later run would
# ever remove them. Nothing else creates dot-folders with these names.
for stale in "$ADDONS/.${ADDON_ID}.old."* "$ADDONS/.${ADDON_ID}.staging."*; do
    [ -d "$stale" ] || continue
    rm -rf "$stale" && log "removed leftover $(basename "$stale")"
done

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
# Stage on the DESTINATION filesystem (mktemp -d usually lands on tmpfs, and a
# cross-filesystem mv is a copy that can fail halfway), swap the old install
# aside instead of deleting it, and only log success when every step worked -
# so a failed update leaves the previous skin in place, not a missing addon.
# Every ERROR path sets status=1 so the exit code reports the failure (the
# systemd oneshot variant in the README shows it; start-kodi.sh ignores it
# on purpose and launches Kodi regardless).
log "updating $inst -> $bestv from $(basename "$best")"
status=0
tmp="$(mktemp -d "$ADDONS/.${ADDON_ID}.staging.XXXXXX")"
old="$ADDONS/.${ADDON_ID}.old.$$"
if unzip -q -o "$best" "$ADDON_ID/*" -d "$tmp" && [ -d "$tmp/$ADDON_ID" ]; then
    if [ -d "$ADDONS/$ADDON_ID" ] && ! mv "$ADDONS/$ADDON_ID" "$old"; then
        log "ERROR: could not move the installed skin aside; leaving it untouched"
        status=1
    elif mv "$tmp/$ADDON_ID" "$ADDONS/$ADDON_ID"; then
        rm -rf "$old"
        log "done, now at $bestv"
    else
        # Put the previous install back so Kodi still has a skin.
        [ -d "$old" ] && mv "$old" "$ADDONS/$ADDON_ID"
        log "ERROR: could not install $bestv; previous version restored"
        status=1
    fi
else
    log "ERROR: failed to extract $best"
    status=1
fi
rm -rf "$tmp"
exit "$status"
