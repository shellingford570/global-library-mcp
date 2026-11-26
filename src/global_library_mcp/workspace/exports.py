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

from .policy import evaluate as evaluate_rights

_YEAR = re.compile(r"(1[5-9]\d\d|20\d\d)")


def year_of(publication_date: str | None) -> str | None:
    if not publication_date:
        return None
    m = _YEAR.search(str(publication_date))
    return m.group(1) if m else None


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
    """saved_document_id -> unique key within this export set."""
    used: dict[str, int] = {}
    out: dict[str, str] = {}
    for doc in sorted(docs, key=lambda d: (base_citation_key(d), d["saved_document_id"])):
        base = base_citation_key(doc)
        n = used.get(base, 0)
        used[base] = n + 1
        out[doc["saved_document_id"]] = base if n == 0 else f"{base}{chr(ord('a') + n)}"
    return out


def split_authors(author: str | None) -> list[str]:
    if not author:
        return []
    parts = re.split(r"\s*;\s*|\s+and\s+", str(author))
    return [p.strip() for p in parts if p.strip()]


def csl_author(name: str) -> dict[str, str]:
    """CSL name: family/given only when the split is safe,
    otherwise a literal (organisation names, CJK names)."""
    name = name.strip()
    if "," in name:
        family, given = name.split(",", 1)
        return {"family": family.strip(), "given": given.strip()}
    if re.search(r"[぀-ヿ㐀-鿿]", name) or " " not in name:
        return {"literal": name}
    tokens = name.split()
    if len(tokens) == 2:
        return {"family": tokens[1], "given": tokens[0]}
    return {"literal": name}


# ---------------------------------------------------------------- BibTeX
def _tex(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("\\", r"\textbackslash{}")
    for ch in ("{", "}", "&", "%", "#", "_"):
        text = text.replace(ch, "\\" + ch)
    return text


def _bibtex_type(doc: dict[str, Any]) -> str:
    kind = (doc.get("material_type") or "").lower()
    if "newspaper" in kind or "新聞" in kind:
        return "article"
    if "article" in kind or "論文" in kind:
        return "article"
    if "manual" in kind:
        return "manual"
    if doc.get("title"):
        return "book"
    return "misc"


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
        year = year_of(doc.get("publication_date"))
        if year:
            fields.append(("year", year))
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
              "manual": "MANUAL"}


def _ris_value(value: Any) -> str:
    """One physical line per tag: CR/LF are stripped so stored
    metadata can never inject extra RIS records or tags."""
    return re.sub(r"[\r\n]+", " ", str(value)).strip()


def to_ris(docs: list[dict[str, Any]]) -> str:
    records = []
    for doc in docs:
        kind = _bibtex_type(doc)
        lines = [f"TY  - {_RIS_TYPES.get(kind, 'GEN')}"]
        if doc.get("title"):
            lines.append(f"TI  - {_ris_value(doc['title'])}")
        for author in split_authors(doc.get("author")):
            lines.append(f"AU  - {_ris_value(author)}")
        year = year_of(doc.get("publication_date"))
        if year:
            lines.append(f"PY  - {year}")
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
              "manual": "book", "misc": "document"}


def to_csl_json(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = assign_keys(docs)
    out = []
    for doc in docs:
        item: dict[str, Any] = {"id": keys[doc["saved_document_id"]]}
        kind = _bibtex_type(doc)
        item["type"] = "article-newspaper" if kind == "article" and (
            "newspaper" in (doc.get("material_type") or "").lower()
            or "新聞" in (doc.get("material_type") or "")) else _CSL_TYPES.get(kind, "book")
        if doc.get("title"):
            item["title"] = doc["title"]
        authors = [csl_author(a) for a in split_authors(doc.get("author"))]
        if authors:
            item["author"] = authors
        translators = [csl_author(a) for a in split_authors(doc.get("translator"))]
        if translators:
            item["translator"] = translators
        year = year_of(doc.get("publication_date"))
        if year:
            item["issued"] = {"date-parts": [[int(year)]]}
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
    return str(text if text is not None else "").replace("\r", " ")


def project_markdown(project: dict[str, Any], documents: list[dict[str, Any]],
                      citations: list[dict[str, Any]], notes: list[dict[str, Any]],
                      comparisons: list[dict[str, Any]],
                      history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic project report. Sections keep the five
    kinds of content separate (researcher's writing / fetched
    quotations / system bibliographic data / verification
    results / unverified candidates). Excerpts pass the rights
    gate again at export time; omissions are listed."""
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
                       f"（mode: {_md(params.get('mode', ''))}, status: {_md(h.get('search_status'))}）")
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
            decision = evaluate_rights(statement)
            header = (f"### [{keys.get(cit['saved_document_id'], '?')}] "
                      f"p. {_md(cit.get('page_id'))}")
            out.append(header)
            out.append(f"- 検証状態: {_md(cit.get('quotation_verification_status') or 'not_checked')}"
                       f" / ページ対応: {_md(cit.get('page_mapping_status') or 'unknown')}"
                       f" / 出所: {_md(cit.get('provenance'))}")
            if cit.get("original_excerpt") and decision["excerpt_export"]:
                out.append("")
                out.append("> " + _md(cit["original_excerpt"]).replace("\n", "\n> "))
            else:
                reason = cit.get("excerpt_omitted_reason") or decision["reason"]
                omissions.append({"citation_id": cit["citation_id"], "reason": reason})
                out.append(f"- 原文抜粋は出力されません（{reason}）。"
                           f"資料: {_md(doc.get('landing_url') or '')}")
            if cit.get("user_annotation"):
                out.append(f"- 研究者注釈: {_md(cit['user_annotation'])}")
            out.append("")
    if comparisons:
        out += ["## 文献比較", ""]
        for comp in comparisons:
            out.append(f"### {_md(comp.get('title') or '比較')}")
            out.append(f"- 意味比較: {_md(comp.get('semantic_status'))}（辞書概念の一致は意味の一致を意味しません）")
            shared = (comp.get("dictionary_concept_overlap") or {}).get("shared_concepts") or []
            if shared:
                out.append(f"- 共通概念候補: {', '.join(_md(s) for s in shared[:20])}")
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
    for doc in documents:
        rights = doc.get("rights_snapshot") or {}
        out.append(f"- [{keys[doc['saved_document_id']]}] 権利: {_md(rights.get('statement') or 'unknown')}"
                   f"（区分: {_md(evaluate_rights(rights.get('statement'))['category'])}）")
    for omission in omissions:
        out.append(f"- 抜粋省略: {omission['citation_id']} — {omission['reason']}")
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
