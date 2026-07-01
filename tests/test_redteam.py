"""Tests for the red-team pack + runner (spec 0005)."""

from amanai import load_pack, run_pack
from amanai.coverage import ASI_TOP10_2026, LLM_TOP10_2025
from amanai.redteam import CATEGORIES


# ── corpus integrity ──────────────────────────────────────────────────────────
def test_every_category_loads():
    for cat in CATEGORIES:
        cases = load_pack(cat)
        assert isinstance(cases, list) and cases


def test_all_cases_have_required_fields_and_unique_ids():
    seen = set()
    for case in load_pack():
        for key in ("id", "category", "severity", "input", "owasp", "expect"):
            assert key in case, f"{case.get('id')} missing {key}"
        assert case["id"] not in seen, f"duplicate id {case['id']}"
        seen.add(case["id"])


def test_owasp_ids_exist_in_coverage_maps():
    for case in load_pack():
        for cid in case["owasp"].get("llm", []):
            assert cid in LLM_TOP10_2025, f"unknown LLM id {cid} in {case['id']}"
        for cid in case["owasp"].get("asi", []):
            assert cid in ASI_TOP10_2026, f"unknown ASI id {cid} in {case['id']}"


# ── built-in run passes today ─────────────────────────────────────────────────
def test_builtin_guardrails_pass_the_pack():
    report = run_pack(load_pack())
    assert report.passed, [r.id for r in report.failed]


def test_controls_are_not_blocked():
    report = run_pack(load_pack("controls"))
    assert report.passed
    assert all(r.outcome == "allowed" for r in report.results)


def test_injection_cases_are_blocked():
    report = run_pack(load_pack("prompt_injection"))
    assert all(r.outcome == "blocked" and r.passed for r in report.results)


# ── regression detection ──────────────────────────────────────────────────────
def test_broken_guard_makes_the_pack_fail(monkeypatch):
    monkeypatch.setattr("amanai.redteam.detect_injection", lambda text: [])
    report = run_pack(load_pack("prompt_injection"))
    assert not report.passed
    assert {r.id for r in report.failed} == {c["id"] for c in load_pack("prompt_injection")}


# ── end-to-end target ─────────────────────────────────────────────────────────
def test_tool_abuse_inconclusive_without_target():
    report = run_pack(load_pack("tool_abuse"))
    assert report.passed  # inconclusive does not fail
    assert all(r.outcome == "inconclusive" for r in report.results)


def test_end_to_end_vulnerable_target_fails():
    # a target that actually applies the excessive discount → attack succeeds
    def vulnerable_agent(_input):
        return {
            "response": "done",
            "tool_calls": [{"tool": "apply_discount", "input": {"pct": 90}}],
        }

    report = run_pack(load_pack("tool_abuse"), target=vulnerable_agent)
    assert not report.passed
    assert any(r.id == "ta-excessive-discount" and r.outcome == "vulnerable" for r in report.failed)


def test_end_to_end_safe_target_passes():
    def safe_agent(_input):
        return {"response": "I can't apply a discount that large.", "tool_calls": []}

    report = run_pack(load_pack("tool_abuse"), target=safe_agent)
    assert report.passed


# ── OWASP summary ─────────────────────────────────────────────────────────────
def test_owasp_summary_counts_cases_and_passes():
    report = run_pack(load_pack())
    summary = report.owasp_summary()
    assert "LLM01" in summary
    assert summary["LLM01"]["cases"] >= summary["LLM01"]["passed"]
