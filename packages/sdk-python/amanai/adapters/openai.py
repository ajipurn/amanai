"""OpenAI / Anthropic tool-call adapter — gate a provider tool-call, no SDK import.

Duck-typed on attributes, so it works without `openai` or `anthropic` installed:

  * OpenAI:    tool_call.function.name + tool_call.function.arguments (JSON string)
  * Anthropic: tool_call.name + tool_call.input (dict)
  * dict forms of either ({"function": {...}} / {"name": ..., "input": ...})

Usage in your tool-call loop, before dispatching the tool:

    from amanai import set_policy
    from amanai.adapters.openai import guard_openai_tool_call

    set_policy("amanai.policy.json")
    for tc in response.choices[0].message.tool_calls:
        guard_openai_tool_call(tc)      # raises ToolBlocked/ApprovalRequired in enforce
        result = dispatch(tc)           # your existing dispatch
"""

from __future__ import annotations

import json

from amanai.adapters import guard_tool_call
from amanai.policy import PolicyDecision


def _name_args(name, args) -> tuple[str, dict]:
    if not name:
        raise ValueError("tool-call has no name")
    if args is None:
        args = {}
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"tool-call arguments are not valid JSON: {e}") from e
    if not isinstance(args, dict):
        raise ValueError(f"tool-call arguments must be an object, got {type(args).__name__}")
    return str(name), dict(args)


def extract_openai_tool_call(tool_call) -> tuple[str, dict]:
    """Return `(name, args)` from an OpenAI/Anthropic tool-call object or dict.
    Parses a JSON `arguments` string. Raises `ValueError` on an unrecognized shape."""
    if isinstance(tool_call, dict):
        if "function" in tool_call:
            fn = tool_call["function"] or {}
            return _name_args(fn.get("name"), fn.get("arguments"))
        if "name" in tool_call:
            return _name_args(
                tool_call.get("name"), tool_call.get("input", tool_call.get("arguments"))
            )
        raise ValueError(f"unrecognized tool-call dict: keys={list(tool_call)}")

    fn = getattr(tool_call, "function", None)
    if fn is not None:  # OpenAI shape
        return _name_args(getattr(fn, "name", None), getattr(fn, "arguments", None))

    name = getattr(tool_call, "name", None)
    if name is not None:  # Anthropic shape
        args = getattr(tool_call, "input", None)
        if args is None:
            args = getattr(tool_call, "arguments", None)
        return _name_args(name, args)

    raise ValueError(f"unrecognized tool-call object: {tool_call!r}")


def guard_openai_tool_call(
    tool_call, *, capability: str | None = None, context: dict | None = None
) -> PolicyDecision:
    """Extract `(name, args)` from a provider tool-call and enforce the active
    policy before it runs. Call this in your loop before dispatching the tool."""
    name, args = extract_openai_tool_call(tool_call)
    return guard_tool_call(name, args, capability=capability, context=context)
