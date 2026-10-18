import pytest

from wtstats import config, db
from wtstats.importers import classify_series, import_file, reclassify_videos, title_series


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SERIES_OVERRIDES_FILE", tmp_path / "youtube_series.csv")
    return db.connect(tmp_path / "t.db"), tmp_path / "raw", tmp_path


@pytest.mark.parametrize("title,series", [
    ("WikiTree Tech Talk (April 2026)", "Tech Talk"),
    ("Link Builders Cubicle Party (July 2026) w/host @Robinson-27225", "Link Builders Cubicle Party"),
    ("Ask Ale\u0161: What Would You Like To Know About WikiTree Plus? w/host Greg Clarke (Feb 2026)", "WikiTree Ask Ale\u0161"),
    ("Member Q & A via Zoom (Jul 2026) 1 of 2", "WikiTree Member Q&A"),
    ("Azure & Eowyn Answer Everything (19 Aug 2026) #Cemeteries Week on WikiTree", "Azure & Eowyn"),
    ("Declaration of Arbroath Connection Combat: Robert the Bruce vs Edward Longshanks", "#ConnectionCheckers"),
    ("Which #ConnectionCombat profile are you closest to MLK Jr or Henry the VIII?", "#ConnectionCheckers"),
    ("\U0001f9e9This Week's #ConnectionCheckers features New Zealand's Finest!", "#ConnectionCheckers"),
    ("WikiTree #SaturdayRoundup (21 Feb 2026)", "WikiTree Saturday Roundup"),
    ("#WikiTreeDay2023 Global Project Trailer", "WikiTree Day"),
    ("WikiTree Day: Apps w/Greg", "WikiTree Day"),
    ("WikiTree How To: Invite your family to WikiTree!", "WikiTree How To"),
    # the formats the owner said are each their own series
    ("WikiTree #CemeterySpotlight Berea Cemetery, Berea, Kentucky", "#CemeterySpotlight"),
    ("#WikiTreeWeek2025 Monday (3 Nov 2025) Panel - Beyond the Narrative", "WikiTree Week"),
    ("#2024WikiTreeWeek Countdown 5 days to go! Global Genealogy Spotlight!", "WikiTree Week"),
    ("#2024WikiGames Long-Distance Locating Winner Ceremony", "WikiGames"),
    ('WikiTree #WikiTree Friday "Night" Bingo + Bio Check App', 'Friday "Night" Bingo'),
    ("12 Days of Elf-Mas Day Ten (31 Dec 2025)", "12 Days of Elf-Mas"),
    ("#WikiTreeMeetOurMembers: Kahlil Thomas We're celebrating Kahlil", "WikiTree Meet Our Members"),
    ("WikiTree 1776 Project Research Party (4 Feb 2026)", "Research Parties"),
    ("#OneNameTuesday showcase: Sheldon", "One Name Tuesday"),
    ("Project Showcase: England This project was started on WikiTree in 2018", "Project Showcase"),
    ("What is WikiTree?", "Other"),
    ("#OnePlaceWednesday showcase: Avalon, California Explore the lives & stories", "#OnePlaceWednesday"),
    ("\U0001f333 Genealogy is better together! #GenealogyCollaborationHour TODAY at 5 PM ET", "#GenealogyCollaborationHour"),
    ("No need to swipe right! #FridayDateNight is hunting profiles with no dates", "#FridayDateNight"),
    ("WikiTree #Hacktoberfest2025 Week 1", "#Hacktoberfest"),
    # LiveCasts and Live with Sarah and Eowyn are the Saturday Roundup (owner's choice), even a LiveCast at RootsTech
    ("WikiTree LiveCast (19 September 2020) - Weekly recap + tree chat about cousin bait", "WikiTree Saturday Roundup"),
    ("WikiTree Live with Sarah and Eowyn - Special Guest Susie MacLeod", "WikiTree Saturday Roundup"),
    ("WikiTree Live: The Past & Future of WikiTree", "WikiTree Saturday Roundup"),
    ("LiveCast at RootsTech 2017", "WikiTree Saturday Roundup"),
    ("WikiTree at @familysearch #RootsTech2025 Take a tour of the booth", "RootsTech"),
    ("2024 WikiTree Symposium Countdown - 6 days to go!", "WikiTree Symposium"),
    ("#WikiTreeTours: The Power of the WikiTree Browser Extension", "WikiTree Tours"),
    ("Tree Tours - Exploring the New WikiTree!", "WikiTree Tours"),
    ("WikiTree Profile Improvement Project: Legacy Team (January 2026)", "WikiTree Profile Improvement Project"),
    ("New Member Chat (September 2025)", "WikiTree New Members"),
    ("WikiTree Heritage Exchange Video Series: #1 Intro to Heritage Exchange", "WikiTree Heritage Exchange"),
    ("WikiTree Easter Egg Hunt (2026)", "WikiTree Easter Egg Hunt"),
    ("Which King are you most closely connected to? Tudor-4", "ConnectionFinder"),
    ("Which @DoctorWho are you most closely connected to? #DoctorWho", "ConnectionFinder"),
    ("Over 500 Broadwell profiles. Countless connections. One collaborative effort. This is the power of One Name Tuesday", "One Name Tuesday"),
    ("\U0001f3ac FRIDAY SPOTLIGHT: Jason Momoa Family Connections!", "Spotlight Profile Shorts"),
    ("Ask @Ale\u0161Trtnik-e6z w/@uptergroveGreg What Do You Want To Know About WikiTree Plus? (June 2023)", "WikiTree Ask Ale\u0161"),
    ("Play this week's Big Tree Bowl: Super Bowl Performers Connections Checkers", "#ConnectionCheckers"),
    ("March 2025 RAWK Reveal 16 April 2025", "RAWK"),
    ("December RAWK Wrap-up with host @fluteroots", "RAWK"),
    ("WikiTree Global Spotlight (Feb 2024)", "Global Spotlight"),
    ("15 Nations Tour Wrap-up: Estonia w/@DavidRandall-8651", "15 Nations Global Tour"),
    ("WikiTree's 15 Nation Global Tour: Kenya Wrap-up", "15 Nations Global Tour"),
    ("\U0001f1eb\U0001f1f7 Join the France Project for a Disco(rd) Party!", "Disco(rd) Party"),
    ("Watchlist Weevil Challenge - Week Two w/@Robinson-27225", "Watchlist Weevil Challenge"),
    ("Alabama Challenge: 1st Month - Africatown Plateau Cemetery 14 July 2024", "Alabama Challenge"),
    ("Welcome to WikiTree Series: Privacy", "Welcome to WikiTree"),
])
def test_series_rules_follow_the_owners_decisions(title, series):
    assert title_series(title) == series


