"""Citation and report exporters (b7, brief sections 21-25).

Deterministic template processing only - no LLM. Unknown
bibliographic fields are OMITTED, never invented. Candidate
work/author ids are never exported as authority data.
BibTeX output targets classic BibTeX (UTF-8 source for
modern engines such as bibtex8/xelatex pipelines); metadata
backslashes and braces are escaped so stored text cannot
smuggle TeX commands into an export.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .policy import effective_decision
from .policy import evaluate as evaluate_rights

def parse_date_parts(publication_date: str | None) -> tuple[int, int | None, int | None] | None:
    """(year, month, day) from a stored publication_date, or
    None when no defensible year exists. Final review section
    22: no 1500-2099 clamp (classical and early materials are
    real), no fabrication for BCE / uncertain dates, ranges
    resolve to their first year, and a full ISO date keeps
    month and day (newspaper issues need them)."""
    if not publication_date:
        return None
    text = str(publication_date)
    if re.search(r"(BCE|BC\b|紀元前)", text):
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        year, month, day = (int(g) for g in m.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return year, month, day
    m = re.search(r"(\d{4})-(\d{1,2})(?!\d)", text)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2)), None
    m = re.search(r"(?<!\d)(\d{3,4})(?!\d)", text)
    if m:
        return int(m.group(1)), None, None
    return None


def year_of(publication_date: str | None) -> str | None:
    parts = parse_date_parts(publication_date)
    return str(parts[0]) if parts else None


def _slug(text: str | None, fallback: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text or fallback


def base_citation_key(doc: dict[str, Any]) -> str:
    """Stable key from the record itself (author+year+title),
    so re-exporting the same document yields the same key."""
    author = (doc.get("author") or "").split(";")[0].split(",")[0].strip()
    author_slug = _slug(author, "anon")
    year = year_of(doc.get("publication_date")) or "nd"
    title_word = ""
    for token in re.split(r"[^A-Za-z0-9]+", unicodedata.normalize("NFKC", doc.get("title") or "")):
        if len(token) >= 3:
            title_word = token.lower()
            break
    return f"{author_slug}{year}{title_word}"


def assign_keys(docs: list[dict[str, Any]]) -> dict[str, str]:
    """saved_document_id -> unique key within this export set.

    Final review section 21: a document's STORED citation key
    (assigned once at save time) always wins, so adding or
    removing other documents never renames it. Documents
    without a stored key fall back to the deterministic base
    key with suffixes that are checked against every key in
    the set (a suffix can never shadow another base key)."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for doc in docs:
        key = doc.get("citation_key")
        if key and key not in used:
            out[doc["saved_document_id"]] = key
            used.add(key)
    pending = [d for d in docs if d["saved_document_id"] not in out]
    for doc in sorted(pending, key=lambda d: (base_citation_key(d), d["saved_document_id"])):
        base = base_citation_key(doc)
        candidate, n = base, 0
        while candidate in used:
            n += 1
            candidate = base + (chr(ord("a") + n - 1) if n <= 26 else f"-{n - 26}")
        out[doc["saved_document_id"]] = candidate
        used.add(candidate)
    return out


def split_authors(author: str | None) -> list[str]:
    if not author:
        return []
    parts = re.split(r"\s*;\s*|\s+and\s+", str(author))
    return [p.strip() for p in parts if p.strip()]


_ORG_WORDS = (
    "university", "institute", "library", "museum", "society",
    "committee", "ministry", "department", "commission", "bureau",
    "academy", "school", "college", "press", "company", "council",
    "大学", "図書館", "研究所", "学会", "協会", "委員会", "博物館",
)


def csl_author(name: str) -> dict[str, str]:
    """CSL name: family/given only when the split is safe,
    otherwise a literal. Final review section 22: a bare
    two-token string is split only for plainly personal Latin
    names; organisation names (keyword-bearing) and CJK names
    stay literal so an institution is never misread as a
    person."""
    name = name.strip()
    if "," in name:
        family, given = name.split(",", 1)
        return {"family": family.strip(), "given": given.strip()}
    if re.search(r"[぀-ヿ㐀-鿿]", name) or " " not in name:
        return {"literal": name}
    if any(word in name.lower() for word in _ORG_WORDS):
        return {"literal": name}
    tokens = name.split()
    if len(tokens) == 2 and all(re.fullmatch(r"[A-Z][A-Za-z.'-]*", t) for t in tokens):
        return {"family": tokens[1], "given": tokens[0]}
    return {"literal": name}


