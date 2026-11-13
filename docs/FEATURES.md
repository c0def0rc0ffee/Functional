# Functional: features in full

Everything the skin does, screen by screen. Every setting named here lives in **Settings > Skin Settings**; [SETTINGS.md](SETTINGS.md) lists them page by page. Back to the [README](../README.md).

## Home Screen

- **Main menu tiles you own**: eight ordered slots, each one of the skin's screens (Movies, TV Shows, Music, Pictures, Weather, Lists, Stats, Favourites, Add-ons, Settings) or any Favourite from Kodi's list, with a label of your choosing; untouched, the menu is the familiar one
- Menu position configurable: top, centre, or bottom of the screen
- Round icon buttons for **Favourites, Add-ons, Settings, and Power**, with an optional "invisible until focused" mode for a minimal look
- Real-time date and time, with an optional **weather widget** (temperature + conditions) beside the clock
- Library stats panel showing movie counts (total, unwatched, watched), TV show counts (total, unwatched) and total episodes, updated instantly via a background service rather than slow container queries
- **Coming up** list of Engage's next slots down the left, with a countdown on the slot that plays next (the minutes left and a bar that empties) while Engage's countdown setting is on
- Resume button when media is playing; queue button with item count when items are queued
- **Sleep timer** from the power menu: at a set time, when the video playing now finishes, or after a number of episodes, with a countdown on Home and on the OSD
- **Continue Watching** pop-up behind an edge tab: in-progress movies and episodes, plus a **Next Up** row with the next unwatched episode of every show you are part way through, each row with a press-and-hold Resume / Mark as watched / Mark as unwatched menu, and optionally **Hide**, which keeps a title or a Next Up show out until it is played again (off by default). A **Recently Added** tab beside it opens the same pop-up on a page of the newest movies and episodes, and an optional **Watchlist** tab shows the titles carrying a tag you choose, or one of your Lists in its own order (off by default)
- **Home rows**: up to three rows of posters under the main menu, each with its own source (recently added, in progress, unwatched, random films or one of your Lists); while any is on the menu sits at the top (off by default)
- Optional logo, version footer, loading splash, and date/time, all toggleable

## Backgrounds

One unified **Background** selector so the modes can never conflict:

- **Off**: plain background
- **Static Image**: pick any image; its filename can show as a caption
- **Slideshow: Recently Watched**: cycles fanart from your recently watched movies, and shows random library fanart until something has been watched. A new install starts here
- **Slideshow: Random Library**: random fanart from across your movies and TV shows
- **Slideshow: Genre**: random fanart from one library genre of your choice (movies, TV shows, or both)
- **Slideshow: Folder**: cycles every picture in a folder you choose (browse with thumbnails and tap any image in the target folder)

Around the selector:

- A configurable rotate interval (10s / 30s / 1m / 2m / 5m; unset = 20s)
- A dim level (0 to 90%) so text stays readable
- A caption position for the slideshow/static label
- **Time of day slots**: every background option also exists per slot. A schedule of two to four slots, each with its own start time, swaps the whole background configuration on the clock
- **Follow Focused Tile** (off by default): random film, TV or music fanart while the Movies, TV Shows or Music tile has focus, and the chosen mode everywhere else
- **Slow Zoom** (off by default): drifts the picture gently in and out. It is one setting for every slot, and Reduce Motion stops it

The background is not limited to the home screen:

- **Show On All Screens**: paints the same background behind the library, settings and every other window, with its own separate dim level so list rows and labels stay readable over it
- **Keep Playing Video Behind Menus**: leave a film playing, press back, and the picture keeps running behind the menus while you browse. Works whether or not the background is shown on all screens

## Video Library

![Gallery view of famous science fiction posters, Back to the Future focused, with its year, age and 4K badge in the header](../screenshots/gallery.jpg)

- **Gallery view**: poster grid with four sizes (Small, Medium, Large, Extra Large), plus a small-grid column count toggle (11/12) for TVs with overscan, and a Tall/Compact poster-shape option
- **List view**: traditional file list alternative
- Watched marks in both views: an accent corner badge with a tick on completed movies, episodes and fully watched shows in the gallery, a tick and a dimmed title in the list view, and a watched-of-total episode count on shows and seasons that are part way through
- Info bar with the focused item's metadata, every field individually toggleable:
  - Genre, duration, star rating, age rating (PG/12/15/etc.), resolution (4K/1080p/720p/480p), last played date
  - **"Ends at" time**: a background service works out when the focused movie or episode would finish if started now (e.g. "Ends at 22:47")
  - Episode air dates and movie release years shown automatically by content type
- Info bar position switchable between top and bottom; live-tunable top/bottom clearance
- **Studio or network logo**: an optional logo on the information screen, top right, from Kodi's Studio Icons pack (off by default). Switching it on offers to install the pack; switching it off offers to leave it, disable it or uninstall it
- **More like this**: an optional row on the information screen of up to twelve titles from your library with the same collection, director or genre, newest first (off by default)

## Slide-Out Library Options

![The Library Options panel slid out over the poster gallery, showing View, Sort, Direction, Filter, Layout Adjust and Close](../screenshots/library-options.jpg)

A left-side panel that slides in over the library, with collapsible dropdowns:

