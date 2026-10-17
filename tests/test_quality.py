import pandas as pd
import pytest

from wtstats import db, quality
from wtstats.series import daily_series


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "q.db")


def put(conn, platform, metric, values, start="2024-01-01"):
    days = pd.date_range(start, periods=len(values))
    conn.executemany(
        "INSERT OR REPLACE INTO daily_metrics VALUES (?, 'day', ?, ?, ?, NULL)",
        [(platform, d.date().isoformat(), metric, float(v)) for d, v in zip(days, values) if v is not None])


def flags(conn):
    return conn.execute("SELECT platform, period_start, metric FROM data_flags").fetchall()


def test_same_interactions_on_facebook_and_instagram_flags_both(conn):
    vals = [100 + (i * 7) % 40 for i in range(31)]            # January 2024: identical on both
    put(conn, "facebook", "interactions", vals); put(conn, "instagram", "interactions", vals)
    put(conn, "facebook", "interactions", [50 + i for i in range(29)], start="2024-02-01")   # February: genuinely different
    put(conn, "instagram", "interactions", [10 + 2 * i for i in range(29)], start="2024-02-01")
    quality.rebuild_flags(conn)
    got = flags(conn)
    assert {p for p, d, m in got if d.startswith("2024-01")} == {"facebook", "instagram"}
    assert not [f for f in got if f[1].startswith("2024-02")]


def test_instagram_new_followers_copied_from_profile_visits_is_flagged_for_that_month(conn):
    vis = [3, 0, 1, 4, 2] * 6 + [3]
    put(conn, "instagram", "profile_visits", vis, start="2022-10-01")
    put(conn, "instagram", "new_followers", vis, start="2022-10-01")
    put(conn, "instagram", "profile_visits", [2, 3, 1] * 10, start="2022-11-01")
    put(conn, "instagram", "new_followers", [1, 0, 0] * 10, start="2022-11-01")
    quality.rebuild_flags(conn)
    got = flags(conn)
    assert len(got) == 31 and {(p, m) for p, d, m in got} == {("instagram", "new_followers")}


def test_facebook_reach_far_below_viewers_is_flagged_but_agreeing_days_are_not(conn):
    put(conn, "facebook", "viewers", [600, 620, 580, 640], start="2025-08-30")
    put(conn, "facebook", "reach", [610, 600, 40, 55], start="2025-08-30")      # agrees, agrees, then collapses
    put(conn, "facebook", "views", [900, 5, 1000, 1000], start="2025-08-30")     # 5 views from 620 viewers is impossible
    quality.rebuild_flags(conn)
    assert sorted(flags(conn)) == [("facebook", "2025-08-31", "views"), ("facebook", "2025-09-01", "reach"),
                                   ("facebook", "2025-09-02", "reach")]


def test_find_gaps_reports_ranges_and_groups_metrics(conn):
    put(conn, "instagram", "interactions", [5, None, None, 7, 8, None, 9])
    put(conn, "instagram", "reach", [1, 2, 3, 4, 5, 6, 7])
    put(conn, "linkedin", "comments", [1, 1, None, 1]); put(conn, "linkedin", "clicks", [1, 1, None, 1])
    g = quality.find_gaps(conn)
    assert g[["platform", "first_missing", "last_missing", "days", "metrics"]].values.tolist() == [
        ["instagram", "2024-01-02", "2024-01-03", 2, "interactions"],
        ["instagram", "2024-01-06", "2024-01-06", 1, "interactions"],
        ["linkedin", "2024-01-03", "2024-01-03", 1, "clicks, comments"]]


def test_daily_series_sums_metrics_and_falls_back_when_one_is_missing():
    rows = []
    for d, reach, viewers in [("2025-08-31", 600, 610), ("2025-09-01", None, 640), ("2025-09-02", None, 650)]:
        for metric, v in (("reach", reach), ("viewers", viewers)):
            if v is not None:
                rows.append(("facebook", "day", pd.Timestamp(d), metric, float(v)))
    daily = pd.DataFrame(rows, columns=["platform", "granularity", "period_start", "metric", "value"])
    s = daily_series(daily, "facebook", ["reach|viewers"])
    assert s.tolist() == [600.0, 640.0, 650.0]                   # reach where there is one (not summed with viewers), else viewers
    assert daily_series(daily, "facebook", ["reach", "viewers"]).iloc[0] == 1210.0   # plain list still sums
    assert daily_series(daily, "tiktok", ["video_views"]).empty
