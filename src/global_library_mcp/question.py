"""Rule-based question understanding.

Decomposes a natural-language question into the elements the
relevance gate needs: core concepts (what the question is actually
about), generic/peripheral terms (words that prove nothing on their
own), era, region, intent, and the concrete requirements evidence
must satisfy.

This is deliberately rule-based and testable: no LLM is required.
The analysis object is a plain dataclass so a future LLM-based
analyser can replace `analyze_question` without touching the gate.

Orthography: matching must survive old/new character forms
(發電 vs 発電), historical kana (ゐ/ゑ), and conservative synonym
groups (水力電気 is period vocabulary for hydroelectric generation;
水車 and turbine are only *weakly* linked, context permitting).
Synonym groups are curated and small on purpose: treating different
concepts as synonyms would manufacture relevance.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from global_library_mcp.evidence import extract_terms

# --- normalisation -------------------------------------------------------

_CHAR_VARIANTS = str.maketrans({
    "發": "発", "氣": "気", "體": "体", "澤": "沢", "廣": "広", "應": "応",
    "區": "区", "會": "会", "國": "国", "學": "学", "濟": "済", "醫": "医",
    "藥": "薬", "鐵": "鉄", "驛": "駅", "廳": "庁", "縣": "県", "臺": "台",
    "灣": "湾", "滿": "満", "亞": "亜", "歐": "欧", "獨": "独", "佛": "仏",
    "龍": "竜", "齒": "歯", "邊": "辺", "關": "関", "圖": "図", "號": "号",
    "點": "点", "實": "実", "價": "価", "勞": "労", "壓": "圧", "變": "変",
    "黨": "党", "單": "単", "戰": "戦", "觀": "観", "覽": "覧", "顯": "顕",
    "驗": "験", "驅": "駆", "澁": "渋", "櫻": "桜", "舊": "旧", "莊": "荘",
    "乘": "乗", "亂": "乱", "淨": "浄", "增": "増", "寬": "寛", "德": "徳",
    "聽": "聴", "聲": "声", "賣": "売", "買": "買", "來": "来", "東": "東",
    "ゐ": "い", "ゑ": "え", "ヰ": "イ", "ヱ": "エ", "づ": "ず", "ぢ": "じ",
})


def normalize_text(text: str) -> str:
    """NFKC + old-form kanji/kana folding + lowercase, for matching."""
    folded = unicodedata.normalize("NFKC", text or "")
    return folded.translate(_CHAR_VARIANTS).lower()


# --- synonyms (conservative, curated) -------------------------------------

SYNONYM_GROUPS: dict[str, set[str]] = {
    "水力発電": {"水力発電", "水力電気", "発電水力", "hydroelectricity", "hydroelectric", "hydro-electric power"},
    "発電": {"発電", "power generation", "electric generation"},
    "鉄道": {"鉄道", "railway", "railroad"},
    "電信": {"電信", "telegraph"},
    "電話": {"電話", "telephone"},
    "蒸気機関": {"蒸気機関", "蒸汽機関", "steam engine"},
    "活版印刷": {"活版印刷", "letterpress", "活字印刷"},
    "地震": {"地震", "earthquake"},
    "写真": {"写真", "photograph", "photography"},
    "水車": {"水車", "water wheel", "waterwheel"},
    "タービン": {"タービン", "turbine"},
    "送電": {"送電", "power transmission", "electric transmission"},
    "電灯": {"電灯", "electric light", "electric lighting"},
    "ガス灯": {"ガス灯", "gas light", "gaslight"},
    "紡績": {"紡績", "spinning", "cotton spinning"},
    "種痘": {"種痘", "痘種", "牛痘"},
}

# Context-dependent near-synonyms: counted as weak evidence only.
WEAK_LINKS: dict[str, set[str]] = {
    "水車": {"タービン", "turbine"},
    "タービン": {"水車"},
}

_CANONICAL_OF: dict[str, str] = {}
for _canonical, _members in SYNONYM_GROUPS.items():
    for _member in _members:
        _CANONICAL_OF[normalize_text(_member)] = _canonical


def concept_variants(concept: str, *, include_weak: bool = False) -> set[str]:
    """All normalised surface forms that may realise a concept."""
    normalised = normalize_text(concept)
    variants = {normalised}
    canonical = _CANONICAL_OF.get(normalised)
    if canonical:
        variants |= {normalize_text(member) for member in SYNONYM_GROUPS[canonical]}
        if include_weak:
            variants |= {normalize_text(member) for member in WEAK_LINKS.get(canonical, set())}
    return variants


def find_concept(text_normalised: str, concept: str) -> str | None:
    """Return the matched variant of a concept in normalised text."""
    for variant in sorted(concept_variants(concept), key=len, reverse=True):
        if variant and variant in text_normalised:
            return variant
    return None


# --- question element vocabularies -----------------------------------------

GENERIC_TERMS = {
    "時代", "歴史", "通信", "原理", "影響", "発達", "発展", "普及", "制度",
    "社会", "文化", "科学", "記録", "資料", "説明", "記述", "内容", "方法",
    "事業", "関係", "状況", "様子", "当時", "日本", "技術", "産業", "明治時代",
    "大正時代", "昭和時代", "変化", "様相", "概要", "始まり", "導入", "建設",
}

ERAS: dict[str, tuple[int, int]] = {
    "江戸": (1603, 1868), "慶応": (1865, 1868), "明治": (1868, 1912),
    "大正": (1912, 1926), "昭和": (1926, 1989), "平成": (1989, 2019),
    "令和": (2019, 2100),
}
_ERA_YEAR_RE = re.compile(r"(明治|大正|昭和|平成|慶応)([一二三四五六七八九十]+)年")
_KANJI_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _kanji_number(text: str) -> int | None:
    if text in _KANJI_DIGITS:
        return _KANJI_DIGITS[text]
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _KANJI_DIGITS.get(left, 1) if left else 1
        ones = _KANJI_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


REGIONS: dict[str, str] = {
    "日本": "日本", "米国": "米国", "アメリカ": "米国", "合衆国": "米国",
    "ドイツ": "ドイツ", "独逸": "ドイツ", "フランス": "フランス", "仏蘭西": "フランス",
    "イギリス": "英国", "英国": "英国", "英吉利": "英国",
    "中国": "中国", "清国": "中国", "韓国": "韓国", "朝鮮": "朝鮮",
    "ロシア": "ロシア", "露西亜": "ロシア", "オランダ": "オランダ", "和蘭": "オランダ",
    "イタリア": "イタリア", "スペイン": "スペイン",
}

_INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("comparison", ("比較", "違い", "相違", "比べ", "変化したか", "どのように変化")),
    ("cause", ("原因", "なぜ", "理由", "どうして", "要因")),
    ("effect", ("影響", "与えた", "及ぼした", "もたらした")),
    ("numeric", ("人口", "何人", "何名", "いくら", "正確な", "何年", "何月", "何日", "数値", "何台", "何軒")),
    ("quotation", ("原文", "引用", "どのように述べて", "どう述べて")),
]

_SUFFIXES = ("技術", "制度", "事業", "産業", "史", "学")
_KATAKANA_RE = re.compile(r"[ァ-ヶー]{3,}")
_QUOTED_RE = re.compile(r"「([^」]{2,})」")


@dataclass
class QuestionAnalysis:
    raw: str
    terms: list[str]
    core_concepts: list[str]
    generic_terms: list[str]
    era: dict[str, Any] | None
    regions: list[str]
    intent: str
    requirements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw, "terms": self.terms, "core_concepts": self.core_concepts,
            "generic_terms": self.generic_terms, "era": self.era, "regions": self.regions,
            "intent": self.intent, "requirements": self.requirements,
        }


def _detect_era(question: str) -> dict[str, Any] | None:
    match = _ERA_YEAR_RE.search(question)
    if match:
        era_name, number = match.group(1), _kanji_number(match.group(2))
        if number:
            start = ERAS[era_name][0]
            return {"label": f"{era_name}{match.group(2)}年", "era": era_name, "year": start + number - 1,
                    "start": ERAS[era_name][0], "end": ERAS[era_name][1]}
    for name, (start, end) in ERAS.items():
        if name in question:
            return {"label": name, "era": name, "year": None, "start": start, "end": end}
    year_match = re.search(r"(1[5-9]\d{2}|20\d{2})年", question)
    if year_match:
        year = int(year_match.group(1))
        return {"label": f"{year}年", "era": None, "year": year, "start": year, "end": year}
    century = re.search(r"(\d{1,2})世紀", question)
    if century:
        c = int(century.group(1))
        return {"label": f"{c}世紀", "era": None, "year": None, "start": (c - 1) * 100 + 1, "end": c * 100}
    return None


def analyze_question(question: str) -> QuestionAnalysis:
    raw = question or ""
    terms = extract_terms(raw)
    era = _detect_era(raw)
    regions: list[str] = []
    for surface, canonical in REGIONS.items():
        if surface in raw and canonical not in regions:
            regions.append(canonical)
    intent = "explanation"
    for name, keywords in _INTENT_KEYWORDS:
        if any(keyword in raw for keyword in keywords):
            intent = name
            break

    era_words = set(ERAS) | {"明治時代", "大正時代", "昭和時代", "江戸時代"}
    region_words = set(REGIONS)
    core: list[str] = []
    generic: list[str] = []
    candidates: list[str] = []
    candidates.extend(_QUOTED_RE.findall(raw))
    candidates.extend(_KATAKANA_RE.findall(raw))
    candidates.extend(terms)
    for candidate in candidates:
        if candidate in era_words or candidate in region_words:
            continue
        if candidate in GENERIC_TERMS:
            if candidate not in generic:
                generic.append(candidate)
            continue
        if candidate not in core:
            core.append(candidate)
        # A shortened form without a generic suffix is often the real
        # concept (水力発電技術 -> 水力発電); register it as an alias.
        for suffix in _SUFFIXES:
            if candidate.endswith(suffix) and len(candidate) - len(suffix) >= 2:
                alias = candidate[: -len(suffix)]
                if alias not in core:
                    core.append(alias)
                break

    requirements: list[dict[str, Any]] = [{"type": "core_concept", "concept": c} for c in core]
    if era:
        requirements.append({"type": "era", "label": era["label"], "start": era["start"], "end": era["end"]})
    for region in regions:
        requirements.append({"type": "region", "region": region})
    if intent == "numeric":
        requirements.append({"type": "numeric"})
    return QuestionAnalysis(raw=raw, terms=terms, core_concepts=core, generic_terms=generic,
                            era=era, regions=regions, intent=intent, requirements=requirements)
