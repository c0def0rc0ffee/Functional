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

## 0.23.28 (13/11/2026)

- New: the Coming up list counts down to the slot that plays next. While
  Engage's countdown switch is on (Engage 1.11.11 or later) and the next
  slot is within its window, its line shows the minutes left and a thin
  bar that empties as it nears.
- New: the skip pill can be set per show: the default, Intros and Recaps,
  With Credits, or No Pill. The info screen's per show button reads This
  Show while the pill is on and asks which choice to change. A show set to
  No Pill asks the server nothing. The Playback page's switch still turns
  the pill off for every show, and it stays off by default.

## 0.23.27 (11/11/2026)

- Fixed: TV episodes could get stuck sorted by rating. Kodi keeps one
  sort for every episode list, so choosing Rating in one show sorted
  them all that way, and the Sort menu had no way back. The Sort menu
  now has an Episode choice in episode lists, which puts every show
  back in season and episode order.

## 0.23.26 (10/11/2026)

- Fixed: saying yes to powering down after a Port by Time queue could
  be refused with "No queue of videos is playing", because the answer
  came before Kodi had started the queue's first item. A yes now waits
  up to 30 seconds for the queue to start, so the box powers down after
  it as asked and Queue shows on the seek bar and the OSD.

## 0.23.25 (10/11/2026)

- New Follow Focused Tile row under Skin Settings, Background, below
  the mode selector, off by default. Switched on, focusing the Movies,
  TV Shows or Music tile on Home turns the background to random fanart
  of that kind, and every other tile keeps the chosen mode. Moving
  between tiles brings back the picture each kind was showing, the
  edge buttons step through the followed pictures, and a kind with no
  fanart leaves the mode in charge. Left off, the background looks as
  before.

## 0.23.24 (09/11/2026)

- New Slow Zoom row under Skin Settings, Background, below Dim, off by
  default. Switched on, the background picture zooms slowly in and out,
  about a tenth over 30 seconds each way, while the dim, the captions
  and the seasonal decorations hold still. It follows Show On All
  Screens, is one setting for every time slot, and Reduce Motion stops
  it. Left off, the background looks as before.

## 0.23.23 (09/11/2026)

- New Skip Intro Pill row under Skin Settings, Playback, off by
  default. While an intro or recap your Jellyfin server has marked is
  playing, a Skip Intro or Skip Recap button shows bottom right with a
  bar that empties as it plays: OK skips to its end, Back hides it. Skip
  Credits Too adds the end credits, but not while the Next Episode Card
  is on. The markers come from the Intro Skipper or TheIntroDB plugin on
  the server. Switching the pill on offers to turn the Jellyfin add-on's
  own skip buttons off so the two do not overlap, and switching it off
  offers them back. Left off, playback looks as before.

## 0.23.22 (08/11/2026)

- New Text on Accent row under Skin Settings, Overall, beside Custom
  Accent Colour. Left on White, every screen looks as before. Set to Auto,
  the text on a focused row or button, a selected list row and the badge
  pills turns dark when the accent is light: Amber, Orange, or a custom
  colour that is light, so a yellow accent stays readable. Text on the
  skin's dark panels is not touched.

## 0.23.21 (08/11/2026)

- With the next episode card switched on, a show's info screen has a
  Next Card button: each show can use the default, Unwatched, In Order or
  no card at all. The choice stays with the show when the library is
  refreshed. With the card switched off nothing changes.

## 0.23.20 (08/11/2026)

- New Next Episode Card row under Skin Settings, Playback, off by
  default. Set to Unwatched or In Order, a card shows the next episode
  bottom right near the end of a library episode, as the credits start
  or at the time set on At the Latest. OK plays it at once and Back hides
  the card. Live TV, specials and a queue that already has a next item
  get no card. Left off, playback looks as before.

## 0.23.19 (07/11/2026)

- New Offer to Power Down After Port by Time switch under Skin Settings,
  Lists and Favourites, off by default. Switched on, Port by Time asks
  whether to power the box down when the queue finishes. It powers down
  only after the last item ends by itself, with ten seconds' warning in
  which any key keeps it on; stopping it yourself or playing something
  else calls it off. Left off, Port by Time asks nothing new.

## 0.23.18 (07/11/2026)

- New Show Start Badge switch under Skin Settings, Playback, off by
  default. Switched on, the first six seconds of a video show its picture
  mode (Dolby Vision, HDR10, HLG or SDR), its resolution and its age
  rating at the top right. Live TV never shows it. Left off, playback
  looks as before.

