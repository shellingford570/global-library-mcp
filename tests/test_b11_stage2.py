"""b11 Stage 2 tests (sections 23-30): NLI backend interface,
synthetic backend, shadow status separation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402
import pytest  # noqa: E402

from global_library_mcp.nli_backend import (  # noqa: E402
    NLINotAvailable, SyntheticNLIBackend, UnavailableNLIBackend,
    shadow_assess)

ROOT = Path(__file__).resolve().parents[1]


def test_unavailable_backend_raises_and_status():
    b = UnavailableNLIBackend()
    assert b.status() == "unavailable"
    with pytest.raises(NLINotAvailable):
        b.predict("p", "h")


def test_shadow_never_changes_rule_status():
    b = SyntheticNLIBackend()
    for status in ("insufficient_evidence", "rejected",
                   "support_candidate"):
        rec = shadow_assess(
            rule_based_status=status,
            premise="The mill produced 40 kW in 1890.",
            hypothesis="The mill produced 40 kW in 1890.", backend=b)
        assert rec["rule_based_status"] == status
        assert rec["nli_status"] == "synthetic_test"


def test_shadow_contradiction_is_candidate_wording():
    rec = shadow_assess(
        rule_based_status="insufficient_evidence",
        premise="The mill produced 40 kW in 1890.",
        hypothesis="The mill produced 90 kW in 1890.",
        backend=SyntheticNLIBackend())
    assert rec["nli_relation"] == "contradiction_candidate"


def test_shadow_unavailable_backend_records_reason():
    rec = shadow_assess(rule_based_status="support_candidate",
                        premise="x", hypothesis="y",
                        backend=UnavailableNLIBackend())
    assert rec["nli_relation"] == "not_checked"
    assert rec["nli_status"] == "unavailable"
    assert rec["rule_based_status"] == "support_candidate"


def test_proxy_eval_runs_and_is_labelled_proxy():
    sys.path.insert(0, str(ROOT / "eval"))
    import b11_nli_eval as ev
    cases = json.loads((ROOT / "eval/b11_nli_cases.json").read_text())["cases"]
    result = ev.run(cases)
    assert result["evaluation_kind"] == "proxy_synthetic_backend"
    assert result["cases"] == len(cases) == 14
    assert 0.0 <= result["agreement"] <= 1.0
