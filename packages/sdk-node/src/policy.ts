/**
 * Action Policy Engine (TypeScript port) — the product center, mirroring
 * `amanai/policy.py`. Same policy JSON, same deterministic decisions. No LLM is
 * ever in the decision path.
 *
 * A rule is `{id, tool?, capability?, args?, context?, action, reason?}`. The
 * legacy flat shape `{tool, arg, op, value, action?}` still loads (normalized to
 * one arg predicate, defaulting to `block`).
 */

import { createHash } from "node:crypto";
import { KNOWN_OPERATORS, opMatch } from "./operators.js";

export type Outcome = "allow" | "block" | "warn" | "require_approval";
export type Mode = "enforce" | "shadow" | "test";

export const OUTCOMES: ReadonlySet<Outcome> = new Set([
  "allow", "block", "warn", "require_approval",
]);
export const MODES: ReadonlySet<Mode> = new Set(["enforce", "shadow", "test"]);

export interface ActionRequest {
  tool: string;
  input: Record<string, unknown>;
  capability: string | null;
  context: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

/** Build an ActionRequest with Python-matching defaults. */
export function actionRequest(
  tool: string,
  input: Record<string, unknown> = {},
  opts: { capability?: string | null; context?: Record<string, unknown>; metadata?: Record<string, unknown> } = {},
): ActionRequest {
  return {
    tool,
    input,
    capability: opts.capability ?? null,
    context: opts.context ?? {},
    metadata: opts.metadata ?? {},
  };
}

export interface PolicyDecision {
  outcome: Outcome;
  ruleId: string | null;
  reason: string;
  metadata: Record<string, unknown>;
  /** Which policy version decided (see `Policy.digest`); null when none loaded. */
  policyDigest: string | null;
}

/** Emit the Python-identical JSON keys (`rule_id`) so traces are cross-readable. */
export function decisionToJSON(d: PolicyDecision): Record<string, unknown> {
  return {
    outcome: d.outcome,
    rule_id: d.ruleId,
    reason: d.reason,
    metadata: d.metadata,
    policy_digest: d.policyDigest,
  };
}

export function actionToJSON(a: ActionRequest): Record<string, unknown> {
  return {
    tool: a.tool,
    input: a.input,
    capability: a.capability,
    context: a.context,
    metadata: a.metadata,
  };
}

interface Pred {
  key: string; // the arg or context key to look up
  op: string;
  value: unknown;
}

export interface Rule {
  id: string;
  action: Outcome;
  tool: string | null;
  capability: string | null;
  reason: string | null;
  args: Pred[];
  context: Pred[];
}

export class PolicyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PolicyError";
  }
}

export class ToolBlocked extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ToolBlocked";
  }
}

export class ApprovalRequired extends Error {
  decision: PolicyDecision;
  action: ActionRequest;
  constructor(action: ActionRequest, decision: PolicyDecision) {
    super(decision.reason || "approval required");
    this.name = "ApprovalRequired";
    this.action = action;
    this.decision = decision;
  }
}

// ── Python-canonical JSON (json.dumps(sort_keys=True)) for deterministic ids ────
function pyStr(s: string): string {
  // JSON.stringify handles quotes/backslashes/control chars; then escape non-ASCII
  // to \\uXXXX (lowercase) to match Python's ensure_ascii default.
  let out = "";
  for (const ch of JSON.stringify(s)) {
    const code = ch.charCodeAt(0);
    out += code > 0x7f ? "\\u" + code.toString(16).padStart(4, "0") : ch;
  }
  return out;
}

function pyJson(obj: unknown): string {
  if (obj === null || obj === undefined) return "null";
  if (typeof obj === "boolean") return obj ? "true" : "false";
  if (typeof obj === "number") return String(obj);
  if (typeof obj === "string") return pyStr(obj);
  if (Array.isArray(obj)) return "[" + obj.map(pyJson).join(", ") + "]";
  const keys = Object.keys(obj as Record<string, unknown>).sort();
  return (
    "{" + keys.map((k) => pyStr(k) + ": " + pyJson((obj as Record<string, unknown>)[k])).join(", ") + "}"
  );
}

function hash8(obj: unknown, prefix: string): string {
  return prefix + createHash("sha1").update(pyJson(obj)).digest("hex").slice(0, 8);
}

// ── loading & validation ──────────────────────────────────────────────────────
function validatePred(pred: unknown, keyName: "arg" | "key", idx: number): Pred {
  if (typeof pred !== "object" || pred === null || Array.isArray(pred)) {
    throw new PolicyError(`rule ${idx}: predicate must be an object, got ${JSON.stringify(pred)}`);
  }
  const p = pred as Record<string, unknown>;
  if (!(keyName in p) || !("op" in p)) {
    throw new PolicyError(`rule ${idx}: predicate needs '${keyName}' and 'op': ${JSON.stringify(p)}`);
  }
  if (!KNOWN_OPERATORS.has(p.op as string)) {
    throw new PolicyError(`rule ${idx}: unknown operator ${JSON.stringify(p.op)}`);
  }
  return { key: p[keyName] as string, op: p.op as string, value: p.value };
}

