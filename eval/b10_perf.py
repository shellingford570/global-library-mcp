"""b10 performance measurements (brief section 45).

Local components only, on this machine, with the fixture
service-evaluation numbers referenced from their own result
files. Reports medians over repeated runs. Nothing here is a
guarantee about other hardware.

Usage: python eval/b10_perf.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.discovery import analyze_discovery_query  # noqa: E402
from global_library_mcp.expansion import QueryExpansionEngine  # noqa: E402
from global_library_mcp.lexical import LexicalScorer  # noqa: E402
from global_library_mcp.question import analyze_question  # noqa: E402
from global_library_mcp.research import (  # noqa: E402
    assess_claim_evidence, compare_facts, structure_claim,
    structure_question)
from global_library_mcp.research_ranker import ResearchRanker  # noqa: E402
from types import SimpleNamespace  # noqa: E402


def _median_ms(fn, runs=30):
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(samples), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    query = "19世紀ドイツの蒸気機関と水力発電"
    items = [SimpleNamespace(
        title=f"Die Dampfmaschine Band {i}", author="Friedrich Müller",
        subjects=["Dampfmaschine", "Industrie"], description="",
        language="de", ocr=bool(i % 2), record_id=f"ddb:{i}",
        library_id="ddb", year=1850, material_type="book", work_id=None)
        for i in range(30)]
    analysis = analyze_discovery_query(query)
    claim = structure_claim("明治時代の日本で水力発電所が建設された")
    candidates = [{"document_id": "d", "admitted": True,
                   "text": "明治25年、日本において水力発電所が建設された。"}]
    facts = [{"value": 120, "unit": "kw", "document_id": "a", "work_id": "w1"},
             {"value": 150, "unit": "kw", "document_id": "b", "work_id": "w2"}]
    docs = [f"Die Dampfmaschine und ihre Anwendung {i}" for i in range(30)]
    report = {
        "measurement_kind": "local component medians (this VM, 1.5 shared CPUs)",
        "question_analysis_ms": _median_ms(lambda: analyze_question(query)),
        "discovery_analysis_ms": _median_ms(lambda: analyze_discovery_query(query)),
        "expansion_plan_ms": _median_ms(
            lambda: QueryExpansionEngine().expand(analysis, mode="standard")),
        "lexical_fit_and_score_30_docs_ms": _median_ms(
            lambda: LexicalScorer(docs).score("Dampfmaschine")),
        "research_ranker_30_items_ms": _median_ms(
            lambda: ResearchRanker().rank(analysis, list(items), {})),
        "structure_question_ms": _median_ms(lambda: structure_question(query)),
        "structure_claim_ms": _median_ms(
            lambda: structure_claim("明治時代の日本で水力発電所が建設された")),
        "assess_claim_evidence_ms": _median_ms(
            lambda: assess_claim_evidence(claim, candidates)),
        "compare_facts_ms": _median_ms(lambda: compare_facts(facts)),
        "notes": {
            "semantic_model": "load 2.77 s, encode ~12 ms/text (docs/b10-model-card.md)",
            "service_fixture_eval": "eval/results-b10-service-after-stage3.json "
                                    "(quick 11.7 s / standard 15.3 s mean per case over fixture transport; "
                                    "these are fixture-environment timings, not live network timings)",
        },
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
