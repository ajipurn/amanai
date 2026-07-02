"""Canonical map: what this SDK covers in the OWASP frameworks.

Single source of truth for both `COVERAGE.md` and `tests/test_coverage.py`.
Honest by design — every framework ID is either in `CAPABILITIES` (the SDK does
something about it now) or in `NOT_COVERED` (out of scope, or planned for the
server). `tests/test_coverage.py` fails if any ID is left unaccounted for, so the
SDK can never silently over-claim.

`status` values:
  enforce  — runtime control that blocks/sanitizes in-process
  partial  — heuristic / known-pattern only (not robust)
  test     — offline assertion or static check; finds, does not block
"""

# --- Official frameworks (for validation + the docs) -------------------------

LLM_TOP10_2025 = {
    "LLM01": "Prompt Injection",
    "LLM02": "Sensitive Information Disclosure",
    "LLM03": "Supply Chain",
    "LLM04": "Data and Model Poisoning",
    "LLM05": "Improper Output Handling",
    "LLM06": "Excessive Agency",
    "LLM07": "System Prompt Leakage",
    "LLM08": "Vector and Embedding Weaknesses",
    "LLM09": "Misinformation",
    "LLM10": "Unbounded Consumption",
}

ASI_TOP10_2026 = {
    "ASI01": "Agent Goal Hijack",
    "ASI02": "Tool Misuse & Exploitation",
    "ASI03": "Agent Identity & Privilege Abuse",
    "ASI04": "Agentic Supply Chain Compromise",
    "ASI05": "Unexpected Code Execution",
    "ASI06": "Memory & Context Poisoning",
    "ASI07": "Insecure Inter-Agent Communication",
    "ASI08": "Cascading Agent Failures",
    "ASI09": "Human-Agent Trust Exploitation",
    "ASI10": "Rogue Agents",
}

# --- What the SDK does now ----------------------------------------------------

CAPABILITIES = {
    "guard_input": {
        "owasp": ["LLM01", "LLM07"],
        "asi": ["ASI01"],
        "status": "partial",
        "how": "blocks known prompt-injection / system-prompt-exfil markers on "
        "inputs (English substring + regex; not ML)",
    },
    "guard_output": {
        "owasp": ["LLM02"],
        "asi": [],
        "status": "partial",
        "how": "redacts PII/secrets on outputs (email, phone, card+Luhn, api-key)",
    },
    "tool_policy": {
        "owasp": ["LLM06"],
        "asi": ["ASI02", "ASI03", "ASI09"],
        "status": "enforce",
        "how": "Action Policy Engine: evaluates each tool-call against a policy "
        "(tool/capability/arg/context rules) and enforces allow/block/warn/"
        "require_approval before execution. Includes an `internal_url` arg op "
        "that blocks SSRF to private/loopback/link-local/reserved and cloud-"
        "metadata addresses (literal-IP + known-host; no DNS resolution). "
        "ASI09: enforces the human-approval gate — parks the action and "
        "`approve_action` grants one-shot execution; the inbox/UI is the caller's",
    },
    "tool_assertion": {
        "owasp": ["LLM06"],
        "asi": ["ASI02"],
        "status": "test",
        "how": "offline assertion sharing the engine's operators: did a captured "
        "tool-call violate the same rule the runtime enforces",
    },
    "mcp.tool_poisoning": {
        "owasp": ["LLM01"],
        "asi": ["ASI07"],
        "status": "test",
        "how": "static scan of MCP tool descriptions for injected instructions",
    },
    "mcp.dangerous_capability": {
        "owasp": ["LLM06"],
        "asi": ["ASI02", "ASI05"],
        "status": "test",
        "how": "static scan for high-privilege / exec-capable MCP tools",
    },
    "mcp.missing_schema": {
        "owasp": ["LLM05"],
        "asi": ["ASI02"],
        "status": "test",
        "how": "flags MCP tools without input schemas (unvalidated args)",
    },
}

# --- What the SDK deliberately does NOT cover (and where to look) -------------

NOT_COVERED = {
    "LLM03": "software composition analysis / SBOM (e.g. Snyk, Dependabot)",
    "LLM04": "ML training pipeline & data governance (MLOps)",
    "LLM08": "your RAG / vector-store hardening",
    "LLM09": "groundedness eval (needs a judge model + sources)",
    "LLM10": "gateway rate & cost limits — Amanai server (planned)",
    "ASI04": "software composition analysis / SBOM",
    "ASI06": "agent memory-store validation — Amanai server (planned)",
    "ASI08": "orchestration circuit-breakers — Amanai server (planned)",
    "ASI10": "agent identity + behavior monitoring — Amanai server (planned)",
}

# Convenience alias — the public, machine-readable coverage map.
COVERAGE = CAPABILITIES


def _capability_key(detector: dict) -> str | None:
    """Map a judge detector / MCP check dict to a CAPABILITIES key."""
    check = detector.get("check")
    if check:
        return f"mcp.{check}"
    return {"tool_assertion": "tool_assertion"}.get(detector.get("type"))


def coverage_for(detector: dict) -> dict:
    """OWASP/ASI IDs a judge detector maps to.

    Generic detectors (string_match / llm_judge) depend on the rubric, so they
    carry no fixed ID and return empty lists.
    """
    cap = CAPABILITIES.get(_capability_key(detector), {})
    return {"owasp": list(cap.get("owasp", [])), "asi": list(cap.get("asi", []))}


def covered_ids() -> set[str]:
    ids: set[str] = set()
    for cap in CAPABILITIES.values():
        ids.update(cap["owasp"])
        ids.update(cap["asi"])
    return ids
