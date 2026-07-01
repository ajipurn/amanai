# Integrate Amanai with LangChain

Wrap the tools you hand the agent — a blocked call raises before the tool body
runs. `langchain-core` is imported lazily; the Amanai SDK itself stays
zero-dependency.

```python
from amanai import set_policy
from amanai.adapters.langchain import guard_langchain_tool

set_policy("amanai.policy.json")
tools = [guard_langchain_tool(t) for t in tools]     # then pass these to your agent
```

`guard_langchain_tool` preserves `.name` / `.description` / `.args_schema`, so the
agent still introspects the tool normally. Both the sync `_run` and async `_arun`
(if present) are gated.

Observe-only (shadow) — record a trace without blocking, no tool wrapping:

```python
from amanai import set_mode
from amanai.adapters.langchain import AmanaiCallbackHandler

set_mode("shadow")
agent_executor.invoke(inputs, config={"callbacks": [AmanaiCallbackHandler()]})
```

Enforce with the wrapper; observe with the callback.
