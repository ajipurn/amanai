"""Cross-language parity (spec 0004): the Python engine must decide every shared
vector in `spec/parity/vectors.json` identically to the Node engine. The Node side
runs the same file in `packages/sdk-node/test/parity.test.ts`; if the two engines
diverge, one of these suites fails."""

import json
from pathlib import Path

import pytest

from amanai import ActionRequest, evaluate, load_policy

VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "parity" / "vectors.json").read_text()
)


@pytest.mark.parametrize("vec", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vector_decides_as_expected(vec):
    policy = load_policy(vec["policy"])
    a = vec["action"]
    action = ActionRequest(
        a["tool"],
        a.get("input", {}),
        capability=a.get("capability"),
        context=a.get("context", {}),
    )
    decision = evaluate(action, policy)
    assert decision.outcome == vec["expect"]["outcome"]
    assert decision.rule_id == vec["expect"]["ruleId"]
