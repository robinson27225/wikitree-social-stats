# Changelog

The version is `wtstats.__version__` and is shown in the dashboard sidebar. Bump it, and add an entry here, with each release.

## 1.0.0 - 2026-10-17

First release for WikiTree members.

- Loads Facebook, Instagram, TikTok and LinkedIn daily exports (CSV, Excel and LinkedIn's `.xls`), Meta single-metric exports,
  the scheduler's daily export and monthly YouTube exports into SQLite. Every file is archived untouched first.
- History from 2021 for Facebook and Instagram, May 2023 for LinkedIn, Sep 2023 for TikTok.
- Dashboard: Overview, Channels, Posts, YouTube, Data & quality. Over time or Year over year; YouTube by month, year or
  year over year.
- Data-quality rules: values that cannot be right are flagged and left out of the charts, gaps are listed, and changes of
  measure are marked on the charts (Facebook Reach to Viewers, Instagram Content interactions).
