import re
from pathlib import Path

from wtstats import __version__, config

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_the_top_changelog_entry():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    top = re.search(r"^## (\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(), flags=re.MULTILINE).group(1)
    assert top == __version__, "bump wtstats.__version__ and the top CHANGELOG entry together"


def test_logo_and_scheduler_link_are_in_place():
    assert config.LOGO.exists() and config.LOGO.stat().st_size > 1000
    assert config.SCHEDULER_URL == "https://wikitree-social-scheduler.fly.dev/"
