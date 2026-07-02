"""Approval grant/resume protocol — the SDK side of a human-in-the-loop flow.

The engine parks a `require_approval` action (`ApprovalRequired.pending`), the app
persists its token wherever approvals live (a queue, an inbox, a human), and
`approve_action(token)` grants exactly one execution. The inbox/UI itself is the
caller's (or a server product's) job; only the protocol lives in the SDK."""

import pytest

from amanai import (
    ApprovalRequired,
    approve_action,
    collect_trace,
    guard_tool_call,
    set_policy,
    tool,
)
from amanai.policy import ActionRequest, PendingAction, PolicyDecision
from amanai.testing import assert_no_violations

POLICY = [
    {
        "id": "big-refund",
        "tool": "refund_payment",
        "args": [{"arg": "amount", "op": ">=", "value": 1000}],
        "action": "require_approval",
        "reason": "large refund needs a human",
    }
]


def _park(fn, **kwargs) -> str:
    """Call a gated tool, return the pending token it parks."""
    with pytest.raises(ApprovalRequired) as e:
        fn(**kwargs)
    return e.value.pending.token


def test_approval_grants_exactly_one_execution():
    set_policy(POLICY)
    ran = []

    @tool
    def refund_payment(amount):
        ran.append(amount)
        return "refunded"

    token = _park(refund_payment, amount=5000)
    approve_action(token)
    assert refund_payment(amount=5000) == "refunded"  # grant consumed here
    assert ran == [5000]

    with pytest.raises(ApprovalRequired):  # one-shot: same call needs approval again
        refund_payment(amount=5000)
    assert ran == [5000]


def test_approved_execution_is_recorded_as_approved_evidence():
    set_policy(POLICY)

    @tool
    def refund_payment(amount):
        return "refunded"

    token = _park(refund_payment, amount=5000)
    collect_trace()  # drop the pending event
    approve_action(token)
    refund_payment(amount=5000)
    event = collect_trace()[0]
    assert event.status == "approved"
    assert event.decision.outcome == "require_approval"


def test_approve_action_rejects_garbage():
    with pytest.raises(ValueError):
        approve_action("not-a-token")
    with pytest.raises(ValueError):
        approve_action(None)


def test_guard_tool_call_approved_path_returns_decision_and_records():
    set_policy(POLICY)
    with pytest.raises(ApprovalRequired) as e:
        guard_tool_call("refund_payment", {"amount": 5000})
    collect_trace()

    approve_action(e.value.pending)  # PendingAction accepted directly
    decision = guard_tool_call("refund_payment", {"amount": 5000})
    assert decision.outcome == "require_approval"  # caller dispatches
    assert collect_trace()[0].status == "approved"


def test_assert_no_violations_judges_approved_correctly():
    set_policy(POLICY)

    @tool
    def refund_payment(amount):
        return "refunded"

    token = _park(refund_payment, amount=5000)
    approve_action(token)
    refund_payment(amount=5000)
    events = collect_trace()
    assert_no_violations(events)  # approved is the sanctioned path — no violation

    # But an approval grant cannot sanction an action the policy now blocks.
    from amanai import load_policy

    block_now = load_policy(
        [
            {
                "id": "big-refund",
                "tool": "refund_payment",
                "args": [{"arg": "amount", "op": ">=", "value": 1000}],
                "action": "block",
            }
        ]
    )
    with pytest.raises(AssertionError):
        assert_no_violations(events, block_now)


def test_pending_token_is_cross_language_canonical():
    """Locked value — the TS SDK's pendingToken() must produce the identical token
    for the identical action (see packages/sdk-node/test/client.test.ts)."""
    a = ActionRequest("refund_payment", {"amount": 5000})
    assert PendingAction(a, PolicyDecision("require_approval")).token == "pending-bcbb2530"
