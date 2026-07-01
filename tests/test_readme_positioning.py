# tests/test_readme_positioning.py
"""Guards the positioning copy: the honest wedge phrasing is present and the
banned anti-claims never reappear in the README."""

import pathlib

README = (pathlib.Path(__file__).parent.parent / "README.md").read_text().lower()

BANNED = ["only platform", "the first ", "most attacks", "enterprise platform"]
REQUIRED = ["one policy", "self-host", "apache-2.0", "when not to use"]


def test_required_positioning_phrases_present():
    for phrase in REQUIRED:
        assert phrase in README, f"missing required positioning phrase: {phrase!r}"


def test_banned_anticlaims_absent():
    for phrase in BANNED:
        assert phrase not in README, f"banned anti-claim present: {phrase!r}"
