"""Action Policy Engine — behavior through the public interface.

Covers the PRD's testing decisions: deterministic decisions per outcome, the
three modes, validation, context-local traces, capability/context matching, and
the test↔enforce parity that is the product's whole point."""

import contextvars
import json

import pytest

from amanai import (
    ActionRequest,
    ApprovalRequired,
    PolicyError,
    ToolBlocked,
    TraceEvent,
    clear_tool_policy,
    collect_tool_calls,
    collect_trace,
    evaluate,
    get_policy,
    load_policy,
    record_tool_call,
    registered_tools,
    set_context,
    set_mode,
    set_policy,
    tool,
    uncovered_tools,
)
from amanai.testing import (
    assert_blocked,
    assert_no_violations,
    assert_requires_approval,
    replay,
)


# ── deterministic decisions per outcome ───────────────────────────────────────
@pytest.mark.parametrize("action", ["allow", "block", "warn", "require_approval"])
def test_evaluate_is_deterministic_per_outcome(action):
    set_policy(
        [{"id": "r", "tool": "t", "args": [{"arg": "x", "op": ">=", "value": 1}], "action": action}]
    )
    d1 = evaluate(ActionRequest("t", {"x": 5}))
    d2 = evaluate(ActionRequest("t", {"x": 5}))
    assert d1.outcome == d2.outcome == action
    assert d1.rule_id == "r"


def test_no_matching_rule_allows():
    set_policy([{"id": "r", "tool": "t", "args": [{"arg": "x", "op": ">=", "value": 100}]}])
    d = evaluate(ActionRequest("t", {"x": 5}))
    assert d.outcome == "allow" and d.rule_id is None


def test_no_policy_loaded_allows():
    assert evaluate(ActionRequest("anything", {})).outcome == "allow"


# ── enforce mode ──────────────────────────────────────────────────────────────
def test_block_does_not_execute_in_enforce():
    set_policy(
        [
            {
                "id": "b",
                "tool": "act",
                "args": [{"arg": "n", "op": ">=", "value": 10}],
                "action": "block",
                "reason": "too big",
            }
        ]
    )
    ran = []

    @tool
    def act(n):
        ran.append(n)
        return n

    with pytest.raises(ToolBlocked):
        act(n=50)
    assert ran == []  # dangerous function never ran
    trace = collect_trace()
    assert len(trace) == 1 and trace[0].status == "blocked"
    assert trace[0].decision.reason == "too big"


def test_require_approval_does_not_execute_in_enforce():
    set_policy(
        [
            {
                "id": "a",
                "tool": "act",
                "args": [{"arg": "n", "op": ">", "value": 100}],
                "action": "require_approval",
            }
        ]
    )
    ran = []

    @tool
    def act(n):
        ran.append(n)
        return n

    err = assert_requires_approval(act, n=500)
    assert ran == []
    assert isinstance(err, ApprovalRequired)
    assert err.pending.decision.outcome == "require_approval"
    assert err.pending.token.startswith("pending-")
    assert collect_trace()[0].status == "pending"


def test_warn_executes_and_records_evidence():
    set_policy(
        [
            {
                "id": "w",
                "tool": "act",
                "args": [{"arg": "n", "op": ">=", "value": 10}],
                "action": "warn",
            }
        ]
    )

    @tool
    def act(n):
        return {"n": n}

    assert act(n=50) == {"n": 50}
    trace = collect_trace()
    assert trace[0].status == "executed" and trace[0].decision.outcome == "warn"


# ── shadow mode ───────────────────────────────────────────────────────────────
def test_shadow_executes_but_records_violation():
    set_policy(
        [
            {
                "id": "b",
                "tool": "act",
                "args": [{"arg": "n", "op": ">=", "value": 10}],
                "action": "block",
            }
        ]
    )
    set_mode("shadow")
    ran = []

    @tool
    def act(n):
        ran.append(n)
        return n

    assert act(n=50) == 50  # ran anyway
    assert ran == [50]
    trace = collect_trace()
    assert trace[0].status == "shadowed" and trace[0].decision.outcome == "block"


