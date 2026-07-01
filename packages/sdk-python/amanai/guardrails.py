"""Runtime guardrails (Phase 2) — inline, local, no network.

Privacy-first: detection runs in your process; nothing is sent anywhere. Use it to
block prompt injection on inputs and redact PII on outputs.

    from amanai import guard_input, guard_output, GuardrailBlocked

    try:
        user_msg = guard_input(user_msg)          # raises on injection
    except GuardrailBlocked:
        return "I can't help with that request."
    reply = guard_output(model_reply)             # redacts PII/secrets
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from amanai.coverage import CAPABILITIES

_INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous",
    "ignore the above",
    "disregard previous",
    "disregard all",
    "forget your instructions",
    "you are now",
    "developer mode",
    "do anything now",
    "dan mode",
    "reveal your system prompt",
    "reveal your prompt",
    "print your system prompt",
    "override your instructions",
    "new instructions:",
    "you are going to act as",
    "uncensored",
    "disregard the system prompt",
    "repeat the words above",
    "print everything above",
]

_PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "api_key": re.compile(r"\b(?:sk|pk)[-_][A-Za-z0-9]{16,}\b"),
}


class GuardrailBlocked(Exception):
    """Raised by guard_input when an injection attempt is blocked."""


@dataclass
class GuardResult:
    flagged: bool
    categories: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    redacted: str = ""


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13:
        return False
    total, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_injection(text: str) -> list[str]:
    low = (text or "").lower()
    hits = [m for m in _INJECTION_MARKERS if m in low]
    # ponytail: bounded {0,3} words - no ReDoS, catches the/prior/any/those variants
    if re.search(r"ignore\s+(\w+\s+){0,3}instructions", low):
        hits.append("ignore-instructions (regex)")
    return hits


def detect_pii(text: str) -> list[dict]:
    found: list[dict] = []
    for kind, pat in _PII_PATTERNS.items():
        for m in pat.finditer(text or ""):
            value = m.group(0)
            if kind == "credit_card" and not _luhn_ok(value):
                continue
            found.append({"type": kind, "value": value, "owasp": ["LLM02"]})
    return found


def redact_pii(text: str) -> str:
    out = text or ""
    for kind, pat in _PII_PATTERNS.items():

        def _sub(m: re.Match) -> str:
            if kind == "credit_card" and not _luhn_ok(m.group(0)):
                return m.group(0)
            return f"[REDACTED:{kind}]"

        out = pat.sub(_sub, out)
    return out


def scan(text: str) -> GuardResult:
    injection = detect_injection(text)
    pii = detect_pii(text)
    categories = []
    if injection:
        categories.append("prompt_injection")
    if pii:
        categories.append("pii")
    inj = CAPABILITIES["guard_input"]
    findings = [
        {"type": "prompt_injection", "marker": m, "owasp": inj["owasp"], "asi": inj["asi"]}
        for m in injection
    ] + pii
    return GuardResult(
        flagged=bool(categories),
        categories=categories,
        findings=findings,
        redacted=redact_pii(text),
    )


def guard_input(text: str, *, block: bool = True) -> str:
    """Check an incoming message. Raises GuardrailBlocked on injection (if block)."""
    if detect_injection(text) and block:
        raise GuardrailBlocked("prompt injection detected")
    return text


def guard_output(text: str, *, redact: bool = True) -> str:
    """Sanitize an outgoing message — redacts PII/secrets by default."""
    return redact_pii(text) if redact else text
