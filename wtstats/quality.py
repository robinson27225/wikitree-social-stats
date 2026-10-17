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

    # A metric far below one it should not be below (e.g. Facebook views under viewers).
    for platform, metric, other, factor, reason in config.BELOW_CHECKS:
        why = reason or f"{metric} is {'lower than' if factor >= 1 else 'far below'} {other} that day; the export value cannot be right"
        conn.execute(
            """INSERT OR IGNORE INTO data_flags
               SELECT 'daily', v.platform, v.period_start, v.metric, ?
               FROM daily_metrics v JOIN daily_metrics w
                 ON w.platform = v.platform AND w.granularity = v.granularity
                AND w.period_start = v.period_start AND w.metric = ?
               WHERE v.platform = ? AND v.granularity = 'day' AND v.metric = ? AND v.value < w.value * ?""",
            (why, other, platform, metric, factor),
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
        for month, days in _mirrored_months(df):
            conn.executemany(
                "INSERT OR IGNORE INTO data_flags VALUES ('daily', ?, ?, ?, ?)",
                [(platform, d, metric, f"identical to {twin}; the export repeated that column") for d in days],
            )

    # The same metric identical on two platforms: one sheet was pasted over the other, so flag both.
    for plat_a, plat_b, metric, flag in config.CROSS_PLATFORM_DUPLICATE_CHECKS:
        df = pd.read_sql_query(
            """SELECT a.period_start, a.value AS a, b.value AS b
               FROM daily_metrics a JOIN daily_metrics b
                 ON b.granularity = a.granularity AND b.period_start = a.period_start AND b.metric = a.metric
               WHERE a.platform = ? AND b.platform = ? AND a.granularity = 'day' AND a.metric = ?""",
            conn, params=(plat_a, plat_b, metric),
        )
        for month, days in _mirrored_months(df):
            for platform, other in ((plat_a, plat_b), (plat_b, plat_a)):
                if flag not in ("both", platform):
                    continue
                conn.executemany(
                    "INSERT OR IGNORE INTO data_flags VALUES ('daily', ?, ?, ?, ?)",
                    [(platform, d, metric, f"identical to {other}'s {metric}; copied from there, so not this channel's own figure" if flag != "both" else f"identical to {other}'s {metric}; one sheet was pasted over the other")
                     for d in days],
                )


def _mirrored_months(df: pd.DataFrame):
    """Yield (month, [days]) for months where columns a and b match on nearly every day."""
    if df.empty:
        return
    df = df.assign(month=df["period_start"].str[:7])
    for month, g in df.groupby("month"):
        if len(g) >= config.DUPLICATE_MIN_DAYS and (g["a"] == g["b"]).mean() >= 0.95 and g["a"].sum() > 0:
            yield month, list(g["period_start"])


def find_gaps(conn: sqlite3.Connection) -> pd.DataFrame:
    """Days with no value for a metric between its first and last recorded day, as ranges.

    A blank is not a zero: weekly and monthly totals that include these days are understated.
    Columns: platform, first_missing, last_missing, days, metrics.
    """
    d = pd.read_sql_query(
        "SELECT platform, metric, period_start FROM daily_metrics WHERE granularity = 'day'", conn, parse_dates=["period_start"])
    rows = []
    for (platform, metric), g in d.groupby(["platform", "metric"]):
        days = pd.DatetimeIndex(sorted(g["period_start"].unique()))
        missing = pd.date_range(days.min(), days.max()).difference(days)
        if missing.empty:
            continue
        start = prev = missing[0]
        for day in list(missing[1:]) + [None]:
            if day is not None and (day - prev).days == 1:
                prev = day
                continue
            rows.append((platform, start.date().isoformat(), prev.date().isoformat(), (prev - start).days + 1, metric))
            if day is not None:
                start = prev = day
    if not rows:
        return pd.DataFrame(columns=["platform", "first_missing", "last_missing", "days", "metrics"])
    out = pd.DataFrame(rows, columns=["platform", "first_missing", "last_missing", "days", "metric"])
    return (out.groupby(["platform", "first_missing", "last_missing", "days"])["metric"]
               .apply(lambda m: ", ".join(sorted(m))).rename("metrics").reset_index()
               .sort_values(["platform", "first_missing"]).reset_index(drop=True))
