"""External audit log (b9 brief section 26; final-review
rework).

Append-only JSONL with size-based rotation. Records WHO (an
HMAC pseudonym - keyed, so the pseudonym cannot be reversed
by dictionary attack against known user ids; the key is
operator-managed and never logged), WHAT tool, WHICH library,
the outcome, the REAL upstream attempt/byte counters taken
from the send guard, the final response size, and denial /
cancellation / revocation events - never search terms, OCR
text, excerpts, notes, tokens, cookies or upstream raw
responses, so the log cannot be used to reconstruct a user's
research topics beyond the library level.

Capacity: the in-memory mirror keeps at most 1,000 events;
the file rotates at 5 MiB to a single .1 file, so on-disk
audit data is bounded at roughly 10 MiB per deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_MEMORY_EVENTS = 1_000
RETENTION_NOTE = ("rotate at 5 MiB to a single .1 file (about "
                  "10 MiB total); delete by removing the log "
                  "files - no other copies are kept")


class AuditLog:
    def __init__(self, path: str = "", hmac_key: str = ""):
        self.path = path
        self.events: list[dict[str, Any]] = []   # in-memory mirror for tests
        # Pseudonym key: the operator-managed secret when
        # configured; otherwise an ephemeral per-process key
        # (pseudonyms are then stable only within the process -
        # recorded honestly in the doctor output).
        self._key = hmac_key.encode("utf-8") if hmac_key \
            else os.urandom(32)
        self.hmac_key_configured = bool(hmac_key)

    def pseudonym(self, user_id: str) -> str:
        digest = hmac.new(self._key, user_id.encode("utf-8"),
                          hashlib.sha256).hexdigest()
        return "u_" + digest[:16]

    def record(self, *, user_id: str, tool: str, library_id: str = "",
               status: str = "ok", auth: str = "ok", http_attempts: int = 0,
               bytes_received: int = 0, response_bytes: int = 0,
               response_bytes_basis: str = "",
               rights_category: str = "",
               denials: int = 0, duration_ms: int = 0,
               cancelled: bool = False, limit_hit: str = "",
               error_class: str = "") -> dict[str, Any]:
        event = {
            "event_id": uuid.uuid4().hex,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": self.pseudonym(user_id),
            "tool": tool,
            "library_id": library_id,
            "status": status,
            "auth": auth,
            "http_attempts": int(http_attempts),
            "bytes_received": int(bytes_received),
            "response_bytes": int(response_bytes),
            # b10 4.11: WHAT the byte count measures. The tool
            # layer can only measure its projected payload; the
            # SDK then wraps it (the payload travels twice in
            # the final MCP response), so the two numbers are
            # recorded as distinct quantities, never conflated.
            "response_bytes_basis": response_bytes_basis,
            "rights_category": rights_category,
            "denials": int(denials),
            "duration_ms": int(duration_ms),
            "cancelled": bool(cancelled),
            "limit_hit": limit_hit,
            "error_class": error_class,
        }
        self.events.append(event)
        if len(self.events) > MAX_MEMORY_EVENTS:
            del self.events[: len(self.events) - MAX_MEMORY_EVENTS]
        if self.path:
            self._append(event)
        return event

    def _append(self, event: dict[str, Any]) -> None:
        try:
            if os.path.exists(self.path) \
                    and os.path.getsize(self.path) > MAX_LOG_BYTES:
                os.replace(self.path, self.path + ".1")
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass  # auditing must never break the request path
