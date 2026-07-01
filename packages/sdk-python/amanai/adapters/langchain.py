"""LangChain adapter — enforce policy on LangChain tools without rewriting them.

`guard_langchain_tool(tool)` returns a policy-gated `BaseTool`: a blocked call
raises before the tool body runs (enforce mode). `AmanaiCallbackHandler` records a
trace in shadow mode for observe-only use. `langchain-core` is imported lazily —
the SDK stays zero-dependency and only needs LangChain when you call these.

    from amanai.adapters.langchain import guard_langchain_tool
    tools = [guard_langchain_tool(t) for t in tools]   # hand these to your agent
"""

from __future__ import annotations

from amanai.adapters import guard_tool_call
from amanai.client import record_tool_call


def _require_langchain():
    try:
        from langchain_core.tools import BaseTool  # noqa: F401
        from langchain_core.callbacks import BaseCallbackHandler  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "the LangChain adapter needs langchain-core: pip install langchain-core"
        ) from e


def guard_langchain_tool(tool, *, capability: str | None = None, context: dict | None = None):
    """Return `tool` with its `_run` (and `_arun`, if present) policy-gated: the
    guard runs before the tool body, so a blocked call raises `ToolBlocked` and the
    body never executes. `.name`/`.description`/`.args_schema` are preserved."""
    _require_langchain()
    name = getattr(tool, "name", None) or type(tool).__name__

    def _arguments(args, kwargs) -> dict:
        arguments = dict(kwargs)
        if args:
            arguments["_args"] = list(args)
        return arguments

    orig_run = tool._run

    def guarded_run(*args, **kwargs):
        arguments = _arguments(args, kwargs)
        guard_tool_call(name, arguments, capability=capability, context=context)
        result = orig_run(*args, **kwargs)
        record_tool_call(name, arguments, result, capability=capability, context=context)
        return result

    # ponytail: BaseTool is a pydantic model; object.__setattr__ bypasses field
    # validation to shadow the bound method with our closure. Sync path only —
    # patch _arun too if you use async tools.
    object.__setattr__(tool, "_run", guarded_run)

    orig_arun = getattr(tool, "_arun", None)
    if callable(orig_arun):

        async def guarded_arun(*args, **kwargs):
            arguments = _arguments(args, kwargs)
            guard_tool_call(name, arguments, capability=capability, context=context)
            result = await orig_arun(*args, **kwargs)
            record_tool_call(name, arguments, result, capability=capability, context=context)
            return result

        object.__setattr__(tool, "_arun", guarded_arun)

    return tool


def AmanaiCallbackHandler(*, capability: str | None = None, context: dict | None = None):
    """Build a LangChain callback handler that records a trace in shadow mode via
    `on_tool_start` — observe-only, does not block. Attach to an executor/run to
    trace tool-calls without wrapping the tools. (Factory: the base class is
    resolved lazily so importing this module needs no LangChain.)"""
    _require_langchain()
    from langchain_core.callbacks import BaseCallbackHandler

    class _Handler(BaseCallbackHandler):
        def on_tool_start(self, serialized, input_str, **kwargs):
            name = (serialized or {}).get("name", "tool")
            guard_tool_call(name, {"input": input_str}, capability=capability, context=context)

    return _Handler()
