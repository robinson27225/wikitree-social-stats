<img src="assets/logo.png" alt="WikiTree" width="96" align="right">

# WikiTree Social Stats

Version 1.4.1 (see [CHANGELOG.md](CHANGELOG.md)) · [Social scheduler](https://wikitree-social-scheduler.fly.dev/)

Loads exported social media numbers into a small SQLite database and shows them in a Streamlit dashboard.

## Quick start

```bash
pip install -r requirements.txt
python -m wtstats import path/to/export1.csv path/to/export2.csv   # type is detected from the columns
python -m wtstats import WikiTreers_YT_August_2026.csv             # YouTube: the month comes from the file name
python -m wtstats status                                           # what is loaded
streamlit run app.py
```

## Loading data

Each file is recognised by its columns, so you do not say which channel it is:

| File | Kept as |
|---|---|
| Facebook / Instagram / TikTok / LinkedIn daily (or monthly) sheet, as CSV | account-level numbers, one row per channel, period and metric |
| Excel workbook (`.xlsx`, or the older `.xls` such as LinkedIn's follower export) | every recognised tab loaded the same way; Twitter tabs and other tabs are skipped and reported |
| Scheduler export (`date,channel,platform,posts,views,...`) | totals for the posts published on that day, per channel |
| YouTube table export (one file per month, from a saved view) | per-video numbers for the period the file covers |

- **Every file is copied untouched into `data/raw/` before it is read.** The scheduler removes its data after an export, so that copy may be the only one. `data/` is committed to this repository, so git history is the backup.
- **Loads never delete or blank anything.** A later file can add or correct values, never erase them. Importing the same file twice is skipped (use `--force` to redo it).
- **A YouTube file doesn't say which period it covers.** The importer takes the month from the file name
  (`WikiTreers_YT_July_2026.csv` -> July 2026), or you pass `--period 2026-07`, or a range such as
  `--period 2026-01-01:2026-10-17`. If it can't tell, it archives the file and loads nothing.
- YouTube months hold that month's activity only. A date range (like year to date) overlaps the months, so the
  dashboard keeps them apart and never adds them together. Each file's own columns are kept, so a saved view in
  YouTube Studio gives the same columns every month.
- A YouTube export lists at most 500 videos (the top 500 by likes). A video missing from a month is not necessarily zero.
- **To undo an import:** `python -m wtstats remove <part of the file name>` shows what would go; add `--yes` to delete
  that file's data, its import-log entry and its archived copy. Values a later file replaced stay.
- **Excel workbooks:** each tab is logged as its own import. The archived copy keeps only the tabs that were loaded
  (saved as `.xlsx`): Twitter tabs (see `SKIP_SHEET_PATTERNS`) and other tabs, such as LinkedIn's follower demographics, are
  not kept, because the repository is public. Older header names are mapped onto the current ones
  (`Impressions (total)` -> `impressions`; TikTok 2023 `New Followers` and LinkedIn's `Total followers` -> the daily follower
  change); a repeated header or date-only block further down a tab is ignored.
- **Meta Insights exports** (one metric per file, UTF-16, starting `sep=,`) don't say which channel they are from:
  `python -m wtstats import --platform instagram --from 2025-08-22 Interactions.csv`. The metric comes from the file's
  title (`META_EXPORT_METRICS` in `wtstats/config.py`, or pass `--metric`). `--from` / `--until` limit the days loaded,
  for a metric that only existed from a date: Instagram's *Content interactions* is zero before Aug 22, 2025, which means
  "not available", not zero, so those days are not loaded.
- Monthly history files work the same way; a date like `2026-01` or `Jan 2026` is stored as a month.

## How the numbers are handled

- Empty future rows (the sheets are pre-filled to Dec 31) are skipped, not stored as zeros.
- Numbers with thousands separators (`"2,299"`) are read correctly.
- **Blanks:** an Instagram *New Followers* blank and a blank in any LinkedIn count (impressions, clicks, reactions, comments, reposts, page views, visitors) are stored as 0. A blank anywhere else is "not recorded", not zero. LinkedIn *followers* is entered by hand, so a blank there stays blank.
- **TikTok:** *Followers* was a daily change until Aug 31, 2026 and a running total after. The total is stored as `followers_total`; the daily change after the cutover is derived from consecutive days. The cutover date is `TIKTOK_FOLLOWERS_TOTAL_FROM` in `wtstats/config.py`.
- **LinkedIn:** the engagement rate is not stored (recompute it from the counts).
- **Flagged values** are kept in the database but left out of the charts, and listed on the *Data & quality* tab:
  - Facebook *Views* below *Viewers* (Apr 2-3, 2026);
  - Facebook *Reach* in Sep 2025, when it drops to about a tenth of *Viewers* (Facebook's own export confirms the numbers, so they are real, just no longer comparable with earlier Reach; *Viewers* is used instead);
  - columns copied from another (Facebook *Link Clicks* = *Page Visits* in Jan 2026; Instagram *New Followers* = *Profile Visits* in Oct 2022);
  - Instagram *Interactions* Jan 1 - Aug 31, 2024, a copy of Facebook's (Facebook's are real; Instagram's should be blank).
  The rules and thresholds are in `wtstats/config.py`.
- **People reached** for Facebook is Reach through Aug 2025 and Viewers from Sep 2025 (they agree in Aug 2025, when both were recorded). The chart marks the change with a dotted line (`CHART_BREAKS` in `wtstats/config.py`).
- **LinkedIn followers** come from the manually filled sheets through Dec 2024 and LinkedIn's own export from Oct 16, 2025. Jan 1 - Oct 15, 2025 was never recorded and is lost (the Data tab lists it as a gap, with a note).
- **Instagram interactions** for Jun 2025 and Aug 1-21, 2025 can't be filled: Meta's *Content interactions* only exists from Aug 22, 2025, and its export shows 0 before that (not available, not zero).
- **Gaps** (days with no value) are listed on the *Data & quality* tab. A blank is not a zero, so totals that include them are understated.
- Small negatives (-1) in TikTok comments and LinkedIn comments or reposts are deletions in the export and are kept; follower changes are net and can be negative.
- Scheduler totals are as of the export and are kept apart from the account-level numbers, because they measure different things.
- Dates are used as exported. The scheduler's date is the published date in Pacific time.

Channel rules (which columns identify a platform, what to drop, blank handling, YouTube series, dashboard metric groups) are all in `wtstats/config.py`.

## Reading the dashboard

- **Over time** or **Year over year** (Overview and Channels): year over year lays every year with data over Jan-Dec, one
  line per year (each year has its own colour; the latest is the thickest). It uses whole months or weeks only, ignores the date range, and each card compares
  the year so far with the same dates a year earlier. Running totals (TikTok follower total) are left out.
- **YouTube:** the tab opens with the channel's subscribers, then its views, then views by series. Group the monthly files by **Month**, **Year** or **Year over year**. *Channel subscribers* shows the whole
  channel's net subscribers per month.
- A dotted line marks where a measure changes (`CHART_BREAKS`).

## YouTube series and subscribers

- **Series.** A video's series is, in order: the owner's choice in `data/youtube_series.csv` (columns `video_id,series`), else
  its playlist (a `Playlist` column in the export, if you add one), else the title rules in `wtstats/config.py`
  (`SERIES_RULES`; the first match wins). After changing any of these, run `python -m wtstats reclassify`.
- Every format is its own series, named like its YouTube playlist (WikiTree Week and WikiGames are separate; so are Tech Talk and
  Link Builders, Ask Aleš and Member Q&A). Where a title *starts* decides between look-alikes: "#ConnectionFinder: ..." is
  ConnectionFinder, while "Are you related ..." is Spotlight Profile Shorts even when it ends with the #ConnectionFinder tag.
  Videos that match no rule are listed as "Other"; `data/youtube_series.csv` files individual videos (the Nov 2024 Symposium sessions have no
  identifying words in their titles, so they are listed there).
- **Channel subscribers and views.** The whole channel's net subscribers and views per month. **A month's per-video export is the source:**
  its *Total* row is stored as that month's channel number (it covers every video, so it is higher than the sum of the listed ones, which
  are capped at 500). For months with no export, use a sheet or YouTube Studio's chart export as `Date,Subscribers,Views` and run
  `python -m wtstats import --monthly "Chart data.csv"`; `--monthly` treats every row as a whole month, whatever its date looks like.
  A sheet never replaces a month that has an export, whichever is loaded first. Every month from Jan 2021 to Sep 2026 now has an export.
- **Community posts.** The export mixes videos with community-page posts. It has no column for that, so any item with a duration of exactly
  16 seconds (`COMMUNITY_POST_DURATION_S`) is shown as a community post; the YouTube tab can show videos, posts or both.

## Hosting (Streamlit Community Cloud)

The repository contains the data (`data/raw/` and the built `data/stats.db`), so the app can run straight from it.

1. Go to https://share.streamlit.io and sign in with GitHub.
2. *Create app* -> pick this repository, branch `main`, main file `app.py`.
3. Under *Advanced settings* choose Python 3.12 or 3.13. Deploy.

The hosted copy is read-only and public. Its disk is reset on every restart, so new data can only arrive through a commit.

## Monthly update

1. Download the month's exports (use the same saved view for YouTube; put the month in its file name).
2. `python -m wtstats import <the new files>` and check `python -m wtstats status`.
3. Commit `data/` and push. The hosted app redeploys by itself.

Files that were already imported are skipped, so re-running with the whole folder is safe.

## Versions

The version lives in `wtstats/__init__.py` (`python -m wtstats --version`) and is shown in the dashboard sidebar. Bump it and add an entry to `CHANGELOG.md` for each release; a test fails if the two disagree.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Limits of the data

- The scheduler exports one row per channel per day (totals for that day's posts), not one row per post. The dashboard can say which days did well, not which individual post. "Per post" on the Posts tab is the day's total divided by the number of posts that day.
- Threads, Bluesky and Mastodon only appear through the scheduler export, so they have no account-level history.
