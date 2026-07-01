"""Action Policy Engine — the product center: policy-as-code for agent actions.

One policy contract, three lives:

  * runtime enforcement (`enforce` mode blocks unsafe calls before they run),
  * shadow observation (`shadow` records what it *would* block),
  * CI assertion (`test` evaluates traces with no side effects).

The public seam is small and deterministic — no LLM decides whether a tool runs:

    from amanai import load_policy, set_policy, evaluate, ActionRequest

    set_policy(load_policy("amanai.policy.json"))
    decision = evaluate(ActionRequest("apply_discount", {"pct": 90}))
    decision.outcome   # "block"
    decision.rule_id   # "discount-cap"
    decision.reason    # "discount >= 50% not allowed"

A rule is `{id, tool?, capability?, args?, context?, action, reason?}`. The legacy
flat shape `{tool, arg, op, value, action?}` still loads — it normalizes to one
arg predicate, defaulting to `block`. The DSL is intentionally small; it is not
a general-purpose policy language.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from amanai.operators import KNOWN_OPERATORS, op_match

# ── outcomes & modes ──────────────────────────────────────────────────────────
OUTCOMES = frozenset({"allow", "block", "warn", "require_approval"})
MODES = frozenset({"enforce", "shadow", "test"})


# ── exceptions ────────────────────────────────────────────────────────────────
class ToolBlocked(Exception):
    """Raised when a tool-call violates a `block` rule in `enforce` mode."""


class ApprovalRequired(Exception):
    """Raised when a `require_approval` rule gates a tool-call in `enforce` mode.

    Carries the structured `PendingAction` so a human or callback can decide.
    """

    def __init__(self, pending: "PendingAction"):
        self.pending = pending
        super().__init__(pending.decision.reason or "approval required")


class PolicyError(ValueError):
    """Raised when a policy file is malformed — fail early, not at runtime."""


# ── canonical schema ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ActionRequest:
    """A normalized, framework-neutral tool-call awaiting a decision."""

    tool: str
    input: dict = field(default_factory=dict)
    capability: str | None = None
    context: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    """The engine's verdict for one action."""

    outcome: str
    rule_id: str | None = None
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome in ("allow", "warn")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TraceEvent:
    """Evidence: one action, its decision, and what happened when executed."""

    action: ActionRequest
    decision: PolicyDecision
    status: str  # executed | blocked | shadowed | pending | evaluated | error
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict(),
            "decision": self.decision.to_dict(),
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class PendingAction:
    """A `require_approval` action parked for a human/callback decision."""

    action: ActionRequest
    decision: PolicyDecision

    @property
    def token(self) -> str:
        return _hash8(self.action.to_dict(), "pending-")


# ── rules & policy ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Rule:
    id: str
    action: str
    tool: str | None = None
    capability: str | None = None
    reason: str | None = None
    args: tuple[dict, ...] = ()
    context: tuple[dict, ...] = ()

    def matches(self, action: ActionRequest) -> bool:
        if self.tool is not None and self.tool != action.tool:
            return False
        if self.capability is not None and self.capability != action.capability:
            return False
        return _preds_true(self.args, action.input) and _preds_true(self.context, action.context)


def _preds_true(preds: tuple[dict, ...], source: dict) -> bool:
    for pred in preds:
        key = pred.get("arg") or pred.get("key")
        # An absent key means the predicate can't be satisfied → rule skipped.
        # Preserves legacy "arg not present → no match" semantics.
        if key not in source or not op_match(pred["op"], source[key], pred.get("value")):
            return False
    return True


class Policy:
    """An ordered, validated set of rules. First match wins."""

    def __init__(self, rules: list[Rule]):
        self.rules = rules

    @property
    def ids(self) -> list[str]:
        return [r.id for r in self.rules]

    def match(self, action: ActionRequest) -> Rule | None:
        for rule in self.rules:
            if rule.matches(action):
                return rule
        return None


# ── loading & validation ──────────────────────────────────────────────────────
def _hash8(obj, prefix: str) -> str:
    """Deterministic short id: sha1 of the canonical JSON, prefixed."""
    blob = json.dumps(obj, sort_keys=True, default=str)
    return prefix + hashlib.sha1(blob.encode()).hexdigest()[:8]


def _validate_pred(pred: dict, key_name: str, idx: int) -> dict:
    if not isinstance(pred, dict):
        raise PolicyError(f"rule {idx}: predicate must be an object, got {pred!r}")
    if key_name not in pred or "op" not in pred:
        raise PolicyError(f"rule {idx}: predicate needs {key_name!r} and 'op': {pred!r}")
    if pred["op"] not in KNOWN_OPERATORS:
        raise PolicyError(f"rule {idx}: unknown operator {pred['op']!r}")
    return {key_name: pred[key_name], "op": pred["op"], "value": pred.get("value")}


