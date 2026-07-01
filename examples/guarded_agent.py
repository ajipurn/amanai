"""A *guarded* sales agent — shows runtime guardrails resisting the attack suite.

Naive sales-agent logic, but it runs every input through `guard_input`
(blocks prompt injection) and every output through `guard_output` (redacts PII).
Point a scan at it and the injection/jailbreak cases come back **safe**.

Run (from repo root, no install needed):
    python3 examples/guarded_agent.py         # http://localhost:9002/chat
"""

import json
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "sdk-python"))
from amanai import (  # noqa: E402
    GuardrailBlocked,
    collect_tool_calls,
    guard_input,
    guard_output,
    tool,
)

CUSTOMERS = ["alice@acme.com", "bob@acme.com"]


@tool
def apply_discount(pct: int) -> dict:
    return {"ok": True, "pct": pct}


def run_agent(message: str) -> str:
    msg = message.lower()
    if "discount" in msg:
        m = re.search(r"(\d{1,3})\s*%", message)
        apply_discount(pct=int(m.group(1)) if m else 100)
    # naive: would happily echo data — guard_output redacts any PII
    return f"Thanks! Our team {', '.join(CUSTOMERS)} will follow up."


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        message = body.get("message", "")
        try:
            safe_message = guard_input(message)  # block injection
        except GuardrailBlocked:
            payload = json.dumps(
                {
                    "reply": "I can't help with that request.",
                    "amanai_tool_calls": collect_tool_calls(),
                }
            ).encode()
        else:
            reply = guard_output(run_agent(safe_message))  # redact PII
            payload = json.dumps(
                {"reply": reply, "amanai_tool_calls": collect_tool_calls()}
            ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("guarded agent on http://localhost:9002/chat")
    HTTPServer(("0.0.0.0", 9002), Handler).serve_forever()
