"""Protect tools and collect traces — the runtime entry point into the engine.

`@tool` is a thin adapter: it normalizes the call into an `ActionRequest`, asks
the Action Policy Engine for a decision, enforces it according to the current
mode, and records a `TraceEvent` as evidence. The policy logic lives in
`policy.py`; this module only wires real Python calls into it.

    from amanai import tool, set_policy, collect_trace

    @tool(capability="money_movement", risk="high")
    def refund_payment(amount): ...

    set_policy("amanai.policy.json")
    refund_payment(amount=500)          # ToolBlocked / ApprovalRequired per policy
    trace = collect_trace()             # canonical evidence for CI / monitoring
"""

from __future__ import annotations

import contextvars
import functools
import inspect
from typing import Any, Callable

from amanai.policy import (
    ActionRequest,
    ApprovalRequired,
    PendingAction,
    Policy,
    ToolBlocked,
    TraceEvent,
    evaluate,
    get_context,
    get_mode,
    get_policy,
)

# Context-local trace buffer — concurrent requests never see each other's calls.
_trace: contextvars.ContextVar[list | None] = contextvars.ContextVar("amanai_trace", default=None)

# Static, declaration-time inventory of every protected tool (for security review).
_REGISTRY: dict[str, dict] = {}


def _buffer() -> list:
    buf = _trace.get()
    if buf is None:
        buf = []
        _trace.set(buf)
    return buf


def record_event(event: TraceEvent) -> None:
    _buffer().append(event)


def _normalize_args(fn: Callable, args: tuple, kwargs: dict) -> dict:
    """Map a call to {param_name: value} so policies match regardless of whether
    the tool was called positionally or by keyword (`apply_discount(50)` ==
    `apply_discount(pct=50)`)."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)
        out: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name not in bound.arguments:
                continue
            val = bound.arguments[name]
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                out.update(val)  # **kwargs → flatten to top level
            elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                out[name] = list(val)  # *args → keep as a list
            else:
                out[name] = val
        return out
    except (TypeError, ValueError):
        # Builtins / C-functions without an introspectable signature.
        out = dict(kwargs)
        if args:
            out["_args"] = list(args)
        return out


def record_tool_call(
    tool_name: str,
    tool_input: dict,
    tool_output: Any,
    *,
    capability: str | None = None,
    context: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """Manually record an executed tool-call.

    Use this when you can't decorate the function. Because the tool has already
    run, Amanai cannot prevent it here; it still evaluates the active policy and
    marks policy violations as `shadowed` so CI/monitoring can catch bypasses.
    """
    action = ActionRequest(
        tool_name,
        dict(tool_input),
        capability=capability,
        context=context if context is not None else get_context(),
        metadata=metadata or {},
    )
    decision = evaluate(action)
    status = "shadowed" if decision.outcome in ("block", "require_approval") else "executed"
    record_event(TraceEvent(action, decision, status=status, output=tool_output))


def tool(
    fn: Callable | None = None,
    *,
    name: str | None = None,
    capability: str | None = None,
    risk: str | None = None,
    input_schema: dict | None = None,
):
    """Protect a function with the Action Policy Engine.

    Usage: `@tool` or `@tool(name="billing.refund", capability="money_movement")`.

    Behavior depends on the current mode (`enforce` by default):
      * enforce — `block` raises `ToolBlocked`, `require_approval` raises
        `ApprovalRequired`; neither runs the function.
      * shadow  — violations execute anyway but are recorded as evidence.
      * test    — nothing executes (no side effects); the decision is recorded.
    """

    def decorate(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        meta = {
            "capability": capability,
            "risk": risk,
            "input_schema": input_schema,
            "python_name": fn.__name__,
        }
        _REGISTRY[tool_name] = meta

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            inp = _normalize_args(fn, args, kwargs)
            action = ActionRequest(
                tool_name, inp, capability=capability, context=get_context(), metadata=meta
            )
            decision = evaluate(action)
            mode = get_mode()

            if mode == "test":
                record_event(TraceEvent(action, decision, status="evaluated"))
                return None

            if decision.outcome == "block" and mode == "enforce":
                record_event(TraceEvent(action, decision, status="blocked"))
                raise ToolBlocked(decision.reason or f"{tool_name} blocked by policy")
            if decision.outcome == "require_approval" and mode == "enforce":
                pending = PendingAction(action, decision)
                record_event(TraceEvent(action, decision, status="pending"))
                raise ApprovalRequired(pending)

            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                record_event(TraceEvent(action, decision, status="error", error=str(e)))
                raise

            # In shadow mode a would-be-blocked call still ran — mark it.
            shadowed = decision.outcome in ("block", "require_approval")
            record_event(
                TraceEvent(
                    action, decision, status="shadowed" if shadowed else "executed", output=result
                )
            )
            return result

        return wrapper

    return decorate(fn) if callable(fn) else decorate


def collect_trace() -> list[TraceEvent]:
    """Return the canonical trace events recorded so far and clear the buffer."""
    buf = _trace.get() or []
    _trace.set([])
    return list(buf)


def collect_tool_calls() -> list:
    """Legacy view: the executed tool-calls as `{tool, input, output}` dicts.

    Derived from the trace — blocked/pending/evaluated actions are omitted, so a
    test can prove a dangerous function did not run. Drains the buffer (use
    `collect_trace` if you want the full evidence instead)."""
    out = []
    for e in collect_trace():
        if e.status in ("executed", "shadowed"):
            rec = {"tool": e.action.tool, "input": dict(e.action.input), "output": e.output}
            if e.decision.outcome == "warn":
                rec["policy_warning"] = True
            out.append(rec)
    return out


def reset() -> None:
    _trace.set([])


def registered_tools() -> dict[str, dict]:
    """Every `@tool`-protected function and its declared capability/risk/schema —
    the inventory a security engineer reviews for high-risk actions."""
    return dict(_REGISTRY)


def uncovered_tools(policy: Policy | None = None) -> list[str]:
    """Names of registered tools that no rule covers (by tool name or capability)
    in the given (or active) policy — risky actions left silently unprotected."""
    pol = policy if policy is not None else get_policy()
    names, caps = set(), set()
    if pol is not None:
        for r in pol.rules:
            if r.tool:
                names.add(r.tool)
            if r.capability:
                caps.add(r.capability)
    return [
        name
        for name, meta in _REGISTRY.items()
        if name not in names and meta.get("capability") not in caps
    ]