def test_shadow_ci_flags_would_be_violation():
    set_policy(
        [
            {
                "id": "d",
                "tool": "apply_discount",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
            }
        ]
    )
    set_mode("shadow")

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    apply_discount(pct=90)
    with pytest.raises(AssertionError):  # the trace records a would-be violation
        assert_no_violations(collect_trace())


# ── test mode (no side effects) ───────────────────────────────────────────────
def test_test_mode_has_no_side_effects():
    set_policy(
        [
            {
                "id": "x",
                "tool": "act",
                "args": [{"arg": "n", "op": ">=", "value": 1}],
                "action": "allow",
            }
        ]
    )
    set_mode("test")
    ran = []

    @tool
    def act(n):
        ran.append(n)
        return n

    assert act(n=5) is None  # tool body never invoked
    assert ran == []
    assert collect_trace()[0].status == "evaluated"


# ── canonical schema & normalization ──────────────────────────────────────────
def test_trace_event_canonical_shape():
    @tool
    def act(n):
        return {"n": n}

    act(n=3)
    event = collect_trace()[0]
    d = event.to_dict()
    assert set(d) == {"id", "ts", "action", "decision", "status", "output", "error"}
    assert d["id"].startswith("evt-") and len(d["id"]) == 4 + 32
    assert d["ts"].endswith("Z")  # canonical UTC, same format as the TS SDK
    assert d["action"]["tool"] == "act" and d["action"]["input"] == {"n": 3}
    assert d["decision"]["outcome"] == "allow"
    assert d["status"] == "executed"


def test_decision_records_policy_digest():
    """Evidence must answer "which policy version decided this?": every decision
    made under a policy carries its digest; no policy → None."""
    set_policy([{"id": "d", "tool": "apply", "args": [{"arg": "pct", "op": ">=", "value": 50}]}])

    @tool
    def apply(pct):
        return pct

    digest = get_policy().digest
    assert digest.startswith("policy-")

    apply(pct=10)  # allowed, but still evaluated under the policy
    event = collect_trace()[0]
    assert event.decision.policy_digest == digest

    clear_tool_policy()
    apply(pct=90)
    assert collect_trace()[0].decision.policy_digest is None  # no policy loaded


def test_policy_digest_is_stable_and_version_sensitive():
    rules = [{"id": "d", "tool": "apply", "args": [{"arg": "pct", "op": ">=", "value": 50}]}]
    assert load_policy(rules).digest == load_policy(rules).digest  # same rules, same digest
    changed = [{"id": "d", "tool": "apply", "args": [{"arg": "pct", "op": ">=", "value": 60}]}]
    assert load_policy(rules).digest != load_policy(changed).digest  # any edit, new version


def test_trace_round_trip_preserves_id_ts_and_legacy_loads_empty():
    @tool
    def act(n):
        return n

    act(n=1)
    event = collect_trace()[0]
    again = TraceEvent.from_dict(event.to_dict())
    assert (again.id, again.ts) == (event.id, event.ts)

    # Pre-0.3 trace: no id/ts — loads as "" (unknown), never fabricated on load.
    legacy = {k: v for k, v in event.to_dict().items() if k not in ("id", "ts")}
    old = TraceEvent.from_dict(legacy)
    assert old.id == "" and old.ts == ""


def test_positional_args_are_normalized():
    set_policy([{"id": "d", "tool": "apply", "args": [{"arg": "pct", "op": ">=", "value": 50}]}])

    @tool
    def apply(pct):
        return pct

    with pytest.raises(ToolBlocked):
        apply(90)  # positional still matches the named-arg predicate


# ── capability & context matching ─────────────────────────────────────────────
def test_capability_rule_matches_tagged_tool():
    set_policy(
        [
            {
                "id": "ext",
                "capability": "external_comms",
                "args": [{"arg": "to", "op": "email_external", "value": ["acme.com"]}],
                "action": "block",
            }
        ]
    )

    @tool(capability="external_comms")
    def send(to, body):
        return {"to": to}

    assert_blocked(send, to="x@evil.com", body="b")
    assert send(to="ok@acme.com", body="b") == {"to": "ok@acme.com"}  # internal allowed


