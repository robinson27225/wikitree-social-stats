"""Turn stored metrics into the daily series the dashboard plots."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def daily_series(daily: pd.DataFrame, platform: str, metrics: list[str]) -> pd.Series:
    """One value per day for a platform: the listed metrics summed.

    An entry like "reach|viewers" means "reach, and where reach is missing, viewers" (a measure that was
    renamed or replaced). `daily` needs the columns platform, granularity, period_start, metric, value;
    values the quality rules flagged should already be removed.
    """
    day = daily[(daily["platform"] == platform) & (daily["granularity"] == "day")]
    wide = day.pivot_table(index="period_start", columns="metric", values="value", aggfunc="sum")
    parts = []
    for entry in metrics:
        cols = [wide[name] for name in entry.split("|") if name in wide.columns]
        if not cols:
            continue
        s = cols[0]
        for fallback in cols[1:]:
            s = s.combine_first(fallback)
        parts.append(s)
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).sum(axis=1, min_count=1).dropna().sort_index()


def yoy_table(s: pd.Series, rollup: str = "Month") -> pd.DataFrame:
    """Year-over-year layout of a daily series: one row per month (1-12) or week (1-52), one column per year.

    Each cell is that month's or week's total. Only complete buckets are used: a month or week that starts
    before the series does, or ends after it, would look like a false dip, so it is left out (as is week 53).
    """
    s = s.dropna().sort_index()
    if s.empty:
        return pd.DataFrame()
    first, last = s.index.min().normalize(), s.index.max().normalize()
    if rollup == "Week":
        start = s.index.to_period(config.WEEK_PERIOD).start_time
        end = start + pd.Timedelta(days=6)
        pos = (start.dayofyear.to_numpy() - 1) // 7 + 1  # a week starting Dec 29-31 would be week 53; it straddles the year-end, so it is dropped
    else:
        start = s.index.to_period("M").start_time
        end = start + pd.offsets.MonthEnd(0)
        pos = start.month.to_numpy()
    df = pd.DataFrame({"start": start, "end": end, "pos": pos, "year": start.year.to_numpy(), "value": s.to_numpy()})
    g = df.groupby(["start", "end", "pos", "year"], as_index=False)["value"].sum()
    g = g[(g["start"] >= first) & (g["end"] <= last) & (g["pos"] <= 52)]
    return g.pivot(index="pos", columns="year", values="value").sort_index() if len(g) else pd.DataFrame()


def ytd_vs_prior(s: pd.Series) -> dict | None:
    """The latest year's total so far, and the same dates a year earlier (None if the series doesn't reach back that far)."""
    s = s.dropna().sort_index()
    if s.empty:
        return None
    last = s.index.max()
    y0 = pd.Timestamp(last.year, 1, 1)
    p0, p1 = y0 - pd.DateOffset(years=1), last - pd.DateOffset(years=1)
    return {"year": last.year, "last": last, "cur": float(s[y0:last].sum()),
            "prev": float(s[p0:p1].sum()) if s.index.min() <= p0 else None}
