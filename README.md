<p align="center">
  <img src="./assets/amanai.svg" alt="Amanai logo" width="180" />
</p>

<h1 align="center">Amanai</h1>

<p align="center">
  <a href="https://pypi.org/project/amanai/">
    <img alt="release version" src="https://img.shields.io/pypi/v/amanai?style=flat-square&label=release&color=f97316&labelColor=3f3f46" />
  </a>
  <a href="./packages/sdk-python/pyproject.toml">
    <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-111827?style=flat-square&logo=python&logoColor=white&labelColor=3f3f46" />
  </a>
  <a href="./LICENSE">
    <img alt="License Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-0ea5e9?style=flat-square&labelColor=3f3f46" />
  </a>
</p>

<p align="center">
  <strong>Policy-as-code for AI agent actions.</strong><br />
  Test policies in CI, enforce them at runtime, and keep evidence for audit.
</p>

AI agents now trigger tools with real side effects: applying discounts, refunding
payments, sending emails, running commands. The risk is no longer only what the
model *says* — it is what the agent *does*.

Amanai is an **Action Policy Engine** for those tool calls. Write **one policy** for
risky actions and use it in two places: the SDK enforces it at runtime, and the same
policy drives CI assertions against recorded agent behavior. Local, deterministic,
**Apache-2.0**, self-hostable, and independent — no server required to start.

```bash
pip install ./packages/sdk-python      # pure-Python, zero deps, no server
```

```python
from amanai import set_policy, tool, ToolBlocked

set_policy([{"id": "discount-cap", "tool": "apply_discount",
             "args": [{"arg": "pct", "op": ">=", "value": 50}], "action": "block"}])

@tool
def apply_discount(pct): ...            # raises ToolBlocked when pct >= 50
```

> **Status:** The SDK is the focus and feature-complete — the same policy drives both
> runtime enforcement and the offline `tool_assertion` detector
> (`examples/action.policy.json`). A self-hostable server and dashboard are
> future work.

## What it does

- **Action policies** — `set_policy` + `@tool` evaluate each call *before* it runs
  and return a decision: `allow`, `block`, `warn`, or `require_approval`. Rules match
  tool names, capabilities, argument predicates, and context (role, tenant, environment).
- **Runtime modes** — `enforce`, `shadow` (observe before blocking), or `test`
  (CI, no side effects).
- **Evidence traces** — every decision becomes a canonical `TraceEvent` (action,
  decision, execution status) for debugging and audit.
- **One-policy loop** — the same file enforces at runtime and asserts expected
  behavior in CI; a contract test keeps both sides aligned.
- **Local guardrails** — `guard_input` blocks prompt injection; `guard_output`
  redacts PII (emails, cards, secrets). No network required.
- **Offline judge & MCP checks** — score inputs, responses, and tool calls against
  detectors; flag poisoned, dangerous, or unvalidated MCP tools.

Full OWASP LLM Top 10 (2025) + Agentic Top 10 (2026) mapping — including what
Amanai deliberately does **not** cover — is in [COVERAGE.md](./COVERAGE.md).

## Quick demo

```bash
PYTHONPATH=packages/sdk-python python examples/action_policy_demo.py
```

An unsafe support agent can apply any discount, refund any amount, and email anyone.
Add one policy file: Amanai blocks the unsafe calls at runtime *and* flags the same
violations in CI from a recorded trace.

## How Amanai compares

|                  | **Amanai**             | MS AGT + RAMPART | Promptfoo | DeepTeam   | Straiker/Noma |
| ---------------- | ---------------------- | ---------------- | --------- | ---------- | ------------- |
| License / owner  | **Apache-2.0, indep.** | MIT, Microsoft   | MIT, OpenAI | Apache-2.0 | Commercial   |
| Red-team testing | Yes (assertions)       | Yes              | Yes       | Yes (attack lib) | Yes       |
| Runtime enforce  | Yes                    | Yes (native)     | No        | No         | Yes          |
| One-policy loop  | Yes                    | Yes              | No        | No         | Yes          |
| Setup weight     | **Library (`pip`); server opt-in** | Heavy (7 pkgs) | Light     | Light      | SaaS          |

