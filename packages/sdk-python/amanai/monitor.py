"""Send production traces to Amanai for continuous security monitoring.

Stdlib only (urllib) — keeps the SDK dependency-free. Opt-in: unlike the local
guardrails, this makes a network call to your Amanai instance.

It ships `TraceEvent`s (action + decision + status) and redacts PII/secrets
first, so monitoring never creates new exposure.

    from amanai import Monitor, collect_trace

    mon = Monitor("http://localhost:8000", PUBLIC_KEY, SECRET_KEY)
    mon.log_trace(collect_trace(), user_id="u123", session_id="s456")
    # -> {"trace_id": ..., "flagged": true, "alerts": [...]}
"""

import base64
import json
import urllib.request

from amanai.guardrails import redact_pii


def _redact(obj):
    """Recursively redact PII/secrets from any string in a JSON-able structure."""
    if isinstance(obj, str):
        return redact_pii(obj)
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


class Monitor:
    def __init__(self, base_url: str, public_key: str, secret_key: str):
        self.endpoint = base_url.rstrip("/") + "/api/public/traces"
        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self._auth = f"Basic {token}"

    def _post(self, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"content-type": "application/json", "authorization": self._auth},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode())

    def log_trace(
        self,
        events,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        redact: bool = True,
        timeout: float = 10.0,
    ) -> dict:
        """Send canonical trace events (the Action Policy Engine's evidence)."""
        serialized = [e.to_dict() for e in events]
        if redact:
            serialized = _redact(serialized)
        return self._post(
            {"events": serialized, "user_id": user_id, "session_id": session_id}, timeout
        )
