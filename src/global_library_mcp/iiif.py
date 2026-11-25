"""Shared IIIF helpers (b5, section 7).

One place that understands IIIF Presentation API 2 and 3
manifests, so new library adapters do not each re-implement
manifest parsing. The parser only EXTRACTS structure: which
canvas corresponds to which image service and which OCR
resource. Whether that correspondence is *proven* is decided
by the adapter: a canvas/OCR pairing counts as proven only
when the manifest itself links them (v2 ``seeAlso`` on the
canvas, v3 annotation/supplementing annotations, or an OCR
URL pattern the provider documents as page-indexed) - never
by guessing page numbers.

Also contains small, bounded parsers for ALTO XML and hOCR,
the two OCR formats the connected libraries serve.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from dataclasses import dataclass, field
from html import unescape


@dataclass
class IiifCanvas:
    """One canvas of a manifest, in manifest order."""

    index: int  # 0-based position in the manifest's canvas list
    canvas_id: str
    label: str | None = None
    image_service_id: str | None = None
    image_url: str | None = None
    ocr_urls: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None


@dataclass
class IiifManifest:
    manifest_id: str | None
    label: str | None
    version: int  # 2 or 3
    license_url: str | None
    metadata: dict[str, str]
    canvases: list[IiifCanvas]
    raw: dict


def _lang_value(value: object) -> str | None:
    """Best single string from a IIIF v2/v3 label-ish value."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            found = _lang_value(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        for key in ("en", "de", "fr", "ja", "none", "@value"):
            if key in value:
                found = _lang_value(value[key])
                if found:
                    return found
        for item in value.values():
            found = _lang_value(item)
            if found:
                return found
    return None


def _metadata_dict(entries: object) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = _lang_value(entry.get("label"))
        value = _lang_value(entry.get("value"))
        if label and value and label not in out:
            out[label] = re.sub(r"<[^>]+>", "", value).strip()
    return out


def parse_manifest(payload: dict) -> IiifManifest:
    """Parse a Presentation API v2 or v3 manifest payload."""
    context = str(payload.get("@context") or "")
    if "/presentation/3" in context or payload.get("type") == "Manifest":
        return _parse_v3(payload)
    return _parse_v2(payload)


def _parse_v2(payload: dict) -> IiifManifest:
    canvases: list[IiifCanvas] = []
    sequences = payload.get("sequences") or []
    raw_canvases: list = []
    if sequences and isinstance(sequences[0], dict):
        raw_canvases = sequences[0].get("canvases") or []
    for index, canvas in enumerate(raw_canvases):
        if not isinstance(canvas, dict):
            continue
        record = IiifCanvas(index=index, canvas_id=str(canvas.get("@id") or ""))
        record.label = _lang_value(canvas.get("label"))
        record.width = canvas.get("width")
        record.height = canvas.get("height")
        images = canvas.get("images") or []
        if images and isinstance(images[0], dict):
            resource = images[0].get("resource") or {}
            record.image_url = resource.get("@id")
            service = resource.get("service") or {}
            record.image_service_id = service.get("@id")
        for key in ("seeAlso", "otherContent"):
            linked = canvas.get(key)
            if isinstance(linked, dict):
                linked = [linked]
            for item in linked or []:
                if isinstance(item, dict) and item.get("@id"):
                    record.ocr_urls.append(str(item["@id"]))
        canvases.append(record)
    return IiifManifest(
        manifest_id=payload.get("@id"),
        label=_lang_value(payload.get("label")),
        version=2,
        license_url=payload.get("license"),
        metadata=_metadata_dict(payload.get("metadata")),
        canvases=canvases,
        raw=payload,
    )


def _parse_v3(payload: dict) -> IiifManifest:
    canvases: list[IiifCanvas] = []
    for index, canvas in enumerate(payload.get("items") or []):
        if not isinstance(canvas, dict) or canvas.get("type") != "Canvas":
            continue
        record = IiifCanvas(index=index, canvas_id=str(canvas.get("id") or ""))
        record.label = _lang_value(canvas.get("label"))
        record.width = canvas.get("width")
        record.height = canvas.get("height")
        for page in canvas.get("items") or []:
            for annotation in (page or {}).get("items") or []:
                body = (annotation or {}).get("body") or {}
                if body.get("type") == "Image":
                    record.image_url = body.get("id")
                    service = body.get("service") or []
                    if service and isinstance(service[0], dict):
                        record.image_service_id = service[0].get("id")
        for page in canvas.get("annotations") or []:
            for annotation in (page or {}).get("items") or []:
                body = (annotation or {}).get("body") or {}
                if body.get("id"):
                    record.ocr_urls.append(str(body["id"]))
        canvases.append(record)
    rights = payload.get("rights")
    return IiifManifest(
        manifest_id=payload.get("id"),
        label=_lang_value(payload.get("label")),
        version=3,
        license_url=rights if isinstance(rights, str) else None,
        metadata=_metadata_dict(payload.get("metadata")),
        canvases=canvases,
        raw=payload,
    )


def alto_to_text(xml_text: str, *, max_chars: int = 2_000_000) -> str:
    """Plain text from an ALTO XML document (bounded, namespace-
    agnostic). Raises ValueError on malformed XML so callers can
    treat it as a failed fetch, not as empty text."""
    if len(xml_text) > max_chars:
        raise ValueError("ALTO document exceeds the size bound")
    root = ET.fromstring(xml_text)
    lines: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "TextLine":
            continue
        words = [
            node.get("CONTENT") or ""
            for node in element.iter()
            if node.tag.rsplit("}", 1)[-1] == "String"
        ]
        line = " ".join(word for word in words if word)
        if line:
            lines.append(line)
    return "\n".join(lines)


class _HocrTextParser(HTMLParser):
    """Collects ocrx_word text grouped by ocr_line. A regex cannot
    do this correctly: word spans nest inside line spans, so a
    non-greedy match ends the line at the first word's close tag
    (found by the b5 fixture tests)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[list[str]] = []
        self._line: list[str] | None = None
        self._word: list[str] | None = None
        self._span_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "span":
            return
        classes = dict(attrs).get("class") or ""
        if "ocr_line" in classes:
            self._line = []
            self._span_stack.append("line")
        elif "ocrx_word" in classes:
            self._word = []
            self._span_stack.append("word")
        else:
            self._span_stack.append("other")

    def handle_data(self, data: str) -> None:
        if self._word is not None:
            self._word.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "span" or not self._span_stack:
            return
        kind = self._span_stack.pop()
        if kind == "word" and self._word is not None:
            word = "".join(self._word).strip()
            self._word = None
            if word:
                if self._line is None:
                    self._line = []
                self._line.append(word)
        elif kind == "line" and self._line is not None:
            if self._line:
                self.lines.append(self._line)
            self._line = None

    def text(self) -> str:
        if self._line:
            self.lines.append(self._line)
            self._line = None
        return "\n".join(" ".join(line) for line in self.lines)


def hocr_to_text(html_text: str) -> str:
    """Plain text from an hOCR document, words grouped by line."""
    parser = _HocrTextParser()
    parser.feed(html_text or "")
    return parser.text()
