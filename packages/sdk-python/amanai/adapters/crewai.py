"""CrewAI adapter — enforce policy on CrewAI tools without rewriting them.

`guard_crewai_tool(tool)` returns a policy-gated CrewAI `BaseTool`: a blocked call
raises before the tool body runs. `crewai.tools` is imported lazily — the SDK stays
zero-dependency and only needs CrewAI when you call this.

    from amanai.adapters.crewai import guard_crewai_tool
    agent = Agent(..., tools=[guard_crewai_tool(t) for t in tools])
"""

from __future__ import annotations

from amanai.adapters import guard_tool_call
from amanai.client import record_tool_call


def _require_crewai():
    try:
        from crewai.tools import BaseTool  # noqa: F401
    except ImportError as e:
        raise ImportError("the CrewAI adapter needs crewai: pip install crewai") from e


def guard_crewai_tool(tool, *, capability: str | None = None, context: dict | None = None):
    """Return `tool` with its `_run` policy-gated: the guard runs before the tool
    body, so a blocked call raises `ToolBlocked` and the body never executes."""
    _require_crewai()
    name = getattr(tool, "name", None) or type(tool).__name__
    orig_run = tool._run

    def guarded_run(*args, **kwargs):
        arguments = dict(kwargs)
        if args:
            arguments["_args"] = list(args)
        guard_tool_call(name, arguments, capability=capability, context=context)
        result = orig_run(*args, **kwargs)
        record_tool_call(name, arguments, result, capability=capability, context=context)
        return result

    # ponytail: BaseTool is a pydantic model; object.__setattr__ bypasses field
    # validation to shadow the bound method. Sync path only.
    object.__setattr__(tool, "_run", guarded_run)
    return tool
