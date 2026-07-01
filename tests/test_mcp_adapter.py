"""MCP adapter: the pre-forward gate enforces the same policy as `@tool`.

`guard_mcp_call` is the only new surface — it must block/gate live MCP tool-calls
before the transport forwards them, using the active policy and mode. Executed
evidence (with output) is the existing `record_tool_call`'s job, so this only
checks the gate.
"""

import pytest

from amanai import (
    ApprovalRequired,
    ToolBlocked,
    collect_trace,
    guard_mcp_call,
    set_context,
    set_mode,
    set_policy,
)

POLICY = [
    {
        "id": "discount-cap",
        "tool": "apply_discount",
        "args": [{"arg": "pct", "op": ">=", "value": 50}],
        "action": "block",
        "reason": "discount >= 50% blocked",
    },
    {"id": "refund-approval", "tool": "refund", "action": "require_approval"},
    {
        "id": "external-email",
        "capability": "external_comms",
        "args": [{"arg": "to", "op": "email_external", "value": ["acme.com"]}],
        "action": "block",
    },
]


def test_allow_passes_through():
    set_policy(POLICY)
    assert guard_mcp_call("apply_discount", {"pct": 10}).outcome == "allow"


def test_no_rule_allows():
    set_policy(POLICY)
    assert guard_mcp_call("unknown_tool", {"x": 1}).outcome == "allow"


def test_block_raises_and_records_evidence():
    set_policy(POLICY)
    with pytest.raises(ToolBlocked):
        guard_mcp_call("apply_discount", {"pct": 90})
    trace = collect_trace()
    assert [e.status for e in trace] == ["blocked"]
    assert trace[0].decision.rule_id == "discount-cap"


def test_require_approval_raises_with_pending_token():
    set_policy(POLICY)
    with pytest.raises(ApprovalRequired) as exc:
        guard_mcp_call("refund", {"amount": 500})
    assert exc.value.pending.token.startswith("pending-")
    assert [e.status for e in collect_trace()] == ["pending"]


def test_capability_rule_matches_when_capability_passed():
    set_policy(POLICY)
    with pytest.raises(ToolBlocked):
        guard_mcp_call("send_mail", {"to": "x@evil.com"}, capability="external_comms")


def test_shadow_mode_returns_without_raising():
    set_policy(POLICY)
    set_mode("shadow")
    decision = guard_mcp_call("apply_discount", {"pct": 90})
    assert decision.outcome == "block"  # would-be violation, surfaced not raised
    assert collect_trace() == []  # output evidence is record_tool_call's job


def test_context_predicate_uses_active_context():
    set_policy(
        [
            {
                "id": "prod-only",
                "tool": "deploy",
                "context": [{"key": "env", "op": "==", "value": "prod"}],
                "action": "block",
            }
        ]
    )
    assert guard_mcp_call("deploy", {}, context={"env": "dev"}).outcome == "allow"
    set_context(env="prod")
    with pytest.raises(ToolBlocked):
        guard_mcp_call("deploy", {})
