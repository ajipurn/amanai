/**
 * Operator match logic — the single source of truth for rule predicates, ported
 * to match Python `amanai/operators.py::op_match` exactly. Runtime enforcement
 * and the parity vectors both rely on identical semantics, so "what you test" and
 * "what you enforce" can never drift across languages.
 *
 * Like the Python version, `opMatch` never throws: an unknown operator or a type
 * error returns false so a malformed value can't crash a security decision.
 */

/** Every operator the DSL understands. An op outside this set fails policy load. */
export const KNOWN_OPERATORS = new Set<string>([
  ">=", ">", "<=", "<",
  "==", "eq", "!=", "ne",
  "contains", "regex",
  "in", "membership", "not_in",
  "email_external", "domain_in", "domain_not_in", "internal_url",
]);

/** Mirror Python `float(x)`: True→1, numeric string→number, "" / None / list → NaN. */
function pyFloat(x: unknown): number {
  if (typeof x === "number") return x;
  if (typeof x === "boolean") return x ? 1 : 0;
  if (typeof x === "string") {
    const t = x.trim();
    if (t === "") return NaN;
    return Number(t);
  }
  return NaN; // null/undefined/object → Python float() raises → treated as no-match
}

/** Numeric-first equality with a Python-like fallback (so "5" == 5). */
function pyEq(value: unknown, target: unknown): boolean {
  const a = pyFloat(value);
  const b = pyFloat(target);
  if (!Number.isNaN(a) && !Number.isNaN(b)) return a === b;
  if (typeof value === "object" || typeof target === "object") {
    return JSON.stringify(value) === JSON.stringify(target);
  }
  return value === target;
}

function asArray(target: unknown): unknown[] {
  return Array.isArray(target) ? target : [];
}

function domainOf(value: unknown): string {
  const s = String(value);
  return s.slice(s.lastIndexOf("@") + 1).toLowerCase();
}

function domains(target: unknown): string[] {
  return asArray(target).map((d) => String(d).toLowerCase());
}

// Internal hosts that aren't literal IPs (localhost → loopback; GCP metadata host).
const INTERNAL_HOSTS = new Set(["localhost", "metadata.google.internal"]);

function parseIpv4(host: string): number[] | null {
  const parts = host.split(".");
  if (parts.length !== 4) return null;
  const octets: number[] = [];
  for (const p of parts) {
    if (!/^\d{1,3}$/.test(p)) return null;
    const n = Number(p);
    if (n > 255) return null;
    octets.push(n);
  }
  return octets;
}

/**
 * True for private/loopback/link-local/reserved/unspecified addresses and known
 * internal hosts. Literal-IP + known-hostname only — no DNS resolution, matching
 * the Python posture (catches direct-IP SSRF, not DNS-rebinding).
 */
function isInternalUrl(value: unknown): boolean {
  let host: string;
  try {
    host = new URL(String(value)).hostname || String(value).trim();
  } catch {
    host = String(value).trim();
  }
  host = host.trim().replace(/\.$/, "").replace(/^\[|\]$/g, "").toLowerCase();
  if (!host) return false;
  if (INTERNAL_HOSTS.has(host)) return true;

  const v4 = parseIpv4(host);
  if (v4) {
    const [a, b] = v4;
    if (a === 10) return true; // private 10/8
    if (a === 172 && b >= 16 && b <= 31) return true; // private 172.16/12
    if (a === 192 && b === 168) return true; // private 192.168/16
    if (a === 127) return true; // loopback 127/8
    if (a === 169 && b === 254) return true; // link-local 169.254/16
    if (a === 0) return true; // unspecified / this-network
    if (a >= 240) return true; // reserved 240/4
    return false;
  }
  // Minimal IPv6 specials (full parity for v6 is out of scope — v4 + hosts only).
  if (host === "::1") return true; // loopback
  if (host.startsWith("fe80:") || host.startsWith("fc") || host.startsWith("fd")) return true;
  if (host === "::") return true; // unspecified
  return false; // a hostname we don't resolve → external
}

/** True when `value` satisfies `op` against `target`. Never throws. */
export function opMatch(op: string, value: unknown, target: unknown): boolean {
  try {
    switch (op) {
      case ">=":
      case ">":
      case "<=":
      case "<": {
        const x = pyFloat(value);
        const y = pyFloat(target);
        if (Number.isNaN(x) || Number.isNaN(y)) return false;
        return op === ">=" ? x >= y : op === ">" ? x > y : op === "<=" ? x <= y : x < y;
      }
      case "==":
      case "eq":
        return pyEq(value, target);
      case "!=":
      case "ne":
        return !pyEq(value, target);
      case "contains":
        return String(value).toLowerCase().includes(String(target).toLowerCase());
      case "regex":
        // ponytail: policy-supplied regex, no ReDoS guard — same posture as Python.
        return new RegExp(String(target)).test(String(value));
      case "in":
      case "membership":
        return asArray(target).includes(value);
      case "not_in":
        return !asArray(target).includes(value);
      case "email_external":
        return !domains(target).includes(domainOf(value));
      case "domain_in":
        return domains(target).includes(domainOf(value));
      case "domain_not_in":
        return !domains(target).includes(domainOf(value));
      case "internal_url":
        return isInternalUrl(value) === Boolean(target);
      default:
        return false;
    }
  } catch {
    return false;
  }
}
