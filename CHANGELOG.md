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

## 0.13.0 (02/10/2026)

- A fix release after a full review of the skin and its helper.
- Screens that could trap or lose focus no longer do: the Lists action row
  with an empty list selected, Favourites with nothing in a category, Home
  on a cold start, the genre picker's scrollbar and the subtitle search.
- Settings dialogs show their button row, the volume pop-up shows its
  level, the queue's highlighted row shows its title, progress dialogs
  have a bar and add-on information fits all of its buttons.
- The settings backup no longer rewrites itself every twenty seconds, and
  a settings reset can no longer replace the backup or grey out Restore.
- Lists are safer: an unreadable lists file is never overwritten, the
  previous copy is kept, and an import checks each item against this
  library.
- A sleep timer set on the clock now replaces an episode count, the music
  queue end time counts from the track playing, the Duration field switch
  works, and cancelling the search keyboard leaves the list alone.
- Picking a genre keeps an age or search filter, and a sort the list does
  not offer no longer reverses it.
- Home tiles keep clear of the stats column with up to eight tiles.

## 0.12.16 (27/09/2026)

- Remove Watched, a switch each list has on the Lists screen. Turned on,
  anything on that list that gets watched leaves it, with a notification
  saying which list it left. Finishing a film or episode counts, as does
  marking it watched by hand; a stream or file counts once it has played
  past nine tenths. Other lists holding the same item keep it.

## 0.12.15 (23/09/2026)

- Main menu tiles you own. The Main Menu settings page now has eight
  ordered slots; each can be one of the skin's screens or any favourite
  from Kodi's list (an add-on, a playlist, a library node, a file), with
  its own label. Untouched, the menu is exactly what it was.

## 0.12.14 (23/09/2026)

- Watched marks in the list view at last: a tick and a dimmed title on
  played rows. Shows and seasons that are part way through show their
  watched of total episode count, in the list and on the gallery poster;
  before, a show was marked only once every episode had been played.

## 0.12.13 (22/09/2026)

- Any colour as the accent: a Custom accent colour row on the Overall
  settings page opens Kodi's colour picker, and the highlight shade used
  for selected rows and figures now follows the accent, preset or custom,
  instead of staying blue.

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

