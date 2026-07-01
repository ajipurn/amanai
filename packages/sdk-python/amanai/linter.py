"""Semantic policy linter — catch bugs `load_policy` can't see.

`load_policy` validates *structure* (types, known operators, duplicate ids, that a
rule matches on a tool or capability). It does not catch policies that are
structurally valid but semantically wrong under first-match-wins:

  * a broad rule before a narrow one makes the narrow rule *unreachable*,
  * two rules with the same match but different actions are order-dependent,
  * duplicate predicate sets are dead weight,
  * `block`/`require_approval` rules with no reason weaken the audit trail,
  * registered tools no rule covers are silently unprotected.

`lint_policy` returns `Finding`s. The bias is deliberate: only report a rule
unreachable (`error`) when an earlier rule *provably* matches a superset of its
actions (exact predicate subset). Fuzzier numeric-range subsumption is reported at
`info`, never `error` — a false "delete this rule" is worse than a missed one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from amanai.policy import Policy, Rule, load_policy


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warn | info
    code: str  # unreachable-rule | conflicting-rules | redundant-rule | missing-reason | uncovered-tool
    rule_ids: tuple[str, ...]
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "rule_ids": list(self.rule_ids),
            "message": self.message,
        }


# ── match-set model ───────────────────────────────────────────────────────────
def _vrepr(value) -> str:
    """Canonical string for a predicate value so 50 and 50.0 compare equal but a
    number never collides with the string "50.0"."""
    if isinstance(value, bool):
        return json.dumps(value)  # true / false — not a number
    if isinstance(value, (int, float)):
        return "num:" + repr(float(value))
    return json.dumps(value, sort_keys=True, default=str)


def _match_set(rule: Rule) -> dict:
    """The constraints a rule matches on, as comparable sets. Fewer constraints ⇒
    broader match."""
    return {
        "tool": rule.tool,
        "capability": rule.capability,
        "args": frozenset((p["arg"], p["op"], _vrepr(p.get("value"))) for p in rule.args),
        "context": frozenset((p["key"], p["op"], _vrepr(p.get("value"))) for p in rule.context),
    }


def _subsumes(a: dict, b: dict) -> bool:
    """True when match-set `a` matches every action `b` matches (a is broader or
    equal): a constrains on ≤ the targets b does, with a predicate subset.

    Exact-predicate subset only — sound (no false "unreachable"), blind to numeric
    ranges (handled by `_range_subsumes` at lower confidence).
    # ponytail: exact subset; upgrade to interval reasoning if authors hit it.
    """
    if a["tool"] not in (None, b["tool"]):
        return False
    if a["capability"] not in (None, b["capability"]):
        return False
    return a["args"] <= b["args"] and a["context"] <= b["context"]


# ── numeric-range heuristic (lower confidence → info) ─────────────────────────
_DIR_GE = {">=", ">"}
_DIR_LE = {"<=", "<"}


def _arg_map(preds) -> dict | None:
    """{arg: (op, value)}; None if a key repeats (ambiguous — bail)."""
    out: dict = {}
    for p in preds:
        k = p["arg"]
        if k in out:
            return None
        out[k] = (p["op"], p.get("value"))
    return out


def _range_subsumes(a: Rule, b: Rule, aset: dict, bset: dict) -> bool:
    """True when `a` covers a broader numeric range than `b` on the same keys/ops
    (e.g. `pct>=40` before `pct>=50`). Conservative: same target, identical
    context, identical arg keys+ops, at least one value differing in the subsuming
    direction, nothing ambiguous."""
    if aset["tool"] not in (None, bset["tool"]):
        return False
    if aset["capability"] not in (None, bset["capability"]):
        return False
    if aset["context"] != bset["context"]:
        return False
    am, bm = _arg_map(a.args), _arg_map(b.args)
    if am is None or bm is None or set(am) != set(bm):
        return False
    differ = False
    for k in am:
        aop, av = am[k]
        bop, bv = bm[k]
        if aop != bop:
            return False
        if _vrepr(av) == _vrepr(bv):
            continue  # identical predicate
        try:
            af, bf = float(av), float(bv)
        except (TypeError, ValueError):
            return False  # differing non-numeric value → can't reason
        if aop in _DIR_GE and af > bf:
            return False
        if aop in _DIR_LE and af < bf:
            return False
        if aop not in _DIR_GE and aop not in _DIR_LE:
            return False  # differing value on a non-directional op
        differ = True
    return differ


# ── coverage (tools no rule protects) ─────────────────────────────────────────
def _uncovered(policy: Policy, tools) -> list[str]:
    names, caps = set(), set()
    for r in policy.rules:
        if r.tool:
            names.add(r.tool)
        if r.capability:
            caps.add(r.capability)
    items = tools.items() if isinstance(tools, dict) else [(n, {}) for n in tools]
    return [
        name
        for name, meta in items
        if name not in names and (meta or {}).get("capability") not in caps
    ]


# ── entry point ───────────────────────────────────────────────────────────────
_RANK = {"error": 0, "warn": 1, "info": 2}


def lint_policy(source, *, tools=None) -> list[Finding]:
    """Semantically lint a policy. `source` is anything `load_policy` accepts;
    `tools` is a `registered_tools()` dict or a list of tool names to check
    coverage against. Never raises on a policy `load_policy` accepts. Findings are
    ordered: errors first, then by rule position."""
    policy = load_policy(source)
    rules = policy.rules
    sets = [_match_set(r) for r in rules]
    findings: list[Finding] = []

    # One finding per shadowed rule, naming the earliest rule that covers it.
    for j in range(len(rules)):
        b, bset = rules[j], sets[j]
        for i in range(j):
            a, aset = rules[i], sets[i]
            if aset == bset:
                if a.action != b.action:
                    findings.append(
                        Finding(
                            "warn",
                            "conflicting-rules",
                            (a.id, b.id),
                            f"rule {b.id!r} has the same match as earlier rule {a.id!r} but a "
                            f"different action ({a.action} vs {b.action}); the earlier rule wins",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            "warn",
                            "redundant-rule",
                            (a.id, b.id),
                            f"rule {b.id!r} duplicates earlier rule {a.id!r} (same match and action)",
                        )
                    )
                break
            if _subsumes(aset, bset):
                findings.append(
                    Finding(
                        "error",
                        "unreachable-rule",
                        (a.id, b.id),
                        f"rule {b.id!r} is unreachable: earlier rule {a.id!r} already matches "
                        f"every action it would",
                    )
                )
                break
            if _range_subsumes(a, b, aset, bset):
                findings.append(
                    Finding(
                        "info",
                        "unreachable-rule",
                        (a.id, b.id),
                        f"rule {b.id!r} may be unreachable: earlier rule {a.id!r} covers a broader "
                        f"numeric range (heuristic)",
                    )
                )
                break

    for r in rules:
        if r.action in ("block", "require_approval") and r.reason is None:
            findings.append(
                Finding(
                    "info",
                    "missing-reason",
                    (r.id,),
                    f"rule {r.id!r} ({r.action}) has no 'reason'; audit traces will be weaker",
                )
            )

    if tools is not None:
        for name in _uncovered(policy, tools):
            findings.append(
                Finding(
                    "warn",
                    "uncovered-tool",
                    (),
                    f"tool {name!r} is not covered by any rule (by name or capability)",
                )
            )

    pos = {r.id: idx for idx, r in enumerate(rules)}
    findings.sort(
        key=lambda f: (
            _RANK[f.severity],
            min((pos[i] for i in f.rule_ids if i in pos), default=len(rules)),
        )
    )
    return findings
