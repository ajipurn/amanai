import { describe, expect, it } from "vitest";
import {
  ToolBlocked,
  collectTrace,
  guardToolCall,
  runWithContext,
  setMode,
  setPolicy,
  loadPolicy,
  tool,
} from "../src/index.js";

const POLICY = [
  { id: "cap", tool: "apply_discount", args: [{ arg: "pct", op: ">=", value: 50 }], action: "block", reason: "too high" },
];

describe("tool wrapper", () => {
  it("blocks in enforce mode before the body runs", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(POLICY));
      setMode("enforce");
      let ran = false;
      const applyDiscount = tool((args: { pct: number }) => {
        ran = true;
        return "applied";
      }, { name: "apply_discount" });
      expect(() => applyDiscount({ pct: 90 })).toThrow(ToolBlocked);
      expect(ran).toBe(false);
    });
  });

  it("runs and records executed evidence when allowed", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(POLICY));
      setMode("enforce");
      const applyDiscount = tool((args: { pct: number }) => "applied", { name: "apply_discount" });
      expect(applyDiscount({ pct: 10 })).toBe("applied");
      const trace = collectTrace();
      expect(trace).toHaveLength(1);
      expect(trace[0].status).toBe("executed");
    });
  });

  it("test mode records without executing", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(POLICY));
      setMode("test");
      let ran = false;
      const applyDiscount = tool(() => {
        ran = true;
        return "x";
      }, { name: "apply_discount" });
      applyDiscount({ pct: 10 });
      expect(ran).toBe(false);
      expect(collectTrace()[0].status).toBe("evaluated");
    });
  });
});

describe("guardToolCall", () => {
  it("raises ToolBlocked in enforce mode", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(POLICY));
      setMode("enforce");
      expect(() => guardToolCall("apply_discount", { pct: 90 })).toThrow(ToolBlocked);
    });
  });
});

describe("context isolation", () => {
  it("two runWithContext scopes do not share policy or trace", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(POLICY));
      setMode("enforce");
      const t = tool((a: { pct: number }) => "ok", { name: "apply_discount" });
      t({ pct: 10 });
      expect(collectTrace()).toHaveLength(1);
    });
    runWithContext(() => {
      // fresh store: no policy loaded → allow, and an empty trace
      const t = tool((a: { pct: number }) => "ok", { name: "apply_discount" });
      expect(t({ pct: 90 })).toBe("ok"); // no policy → not blocked
    });
  });
});
