"""Turn stored metrics into the daily series the dashboard plots."""
from __future__ import annotations

import pandas as pd


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