## 0.23.17 (07/11/2026)

- New Close Info Panel After setting under Skin Settings, Playback, Off
  by default. Set to 5, 10, 20 or 30 seconds, the info panel you open with
  Info during a video closes itself after that time.
- New Title Logo on Info Panel switch beside it, off by default. Switched
  on, the info panel shows a film's logo in place of its title when the
  film has one. Episodes and other videos keep their title. Left off,
  the info panel looks as before.

## 0.23.16 (07/11/2026)

- New Show Sleep Button switch under Skin Settings, Playback, off by
  default. Switched on, the video OSD gets a moon button left of Previous
  that opens the sleep timer choices, so a timer can be set or cancelled
  without leaving the film. Left off, the OSD and the power menu look as
  before.

## 0.23.15 (07/11/2026)

- New Show Chapter Marks switch under Skin Settings, Playback, off by
  default. Switched on, the video OSD gets a progress bar with a mark at
  the start of each chapter, and the seek bar shows the same marks. A
  file without chapters shows the bar alone. Left off, the OSD and the
  seek bar look as before.

## 0.23.14 (06/11/2026)

- New release badges on the movie gallery, three switches under Skin
  Settings, Library, Visible Fields, all off by default. 4K Badge marks
  4K and 8K films, HDR Badge shows HDR, DV for Dolby Vision or HLG, and
  Resolution Badge shows 1080, 720 or SD for films below 4K. The badges
  sit at the top left of the poster. Left off, the gallery looks as
  before.

## 0.23.13 (06/11/2026)

- New Preview Settings switch under Skin Settings, Overall, off by
  default. Switched on, the panel under the help text shows what the
  focused setting does: the Home Screen drawn live, or a picture of each
  value, following the value as you change it. A setting with nothing to
  show says so. Left off, Skin Settings looks as before.
- Fixed the dim settings at their no dim step. Video Dim, the Home
  background dim and the dim for other windows covered the screen in
  white at 0, in every earlier release. They now leave the picture at
  full brightness.

## 0.23.12 (05/11/2026)

- New Show Greeting switch under Skin Settings, Home Screen, at the foot
  of the Around the Screen list, off by default. Switched on, the clock
  on Home reads Good morning, Good afternoon or Good evening by the hour
  in front of the time, with your profile name when Kodi has more than
  one profile. It goes with the clock, so Show Date and Time off hides it
  too, and with the main menu at the top and five or more tiles there is
  no room beside the clock, so the time shows alone there. Left off, the
  clock reads exactly as before.
- A new install starts with the background on Slideshow: Recently
  Watched rather than Off, and Recently Watched shows random library
  fanart until something has been watched. An existing setup keeps its
  own choice, Off included.

## 0.23.11 (05/11/2026)

- New Rounded Corners switch under Skin Settings, Library, below Compact
  Posters, off by default. Switched on, the posters in the Movies and TV
  Shows gallery and the art on the video, music and add-on info screens,
  the version manager and the full screen info card are drawn with
  rounded corners, the focus frame, the watched badge and the watched count
  strip following the poster's shape. Left off, every poster is square as
  before. The rows below it on the Library settings page sit 40 px lower to
  make room.

## 0.23.10 (04/11/2026)

- New Reduce Motion switch under Skin Settings, Overall, off by default.
  Switched on, the slide and fade effects when windows, menus and pop-ups
  open, close, appear or go are skipped, so everything changes in one
  step, the moving art on the About and credits pages holds still, and the
  steam over the cup on the credits page is not drawn.
  The seasonal theme decorations keep their own switches. Left off, the
  skin moves exactly as before.

## 0.23.9 (04/11/2026)

- A list row whose library id had moved to another film, as happens when a
  file is replaced or the library rebuilt, could show one title and start
  another. Every stored id is now checked against the library after
  loading and again when a row is played, ported, moved or copied: a moved
  id is found again from the file, and one whose file has gone falls back
  to playing by path.

## 0.23.8 (22/10/2026)

- A list item's menu can now move or copy it to another list, or to a new
  one made there and then.

## 0.23.7 (22/10/2026)

- The Radarr settings page is called Radarr again, and the switch that lets
  JellyStat manage the lists has moved to the Add-ons page.
- The time on a Coming up Ends At line is no longer clipped.

