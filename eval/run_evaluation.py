"""Live answer-quality evaluation for Global Library MCP.

Runs the research pipeline over eval/questions.json against the real
NDL APIs and records what actually happened: discovery, OCR capture,
citation resolution, claim support screening, insufficient-evidence
behaviour, timing and request counts.

The default provider is the deterministic MockProvider: this measures
the pipeline and the claim checker, NOT the prose quality of a real
LLM. Real-LLM evaluation requires an operator-approved API key
(LLM_ENABLED=true etc.) and is reported separately when run.

Usage:
    python eval/run_evaluation.py [--limit N] [--out PATH] [--image-checks N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from global_library_mcp.answer import MockProvider, OpenAICompatibleProvider  # noqa: E402
from global_library_mcp.service import LibraryService  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class RequestCounter:
    """Counts requests via httpx event hooks.

    A custom transport must not be substituted for the default one:
    doing so bypasses httpx's environment proxy handling and every
    request fails instantly in proxied environments (this bug produced
    a bogus all-insufficient first run; the hook approach avoids it).
    """

    def __init__(self):
        self.count = 0

    async def __call__(self, request):
        self.count += 1


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results-phase4.json")
    parser.add_argument("--image-checks", type=int, default=10, help="max questions whose first evidence page gets a full IIIF verify")
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval" / "questions.json")
    parser.add_argument("--max-calls", type=int, default=0, help="stop starting new questions once this many HTTP requests were made (0 = no cap)")
    parser.add_argument("--provider", choices=("mock", "openai"), default="mock",
                        help="answer provider; 'openai' is the real-LLM path and must go through eval/real_llm_run.py's budget guard")
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    questions = dataset["questions"][: args.limit or None]
    counter = RequestCounter()
    records = []
    image_checks_done = 0
    async with httpx.AsyncClient(timeout=40, event_hooks={"request": [counter]}, headers={"User-Agent": "global-library-mcp/0.1 (evaluation)"}) as client:
        service = LibraryService(client)
        for item in questions:
            if args.max_calls and counter.count >= args.max_calls:
                records.append({"id": item["id"], "category": item["category"], "question": item["question"],
                                "expect": item["expect"], "status": "skipped_cap", "seconds": 0, "requests": 0})
                continue
            started = time.perf_counter()
            before = counter.count
            record = {"id": item["id"], "category": item["category"], "question": item["question"], "expect": item["expect"]}
            try:
                provider = MockProvider() if args.provider == "mock" else OpenAICompatibleProvider(client)
                result = await service.answer(item["question"], libraries=["ndl"], limit=5, provider=provider)
                record["status"] = result["status"]
                record["evidence"] = len(result.get("evidence", []))
                record["unverified"] = len(result.get("unverified", []))
                record["citations"] = [c["citation_key"] for c in result.get("citations", [])]
                record["related"] = len(result.get("related", []))
                record["related_statuses"] = [(r.get("relevance") or {}).get("status") for r in result.get("related", [])]
                record["reason"] = result.get("reason")
                record["claims"] = [{"support": c.get("support"), "overlap": c.get("overlap")} for c in result.get("claims", [])]
                evidence_keys = {e["citation_key"] for e in result.get("evidence", [])}
                evidence_keys |= {p["citation_key"] for p in result.get("premise_contradictions", [])}
                record["citations_resolve"] = all(k in evidence_keys for k in record["citations"])
                record["search_errors"] = (result.get("search") or {}).get("errors", [])
                retrieval = result.get("retrieval") or {}
                record["first_evidence_rank"] = retrieval.get("first_evidence_rank")
                record["retrieval_failure_reason"] = retrieval.get("failure_reason")
                record["premise_contradictions"] = len(result.get("premise_contradictions", []))
                record["correction_quotes"] = (result.get("correction") or {}).get("quotes", [])
                if result.get("evidence") and image_checks_done < args.image_checks:
                    first = result["evidence"][0]
                    report = await service.verify_page(first["library_id"], first["page_id"])
                    record["image_check"] = {"page_id": first["page_id"], "status": report.get("status"),
                                             "image_reachable": (report.get("checks") or {}).get("image_reachable", {}).get("ok")}
                    image_checks_done += 1
            except Exception as exc:  # noqa: BLE001 - recorded per question
                record["status"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["seconds"] = round(time.perf_counter() - started, 2)
            record["requests"] = counter.count - before
            records.append(record)
            print(f"{record['id']} [{record['category']}] -> {record['status']} ev={record.get('evidence', 0)} "
                  f"claims={len(record.get('claims', []))} {record['seconds']}s req={record['requests']}")
            await asyncio.sleep(0.25)

    expect_evidence = [r for r in records if r["expect"] == "evidence"]
    expect_insufficient = [r for r in records if r["expect"] == "insufficient"]
    expect_correction = [r for r in records if r["expect"] == "correction"]
    ranks = [r.get("first_evidence_rank") for r in expect_evidence]
    all_claims = [c for r in records for c in r.get("claims", [])]
    page_attempts = sum(r.get("evidence", 0) + r.get("unverified", 0) for r in records)
    image_records = [r["image_check"] for r in records if r.get("image_check")]
    metrics = {
        "questions": len(records),
        "discovery_rate": round(sum(1 for r in expect_evidence if r.get("evidence", 0) > 0) / max(len(expect_evidence), 1), 3),
        "ocr_capture_rate": round(sum(r.get("evidence", 0) for r in records) / max(page_attempts, 1), 3),
        "image_reachable_rate": round(sum(1 for c in image_records if c.get("image_reachable")) / max(len(image_records), 1), 3) if image_records else None,
        "citation_resolution_rate": round(sum(1 for r in records if r.get("citations_resolve", True)) / max(len(records), 1), 3),
        "claim_supported_rate": round(sum(1 for c in all_claims if c["support"] == "supported") / max(len(all_claims), 1), 3) if all_claims else None,
        "claim_status_counts": {s: sum(1 for c in all_claims if c["support"] == s) for s in ("supported", "uncertain", "unsupported", "conflicting", "not_checked")},
        "insufficient_correct_rate": round(sum(1 for r in expect_insufficient if r["status"] == "insufficient_evidence") / max(len(expect_insufficient), 1), 3),
        "refusal_correct_rate": round(sum(1 for r in expect_insufficient if r["status"] in ("insufficient_evidence", "answer_withheld")) / max(len(expect_insufficient), 1), 3),
        "answerable_success_rate": round(sum(1 for r in expect_evidence if r["status"] in ("answered", "answered_partial")) / max(len(expect_evidence), 1), 3),
        "partial_answer_rate": round(sum(1 for r in records if r["status"] == "answered_partial") / max(len(records), 1), 3),
        "false_answer_rate": round(sum(1 for r in expect_insufficient if r["status"] in ("answered", "answered_partial")) / max(len(expect_insufficient), 1), 3),
        "false_refusal_rate": round(sum(1 for r in expect_evidence if r["status"] in ("insufficient_evidence", "answer_withheld")) / max(len(expect_evidence), 1), 3),
        "related_status_counts": {s: sum(1 for r in records for st in r.get("related_statuses", []) if st == s) for s in ("relevant", "partially_relevant", "irrelevant", "uncertain", "not_checked")},
        "requests_per_question": round(counter.count / max(len(records), 1), 1),
        "avg_seconds": round(sum(r["seconds"] for r in records) / max(len(records), 1), 2),
        "total_requests": counter.count,
        "provider": "mock" if args.provider == "mock" else f"openai-compatible:{__import__('os').getenv('LLM_MODEL', 'gpt-4o-mini')}",
        "insufficient_handled_rate": round(sum(1 for r in expect_insufficient if r["status"] in ("insufficient_evidence", "answer_withheld", "corrected_premise")) / max(len(expect_insufficient), 1), 3),
        "corrections_on_insufficient": sum(1 for r in expect_insufficient if r["status"] == "corrected_premise"),
        "false_corrections": sum(1 for r in expect_evidence if r["status"] == "corrected_premise"),
        "correction_success_rate": round(sum(1 for r in expect_correction if r["status"] == "corrected_premise") / max(len(expect_correction), 1), 3) if expect_correction else None,
        "correction_safe_rate": round(sum(1 for r in expect_correction if r["status"] in ("corrected_premise", "insufficient_evidence")) / max(len(expect_correction), 1), 3) if expect_correction else None,
        "correction_false_answer_rate": round(sum(1 for r in expect_correction if r["status"] in ("answered", "answered_partial")) / max(len(expect_correction), 1), 3) if expect_correction else None,
        "recall_at_3": round(sum(1 for rank in ranks if rank is not None and rank <= 3) / max(len(ranks), 1), 3) if ranks else None,
        "recall_at_6": round(sum(1 for rank in ranks if rank is not None and rank <= 6) / max(len(ranks), 1), 3) if ranks else None,
        "mrr": round(sum(1.0 / rank for rank in ranks if rank) / max(len(ranks), 1), 3) if ranks else None,
        "retrieval_failure_counts": {reason: sum(1 for r in records if r.get("retrieval_failure_reason") == reason) for reason in ("no_candidates", "budget_exhausted", "no_relevant_pages", "premise_contradicted", "all_pages_failed_verification")},
    }
    payload = {"dataset_version": dataset["version"], "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "metrics": metrics, "records": records}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
