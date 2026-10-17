import pytest

from wtstats import db
from wtstats.importers import ImportError_, import_file, is_meta_export, read_meta_export


@pytest.fixture
def env(tmp_path):
    return db.connect(tmp_path / "t.db"), tmp_path / "raw", tmp_path


def rows(conn, sql, *a):
    return conn.execute(sql, a).fetchall()


# Meta writes these as UTF-16 with a "sep=," line first and the metric's title on the second line
META = '''sep=,
"Content interactions"
"Date","Primary"
"2025-08-20T00:00:00","0"
"2025-08-21T00:00:00","0"
"2025-08-22T00:00:00","6"
"2025-08-23T00:00:00","17"
"2025-12-24T00:00:00","-1"
'''


def write_meta(tmp, name="Interactions_1.csv", text=META):
    p = tmp / name
    p.write_bytes(text.encode("utf-16"))
    return p


def test_meta_export_is_recognised_and_read():
    assert is_meta_export(META)
    assert not is_meta_export("Date,Reach\n01/01/2026,5\n")
    metric, df = read_meta_export(META)
    assert metric == "interactions" and df["date"].tolist()[:3] == ["2025-08-20", "2025-08-21", "2025-08-22"]
    assert read_meta_export(META.replace("Content interactions", "Something new"), metric="views")[0] == "views"
    with pytest.raises(ImportError_, match="pass --metric"):
        read_meta_export(META.replace("Content interactions", "Something new"))


def test_meta_export_needs_the_channel_named(env):
    conn, raw, tmp = env
    with pytest.raises(ImportError_, match="--platform"):
        import_file(conn, write_meta(tmp), raw_dir=raw)


def test_from_date_keeps_the_zeros_before_the_metric_existed_out(env):
    conn, raw, tmp = env
    # July came from an earlier sheet and must survive; the zeros before Aug 22 are "metric not available", not data
    conn.execute("INSERT INTO daily_metrics VALUES ('instagram','day','2025-08-20','interactions',31,NULL)")
    r = import_file(conn, write_meta(tmp), raw_dir=raw, platform="instagram", since="2025-08-22")
    assert rows(conn, "SELECT period_start, value FROM daily_metrics WHERE metric='interactions' ORDER BY 1") == [
        ("2025-08-20", 31.0), ("2025-08-22", 6.0), ("2025-08-23", 17.0), ("2025-12-24", -1.0)]
    assert any("from 2025-08-22" in n for n in r["notes"])


def test_without_from_date_the_zeros_would_overwrite(env):
    conn, raw, tmp = env
    conn.execute("INSERT INTO daily_metrics VALUES ('instagram','day','2025-08-20','interactions',31,NULL)")
    import_file(conn, write_meta(tmp), raw_dir=raw, platform="instagram")
    assert rows(conn, "SELECT value FROM daily_metrics WHERE period_start='2025-08-20'") == [(0.0,)]   # why --from matters


def test_until_date_and_bad_dates(env):
    conn, raw, tmp = env
    import_file(conn, write_meta(tmp), raw_dir=raw, platform="instagram", since="2025-08-22", until="2025-08-22")
    assert rows(conn, "SELECT period_start FROM daily_metrics") == [("2025-08-22",)]
    with pytest.raises(ImportError_, match="must be a date"):
        import_file(conn, write_meta(tmp, "other.csv", META + "\n"), raw_dir=raw, platform="instagram", since="Aug 22")


def test_from_date_is_refused_for_workbooks(env):
    conn, raw, tmp = env
    import openpyxl
    wb = openpyxl.Workbook(); wb.active.append(["Date"]); wb.save(tmp / "w.xlsx")
    with pytest.raises(ImportError_, match="single CSV"):
        import_file(conn, tmp / "w.xlsx", raw_dir=raw, since="2025-01-01")
