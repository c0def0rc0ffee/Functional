# Functional Skin: Install Guide

The display name is **Functional**. The addon ID and folder name are both `skin.functional`. Release zips are named `skin.functional-<version>.zip` (built into `Skin Dist/` by `build_zip.py`).

## Method 1: Repository add-on (recommended, updates itself)

Install one small zip once and Kodi keeps the skin current on its own, exactly like an add-on from the official repository. New releases are picked up automatically on Kodi's normal update schedule.

### One-time prep (per device)

Kodi blocks installing from zip by default. Enable it once:

1. **Settings → System → Add-ons**
2. Toggle **Unknown sources** on
3. Confirm the warning dialog

### Install the repository add-on (once per device)

1. Download `repository.functional-1.0.1.zip` onto the device. It is served straight from GitHub:

   <https://raw.githubusercontent.com/c0def0rc0ffee/Functional/repo/zips/repository.functional/repository.functional-1.0.1.zip>

   No browser on the device? Copy it over on a USB stick or network share instead. The same zip also sits in `Skin Dist/repo/zips/repository.functional/` in the repo.
2. In Kodi: **Settings → Add-ons → Install from zip file**, browse to the zip and select it
3. Wait for the "Add-on installed" notification

### Install the skin from the repository

1. **Settings → Add-ons → Install from repository → Functional Repository → Look and feel → Skin → Functional → Install**
2. Activate it: **Settings → Interface → Skin → Skin → Functional**, then answer **Yes** to "Keep this skin?"

From here on Kodi checks the repository for new versions by itself. To force a check at any time: **Settings → System → Add-ons → Updates** should be set to **Install updates automatically**, and **Add-ons → My add-ons → Check for updates** triggers one immediately.

## Method 2: Install from Zip (manual updates)

The direct route when a device should stay pinned to one version.

### One-time prep (per device)

Same as above: enable **Unknown sources** under **Settings → System → Add-ons**.

### Install

1. Copy the latest `skin.functional-*.zip` to the device (USB stick, network share, cloud download, whatever's easiest)
2. In Kodi: **Settings → Add-ons → Install from zip file**
3. Browse to the zip and select it
4. Wait for the "Add-on installed" notification at the top-right
5. Activate the skin: **Settings → Interface → Skin → Skin → Functional**
6. When asked "Keep this skin?", pick **Yes** (or **Use these settings now**)

Done.

## Method 3: Manual copy

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

## Method 4: Unattended update on boot (Linux HTPC)

For a headless / remote-only Linux box, the scripts in [`mint-autoupdate/`](mint-autoupdate/) swap in a newer zip at boot, before Kodi starts. Drop a new `skin.functional-*.zip` in the drop folder and reboot. See that folder's README for setup.

## Updating to a newer version

- **Repository method**: nothing to do, Kodi installs new versions on its own (or trigger one via **Add-ons → My add-ons → Check for updates**)
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
