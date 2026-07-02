import { describe, expect, it } from "vitest";
import { PolicyError, actionRequest, evaluate, loadPolicy } from "../src/index.js";

describe("loadPolicy validation", () => {
  it("accepts a canonical rule", () => {
    const p = loadPolicy([{ id: "d", tool: "x", action: "block" }]);
    expect(p.ids).toEqual(["d"]);
  });

  it("loads the legacy flat form", () => {
    const p = loadPolicy([{ tool: "x", arg: "pct", op: ">=", value: 50 }]);
    expect(p.rules[0].args).toHaveLength(1);
    expect(p.rules[0].action).toBe("block"); // defaults to block
  });

  it("rejects an unknown operator", () => {
    expect(() => loadPolicy([{ tool: "x", args: [{ arg: "p", op: "??", value: 1 }], action: "block" }])).toThrow(
      PolicyError,
    );
  });

  it("rejects an unsupported action", () => {
    expect(() => loadPolicy([{ tool: "x", action: "nope" }])).toThrow(PolicyError);
  });

  it("rejects a rule with no tool or capability", () => {
    expect(() => loadPolicy([{ action: "block" }])).toThrow(PolicyError);
  });

  it("rejects duplicate ids", () => {
    expect(() => loadPolicy([{ id: "d", tool: "x", action: "block" }, { id: "d", tool: "y", action: "block" }])).toThrow(
      PolicyError,
    );
  });

  it("rejects non-array policy", () => {
    expect(() => loadPolicy("{}")).toThrow(PolicyError);
  });
});

describe("evaluate", () => {
  it("returns allow with null ruleId when nothing matches", () => {
    const p = loadPolicy([{ id: "d", tool: "x", args: [{ arg: "p", op: ">=", value: 50 }], action: "block" }]);
    const d = evaluate(actionRequest("x", { p: 10 }), p);
    expect(d.outcome).toBe("allow");
    expect(d.ruleId).toBeNull();
  });

  it("first match wins", () => {
    const p = loadPolicy([
      { id: "a", tool: "x", action: "warn" },
      { id: "b", tool: "x", action: "block" },
    ]);
    expect(evaluate(actionRequest("x", {}), p).ruleId).toBe("a");
  });
});

describe("policy digest", () => {
  const RULES = [{ id: "d", tool: "x", args: [{ arg: "p", op: ">=", value: 50 }], action: "block" }];

  it("is stable for the same rules and changes when a rule changes", () => {
    const digest = loadPolicy(RULES).digest;
    expect(digest).toMatch(/^policy-[0-9a-f]{8}$/);
    expect(loadPolicy(RULES).digest).toBe(digest);
    const changed = [{ id: "d", tool: "x", args: [{ arg: "p", op: ">=", value: 60 }], action: "block" }];
    expect(loadPolicy(changed).digest).not.toBe(digest);
  });

  it("is stamped into every decision, matched or not", () => {
    const p = loadPolicy(RULES);
    expect(evaluate(actionRequest("x", { p: 90 }), p).policyDigest).toBe(p.digest);
    expect(evaluate(actionRequest("other", {}), p).policyDigest).toBe(p.digest);
  });
});