def test_context_rule_uses_role_and_tenant():
    set_policy(
        [
            {
                "id": "support-cap",
                "tool": "refund",
                "context": [{"key": "role", "op": "==", "value": "support"}],
                "args": [{"arg": "amount", "op": ">", "value": 100}],
                "action": "block",
            }
        ]
    )
    support = ActionRequest("refund", {"amount": 500}, context={"role": "support", "tenant": "t1"})
    admin = ActionRequest("refund", {"amount": 500}, context={"role": "admin"})
    assert evaluate(support).outcome == "block"
    assert evaluate(admin).outcome == "allow"


def test_tool_injects_active_context():
    set_policy(
        [
            {
                "id": "env",
                "tool": "deploy",
                "context": [{"key": "environment", "op": "==", "value": "prod"}],
                "args": [{"arg": "force", "op": "==", "value": True}],
                "action": "block",
            }
        ]
    )
    set_context(environment="prod", user_id="u1")

    @tool
    def deploy(force):
        return force

    assert_blocked(deploy, force=True)


# ── validation ────────────────────────────────────────────────────────────────
def test_missing_id_gets_deterministic_id():
    rule = {"tool": "t", "arg": "a", "op": ">=", "value": 1}
    p1, p2 = load_policy([dict(rule)]), load_policy([dict(rule)])
    assert p1.ids[0].startswith("rule-")
    assert p1.ids == p2.ids  # stable across loads


def test_require_ids_rejects_missing_id():
    with pytest.raises(PolicyError):
        load_policy([{"tool": "t", "arg": "a", "op": ">=", "value": 1}], require_ids=True)


def test_unknown_operator_rejected():
    with pytest.raises(PolicyError, match="unknown operator"):
        load_policy([{"id": "x", "tool": "t", "args": [{"arg": "a", "op": "~=", "value": 1}]}])


def test_unsupported_action_rejected():
    with pytest.raises(PolicyError, match="unsupported action"):
        load_policy(
            [
                {
                    "id": "x",
                    "tool": "t",
                    "action": "nuke",
                    "args": [{"arg": "a", "op": ">", "value": 1}],
                }
            ]
        )


def test_malformed_predicate_rejected():
    with pytest.raises(PolicyError):
        load_policy([{"id": "x", "tool": "t", "args": [{"op": ">", "value": 1}]}])  # no arg


def test_rule_without_tool_or_capability_rejected():
    with pytest.raises(PolicyError, match="tool.*capability"):
        load_policy([{"id": "x", "args": [{"arg": "a", "op": ">", "value": 1}]}])


def test_duplicate_ids_rejected():
    with pytest.raises(PolicyError, match="duplicate"):
        load_policy(
            [
                {"id": "d", "tool": "t", "args": [{"arg": "a", "op": ">", "value": 1}]},
                {"id": "d", "tool": "u", "args": [{"arg": "b", "op": "<", "value": 2}]},
            ]
        )


def test_invalid_json_string_rejected():
    with pytest.raises(PolicyError, match="JSON"):
        load_policy("{not valid json")


def test_load_from_file(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps([{"id": "r", "tool": "t", "args": [{"arg": "a", "op": ">", "value": 1}]}])
    )
    assert load_policy(str(f)).ids == ["r"]


# ── operators added by the engine ─────────────────────────────────────────────
def test_regex_and_membership_operators():
    pol = load_policy(
        [
            {
                "id": "rx",
                "tool": "t",
                "args": [{"arg": "cmd", "op": "regex", "value": r"rm\s+-rf"}],
                "action": "block",
            },
            {
                "id": "mem",
                "tool": "u",
                "args": [{"arg": "region", "op": "in", "value": ["eu", "us"]}],
                "action": "warn",
            },
        ]
    )
    assert evaluate(ActionRequest("t", {"cmd": "rm -rf /"}), pol).outcome == "block"
    assert evaluate(ActionRequest("t", {"cmd": "ls"}), pol).outcome == "allow"
    assert evaluate(ActionRequest("u", {"region": "eu"}), pol).outcome == "warn"
    assert evaluate(ActionRequest("u", {"region": "apac"}), pol).outcome == "allow"


