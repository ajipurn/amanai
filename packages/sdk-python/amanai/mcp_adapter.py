"""MCP adapter — gate live MCP tool-calls with the Action Policy Engine.

`guard_mcp_call` is the framework-neutral `guard_tool_call` (see
`amanai.adapters`): it takes the MCP call shape (`name: str`, `arguments: dict`)
directly, so it guards any MCP client/server without importing the `mcp` package.
This complements the *static* MCP checks in `judge.run_mcp_check`, which scan tool
*definitions*; this enforces policy on live tool *calls*.

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

from amanai.adapters import guard_tool_call as guard_mcp_call

__all__ = ["guard_mcp_call"]
