"""Read the export files and load them into SQLite.

Every file is archived untouched before it is parsed: the scheduler deletes its
data after an export, so the archived copy may be the only one that exists.
Loads only ever insert or update rows; a blank cell never overwrites a stored value.
"""
from __future__ import annotations

import calendar
import hashlib
import re
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import config, quality


class ImportError_(ValueError):
    """The file could not be recognised or parsed."""


# --- parsing helpers --------------------------------------------------------

def normalize_header(h: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(h).strip().lower()).strip("_")


def parse_number(s) -> float | None:
    """'2,299' -> 2299.0; '' / NaN -> None."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


_PERIOD_FORMATS = [
    ("%m/%d/%Y", "day"),
    ("%Y-%m-%d", "day"),
    ("%Y-%m", "month"),
    ("%b %Y", "month"),
    ("%B %Y", "month"),
    ("%m/%Y", "month"),
]


def parse_period(s: str) -> tuple[str, str]:
    """'01/31/2026' -> ('day', '2026-01-31'); '2026-01' -> ('month', '2026-01-01')."""
    s = str(s).strip()
    for fmt, gran in _PERIOD_FORMATS:
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return gran, (d.date().replace(day=1) if gran == "month" else d.date()).isoformat()
    raise ImportError_(f"unrecognised date {s!r}")


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [normalize_header(c) for c in df.columns]
    return df


def detect_kind(columns: set[str]) -> tuple[str, str | None]:
    """Return (kind, platform) for a file's normalised columns."""
    if config.SCHEDULER_SIGNATURE <= columns:
        return "scheduler", None
    if config.YOUTUBE_SIGNATURE <= columns:
        return "youtube", "youtube"
    for platform, sig in config.DAILY_SIGNATURES.items():
        if sig <= columns:
            return "daily", platform
    raise ImportError_(f"could not tell which channel this file is from; columns: {sorted(columns)}")


_MONTH_NUMBERS = {name.lower(): i for i in range(1, 13) for name in (calendar.month_name[i], calendar.month_abbr[i])}


def month_span(year: int, month: int) -> tuple[str, str]:
    return date(year, month, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def parse_period_arg(text: str) -> tuple[str, str]:
    """'2026-07' -> that month; '2026-01-01:2026-10-17' -> that inclusive range."""
    text = text.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})", text):
        try:
            return month_span(int(m[1]), int(m[2]))
        except ValueError:
            pass
    elif m := re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})", text):
        try:
            if date.fromisoformat(m[1]) <= date.fromisoformat(m[2]):
                return m[1], m[2]
        except ValueError:
            pass
    raise ImportError_(f"unrecognised period {text!r}; use YYYY-MM or YYYY-MM-DD:YYYY-MM-DD")


def infer_period_from_name(name: str) -> tuple[str, str] | None:
    """'WikiTreers_YT_August_2026.csv' (or '..._2026-08.csv') -> August 2026, else None."""
    stem = Path(name).stem.lower()
    for word, year in re.findall(r"([a-z]+)[\s_.-]+(20\d{2})", stem):
        if word in _MONTH_NUMBERS:
            return month_span(int(year), _MONTH_NUMBERS[word])
    if m := re.search(r"(20\d{2})[-_.](0[1-9]|1[0-2])(?!\d)", stem):
        return month_span(int(m[1]), int(m[2]))
    return None


def classify_series(title: str) -> str:
    for name, pattern in config.SERIES_RULES:
        if re.search(pattern, title, flags=re.IGNORECASE):
            return name
    return config.OTHER_SERIES


# --- loaders ----------------------------------------------------------------

def import_daily(conn: sqlite3.Connection, df: pd.DataFrame, platform: str, import_id: int) -> tuple[int, int, str]:
    drop = config.DROP_METRICS.get(platform, set())
    metrics = [c for c in df.columns if c != "date" and c not in drop]
    zero_fill = config.BLANK_MEANS_ZERO.get(platform, set())
    out, read, loaded = [], 0, 0
    for n, rec in enumerate(df.to_dict("records"), start=2):
        if str(rec.get("date", "")).strip() == "":
            continue
        read += 1
        try:
            gran, start = parse_period(rec["date"])
        except ImportError_ as e:
            raise ImportError_(f"row {n}: {e}") from None
        values = {m: parse_number(rec[m]) for m in metrics}
        if all(v is None for v in values.values()):
            continue  # the sheets are pre-filled with empty future dates
        loaded += 1
        for m in zero_fill & values.keys():
            if values[m] is None:
                values[m] = 0.0
        if platform == "tiktok" and "followers" in values:
            v = values.pop("followers")
            if v is not None:
                key = "followers_total" if start >= config.TIKTOK_FOLLOWERS_TOTAL_FROM else "followers_change"
                values[key] = v
        out += [(platform, gran, start, m, v, import_id) for m, v in values.items() if v is not None]
    conn.executemany(
        """INSERT INTO daily_metrics (platform, granularity, period_start, metric, value, import_id)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (platform, granularity, period_start, metric)
           DO UPDATE SET value = excluded.value, import_id = excluded.import_id""",
        out,
    )
    return read, loaded, ""


