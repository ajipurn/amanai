"""Runtime tool-call policy (Phase 2). Pure-logic, no infra."""

from amanai import (
    ToolBlocked,
    clear_tool_policy,
    collect_tool_calls,
    set_policy,
    tool,
)


def _blocked(fn, **kwargs) -> bool:
    try:
        fn(**kwargs)
        return False
    except ToolBlocked:
        return True


def test_block_rule_raises_and_is_not_recorded():
    set_policy([{"tool": "apply_discount", "arg": "pct", "op": ">=", "value": 50}])

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    assert _blocked(apply_discount, pct=100)
    assert collect_tool_calls() == []  # blocked call never executed, never recorded
    clear_tool_policy()


def test_allowed_under_threshold_is_recorded():
    set_policy([{"tool": "apply_discount", "arg": "pct", "op": ">=", "value": 50}])

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    apply_discount(pct=10)
    calls = collect_tool_calls()
    assert len(calls) == 1 and calls[0]["input"]["pct"] == 10
    clear_tool_policy()


def test_email_external_blocked_internal_allowed():
    set_policy(
        [{"tool": "send_email", "arg": "to", "op": "email_external", "value": ["acme.com"]}]
    )

    @tool
    def send_email(to, body):
        return {"to": to}

    assert _blocked(send_email, to="x@evil.com", body="b")
    send_email(to="ok@acme.com", body="b")
    assert len(collect_tool_calls()) == 1
    clear_tool_policy()


def test_warn_action_records_with_flag():
    set_policy(
        [{"tool": "apply_discount", "arg": "pct", "op": ">=", "value": 50, "action": "warn"}]
    )

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    apply_discount(pct=80)
    calls = collect_tool_calls()
    assert len(calls) == 1 and calls[0].get("policy_warning") is True
    clear_tool_policy()


def test_no_policy_allows_everything():
    clear_tool_policy()

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    apply_discount(pct=100)
    assert len(collect_tool_calls()) == 1
