"""`amanai` command-line interface — use the engine from a terminal or CI.

A thin argparse front end over the SDK. It owns argument parsing, output
formatting, and exit codes; every subcommand delegates to an existing engine
function (no policy logic lives here).

Exit codes (uniform):
    0  success / no findings / clean
    1  findings or violations (policy error, lint error, trace violation, vulnerable MCP)
    2  usage error (bad args, missing file)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from amanai.judge import run_mcp_check
from amanai.linter import lint_policy
from amanai.policy import (
    ActionRequest,
    PolicyError,
    evaluate,
    load_policy,
    load_trace,
    set_policy,
)
from amanai.redteam import load_pack, run_pack
from amanai.testing import assert_no_violations

_MCP_CHECKS = ("tool_poisoning", "dangerous_capability", "missing_schema")


# ── helpers ───────────────────────────────────────────────────────────────────
def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def _require_file(path: str) -> bool:
    if not Path(path).exists():
        _err(f"file not found: {path}")
        return False
    return True


def _parse_kv(pairs) -> dict:
    """`k=v` items → dict, parsing each value as JSON with a string fallback so
    `pct=90`→int, `flag=true`→bool, `role=support`→str."""
    out: dict = {}
    for item in pairs or []:
        key, sep, val = item.partition("=")
        if not sep:
            raise ValueError(f"expected key=value, got {item!r}")
        try:
            out[key] = json.loads(val)
        except json.JSONDecodeError:
            out[key] = val
    return out


# ── subcommands ───────────────────────────────────────────────────────────────
def _cmd_validate(args) -> int:
    if not _require_file(args.policy):
        return 2
    try:
        policy = load_policy(args.policy, require_ids=args.require_ids)
    except PolicyError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            _err(str(e))
        return 1
    if args.json:
        print(json.dumps({"ok": True, "rules": len(policy.rules)}))
    else:
        print(f"ok: {len(policy.rules)} rule(s) valid")
    return 0


def _cmd_lint(args) -> int:
    if not _require_file(args.policy):
        return 2
    try:
        findings = lint_policy(args.policy)
    except PolicyError as e:
        _err(str(e))
        return 1
    if args.json:
        print(json.dumps([f.to_dict() for f in findings]))
    else:
        for f in findings:
            ids = ", ".join(f.rule_ids)
            print(f"{f.severity:5} {f.code}: {f.message}" + (f"  [{ids}]" if ids else ""))
        if not findings:
            print("ok: no findings")
    gate = any(f.severity == "error" for f in findings) or (
        args.strict and any(f.severity == "warn" for f in findings)
    )
    return 1 if gate else 0


def _cmd_test(args) -> int:
    if not (_require_file(args.policy) and _require_file(args.trace)):
        return 2
    try:
        set_policy(load_policy(args.policy))
        events = load_trace(args.trace)
    except PolicyError as e:
        _err(str(e))
        return 1
    try:
        assert_no_violations(events)
    except AssertionError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            _err(str(e))
        return 1
    if args.json:
        print(json.dumps({"ok": True, "events": len(events)}))
    else:
        print(f"ok: no violations in {len(events)} event(s)")
    return 0


def _cmd_check_mcp(args) -> int:
    if not _require_file(args.tools):
        return 2
    try:
        tools = json.loads(Path(args.tools).read_text())
    except json.JSONDecodeError as e:
        _err(f"invalid tools JSON: {e}")
        return 1
    if not isinstance(tools, list):
        _err("tools file must be a JSON list of tool definitions")
        return 1
    checks = [args.check] if args.check else list(_MCP_CHECKS)
    results, vulnerable = [], False
    for c in checks:
        status, reason = run_mcp_check({"check": c}, tools)
        results.append({"check": c, "status": status, "reason": reason})
        if status == "vulnerable":
            vulnerable = True
    if args.json:
        print(json.dumps(results))
    else:
        for r in results:
            print(f"{r['status']:12} {r['check']}: {r['reason']}")
    return 1 if vulnerable else 0


def _cmd_explain(args) -> int:
    if not _require_file(args.policy):
        return 2
    try:
        policy = load_policy(args.policy)
        action = ActionRequest(
            args.tool,
            _parse_kv(args.arg),
            capability=args.capability,
            context=_parse_kv(args.ctx),
        )
    except (PolicyError, ValueError) as e:
        _err(str(e))
        return 2
    decision = evaluate(action, policy)
    if args.json:
        print(json.dumps(decision.to_dict()))
    else:
        print(f"{decision.outcome}  rule={decision.rule_id}  reason={decision.reason}")
    return 0


def _import_target(spec: str):
    """`pkg.module:function` → the callable, for end-to-end redteam runs."""
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"target must be 'module:function', got {spec!r}")
    return getattr(importlib.import_module(module_name), attr)


def _cmd_redteam(args) -> int:
    try:
        cases = load_pack(args.pack)
    except (FileNotFoundError, OSError) as e:
        _err(f"unknown pack {args.pack!r}: {e}")
        return 2
    target = None
    if args.target:
        try:
            target = _import_target(args.target)
        except (ImportError, AttributeError, ValueError) as e:
            _err(f"cannot import target {args.target!r}: {e}")
            return 2
    report = run_pack(cases, target=target)
    if args.json:
        print(json.dumps(report.to_dict()))
    else:
        for r in report.results:
            mark = "PASS" if r.passed else "FAIL"
            print(f"{mark} {r.id} [{r.category}] {r.outcome}: {r.reason}")
        print(f"\n{len(report.results) - len(report.failed)}/{len(report.results)} passed")
    return 1 if report.failed else 0


_HANDLERS = {
    "validate": _cmd_validate,
    "lint": _cmd_lint,
    "test": _cmd_test,
    "check-mcp": _cmd_check_mcp,
    "explain": _cmd_explain,
    "redteam": _cmd_redteam,
}


# ── parser ────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amanai", description="Action Policy Engine CLI")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("validate", parents=[common], help="structurally validate a policy")
    p.add_argument("policy")
    p.add_argument("--require-ids", action="store_true", help="reject rules without an id")

    p = sub.add_parser("lint", parents=[common], help="semantically lint a policy")
    p.add_argument("policy")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")

    p = sub.add_parser("test", parents=[common], help="assert a recorded trace against a policy")
    p.add_argument("policy")
    p.add_argument("trace")

    p = sub.add_parser("check-mcp", parents=[common], help="static checks on MCP tool definitions")
    p.add_argument("tools")
    p.add_argument("--check", choices=_MCP_CHECKS, help="run one check (default: all)")

    p = sub.add_parser("explain", parents=[common], help="evaluate one hypothetical action")
    p.add_argument("policy")
    p.add_argument("--tool", required=True)
    p.add_argument("--capability")
    p.add_argument("--arg", action="append", metavar="K=V", help="action argument (repeatable)")
    p.add_argument("--ctx", action="append", metavar="K=V", help="context value (repeatable)")

    p = sub.add_parser("redteam", parents=[common], help="run the attack corpus for regressions")
    p.add_argument("--pack", help="one category (default: all)")
    p.add_argument("--target", metavar="MOD:FN", help="agent callable for end-to-end cases")

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits on -h or bad args; surface the code
        return int(e.code or 0)
    if not args.cmd:
        parser.print_help()
        return 2
    return _HANDLERS[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
