import { describe, expect, it } from "vitest";
import { opMatch } from "../src/operators.js";

describe("opMatch", () => {
  const cases: Array<[string, unknown, unknown, boolean]> = [
    [">=", 50, 50, true],
    [">=", 49, 50, false],
    [">", 51, 50, true],
    ["<", 10, 20, true],
    ["==", "5", 5, true], // numeric-first coercion
    ["==", "abc", "abc", true],
    ["!=", 5, 6, true],
    ["contains", "Hello World", "world", true],
    ["regex", "abc123", "\\d+", true],
    ["in", "b", ["a", "b"], true],
    ["not_in", "c", ["a", "b"], true],
    ["email_external", "x@evil.com", ["acme.com"], true],
    ["email_external", "x@acme.com", ["acme.com"], false],
    ["domain_in", "x@acme.com", ["acme.com"], true],
    ["internal_url", "http://10.0.0.1", true, true],
    ["internal_url", "http://169.254.169.254", true, true],
    ["internal_url", "http://8.8.8.8", true, false],
    ["internal_url", "localhost", true, true],
    ["internal_url", "http://8.8.8.8", false, true], // fire-on-external
    // never throws → false for malformed / unknown
    [">=", "abc", 50, false],
    [">=", null, 50, false],
    ["unknown_op", 1, 1, false],
  ];

  for (const [op, value, target, expected] of cases) {
    it(`${op}(${JSON.stringify(value)}, ${JSON.stringify(target)}) === ${expected}`, () => {
      expect(opMatch(op, value, target)).toBe(expected);
    });
  }
});
