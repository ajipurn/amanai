"""Tests for the OpenAI/Anthropic tool-call adapter (spec 0001). No `openai` or
`anthropic` dependency — provider objects are faked with SimpleNamespace."""

from types import SimpleNamespace

import pytest

from amanai import ToolBlocked, set_mode, set_policy
from amanai.adapters.openai import extract_openai_tool_call, guard_openai_tool_call

POLICY = [
    {
        "id": "discount-cap",
        "tool": "apply_discount",
        "args": [{"arg": "pct", "op": ">=", "value": 50}],
        "action": "block",
        "reason": "too high",
    }
]


def _openai_obj(name, arguments_json):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments_json))


def _anthropic_obj(name, input_dict):
    return SimpleNamespace(name=name, input=input_dict)


# ── extraction ────────────────────────────────────────────────────────────────
def test_extract_openai_object_parses_json_arguments():
    name, args = extract_openai_tool_call(_openai_obj("apply_discount", '{"pct": 90}'))
    assert name == "apply_discount"
    assert args == {"pct": 90}


def test_extract_anthropic_object_uses_input_dict():
    name, args = extract_openai_tool_call(_anthropic_obj("apply_discount", {"pct": 90}))
    assert (name, args) == ("apply_discount", {"pct": 90})


def test_extract_openai_dict_form():
    tc = {"function": {"name": "apply_discount", "arguments": '{"pct": 10}'}}
    assert extract_openai_tool_call(tc) == ("apply_discount", {"pct": 10})


def test_extract_anthropic_dict_form():
    tc = {"name": "apply_discount", "input": {"pct": 10}}
    assert extract_openai_tool_call(tc) == ("apply_discount", {"pct": 10})


def test_extract_empty_arguments_string_is_empty_dict():
    name, args = extract_openai_tool_call(_openai_obj("noop", ""))
    assert (name, args) == ("noop", {})


def test_extract_bad_json_raises_valueerror():
    with pytest.raises(ValueError):
        extract_openai_tool_call(_openai_obj("x", "{not json"))


def test_extract_unrecognized_shape_raises():
    with pytest.raises(ValueError):
        extract_openai_tool_call(SimpleNamespace(foo="bar"))


# ── enforcement ───────────────────────────────────────────────────────────────
def test_guard_blocks_in_enforce_mode():
    set_policy(POLICY)
    set_mode("enforce")
    with pytest.raises(ToolBlocked):
        guard_openai_tool_call(_openai_obj("apply_discount", '{"pct": 90}'))


def test_guard_allows_below_threshold():
    set_policy(POLICY)
    set_mode("enforce")
    decision = guard_openai_tool_call(_openai_obj("apply_discount", '{"pct": 10}'))
    assert decision.outcome == "allow"


def test_guard_shadow_mode_returns_decision_without_raising():
    set_policy(POLICY)
    set_mode("shadow")
    try:
        decision = guard_openai_tool_call(_anthropic_obj("apply_discount", {"pct": 90}))
        assert decision.outcome == "block"
    finally:
        set_mode("enforce")
