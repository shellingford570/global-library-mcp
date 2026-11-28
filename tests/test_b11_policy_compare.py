"""b11 final review section 38: old expectations vs new policy,
reported SEPARATELY, in a separate file.

The frozen b10 challenge probes (eval/b10_final_eval.py) expect
contradiction/consistency verdicts for compare_facts inputs
that omit identity fields (predicate/object). The b11 policy
(brief section 10, kept in the final review) REQUIRES
insufficient_context for such inputs. Both agreements are
measured and asserted separately here; the frozen b10 file is
not modified. Positive cases WITH full identity fields must
still compare successfully under the new policy - safety is
not bought by refusing everything.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

from global_library_mcp.research import compare_facts  # noqa: E402

# The three probes whose b10 expectation diverges under the
# b11 policy, with the inputs as frozen in b10_final_eval.py
# (identity fields absent).
_DIVERGENT_PROBES = [
    ("kw_vs_mw", "contradiction_candidate"),
    ("km_m_conversion", "consistent_candidate"),
    ("different_place", "differing_scope"),
]


def _fact(**kw):
    base = {"subject": "発電所", "predicate": "出力", "object": "電力",
            "place": "横浜", "unit": "kW", "value": 100.0,
            "library_id": "ndl", "record_id": "1"}
    base.update(kw)
    return base


def test_new_policy_refuses_identity_less_comparisons():
    # Same shape as the frozen probes: no predicate/object.
    a = {"subject": "発電所", "place": "横浜", "unit": "kW",
         "value": 100.0, "library_id": "ndl", "record_id": "1"}
    b = {"subject": "発電所", "place": "横浜", "unit": "MW",
         "value": 100.0, "library_id": "ndl", "record_id": "2"}
    out = compare_facts([a, b])
    assert out["pairs"][0]["status"] == "insufficient_context"


def test_new_policy_positive_cases_still_compare():
    # Full identity fields: a unit contradiction IS detected...
    out = compare_facts([_fact(), _fact(unit="MW", record_id="2")])
    assert out["pairs"][0]["status"] == "contradiction_candidate"
    # ...a true conversion is consistent (100 kW == 0.1 MW)...
    out = compare_facts([_fact(), _fact(unit="MW", value=0.1,
                                        record_id="2")])
    assert out["pairs"][0]["status"] == "consistent_candidate"
    # ...and a different place is a scope difference, each
    # under the NEW policy with sufficient conditions.
    out = compare_facts([_fact(), _fact(place="東京", record_id="2")])
    assert out["pairs"][0]["status"] == "differing_scope"


def test_old_and_new_agreement_reported_separately():
    """Run the frozen probe expectations: agreement with the
    OLD (b10) expectations and agreement with the NEW (b11)
    policy are different numbers and both are pinned here."""
    probes = [
        # (name, facts, b10 expectation, b11 policy expectation)
        ("kw_vs_mw",
         [{"subject": "発電所", "place": "横浜", "unit": "kW",
           "value": 100.0, "library_id": "ndl", "record_id": "1"},
          {"subject": "発電所", "place": "横浜", "unit": "MW",
           "value": 100.0, "library_id": "ndl", "record_id": "2"}],
         "contradiction_candidate", "insufficient_context"),
        ("km_m_conversion",
         [{"subject": "鉄道", "place": "東京", "unit": "km",
           "value": 1.0, "library_id": "ndl", "record_id": "1"},
          {"subject": "鉄道", "place": "東京", "unit": "m",
           "value": 1000.0, "library_id": "ndl", "record_id": "2"}],
         "consistent_candidate", "insufficient_context"),
        ("different_place",
         [{"subject": "発電所", "unit": "kW", "value": 100.0,
           "library_id": "ndl", "record_id": "1"},
          {"subject": "発電所", "place": "大阪", "unit": "kW",
           "value": 100.0, "library_id": "ndl", "record_id": "2"}],
         "differing_scope", "insufficient_context"),
    ]
    old_agree = new_agree = 0
    for _name, facts, old_exp, new_exp in probes:
        status = compare_facts(facts)["pairs"][0]["status"]
        old_agree += status == old_exp
        new_agree += status == new_exp
    # The divergence is exactly the documented one: the three
    # identity-less probes agree with the new policy, not the
    # frozen old expectations. Neither number is hidden.
    assert new_agree == 3
    assert old_agree == 0
