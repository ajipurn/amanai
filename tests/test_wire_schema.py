"""Wire-format contract: what the SDK emits must match spec/wire/*.schema.json.

The schema is the public contract a trace consumer (CI, a server) codes against.
This test is hand-rolled (no jsonschema dependency): it compares the emitted
shape — key sets, status/outcome enums, id/ts formats — against the schema file,
so either side drifting fails the build."""

import json
import re
from pathlib import Path

from amanai import OUTCOMES, collect_trace, set_policy, tool

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "wire" / "trace-event.v1.schema.json")
    .read_text()
)
DEFS = SCHEMA["$defs"]

# Every status the engine can record (keep in sync with TraceEvent's docstring).
ENGINE_STATUSES = {"executed", "blocked", "shadowed", "pending", "evaluated", "error", "approved"}


def _emit_event() -> dict:
    set_policy([{"id": "d", "tool": "act", "args": [{"arg": "n", "op": ">=", "value": 100}]}])

    @tool
    def act(n):
        return n

    act(n=1)
    return collect_trace()[0].to_dict()


def test_emitted_event_matches_schema_shape():
    d = _emit_event()
    assert set(d) == set(DEFS["traceEvent"]["required"])
    assert set(d["action"]) == set(DEFS["action"]["required"])
    assert set(d["decision"]) == set(DEFS["decision"]["required"])


def test_enums_match_engine():
    assert set(DEFS["traceEvent"]["properties"]["status"]["enum"]) == ENGINE_STATUSES
    assert set(DEFS["decision"]["properties"]["outcome"]["enum"]) == set(OUTCOMES)


def test_id_and_ts_match_schema_formats():
    d = _emit_event()
    assert re.fullmatch(DEFS["traceEvent"]["properties"]["id"]["pattern"], d["id"])
    assert d["ts"].endswith("Z")
    assert re.fullmatch(
        DEFS["decision"]["properties"]["policy_digest"]["pattern"], d["decision"]["policy_digest"]
    )
