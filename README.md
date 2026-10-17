# WikiTree Social Stats

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
| Excel workbook (`.xlsx`) with one tab per channel and year | every recognised tab loaded the same way; Twitter tabs and other tabs are skipped and reported |
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
- **Excel workbooks:** each tab is logged as its own import. The archived copy leaves out tabs that were skipped on purpose
  (Twitter, see `SKIP_SHEET_PATTERNS`), because the repository is public. Older header names are mapped onto the current
  ones (`Impressions (total)` -> `impressions`, TikTok 2023 `New Followers` -> daily follower change); a repeated header or
  date-only block further down a tab is ignored.
- Monthly history files work the same way; a date like `2026-01` or `Jan 2026` is stored as a month.

## How the numbers are handled

- Empty future rows (the sheets are pre-filled to Dec 31) are skipped, not stored as zeros.
- Numbers with thousands separators (`"2,299"`) are read correctly.
- **Instagram:** a blank *New Followers* is stored as 0.
- **TikTok:** *Followers* was a daily change until Aug 31, 2026 and a running total after. The total is stored as `followers_total`; the daily change after the cutover is derived from consecutive days. The cutover date is `TIKTOK_FOLLOWERS_TOTAL_FROM` in `wtstats/config.py`.
- **LinkedIn:** the engagement rate is not stored (recompute it from the counts).
- **Flagged values** are kept in the database but left out of the charts, and listed on the *Data & quality* tab:
  - Facebook *Views* below *Viewers* (Apr 2-3, 2026);
  - Facebook *Reach* far below *Viewers* (Sep 2025: Reach collapses while Viewers carries on);
  - columns copied from another (Facebook *Link Clicks* = *Page Visits* in Jan 2026; Instagram *New Followers* = *Profile Visits* in Oct 2022);
  - Facebook and Instagram *Interactions*, identical Jan 1 - Aug 31, 2024 (both flagged, because we can't tell which sheet is right).
  The rules and thresholds are in `wtstats/config.py`.
- **People reached** for Facebook is Reach through Aug 2025 and Viewers after (they agree in Aug 2025, when both were recorded).
- **Gaps** (days with no value) are listed on the *Data & quality* tab. A blank is not a zero, so totals that include them are understated.
- Small negatives (-1) in TikTok comments and LinkedIn comments or reposts are deletions in the export and are kept; follower changes are net and can be negative.
- Scheduler totals are as of the export and are kept apart from the account-level numbers, because they measure different things.
- Dates are used as exported. The scheduler's date is the published date in Pacific time.

Channel rules (which columns identify a platform, what to drop, blank handling, YouTube series, dashboard metric groups) are all in `wtstats/config.py`.

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

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Limits of the data

- The scheduler exports one row per channel per day (totals for that day's posts), not one row per post. The dashboard can say which days did well, not which individual post. "Per post" on the Posts tab is the day's total divided by the number of posts that day.
- Threads, Bluesky and Mastodon only appear through the scheduler export, so they have no account-level history.