# ---------------------------------------------------------------- BibTeX
def _tex(value: Any) -> str:
    # Single-pass escaping: chained replaces would re-escape
    # the backslashes introduced by earlier replacements.
    text = str(value).replace("\r", " ").replace("\n", " ")
    out = []
    for ch in text:
        if ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch in "{}&%#_":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _kind(doc: dict[str, Any]) -> str:
    """Canonical material kind from the stored material_type.
    Final review section 22: an unknown kind stays unknown -
    a record is never promoted to "book" merely for having a
    title."""
    raw = (doc.get("material_type") or "").lower()
    if "newspaper" in raw or "新聞" in raw:
        return "newspaper"
    if "article" in raw or "論文" in raw or "journal" in raw or "雑誌" in raw:
        return "article"
    if "map" in raw or "地図" in raw:
        return "map"
    if "manuscript" in raw or "写本" in raw:
        return "manuscript"
    if "postcard" in raw or "絵葉書" in raw:
        return "postcard"
    if "photo" in raw or "写真" in raw or "image" in raw:
        return "photograph"
    if "government" in raw or "政府" in raw or "官報" in raw:
        return "government"
    if "manual" in raw or "マニュアル" in raw:
        return "manual"
    if "book" in raw or "図書" in raw or "書籍" in raw:
        return "book"
    return "unknown"


_BIBTEX_TYPES = {"book": "book", "article": "article", "manual": "manual"}


def _bibtex_type(doc: dict[str, Any]) -> str:
    # Classic BibTeX has no newspaper/map/manuscript types;
    # the safe generic @misc is used rather than a wrong
    # specific type (a newspaper issue is not a journal
    # article, and its name is not a journal title).
    return _BIBTEX_TYPES.get(_kind(doc), "misc")


