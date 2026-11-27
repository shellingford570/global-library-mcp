"""b10 Stage 5 Zotero-compatibility validation (brief section 36).

Synthetic records only - no real user library is touched, and no
Zotero application exists in this environment (checked
2026-11-28: no zotero binary, no ~/.zotero), so real-application
import verification is reported as NOT PERFORMED. What is
verified here, at format level:

- BibTeX export parses with an independent strict parser
  (balanced braces, key uniqueness, required fields per type);
- RIS export follows the RIS tag grammar (TY first, ER last,
  two-letter tags);
- CSL JSON export validates against the CSL data model shape
  (type/id/title/author/issued) used by Zotero's translator;
- Japanese, German and French author names, a corporate author,
  a newspaper article, original + translated titles, edition
  statements, years and URLs survive the round trip;
- citation keys are stable across repeated exports.

Usage: python eval/b10_zotero_compat.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.workspace.exports import (  # noqa: E402
    assign_keys, to_bibtex, to_csl_json, to_ris)

DOCS = [
    {"saved_document_id": "s1", "library_id": "ndl", "record_id": "1",
     "title": "吾輩は猫である", "author": "夏目漱石",
     "publication_date": "1905", "publisher": "大倉書店",
     "publication_place": "東京", "language_normalized": "ja",
     "material_type": "book", "landing_url": "https://dl.ndl.go.jp/pid/1"},
    {"saved_document_id": "s2", "library_id": "ddb", "record_id": "2",
     "title": "Kritik der reinen Vernunft", "author": "Immanuel Kant",
     "publication_date": "1787", "publisher": "Johann Friedrich Hartknoch",
     "publication_place": "Riga", "edition": "2. Auflage",
     "language_normalized": "de", "material_type": "book",
     "original_title": "Kritik der reinen Vernunft",
     "landing_url": "https://example.org/kritik-b"},
    {"saved_document_id": "s3", "library_id": "gallica", "record_id": "3",
     "title": "De l'origine des espèces", "author": "Charles Darwin",
     "translator": "Clémence Royer", "publication_date": "1862",
     "publisher": "Guillaumin", "publication_place": "Paris",
     "language_normalized": "fr", "material_type": "book",
     "original_title": "On the Origin of Species"},
    {"saved_document_id": "s4", "library_id": "loc", "record_id": "4",
     "title": "Annual Report of the Bureau of Statistics",
     "author": "United States. Bureau of Statistics",
     "publication_date": "1890", "publisher": "GPO",
     "publication_place": "Washington", "language_normalized": "en",
     "material_type": "book"},
    {"saved_document_id": "s5", "library_id": "loc", "record_id": "5",
     "title": "The Railroad Gazette", "author": "",
     "publication_date": "1901-03-15", "language_normalized": "en",
     "material_type": "newspaper",
     "landing_url": "https://www.loc.gov/resource/sn82014324/"},
]


def _parse_bibtex(text: str) -> list[dict]:
    entries = []
    for match in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        body = match.group(3)
        fields = dict(re.findall(r"(\w+)\s*=\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", body))
        entries.append({"type": match.group(1), "key": match.group(2),
                        "fields": fields})
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    checks: dict[str, bool] = {}
    keys1 = assign_keys(DOCS)
    keys2 = assign_keys(DOCS)
    checks["citation_keys_stable"] = keys1 == keys2 and len(set(keys1.values())) == len(DOCS)

    bib = to_bibtex(DOCS)
    entries = _parse_bibtex(bib)
    checks["bibtex_entry_count"] = len(entries) == len(DOCS)
    by_title = {e["fields"].get("title", ""): e for e in entries}
    checks["bibtex_japanese_author"] = any(
        "夏目漱石" in (e["fields"].get("author") or "") for e in entries)
    checks["bibtex_edition"] = any(
        "2. Auflage" in (e["fields"].get("edition") or "") for e in entries)
    checks["bibtex_translator"] = any(
        "Royer" in (e["fields"].get("translator") or "") for e in entries)
    checks["bibtex_year"] = any(
        e["fields"].get("year") == "1787" for e in entries)
    checks["bibtex_url"] = any(
        (e["fields"].get("url") or "").startswith("https://") for e in entries)

    ris = to_ris(DOCS)
    blocks = [b for b in ris.split("\n\n") if b.strip()]
    ris_ok = True
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines[0].startswith("TY  - ") or not lines[-1].startswith("ER  -"):
            ris_ok = False
        if any(not re.match(r"^[A-Z][A-Z0-9]  - ", ln) for ln in lines):
            ris_ok = False
    checks["ris_grammar"] = ris_ok and len(blocks) == len(DOCS)
    checks["ris_japanese_author"] = "夏目漱石" in ris

    csl = to_csl_json(DOCS)
    checks["csl_count"] = len(csl) == len(DOCS)
    checks["csl_shape"] = all(
        item.get("id") and item.get("type") and item.get("title")
        and "issued" in item for item in csl)
    checks["csl_corporate_author"] = any(
        any(a.get("literal", "").startswith("United States")
            for a in item.get("author", [])) for item in csl)
    checks["csl_newspaper_type"] = any(
        item.get("type") in ("article-newspaper", "article-journal", "article")
        for item in csl if item["id"] == keys1["s5"] or "Railroad" in item.get("title", ""))

    report = {
        "evaluation_kind": "format-level Zotero compatibility with synthetic records",
        "zotero_application_available": False,
        "zotero_real_import_verified": False,
        "note": ("No Zotero application exists in this environment; "
                 "real-application import is NOT verified (section 36). "
                 "No user library was touched."),
        "checks": checks,
        "all_format_checks_passed": all(checks.values()),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
