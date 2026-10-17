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
