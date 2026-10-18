# Changelog

The version is `wtstats.__version__` and is shown in the dashboard sidebar. Bump it, and add an entry here, with each release.

## 1.4.1 - 2026-10-18

- Data tab: the two gaps that can't be filled (Instagram interactions Jun and Aug 1-21, 2025; LinkedIn followers Jan 1 - Oct 15, 2025) now say so.

## 1.4.0 - 2026-10-18

- YouTube monthly exports for every month from Jan 2021 to Sep 2026 are loaded, so every month's channel subscribers and views
  come from its export.
- New series: Events Committee; "Global Genealogy Spotlight" counts as Global Spotlight; the Nov 2024 Symposium sessions are filed
  under WikiTree Symposium (`data/youtube_series.csv`).

## 1.3.0 - 2026-10-18

- YouTube tab order: channel subscribers, channel views, then views by series.
- New series: RAWK, Global Spotlight, 15 Nations Global Tour, Disco(rd) Party, Watchlist Weevil Challenge, Alabama Challenge,
  Welcome to WikiTree, Why I Love WikiTree, Global Family Reunion, NEWT Team, WikiTree Holocaust Project, One Million Members.
- "Which ... are you most closely connected to?" videos are ConnectionFinder; the "Over N profiles. Countless connections."
  community posts are One Name Tuesday; "FRIDAY SPOTLIGHT" titles are Spotlight Profile Shorts.
- YouTube monthly exports Jan - Apr 2025 loaded (so Jan 2025 - Sep 2026 is complete).

## 1.2.2 - 2026-10-17

- Channel subscribers and views per month now always come from the month's per-video export (its Total row); a sheet only
  fills months that have no export, and never replaces one.
- YouTube monthly exports May - Sep 2025 loaded.

## 1.2.1 - 2026-10-17

- YouTube: a series that gained no subscribers is left off the *Subscribers gained* charts.
- Channel numbers corrected (Feb 2023 subscribers; Oct - Dec 2025 views from the exports).
- YouTube monthly exports Oct - Dec 2025 loaded.

## 1.2.0 - 2026-10-17

- YouTube: channel subscribers *and views* by month (Jan 2022 - Sep 2026), shown by Month, Year or Year over year.
- YouTube: monthly per-video exports for Jan - Jun and Sep 2026 loaded.
- New series: #OnePlaceWednesday, #GenealogyCollaborationHour, WikiTree Easter Egg Hunt, #FridayDateNight, #Hacktoberfest,
  WikiTree Symposium, RootsTech, WikiTree Tours, WikiTree Profile Improvement Project, WikiTree New Members, WikiTree Heritage
  Exchange. LiveCasts and "Live with Sarah and Eowyn" are filed under WikiTree Saturday Roundup.
- YouTube tab: show videos, community posts, or both.

## 1.1.1 - 2026-10-17

- YouTube series reorganised to follow the channel's playlists: each format is its own series (WikiTree Week, WikiGames,
  #CemeterySpotlight, Friday "Night" Bingo, 12 Days of Elf-Mas, WikiTree Meet Our Members, Research Parties, One Name Tuesday,
  Project Showcase are new). Names now match the playlist titles (WikiTree Saturday Roundup, #ConnectionCheckers, WikiTree Ask
  Aleš, WikiTree Member Q&A, Link Builders Cubicle Party, WikiTree How To).
- "#ConnectionFinder: ..." and "Are you related ..." are told apart by how the title starts; the latter is Spotlight Profile
  Shorts even if it carries the #ConnectionFinder tag.

## 1.1.0 - 2026-10-17

- Year over year: each year has its own colour (2021 red, 2022 blue, 2023 green, 2024 orange, 2025 gold, 2026 violet);
  the latest year is the thickest line.
- YouTube channel subscribers by month (from the channel's own Date + Subscribers export), grouped by Month, Year or
  Year over year.
- YouTube series: Link Builders and Tech Talk, Ask Aleš and Member Q&A are separate; new series Azure & Eowyn and
  Spotlight Profile Shorts ("Are you related..."); Connection Combat is filed with ConnectionCheckers; ConnectionFinder is its
  own series. A Playlist column in the export, or `data/youtube_series.csv`, sets a video's series; `reclassify` refiles videos.
- Fix: the hosted app no longer breaks after a redeploy ("cannot import name ...").

## 1.0.0 - 2026-10-17

First release for WikiTree members.

- Loads Facebook, Instagram, TikTok and LinkedIn daily exports (CSV, Excel and LinkedIn's `.xls`), Meta single-metric exports,
  the scheduler's daily export and monthly YouTube exports into SQLite. Every file is archived untouched first.
- History from 2021 for Facebook and Instagram, May 2023 for LinkedIn, Sep 2023 for TikTok.
- Dashboard: Overview, Channels, Posts, YouTube, Data & quality. Over time or Year over year; YouTube by month, year or
  year over year.
- Data-quality rules: values that cannot be right are flagged and left out of the charts, gaps are listed, and changes of
  measure are marked on the charts (Facebook Reach to Viewers, Instagram Content interactions).
