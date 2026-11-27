"""b10 Stage 6 scenario evaluation A-L (brief section 40).

Each scenario is labelled by evidence kind: fixture (fixed
corpora / fixture transports), simulation, or live. Live checks
are run separately (eval/b10_live_check.py) because they depend
on the network; this script covers everything decidable offline
and reads the Stage 2-5 result files where a scenario was
already measured there.

Usage: python eval/b10_scenarios.py --out results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))
from global_library_mcp import service as _LS  # noqa: F401,E402
from global_library_mcp.authority import AuthorityResolver, identify_edition  # noqa: E402
from global_library_mcp.compare import concept_overlap  # noqa: E402
from global_library_mcp.research import structure_claim  # noqa: E402


def _load(name):
    path = ROOT / "eval" / name
    return json.loads(path.read_text()) if path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    resolver = AuthorityResolver()
    scenarios: dict[str, dict] = {}

    # A: original-work discovery (resolver + work identity).
    res = resolver.resolve_work("純粋理性批判")
    top = res.candidates[0] if res.candidates else None
    scenarios["A_original_work_discovery"] = {
        "kind": "fixture(local lexicon)",
        "work_resolved": bool(top) and top.record.authority_id == "work:kritik-reinen-vernunft",
        "original_title": top.record.canonical_name if top else None,
        "note": "live Top-10 rank is measured separately (b10_live_check)"}

    # B: edition identification.
    a = identify_edition("work:kritik-reinen-vernunft", 1781)
    b = identify_edition("work:kritik-reinen-vernunft", 1787)
    o1 = identify_edition("work:origin-of-species", 1859)
    o6 = identify_edition("work:origin-of-species", 1872)
    scenarios["B_edition_identification"] = {
        "kind": "fixture",
        "kant_A_vs_B_distinct": bool(a and b and a["edition_id"] != b["edition_id"]),
        "origin_1_vs_6_distinct": bool(o1 and o6 and o1["edition_id"] != o6["edition_id"]),
        "unknown_year_rejected": identify_edition("work:origin-of-species", 1863) is None}

    # C/D/E: dataset categories measured in Stages 1-3.
    b10fixed = _load("b10-fixed.json")
    cats = {}
    for case in (b10fixed or {}).get("cases", []):
        cats[case["category"]] = cats.get(case["category"], 0) + 1
    alloc = _load("results-b10-allocation.json") or {}
    policy_a = (alloc.get("policies") or {}).get("A_legacy_b6_release") or {}
    scenarios["C_historical_notation"] = {
        "kind": "fixture(dataset)",
        "dataset_cases": cats.get("historical_notation", 0),
        "note": "scored via the multilingual subject + notation categories in the Stage 1/3 simulation runs"}
    scenarios["D_multilingual_industrial_history"] = {
        "kind": "simulation",
        "b6_fixed_recall@10": (policy_a.get("b6_fixed_F") or {}).get("recall@10"),
        "b6_challenge_recall@10": (policy_a.get("b6_challenge_F") or {}).get("recall@10")}
    scenarios["E_nordic_allocation"] = {
        "kind": "simulation",
        "b8_standard_recall@10": (policy_a.get("b8_fixed_standard") or {}).get("recall@10"),
        "b8_cross_language_rate": (policy_a.get("b8_fixed_standard") or {}).get("cross_language_discovery_rate")}

    # F: newspaper research (b6 corpus newspaper cases).
    corpus = _load("b6-corpus.json") or []
    news = [r for r in corpus if r.get("material_type") == "newspaper"]
    scenarios["F_newspaper_research"] = {
        "kind": "fixture(corpus)",
        "newspaper_records_in_corpus": len(news),
        "note": "material-type ranking signal covered by ranking tests; live newspaper search depends on LoC availability"}

    # G: historical claim (Stage 4 results).
    claims = _load("results-b10-claims-fixed.json") or {}
    scenarios["G_historical_claim"] = {
        "kind": "fixture(dataset)",
        "stats": claims.get("stats"),
        "false_support_promotions": claims.get("false_support_promotions")}
    claim = structure_claim("明治時代の日本で水力発電所が建設された")
    scenarios["G_claim_structure_example"] = {
        "kind": "fixture", "claim": claim.to_dict()}

    # H: multilingual comparison (existing compare layer).
    overlap = concept_overlap({
        "ja_doc": "蒸気機関は工場の動力となった。蒸気機関の普及は輸送を変えた。",
        "de_doc": "Die Dampfmaschine wurde zum Antrieb der Fabriken. Die Dampfmaschine veränderte den Verkehr."})
    scenarios["H_multilingual_comparison"] = {
        "kind": "fixture(synthetic pair)", "concept_overlap_computed": bool(overlap)}

    # I: contradiction candidates (Stage 4 results).
    scenarios["I_contradiction_candidates"] = {
        "kind": "fixture(dataset)",
        "fixed_rate": ((claims.get("stats") or {}).get("contradiction") or {}).get("rate")}

    # J: false premises - structuring never promotes; admission
    # gates are the frozen pipeline's (pytest suites).
    scenarios["J_false_premise"] = {
        "kind": "fixture(dataset)+frozen gates",
        "dataset_cases": cats.get("false_premise_negative", 0),
        "note": "premise handling lives in the frozen evidence pipeline (Phase 7/9 suites in pytest); b10 structuring adds no promotion path"}

    # K: research saving - workspace Playwright journeys.
    scenarios["K_research_saving"] = {
        "kind": "fixture(Playwright)",
        "note": "6 mandatory workspace journeys pass (Stage 5 local run); b10 artefacts covered by tests/test_b10_workspace.py"}

    # L: external safety - b9 security evaluation + Stage 0 tests.
    scenarios["L_external_safety"] = {
        "kind": "fixture(security eval)",
        "note": "external profile unchanged (5 tools, no text transfer); Stage 0 hardening tests in tests/test_b10_stage0.py; security eval re-run in Stage 6"}

    report = {"evaluation_kind": "b10 scenarios A-L (offline-decidable parts)",
              "scenarios": scenarios}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(scenarios, ensure_ascii=False, indent=1)[:1800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
