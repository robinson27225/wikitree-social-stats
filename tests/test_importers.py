import sqlite3

import pytest

from wtstats import db
from wtstats.importers import ImportError_, classify_series, detect_kind, import_file, parse_number, parse_period


@pytest.fixture
def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    return conn, tmp_path / "raw", tmp_path


def write(tmp, name, text):
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def run(env, name, text, **kw):
    conn, raw, tmp = env
    return import_file(conn, write(tmp, name, text), raw_dir=raw, **kw)


def rows(conn, sql, *a):
    return conn.execute(sql, a).fetchall()


def test_parse_helpers():
    assert parse_number('"2,299"'.strip('"')) == 2299.0
    assert parse_number("") is None and parse_number(" ") is None
    assert parse_period("01/31/2026") == ("day", "2026-01-31")
    assert parse_period("2026-02") == ("month", "2026-02-01")
    assert parse_period("Mar 2026") == ("month", "2026-03-01")
    with pytest.raises(ImportError_):
        parse_period("last week")


def test_detect_kind():
    assert detect_kind({"date", "page_visits", "new_likes"}) == ("daily", "facebook")
    assert detect_kind({"date", "channel", "platform", "posts", "views"})[0] == "scheduler"
    assert detect_kind({"content", "video_title", "views"})[0] == "youtube"
    with pytest.raises(ImportError_):
        detect_kind({"a", "b"})


FB = """Date,Reach,Page Visits,New Likes,Link Clicks,Interactions,Views,Viewers
01/01/2026,,5,2,5,59,"2,299",866
01/02/2026,,20,3,20,29,"2,295",985
04/02/2026,,20,4,2,22,9,592
10/01/2026,,,,,,,
"""


def test_facebook_commas_empty_rows_and_flags(env):
    conn = env[0]
    r = run(env, "fb.csv", FB)
    assert (r["rows_read"], r["rows_loaded"]) == (4, 3)  # the pre-filled empty date is skipped
    assert rows(conn, "SELECT value FROM daily_metrics WHERE period_start='2026-01-01' AND metric='views'") == [(2299.0,)]
    assert not rows(conn, "SELECT 1 FROM daily_metrics WHERE metric='reach'")  # blank column stores nothing
    flags = rows(conn, "SELECT period_start, metric FROM data_flags")
    assert ("2026-04-02", "views") in flags  # fewer views than viewers


def test_duplicate_column_month_is_flagged(env):
    conn = env[0]
    lines = ["Date,Reach,Page Visits,New Likes,Link Clicks,Interactions,Views,Viewers"]
    lines += [f"01/{d:02d}/2026,,{d},1,{d},5,100,50" for d in range(1, 21)]
    run(env, "fb.csv", "\n".join(lines) + "\n")
    assert rows(conn, "SELECT COUNT(*) FROM data_flags WHERE metric='link_clicks'") == [(20,)]


def test_reimport_is_skipped_and_never_blanks_values(env):
    conn = env[0]
    run(env, "fb.csv", FB)
    assert run(env, "fb.csv", FB)["status"] == "skipped"
    # a later file with a blank for an already stored cell must not erase it
    run(env, "fb2.csv", "Date,Reach,Page Visits,New Likes,Link Clicks,Interactions,Views,Viewers\n01/01/2026,,5,,5,59,,866\n")
    assert rows(conn, "SELECT value FROM daily_metrics WHERE period_start='2026-01-01' AND metric='views'") == [(2299.0,)]


def test_raw_file_is_archived_untouched(env):
    _, raw, tmp = env
    run(env, "fb.csv", FB)
    archived = list(raw.glob("*_fb.csv"))
    assert len(archived) == 1 and archived[0].read_text() == FB


IG = "Date,Reach,Profile Visits,New Followers,Interactions,Views\n01/06/2026,147,1,,4,252\n01/07/2026,67,1,1,9,193\n"


def test_instagram_blank_new_followers_is_zero(env):
    conn = env[0]
    run(env, "ig.csv", IG)
    assert rows(conn, "SELECT value FROM daily_metrics WHERE metric='new_followers' ORDER BY period_start") == [(0.0,), (1.0,)]


TT = """Date,Video views,Profile views,Likes,Comments,Shares,Followers,Total Viewers,New Viewers,Returning Viewers
08/30/2026,13,0,0,0,0,-2,119,92,27
08/31/2026,9,0,0,0,0,1,13,10,3
09/01/2026,164,1,1,0,0,613,8,,
09/02/2026,157,0,3,0,0,615,151,,
"""


