# Security coverage

What the Amanai SDK actually covers in the **OWASP LLM Top 10 (2025)** and the
**OWASP Top 10 for Agentic Applications (ASI, 2026)** — and, just as importantly,
what it does **not**.

This is generated from the machine-readable source of truth,
[`amanai/coverage.py`](./packages/sdk-python/amanai/coverage.py).
`tests/test_coverage.py` fails the build if the two drift or if any framework ID
is left unaccounted for — so this SDK can't silently over-claim.

**Legend** — ✅ **enforce** (runtime control, blocks/sanitizes in-process) ·
🟡 **partial / test** (heuristic, known-pattern, or find-only — does not block) ·
❌ **not covered** (out of scope for a library — use the tool noted, or planned
for the Amanai server).

## OWASP LLM Top 10 (2025)

| ID | Risk | Status | How / where |
| --- | --- | --- | --- |
| LLM01 | Prompt Injection | 🟡 partial | `guard_input` — known markers + regex (English substring; not ML) |
| LLM02 | Sensitive Information Disclosure | 🟡 partial | `guard_output` — redact PII (email, phone, card+Luhn, api-key) |
| LLM03 | Supply Chain | ❌ | SCA / SBOM (Snyk, Dependabot) |
| LLM04 | Data and Model Poisoning | ❌ | ML training pipeline & data governance (MLOps) |
| LLM05 | Improper Output Handling | 🟡 test | MCP `missing_schema` (unvalidated args) |
| LLM06 | Excessive Agency | ✅ enforce | **Action Policy Engine** — evaluate every tool-call, enforce `allow`/`block`/`warn`/`require_approval`; same policy asserted in CI via `tool_assertion` |
| LLM07 | System Prompt Leakage | 🟡 partial | `guard_input` flags exfil attempts (output-side redaction planned) |
| LLM08 | Vector and Embedding Weaknesses | ❌ | your RAG / vector-store hardening |
| LLM09 | Misinformation | ❌ | groundedness eval (judge model + sources) |
| LLM10 | Unbounded Consumption | ❌ | gateway rate & cost limits — Amanai server (planned) |

## OWASP Top 10 for Agentic Applications (ASI, 2026)

| ID | Risk | Status | How / where |
| --- | --- | --- | --- |
| ASI01 | Agent Goal Hijack | 🟡 partial | `guard_input` injection markers |
| ASI02 | Tool Misuse & Exploitation | ✅ enforce | **Action Policy Engine** (tool/capability/arg/context rules), incl. `internal_url` SSRF block (private/loopback/link-local/reserved + cloud-metadata IPs; literal-IP + known-host, no DNS) + `tool_assertion` + MCP `dangerous_capability` |
| ASI03 | Agent Identity & Privilege Abuse | ✅ enforce | context-aware rules (role / tenant / env) + arg-level blocks (e.g. `email_external`); full identity → server |
| ASI04 | Agentic Supply Chain Compromise | ❌ | SCA / SBOM |
| ASI05 | Unexpected Code Execution | 🟡 test | MCP `dangerous_capability` (exec/shell keywords); sandbox → server |
| ASI06 | Memory & Context Poisoning | ❌ | agent memory-store validation — Amanai server (planned) |
| ASI07 | Insecure Inter-Agent Communication | 🟡 test | MCP `tool_poisoning` (poisoned descriptions); channel security → server |
| ASI08 | Cascading Agent Failures | ❌ | orchestration circuit-breakers — Amanai server (planned) |
| ASI09 | Human-Agent Trust Exploitation | ✅ enforce | **Action Policy Engine** — `require_approval` gate parks high-risk actions; `approve_action` grants one-shot execution (inbox/UI is the caller's) |
| ASI10 | Rogue Agents | ❌ | agent identity + behavior monitoring — Amanai server (planned) |

## In one line

Amanai's SDK is an **Action Policy Engine** for the input / output / tool-call
boundary — strongest on **LLM06 / ASI02 / ASI03 / ASI09 (excessive agency, tool
misuse, privilege abuse, human-approval gating)**, plus partial
prompt-injection, PII, and a few static MCP checks. Orchestration-level risks
(memory, inter-agent, cascading, rogue agents, rate limits) are the **Amanai
server's** job and are planned, not shipped. Supply-chain, model-poisoning, and
vector risks are **not a guardrail library's job** — use the noted tools.
