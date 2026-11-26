"""Document-language normalisation (b6 final review, section 11).

Library metadata expresses language in many shapes: ISO 639-1
(ja), 639-2/T (jpn), 639-2/B (ger), English names (Japanese),
endonyms (Deutsch, français) and Japanese names (日本語). Filters
must compare normalised codes, never raw strings, and an
unrecognised value is UNKNOWN - it is never counted as a match
for a requested language and never guessed from the holding
institution's country. The raw metadata value is always kept
alongside the normalised one.
"""
from __future__ import annotations

from typing import Any

# canonical code -> accepted surface forms (lower-cased)
_ALIASES: dict[str, set[str]] = {
    "ja": {"ja", "jpn", "japanese", "日本語", "にほんご"},
    "en": {"en", "eng", "english", "英語", "えいご"},
    "de": {"de", "deu", "ger", "german", "deutsch", "ドイツ語", "どいつご"},
    "fr": {"fr", "fra", "fre", "french", "français", "francais", "フランス語"},
    "zh": {"zh", "chi", "zho", "chinese", "中国語", "中文"},
    "ko": {"ko", "kor", "korean", "韓国語", "朝鮮語"},
    "es": {"es", "spa", "spanish", "español", "espanol", "スペイン語"},
    "it": {"it", "ita", "italian", "italiano", "イタリア語"},
    "ru": {"ru", "rus", "russian", "русский", "ロシア語"},
    "la": {"la", "lat", "latin", "ラテン語"},
    "nl": {"nl", "nld", "dut", "dutch", "nederlands", "オランダ語"},
    "pt": {"pt", "por", "portuguese", "português", "ポルトガル語"},
}

_LOOKUP: dict[str, str] = {}
for _code, _forms in _ALIASES.items():
    for _form in _forms:
        _LOOKUP[_form] = _code

SUPPORTED = tuple(_ALIASES.keys())


def normalize_language(value: Any) -> list[str]:
    """Normalise a raw language value (string, list, compound
    string like 'eng; ger', or missing) to a list of ISO 639-1
    codes. Unrecognised parts are dropped; an empty result means
    the language is unknown."""
    if value is None:
        return []
    parts: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            parts.extend(normalize_language(item))
        return list(dict.fromkeys(parts))
    text = str(value).strip().lower()
    if not text:
        return []
    for chunk in text.replace(";", " ").replace(",", " ").replace("/", " ").split():
        code = _LOOKUP.get(chunk)
        if code and code not in parts:
            parts.append(code)
    if not parts:
        code = _LOOKUP.get(text)
        if code:
            parts.append(code)
    return parts


def language_matches(value: Any, requested: list[str]) -> bool | None:
    """True/False when the record's language is known; None when
    it is unknown (unknown never counts as a match)."""
    codes = normalize_language(value)
    if not codes:
        return None
    wanted = {c for code in requested for c in normalize_language(code)}
    return bool(set(codes) & wanted)