def test_tiktok_followers_change_then_total(env):
    conn = env[0]
    run(env, "tt.csv", TT)
    got = dict(rows(conn, "SELECT period_start || ':' || metric, value FROM daily_metrics WHERE metric LIKE 'followers%'"))
    assert got["2026-08-30:followers_change"] == -2.0
    assert got["2026-09-01:followers_total"] == 613.0
    assert "2026-09-01:followers_change" not in got  # no previous total to subtract
    assert got["2026-09-02:followers_change"] == 2.0  # derived from consecutive totals


LI = "Date,Impressions ,Clicks ,Reactions ,Comments ,Reposts ,Engagement rate ,Overview page views,Overview unique visitors,Total page views,Total unique visitors\n01/01/2026,51,1,5,1,1,0.15,0,0,0,0\n"


def test_linkedin_trailing_space_headers_and_dropped_rate(env):
    conn = env[0]
    run(env, "li.csv", LI)
    metrics = {m for (m,) in rows(conn, "SELECT DISTINCT metric FROM daily_metrics")}
    assert "impressions" in metrics and "clicks" in metrics and "engagement_rate" not in metrics


SCHED = """date,channel,platform,posts,posts_with_numbers,views,reach,viewers,engagements,interactions,link_clicks,visits,follows,shares,comments,likes,saves
2026-08-03,WikiTree (Facebook),facebook,1,1,2697,,1888,109,80,29,,,8,0,72,
2026-08-03,WikiTree (Instagram),instagram,1,1,631,473,,232,232,,15,4,0,11,197,24
2026-08-03,WikiTree on Bluesky,bluesky,1,1,,,,21,21,,,,14,2,5,
"""


def test_scheduler_rows_are_per_platform_channel_day(env):
    conn = env[0]
    r = run(env, "sched.csv", SCHED)
    assert r["kind"] == "scheduler" and r["notes"] == []  # all totals add up
    assert rows(conn, "SELECT value FROM post_day_metrics WHERE platform='instagram' AND metric='saves'") == [(24.0,)]
    assert not rows(conn, "SELECT 1 FROM post_day_metrics WHERE platform='bluesky' AND metric='views'")


def test_scheduler_total_mismatch_is_reported(env):
    bad = SCHED.replace(",232,232,,15,4,0,11,197,24", ",232,230,,15,4,0,11,197,24")
    r = run(env, "sched.csv", bad)
    assert any("do not equal" in n for n in r["notes"])


YT_YTD = '''Content,Video title,Video publish time,Duration,Likes,Shares,Views,Watch time (hours),Subscribers,Thumbnail impressions
MDZ13G7HSPY,What is WikiTree?,"Aug 13, 2023",91,111,85,"10,276",145.7933,167,3805
 -MQXzjRbR_E,WikiTree #SaturdayRoundup (14 Mar 2026),"Mar 14, 2026",7214,39,2,332,137.4,2,8651
0hT6pZNaMoQ,"#OneNameTuesday showcase: Sheldon
Almost 6k Sheldon profiles","Sep 8, 2026",16,0,0,23,0.0149,0,0
Showing top 500 results
'''

YT_JULY = '''Content,Video title,Video publish time,Duration,Likes,Shares,Chat messages,Reactions,Views,Subscribers
MDZ13G7HSPY,What is WikiTree?,"Aug 13, 2023",91,3,0,,,1615,1
 -MQXzjRbR_E,WikiTree #SaturdayRoundup (14 Mar 2026),"Mar 14, 2026",7214,0,0,12,2,40,0
Showing top 500 results
'''


def test_youtube_period_from_file_name_and_explicit(env):
    conn = env[0]
    r = run(env, "WikiTreers_YT_July_2026.csv", YT_JULY)
    assert any("2026-07-01 to 2026-07-31" in n for n in r["notes"])
    r = run(env, "Table_data.csv", YT_YTD, period="2026-01-01:2026-10-17")
    assert rows(conn, "SELECT DISTINCT period_start, period_end FROM youtube_stats ORDER BY 1") == [
        ("2026-01-01", "2026-10-17"), ("2026-07-01", "2026-07-31")]


