from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "app.py"


def test_dashboard_renders_without_errors():
    """Runs the whole app against whatever is in data/stats.db (or the empty-state page if there is none)."""
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
