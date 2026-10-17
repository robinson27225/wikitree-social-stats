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
    "tiktok": {"video_views", "new_viewers"},
    "linkedin": {"impressions", "overview_page_views"},
}
SCHEDULER_SIGNATURE = {"date", "channel", "platform", "posts"}
YOUTUBE_SIGNATURE = {"content", "video_title", "views"}

# --- Per-platform rules -----------------------------------------------------
# Columns that are derivable from other columns; not stored.
DROP_METRICS = {"linkedin": {"engagement_rate"}}

# A blank in these columns means "none that day". Instagram writes explicit 0s
# from September onward but left blanks before, so blanks are read as 0.
# Only applied to rows that have at least one other value.
BLANK_MEANS_ZERO = {"instagram": {"new_followers"}}

# TikTok's "Followers" column was a daily net change through August 2026 and a
# running total from this date on. Both are stored under distinct names; the
# daily change after the cutover is derived from consecutive totals.
TIKTOK_FOLLOWERS_TOTAL_FROM = "2026-09-01"

# (platform, metric, duplicate_of): a month where `metric` equals `duplicate_of`
# on (nearly) every day is a copy-paste artefact in the export; those values are flagged.
DUPLICATE_COLUMN_CHECKS = [("facebook", "link_clicks", "page_visits")]
DUPLICATE_MIN_DAYS = 15

# --- YouTube series (parsed from titles) -----------------------------------
# First match wins, so more specific series come first.
SERIES_RULES = [
    ("SourceAThon", r"source-?a-?thon"),
    ("ConnectAThon", r"connect-?a-?thon"),
    ("Saturday Roundup", r"saturday\s*round-?up"),
    ("WikiTree Challenge", r"wikitree challenge|#wtchallenge"),
    ("ConnectionCheckers / Finder", r"connection\s*(checkers?|finder)|#fridayspotlight|are you related or connected"),
    ("Question of the Week", r"question\s*of\s*the\s*week"),
    ("Q&A and Ask Aleš", r"member q\s*&\s*a|ask ale"),
    ("WikiTree Day", r"wikitree day"),
    ("Data Doctors", r"data doctors"),
    ("Link Builders / Tech Talk", r"link builders|tech talk"),
    ("How-To", r"\bhow-?to\b|tutorial"),
]
OTHER_SERIES = "Other"

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
        {"facebook": ["viewers"], "instagram": ["reach"], "tiktok": ["total_viewers"]},
        "Daily unique people. Summing days into weeks or months counts repeat viewers more than once.",
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
        {"facebook": ["new_likes"], "instagram": ["new_followers"], "tiktok": ["followers_change"]},
        "Facebook counts new page likes. TikTok is net (unfollows subtract). LinkedIn does not export follower data.",
    ),
}
