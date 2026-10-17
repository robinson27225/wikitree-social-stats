"""Channel definitions and data rules for the WikiTree social stats loader.

Everything that is specific to how a platform exports its numbers lives here,
so a new column or a changed export format is a config edit, not a code change.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("WTSTATS_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "stats.db"
RAW_DIR = DATA_DIR / "raw"
ASSETS_DIR = ROOT / "assets"
LOGO = ASSETS_DIR / "logo.png"
SCHEDULER_URL = "https://wikitree-social-scheduler.fly.dev/"

# Dates in every export are used as given. The scheduler export is the
# *published* date in Pacific time; the platform exports are the platforms' own days.
TIMEZONE = "America/Los_Angeles"

PLATFORMS = ["facebook", "instagram", "tiktok", "linkedin", "youtube", "threads", "bluesky", "mastodon"]
LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "threads": "Threads",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
}
# Categorical slots 1-8 of the validated reference palette, assigned once per
# platform so a platform keeps its colour in every chart.
COLORS = {
    "facebook": "#2a78d6",
    "instagram": "#eb6834",
    "tiktok": "#1baf7a",
    "linkedin": "#eda100",
    "youtube": "#e87ba4",
    "threads": "#008300",
    "bluesky": "#6250d6",
    "mastodon": "#e34948",
}

# --- File recognition -------------------------------------------------------
# A daily/monthly platform export is recognised by columns only that platform has
# (after header normalisation: lower-case, non-alphanumerics -> "_").
DAILY_SIGNATURES = {
    "facebook": {"page_visits", "new_likes"},
    "instagram": {"profile_visits", "new_followers"},
    "tiktok": {"video_views", "profile_views"},
    "linkedin": {"impressions", "overview_page_views"},
    "youtube": {"date", "subscribers"},  # the channel's own Date + Subscribers export (the per-video table is told apart first)
}
# LinkedIn's own follower export (the "New followers" tab) has different columns from the manual sheets.
EXTRA_DAILY_SIGNATURES = [({"organic_followers", "total_followers"}, "linkedin")]
SCHEDULER_SIGNATURE = {"date", "channel", "platform", "posts"}
YOUTUBE_SIGNATURE = {"content", "video_title", "views"}

# Workbook tabs whose names match are left out on purpose (Twitter is not tracked).
SKIP_SHEET_PATTERNS = [r"\btw\b", r"twitter"]

# Meta's Insights exports are single-metric files (UTF-16, a "sep=," line, then the metric's title) that don't say which
# channel they are from, so the channel is passed in. The title says which metric it is:
META_EXPORT_METRICS = {"content interactions": "interactions", "reach": "reach"}

# --- Per-platform rules -----------------------------------------------------
# Columns that are derivable from other columns; not stored.
DROP_METRICS = {"linkedin": {"engagement_rate", "sponsored_followers", "organic_followers", "auto_invited_followers"}}

# Older or differently exported columns that mean the same as a current one.
#  - TikTok 2023 called the daily follower change "New Followers".
#  - LinkedIn's follower export's "Total followers" is the net daily change, same as the manual "followers" column.
RENAME_METRICS = {"tiktok": {"new_followers": "followers"}, "linkedin": {"total_followers": "followers"}}

# A blank in these columns means "none that day". Instagram writes explicit 0s
# from September onward but left blanks before, so blanks are read as 0.
# Only applied to rows that have at least one other value.
# LinkedIn exports a value for every count each day, so a blank is zero. Its manually entered `followers` column
# is not in the list: the 2025 sheet never filled it in, so a blank there means "not recorded".
BLANK_MEANS_ZERO = {
    "instagram": {"new_followers"},
    "linkedin": {"impressions", "clicks", "reactions", "comments", "reposts", "overview_page_views",
                 "overview_unique_visitors", "total_page_views", "total_unique_visitors"},
}

# TikTok's "Followers" column was a daily net change through August 2026 and a
# running total from this date on. Both are stored under distinct names; the
# daily change after the cutover is derived from consecutive totals.
TIKTOK_FOLLOWERS_TOTAL_FROM = "2026-09-01"

# (platform, metric, duplicate_of): a month where `metric` equals `duplicate_of`
# on (nearly) every day is a copy-paste artefact in the export; those values are flagged.
# Instagram Oct 2022: New Followers is a copy of Profile Visits (normal months: ~1 vs ~2.5 a day).
DUPLICATE_COLUMN_CHECKS = [
    ("facebook", "link_clicks", "page_visits"),
    ("instagram", "new_followers", "profile_visits"),
]
DUPLICATE_MIN_DAYS = 15

# (platform_a, platform_b, metric, flag): the same metric identical on both platforms for a month means one
# sheet was pasted into the other. `flag` says whose values are wrong ("both" when unknown).
# Facebook and Instagram Interactions are identical Jan 1 - Aug 31, 2024. Facebook's are real; Instagram's
# should be blank (confirmed by the owner of the sheets).
CROSS_PLATFORM_DUPLICATE_CHECKS = [("facebook", "instagram", "interactions", "instagram")]

# (platform, metric, other_metric, factor, reason): flag `metric` on days it is below factor x `other_metric`.
# `reason` None uses a generic "cannot be right" message.
#  - Facebook Views can't be below Viewers.
#  - Facebook Reach matches Viewers through Aug 2025, then falls to about a tenth of it in Sep 2025. Facebook's own
#    Reach export confirms the Sep 2025 numbers, so they are real but no longer comparable with earlier Reach:
#    Reach is left out from there and Viewers is used instead.
BELOW_CHECKS = [
    ("facebook", "views", "viewers", 1.0, None),
    ("facebook", "reach", "viewers", 0.5,
     "Facebook's Reach dropped to about a tenth of Viewers in Sep 2025 (its own export shows these same numbers); "
     "Viewers is used from here"),
]

# (family, platform) -> [(date, label)]: a dotted line on that chart where the measure changes.
CHART_BREAKS = {
    ("audience", "facebook"): [("2025-09-01", "Reach \u2192 Viewers")],
    # Instagram's "Interactions" is Meta's newer "Content interactions" from this day (zero before it in that export).
    ("engagement", "instagram"): [("2025-08-22", "Content interactions")],
}

# --- YouTube series (parsed from titles) -----------------------------------
# Which series a video belongs to, in order of precedence:
#   1. data/youtube_series.csv (video_id,series): the owner's manual choice for a video
#   2. a Playlist column in the YouTube export, when the video has one
#   3. these title rules; the first match wins, so more specific series come first
# After changing a rule, run `python -m wtstats reclassify` to refile the videos already loaded.
SERIES_OVERRIDES_FILE = DATA_DIR / "youtube_series.csv"
PLAYLIST_COLUMNS = ("playlist", "playlists", "playlist_title", "playlist_titles")
# Series are named like the owner's YouTube playlists where there is one (e.g. "WikiTree Saturday Roundup"), so a Playlist
# column and these rules never give the same series two names. Videos are told apart by how a title STARTS where that
# matters: "#ConnectionFinder: ..." is one series, "Are you related ..." (even ending in #ConnectionFinder) another.
SERIES_RULES = [
    ("SourceAThon", r"source-?a-?thon"),
    ("ConnectAThon", r"connect-?a-?thon"),
    ("WikiTree Saturday Roundup", r"saturday\s*round-?up"),
    ("WikiTree Challenge", r"wikitree challenge|#wtchallenge"),
    ("Spotlight Profile Shorts", r"^\W*(?:#?friday\s*spotlight\W*)?are you related"),
    ("ConnectionFinder", r"^\W*connection\s*finder"),
    ("#ConnectionCheckers", r"connection\s*(checkers?|combat)"),
    ("ConnectionFinder", r"connection\s*finder"),         # a #ConnectionFinder tag later in a title that starts with neither
    ("Spotlight Profile Shorts", r"#friday\s*spotlight"),
    ("Question of the Week", r"question\s*of\s*the\s*week"),
    ("WikiTree Ask Ale\u0161", r"ask ale"),
    ("WikiTree Member Q&A", r"member q\s*&\s*a"),
    ("WikiTree Day", r"wikitree\s*day"),
    ("Data Doctors", r"data doctors"),
    ("Link Builders Cubicle Party", r"link builders"),
    ("Tech Talk", r"tech talk"),
    ("Azure & Eowyn", r"azure\s*&\s*eowyn"),
    ("#CemeterySpotlight", r"cemetery\s*spotlight"),
    ("WikiTree Week", r"wikitree\s*week"),                 # not the same series as WikiGames
    ("WikiGames", r"wiki\s*games?"),
    ('Friday "Night" Bingo', r"bingo"),
    ("12 Days of Elf-Mas", r"elf-?mas"),
    ("WikiTree Meet Our Members", r"meet\s*our\s*members"),
    ("Research Parties", r"research part(y|ies)"),
    ("One Name Tuesday", r"one\s*name\s*tuesday"),
    ("Project Showcase", r"project showcase"),
    ("#OnePlaceWednesday", r"one\s*place\s*wednesday"),
    ("#GenealogyCollaborationHour", r"genealogy\s*collaboration\s*hour"),
    ("WikiTree Easter Egg Hunt", r"easter egg hunt"),
    ("#FridayDateNight", r"friday\s*date\s*night"),
    ("#Hacktoberfest", r"hacktoberfest"),
    # LiveCasts and "Live with Sarah and Eowyn" are the Saturday Roundup (the owner's choice), so they come before RootsTech
    ("WikiTree Saturday Roundup", r"live\s*cast|live with sarah"),
    ("WikiTree Symposium", r"symposium"),
    ("RootsTech", r"rootstech"),
    ("WikiTree Tours", r"(wikitree|tree)\s*tours?"),
    ("WikiTree Profile Improvement Project", r"profile improvement"),
    ("WikiTree New Members", r"new member (chat|orientation)"),
    ("WikiTree Heritage Exchange", r"heritage exchange"),
    ("WikiTree How To", r"\bhow[- ]?to\b|tutorial"),
]

# The export has no "is this a post" column. Community-page posts show up with this placeholder duration (138 of the
# ~1,270 items have exactly 16 seconds, across every series), so they are labelled from it.
COMMUNITY_POST_DURATION_S = 16
OTHER_SERIES = "Other"

# Running totals: weeks and months take the last value, not the sum, and year-over-year leaves them out.
NON_ADDITIVE_METRICS = {"followers_total"}

# --- Dashboard metric families ----------------------------------------------
# family -> (label, {platform: [daily metrics summed]}, caveat)
FAMILIES = {
    "views": (
        "Views / impressions",
        {"facebook": ["views"], "instagram": ["views"], "tiktok": ["video_views"], "linkedin": ["impressions"]},
        "Each platform counts a view its own way; compare trends within a platform, not levels across platforms.",
    ),
    "audience": (
        "People reached (daily unique)",
        {"facebook": ["reach|viewers"], "instagram": ["reach"], "tiktok": ["total_viewers"]},
        "Daily unique people. Summing days into weeks or months counts repeat viewers more than once. "
        "Facebook is Reach through Aug 2025 and Viewers from Sep 2025 (the two agree in Aug 2025; Reach then drops to a tenth of Viewers).",
    ),
    "engagement": (
        "Engagement (reactions, comments, shares)",
        {
            "facebook": ["interactions"],
            "instagram": ["interactions"],
            "tiktok": ["likes", "comments", "shares"],
            "linkedin": ["reactions", "comments", "reposts"],
        },
        "Facebook and Instagram report a combined interactions figure; TikTok and LinkedIn are summed from their parts.",
    ),
    "clicks": (
        "Link clicks",
        {"facebook": ["link_clicks"], "linkedin": ["clicks"]},
        "Facebook link clicks for January 2026 are flagged and left out (the column duplicates Page Visits that month).",
    ),
    "visits": (
        "Profile / page visits",
        {
            "facebook": ["page_visits"],
            "instagram": ["profile_visits"],
            "tiktok": ["profile_views"],
            "linkedin": ["total_page_views"],
        },
        "",
    ),
    "growth": (
        "New followers (net)",
        {"facebook": ["new_likes"], "instagram": ["new_followers"], "tiktok": ["followers_change"], "linkedin": ["followers"]},
        "Facebook counts new page likes. TikTok and LinkedIn are net (unfollows subtract). LinkedIn is the manual sheet through "
        "Dec 2024 and LinkedIn's own export from Oct 16, 2025; nothing in between.",
    ),
}
