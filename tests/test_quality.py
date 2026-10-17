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


def _two_months_of_interactions(conn):
    vals = [100 + (i * 7) % 40 for i in range(31)]            # January 2024: identical on both
    put(conn, "facebook", "interactions", vals); put(conn, "instagram", "interactions", vals)
    put(conn, "facebook", "interactions", [50 + i for i in range(29)], start="2024-02-01")   # February: genuinely different
    put(conn, "instagram", "interactions", [10 + 2 * i for i in range(29)], start="2024-02-01")


def test_interactions_copied_into_instagram_flags_only_the_side_that_is_wrong(conn):
    _two_months_of_interactions(conn)
    quality.rebuild_flags(conn)
    got = flags(conn)
    assert {p for p, d, m in got if d.startswith("2024-01")} == {"instagram"}      # Facebook's are real
    assert not [f for f in got if f[1].startswith("2024-02")]


def test_cross_platform_duplicate_flags_both_when_it_is_not_known_which_is_right(conn, monkeypatch):
    from wtstats import config
    monkeypatch.setattr(config, "CROSS_PLATFORM_DUPLICATE_CHECKS", [("facebook", "instagram", "interactions", "both")])
    _two_months_of_interactions(conn)
    quality.rebuild_flags(conn)
    assert {p for p, d, m in flags(conn) if d.startswith("2024-01")} == {"facebook", "instagram"}


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


def _daily(start, end, per_day=1.0, hole=None):
    idx = pd.date_range(start, end)
    s = pd.Series(per_day, index=idx)
    return s.drop(pd.to_datetime(hole)) if hole is not None else s


def test_yoy_table_has_a_column_per_year_and_drops_incomplete_months():
    from wtstats.series import yoy_table
    s = _daily("2023-05-03", "2025-10-15")          # starts mid-May 2023, ends mid-Oct 2025
    t = yoy_table(s, "Month")
    assert list(t.columns) == [2023, 2024, 2025]
    assert pd.isna(t.loc[5, 2023]) and t.loc[6, 2023] == 30          # May 2023 started on the 3rd, so it is left out
    assert pd.isna(t.loc[10, 2025]) and t.loc[9, 2025] == 30         # Oct 2025 stops on the 15th, so it is left out
    assert t.loc[2, 2024] == 29 and t.loc[2, 2025] == 28             # leap year handled by the calendar


def test_yoy_table_weeks_use_whole_weeks_only():
    from wtstats.series import yoy_table
    t = yoy_table(_daily("2024-01-03", "2025-02-20"), "Week")        # Wed start, Thu end
    vals = t.to_numpy().ravel()
    assert (vals[~pd.isna(vals)] == 7).all()                         # every filled cell is exactly one whole week
    assert pd.isna(t.loc[1, 2024])                                   # the first, partial week is out
    assert t.index.max() <= 52                                       # a week starting Dec 29-31 (week 53) is out


def test_yoy_table_empty_series():
    from wtstats.series import yoy_table
    assert yoy_table(pd.Series(dtype=float)).empty


def test_ytd_vs_prior_compares_the_same_dates():
    from wtstats.series import ytd_vs_prior
    s = _daily("2025-01-01", "2026-03-10")
    r = ytd_vs_prior(s)
    assert r["year"] == 2026 and r["cur"] == 69 and r["prev"] == 69   # Jan 1-Mar 10 each year (2026 has no leap day)
    assert ytd_vs_prior(_daily("2025-06-01", "2026-03-10"))["prev"] is None   # no data back to Jan 1, 2025