def test_domain_in_operator():
    pol = load_policy(
        [
            {
                "id": "blk",
                "tool": "send",
                "args": [{"arg": "to", "op": "domain_in", "value": ["evil.com"]}],
                "action": "block",
            }
        ]
    )
    assert evaluate(ActionRequest("send", {"to": "a@evil.com"}), pol).outcome == "block"
    assert evaluate(ActionRequest("send", {"to": "a@good.com"}), pol).outcome == "allow"


# ── context-local trace isolation ─────────────────────────────────────────────
def test_trace_storage_is_context_local():
    @tool
    def ping(x):
        return {"x": x}

    def request(v):
        from amanai import reset

        reset()  # each request starts its own buffer (context-local write)
        ping(x=v)
        return collect_tool_calls()

    r1 = contextvars.copy_context().run(request, 1)
    r2 = contextvars.copy_context().run(request, 2)
    assert [c["input"]["x"] for c in r1] == [1]
    assert [c["input"]["x"] for c in r2] == [2]
    assert collect_tool_calls() == []  # this context untouched by either request


# ── replay & inventory ────────────────────────────────────────────────────────
def test_replay_reevaluates_trace_against_policy():
    @tool
    def act(n):
        return n

    act(n=5)
    act(n=50)  # both run with no policy active
    trace = collect_trace()
    pol = load_policy(
        [
            {
                "id": "r",
                "tool": "act",
                "args": [{"arg": "n", "op": ">=", "value": 10}],
                "action": "block",
            }
        ]
    )
    assert [d.outcome for d in replay(trace, pol)] == ["allow", "block"]


def test_assert_no_violations_reevaluates_trace_against_current_policy():
    @tool
    def act(n):
        return n

    act(n=50)  # recorded as allowed because no policy was active yet
    trace = collect_trace()
    set_policy([{"id": "r", "tool": "act", "args": [{"arg": "n", "op": ">=", "value": 10}]}])

    with pytest.raises(AssertionError, match="act\\[r\\]"):
        assert_no_violations(trace)


def test_manual_record_evaluates_policy_and_flags_executed_violation():
    set_policy(
        [
            {
                "id": "discount-cap",
                "tool": "apply_discount",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
            }
        ]
    )

    record_tool_call("apply_discount", {"pct": 90}, {"ok": True})
    trace = collect_trace()
    assert trace[0].decision.outcome == "block"
    assert trace[0].status == "shadowed"
    with pytest.raises(AssertionError, match="apply_discount\\[discount-cap\\]"):
        assert_no_violations(trace)


def test_tool_can_use_stable_policy_name():
    set_policy(
        [
            {
                "id": "refund-limit",
                "tool": "billing.refund.test",
                "args": [{"arg": "amount", "op": ">", "value": 100}],
            }
        ]
    )

    @tool(name="billing.refund.test", capability="money_movement")
    def refund(amount):
        return {"amount": amount}

    with pytest.raises(ToolBlocked):
        refund(amount=500)
    trace = collect_trace()
    assert trace[0].action.tool == "billing.refund.test"
    assert registered_tools()["billing.refund.test"]["python_name"] == "refund"


def test_uncovered_tools_flags_unprotected():
    @tool(capability="money_apt")
    def covered_by_cap(x):
        return x

    @tool
    def covered_by_name_apt(x):
        return x

    @tool
    def naked_apt(x):
        return x

    pol = load_policy(
        [
            {"id": "c", "capability": "money_apt", "args": [{"arg": "x", "op": ">", "value": 0}]},
            {
                "id": "n",
                "tool": "covered_by_name_apt",
                "args": [{"arg": "x", "op": ">", "value": 0}],
            },
        ]
    )
    u = uncovered_tools(pol)
    assert "naked_apt" in u
    assert "covered_by_cap" not in u and "covered_by_name_apt" not in u
