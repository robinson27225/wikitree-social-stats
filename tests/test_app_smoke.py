import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture(autouse=True)
def keep_wtstats_modules():
    """The app drops and re-imports the wtstats modules every run (see app.py). Put the originals back afterwards, so the
    other tests, which imported those modules at collection time, keep talking to the same module objects."""
    saved = {k: v for k, v in sys.modules.items() if k == "wtstats" or k.startswith("wtstats.")}
    yield
    for name in [m for m in sys.modules if m == "wtstats" or m.startswith("wtstats.")]:
        del sys.modules[name]
    sys.modules.update(saved)


def test_dashboard_renders_without_errors():
    """Runs the whole app against whatever is in data/stats.db (or the empty-state page if there is none)."""
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]


def test_a_redeploy_that_leaves_old_modules_in_memory_cannot_break_the_app():
    """Streamlit Cloud reloads app.py on a push without restarting Python. The old wtstats modules stay cached, and the
    new app.py failed with "cannot import name 'yoy_table'" / "'__version__'". The app drops stale modules itself."""
    import sys
    import types

    import wtstats  # noqa: F401  (make sure the real package is loaded first)

    old_package = types.ModuleType("wtstats")                      # the previous release: no __version__
    old_package.__path__ = wtstats.__path__
    old_series = types.ModuleType("wtstats.series")                # ...and a series module without yoy_table
    old_series.daily_series = lambda *a, **k: None
    saved = {k: v for k, v in sys.modules.items() if k == "wtstats" or k.startswith("wtstats.")}
    sys.modules["wtstats"], sys.modules["wtstats.series"] = old_package, old_series
    try:
        at = AppTest.from_file(str(APP), default_timeout=90).run()
        assert not at.exception, [e.value for e in at.exception]
    finally:
        sys.modules.update(saved)


def test_series_that_gained_no_subscribers_are_left_off_the_youtube_bars():
    import base64
    import json

    import numpy as np
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    pick = [s for s in at.selectbox if "Subscribers gained" in s.options]
    if not pick:
        pytest.skip("no YouTube data loaded")
    pick[0].select_index(pick[0].options.index("Subscribers gained")).run()
    assert not at.exception
    bars = [json.loads(c.proto.spec)["data"][0] for c in at.get("plotly_chart")]
    bars = [b for b in bars if b.get("orientation") == "h"]
    assert bars
    for b in bars:
        x = b["x"]
        if isinstance(x, dict):  # plotly sends numeric arrays as base64
            x = np.frombuffer(base64.b64decode(x["bdata"]), dtype=np.dtype(x["dtype"]))
        assert all(v != 0 for v in x)


def _bar_labels(at):
    import json
    bars = [json.loads(c.proto.spec)["data"][0] for c in at.get("plotly_chart")]
    return [b for b in bars if b.get("orientation") == "h"]


def test_youtube_views_by_series_open_on_the_current_year_with_the_top_ten_and_a_button_for_all():
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    period = [s for s in at.selectbox if s.label == "Period"]
    if not period:
        pytest.skip("no YouTube data loaded")
    assert period[0].value.startswith(str(max(int(o[:4]) for o in period[0].options if o[:4].isdigit())))
    assert not at.exception
    assert len(_bar_labels(at)[0]["y"]) <= 10
    button = [b for b in at.button if b.key == "yt_series_btn"]
    assert button and "Show all" in button[0].label
    button[0].click().run()
    assert not at.exception
    assert len(_bar_labels(at)[0]["y"]) > 10
    again = [b for b in at.button if b.key == "yt_series_btn"][0]
    assert "top 10" in again.label
