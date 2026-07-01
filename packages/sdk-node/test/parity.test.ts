import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { actionRequest, evaluate, loadPolicy } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const vectorsPath = resolve(here, "../../../spec/parity/vectors.json");

interface Vector {
  name: string;
  policy: unknown[];
  action: { tool: string; input?: Record<string, unknown>; capability?: string; context?: Record<string, unknown> };
  expect: { outcome: string; ruleId: string | null };
}

const vectors: Vector[] = JSON.parse(readFileSync(vectorsPath, "utf8"));

describe("cross-language parity vectors", () => {
  for (const vec of vectors) {
    it(vec.name, () => {
      const policy = loadPolicy(vec.policy);
      const action = actionRequest(vec.action.tool, vec.action.input ?? {}, {
        capability: vec.action.capability ?? null,
        context: vec.action.context ?? {},
      });
      const decision = evaluate(action, policy);
      expect(decision.outcome).toBe(vec.expect.outcome);
      expect(decision.ruleId).toBe(vec.expect.ruleId);
    });
  }
});
