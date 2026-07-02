"""Amanai SDK — policy-as-code for AI agent actions.

Test the policy in CI. Enforce the same policy at runtime. Keep evidence for audit.

The Action Policy Engine is the product center. Five verbs:

    from amanai import load_policy, set_policy, evaluate, tool, collect_trace

    set_policy(load_policy("amanai.policy.json"))   # 1. load policy

    @tool(capability="money_movement", risk="high")  # 3. protect tool
    def refund_payment(amount): ...

    evaluate(ActionRequest("refund_payment", {"amount": 500}))  # 2. evaluate action
    trace = collect_trace()                          # 4. collect trace
    # 5. assert in tests → amanai.testing

Decisions are deterministic — no LLM decides whether a high-risk tool runs.
Prompt-injection and PII guardrails remain supporting modules, not the center.
"""

from amanai.client import (
    approve_action,
    collect_tool_calls,
    collect_trace,
    record_tool_call,
    registered_tools,
    reset,
    tool,
    uncovered_tools,
)
from amanai.coverage import COVERAGE, coverage_for
from amanai.guardrails import (
    GuardrailBlocked,
    GuardResult,
    detect_injection,
    detect_pii,
    guard_input,
    guard_output,
    redact_pii,
    scan,
)
from amanai.adapters import guard_tool_call
from amanai.judge import run_detector, run_mcp_check
from amanai.linter import Finding, lint_policy
from amanai.mcp_adapter import guard_mcp_call
from amanai.monitor import Monitor
from amanai.redteam import Report, load_pack, run_pack
from amanai.policy import (
    MODES,
    OUTCOMES,
    ActionRequest,
    ApprovalRequired,
    PendingAction,
    Policy,
    PolicyDecision,
    PolicyError,
    Rule,
    ToolBlocked,
    TraceEvent,
    clear_context,
    clear_tool_policy,
    evaluate,
    get_context,
    get_mode,
    get_policy,
    load_policy,
    load_trace,
    set_context,
    set_mode,
    set_policy,
)

__all__ = [
    # --- Action Policy Engine ---
    "load_policy",
    "load_trace",
    "set_policy",
    "get_policy",
    "evaluate",
    "Policy",
    "Rule",
    "ActionRequest",
    "PolicyDecision",
    "TraceEvent",
    "PendingAction",
    "ToolBlocked",
    "ApprovalRequired",
    "PolicyError",
    "OUTCOMES",
    "MODES",
    # modes & context
    "set_mode",
    "get_mode",
    "set_context",
    "get_context",
    "clear_context",
    # protect & collect
    "tool",
    "approve_action",
    "record_tool_call",
    "collect_tool_calls",
    "collect_trace",
    "reset",
    "registered_tools",
    "uncovered_tools",
    # adapters (framework funnel)
    "guard_tool_call",
    "guard_mcp_call",
    # --- supporting: offline judge & MCP static checks ---
    "run_detector",
    "run_mcp_check",
    # --- policy linter ---
    "lint_policy",
    "Finding",
    # --- red-team pack ---
    "load_pack",
    "run_pack",
    "Report",
    # clear active policy
    "clear_tool_policy",
    # --- supporting: guardrails ---
    "scan",
    "guard_input",
    "guard_output",
    "redact_pii",
    "detect_injection",
    "detect_pii",
    "GuardResult",
    "GuardrailBlocked",
    # --- supporting: monitoring & coverage ---
    "Monitor",
    "COVERAGE",
    "coverage_for",
]
__version__ = "0.3.1"
