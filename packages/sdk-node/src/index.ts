/**
 * Amanai SDK (TypeScript) — policy-as-code for AI agent actions.
 *
 * The core Action Policy Engine, ported from the Python SDK: it loads the same
 * policy JSON and returns the same decisions (guaranteed by shared parity vectors).
 * Guardrails, the offline judge, and the monitor are Python-only for now.
 */

export {
  OUTCOMES,
  MODES,
  Policy,
  PolicyError,
  ToolBlocked,
  ApprovalRequired,
  actionRequest,
  loadPolicy,
  evaluate,
  actionToJSON,
  decisionToJSON,
  pendingToken,
} from "./policy.js";
export type { Outcome, Mode, ActionRequest, PolicyDecision, Rule } from "./policy.js";

export {
  runWithContext,
  setPolicy,
  getPolicy,
  clearPolicy,
  setMode,
  getMode,
  setContext,
  getContext,
  clearContext,
  recordEvent,
  collectTrace,
  reset,
  approveAction,
  traceEventToJSON,
} from "./context.js";
export type { TraceEvent } from "./context.js";

export { tool, guardToolCall } from "./client.js";

export { KNOWN_OPERATORS, opMatch } from "./operators.js";
