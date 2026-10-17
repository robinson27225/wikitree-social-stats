"""Command line: python -m wtstats import FILE...  |  python -m wtstats status"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, db
from .importers import ImportError_, import_file


def cmd_import(args) -> int:
    conn = db.connect(args.db)
    failed = 0
    for f in args.files:
        try:
            r = import_file(conn, f, raw_dir=args.raw_dir, platform=args.platform,
                            period=args.period, force=args.force)
        except (ImportError_, OSError) as e:
            conn.rollback()
            print(f"FAILED   {Path(f).name}: {e}")
            failed += 1
            continue
        if r["status"] == "skipped":
            print(f"skipped  {r['file']}: {r['reason']}")
        else:
            print(f"imported {r['file']}: {r['kind']}/{r['platform'] or 'multi'}  "
                  f"{r['rows_loaded']} of {r['rows_read']} rows")
            for n in r["notes"]:
                print(f"           note: {n}")
    return 1 if failed else 0


def cmd_status(args) -> int:
    conn = db.connect(args.db)
    print("Account-level (daily_metrics)")
    for row in conn.execute(
        """SELECT platform, granularity, MIN(period_start), MAX(period_start),
                  COUNT(DISTINCT period_start), COUNT(DISTINCT metric)
           FROM daily_metrics GROUP BY platform, granularity ORDER BY platform"""
    ):
        print("  %-10s %-6s %s -> %s  %4d periods  %2d metrics" % row)
    print("Scheduler (post_day_metrics)")
    for row in conn.execute(
        """SELECT platform, MIN(date), MAX(date), COUNT(DISTINCT date) FROM post_day_metrics
           GROUP BY platform ORDER BY platform"""
    ):
        print("  %-10s %s -> %s  %3d days" % row)
    n, = conn.execute("SELECT COUNT(*) FROM youtube_videos").fetchone()
    print(f"YouTube: {n} videos")
    for row in conn.execute(
        """SELECT period_start, period_end, COUNT(DISTINCT video_id), COUNT(DISTINCT metric)
           FROM youtube_stats GROUP BY period_start, period_end ORDER BY period_start, period_end"""
    ):
        print("  %s -> %s  %4d videos  %2d metrics" % row)
    flags, = conn.execute("SELECT COUNT(*) FROM data_flags").fetchone()
    print(f"Flagged values left out of charts: {flags}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wtstats")
    p.add_argument("--db", default=config.DB_PATH, help="SQLite file (default: data/stats.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import", help="archive and load export files")
    pi.add_argument("files", nargs="+")
    pi.add_argument("--platform", choices=sorted(config.DAILY_SIGNATURES), help="override auto-detection (daily files only)")
    pi.add_argument("--period", help="YouTube only: the period the file covers, as YYYY-MM or YYYY-MM-DD:YYYY-MM-DD "
                                     "(default: the month named in the file name, e.g. ..._July_2026.csv)")
    pi.add_argument("--raw-dir", default=config.RAW_DIR, help="where untouched copies of the files are kept")
    pi.add_argument("--force", action="store_true", help="re-import a file that was already imported")
    pi.set_defaults(func=cmd_import)

    ps = sub.add_parser("status", help="show what is loaded")
    ps.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
