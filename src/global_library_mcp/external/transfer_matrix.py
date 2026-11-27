"""Per-library external-transfer matrix (b9 brief section 13).

One entry per implemented adapter. Values are
``allowed`` / ``restricted`` / ``unknown`` per content kind:

- ``metadata``: minimal bibliographic fields (title, author,
  year, language, provider) via the library's official API;
- ``reference_url``: the item's landing/original reference URL;
- ``ocr_excerpt``: a short verbatim OCR excerpt;
- ``image_url``: an original-image URL;
- ``third_party_ai``: whether the library's terms explicitly
  contemplate sending content to a third-party AI service.

OCR full text and original-image binaries are prohibited for
every library by policy (they are not matrix columns).

Grounding rule (brief section 13): a cell is ``allowed`` only
where the library's official API/terms permit that use; where
the official material does not address the use, the cell is
``unknown`` and the policy treats it as not permitted for
anything beyond minimal reference data. ``source`` records the
official page the judgement rests on and ``checked`` the date
it was confirmed for this matrix (2026-11-27, from the
project's recorded terms research in libraries.yaml /
docs/library-rights-normalization.md plus the official API
terms pages). Item-level rights statements always apply on
top of this matrix: the matrix can only restrict further,
never loosen an item's own rights.
"""

from __future__ import annotations

CHECKED = "2026-11-27"

# library_id -> {kind: value, ..., attribution, commercial,
#                item_check_required, source}
MATRIX: dict[str, dict[str, str]] = {
    "ndl": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "National Diet Library Digital Collections",
        "commercial": "restricted by NDL terms; item rights govern",
        "item_check_required": "yes",
        "source": "https://dl.ndl.go.jp/ (NDL Digital Collections terms of use)",
    },
    "internet-archive": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Internet Archive",
        "commercial": "item rights govern; lending items restricted",
        "item_check_required": "yes",
        "source": "https://archive.org/about/terms.php",
    },
    "loc": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Library of Congress",
        "commercial": "item rights govern (Rights & Restrictions)",
        "item_check_required": "yes",
        "source": "https://www.loc.gov/legal/",
    },
    "bsb": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Bayerische Staatsbibliothek / MDZ",
        "commercial": "provider/item-specific (registry terms_rights)",
        "item_check_required": "yes",
        "source": "https://www.digitale-sammlungen.de/en/ (MDZ terms)",
    },
    "ddb": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Deutsche Digitale Bibliothek",
        "commercial": "API terms: commercial use, credit and bulk-access conditions apply",
        "item_check_required": "yes",
        "source": "https://www.deutsche-digitale-bibliothek.de/content/api (API terms)",
    },
    "gallica": {
        "metadata": "restricted",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "BnF / Gallica",
        "commercial": "BnF terms restrict commercial use, mining and harvesting",
        "item_check_required": "yes",
        "source": "https://gallica.bnf.fr/ (BnF reuse conditions)",
    },
    "europeana": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Europeana and the providing institution",
        "commercial": "item rights statement governs (Europeana Rights Framework)",
        "item_check_required": "yes",
        "source": "https://www.europeana.eu/en/rights (Rights Framework)",
    },
    "e-rara": {
        "metadata": "unknown",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "e-rara / ETH-Bibliothek",
        "commercial": "unknown - not confirmed from official terms",
        "item_check_required": "yes",
        "source": "https://www.e-rara.ch/ (terms not confirmed for API transfer)",
    },
    "finna": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Finna / the providing organisation",
        "commercial": "metadata CC0; item rights are the provider's, not CC0",
        "item_check_required": "yes",
        "source": "https://www.finna.fi/Content/api (Finna API; metadata CC0)",
    },
    "finland-nl-digi": {
        "metadata": "unknown",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "National Library of Finland",
        "commercial": "unknown - digi service terms not confirmed for transfer",
        "item_check_required": "yes",
        "source": "https://digi.kansalliskirjasto.fi/ (terms not confirmed)",
    },
    "dpla": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "DPLA and the providing institution",
        "commercial": "metadata CC0; item rights via RightsStatements.org govern",
        "item_check_required": "yes",
        "source": "https://dp.la/info/developers/codex/policies (DPLA API policies)",
    },
    "kb-delpher": {
        "metadata": "restricted",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "KB, national library of the Netherlands / Delpher",
        "commercial": "KB terms restrict reuse; item rights govern",
        "item_check_required": "yes",
        "source": "https://www.delpher.nl/ (KB terms of use)",
    },
    "japan-search": {
        "metadata": "allowed",
        "reference_url": "allowed",
        "ocr_excerpt": "restricted",
        "image_url": "restricted",
        "third_party_ai": "unknown",
        "attribution": "Japan Search / the providing organisation",
        "commercial": "per-item accessInfo licence and restrictions govern",
        "item_check_required": "yes",
        "source": "https://jpsearch.go.jp/ (Japan Search terms; per-item accessInfo)",
    },
}

_KINDS = ("metadata", "reference_url", "ocr_excerpt", "image_url", "third_party_ai")


def matrix_entry(library_id: str) -> dict[str, str]:
    """The matrix row for a library; unlisted libraries are all
    ``unknown`` (fail-closed)."""
    entry = MATRIX.get(library_id)
    if entry is None:
        return {kind: "unknown" for kind in _KINDS} | {
            "attribution": "",
            "commercial": "unknown",
            "item_check_required": "yes",
            "source": "",
        }
    return entry


def transfer_allowed(library_id: str, kind: str) -> bool:
    return matrix_entry(library_id).get(kind) == "allowed"