def import_scheduler(conn: sqlite3.Connection, df: pd.DataFrame, import_id: int) -> tuple[int, int, str]:
    meta = {"date", "channel", "platform"}
    metrics = [c for c in df.columns if c not in meta]
    out, read, loaded, mismatches = [], 0, 0, 0
    for n, rec in enumerate(df.to_dict("records"), start=2):
        if str(rec.get("date", "")).strip() == "":
            continue
        read += 1
        try:
            gran, day = parse_period(rec["date"])
        except ImportError_ as e:
            raise ImportError_(f"row {n}: {e}") from None
        if gran != "day":
            raise ImportError_(f"row {n}: scheduler rows must be daily, got {rec['date']!r}")
        values = {m: parse_number(rec[m]) for m in metrics}
        if all(v is None for v in values.values()):
            continue
        loaded += 1
        mismatches += quality.scheduler_row_mismatch(values)
        platform = str(rec["platform"]).strip().lower()
        out += [(platform, str(rec["channel"]).strip(), day, m, v, import_id) for m, v in values.items() if v is not None]
    conn.executemany(
        """INSERT INTO post_day_metrics (platform, channel, date, metric, value, import_id)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (platform, channel, date, metric)
           DO UPDATE SET value = excluded.value, import_id = excluded.import_id""",
        out,
    )
    note = f"{mismatches} rows where interactions/engagements do not equal the sum of their parts" if mismatches else ""
    return read, loaded, note


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_FOOTER = re.compile(r"showing top (\d+) results", re.IGNORECASE)


_YOUTUBE_META = {"content", "video_title", "video_publish_time", "duration"}


def import_youtube(conn: sqlite3.Connection, df: pd.DataFrame, import_id: int, period: tuple[str, str]) -> tuple[int, int, str]:
    """Every column beyond the video's identity is a metric, so a different set of columns needs no code change."""
    notes = [f"covers {period[0]} to {period[1]}"]
    footer = next((m for c in df["content"] if (m := _FOOTER.search(str(c)))), None)
    # YouTube ids can start with "-", and the export pads those with a leading space.
    rows = df[df["content"].map(lambda c: bool(_VIDEO_ID.match(str(c).strip())))]
    if footer and int(footer.group(1)) <= len(rows):
        notes.append(f"export is capped at the top {footer.group(1)} videos; videos beyond that are missing")
    metrics = [c for c in df.columns if c not in _YOUTUBE_META]
    videos, stats = [], []
    for rec in rows.to_dict("records"):
        vid = rec["content"].strip()
        title = " ".join(rec["video_title"].split())  # titles can contain line breaks
        try:
            published = datetime.strptime(rec["video_publish_time"].strip(), "%b %d, %Y").date().isoformat()
        except ValueError:
            published = None
        duration = parse_number(rec.get("duration"))
        videos.append((vid, title, published, int(duration) if duration is not None else None, classify_series(title)))
        for m in metrics:
            v = parse_number(rec[m])
            if v is not None:
                stats.append((vid, period[0], period[1], m, v, import_id))
    conn.executemany(
        """INSERT INTO youtube_videos (video_id, title, published_date, duration_s, series) VALUES (?,?,?,?,?)
           ON CONFLICT (video_id) DO UPDATE SET title = excluded.title, published_date = excluded.published_date,
               duration_s = excluded.duration_s, series = excluded.series""",
        videos,
    )
    conn.executemany(
        """INSERT INTO youtube_stats (video_id, period_start, period_end, metric, value, import_id) VALUES (?,?,?,?,?,?)
           ON CONFLICT (video_id, period_start, period_end, metric)
           DO UPDATE SET value = excluded.value, import_id = excluded.import_id""",
        stats,
    )
    return len(rows), len(rows), "; ".join(notes)


# --- orchestration ----------------------------------------------------------

