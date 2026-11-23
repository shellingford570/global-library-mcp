from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Capability:
    bibliographic: bool | str = "unknown"
    fulltext: bool | str = "unknown"
    ocr: bool | str = "unknown"
    image: bool | str = "unknown"
    page: bool | str = "unknown"
    iiif: bool | str = "unknown"


@dataclass(slots=True)
class Rights:
    statement: str = "unknown"
    url: str | None = None
    source: str | None = None


@dataclass(slots=True)
class SearchResult:
    library_id: str
    library_name: str
    record_id: str
    title: str
    author: str | None = None
    date: str | None = None
    language: str | None = None
    description: str | None = None
    landing_url: str | None = None
    image_url: str | None = None
    iiif_manifest_url: str | None = None
    fulltext_status: str = "unknown"
    rights: Rights = field(default_factory=Rights)
    source_protocol: str | None = None
    retrieved_at: str = field(default_factory=now_iso)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchResponse:
    query: str
    results: list[SearchResult]
    errors: list[dict[str, str]] = field(default_factory=list)
    retrieved_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "results": [item.to_dict() for item in self.results],
            "errors": self.errors,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(slots=True)
class Evidence:
    """One page of OCR text whose identity has been cross-checked.

    An Evidence record is only marked ``verified`` when the page payload
    returned by the library matches the requested page (book PID, page id
    and digital frame) and the OCR text passed the quality gate. Anything
    else must be carried as unverified and never used as the basis for a
    page-level claim.
    """

    library_id: str
    library_name: str
    record_id: str
    title: str
    page_id: str
    digital_frame: int | None = None
    printed_page: str = "unknown"
    ocr_text: str = ""
    ocr_source: str = "unknown"
    ocr_quality: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None
    landing_url: str | None = None
    matched_term: str | None = None
    verified: bool = False
    verification_notes: list[str] = field(default_factory=list)
    relevance: dict[str, Any] = field(default_factory=dict)
    semantics: dict[str, Any] = field(default_factory=dict)
    page_kind: str | None = None
    rights: Rights = field(default_factory=Rights)
    retrieved_at: str = field(default_factory=now_iso)

    @property
    def citation_key(self) -> str:
        return f"{self.library_id}:{self.record_id}:{self.page_id}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation_key"] = self.citation_key
        return data
