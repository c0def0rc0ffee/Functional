# Builds both versioned zips for skin.functional:
#   Skin Dist\skin.functional-<version>.zip      - Kodi-installable skin
#   Skin Git\skin.functional-<version>-src.zip   - GitHub-bound source snapshot
#
# This is a thin wrapper: the real work is in build_zip.py, which MUST be
# used instead of Compress-Archive. Compress-Archive writes backslash paths
# and no directory entries, and Linux Kodi (LibreELEC etc.) refuses to
# install such zips. The version is read from skin.functional\addon.xml.
# Run from the repo root:  powershell -File build-zip.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $root 'build_zip.py')
if ($LASTEXITCODE -ne 0) { throw "build_zip.py failed (exit $LASTEXITCODE)" }