def _normalize_rule(raw: dict, idx: int, require_ids: bool) -> Rule:
    if not isinstance(raw, dict):
        raise PolicyError(f"rule {idx}: must be an object, got {raw!r}")

    args = list(raw.get("args") or [])
    context = list(raw.get("context") or [])
    # Legacy flat form: {tool, arg, op, value} → one arg predicate.
    if "arg" in raw and "op" in raw:
        args.append({"arg": raw["arg"], "op": raw["op"], "value": raw.get("value")})

    args = tuple(_validate_pred(p, "arg", idx) for p in args)
    context = tuple(_validate_pred(p, "key", idx) for p in context)

    action = raw.get("action", "block")  # fail closed: unannotated rules block
    if action not in OUTCOMES:
        raise PolicyError(f"rule {idx}: unsupported action {action!r} (use {sorted(OUTCOMES)})")

    if raw.get("tool") is None and raw.get("capability") is None:
        raise PolicyError(f"rule {idx}: needs a 'tool' or 'capability' to match on")

    rid = raw.get("id")
    if rid is None:
        if require_ids:
            raise PolicyError(f"rule {idx}: missing required 'id'")
        rid = _hash8({k: raw[k] for k in sorted(raw) if k != "id"}, "rule-")

    return Rule(
        id=rid,
        action=action,
        tool=raw.get("tool"),
        capability=raw.get("capability"),
        reason=raw.get("reason"),
        args=args,
        context=context,
    )


def load_policy(source, *, require_ids: bool = False) -> Policy:
    """Load and validate a policy from a list of rule dicts, a JSON file path, or
    a JSON string. Raises `PolicyError` on any malformed rule. Rules without an
    `id` get a deterministic generated one (set `require_ids=True` to reject)."""
    if isinstance(source, Policy):
        return source
    if isinstance(source, (str, Path)):
        text = Path(source).read_text() if Path(str(source)).exists() else str(source)
        try:
            raw_rules = json.loads(text)
        except json.JSONDecodeError as e:
            raise PolicyError(f"invalid policy JSON: {e}") from e
    else:
        raw_rules = source

    if not isinstance(raw_rules, list):
        raise PolicyError("policy must be a list of rules")

    rules = [_normalize_rule(r, i, require_ids) for i, r in enumerate(raw_rules)]
    seen: set[str] = set()
    for r in rules:
        if r.id in seen:
            raise PolicyError(f"duplicate rule id {r.id!r}")
        seen.add(r.id)
    return Policy(rules)


# ── context-local state (per request/invocation, never global) ────────────────
_active_policy: contextvars.ContextVar[Policy | None] = contextvars.ContextVar(
    "amanai_policy", default=None
)
_mode: contextvars.ContextVar[str] = contextvars.ContextVar("amanai_mode", default="enforce")
_context: contextvars.ContextVar[dict] = contextvars.ContextVar("amanai_ctx", default={})


def set_policy(source) -> Policy:
    """Activate a policy for the current context. Accepts a `Policy`, rule list,
    path, or JSON string (anything `load_policy` takes)."""
    pol = load_policy(source)
    _active_policy.set(pol)
    return pol


def get_policy() -> Policy | None:
    return _active_policy.get()


def clear_tool_policy() -> None:
    """Deactivate the current context's policy (evaluate -> allow, no rules)."""
    _active_policy.set(None)


def set_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r} (use {sorted(MODES)})")
    _mode.set(mode)


def get_mode() -> str:
    return _mode.get()


def set_context(**ctx) -> None:
    """Attach authorization context (user_id, role, tenant, session_id,
    environment, …) to actions evaluated in the current context."""
    _context.set({**_context.get(), **ctx})


def get_context() -> dict:
    return dict(_context.get())


def clear_context() -> None:
    _context.set({})


# ── evaluation (deterministic, no execution) ──────────────────────────────────
def evaluate(action: ActionRequest, policy: Policy | None = None) -> PolicyDecision:
    """Decide what to do with an action. Pure: never executes a tool, never calls
    an LLM. Uses the active policy unless one is passed (for replay)."""
    pol = policy if policy is not None else _active_policy.get()
    if pol is None:
        return PolicyDecision("allow", None, "no policy loaded")
    rule = pol.match(action)
    if rule is None:
        return PolicyDecision("allow", None, "no matching policy rule")
    return PolicyDecision(
        outcome=rule.action,
        rule_id=rule.id,
        reason=rule.reason or f"matched rule {rule.id}",
        metadata={"capability": rule.capability} if rule.capability else {},
    )

