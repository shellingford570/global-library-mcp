from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        document = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.entries: dict[str, dict[str, Any]] = {
            item["id"]: item for item in document.get("libraries", []) if item.get("id")
        }

    def list(self) -> list[dict[str, Any]]:
        return list(self.entries.values())

    def get(self, library_id: str) -> dict[str, Any] | None:
        return self.entries.get(library_id)

    def capabilities(self, library_id: str) -> dict[str, Any]:
        entry = self.get(library_id)
        if not entry:
            raise KeyError(f"Unknown library: {library_id}")
        return {
            "id": library_id,
            "name": entry.get("name", library_id),
            "official_site": entry.get("official_site"),
            "capabilities": entry.get("capabilities", {}),
            "standards": entry.get("standards", "unknown"),
            "auth": entry.get("auth", "unknown"),
            "terms_rights": entry.get("terms_rights", "unknown"),
            "rate_limits": entry.get("rate_limits", "unknown"),
            "verification": entry.get("verification", "unknown"),
            "last_verified": entry.get("last_verified", "unknown"),
        }
