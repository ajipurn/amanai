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
policy drives CI assertions against recorded agent behavior. Local-first, deterministic,
**Apache-2.0**, and independent — runs entirely in your process, no server required.

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
> (`examples/action.policy.json`). A server and dashboard are being built as a
> separate product; the SDK stands alone and will stay Apache-2.0.

Building in TypeScript? A zero-dependency [TypeScript SDK](packages/sdk-node)
(`npm install @amanai/sdk`) ports the core engine — it loads the **same policy JSON** and
returns the **same decisions**, verified by shared parity vectors run in both
languages' CI.

## What it does

- **Action policies** — `set_policy` + `@tool` evaluate each call *before* it runs
  and return a decision: `allow`, `block`, `warn`, or `require_approval`. Rules match
  tool names, capabilities, argument predicates, and context (role, tenant, environment).
- **Runtime modes** — `enforce`, `shadow` (observe before blocking), or `test`
  (CI, no side effects).
- **Evidence traces** — every decision becomes a canonical `TraceEvent` (action,
  decision, execution status), stamped with a unique event id, a UTC timestamp,
  and the digest of the policy version that decided it — for debugging and audit.
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

Use Amanai when you want a simple test-and-guard loop that is local-first,
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

### Approvals (human-in-the-loop)

A `require_approval` rule parks the action instead of running it; `approve_action`
grants **exactly one** execution — an identical call afterwards needs approval
again. The inbox/UI is yours; the SDK owns the protocol:

```python
from amanai import approve_action, ApprovalRequired

try:
    refund_payment(amount=5000)
except ApprovalRequired as e:
    token = e.pending.token           # park it: queue, Slack, a human
approve_action(token)                 # grant one execution
refund_payment(amount=5000)           # runs; trace records status="approved"
```

Tokens are deterministic and identical across the Python and TypeScript SDKs for
the same action, so a grant can be issued from either side.

## Integrate with your framework

Already built on OpenAI, LangChain, or CrewAI? Don't rewrite each tool — the engine
only needs a tool name and an argument dict, so an adapter funnels the framework's
tool-calls straight in. Frameworks are imported lazily; the SDK stays zero-dependency.

```python
from amanai import set_policy
from amanai.adapters.openai import guard_openai_tool_call   # OpenAI / Anthropic loop

set_policy("amanai.policy.json")
for tc in response.choices[0].message.tool_calls:
    guard_openai_tool_call(tc)      # raises ToolBlocked / ApprovalRequired in enforce
    result = dispatch(tc)
```

Recipes: [OpenAI / Anthropic](docs/integrations/openai.md) ·
[LangChain](docs/integrations/langchain.md) · [CrewAI](docs/integrations/crewai.md).
`guard_tool_call(name, args)` is the framework-neutral funnel underneath them all
(and `guard_mcp_call` is its MCP-shaped alias).

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

## Red-team regression pack

A curated, static attack corpus (prompt injection, jailbreak, system-prompt leak,
PII exfil, tool abuse) plus benign controls, with a dependency-free runner. Use it
to prove the guardrails still catch what they claim, or point it at your own agent:

```python
from amanai import load_pack, run_pack

report = run_pack(load_pack())            # against the built-in guardrails
assert report.passed                      # fails if a guardrail regressed

report = run_pack(load_pack("tool_abuse"), target=my_agent)   # end-to-end
```

Or from CI: `amanai redteam` (exit non-zero on any regression;
`--target module:fn` runs the end-to-end tool-abuse cases against your agent).

This is a **regression harness with a starter corpus**, not an exhaustive attack
library — for breadth (adaptive/generative attacks) use **DeepTeam** or **Garak**.

## Production monitoring (optional — needs a server)

The SDK includes a `Monitor` client for sending live traces to an Amanai server.
The server is a separate product in development; the client already ships in the
SDK, so instrumented apps won't need code changes when it lands:

```python
from amanai import Monitor, collect_trace

mon = Monitor("http://localhost:8000", PUBLIC_KEY, SECRET_KEY)
mon.log_trace(collect_trace(), user_id="u123")   # canonical events, PII redacted
```

## Lint your policy

`load_policy` validates a policy's *structure*; `lint_policy` catches *semantic*
bugs that first-match-wins hides — an unreachable rule, two rules that conflict,
dead duplicates, or a tool no rule covers:

```python
from amanai import lint_policy

for f in lint_policy("amanai.policy.json"):
    print(f.severity, f.code, f.rule_ids, f.message)
```

Findings carry a `severity` (`error` / `warn` / `info`) and a `code`
(`unreachable-rule`, `conflicting-rules`, `redundant-rule`, `missing-reason`,
`uncovered-tool`). It is conservative on `unreachable-rule`: an `error` only when
an earlier rule *provably* matches a superset of the later rule (a false "delete
this" is worse than a miss); broader numeric-range subsumption is reported at
`info`. Pass `tools=registered_tools()` to also flag protected tools no rule covers.

## Command line

The `amanai` command wraps the engine for the terminal and CI — no Python file
needed. Exit codes: `0` clean, `1` findings/violations, `2` usage error.

```bash
amanai validate  amanai.policy.json                 # structural check (load_policy)
amanai lint      amanai.policy.json --strict        # semantic check (unreachable/conflicting rules)
amanai test      amanai.policy.json trace.json      # assert a recorded trace against the policy
amanai check-mcp tools.json                         # static checks on MCP tool definitions
amanai explain   amanai.policy.json --tool apply_discount --arg pct=90   # dry-run one action
```

Add `--json` to any subcommand for machine-readable output. Gate a policy in CI
with two lines and no test file:

```yaml
- run: amanai lint amanai.policy.json --strict
- run: amanai test amanai.policy.json trace.json
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
