# Functional skin: Linux Mint auto-updater (optional)

A hands-off way to update the skin on a media-centre box: drop the new zip in a
folder and reboot, no keyboard, no Kodi "install from zip" menu-diving. The
scripts replace the skin files on disk **before Kodi starts**, so the new skin
loads cleanly on the next launch.

(Normal in-place "install from zip" works fine too; this is just a convenience
for headless / remote-only setups.)

## Files
- `update-functional-skin.sh` checks for a newer `skin.functional-*.zip` in its
  own folder and, if found, extracts it into Kodi's addons directory.
- `start-kodi.sh` runs the updater, then launches Kodi. Use this as your Kodi
  launcher so the update is guaranteed to run first.

It auto-detects the addons directory for Flatpak, Snap, or native Kodi.

## One-time setup
1. Put this `mint-autoupdate` folder somewhere on the box, e.g. `~/kodi-skin/`.
2. Make the scripts executable:
   ```
   chmod +x ~/kodi-skin/update-functional-skin.sh ~/kodi-skin/start-kodi.sh
   ```
3. If you use the **native** or **snap** Kodi (not Flatpak), edit the last line of
   `start-kodi.sh` accordingly (`exec kodi` or `exec snap run kodi`).
4. Make Kodi launch via the wrapper instead of directly:
   - **Autostart (most Mint setups):** Menu → Startup Applications → add a new
     entry with the command `/home/<you>/kodi-skin/start-kodi.sh`, and remove the
     old direct-Kodi autostart entry.
   - **Or a desktop shortcut:** point its `Exec=` at `start-kodi.sh`.

## Updating the skin from then on
1. Copy the new `skin.functional-<version>.zip` into the `~/kodi-skin/` folder
   (overwrite or alongside the old one, it always picks the highest version).
2. Reboot (or just relaunch Kodi via the wrapper).

That's it, no keyboard, no Kodi "install from zip". On boot the updater compares
versions and only swaps in a genuinely newer zip; otherwise it does nothing.

## Checking it worked
A log is written next to the scripts: `skin-autoupdate.log`, e.g.
```
2026-06-15 19:42:01  updating 0.7.39 -> 0.7.44 from skin.functional-0.7.44.zip
2026-06-15 19:42:01  done, now at 0.7.44
```

## Alternative: systemd user service (instead of the wrapper)
If you'd rather not change the Kodi launcher, enable the updater as a user
service that runs at login:
```
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/functional-skin-update.service <<'UNIT'
[Unit]
Description=Update Functional Kodi skin before the session starts
Before=graphical-session.target

[Service]
Type=oneshot
ExecStart=%h/kodi-skin/update-functional-skin.sh

[Install]
WantedBy=default.target
UNIT
systemctl --user enable functional-skin-update.service
```
The wrapper (`start-kodi.sh`) is more reliable for guaranteeing order, but the
service works on setups where Kodi isn't started by the desktop session.
