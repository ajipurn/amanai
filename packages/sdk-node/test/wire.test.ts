import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  collectTrace,
  loadPolicy,
  runWithContext,
  setPolicy,
  tool,
  traceEventToJSON,
} from "../src/index.js";

// Wire-format contract: what this SDK emits must match spec/wire/*.schema.json —
// the same shape the Python SDK emits and a trace consumer codes against.
const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(
  readFileSync(resolve(here, "../../../spec/wire/trace-event.v1.schema.json"), "utf8"),
);
const defs = schema.$defs;

function emitEvent(): Record<string, unknown> {
  return runWithContext(() => {
    setPolicy(loadPolicy([{ id: "d", tool: "act", args: [{ arg: "n", op: ">=", value: 100 }] }]));
    const act = tool((a: { n: number }) => a.n, { name: "act" });
    act({ n: 1 });
    return traceEventToJSON(collectTrace()[0]);
  });
}

describe("wire format v1", () => {
  it("emitted event matches the schema shape", () => {
    const d = emitEvent();
    expect(Object.keys(d).sort()).toEqual([...defs.traceEvent.required].sort());
    expect(Object.keys(d.action as object).sort()).toEqual([...defs.action.required].sort());
    expect(Object.keys(d.decision as object).sort()).toEqual([...defs.decision.required].sort());
  });

  it("id, ts, and policy_digest match the schema formats", () => {
    const d = emitEvent();
    expect(d.id).toMatch(new RegExp(defs.traceEvent.properties.id.pattern));
    expect(d.ts).toMatch(/Z$/);
    expect((d.decision as Record<string, unknown>).policy_digest).toMatch(
      new RegExp(defs.decision.properties.policy_digest.pattern),
    );
  });
});
