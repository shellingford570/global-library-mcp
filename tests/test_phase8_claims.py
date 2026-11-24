"""Phase 8-H: structured claims and partial answers."""
import asyncio

from global_library_mcp.answer import MockProvider
from global_library_mcp.service import LibraryService


class _StubService(LibraryService):
    """LibraryService with collect_evidence replaced by a fixture."""

    def __init__(self, collected):
        self._collected = collected

    async def collect_evidence(self, query, libraries=None, limit=10):
        return self._collected


PAGE_TEXT = "電信は明治二年に開局した。同年、東京と横浜の間に電信線が架設された。"


def _collected():
    return {
        "terms": ["電信"],
        "analysis": {"core_concepts": ["電信"], "era": {"label": "明治"}, "era_bound": True},
        "evidence": [{
            "citation_key": "ndl:1:1_5", "library_id": "ndl", "library_name": "NDL",
            "record_id": "1", "page_id": "1_5", "digital_frame": 5, "title": "電信史",
            "image_url": None, "landing_url": None, "ocr_text": PAGE_TEXT,
            "passages": [{"passage_id": "ndl:1:1_5#p1", "citation_key": "ndl:1:1_5",
                          "text": "電信は明治二年に開局した。", "quote_verified": True}],
        }],
        "retrieval": {}, "premise_contradictions": [], "related": [], "unverified": [],
        "search": {"results": []},
    }


def test_claims_carry_structure_and_passage_links():
    service = _StubService(_collected())
    result = asyncio.run(service.answer("明治の電信について", provider=MockProvider()))
    assert result["status"] in ("answered", "answered_partial")
    claim = result["claims"][0]
    assert claim["claim_id"] == "c1"
    assert claim["support_status"] == claim["support"]
    assert claim["temporal_scope"] == "明治"
    assert "ndl:1:1_5#p1" in claim["evidence_passage_ids"]
    assert isinstance(claim["numeric_values"], list)
    assert isinstance(claim["limitations"], list)
