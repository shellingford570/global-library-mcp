"""External audit log (b9 brief section 26).

Append-only JSONL with size-based rotation. Records WHO (a
one-way pseudonym), WHAT tool, WHICH library, and the outcome
counters - never search terms, OCR text, excerpts, notes,
tokens, cookies or upstream raw responses, so the log cannot
be used to reconstruct a user's research topics beyond the
library level.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from global_library_mcp.external.control import pseudonym

MAX_LOG_BYTES = 5 * 1024 * 1024
RETENTION_NOTE = ("rotate at 5 MiB to a single .1 file; delete by "
                  "removing the log file - no other copies are kept")


class AuditLog:
    def __init__(self, path: str = ""):
        self.path = path
        self.events: list[dict[str, Any]] = []   # in-memory mirror for tests

    def record(self, *, user_id: str, tool: str, library_id: str = "",
               status: str = "ok", auth: str = "ok", http_attempts: int = 0,
               response_bytes: int = 0, rights_category: str = "",
               denials: int = 0, duration_ms: int = 0,
               cancelled: bool = False, limit_hit: str = "",
               error_class: str = "") -> dict[str, Any]:
        event = {
            "event_id": uuid.uuid4().hex,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": pseudonym(user_id),
            "tool": tool,
            "library_id": library_id,
            "status": status,
            "auth": auth,
            "http_attempts": int(http_attempts),
            "response_bytes": int(response_bytes),
            "rights_category": rights_category,
            "denials": int(denials),
            "duration_ms": int(duration_ms),
            "cancelled": bool(cancelled),
            "limit_hit": limit_hit,
            "error_class": error_class,
        }
        self.events.append(event)
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
