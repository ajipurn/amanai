import { describe, expect, it } from "vitest";
import {
  ApprovalRequired,
  ToolBlocked,
  actionRequest,
  approveAction,
  collectTrace,
  guardToolCall,
  pendingToken,
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

  it("stamps recorded evidence with id, UTC ts, and the policy digest", () => {
    runWithContext(() => {
      const policy = loadPolicy(POLICY);
      setPolicy(policy);
      setMode("enforce");
      const applyDiscount = tool((args: { pct: number }) => "applied", { name: "apply_discount" });
      applyDiscount({ pct: 10 });
      const e = collectTrace()[0];
      expect(e.id).toMatch(/^evt-[0-9a-f]{32}$/);
      expect(e.ts).toMatch(/Z$/); // Date.toISOString() — same canonical format as Python
      expect(e.decision.policyDigest).toBe(policy.digest);
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

describe("approvals", () => {
  const APPROVAL_POLICY = [
    { id: "big-refund", tool: "refund_payment", args: [{ arg: "amount", op: ">=", value: 1000 }], action: "require_approval" },
  ];

  it("grants exactly one execution, recorded as approved", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(APPROVAL_POLICY));
      setMode("enforce");
      const ran: number[] = [];
      const refund = tool((a: { amount: number }) => {
        ran.push(a.amount);
        return "refunded";
      }, { name: "refund_payment" });

      let token = "";
      try {
        refund({ amount: 5000 });
      } catch (e) {
        token = (e as ApprovalRequired).token;
      }
      expect(token).toMatch(/^pending-[0-9a-f]{8}$/);
      collectTrace(); // drop the pending event

      approveAction(token);
      expect(refund({ amount: 5000 })).toBe("refunded");
      expect(collectTrace()[0].status).toBe("approved");
      expect(ran).toEqual([5000]);

      expect(() => refund({ amount: 5000 })).toThrow(ApprovalRequired); // one-shot
      expect(ran).toEqual([5000]);
    });
  });

  it("guardToolCall approved path returns the decision and records the grant", () => {
    runWithContext(() => {
      setPolicy(loadPolicy(APPROVAL_POLICY));
      setMode("enforce");
      expect(() => guardToolCall("refund_payment", { amount: 5000 })).toThrow(ApprovalRequired);
      collectTrace();

      approveAction(pendingToken(actionRequest("refund_payment", { amount: 5000 })));
      const decision = guardToolCall("refund_payment", { amount: 5000 });
      expect((decision as { outcome: string }).outcome).toBe("require_approval");
      expect(collectTrace()[0].status).toBe("approved");
    });
  });

  it("pendingToken is byte-identical to the Python SDK for the same action", () => {
    // Locked value — see tests/test_approvals.py::test_pending_token_is_cross_language_canonical
    expect(pendingToken(actionRequest("refund_payment", { amount: 5000 }))).toBe("pending-bcbb2530");
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
