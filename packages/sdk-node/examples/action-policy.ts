/**
 * Enforce an Amanai policy in TypeScript. The same policy JSON works in the Python
 * SDK and blocks the same calls.
 *
 *   npx tsx packages/sdk-node/examples/action-policy.ts
 */

import {
  ToolBlocked,
  collectTrace,
  loadPolicy,
  runWithContext,
  setMode,
  setPolicy,
  tool,
  traceEventToJSON,
} from "../src/index.js";

runWithContext(() => {
  setPolicy(
    loadPolicy([
      {
        id: "discount-cap",
        tool: "apply_discount",
        args: [{ arg: "pct", op: ">=", value: 50 }],
        action: "block",
        reason: "discount of 50% or more is never allowed",
      },
    ]),
  );
  setMode("enforce");

  const applyDiscount = tool((args: { pct: number }) => `applied ${args.pct}%`, {
    name: "apply_discount",
    capability: "pricing",
  });

  for (const pct of [10, 90]) {
    try {
      console.log("OK     ", applyDiscount({ pct }));
    } catch (e) {
      if (e instanceof ToolBlocked) console.log("BLOCKED", `apply_discount(${pct}): ${e.message}`);
      else throw e;
    }
  }

  console.log("\ntrace (evidence for CI / audit):");
  for (const event of collectTrace()) console.log(" ", JSON.stringify(traceEventToJSON(event)));
});