## 0.23.6 (22/10/2026)

- New Add-ons page in the settings, holding the JellyStat and Engage
  settings that used to sit on the Home Screen page.
- A help panel under the settings pages says what the focused setting does
  and where on screen it shows.
- Coming up can end each run of back to back Engage slots with an Ends At
  line giving when the run finishes. Each Engage slot can turn its line off.
- Coming up can scroll: focus the list and press Down to go on through the
  week a day at a time; it goes back to the top when you move away.
- Needs Engage 1.11.8 for the Ends At line and the full week.

## 0.23.5 (22/10/2026)

- New setting, off by default: Coming up can show when Engage slots queued
  behind each other will really start. A slot set for 18:05 behind an 18:00
  one shows when the 18:00 one ends, counting from whatever is playing now.
  Only the list changes; Engage still prompts at the set time. Needs Engage
  1.11.7.

## 0.23.4 (21/10/2026)

- The Coming up list on Home now shows up to 22 Engage slots, up from 11,
  filling the room freed when a day groups its slots under one heading.
  The extra slots need Engage 1.11.6; an older Engage still gives the
  first 11.

## 0.23.3 (21/10/2026)

- Small polish and tidying behind the scenes.

## 0.23.2 (20/10/2026)

- The Coming up list on Home now groups a day that has more than one Engage
  slot: the day is shown once as a title, with each slot on its own line
  beneath it giving just the name and the time. A day with a single slot
  still shows as before, the name with when it is due underneath.

## 0.23.1 (14/10/2026)

- A Specials episode saved from the queue window with Save as List now keeps
  its season, so the Lists screen shows S00E01 under it rather than the show
  name alone.
- Import Lists no longer makes a second list whose name differs from one you
  already have only by case; such a list is skipped and a message says how
  many were. A lists file that already holds such a pair reads with the
  second one renamed, with a number in brackets, instead of dropped.
- Restoring a backup from JellyStat is refused when the backup names a list
  twice, ignoring case, and the list tied to Remove from Radarr is never
  copied onto more than one restored list.
- Setting Port by Time on the TV no longer makes JellyStat refuse its next
  change to the lists as made against an older version.
- The README and the install guide now describe the Lists page in Skin
  Settings and the JellyStat switch on it.

## 0.23.0 (13/10/2026)

- Your lists can now be managed from the JellyStat dashboard on a phone or
  laptop: make and delete lists, rename them, turn Remove Watched on or
  off, search the library to add films, whole shows or episodes, put the
  items in order or take them off, and back up or restore every list. The
  TV's Lists screen shows each change at once. It needs JellyStat 0.27.0 or
  later on the same box, and can be switched off in Skin Settings, Lists,
  which is the page that used to be called Radarr.

## 0.22.2 (13/10/2026)

- Sort Lists now keeps the lists in the order you pick. A new list, an
  item added or taken away, or a rename puts them straight back in that
  order, and the button shows which order is in force. The list you have
  selected stays selected when it moves. Oldest first is the order the
  lists were made in.

## 0.22.1 (13/10/2026)

- The Lists screen has a Sort Lists button at the end of its action row,
  shown when there are two lists or more. It puts the lists in order by
  name, newest or oldest first, or most or fewest items first, and keeps
  that order. Lists made before this count as made in the order they
  were already in.

## 0.22.0 (13/10/2026)

- A whole TV show or season can go on a list as one row. Press and hold
  on a show or season in the TV library and use Add To List. The row
  shows how many episodes it holds.
- Port to Queue plays every episode of it in order. Port Shuffled and
  Port by Time count the show or season as one item and pick one random
  episode from it, so a show added whole gives one episode and the same
  show added as two seasons gives two. A whole show leaves out Specials.
- On a list with Remove Watched on, an episode watched after the show or
  season was added is taken out of it, and the row goes once every
  episode has been watched.

## 0.21.3 (12/10/2026)

- The Coming up list on the left has separators: a faint line between
  slots on the same day, and a heavier one where the day changes.
- With the logo hidden and only the background caption in the top left,
  the Coming up list now starts just under the caption instead of well
  below it, which fits one more slot.

## 0.21.2 (12/10/2026)

- Coming up reads in white. The slots in the Coming up block and the
  list down the left now show their names and times in white like the
  rest of the stats column, with only the headings in the accent colour,
  and the list's names use the same size as its times.

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

