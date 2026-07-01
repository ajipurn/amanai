"""Assert policy in tests — the pytest-facing side of the same policy contract.

CI runs attack prompts through your agent and asserts that the resulting actions
don't violate the policy you enforce at runtime. Because the engine is
deterministic, a CI pass means the runtime would have blocked the same calls.

    from amanai.testing import assert_blocked, assert_no_violations, replay

    def test_excessive_discount_is_blocked():
        set_policy("amanai.policy.json")
        assert_blocked(apply_discount, pct=90)

    def test_attack_trace_is_clean():
        run_agent(attack_prompt)               # produces a trace
        assert_no_violations(collect_trace())
"""

from __future__ import annotations

from contextlib import contextmanager

from amanai.policy import (
    ApprovalRequired,
    Policy,
    PolicyDecision,
    ToolBlocked,
    TraceEvent,
    evaluate,
    get_mode,
    set_mode,
)

# Outcomes that count as a policy violation in a recorded trace.
VIOLATION_OUTCOMES = ("block", "require_approval")
# Statuses meaning the action actually ran (despite the decision).
EXECUTED_STATUSES = ("executed", "shadowed")


@contextmanager
def using_mode(name: str):
    """Temporarily switch runtime mode (enforce/shadow/test), restoring after."""
    prev = get_mode()
    set_mode(name)
    try:
        yield
    finally:
        set_mode(prev)


def assert_blocked(fn, *args, **kwargs):
    """Assert that calling the protected `fn` is blocked (in enforce mode)."""
    with using_mode("enforce"):
        try:
            fn(*args, **kwargs)
        except ToolBlocked:
            return
    raise AssertionError(f"{getattr(fn, '__name__', fn)} was not blocked by policy")


def assert_requires_approval(fn, *args, **kwargs) -> ApprovalRequired:
    """Assert that calling `fn` is gated on approval (in enforce mode)."""
    with using_mode("enforce"):
        try:
            fn(*args, **kwargs)
        except ApprovalRequired as e:
            return e
    raise AssertionError(f"{getattr(fn, '__name__', fn)} did not require approval")


def assert_no_violations(events: list[TraceEvent], policy: Policy | None = None) -> None:
    """Assert that no *executed* action violated the policy.

    A `block`/`require_approval` action that enforce mode actually prevented
    (status `blocked`/`pending`) is the policy working — it does not count. Only
    a call that ran and violates the active (or passed) policy fails the gate.
    Re-evaluating matters: CI must test the policy you enforce now, not blindly
    trust whatever decision was stored in an old/manual trace."""
    bad = []
    for event in events:
        if event.status not in EXECUTED_STATUSES:
            continue
        decision = evaluate(event.action, policy)
        if decision.outcome in VIOLATION_OUTCOMES:
            bad.append((event, decision))
    if bad:
        offenders = ", ".join(f"{event.action.tool}[{decision.rule_id}]" for event, decision in bad)
        raise AssertionError(f"policy violations executed in trace: {offenders}")


def replay(events: list[TraceEvent], policy: Policy | None = None) -> list[PolicyDecision]:
    """Re-evaluate the actions in a recorded trace against the active (or a given)
    policy — reproduce an action-policy failure locally without side effects."""
    return [evaluate(e.action, policy) for e in events]