- **View**: Gallery or List
- **Sort**: Title, Year, Rating, Date Added, Last Played, and Episode in an episode list (back to season and episode order), with an ascending/descending direction toggle
- **Default sort order**: a default sort and direction for Movies and for TV Shows, set once under Library and applied whenever a library screen opens
- **Scroll badge**: while you scroll, a badge shows the sort key of the item under the cursor (year, rating, date added, last played, or the initial letter), so you always know where you are in a long list
- **Filter**: the native watched-status toggle (All Videos / Unwatched / Watched), which filters shows, seasons and episodes correctly and updates the menu label to match
- **Genre**: a genre picker narrows the library to one genre, with an All Genres reset; the menu label always shows the genre actually in force on screen
- **Search**: a keyboard prompt narrows the list to titles containing the text, stacking with the genre and age filters on movies and TV shows and working inside a show's episode list too; the row shows the text in force and a Clear row undoes it
- Quick access to your queue
- Layout adjust controls (gallery size, info-bar position, poster shape, clearance) right in the menu

## Video OSD

![The video OSD over a Star Trek: The Next Generation episode: title, elapsed time, Ends at time, buffer readout and resolution badge](../screenshots/video-osd.jpg)

- Compact on-screen display with animated slide-in
- Title row: movie title with year, or TV show name with season/episode and episode title, with a filename fallback for unscraped content
- Current time and estimated finish time in accent colour (switches to a "Paused" indicator when paused)
- Progress bar with elapsed time, total duration, and percentage
- Resolution badge (4K/1080p/720p/etc.) as an accent-coloured pill
- Optional poster thumbnail
- Nine transport buttons: previous, rewind, play/pause, stop, fast forward, next, audio settings, subtitle search, video settings
- Positionable top or bottom; configurable backdrop dim while the video-settings dialog is open
- **Playback buffer readout**: an optional buffer level on the OSD and the pause/seek bar (cache percentage, megabytes and seconds ahead)
- **Full Buffer** button (optional): switches the current film to buffering the entire file and back again, reopening the stream at the same position
- A reset restores Kodi's own buffering defaults (Playback > Playback Buffer)

## Weather

- Full **Weather window**: large current conditions, an 8-hour hourly strip, and a 5-day forecast, reading from any configured Kodi weather provider
- Home-screen widget beside the clock

## Favourites

- A **categorised, filterable Favourites screen**: chips across the top split your favourites into **All / Movies / TV / Music / Apps / Other**, with a live count on each (empty categories hide themselves)
- Great for large, unsorted favourites lists (watch-later movies, launcher apps, quick-select add-ons): jump straight to the type you want
- Remembers the filter you last used, and a **Default Favourites Filter** setting (Lists and Favourites) chooses which one it opens on
- The helper service classifies each favourite from its stored action, so no manual tagging is needed

## Lists

- **Named lists of anything playable**: hold Select on a movie, episode or song and choose **Add To List** (pick a list or make a new one), or **Add to list <name>** to drop it straight into the last list you used
- A **Lists** entry on the main menu opens the Lists screen: your lists down the left, the selected list's items on the right, with rename, remove, reorder and remove-item actions
- **Port to Queue** copies a list into Kodi's queue and starts it playing; **Port Shuffled** jumbles the order first, so a box set plays in a fresh order every time
- Video and music can share a list: each goes to its own queue
- **Save as List** on the queue screen keeps the current queue for later
- The Lists screen's action buttons sit along the bottom, or along the top under the header (Lists and Favourites settings)
- Porting asks whether to clear the current queue first, or set a standing answer under Lists and Favourites
- **Export** and **Import** (Lists and Favourites settings) carry lists between boxes: export copies the lists file to any folder Kodi can write to, import merges one in by list name without dropping anything
- **Managed from JellyStat**: with JellyStat 0.27.0 or later on the same box, its dashboard can make, rename and delete lists, switch Remove Watched, search the library to add films, whole shows or episodes, put the items in order, and back up or restore every list, from a phone or laptop. The switch **Let JellyStat manage the lists** is in the JellyStat section of the **Add-ons** page of Skin Settings, shown when JellyStat is installed, and is on by default

## Other Windows

Custom-styled to match the skin: File Manager, Event Log, System Info, Add-on Info, the on-screen keyboard, playback bookmarks and chapters, Kodi 21's Manage versions and Manage extras, the colour picker, the controller configuration dialogs, and compact, correctly-positioned toast notifications.

> **Not skinned**: PVR/Live TV and Games. Enabling those features under this skin will leave their windows unable to open. Switch to Estuary if you need them.

## Music

- Dedicated music OSD with album art, track title, artist, album, and progress bar
- Video and music playlist views with header showing item count, total time, and current-item finish time
- Playlist controls: Play All, Shuffle, Repeat, Save, Clear

## Helper Service

A lightweight Python service handles what the skin engine can't do alone, with a non-blocking startup so a slow/unreachable library never freezes the UI:

- **Library stats**: movie/TV/episode counts (total/watched/unwatched), refreshed on a background thread and whenever the library changes
- **Focused item ETA**: provides the "Ends at" finish time shown in the info bar
- **Background slideshow**: fetches recently-watched or random library fanart and rotates it on your chosen interval; the folder mode is rendered natively by Kodi
- **Library state**: applies your default sort order and keeps the Genre label in step with the library node on screen
- **Buffer readout and full-file switch**: publishes the OSD's buffer figures and reopens the stream when you switch the current film to a full buffer
- **Lists**: runs the Add To List, port and queue actions behind the Lists screen
- **Settings backup**: watches the skin's settings file and keeps a rolling snapshot current, for Restore from Backup
- **Optional debug logging** to a file (Settings → Overall → Diagnostics) for troubleshooting
