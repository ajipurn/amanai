/**
 * Per-invocation state — the Node analog of Python's `contextvars`. Policy, mode,
 * authorization context, and the trace buffer live in an `AsyncLocalStorage` store
 * so concurrent requests never see each other's state. Outside any `runWithContext`
 * scope, a module-global default store is used.
 *
 * ponytail: module-global fallback mirrors Python's contextvars default. Wrap a
 * request handler in `runWithContext` for true per-request isolation.
 */

import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import { actionToJSON, decisionToJSON } from "./policy.js";
import type { Mode, Policy, PolicyDecision, ActionRequest } from "./policy.js";

export interface TraceEvent {
  action: ActionRequest;
  decision: PolicyDecision;
  status: string; // executed | blocked | shadowed | pending | evaluated | error | approved
  output?: unknown;
  error?: string | null;
  /** Unique event id (`evt-` + 32 hex) and UTC timestamp — filled by recordEvent. */
  id?: string;
  ts?: string;
}

interface Store {
  policy: Policy | null;
  mode: Mode;
  context: Record<string, unknown>;
  trace: TraceEvent[];
  approvals: Set<string>;
}

function freshStore(): Store {
  return { policy: null, mode: "enforce", context: {}, trace: [], approvals: new Set() };
}

const als = new AsyncLocalStorage<Store>();
const globalStore = freshStore();

function store(): Store {
  return als.getStore() ?? globalStore;
}

/** Run `fn` with a fresh isolated store (policy/mode/context/trace). */
export function runWithContext<T>(fn: () => T): T {
  return als.run(freshStore(), fn);
}

export function setPolicy(policy: Policy): void {
  store().policy = policy;
}
export function getPolicy(): Policy | null {
  return store().policy;
}
export function clearPolicy(): void {
  store().policy = null;
}

export function setMode(mode: Mode): void {
  store().mode = mode;
}
export function getMode(): Mode {
  return store().mode;
}

export function setContext(ctx: Record<string, unknown>): void {
  const s = store();
  s.context = { ...s.context, ...ctx };
}
export function getContext(): Record<string, unknown> {
  return { ...store().context };
}
export function clearContext(): void {
  store().context = {};
}

export function recordEvent(event: TraceEvent): void {
  // Single choke point: every recorded event gets a unique id and a UTC timestamp
  // (`Date.toISOString()` — same canonical format the Python SDK emits).
  event.id ??= "evt-" + randomUUID().replaceAll("-", "");
  event.ts ??= new Date().toISOString();
  store().trace.push(event);
}
/** Return the trace recorded so far and clear the buffer. */
export function collectTrace(): TraceEvent[] {
  const s = store();
  const out = s.trace;
  s.trace = [];
  return out;
}
/** Clear the trace buffer and any unconsumed approval grants. */
export function reset(): void {
  const s = store();
  s.trace = [];
  s.approvals = new Set();
}

/** Grant one execution for a `require_approval`-gated action (see Python
 * `approve_action`). One-shot and context-local: the next matching call consumes
 * the grant; an identical call after that requires approval again. */
export function approveAction(pendingOrToken: string | { token: string }): string {
  const token = typeof pendingOrToken === "string" ? pendingOrToken : pendingOrToken.token;
  if (typeof token !== "string" || !token.startsWith("pending-")) {
    throw new Error(`not an approval token: ${JSON.stringify(pendingOrToken)}`);
  }
  store().approvals.add(token);
  return token;
}

/** Consume a grant if present — one approval sanctions exactly one execution. */
export function consumeApproval(token: string): boolean {
  return store().approvals.delete(token);
}

export function traceEventToJSON(e: TraceEvent): Record<string, unknown> {
  return {
    id: e.id ?? "",
    ts: e.ts ?? "",
    action: actionToJSON(e.action),
    decision: decisionToJSON(e.decision),
    status: e.status,
    output: e.output ?? null,
    error: e.error ?? null,
  };
}
