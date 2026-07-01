# Integrate Amanai with CrewAI

Wrap your CrewAI tools — a blocked call raises before the tool body runs. `crewai`
is imported lazily; the Amanai SDK stays zero-dependency.

```python
from amanai import set_policy
from amanai.adapters.crewai import guard_crewai_tool

set_policy("amanai.policy.json")

agent = Agent(
    role="support",
    tools=[guard_crewai_tool(t) for t in tools],
    ...
)
```

The wrapper gates the tool's `_run`, so any call the policy blocks raises
`ToolBlocked` and never executes. Pass `capability=` / `context=` to
`guard_crewai_tool` if your policy matches on those.
