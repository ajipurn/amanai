"""Guard an OpenAI-style tool-call loop with Amanai — no `openai` dependency.

The model returns tool-calls; we gate each one with the policy before dispatching
it. A blocked call raises `ToolBlocked` and never runs. Fake the provider objects
with SimpleNamespace so the example runs anywhere.

    PYTHONPATH=packages/sdk-python python examples/adapter_openai.py
"""

from types import SimpleNamespace

from amanai import ToolBlocked, collect_trace, set_policy
from amanai.adapters.openai import guard_openai_tool_call


def _tool_call(name, arguments_json):
    """Stand-in for an OpenAI `message.tool_calls[i]` object."""
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments_json))


def dispatch(name, args):
    """Your real tool dispatch would run here."""
    return f"ran {name}({args})"


def main():
    set_policy(
        [
            {
                "id": "discount-cap",
                "tool": "apply_discount",
                "args": [{"arg": "pct", "op": ">=", "value": 50}],
                "action": "block",
                "reason": "discount of 50% or more is never allowed",
            }
        ]
    )

    # What the model "returned" this turn.
    model_tool_calls = [
        _tool_call("apply_discount", '{"pct": 10}'),  # allowed
        _tool_call("apply_discount", '{"pct": 90}'),  # blocked by policy
    ]

    for tc in model_tool_calls:
        name = tc.function.name
        try:
            guard_openai_tool_call(tc)  # raises in enforce mode
        except ToolBlocked as e:
            print(f"BLOCKED {name}: {e}")
            continue
        import json

        args = json.loads(tc.function.arguments)
        print(f"OK      {name}: {dispatch(name, args)}")

    print("\ntrace (evidence for CI / audit):")
    for event in collect_trace():
        print(" ", event.to_dict())


if __name__ == "__main__":
    main()
