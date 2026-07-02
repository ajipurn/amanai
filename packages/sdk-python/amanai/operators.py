"""Operator match logic — the single source of truth for rule predicates.

Runtime enforcement (`policy.py`) and the offline judge (`judge.py`) both call
`op_match` here, so "what you test" and "what you enforce" can never drift —
there is one implementation, not two to keep in sync.

A predicate is *true* when the action's value satisfies the operator against the
rule's target. A true predicate means the rule applies (its action fires).
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

# Every operator the policy DSL understands. Loading a rule with an op outside
# this set fails fast (see `policy.load_policy`).
KNOWN_OPERATORS = frozenset(
    {
        ">=",
        ">",
        "<=",
        "<",
        "==",
        "eq",
        "!=",
        "ne",
        "contains",
        "regex",
        "in",
        "membership",
        "not_in",
        "email_external",
        "domain_in",
        "domain_not_in",
        "internal_url",
    }
)


def _domain(value) -> str:
    return str(value).split("@")[-1].lower()


def _domains(target) -> list[str]:
    return [str(d).lower() for d in (target or [])]


# Hostnames that are internal but aren't literal IPs, so `ipaddress` can't flag
# them. `localhost` resolves to loopback; `metadata.google.internal` is the GCP
# metadata endpoint (AWS/Azure use 169.254.169.254, caught as link-local).
_INTERNAL_HOSTS = frozenset({"localhost", "metadata.google.internal"})


def _is_internal_url(value) -> bool:
    """True if `value` (a URL or bare host) points somewhere internal: a private,
    loopback, link-local, reserved, or unspecified IP, or a known-internal host.

    ponytail: no DNS resolution. Catches literal-IP and known-hostname SSRF only,
    not DNS-rebinding (a public hostname that resolves to an internal IP at
    request time). Resolving needs network + is TOCTOU-prone — out of scope for a
    deterministic in-process check. Same posture as the regex-ReDoS note below.
    """
    # urlsplit needs a scheme to populate .hostname; fall back to the raw string
    # for a bare host like "10.0.0.1" or "localhost".
    host = urlsplit(str(value)).hostname or str(value).strip()
    host = host.strip().rstrip(".").lower()  # drop FQDN root dot
    if not host:
        return False
    if host in _INTERNAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a hostname we don't resolve — treat as external
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
    )


# Canonical numeric grammar, shared with the TypeScript engine (operators.ts
# `pyFloat`). A security decision must coerce numbers identically in both SDKs, so
# we do NOT defer to each language's native parser: Python `float()` accepts "9_0"
# while JS `Number()` rejects it, and JS accepts "0x1f" while Python rejects it —
# that drift flips block/allow across languages. One strict grammar removes it:
# optional sign, decimal or scientific notation, plus inf/infinity/nan
# (case-insensitive). No underscores, no hex/binary/octal.
_NUM_RE = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _to_number(x) -> float:
    """Coerce to float under the canonical grammar, else raise ValueError. bool
    coerces (True → 1.0), matching Python's own numeric `==` semantics."""
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        t = x.strip()
        low = t.lower().lstrip("+-")
        if low in ("inf", "infinity"):
            return float("-inf") if t.lstrip().startswith("-") else float("inf")
        if low == "nan":
            return float("nan")
        if _NUM_RE.match(t):
            return float(t)
    raise ValueError(f"not a canonical number: {x!r}")


def op_match(op: str, value, target) -> bool:
    """True when `value` satisfies `op` against `target`.

    Returns False for unknown operators or type errors (never raises) so a
    malformed value can't crash a security decision.
    """
    try:
        if op in (">=", ">", "<=", "<"):
            x, y = _to_number(value), _to_number(target)
            return {">=": x >= y, ">": x > y, "<=": x <= y, "<": x < y}[op]
        if op in ("==", "eq"):
            # Numeric-first so "5" == 5. Note: bool coerces (True == 1), matching
            # Python's own semantics; use a string value to compare literally.
            try:
                return _to_number(value) == _to_number(target)
            except (TypeError, ValueError):
                return value == target
        if op in ("!=", "ne"):
            try:
                return _to_number(value) != _to_number(target)
            except (TypeError, ValueError):
                return value != target
        if op == "contains":
            return str(target).lower() in str(value).lower()
        if op == "regex":
            # ponytail: policy-supplied regex, no ReDoS guard. Fine while policy
            # authorship is trusted; add a re2/timeout wrapper if policies ever
            # come from untrusted input.
            return re.search(str(target), str(value)) is not None
        if op in ("in", "membership"):
            return value in (target or [])
        if op == "not_in":
            return value not in (target or [])
        if op == "email_external":
            return _domain(value) not in _domains(target)
        if op == "domain_in":
            return _domain(value) in _domains(target)
        if op == "domain_not_in":
            return _domain(value) not in _domains(target)
        if op == "internal_url":
            # target is the rule's `value`: true = fire on internal, false on
            # external. Any parse error falls through to the except → False.
            return _is_internal_url(value) == bool(target)
    except Exception:
        return False
    return False
