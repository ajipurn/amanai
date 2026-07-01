# amanai (TypeScript)

The Action Policy Engine for AI agents — policy-as-code for tool-calls, in
TypeScript. Loads the **same policy JSON** and returns the **same decisions** as
the [Python SDK](../sdk-python) (guaranteed by shared parity vectors). Zero runtime
dependencies.

> v1 ports the **core engine** (policy loading, operators, `evaluate`, `tool`,
> trace collection, `guardToolCall`). Guardrails, the offline judge, and the
> monitor are Python-only for now.

## Install

```bash
npm install @amanai/sdk
```

## Use

```ts
import { loadPolicy, setPolicy, setMode, tool, ToolBlocked, runWithContext } from "@amanai/sdk";

runWithContext(() => {
  setPolicy(loadPolicy([
    { id: "discount-cap", tool: "apply_discount",
      args: [{ arg: "pct", op: ">=", value: 50 }], action: "block", reason: "too high" },
  ]));
  setMode("enforce");

  const applyDiscount = tool((args: { pct: number }) => `applied ${args.pct}%`, { name: "apply_discount" });
  applyDiscount({ pct: 90 });   // throws ToolBlocked
});
```

Gate a provider tool-call loop directly with `guardToolCall(name, args)`. Wrap a
request handler in `runWithContext(...)` for per-request isolation (the Node analog
of Python's contextvars).

## Cross-language parity

`spec/parity/vectors.json` at the repo root is executed by **both** this package's
test suite and the Python suite. If the two engines ever diverge on a vector, a
build fails — the same "one implementation, no drift" guarantee the Python SDK
holds internally, extended across languages.

## Develop

```bash
npm ci
npm run typecheck
npm test          # vitest, includes the parity vectors
npm run build     # tsup → ESM + CJS + d.ts
```
