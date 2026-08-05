# Functional Skin: Install Guide

The display name is **Functional**. The addon ID and folder name are both `skin.functional`. Release zips are named `skin.functional-<version>.zip` (built into `Skin Dist/` by `build_zip.py`).

## Method 1: Install from Zip (recommended)

This is the cleanest way to install on each Kodi device.

### One-time prep (per device)

Kodi blocks installing from zip by default. Enable it once:

1. **Settings → System → Add-ons**
2. Toggle **Unknown sources** on
3. Confirm the warning dialog

### Install

1. Copy the latest `skin.functional-*.zip` to the device (USB stick, network share, cloud download, whatever's easiest)
2. In Kodi: **Settings → Add-ons → Install from zip file**
3. Browse to the zip and select it
4. Wait for the "Add-on installed" notification at the top-right
5. Activate the skin: **Settings → Interface → Skin → Skin → Functional**
6. When asked "Keep this skin?", pick **Yes** (or **Use these settings now**)

Done.

## Method 2: Manual copy

If the device doesn't allow zip install, copy the folder by hand.

1. Extract the zip on your computer and you'll get a `skin.functional/` folder
2. Find Kodi's user addons folder on the target device:
   - **Windows**: `%APPDATA%\Kodi\addons\`
   - **Linux**: `~/.kodi/addons/`
   - **macOS**: `~/Library/Application Support/Kodi/addons/`
   - **Android**: `/Android/data/org.xbmc.kodi/files/.kodi/addons/` (or via SMB share)
   - **LibreELEC/CoreELEC**: `/storage/.kodi/addons/`
3. Copy the entire `skin.functional/` folder into that addons folder
4. **Restart Kodi** (full quit + relaunch)
5. **Settings → Interface → Skin → Skin → Functional**

## Method 3: Unattended update on boot (Linux HTPC)

For a headless / remote-only Linux box, the scripts in [`mint-autoupdate/`](mint-autoupdate/) swap in a newer zip at boot, before Kodi starts. Drop a new `skin.functional-*.zip` in the drop folder and reboot. See that folder's README for setup.

## Updating to a newer version

- **Zip method**: just install the new zip the same way, and Kodi replaces the old version
- **Manual method**: delete the existing `skin.functional/` folder on the device first, then copy the new one

After updating, you might need to switch to a different skin and back, or restart Kodi, for the new XML to load (Kodi caches skin files in memory).

## Migrating from the old `skin.starter`

If a device previously had this skin under the old ID `skin.starter`:

1. In Kodi, switch the active skin to **Estuary** (so the old skin isn't in use)
2. In Kodi: **Add-ons → My add-ons → Look and feel → Skin** → uninstall **Functional** (the old `skin.starter`)
3. Or manually delete `…/Kodi/addons/skin.starter/` on the device
4. Install the new `skin.functional-*.zip` per the steps above
5. Activate it via **Settings → Interface → Skin → Skin → Functional**
