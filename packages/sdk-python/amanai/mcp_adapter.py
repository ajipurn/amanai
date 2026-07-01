"""MCP adapter — gate live MCP tool-calls with the Action Policy Engine.

Dep-free and duck-typed: takes the MCP call shape (`name: str`, `arguments: dict`)
directly, so it guards any MCP client/server without importing the `mcp` package
(PRD: minimal SDK deps). This complements the *static* MCP checks in
`judge.run_mcp_check`, which scan tool *definitions*; this enforces policy on
live tool *calls*.

    from amanai import set_policy
    from amanai.mcp_adapter import guard_mcp_call

    set_policy("amanai.policy.json")

    # in your MCP client/server, before forwarding a tools/call:
    guard_mcp_call("apply_discount", {"pct": 90})     # -> ToolBlocked (enforce)
    result = await session.call_tool("apply_discount", {"pct": 90})
    record_tool_call("apply_discount", {"pct": 90}, result)   # evidence w/ output

`guard_mcp_call` only *gates* (the transport still does the call). For executed
evidence with the real tool output, reuse `record_tool_call` after forwarding.
"""

from __future__ import annotations

from amanai.client import record_event  # shared context-local trace buffer
from amanai.policy import (
    ActionRequest,
    ApprovalRequired,
    PendingAction,
    PolicyDecision,
    ToolBlocked,
    TraceEvent,
    evaluate,
    get_context,
    get_mode,
)


def guard_mcp_call(
    name: str,
    arguments: dict | None = None,
    *,
    capability: str | None = None,
    context: dict | None = None,
) -> PolicyDecision:
    """Evaluate an MCP tool-call and enforce the active policy before it runs.

    enforce: `block` raises `ToolBlocked`, `require_approval` raises
             `ApprovalRequired` — neither is forwarded.
    shadow / test: returns the decision without raising; the caller decides
             whether to forward. (Shadow keeps running; test should skip.)

    Always returns the `PolicyDecision`. Log the executed call + output with
    `record_tool_call` after the transport forwards it.
    """
    action = ActionRequest(
        name,
        dict(arguments or {}),
        capability=capability,
        context=context if context is not None else get_context(),
    )
    decision = evaluate(action)

    if get_mode() == "enforce":
        if decision.outcome == "block":
            record_event(TraceEvent(action, decision, status="blocked"))
            raise ToolBlocked(decision.reason or f"{name} blocked by policy")
        if decision.outcome == "require_approval":
            record_event(TraceEvent(action, decision, status="pending"))
            raise ApprovalRequired(PendingAction(action, decision))

    return decision
