"""Framework adapters — funnel any framework's tool-call into the policy engine.

The engine is framework-neutral: give it a tool name and an argument dict and it
decides. `guard_tool_call` is that funnel (the generalized form of the MCP
adapter's `guard_mcp_call`). The per-framework modules — `amanai.adapters.openai`,
`.langchain`, `.crewai` — only extract `(name, args)` from the framework's own
shape and call it, so adopting Amanai never means rewriting each tool definition.

Importing this package pulls in **no** framework; the per-framework modules import
their framework lazily, inside the call, and raise a clear `ImportError` if it is
missing. The SDK stays zero-dependency.
"""

from __future__ import annotations

from amanai.client import record_event as _record_event
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

__all__ = ["guard_tool_call"]


def guard_tool_call(
    name: str,
    arguments: dict | None = None,
    *,
    capability: str | None = None,
    context: dict | None = None,
) -> PolicyDecision:
    """Evaluate and enforce a tool-call before it runs — the framework-neutral core.

    enforce: `block` raises `ToolBlocked`, `require_approval` raises
             `ApprovalRequired` (both record a `TraceEvent` first); neither runs.
    shadow / test: returns the decision without raising; the caller decides whether
             to forward. Always returns the `PolicyDecision`.

    This only *gates*. For executed evidence with the real tool output, call
    `record_tool_call` after the tool runs.
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
            _record_event(TraceEvent(action, decision, status="blocked"))
            raise ToolBlocked(decision.reason or f"{name} blocked by policy")
        if decision.outcome == "require_approval":
            _record_event(TraceEvent(action, decision, status="pending"))
            raise ApprovalRequired(PendingAction(action, decision))

    return decision
