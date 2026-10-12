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

## 0.21.1 (12/10/2026)

- No more lightning. The flash is gone from Halloween and from Devil's
  Night; the rain, fog and creatures stay as they were.
- On Christmas Eve the sleigh no longer jumps if it happens to be
  crossing the sky just before it comes in to land at midnight.

## 0.21.0 (12/10/2026)

- Christmas, a new seasonal theme. Cream on deep evergreen with a holly
  red accent and gold highlights, snow drifting down and frost in the
  corners. With no background picture of your own, a snowy village at
  night: a tree with twinkling lights and a star, a church, a robin on
  the fence, and a couple of things for those who look closely. With a
  picture, a soft night wash over it with the snow and frost on top.
  Santa's sleigh crosses the moon now and then.
- Christmas Eve, the night of 24 December: the village is always up and
  the sleigh comes round far more often. At midnight it lands on a
  rooftop and stays parked there all Christmas Day.
- Both come on by themselves from the first Saturday of December to the
  end of Boxing Day. The new setting Christmas every year switches that
  off without touching Halloween, and the Theme row picks either one by
  hand at any time.

## 0.20.0 (12/10/2026)

- Halloween has company: spiders scuttling across the screen, fast and
  slow, one now and then letting itself down a thread; a witch on her
  broomstick crossing the sky; and ghosts drifting past. The red tint
  over your background stays as it was, and Devil's Night is unchanged.
- The first time each year that Halloween comes on by itself, it starts
  with the red tint alone. After a while a spider shoots across, then
  another, then the witch, and it builds up from there, the fog rolling
  in and the lightning starting, until after about half an hour all of
  it is running. Every other time, after a restart or with the theme
  picked by hand, it starts with everything at once.

## 0.19.0 (12/10/2026)

- Seasonal themes, in a new Seasonal Themes section on the Overall
  settings page. Halloween turns the whole skin over to horror: bone
  text on near black, a blood red accent, window titles in a dripping
  horror lettering, fog drifting along the foot of every screen, dark
  corners, the odd flash of lightning and bats crossing the sky. With no
  background picture of your own, a haunted house stands on a hill under
  a blood moon with flickering jack o'lanterns; with one, the picture is
  washed red instead.
- Devil's Night, the night of 30 October, sets a cemetery in the rain
  behind every screen, with two headstones, Eric Draven and Shelly
  Webster. A crow flies in and lands on Eric's stone, taps it and caws,
  and every few minutes flies off and comes back.
- Both come on by themselves each year: Halloween on 29 and 31 October,
  Devil's Night on the 30th, until midnight going into 1 November. The
  setting Halloween every year can switch that off, and the Theme row
  picks either one by hand at any time of year. The colours change
  through Kodi's own skin colour setting, so the screen reloads once as
  a theme starts or ends; that waits until nothing is playing.

## 0.18.1 (12/10/2026)

- Coming up shows a slot's name alone. The block in the stats column no
  longer adds the episode after it, so a show reads as just its name,
  the same as the rows of the list on the left.

## 0.18.0 (12/10/2026)

- Coming up list, a Home Screen setting offered when the Engage add-on
  is installed, beside the Coming up block and independent of it. The
  next Engage slots run down the left of Home, each with its episode or
  film and when it is due; OK on a row opens Engage. The list starts
  under the logo and a top menu and grows down as far as the layout
  allows, up to eleven rows with the logo hidden and the menu out of its
  way; a wide menu row across the centre ends it above the row. It
  shows once an Engage release publishes the slots; until then nothing
  appears.
- A centred menu row of up to four tiles now sits on the screen centre
  beside the stats column instead of being pushed left with the wider
  rows.

## 0.17.0 (11/10/2026)

- Coming up, a Home Screen setting offered when the Engage add-on is
  installed. The stats column gains a block with the next Engage watch
  slot, its episode or film and when it is due; OK on it opens Engage.
  It shows once an Engage release publishes the slot; until then
  nothing appears.

## 0.16.0 (11/10/2026)

- Collections, a Library setting. The side menu's filter section gains a
  Collections row that opens Kodi's film collections, one entry each; a
  collection opens like any other list of films. A Show row there cycles
  All, Unfinished (some films watched, some not) and Not started, and
  Search at that level finds collections by name; the two stack. The
  context menu on a film in a collection gains Collection: <name>, which
  opens it. Kodi only lists a collection holding a single film when its
  own "Include sets containing a single movie" setting is on.

## 0.15.0 (11/10/2026)

- Add To List on the background, a Background setting. The caption
  gains a button after the title that puts the film on a list, or on a
  new one, the same picker the context menu uses.
- Previous and next buttons at the screen edges, a Background setting.
  Left and Right from the menu row reach them; Back steps through what
  has been shown, Next goes forward and then on to a fresh picture, and
  the timer carries on from there. They work on the picture folder
  slideshow as well as the library ones.

## 0.14.0 (08/10/2026)

- A new volume pop-up: a large ring in the middle of the screen with the
  volume percent at its centre, filling clockwise as the volume rises.
  Muted greys the ring and says so.
- Show when last watched, a Background setting. The caption under the
  title gains the date the film or show was last played, in the
  recently watched, random and genre modes.
- Unwatched films only, a Background setting for random mode. Only films
  never watched are picked, and TV shows are left out.
- Move and remove buttons on list items, a Lists and Favourites setting.
  The highlighted row on the Lists screen shows up, down and remove;
  Right and Left pick one and OK uses it. Remove asks first.
- Shuffle List in List Options puts a list in a new random order for
  good, after asking.
- Remove from Radarr: one list can be tied to a Radarr server on the new
  Radarr settings page, and its List Options then offer to remove that
  list's films from Radarr, deleting their files and blocking them from
  being added again. It asks first, starts in dry run, which only logs
  what would happen, and does nothing until an address, API key and
  list are set. The List Options drop down itself is new, holding
  Rename, Remove List and Remove Watched.

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

