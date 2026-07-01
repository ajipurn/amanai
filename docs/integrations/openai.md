# Integrate Amanai with the OpenAI / Anthropic tool-call loop

The engine only needs a tool name and an argument dict, so the adapter is pure
duck-typing — **no `openai` or `anthropic` dependency**. Gate each tool-call the
model returns *before* you dispatch it.

```python
from amanai import set_policy
from amanai.adapters.openai import guard_openai_tool_call

set_policy("amanai.policy.json")

resp = client.chat.completions.create(model="...", messages=msgs, tools=tools)
for tc in resp.choices[0].message.tool_calls:
    guard_openai_tool_call(tc)          # raises ToolBlocked / ApprovalRequired in enforce
    result = dispatch(tc)               # your existing tool dispatch
```

Anthropic tool-use blocks work the same way (`tc.name` + `tc.input`):

```python
for block in message.content:
    if block.type == "tool_use":
        guard_openai_tool_call(block)   # duck-typed on .name / .input
        result = run_tool(block.name, block.input)
```

Need executed evidence (with output) for CI? Record it after the tool runs:

```python
from amanai import record_tool_call
record_tool_call(tc.function.name, args, result)
```

`guard_openai_tool_call` **gates**; the trace it produces (plus `record_tool_call`)
feeds `amanai.testing.assert_no_violations` in CI. See
[`examples/adapter_openai.py`](../../examples/adapter_openai.py) for a runnable loop.