Amanai's lane: one independent **library** that does both — test the same policy
in CI and enforce it locally at runtime — with no server required to start.

## When not to use Amanai

- You want the widest attack library out of the box → use **DeepTeam** or **Garak**.
- You want enterprise governance (zero-trust identity, sandboxing, compliance certs)
  → use the **Microsoft Agent Governance Toolkit** or a commercial vendor.
- You want a fully managed SaaS → use **Straiker** or **Noma**.

Use Amanai when you want a simple test-and-guard loop that is self-hostable,
framework-neutral, and independent. Adapters can map framework-specific tool
calls into the core `ActionRequest` schema.

## Instrument your agent (SDK)

Wrap your tools and load a policy. The engine decides, your app enforces, and the
trace gives CI something concrete to assert against:

```python
from amanai import set_policy, tool, collect_trace, ToolBlocked, ApprovalRequired

set_policy("amanai.policy.json")

@tool(name="billing.refund", capability="money_movement", risk="high")
def refund_payment(amount): ...     # ToolBlocked / ApprovalRequired per policy

# in your handler, after running the agent:
return {"reply": text, "amanai_trace": [e.to_dict() for e in collect_trace()]}
```

See `examples/action_policy_demo.py` for a full agent running under policy, and
`amanai.testing` (`assert_blocked`, `assert_no_violations`, `replay`) for the CI
side.

## Runtime guardrails (supporting)

The SDK includes **inline guardrails** that run locally inside your agent. Block
prompt injection on input and redact PII on output:

```python
from amanai import guard_input, guard_output, GuardrailBlocked

try:
    msg = guard_input(user_msg)          # raises on injection
except GuardrailBlocked:
    return "I can't help with that request."
reply = guard_output(model_reply)        # redacts emails, cards, secrets
```

See `examples/guarded_agent.py` for a complete guarded-agent example.

## Production monitoring (optional — needs a server)

The SDK includes a `Monitor` client for sending live traces to an Amanai server.
The server is a planned self-hosted component; the client already ships in the SDK:

```python
from amanai import Monitor, collect_trace

mon = Monitor("http://localhost:8000", PUBLIC_KEY, SECRET_KEY)
mon.log_trace(collect_trace(), user_id="u123")   # canonical events, PII redacted
```

## Continuous integration

Run the suite in CI to gate policies and guardrails. `tests/test_loop.py` and
`tests/test_action_policy.py` prove that one rule can be tested and enforced
through the same loop. See
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) (ruff + pytest on every PR).

## Stack

Pure-Python, **zero dependencies**. Build and test with
[uv](https://docs.astral.sh/uv/); lint with `ruff`. Apache-2.0.

## Install

```bash
pip install amanai                    # from PyPI
pip install ./packages/sdk-python     # from a local checkout
uvx --with pytest pytest              # run the test suite (zero infra)
```

## Local development

```bash
uvx ruff@0.8.4 check .          # lint
uvx --with pytest pytest        # tests (pure logic, zero infra)
pre-commit install              # optional: ruff on every commit
```

## Repository layout

```
amanai/
├── packages/sdk-python/      # amanai — the library
│   └── amanai/               # policy engine · operators · @tool client · MCP adapter · testing · guardrails · judge · monitor
├── examples/                 # action_policy_demo · action.policy.json · quickstart · guarded_agent
├── tests/                    # pure-logic tests (engine, tool policy, loop, guardrails, judge)
└── pyproject.toml            # ruff + pytest config
```

## Contributing & license

Contributions are welcome: new policy operators, guardrail patterns, and SDK
improvements are all useful. See [CONTRIBUTING.md](./CONTRIBUTING.md). Found a
vulnerability in Amanai itself? See [SECURITY.md](./SECURITY.md). Licensed under
[Apache-2.0](./LICENSE).
