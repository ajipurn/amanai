"""CrewAI adapter behavior (spec 0001). Skipped unless crewai is installed; the
zero-dep ImportError path is covered in test_adapters_import_free."""

import pytest

pytest.importorskip("crewai")

from crewai.tools import BaseTool  # noqa: E402

from amanai import ToolBlocked, set_mode, set_policy  # noqa: E402
from amanai.adapters.crewai import guard_crewai_tool  # noqa: E402

_RAN: list = []


class ApplyDiscount(BaseTool):
    name: str = "apply_discount"
    description: str = "apply a discount percentage"

    def _run(self, pct: int) -> str:
        _RAN.append(pct)
        return "applied"


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
    _RAN.clear()
    tool = guard_crewai_tool(ApplyDiscount())
    with pytest.raises(ToolBlocked):
        tool._run(pct=90)
    assert _RAN == []
