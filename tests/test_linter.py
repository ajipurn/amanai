"""Tests for the semantic policy linter (spec 0003)."""

import json
from pathlib import Path

from amanai import Finding, lint_policy

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _codes(findings, severity=None):
    return [f.code for f in findings if severity is None or f.severity == severity]


# ── unreachable (exact subset) ────────────────────────────────────────────────
def test_broad_before_narrow_is_unreachable_error():
    findings = lint_policy(
        [
            {"id": "broad", "tool": "apply_discount", "action": "block", "reason": "r"},
            {
                "id": "narrow",
                "tool": "apply_discount",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "r",
            },
        ]
    )
    errors = [f for f in findings if f.severity == "error"]
    assert len(errors) == 1
    f = errors[0]
    assert f.code == "unreachable-rule"
    assert f.rule_ids == ("broad", "narrow")


def test_capability_rule_subsumes_tool_rule_with_same_capability():
    findings = lint_policy(
        [
            {"id": "cap", "capability": "money", "action": "block", "reason": "r"},
            {
                "id": "tool",
                "tool": "refund",
                "capability": "money",
                "args": [{"arg": "amount", "op": ">", "value": 100}],
                "action": "block",
                "reason": "r",
            },
        ]
    )
    assert "unreachable-rule" in _codes(findings, "error")


# ── numeric range heuristic (info, not error) ─────────────────────────────────
def test_broader_numeric_range_before_narrower_is_info():
    findings = lint_policy(
        [
            {
                "id": "a",
                "tool": "x",
                "args": [{"arg": "pct", "op": ">=", "value": 40}],
                "action": "block",
                "reason": "r",
            },
            {
                "id": "b",
                "tool": "x",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "r",
            },
        ]
    )
    assert _codes(findings, "error") == []
    infos = [f for f in findings if f.severity == "info"]
    assert any(f.code == "unreachable-rule" and f.rule_ids == ("a", "b") for f in infos)


def test_narrower_before_broader_numeric_is_not_flagged():
    findings = lint_policy(
        [
            {
                "id": "a",
                "tool": "x",
                "args": [{"arg": "pct", "op": ">=", "value": 60}],
                "action": "block",
                "reason": "r",
            },
            {
                "id": "b",
                "tool": "x",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "r",
            },
        ]
    )
    # 60 does not subsume 50 for >= — reachable, no unreachable finding.
    assert all(f.code != "unreachable-rule" for f in findings)


# ── conflict & redundant ──────────────────────────────────────────────────────
def test_same_match_different_action_is_conflict():
    findings = lint_policy(
        [
            {
                "id": "a",
                "tool": "x",
                "args": [{"arg": "p", "op": "==", "value": 1}],
                "action": "block",
                "reason": "r",
            },
            {
                "id": "b",
                "tool": "x",
                "args": [{"arg": "p", "op": "==", "value": 1}],
                "action": "warn",
                "reason": "r",
            },
        ]
    )
    conflicts = [f for f in findings if f.code == "conflicting-rules"]
    assert len(conflicts) == 1
    assert conflicts[0].severity == "warn"
    assert conflicts[0].rule_ids == ("a", "b")


def test_same_match_same_action_is_redundant():
    findings = lint_policy(
        [
            {"id": "a", "tool": "x", "action": "block", "reason": "r"},
            {"id": "b", "tool": "x", "action": "block", "reason": "r"},
        ]
    )
    codes = _codes(findings, "warn")
    assert "redundant-rule" in codes


# ── missing reason ────────────────────────────────────────────────────────────
def test_block_without_reason_is_info():
    findings = lint_policy([{"id": "a", "tool": "x", "action": "block"}])
    assert any(f.code == "missing-reason" and f.rule_ids == ("a",) for f in findings)


def test_allow_without_reason_is_not_flagged():
    findings = lint_policy([{"id": "a", "tool": "x", "action": "allow"}])
    assert all(f.code != "missing-reason" for f in findings)


# ── uncovered tools ───────────────────────────────────────────────────────────
def test_uncovered_tool_is_warned():
    findings = lint_policy(
        [{"id": "a", "tool": "x", "action": "block", "reason": "r"}],
        tools={"x": {"capability": None}, "y": {"capability": None}},
    )
    uncovered = [f for f in findings if f.code == "uncovered-tool"]
    assert len(uncovered) == 1
    assert "y" in uncovered[0].message


def test_tool_covered_by_capability_is_not_uncovered():
    findings = lint_policy(
        [{"id": "a", "capability": "money", "action": "block", "reason": "r"}],
        tools={"refund": {"capability": "money"}},
    )
    assert all(f.code != "uncovered-tool" for f in findings)


# ── no false positives on the shipped example ─────────────────────────────────
def test_example_action_policy_has_no_errors():
    findings = lint_policy(str(EXAMPLES / "action.policy.json"))
    assert [f for f in findings if f.severity == "error"] == []


def test_lints_every_example_without_raising():
    for path in EXAMPLES.glob("*.policy.json"):
        findings = lint_policy(str(path))
        assert isinstance(findings, list)
        assert all(isinstance(f, Finding) for f in findings)


# ── value normalization (50 vs 50.0) ──────────────────────────────────────────
def test_int_and_float_thresholds_match_as_same_rule():
    findings = lint_policy(
        [
            {
                "id": "a",
                "tool": "x",
                "args": [{"arg": "p", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "r",
            },
            {
                "id": "b",
                "tool": "x",
                "args": [{"arg": "p", "op": ">=", "value": 50.0}],
                "action": "block",
                "reason": "r",
            },
        ]
    )
    # 50 and 50.0 are the same predicate → redundant, not a numeric-range info.
    assert "redundant-rule" in _codes(findings)


# ── ordering & serialization ──────────────────────────────────────────────────
def test_errors_sort_before_lower_severities():
    findings = lint_policy(
        [
            {"id": "solo", "tool": "z", "action": "block"},  # info: missing-reason
            {"id": "broad", "tool": "x", "action": "block", "reason": "r"},
            {
                "id": "narrow",
                "tool": "x",
                "args": [{"arg": "p", "op": ">=", "value": 1}],
                "action": "block",
                "reason": "r",
            },  # error: unreachable
        ]
    )
    assert findings[0].severity == "error"


def test_finding_to_dict_roundtrips_via_json():
    findings = lint_policy([{"id": "a", "tool": "x", "action": "block"}])
    payload = json.dumps([f.to_dict() for f in findings])
    assert json.loads(payload)[0]["code"] == "missing-reason"
