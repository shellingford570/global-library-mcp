from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys: a duplicated
    key in libraries.yaml previously let a stale entry silently
    override the curated one (b5, section 9)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ValueError(f"duplicate key in registry YAML: {key!r} (line {key_node.start_mark.line + 1})")
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        document = yaml.load(self.path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader) or {}
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
            "implementation_status": entry.get("implementation_status", "research_only"),
            "capability_status": entry.get("capability_status", {}),
            "region": entry.get("region"),
            "country": entry.get("country"),
            "languages": entry.get("languages", []),
            "material_types": entry.get("material_types", []),
        }