def test_youtube_file_without_a_period_is_refused_but_archived(env):
    conn, raw, _ = env
    with pytest.raises(ImportError_, match="which period"):
        run(env, "Table_data.csv", YT_YTD)
    assert list(raw.glob("*_Table_data.csv"))  # the raw copy is kept
    assert rows(conn, "SELECT COUNT(*) FROM youtube_stats") == [(0,)]
    with pytest.raises(ImportError_, match="unrecognised period"):
        run(env, "Table_data.csv", YT_YTD, period="2026")


def test_youtube_each_file_keeps_its_own_columns(env):
    conn = env[0]
    run(env, "WikiTreers_YT_July_2026.csv", YT_JULY)
    run(env, "Table_data.csv", YT_YTD, period="2026-01-01:2026-10-17")
    metrics = lambda start: {m for (m,) in rows(conn, "SELECT DISTINCT metric FROM youtube_stats WHERE period_start = ?", start)}
    assert {"chat_messages", "reactions"} <= metrics("2026-07-01") and "watch_time_hours" not in metrics("2026-07-01")
    assert {"watch_time_hours", "thumbnail_impressions"} <= metrics("2026-01-01") and "reactions" not in metrics("2026-01-01")
    # a blank cell (no chat on a non-live video) stores nothing instead of 0
    assert not rows(conn, "SELECT 1 FROM youtube_stats WHERE video_id='MDZ13G7HSPY' AND metric='chat_messages'")


def test_youtube_periods_do_not_overwrite_each_other(env):
    conn = env[0]
    run(env, "WikiTreers_YT_July_2026.csv", YT_JULY)
    run(env, "WikiTreers_YT_August_2026.csv", YT_JULY.replace("1615", "1850"))
    assert rows(conn, "SELECT period_start, value FROM youtube_stats WHERE video_id='MDZ13G7HSPY' AND metric='views' ORDER BY 1") == [
        ("2026-07-01", 1615.0), ("2026-08-01", 1850.0)]


def test_youtube_ids_with_leading_space_multiline_titles_footer_and_series(env):
    conn = env[0]
    r = run(env, "Table_data.csv", YT_YTD, period="2026-01-01:2026-10-17")
    assert r["rows_loaded"] == 3
    assert not any("capped" in n for n in r["notes"])  # 3 videos listed, footer says up to 500
    assert rows(conn, "SELECT value FROM youtube_stats WHERE video_id='-MQXzjRbR_E' AND metric='views'") == [(332.0,)]
    assert rows(conn, "SELECT value FROM youtube_stats WHERE video_id='MDZ13G7HSPY' AND metric='views'") == [(10276.0,)]
    assert rows(conn, "SELECT title FROM youtube_videos WHERE video_id='0hT6pZNaMoQ'") == [
        ("#OneNameTuesday showcase: Sheldon Almost 6k Sheldon profiles",)]
    assert rows(conn, "SELECT series FROM youtube_videos WHERE video_id='-MQXzjRbR_E'") == [("Saturday Roundup",)]


def test_youtube_export_at_its_row_cap_is_noted(env):
    r = run(env, "WikiTreers_YT_July_2026.csv", YT_JULY.replace("top 500", "top 2"))
    assert any("capped at the top 2" in n for n in r["notes"])


def test_period_helpers():
    from wtstats.importers import infer_period_from_name, parse_period_arg
    assert infer_period_from_name("855f153d-WikiTreers_YT_July_2026.csv") == ("2026-07-01", "2026-07-31")
    assert infer_period_from_name("yt_Feb_2028.csv") == ("2028-02-01", "2028-02-29")
    assert infer_period_from_name("export_2026-08.csv") == ("2026-08-01", "2026-08-31")
    assert infer_period_from_name("Table_data.csv") is None
    assert parse_period_arg("2026-12") == ("2026-12-01", "2026-12-31")
    with pytest.raises(ImportError_):
        parse_period_arg("2026-13")
    with pytest.raises(ImportError_):
        parse_period_arg("2026-10-17:2026-01-01")


def test_classify_series():
    assert classify_series("#SourceAThon - 2 Oct 2026 8AM ET Kick-Off  Livecast") == "SourceAThon"
    assert classify_series("WikiTree #SaturdayRoundup (21 Feb 2026)") == "Saturday Roundup"
    assert classify_series("What is WikiTree?") == "Other"
