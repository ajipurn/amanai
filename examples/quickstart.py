"""Amanai in 5 minutes: write ONE policy file, use it two ways.

  1. Runtime guard  — set_policy(rules) blocks a violating tool-call.
  2. Test assertion — the SAME rule becomes a tool_assertion detector your
     scan runs in CI.

Run:  PYTHONPATH=packages/sdk-python python examples/quickstart.py
"""

import json
import pathlib

from amanai import ToolBlocked, clear_tool_policy, set_policy, tool

RULES = json.loads((pathlib.Path(__file__).parent / "amanai.policy.json").read_text())


def demo() -> None:
    # ---- 1. Runtime guard -------------------------------------------------
    set_policy(RULES)

    @tool
    def apply_discount(pct):
        return {"pct": pct}

    blocked = False
    try:
        apply_discount(pct=90)  # violates pct >= 50
    except ToolBlocked:
        blocked = True
    assert blocked, "expected ToolBlocked for pct=90"
    assert apply_discount(pct=10) == {"pct": 10}, "compliant call should run"
    clear_tool_policy()

    # ---- 2. Same rule as a CI test assertion ------------------------------
    # The same rule, shaped as an Amanai tool_assertion detector for scans.
    detector = {"type": "tool_assertion", "assert": RULES[0]}
    assert detector["assert"] is RULES[0], "test assertion reuses the rule verbatim"

    print("PASS — one policy file guarded a tool-call and seeded a CI assertion.")


if __name__ == "__main__":
    demo()
