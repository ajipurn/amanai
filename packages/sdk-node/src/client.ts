/**
 * Protect tools and collect traces — the runtime entry point into the engine
 * (TypeScript port of `client.py`'s `tool` + trace capture). Behavior depends on
 * the current mode:
 *   enforce — block → ToolBlocked, require_approval → ApprovalRequired; neither runs.
 *   shadow  — a would-be-blocked call still runs but is recorded as evidence.
 *   test    — nothing executes; the decision is recorded.
 *
 * Unlike Python there is no signature binding: a wrapped tool takes an explicit
 * args object, so pass `{ argName: value }`.
 */

import { getContext, getMode, getPolicy, recordEvent } from "./context.js";
import type { TraceEvent } from "./context.js";
import {
  ApprovalRequired,
  ToolBlocked,
  actionRequest,
  evaluate,
} from "./policy.js";
import type { ActionRequest } from "./policy.js";

function decideAndAct(
  name: string,
  input: Record<string, unknown>,
  opts: { capability?: string | null; run?: () => unknown } = {},
): unknown {
  const policy = getPolicy();
  const action: ActionRequest = actionRequest(name, input, {
    capability: opts.capability ?? null,
    context: getContext(),
  });
  const decision = policy
    ? evaluate(action, policy)
    : {
        outcome: "allow" as const,
        ruleId: null,
        reason: "no policy loaded",
        metadata: {},
        policyDigest: null,
      };
  const mode = getMode();

  if (mode === "test") {
    recordEvent({ action, decision, status: "evaluated" });
    return undefined;
  }
  if (decision.outcome === "block" && mode === "enforce") {
    recordEvent({ action, decision, status: "blocked" });
    throw new ToolBlocked(decision.reason || `${name} blocked by policy`);
  }
  if (decision.outcome === "require_approval" && mode === "enforce") {
    recordEvent({ action, decision, status: "pending" });
    throw new ApprovalRequired(action, decision);
  }

  if (!opts.run) {
    // gate-only (guardToolCall): return the decision via a thrown-free path
    return decision;
  }

  let result: unknown;
  try {
    result = opts.run();
  } catch (e) {
    recordEvent({ action, decision, status: "error", error: (e as Error).message });
    throw e;
  }
  const shadowed = decision.outcome === "block" || decision.outcome === "require_approval";
  recordEvent({ action, decision, status: shadowed ? "shadowed" : "executed", output: result });
  return result;
}

/** Wrap a function so each call is evaluated + enforced, then recorded. */
export function tool<A extends Record<string, unknown>, R>(
  fn: (args: A) => R,
  opts: { name?: string; capability?: string | null } = {},
): (args: A) => R {
  const name = opts.name ?? fn.name ?? "tool";
  return (args: A): R =>
    decideAndAct(name, args, { capability: opts.capability, run: () => fn(args) }) as R;
}

/** Gate a tool-call before it runs (the framework-neutral funnel). enforce raises;
 * shadow/test return the decision. */
export function guardToolCall(
  name: string,
  args: Record<string, unknown> = {},
  opts: { capability?: string | null } = {},
) {
  return decideAndAct(name, args, { capability: opts.capability });
}

export type { TraceEvent };