@pytest.mark.parametrize("title,series", [
    # "Are you related ..." is Spotlight Profile Shorts, even when it carries the #ConnectionFinder tag
    ("Are you related or connected to Frank Ifield?", "Spotlight Profile Shorts"),
    ("Are you related or connected to Cass Elliot of @themamas? Cohen-4015 #ConnectionFinder", "Spotlight Profile Shorts"),
    ("\U0001f3b6 #FridaySpotlight Are you related or connected to Garth Hudson of The Band? \U0001f3b9", "Spotlight Profile Shorts"),
    ("\U0001f3ac FRIDAY SPOTLIGHT: Are you related or connected to Charlie Chaplin?", "Spotlight Profile Shorts"),
    # ...while a title that STARTS with #ConnectionFinder is its own series
    ("#ConnectionFinder: Which Indiana notable are you most closely connected to? Jackson-150", "ConnectionFinder"),
    ("#ConnectionFinder: Are you related to the Kennedys?", "ConnectionFinder"),
    ("#WikiTree - Which toy inventor are you most closely connected to? @Barbie #ConnectionFinder", "ConnectionFinder"),
])
def test_connection_finder_and_are_you_related_are_told_apart_by_how_the_title_starts(title, series):
    assert title_series(title) == series


def test_wikitree_week_and_wikigames_are_separate_series():
    assert title_series("#WikiTreeWeek2024 DNA Features Chat w/Greg Clarke") != title_series("#2023WikiGames Closing Ceremony")


def test_manual_choice_beats_playlist_beats_title_rules():
    title = "WikiTree Tech Talk (April 2026)"
    assert classify_series(title) == "Tech Talk"
    assert classify_series(title, playlist="Tech Talks 2026") == "Tech Talks 2026"
    assert classify_series(title, playlist="Tech Talks 2026", video_id="abc", overrides={"abc": "Developer chats"}) == "Developer chats"
    assert classify_series(title, playlist="  ") == "Tech Talk"        # a blank playlist is no playlist


YT = '''Content,Video title,Video publish time,Duration,Playlist,Likes,Views
aaaaaaaaaaa,WikiTree Tech Talk (April 2026),"Apr 28, 2026",3600,Tech Talks,5,100
bbbbbbbbbbb,Member Q & A via Zoom (Jul 2026) 1 of 2,"Jul 2, 2026",3000,,3,80
Showing top 500 results
'''


def test_playlist_column_files_the_video_and_a_blank_falls_back_to_the_title(env):
    conn, raw, tmp = env
    f = tmp / "WikiTreers_YT_July_2026.csv"; f.write_text(YT)
    import_file(conn, f, raw_dir=raw)
    assert dict(conn.execute("SELECT video_id, series FROM youtube_videos").fetchall()) == {"aaaaaaaaaaa": "Tech Talks", "bbbbbbbbbbb": "WikiTree Member Q&A"}
    assert dict(conn.execute("SELECT video_id, playlist FROM youtube_videos").fetchall()) == {"aaaaaaaaaaa": "Tech Talks", "bbbbbbbbbbb": None}
    assert "playlist" not in {m for (m,) in conn.execute("SELECT DISTINCT metric FROM youtube_stats")}   # not mistaken for a metric


