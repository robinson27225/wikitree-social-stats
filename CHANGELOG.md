# Changelog

The version is `wtstats.__version__` and is shown in the dashboard sidebar. Bump it, and add an entry here, with each release.

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