function normalizeRule(raw: unknown, idx: number, requireIds: boolean): Rule {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new PolicyError(`rule ${idx}: must be an object, got ${JSON.stringify(raw)}`);
  }
  const r = raw as Record<string, unknown>;

  const rawArgs = Array.isArray(r.args) ? [...r.args] : [];
  const rawContext = Array.isArray(r.context) ? [...r.context] : [];
  // Legacy flat form: {tool, arg, op, value} → one arg predicate.
  if ("arg" in r && "op" in r) {
    rawArgs.push({ arg: r.arg, op: r.op, value: r.value });
  }

  const args = rawArgs.map((p) => validatePred(p, "arg", idx));
  const context = rawContext.map((p) => validatePred(p, "key", idx));

  const action = (r.action ?? "block") as Outcome; // fail closed
  if (!OUTCOMES.has(action)) {
    throw new PolicyError(`rule ${idx}: unsupported action ${JSON.stringify(action)}`);
  }
  if (r.tool == null && r.capability == null) {
    throw new PolicyError(`rule ${idx}: needs a 'tool' or 'capability' to match on`);
  }

  let id = r.id as string | undefined;
  if (id == null) {
    if (requireIds) throw new PolicyError(`rule ${idx}: missing required 'id'`);
    const withoutId: Record<string, unknown> = {};
    for (const k of Object.keys(r)) if (k !== "id") withoutId[k] = r[k];
    id = hash8(withoutId, "rule-");
  }

  return {
    id,
    action,
    tool: (r.tool as string) ?? null,
    capability: (r.capability as string) ?? null,
    reason: (r.reason as string) ?? null,
    args,
    context,
  };
}

/** The rule's canonical normalized shape, shared with the Python engine
 * (`policy.py::_rule_dict`) so the policy digest is identical across languages. */
function ruleDict(r: Rule): Record<string, unknown> {
  return {
    id: r.id,
    action: r.action,
    tool: r.tool,
    capability: r.capability,
    reason: r.reason,
    args: r.args.map((p) => ({ arg: p.key, op: p.op, value: p.value ?? null })),
    context: r.context.map((p) => ({ key: p.key, op: p.op, value: p.value ?? null })),
  };
}

export class Policy {
  private _digest: string | null = null;

  constructor(public rules: Rule[]) {}

  get ids(): string[] {
    return this.rules.map((r) => r.id);
  }

  /** Deterministic version id of the normalized rules (`policy-` + sha1/8),
   * byte-identical to the Python engine's `Policy.digest`. A version marker,
   * not a cryptographic integrity proof. */
  get digest(): string {
    if (this._digest === null) {
      this._digest = hash8(this.rules.map(ruleDict), "policy-");
    }
    return this._digest;
  }

  match(action: ActionRequest): Rule | null {
    for (const rule of this.rules) {
      if (ruleMatches(rule, action)) return rule;
    }
    return null;
  }
}

function predsTrue(preds: Pred[], source: Record<string, unknown>): boolean {
  for (const pred of preds) {
    if (!(pred.key in source) || !opMatch(pred.op, source[pred.key], pred.value)) {
      return false;
    }
  }
  return true;
}

function ruleMatches(rule: Rule, action: ActionRequest): boolean {
  if (rule.tool !== null && rule.tool !== action.tool) return false;
  if (rule.capability !== null && rule.capability !== action.capability) return false;
  return predsTrue(rule.args, action.input) && predsTrue(rule.context, action.context);
}

/** Load and validate a policy from an array of rule objects or a JSON string. */
export function loadPolicy(source: unknown, opts: { requireIds?: boolean } = {}): Policy {
  if (source instanceof Policy) return source;
  let rawRules: unknown = source;
  if (typeof source === "string") {
    try {
      rawRules = JSON.parse(source);
    } catch (e) {
      throw new PolicyError(`invalid policy JSON: ${(e as Error).message}`);
    }
  }
  if (!Array.isArray(rawRules)) {
    throw new PolicyError("policy must be a list of rules");
  }
  const rules = rawRules.map((r, i) => normalizeRule(r, i, opts.requireIds ?? false));
  const seen = new Set<string>();
  for (const rule of rules) {
    if (seen.has(rule.id)) throw new PolicyError(`duplicate rule id ${JSON.stringify(rule.id)}`);
    seen.add(rule.id);
  }
  return new Policy(rules);
}

/** Decide what to do with an action. Pure: never runs a tool, never calls an LLM. */
export function evaluate(action: ActionRequest, policy: Policy): PolicyDecision {
  const rule = policy.match(action);
  if (rule === null) {
    return {
      outcome: "allow",
      ruleId: null,
      reason: "no matching policy rule",
      metadata: {},
      policyDigest: policy.digest,
    };
  }
  return {
    outcome: rule.action,
    ruleId: rule.id,
    reason: rule.reason || `matched rule ${rule.id}`,
    metadata: rule.capability ? { capability: rule.capability } : {},
    policyDigest: policy.digest,
  };
}
