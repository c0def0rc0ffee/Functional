<!--
  <summary>
  What changed in each release of the Functional skin, newest first. The
  section for the version in addon.xml is copied into that file's news
  element by build_zip.py (run it with the news flag after a version bump)
  and becomes the GitHub release notes at publish time, so this file is
  the one place a change is described.
  </summary>
-->
# Changelog

Newest first. Releases before 0.12.0 are described in their GitHub release notes.

## 0.12.12 (22/09/2026)

- A changelog. This file is the source of what changed, its current section
  travels inside the skin as the add-on's news, so the add-on info screen
  on the TV shows what a new version brought, and the same text becomes the
  release notes on GitHub.

## 0.12.11 (22/09/2026)

- Lists export and import on the Lists and Favourites settings page. Export
  copies the lists file to any folder Kodi can write to; import merges a
  lists file in by list name without removing anything, so it can be run
  twice safely.

## 0.12.10 (22/09/2026)

- Search in the library filter menu. A keyboard prompt narrows the list on
  screen to titles containing the text, stacking with the genre and age
  filters on movies and TV shows and working inside a show's episode list.
  A Clear row undoes it.

## 0.12.9 (22/09/2026)

- Four windows the skin had no file for: playback bookmarks and chapters,
  Kodi 21's Manage versions and Manage extras, the colour picker, and the
  controller configuration dialogs.

## 0.12.8 (22/09/2026)

- Sleep timer by episode: power down when the video playing now finishes,
  or after a chosen number of episodes, from the power menu.

## 0.12.7 (22/09/2026)

- A Recently Added tab beside Continue Watching opens the same pop-up on a
  page of the newest movies and episodes.
- Fixed the pop-up sitting too high with the tab at the top and Next Up
  hidden.

## 0.12.6 (22/09/2026)

- Next Up row in the Continue Watching pop-up: the next unwatched episode of
  every show you are part way through, with the same press and hold menu as
  the other rows.

## 0.12.5 (22/09/2026)

- Groundwork with no visible change: one helper for every command channel,
  named Home edges, and a static check suite the build runs before packaging.

## 0.12.4 (22/09/2026)

- Housekeeping from a code review: the Home menu no longer overlaps the
  corner bar or the Continue tab, the Watching block packs up when the
  blocks above it are hidden, the cast strip cannot show the previous
  title's actors, and every readout the service writes is localised.

## 0.12.3 (22/09/2026)

- The Lists screen's action buttons can sit along the top under the header
  instead of the bottom (Lists and Favourites settings).

## 0.12.2 (22/09/2026)

- Skin Settings split into seven pages so nothing scrolls.
- Review fixes: the build refuses to package without its exclusion list, an
  unreadable lists file is set aside rather than overwritten, and the
  Continue pop-up's actions no longer run on the service's main loop.

## 0.12.1 (22/09/2026)

- The Home Screen settings page split into sections with scrollbars.

## 0.12.0 (22/09/2026)

- A sleep timer in the power menu with a countdown on Home and on the OSD.
- The Home corner bar can sit in any corner or edge centre.
- A Stats page and a Watching block on Home built on JellyStat's figures,
  while that add-on is installed.
- Age filter in the library filter menu, stacking with the genre filter.
- Continue Watching pop-up behind an edge tab.

