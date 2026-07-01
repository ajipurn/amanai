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
import { actionToJSON, decisionToJSON } from "./policy.js";
import type { Mode, Policy, PolicyDecision, ActionRequest } from "./policy.js";

export interface TraceEvent {
  action: ActionRequest;
  decision: PolicyDecision;
  status: string; // executed | blocked | shadowed | pending | evaluated | error
  output?: unknown;
  error?: string | null;
}

interface Store {
  policy: Policy | null;
  mode: Mode;
  context: Record<string, unknown>;
  trace: TraceEvent[];
}

function freshStore(): Store {
  return { policy: null, mode: "enforce", context: {}, trace: [] };
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
  store().trace.push(event);
}
/** Return the trace recorded so far and clear the buffer. */
export function collectTrace(): TraceEvent[] {
  const s = store();
  const out = s.trace;
  s.trace = [];
  return out;
}
export function reset(): void {
  store().trace = [];
}

export function traceEventToJSON(e: TraceEvent): Record<string, unknown> {
  return {
    action: actionToJSON(e.action),
    decision: decisionToJSON(e.decision),
    status: e.status,
    output: e.output ?? null,
    error: e.error ?? null,
  };
}