def to_bibtex(docs: list[dict[str, Any]]) -> str:
    keys = assign_keys(docs)
    entries = []
    for doc in docs:
        fields: list[tuple[str, str]] = []
        if doc.get("title"):
            fields.append(("title", _tex(doc["title"])))
        authors = split_authors(doc.get("author"))
        if authors:
            fields.append(("author", " and ".join(_tex(a) for a in authors)))
        parts = parse_date_parts(doc.get("publication_date"))
        if parts:
            fields.append(("year", str(parts[0])))
            if parts[1]:
                fields.append(("month", str(parts[1])))
        elif doc.get("publication_date"):
            fields.append(("note", _tex(f"publication date as recorded: {doc['publication_date']}")))
        if doc.get("publisher"):
            fields.append(("publisher", _tex(doc["publisher"])))
        if doc.get("publication_place"):
            fields.append(("address", _tex(doc["publication_place"])))
        if doc.get("edition"):
            fields.append(("edition", _tex(doc["edition"])))
        if doc.get("translator"):
            fields.append(("translator", _tex(doc["translator"])))
        if doc.get("volume"):
            fields.append(("volume", _tex(doc["volume"])))
        identifiers = doc.get("identifiers") or {}
        if identifiers.get("isbn"):
            fields.append(("isbn", _tex(identifiers["isbn"])))
        if identifiers.get("doi"):
            fields.append(("doi", _tex(identifiers["doi"])))
        if doc.get("landing_url"):
            fields.append(("url", _tex(doc["landing_url"])))
        if doc.get("retrieved_at"):
            fields.append(("urldate", _tex(str(doc["retrieved_at"])[:10])))
        if doc.get("language_normalized"):
            fields.append(("language", _tex(doc["language_normalized"])))
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
        entries.append(f"@{_bibtex_type(doc)}{{{keys[doc['saved_document_id']]},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


# ------------------------------------------------------------------- RIS
_RIS_TYPES = {"book": "BOOK", "article": "JOUR", "newspaper": "NEWS",
              "manual": "MANUAL", "map": "MAP", "manuscript": "MANSCPT"}


def _ris_value(value: Any) -> str:
    """One physical line per tag: CR/LF are stripped so stored
    metadata can never inject extra RIS records or tags."""
    return re.sub(r"[\r\n]+", " ", str(value)).strip()


def to_ris(docs: list[dict[str, Any]]) -> str:
    records = []
    for doc in docs:
        lines = [f"TY  - {_RIS_TYPES.get(_kind(doc), 'GEN')}"]
        if doc.get("title"):
            lines.append(f"TI  - {_ris_value(doc['title'])}")
        for author in split_authors(doc.get("author")):
            lines.append(f"AU  - {_ris_value(author)}")
        parts = parse_date_parts(doc.get("publication_date"))
        if parts:
            if parts[1] and parts[2]:
                lines.append(f"Y1  - {parts[0]}/{parts[1]:02d}/{parts[2]:02d}")
            else:
                lines.append(f"PY  - {parts[0]}")
        if doc.get("publisher"):
            lines.append(f"PB  - {_ris_value(doc['publisher'])}")
        if doc.get("publication_place"):
            lines.append(f"CY  - {_ris_value(doc['publication_place'])}")
        if doc.get("edition"):
            lines.append(f"ET  - {_ris_value(doc['edition'])}")
        if doc.get("volume"):
            lines.append(f"VL  - {_ris_value(doc['volume'])}")
        identifiers = doc.get("identifiers") or {}
        if identifiers.get("doi"):
            lines.append(f"DO  - {_ris_value(identifiers['doi'])}")
        if identifiers.get("isbn"):
            lines.append(f"SN  - {_ris_value(identifiers['isbn'])}")
        if doc.get("landing_url"):
            lines.append(f"UR  - {_ris_value(doc['landing_url'])}")
        if doc.get("language_normalized"):
            lines.append(f"LA  - {_ris_value(doc['language_normalized'])}")
        lines.append(f"N1  - {_ris_value(doc.get('library_id', ''))} / {_ris_value(doc.get('record_id', ''))}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records) + ("\n" if records else "")


# --------------------------------------------------------------- CSL JSON
_CSL_TYPES = {"book": "book", "article": "article-journal",
              "newspaper": "article-newspaper", "manual": "book",
              "map": "map", "manuscript": "manuscript",
              "photograph": "graphic", "postcard": "document",
              "government": "document", "unknown": "document"}


def to_csl_json(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = assign_keys(docs)
    out = []
    for doc in docs:
        item: dict[str, Any] = {"id": keys[doc["saved_document_id"]]}
        item["type"] = _CSL_TYPES.get(_kind(doc), "document")
        if doc.get("title"):
            item["title"] = doc["title"]
        authors = [csl_author(a) for a in split_authors(doc.get("author"))]
        if authors:
            item["author"] = authors
        translators = [csl_author(a) for a in split_authors(doc.get("translator"))]
        if translators:
            item["translator"] = translators
        parts = parse_date_parts(doc.get("publication_date"))
        if parts:
            date_parts = [parts[0]] + [p for p in parts[1:] if p is not None]
            item["issued"] = {"date-parts": [date_parts]}
        if doc.get("retrieved_at"):
            date = str(doc["retrieved_at"])[:10].split("-")
            if len(date) == 3:
                item["accessed"] = {"date-parts": [[int(date[0]), int(date[1]), int(date[2])]]}
        if doc.get("publisher"):
            item["publisher"] = doc["publisher"]
        if doc.get("publication_place"):
            item["publisher-place"] = doc["publication_place"]
        if doc.get("edition"):
            item["edition"] = doc["edition"]
        if doc.get("volume"):
            item["volume"] = doc["volume"]
        identifiers = doc.get("identifiers") or {}
        if identifiers.get("doi"):
            item["DOI"] = identifiers["doi"]
        if identifiers.get("isbn"):
            item["ISBN"] = identifiers["isbn"]
        if doc.get("landing_url"):
            item["URL"] = doc["landing_url"]
        if doc.get("language_normalized"):
            item["language"] = doc["language_normalized"]
        out.append(item)
    return out


# -------------------------------------------------------------- plain text
def to_plain_text(docs: list[dict[str, Any]]) -> str:
    keys = assign_keys(docs)
    lines = []
    for doc in docs:
        parts = []
        if doc.get("author"):
            parts.append(str(doc["author"]))
        if doc.get("title"):
            parts.append(f"『{doc['title']}』" if re.search(r"[぀-ヿ㐀-鿿]", doc["title"]) else str(doc["title"]))
        year = year_of(doc.get("publication_date"))
        if year:
            parts.append(year)
        if doc.get("publisher"):
            parts.append(str(doc["publisher"]))
        parts.append(f"[{keys[doc['saved_document_id']]}]")
        if doc.get("landing_url"):
            parts.append(str(doc["landing_url"]))
        lines.append(" ".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


# ------------------------------------------------------- Markdown report
def _md(text: Any) -> str:
    """Escape stored text for safe Markdown insertion (final
    review section 23): structural characters are escaped so
    metadata, OCR text and notes cannot break the report's
    structure, inject headings/links/images, close code
    fences, or smuggle raw HTML. The researcher's words stay
    readable; only the syntax-bearing characters change."""
    s = str(text if text is not None else "").replace("\r", " ")
    s = s.replace("\\", "\\\\").replace("`", "\\`")
    s = s.replace("*", "\\*").replace("_", "\\_")
    s = s.replace("[", "\\[").replace("]", "\\]")
    s = s.replace("(", "\\(").replace(")", "\\)")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"(?m)^(\s*)([#])", r"\1\\\2", s)
    s = re.sub(r"(?m)^(\s*)(!)", r"\1\\\2", s)
    return s


def _md_url(url: Any) -> str:
    """A URL safe to print in a report: https only, no spaces
    or parentheses (which would break link syntax). Anything
    else is printed as plain text by the caller, never as a
    link."""
    text = str(url or "")
    return text if re.fullmatch(r"https://[^\s()]+", text) else ""


def project_markdown(project: dict[str, Any], documents: list[dict[str, Any]],
                      citations: list[dict[str, Any]], notes: list[dict[str, Any]],
                      comparisons: list[dict[str, Any]],
                      history: list[dict[str, Any]],
                      latest_rights: dict[str, str | None] | None = None
                      ) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic project report. Sections keep the five
    kinds of content separate (researcher's writing / fetched
    quotations / system bibliographic data / verification
    results / unverified candidates). Excerpts are re-gated at
    export time against BOTH the save-time rights and the
    latest observed rights; omissions are listed. Every
    citation carries its full original-source provenance."""
    latest_rights = latest_rights or {}
    keys = assign_keys(documents)
    docs_by_id = {d["saved_document_id"]: d for d in documents}
    omissions: list[dict[str, Any]] = []
    out: list[str] = [f"# {_md(project.get('title'))}", ""]
    if project.get("description"):
        out += ["## 研究目的", "", _md(project["description"]), ""]
    if history:
        out += ["## 検索履歴", ""]
        for h in history:
            params = h.get("search_parameters") or {}
            out.append(f"- {_md(h.get('created_at'))}: 「{_md(h.get('original_query'))}」"
                       f"（mode: {_md(params.get('mode', ''))}, status: {_md(h.get('search_status'))},"
                       f" 出所: {_md(h.get('provenance') or 'server_recorded')}）")
        out.append("")
    out += ["## 保存資料一覧", ""]
    for doc in documents:
        year = year_of(doc.get("publication_date")) or "年不明"
        out.append(f"- [{keys[doc['saved_document_id']]}] {_md(doc.get('author') or '著者不明')} "
                   f"『{_md(doc.get('title') or '題不明')}』（{year}） "
                   f"{_md(doc.get('library_id'))} / {_md(doc.get('record_id'))}")
    out.append("")
    if citations:
        out += ["## 主要な引用", ""]
        for cit in citations:
            doc = docs_by_id.get(cit["saved_document_id"], {})
            statement = (cit.get("rights_at_save") or {}).get("statement")
            decision = effective_decision(statement, latest_rights.get(cit["saved_document_id"]))
            header = (f"### [{keys.get(cit['saved_document_id'], '?')}] "
                      f"p. {_md(cit.get('page_id'))}")
            out.append(header)
            out.append(f"- 検証状態: {_md(cit.get('quotation_verification_status') or 'not_checked')}"
                       f" / ページ対応: {_md(cit.get('page_mapping_status') or 'unknown')}"
                       f" / 画像: {_md(cit.get('image_verification_status') or 'not_checked')}"
                       f" / 出所: {_md(cit.get('provenance'))}")
            out.append(f"- 原典: 資料ID {_md(doc.get('record_id'))} / ページID {_md(cit.get('page_id'))}"
                       f" / OCR取得元 {_md(cit.get('ocr_source'))}"
                       f" / 引用キー {_md(cit.get('citation_key'))}")
            image = _md_url(cit.get("image_url"))
            landing = _md_url(doc.get("landing_url"))
            if image:
                out.append(f"- 原本画像URL: {image}")
            if landing:
                out.append(f"- ランディングURL: {landing}")
            out.append(f"- 保存日時: {_md(cit.get('saved_at'))} / 取得日時: {_md(cit.get('retrieved_at'))}"
                       f" / 本文保存: {'あり' if cit.get('original_excerpt') else 'なし（参照のみ）'}")
            if cit.get("original_excerpt") and decision["excerpt_export"]:
                out.append("")
                for line in str(cit["original_excerpt"]).split("\n"):
                    out.append("> " + _md(line))
            else:
                reason = decision["reason"] if cit.get("original_excerpt") \
                    else (cit.get("excerpt_omitted_reason") or decision["reason"])
                omissions.append({"citation_id": cit["citation_id"], "reason": reason})
                out.append(f"- 原文抜粋は出力されません（{_md(reason)}）。"
                           f"資料: {_md(doc.get('landing_url') or '')}")
            if cit.get("user_annotation"):
                out.append(f"- 研究者注釈: {_md(cit['user_annotation'])}")
            out.append("")
    if comparisons:
        out += ["## 文献比較", ""]
        for comp in comparisons:
            out.append(f"### {_md(comp.get('title') or '比較')}")
            out.append(f"- 意味比較: {_md(comp.get('semantic_status'))}（意味的な比較は未実施です。辞書概念の一致は意味の一致を意味しません）")
            shared = (comp.get("dictionary_concept_overlap") or {}).get("shared_concepts") or []
            if shared:
                out.append(f"- 共通概念候補: {', '.join(_md(s) for s in shared[:20])}")
            excerpts = comp.get("original_excerpts") or {}
            for doc_id, value in excerpts.items():
                doc = docs_by_id.get(doc_id, {})
                if isinstance(value, dict):
                    out.append(f"- [{keys.get(doc_id, '?')}] 抜粋省略: {_md(value.get('omitted'))}")
                elif isinstance(value, list):
                    statement = (doc.get("rights_snapshot") or {}).get("statement")
                    decision = effective_decision(statement, latest_rights.get(doc_id))
                    if decision["excerpt_export"]:
                        for entry in value[:3]:
                            text = entry.get("text") if isinstance(entry, dict) else entry
                            if text:
                                out.append(f"- [{keys.get(doc_id, '?')}] 抜粋: {_md(text)}")
                    else:
                        out.append(f"- [{keys.get(doc_id, '?')}] 抜粋省略: {_md(decision['reason'])}")
            out.append("")
    if notes:
        out += ["## 研究ノート", ""]
        for note in notes:
            out.append(f"### {_md(note.get('title') or '（無題）')}")
            out.append(_md(note.get("content")))
            out.append("")
    out += ["## 参考文献", "", "```bibtex", to_bibtex(documents).rstrip(), "```", ""]
    out += ["## 権利情報と未検証事項", ""]
    out.append("- 本レポートは決定的なテンプレート生成であり、AI生成文は含みません。")
    out.append("- 未検証の引用・候補は検証済みとは記載していません。")
    out.append("- ノートやメタデータに含まれるMarkdown構文はエスケープされ、レポート構造や外部通信には影響しません。")
    for doc in documents:
        rights = doc.get("rights_snapshot") or {}
        line = (f"- [{keys[doc['saved_document_id']]}] 権利（保存時）: {_md(rights.get('statement') or 'unknown')}"
                f"（区分: {_md(evaluate_rights(rights.get('statement'))['category'])}）")
        latest = latest_rights.get(doc["saved_document_id"])
        if latest and latest != rights.get("statement"):
            decision = effective_decision(rights.get("statement"), latest)
            line += (f" / 最新の観測: {_md(latest)}（区分: {_md(evaluate_rights(latest)['category'])}、"
                     f"現在の出力可否: {'可' if decision['excerpt_export'] else '不可'}）")
        out.append(line)
    for omission in omissions:
        out.append(f"- 抜粋省略: {omission['citation_id']} — {_md(omission['reason'])}")
    out.append("")
    return "\n".join(out), omissions


EXPORT_FORMATS = ("bibtex", "ris", "csl-json", "text", "markdown", "json")


def documents_export(fmt: str, docs: list[dict[str, Any]]) -> tuple[str, str]:
    """Returns (content, content_type)."""
    if fmt == "bibtex":
        return to_bibtex(docs), "application/x-bibtex; charset=utf-8"
    if fmt == "ris":
        return to_ris(docs), "application/x-research-info-systems; charset=utf-8"
    if fmt == "csl-json":
        return json.dumps(to_csl_json(docs), ensure_ascii=False, indent=2), "application/vnd.citationstyles.csl+json; charset=utf-8"
    if fmt == "text":
        return to_plain_text(docs), "text/plain; charset=utf-8"
    raise ValueError(f"unsupported documents export format: {fmt}")
