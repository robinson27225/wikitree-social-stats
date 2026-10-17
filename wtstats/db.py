"""SQLite schema and connection helper."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
-- Replaced by youtube_stats (a snapshot date could not say which period a file covers).
-- Its rows came from files kept in data/raw, so re-import them with --force and --period.
DROP TABLE IF EXISTS youtube_snapshots;

CREATE TABLE IF NOT EXISTS import_log (
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL,            -- daily | scheduler | youtube
    platform      TEXT,
    source_name   TEXT NOT NULL,
    sha256        TEXT NOT NULL UNIQUE,
    archived_path TEXT NOT NULL,
    rows_read     INTEGER,
    rows_loaded   INTEGER,
    imported_at   TEXT NOT NULL,
    notes         TEXT
);

-- Account-level numbers straight from each platform's own daily or monthly export.
CREATE TABLE IF NOT EXISTS daily_metrics (
    platform     TEXT NOT NULL,
    granularity  TEXT NOT NULL CHECK (granularity IN ('day', 'month')),
    period_start TEXT NOT NULL,             -- ISO date; first of month for 'month'
    metric       TEXT NOT NULL,
    value        REAL NOT NULL,
    import_id    INTEGER REFERENCES import_log(id),   -- NULL = derived by the loader
    PRIMARY KEY (platform, granularity, period_start, metric)
);

-- Scheduler output: totals for the posts published on a given day, per channel.
-- Not comparable to daily_metrics (post-attributed, counted as of export).
CREATE TABLE IF NOT EXISTS post_day_metrics (
    platform  TEXT NOT NULL,
    channel   TEXT NOT NULL,
    date      TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL NOT NULL,
    import_id INTEGER REFERENCES import_log(id),
    PRIMARY KEY (platform, channel, date, metric)
);

CREATE TABLE IF NOT EXISTS youtube_videos (
    video_id       TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    published_date TEXT,
    duration_s     INTEGER,
    series         TEXT NOT NULL
);

-- Per-video numbers for a period: one calendar month (the monthly exports) or a
-- date range (e.g. year to date). Periods can overlap, so rows from different
-- periods must not be added together.
CREATE TABLE IF NOT EXISTS youtube_stats (
    video_id     TEXT NOT NULL REFERENCES youtube_videos(video_id),
    period_start TEXT NOT NULL,
    period_end   TEXT NOT NULL,
    metric       TEXT NOT NULL,
    value        REAL NOT NULL,
    import_id    INTEGER REFERENCES import_log(id),
    PRIMARY KEY (video_id, period_start, period_end, metric)
);

-- Values the dashboard leaves out. Rebuilt from the rules in quality.py on every import.
CREATE TABLE IF NOT EXISTS data_flags (
    scope        TEXT NOT NULL,             -- daily
    platform     TEXT NOT NULL,
    period_start TEXT NOT NULL,
    metric       TEXT NOT NULL,
    reason       TEXT NOT NULL,
    PRIMARY KEY (scope, platform, period_start, metric)
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
