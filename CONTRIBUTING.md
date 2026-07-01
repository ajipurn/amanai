# Contributing to Amanai

Thanks for helping build **agent security you can run yourself**. Amanai is
Apache-2.0 and we welcome issues and PRs — new guardrail patterns, detectors,
and SDK improvements.

## Dev setup

```bash
pip install ./packages/sdk-python     # the library (pure-Python, zero deps)
uvx --with pytest pytest              # run the suite
uvx ruff@0.8.4 check .                # lint
```

No services, no Docker — the SDK runs in-process.

## Repo map

- `packages/sdk-python/amanai` — the library: the Action Policy Engine (`policy.py`),
  shared rule operators (`operators.py`), tool-call capture (`@tool` in `client.py`),
  the MCP adapter (`mcp_adapter.py`), guardrails (`guard_input` / `guard_output`),
  offline `judge`, `Monitor` client
- `examples/` — `action_policy_demo`, `quickstart`, `guarded_agent`, `action.policy.json`,
  `amanai.policy.json`
- `tests/` — pure-logic tests (policy engine, tool policy, the test↔enforce loop in
  `test_loop.py`, guardrails, judge, MCP adapter)

## Contributing a detector or guardrail

1. Add the logic to the relevant `amanai` module (`guardrails.py`, `policy.py`, `judge.py`).
2. Op-matching lives in one place — `amanai/operators.py::op_match` — shared by both
   `policy.py` (runtime enforcement) and `judge.py` (offline `tool_assertion`). Change it
   there, not per-caller. `tests/test_loop.py` proves the same rule blocks at runtime and
   flags in the offline detector; this is the core of "what you test is what you enforce".
3. Add a test in `tests/` (assert-based, no framework needed).

## Conventions

- Python: format with `ruff`, keep functions small.
- Keep the dependency surface minimal — the SDK is **zero-dependency**, keep it that way.
- Add a test or a runnable demo for new logic.

## Reporting security issues

Please disclose vulnerabilities in Amanai itself privately (see SECURITY.md) rather
than via public issues.