def test_reclassify_applies_the_overrides_file_to_videos_already_loaded(env):
    conn, raw, tmp = env
    f = tmp / "WikiTreers_YT_July_2026.csv"; f.write_text(YT)
    import_file(conn, f, raw_dir=raw)
    (tmp / "youtube_series.csv").write_text("video_id,series\nbbbbbbbbbbb,Zoom chats\n")
    assert reclassify_videos(conn) == 1
    assert conn.execute("SELECT series FROM youtube_videos WHERE video_id='bbbbbbbbbbb'").fetchone() == ("Zoom chats",)
    assert reclassify_videos(conn) == 0                                  # nothing left to change


def test_overrides_file_needs_its_two_columns(env):
    conn, raw, tmp = env
    (tmp / "youtube_series.csv").write_text("id,name\nx,y\n")
    from wtstats.importers import ImportError_
    with pytest.raises(ImportError_, match="video_id and series"):
        reclassify_videos(conn)


def test_a_database_made_before_playlists_is_upgraded(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE youtube_videos (video_id TEXT PRIMARY KEY, title TEXT NOT NULL, published_date TEXT, duration_s INTEGER, series TEXT NOT NULL)")
    old.execute("INSERT INTO youtube_videos VALUES ('x','t',NULL,NULL,'Other')")
    old.commit(); old.close()
    conn = db.connect(path)
    assert "playlist" in {r[1] for r in conn.execute("PRAGMA table_info(youtube_videos)")}
    assert conn.execute("SELECT video_id, playlist FROM youtube_videos").fetchall() == [("x", None)]


# ---- the channel's own subscribers export: Date + Subscribers ----

def rows(conn, sql, *a):
    return conn.execute(sql, a).fetchall()


def test_channel_subscribers_by_month_load_as_youtube_months(env):
    conn, raw, tmp = env
    f = tmp / "Chart data.csv"; f.write_text("Date,Subscribers\nJun 2026,12\nJul 2026,-3\n2026-08,20\n")
    r = import_file(conn, f, raw_dir=raw)
    assert (r["kind"], r["platform"]) == ("daily", "youtube")
    assert rows(conn, "SELECT granularity, period_start, metric, value FROM daily_metrics ORDER BY 2") == [
        ("month", "2026-06-01", "subscribers", 12.0), ("month", "2026-07-01", "subscribers", -3.0), ("month", "2026-08-01", "subscribers", 20.0)]


def test_a_monthly_file_dated_the_first_of_each_month_can_be_forced_to_months(env):
    conn, raw, tmp = env
    f = tmp / "subs.csv"; f.write_text('Date,Subscribers\n"Jul 1, 2026",7\n"Aug 1, 2026",9\n')
    import_file(conn, f, raw_dir=raw, monthly=True)
    assert rows(conn, "SELECT granularity, period_start FROM daily_metrics ORDER BY 2") == [("month", "2026-07-01"), ("month", "2026-08-01")]
    g = tmp / "subs_daily.csv"; g.write_text('Date,Subscribers\n"Jul 1, 2026",7\n"Jul 2, 2026",1\n')
    import_file(conn, g, raw_dir=raw)                                   # without the option the dates are days
    assert rows(conn, "SELECT COUNT(*) FROM daily_metrics WHERE granularity='day'") == [(2,)]


def test_the_per_video_table_is_still_told_apart_from_a_subscribers_file(env):
    conn, raw, tmp = env
    f = tmp / "WikiTreers_YT_July_2026.csv"; f.write_text(YT)
    r = import_file(conn, f, raw_dir=raw)
    assert r["kind"] == "youtube"


YT_TOTAL = '''Content,Video title,Video publish time,Duration,Likes,Views,Subscribers
Total,,,,8,180,7
aaaaaaaaaaa,WikiTree Tech Talk (April 2026),"Apr 28, 2026",3600,5,100,4
bbbbbbbbbbb,Member Q & A via Zoom (Jul 2026) 1 of 2,"Jul 2, 2026",3000,3,80,3
Showing top 500 results
'''
SHEET = "Date,Subscribers,Views\n2026-07,9,200\n2026-06,5,150\n"


def _channel(conn):
    return dict(((p, m), v) for p, m, v in conn.execute(
        "SELECT period_start, metric, value FROM daily_metrics WHERE platform='youtube' AND granularity='month'"))


@pytest.mark.parametrize("sheet_first", [True, False])
def test_a_months_export_total_beats_the_sheet_whatever_the_order(env, sheet_first):
    conn, raw, tmp = env
    sheet = tmp / "channel.csv"; sheet.write_text(SHEET)
    export = tmp / "WikiTreers_YT_July_2026.csv"; export.write_text(YT_TOTAL)
    order = [lambda: import_file(conn, sheet, raw_dir=raw, monthly=True), lambda: import_file(conn, export, raw_dir=raw)]
    for step in (order if sheet_first else order[::-1]):
        step()
    ch = _channel(conn)
    assert (ch["2026-07-01", "views"], ch["2026-07-01", "subscribers"]) == (180, 7)   # the export's Total row
    assert (ch["2026-06-01", "views"], ch["2026-06-01", "subscribers"]) == (150, 5)   # no export that month: the sheet
