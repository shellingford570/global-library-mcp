"""Generate a CycloneDX SBOM for the installed environment.

Usage: python scripts/generate_sbom.py [output-path]

The SBOM reflects the environment the script runs in (the project
venv, including test dependencies when installed with [test]).
Component versions come from importlib.metadata, never from guesses.
"""
from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sbom.cyclonedx.json"
    components = []
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = dist.metadata["Name"]
        if not name:
            continue
        components.append({
            "type": "library",
            "name": name,
            "version": dist.version,
            "purl": f"pkg:pypi/{name.lower()}@{dist.version}",
        })
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "global-library-mcp"}},
        "components": components,
    }
    out.write_text(json.dumps(sbom, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} with {len(components)} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
