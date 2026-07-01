"""Red-team pack — a curated static attack corpus + a runner.

A regression harness, not an exhaustive attack library: it proves the built-in
guardrails still catch the patterns they claim, and lets you point a runner at your
own agent to see which known attacks get through. For breadth (adaptive/generative
attacks) reach for DeepTeam or Garak — this stays small, deterministic, and
dependency-free.

    from amanai import load_pack, run_pack
    report = run_pack(load_pack())          # against the built-in guardrails
    assert report.passed                    # no regressions

    report = run_pack(load_pack("tool_abuse"), target=my_agent)   # end-to-end
"""

from __future__ import annotations

import importlib.resources as resources
import json
from dataclasses import asdict, dataclass, field

from amanai.guardrails import detect_injection, detect_pii
from amanai.judge import run_detector

# Corpus files, in a deterministic load order.
CATEGORIES = (
    "prompt_injection",
    "jailbreak",
    "system_prompt_leak",
    "pii_exfil",
    "tool_abuse",
    "controls",
)


@dataclass(frozen=True)
class CaseResult:
    id: str
    category: str
    passed: bool
    outcome: str  # blocked | allowed | safe | vulnerable | inconclusive | skipped
    reason: str
    owasp: dict = field(default_factory=dict)


@dataclass
class Report:
    results: list

    @property
    def failed(self) -> list:
        return [r for r in self.results if not r.passed]

    @property
    def passed(self) -> bool:
        """True when no case regressed. Inconclusive cases do not fail the gate."""
        return not self.failed

    def owasp_summary(self) -> dict:
        """{framework_id: {"cases": n, "passed": m}} aggregated from case tags."""
        summary: dict = {}
        for r in self.results:
            for framework in ("llm", "asi"):
                for cid in r.owasp.get(framework, []):
                    slot = summary.setdefault(cid, {"cases": 0, "passed": 0})
                    slot["cases"] += 1
                    if r.passed:
                        slot["passed"] += 1
        return summary

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "results": [asdict(r) for r in self.results],
            "owasp": self.owasp_summary(),
        }


def _corpus_dir():
    return resources.files("amanai.redteam").joinpath("corpus")


def load_pack(name: str | None = None) -> list[dict]:
    """Load one corpus category by name, or every case when `name` is None. Reads
    via `importlib.resources`, so it works from an installed wheel."""
    corpus = _corpus_dir()
    if name:
        return json.loads(corpus.joinpath(f"{name}.json").read_text())
    cases: list[dict] = []
    for category in CATEGORIES:
        cases.extend(json.loads(corpus.joinpath(f"{category}.json").read_text()))
    return cases


def _run_case(case: dict, target, gateway) -> CaseResult:
    cid, category = case["id"], case.get("category", "")
    owasp = case.get("owasp", {})
    exp = case.get("expect", {})

    if "guard" in exp:
        # Built-in guardrail check: injection categories use detect_injection,
        # pii_exfil uses detect_pii.
        if category == "pii_exfil":
            flagged, detector = bool(detect_pii(case["input"])), "detect_pii"
        else:
            flagged, detector = bool(detect_injection(case["input"])), "detect_injection"
        want_block = exp["guard"] == "block"
        outcome = "blocked" if flagged else "allowed"
        reason = f"{detector}: {'flagged' if flagged else 'clean'} (want {exp['guard']})"
        return CaseResult(cid, category, flagged == want_block, outcome, reason, owasp)

    if "detector" in exp:
        # End-to-end: needs a target agent. Without one, inconclusive (not a fail).
        if target is None:
            return CaseResult(
                cid, category, True, "inconclusive", "no target: end-to-end case skipped", owasp
            )
        out = target(case["input"]) or {}
        status, reason = run_detector(
            exp["detector"], case["input"], out.get("response", ""), gateway, out.get("tool_calls")
        )
        # vulnerable == attack succeeded == the case failed.
        return CaseResult(cid, category, status != "vulnerable", status, reason, owasp)

    return CaseResult(cid, category, True, "skipped", "no expect clause", owasp)


def run_pack(cases: list[dict], *, target=None, gateway=None) -> Report:
    """Evaluate each case against the target (built-in guardrails when `target` is
    None) and compare to its `expect`. Returns a `Report`."""
    return Report([_run_case(case, target, gateway) for case in cases])
