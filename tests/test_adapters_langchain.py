"""LangChain adapter behavior (spec 0001). Skipped unless langchain-core is
installed; the zero-dep ImportError path is covered in test_adapters_import_free."""

import pytest

pytest.importorskip("langchain_core")

from langchain_core.tools import StructuredTool  # noqa: E402

from amanai import ToolBlocked, set_mode, set_policy  # noqa: E402
from amanai.adapters.langchain import guard_langchain_tool  # noqa: E402


def _tool(ran):
    def apply_discount(pct: int) -> str:
        ran.append(pct)
        return "applied"

    return StructuredTool.from_function(apply_discount)


def test_blocked_call_raises_before_body_runs():
    set_policy(
        [
            {
                "id": "cap",
                "tool": "apply_discount",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "too high",
            }
        ]
    )
    set_mode("enforce")
    ran: list = []
    tool = guard_langchain_tool(_tool(ran))
    with pytest.raises(ToolBlocked):
        tool.invoke({"pct": 90})
    assert ran == []  # body never executed


def test_allowed_call_runs_and_preserves_name():
    set_policy([])
    set_mode("enforce")
    ran: list = []
    tool = guard_langchain_tool(_tool(ran))
    assert tool.name == "apply_discount"
    assert tool.invoke({"pct": 10}) == "applied"
    assert ran == [10]
