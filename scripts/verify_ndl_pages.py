"""Live verification of NDL pages against their IIIF originals.

Usage:
    python scripts/verify_ndl_pages.py [--save PATH] [PAGE_ID ...]

Defaults to the three reference pages from the project brief. Makes a
small number of requests to the official NDL APIs only. Exits non-zero
if any page does not reach status "verified".
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.service import LibraryService  # noqa: E402

DEFAULT_PAGES = ["994120_50", "1018770_21", "1886468_121"]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", nargs="*", default=DEFAULT_PAGES)
    parser.add_argument("--save", type=Path, default=None)
    args = parser.parse_args()
    reports = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "global-library-mcp/0.1 (live verification)"}) as client:
        service = LibraryService(client)
        for page_id in args.pages:
            report = await service.verify_page("ndl", page_id)
            reports.append(report)
            print(f"{page_id}: {report['status']}")
            for name, check in report.get("checks", {}).items():
                print(f"  {name}: {'OK' if check['ok'] else 'FAIL'} - {check['detail']}")
    if args.save:
        args.save.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {args.save}")
    return 0 if all(r["status"] == "verified" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
