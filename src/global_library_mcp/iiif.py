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
    other_content_urls: list[str] = field(default_factory=list)
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


def _license_url(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        found = value.get("@id") or value.get("id")
        return found if isinstance(found, str) else None
    if isinstance(value, list):
        for item in value:
            found = _license_url(item)
            if found:
                return found
    return None


def _is_ocr_link(item: dict) -> bool:
    """A seeAlso entry counts as an OCR link only when its format
    or profile says so (hOCR / ALTO / plain text). An unlabelled
    seeAlso is not silently treated as OCR."""
    fmt = str(item.get("format") or "").lower()
    profile = str(item.get("profile") or "").lower()
    return (
        "hocr" in fmt or "alto" in fmt or fmt.startswith("text/")
        or "hocr" in profile or "alto" in profile
    )


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
    if not isinstance(payload, dict):
        raise ValueError("IIIF manifest payload is not a JSON object")
    context = str(payload.get("@context") or "")
    if "/presentation/3" in context or payload.get("type") == "Manifest":
        return _parse_v3(payload)
    return _parse_v2(payload)


def _parse_v2(payload: dict) -> IiifManifest:
    canvases: list[IiifCanvas] = []
    raw_canvases: list = []
    for sequence in payload.get("sequences") or []:
        if isinstance(sequence, dict):
            raw_canvases.extend(sequence.get("canvases") or [])
    seen_ids: set[str] = set()
    for canvas in raw_canvases:
        if not isinstance(canvas, dict):
            continue
        canvas_id = str(canvas.get("@id") or "")
        if canvas_id and canvas_id in seen_ids:
            continue
        seen_ids.add(canvas_id)
        record = IiifCanvas(index=len(canvases), canvas_id=canvas_id)
        record.label = _lang_value(canvas.get("label"))
        record.width = canvas.get("width")
        record.height = canvas.get("height")
        images = [img for img in (canvas.get("images") or []) if isinstance(img, dict)]
        # Prefer the first image that carries an image service;
        # fall back to the first image at all.
        chosen = None
        for image in images:
            resource = image.get("resource") or {}
            if isinstance(resource, dict) and resource.get("service"):
                chosen = resource
                break
        if chosen is None and images:
            resource = images[0].get("resource") or {}
            chosen = resource if isinstance(resource, dict) else None
        if chosen:
            record.image_url = chosen.get("@id")
            service = chosen.get("service")
            if isinstance(service, list):
                service = next((s for s in service if isinstance(s, dict)), None)
            if isinstance(service, dict):
                record.image_service_id = service.get("@id")
        see_also = canvas.get("seeAlso")
        if isinstance(see_also, dict):
            see_also = [see_also]
        for item in see_also or []:
            if isinstance(item, dict) and item.get("@id") and _is_ocr_link(item):
                record.ocr_urls.append(str(item["@id"]))
        other = canvas.get("otherContent")
        if isinstance(other, dict):
            other = [other]
        for item in other or []:
            # otherContent points at annotation LISTS, not at OCR
            # itself; keep it visible but never treat it as an
            # OCR link (b5 final review, S12).
            if isinstance(item, dict) and item.get("@id"):
                record.other_content_urls.append(str(item["@id"]))
        canvases.append(record)
    return IiifManifest(
        manifest_id=payload.get("@id"),
        label=_lang_value(payload.get("label")),
        version=2,
        license_url=_license_url(payload.get("license")),
        metadata=_metadata_dict(payload.get("metadata")),
        canvases=canvases,
        raw=payload,
    )


_TEXT_FORMATS = ("text/plain", "text/html", "application/alto+xml", "text/vnd.hocr+html")


def _v3_bodies(annotation: dict):
    """Yield body dicts of a v3 annotation, descending into lists
    and Choice bodies."""
    body = annotation.get("body")
    if isinstance(body, dict):
        body = [body]
    for item in body or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "Choice":
            for choice in item.get("items") or []:
                if isinstance(choice, dict):
                    yield choice
        else:
            yield item


def _parse_v3(payload: dict) -> IiifManifest:
    canvases: list[IiifCanvas] = []
    for canvas in payload.get("items") or []:
        if not isinstance(canvas, dict) or canvas.get("type") != "Canvas":
            continue
        record = IiifCanvas(index=len(canvases), canvas_id=str(canvas.get("id") or ""))
        record.label = _lang_value(canvas.get("label"))
        record.width = canvas.get("width")
        record.height = canvas.get("height")
        for page in canvas.get("items") or []:
            if not isinstance(page, dict):
                continue
            for annotation in page.get("items") or []:
                if not isinstance(annotation, dict):
                    continue
                for body in _v3_bodies(annotation):
                    if body.get("type") != "Image":
                        continue
                    if record.image_url is None:
                        record.image_url = body.get("id")
                    services = body.get("service")
                    if isinstance(services, dict):
                        services = [services]
                    for service in services or []:
                        if isinstance(service, dict) and "ImageService" in str(service.get("type") or ""):
                            if record.image_service_id is None:
                                record.image_service_id = service.get("id")
        for page in canvas.get("annotations") or []:
            if not isinstance(page, dict):
                continue
            # An AnnotationPage given only as an external reference
            # ({"id": ..., "type": "AnnotationPage"}) has no items;
            # it is skipped, never guessed at.
            for annotation in page.get("items") or []:
                if not isinstance(annotation, dict):
                    continue
                motivation = annotation.get("motivation")
                if motivation is not None and motivation != "supplementing":
                    continue  # commenting/tagging/... are not OCR
                for body in _v3_bodies(annotation):
                    fmt = str(body.get("format") or "").lower()
                    if body.get("id") and (body.get("type") == "TextualBody" or fmt in _TEXT_FORMATS):
                        record.ocr_urls.append(str(body["id"]))
        canvases.append(record)
    return IiifManifest(
        manifest_id=payload.get("id"),
        label=_lang_value(payload.get("label")),
        version=3,
        license_url=_license_url(payload.get("rights")),
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
    if "<!ENTITY" in xml_text:
        # ElementTree does not resolve external entities, but a
        # document that declares them is refused outright rather
        # than parsed on a best-effort basis.
        raise ValueError("ALTO document declares XML entities; refused")
    root = ET.fromstring(xml_text)
    lines: list[str] = []
    element_count = 0
    for element in root.iter():
        element_count += 1
        if element_count > 300_000:
            raise ValueError("ALTO document exceeds the element bound")
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


class _HocrTitleParser(HTMLParser):
    """Extracts the document <title> of an hOCR page - the element
    MDZ puts the page identifier in - as a parsed value, instead
    of substring-searching the raw markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self._in_title = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title" and self.title is None:
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = "".join(self._parts).strip()


def hocr_title(html_text: str) -> str | None:
    parser = _HocrTitleParser()
    parser.feed(html_text or "")
    return parser.title


def hocr_to_text(html_text: str, *, max_chars: int = 4_000_000) -> str:
    """Plain text from an hOCR document, words grouped by line."""
    if html_text and len(html_text) > max_chars:
        raise ValueError("hOCR document exceeds the size bound")
    parser = _HocrTextParser()
    parser.feed(html_text or "")
    return parser.text()