def _portable(path: Path) -> str:
    """Path relative to the project when possible, so a committed database works on any machine."""
    try:
        return path.resolve().relative_to(config.ROOT).as_posix()
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_file(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    raw_dir: Path | None = None,
    platform: str | None = None,
    period: str | None = None,
    force: bool = False,
) -> dict:
    """Archive and load one export file. Returns a summary dict (status 'imported' or 'skipped')."""
    path = Path(path)
    raw_dir = Path(raw_dir or config.RAW_DIR)
    digest = sha256_file(path)
    seen = conn.execute("SELECT id, source_name FROM import_log WHERE sha256 = ?", (digest,)).fetchone()
    if seen and not force:
        return {"status": "skipped", "file": path.name, "reason": f"already imported as {seen[1]!r}"}

    df = read_csv(path)
    kind, detected = detect_kind(set(df.columns))
    platform = platform or detected

    raw_dir.mkdir(parents=True, exist_ok=True)
    archived = raw_dir / f"{digest[:8]}_{path.name}"
    if not archived.exists():
        shutil.copy2(path, archived)

    span = None
    if kind == "youtube":  # a YouTube file says nothing about the period it covers
        span = parse_period_arg(period) if period else infer_period_from_name(path.name)
        if span is None:
            raise ImportError_(
                f"{path.name}: cannot tell which period this YouTube file covers. Put the month in the file name "
                "(e.g. WikiTreers_YT_July_2026.csv) or pass --period 2026-07, or --period 2026-01-01:2026-10-17 for a range. "
                "The file has been archived, nothing was loaded."
            )

    if seen:  # forced re-import of the same bytes: reuse its log row
        import_id = seen[0]
        conn.execute("UPDATE import_log SET imported_at = ? WHERE id = ?", (datetime.now().isoformat(timespec="seconds"), import_id))
    else:
        import_id = conn.execute(
            """INSERT INTO import_log (kind, platform, source_name, sha256, archived_path, imported_at)
               VALUES (?,?,?,?,?,?)""",
            (kind, platform, path.name, digest, _portable(archived), datetime.now().isoformat(timespec="seconds")),
        ).lastrowid

    notes = []
    if kind == "daily":
        read, loaded, note = import_daily(conn, df, platform, import_id)
    elif kind == "scheduler":
        read, loaded, note = import_scheduler(conn, df, import_id)
    else:
        read, loaded, note = import_youtube(conn, df, import_id, span)
    if note:
        notes.append(note)

    quality.derive_tiktok_follower_change(conn)
    quality.rebuild_flags(conn)
    conn.execute(
        "UPDATE import_log SET rows_read = ?, rows_loaded = ?, notes = ? WHERE id = ?",
        (read, loaded, "; ".join(notes) or None, import_id),
    )
    conn.commit()
    return {"status": "imported", "file": path.name, "kind": kind, "platform": platform,
            "rows_read": read, "rows_loaded": loaded, "notes": notes}


# --- removal ----------------------------------------------------------------

_IMPORT_TABLES = ("daily_metrics", "post_day_metrics", "youtube_stats")


def find_imports(conn: sqlite3.Connection, text: str) -> list[tuple]:
    """Imports whose file name or checksum contains `text`: (id, kind, source_name, archived_path)."""
    like = f"%{text}%"
    return conn.execute(
        "SELECT id, kind, source_name, archived_path FROM import_log WHERE source_name LIKE ? OR sha256 LIKE ? ORDER BY id",
        (like, like),
    ).fetchall()


def import_row_counts(conn: sqlite3.Connection, import_id: int) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE import_id = ?", (import_id,)).fetchone()[0] for t in _IMPORT_TABLES}


def remove_import(conn: sqlite3.Connection, import_id: int) -> dict[str, int]:
    """Delete everything an import loaded, its log entry and its archived copy.

    Only rows still attributed to this import go: a value a later file replaced belongs to that file now.
    """
    row = conn.execute("SELECT archived_path FROM import_log WHERE id = ?", (import_id,)).fetchone()
    if row is None:
        raise ImportError_(f"no import with id {import_id}")
    counts = {t: conn.execute(f"DELETE FROM {t} WHERE import_id = ?", (import_id,)).rowcount for t in _IMPORT_TABLES}
    counts["youtube_videos"] = conn.execute(
        "DELETE FROM youtube_videos WHERE video_id NOT IN (SELECT DISTINCT video_id FROM youtube_stats)").rowcount
    conn.execute("DELETE FROM import_log WHERE id = ?", (import_id,))
    conn.execute("DELETE FROM daily_metrics WHERE import_id IS NULL")  # derived values; recomputed from what is left
    quality.derive_tiktok_follower_change(conn)
    quality.rebuild_flags(conn)
    conn.commit()
    archived = Path(row[0])
    archived = archived if archived.is_absolute() else config.ROOT / archived
    archived.unlink(missing_ok=True)
    return counts
