# Security Policy

Amanai is a security tool. This policy covers vulnerabilities **in Amanai itself**
(the SDK in this repo), not findings Amanai reports about your own agents.

## Supported versions

Pre-1.0 and ships from `main`. Security fixes land on `main` and the latest
tagged release. Pin a release tag for production use.

## Reporting a vulnerability

Please report privately — do **not** open a public issue:

- Use GitHub's **private vulnerability reporting** (Security → Report a vulnerability), or
- Email `security@amanai.dev` (replace with your project's address).

Include: affected module (e.g. `policy`, `operators`, `guardrails`, `mcp_adapter`,
`judge`, `monitor`), version or commit, reproduction steps, and impact. A
proof-of-concept helps.

We aim to acknowledge within **3 business days** and to share a remediation
timeline after triage. We'll credit reporters who want it once a fix ships.

## Scope

Amanai today is a pure-Python, zero-dependency SDK — there is no hosted API,
worker, CLI, or web service in this repo. If any is added later, this policy's
scope will expand to cover it.

In scope (vulnerabilities in the SDK):

- A policy rule that should `block` / `require_approval` but silently `allow`s —
  operator logic in `amanai/operators.py`, rule matching in `amanai/policy.py`.
- A way to bypass `@tool` enforcement in `enforce` mode (`amanai/client.py`).
- `guard_mcp_call` failing to gate a live MCP tool-call per the active policy
  (`amanai/mcp_adapter.py`).
- Secrets or PII leaking through `Monitor.log_trace` despite `redact=True`
  (`amanai/monitor.py`).
- Supply-chain issues in the SDK's own build/publish pipeline (it ships zero
  runtime dependencies by design — see [CONTRIBUTING.md](./CONTRIBUTING.md)).

Out of scope:

- Vulnerabilities Amanai *detects in your agents* — that's the product working.
- Gaps already declared as `partial` or `NOT_COVERED` in
  [COVERAGE.md](./COVERAGE.md) (e.g. `guard_input`/`guard_output` heuristics,
  LLM03/04/08/09/10, ASI04/06/08/10) — those are documented limitations, not
  silent failures. A bypass of a claimed `enforce` capability is in scope; a gap
  the SDK already admits to is not a new finding.
- The example agents under `examples/` — they exist to demonstrate the policy
  engine, not as hardened services.

## Operational notes

- **Local by default.** The Action Policy Engine and guardrails run in-process
  with no network call. `Monitor` is the one opt-in exception — it posts trace
  events over HTTP(S) to an endpoint and key pair you configure.
- **No credential store in this SDK.** There is no encryption-at-rest here;
  `Monitor` sends whatever public/secret key pair you give it as HTTP basic auth
  to the endpoint you configure. Treat that endpoint and key like any other
  secret in your own infrastructure.
- **Supply-chain hygiene.** The SDK has zero runtime dependencies by design; if
  you fork it, keep it that way, and use hash-locked installs for your own dev
  tooling.
