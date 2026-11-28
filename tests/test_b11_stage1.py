"""b11 Stage 1 tests (sections 15-22): dataset integrity,
grouped splits, blind review package, agreement metrics."""
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

ROOT = Path(__file__).resolve().parents[1]


def _dataset():
    return json.loads((ROOT / "eval/b11-cases.json").read_text())


def test_dataset_provenance_vocabulary_and_counts():
    payload = _dataset()
    cases = payload["cases"]
    assert payload["case_count"] == len(cases) == 294
    from collections import Counter
    prov = Counter(c["label"]["provenance"] for c in cases)
    assert prov["authority_source_supported"] == 6
    assert prov["unresolved"] == 7
    # no human evaluation exists; none may be claimed
    assert prov.get("human_reviewed", 0) == 0
    assert prov.get("independent_human_verified", 0) == 0
    ids = [c["case_id"] for c in cases]
    assert len(set(ids)) == len(ids)


def test_gnd_confirmed_cases_carry_source_records():
    cases = {c["case_id"]: c for c in _dataset()["cases"]}
    marx = cases["b11-gnd-marx"]
    assert marx["expect"]["gnd"] == "118578537"
    assert marx["label"]["source_url"] == \
        "https://lobid.org/gnd/118578537.html"
    assert marx["label"]["checked_fields"] == ["preferredName", "dateOfBirth"]
    ein = cases["b11-gnd-unconfirmed-einstein"]
    assert ein["expect"]["gnd"] is None
    assert ein["label"]["provenance"] == "unresolved"


def test_carried_cases_keep_b10_expectations_verbatim():
    b10 = json.loads((ROOT / "eval/b10-fixed.json").read_text())
    rows = b10["cases"] if isinstance(b10, dict) else b10
    by_id = {c["case_id"]: c for c in _dataset()["cases"]}
    for r in rows[:10]:
        carried = by_id[f"b11-carry-{r['id']}"]
        assert carried["expect"] == r["expect"]
        assert carried["label"]["provenance"] == "agent_assigned"


def test_grouped_splits_zero_overlap_and_reproducible():
    sys.path.insert(0, str(ROOT / "eval"))
    import b11_grouped_splits as gs
    cases = _dataset()["cases"]
    a = gs.assign(cases)
    b = gs.assign(cases)
    assert a == b
    assert a["cross_split_entity_overlap"] == 0
    total = sum(s["case_count"] for s in a["splits"].values())
    assert total == len(cases)


def test_review_csv_is_blind():
    sys.path.insert(0, str(ROOT / "eval"))
    import b11_review as br
    rows = br.blind_rows(_dataset()["cases"])
    text = br.to_csv(rows)
    assert "expect" not in text.splitlines()[0]
    assert "provenance" not in text
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert all(r["judgement"] == "" for r in parsed)
    html = br.review_html(rows)
    assert "118578537" not in html  # expected GND not leaked


def test_agreement_unmeasured_without_two_reviewers():
    sys.path.insert(0, str(ROOT / "eval"))
    import b11_agreement as ag
    assert ag.agreement_report({})["status"] == "unmeasured"
    assert ag.agreement_report({"r1": {"c1": "correct"}})["status"] == \
        "unmeasured"
    # synthetic two-reviewer fixture: metrics compute, clearly a
    # code test, not human evaluation
    rep = ag.agreement_report({
        "r1": {"c1": "correct", "c2": "incorrect", "c3": "correct"},
        "r2": {"c1": "correct", "c2": "correct", "c3": "correct"}})
    assert rep["status"] == "measured"
    assert rep["kappa"]["n"] == 3
    assert 0.0 <= rep["kappa"]["percent_agreement"] <= 1.0
