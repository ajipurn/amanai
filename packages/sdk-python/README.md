# amanai

**Action Policy Engine for AI agents — policy-as-code for tool-calls. Pure-Python, zero dependencies.**

Write **one policy** for risky agent actions. Amanai evaluates every tool-call
against it before the tool runs, enforces the decision, and records a structured
trace as evidence. The same policy file asserts in CI — what you test is what you
enforce. Decisions are deterministic: no LLM decides whether a high-risk tool runs.

```bash
pip install amanai
```

## Action Policy Engine

Five verbs: **load** a policy, **evaluate** an action, **protect** a tool,
**collect** a trace, **assert** it in tests.

```python
from amanai import set_policy, tool, ToolBlocked, ApprovalRequired, collect_trace

set_policy("amanai.policy.json")          # load + validate (raises PolicyError if bad)

@tool(name="billing.refund", capability="money_movement", risk="high")
def refund_payment(amount): ...

refund_payment(amount=500)                # ToolBlocked / ApprovalRequired per policy
trace = collect_trace()                   # canonical evidence: action + decision + status
```

A **policy** is a list of rules. A rule matches on `tool` and/or `capability`,
with optional `args` and `context` predicates, and carries an `action`:

```json
[
  { "id": "discount-cap", "tool": "apply_discount",
    "args": [{ "arg": "pct", "op": ">=", "value": 50 }],
    "action": "block", "reason": "discount of 50% or more is never allowed" },

  { "id": "refund-approval", "tool": "refund_payment",
    "args": [{ "arg": "amount", "op": ">", "value": 100 }],
    "action": "require_approval" },

  { "id": "external-email", "capability": "external_comms",
    "args": [{ "arg": "to", "op": "email_external", "value": ["acme.com"] }],
    "action": "block" }
]
```

- **Outcomes:** `allow` · `block` · `warn` · `require_approval`.
- **Operators:** `>= > <= < == !=` · `contains` · `regex` · `in` / `not_in` ·
  `email_external` · `domain_in` / `domain_not_in`.
- **Modes** (per request, never global): `enforce` blocks before execution ·
  `shadow` records what it *would* block but lets the call run · `test`
  evaluates with no side effects.
- The legacy flat rule `{tool, arg, op, value}` still loads (it defaults to
  `block`). Rules without an `id` get a deterministic generated one.

```python
from amanai import set_mode, set_context, evaluate, ActionRequest

set_mode("shadow")                                   # observe before enforcing
set_context(role="support", tenant="t1", environment="prod")  # authz context for rules
evaluate(ActionRequest("apply_discount", {"pct": 90}))        # -> PolicyDecision(outcome="block", ...)
```

## Assert the same policy in CI

```python
from amanai.testing import assert_blocked, assert_no_violations

def test_excessive_discount_is_blocked():
    set_policy("amanai.policy.json")
    assert_blocked(apply_discount, pct=90)

def test_attack_trace_is_clean():
    run_agent(attack_prompt)             # produces a trace
    assert_no_violations(collect_trace())  # replays actions against the active policy
```

`amanai.testing` also ships `assert_requires_approval`,
`using_mode`, and `replay` (re-evaluate a recorded trace against a policy).

## Runtime guardrails (input / output, supporting)

```python
from amanai import guard_input, guard_output, GuardrailBlocked

try:
    msg = guard_input(user_msg)          # raises GuardrailBlocked on injection
except GuardrailBlocked:
    reply = "I can't help with that."
else:
    reply = guard_output(run_agent(msg)) # redacts emails, cards, secrets
```

## Offline judge & MCP checks (supporting)

Score an agent's input / response / tool-calls against detectors (string match,
tool assertions, MCP checks; LLM-as-judge when you pass a gateway). The
`tool_assertion` detector reuses the engine's operators, so the test side can't
drift from runtime — a contract test guarantees it.

## Monitoring (optional — needs an Amanai server)

```python
from amanai import Monitor, collect_trace

mon = Monitor("http://localhost:8000", PUBLIC_KEY, SECRET_KEY)
mon.log_trace(collect_trace(), user_id="u123")   # canonical events, PII redacted
```

## API

- **Engine:** `load_policy` `set_policy` `get_policy` `evaluate` `Policy` `Rule`
  `ActionRequest` `PolicyDecision` `TraceEvent` `PendingAction` `PolicyError`
- **Modes / context:** `set_mode` `get_mode` `set_context` `get_context` `clear_context`
- **Protect / collect:** `tool` `collect_trace` `collect_tool_calls` `record_tool_call`
  `reset` `registered_tools` `uncovered_tools` `ToolBlocked` `ApprovalRequired`
- **Test:** `amanai.testing` — `assert_blocked`
  `assert_requires_approval` `assert_no_violations` `using_mode` `replay`
- **Policy lifecycle:** `clear_tool_policy` (deactivate the active policy)
- **Guardrails:** `guard_input` `guard_output` `redact_pii` `detect_injection` `detect_pii` `GuardResult` `GuardrailBlocked`
- **Judge / monitor:** `judge` `Monitor`

Apache-2.0. Zero runtime dependencies.
