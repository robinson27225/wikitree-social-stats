"""Rules that derive values from, or flag problems in, what has been imported."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from . import config


def scheduler_row_mismatch(v: dict[str, float | None]) -> int:
    """1 if the row's interactions/engagements don't equal the sum of their parts, else 0.

    interactions = likes + shares + comments (+ saves on Instagram);
    engagements  = interactions (+ link clicks on Facebook).
    """
    z = lambda k: v.get(k) or 0.0
    bad = False
    if v.get("interactions") is not None:
        bad |= v["interactions"] != z("likes") + z("shares") + z("comments") + z("saves")
    if v.get("engagements") is not None and v.get("interactions") is not None:
        bad |= v["engagements"] not in (v["interactions"], v["interactions"] + z("link_clicks"))
    return int(bad)


def derive_tiktok_follower_change(conn: sqlite3.Connection) -> None:
    """From the follower running total, derive the net daily change (needs the previous day)."""
    rows = conn.execute(
        """SELECT period_start, value FROM daily_metrics
           WHERE platform = 'tiktok' AND granularity = 'day' AND metric = 'followers_total'
           ORDER BY period_start"""
    ).fetchall()
    out = []
    for (d0, v0), (d1, v1) in zip(rows, rows[1:]):
        if date.fromisoformat(d1) - date.fromisoformat(d0) == timedelta(days=1):
            out.append(("tiktok", "day", d1, "followers_change", v1 - v0))
    conn.executemany(
        """INSERT INTO daily_metrics (platform, granularity, period_start, metric, value, import_id)
           VALUES (?,?,?,?,?,NULL)
           ON CONFLICT (platform, granularity, period_start, metric)
           DO UPDATE SET value = excluded.value WHERE daily_metrics.import_id IS NULL""",
        out,
    )


def rebuild_flags(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM data_flags")

    # Facebook: a day cannot have fewer views than viewers.
    conn.execute(
        """INSERT OR IGNORE INTO data_flags
           SELECT 'daily', v.platform, v.period_start, 'views',
                  'views (' || CAST(v.value AS INT) || ') is lower than viewers (' || CAST(w.value AS INT) || '); likely a bad value in the export'
           FROM daily_metrics v JOIN daily_metrics w
             ON w.platform = v.platform AND w.granularity = v.granularity
            AND w.period_start = v.period_start AND w.metric = 'viewers'
           WHERE v.platform = 'facebook' AND v.granularity = 'day' AND v.metric = 'views' AND v.value < w.value"""
    )

    # Copy-paste columns: a month where one column mirrors another is not real data.
    for platform, metric, twin in config.DUPLICATE_COLUMN_CHECKS:
        df = pd.read_sql_query(
            """SELECT a.period_start, a.value AS a, b.value AS b
               FROM daily_metrics a JOIN daily_metrics b
                 ON b.platform = a.platform AND b.granularity = a.granularity
                AND b.period_start = a.period_start AND b.metric = ?
               WHERE a.platform = ? AND a.granularity = 'day' AND a.metric = ?""",
            conn, params=(twin, platform, metric),
        )
        if df.empty:
            continue
        df["month"] = df["period_start"].str[:7]
        for month, g in df.groupby("month"):
            if len(g) >= config.DUPLICATE_MIN_DAYS and (g["a"] == g["b"]).all() and g["a"].sum() > 0:
                conn.executemany(
                    "INSERT OR IGNORE INTO data_flags VALUES ('daily', ?, ?, ?, ?)",
                    [(platform, d, metric, f"identical to {twin} on every day of {month}; the export repeated that column")
                     for d in g["period_start"]],
                )
