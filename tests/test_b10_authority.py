"""b10 Stage 2: AuthorityResolver (brief sections 12-15).

Live-source tests use fixture payloads shaped exactly like the real
lobid GND responses captured 2026-11-28; no test performs network
access.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_library_mcp import service as _LS  # noqa: F401,E402  (import order)
from global_library_mcp.authority import (  # noqa: E402
    AuthorityResolver, GndSource, ViafSource, WikidataSource,
    editions_of, identify_edition)


def _gnd_payload(members):
    return {"totalItems": len(members), "member": members}


_DARWINS = _gnd_payload([
    {"id": "https://d-nb.info/gnd/118523813",
     "preferredName": "Darwin, Charles",
     "dateOfBirth": ["1809-02-12"], "dateOfDeath": ["1882-04-19"]},
    {"id": "https://d-nb.info/gnd/118671049",
     "preferredName": "Darwin, Erasmus",
     "dateOfBirth": ["1731-12-12"], "dateOfDeath": ["1802-04-18"]},
    {"id": "https://d-nb.info/gnd/122406761",
     "preferredName": "Darwin, Charles",
     "dateOfBirth": ["1758-09-03"], "dateOfDeath": ["1778-05-15"]},
])


def _resolver_with(payload_by_q):
    def fetch(url):
        for key, payload in payload_by_q.items():
            if key in url:
                return payload
        raise AssertionError(f"unexpected url {url}")

    return AuthorityResolver(live_sources=[GndSource(fetch=fetch)])


def test_charles_vs_erasmus_and_namesake():
    resolver = _resolver_with({"Darwin": _DARWINS})
    res = resolver.resolve_person("Charles Darwin", birth_year=1809,
                                  death_year=1882)
    assert res.status == "authority_verified"
    top = res.candidates[0]
    assert top.record.authority_id == "gnd:118523813"
    # the 1758 namesake is hard-excluded by the year conflict
    excluded = [c for c in res.candidates if c.excluded_reason]
    assert any("122406761" in c.record.authority_id for c in excluded)


def test_surname_only_is_ambiguous():
    resolver = _resolver_with({"Darwin": _DARWINS})
    res = resolver.resolve_person("Darwin")
    assert res.status in ("ambiguous", "insufficient_metadata")
    assert res.status != "authority_verified"


def test_year_conflict_never_verifies():
    resolver = _resolver_with({"Darwin": _DARWINS})
    res = resolver.resolve_person("Charles Darwin", birth_year=1731)
    top_ids = [c.record.authority_id for c in res.candidates
               if not c.excluded_reason]
    assert "gnd:118523813" not in top_ids  # 1809 excluded by 1731


def test_local_weber_disambiguation():
    resolver = AuthorityResolver()
    res = resolver.resolve_person("Max Weber", birth_year=1864, death_year=1920)
    assert res.status == "authority_verified"
    assert res.candidates[0].record.authority_id == "author:weber-max"
    res2 = resolver.resolve_person("Alfred Weber", birth_year=1868,
                                   death_year=1958)
    assert res2.candidates[0].record.authority_id == "author:weber-alfred"


def test_local_japanese_name_forms():
    resolver = AuthorityResolver()
    res = resolver.resolve_person("夏目漱石", birth_year=1867, death_year=1916)
    assert res.candidates[0].record.authority_id == "author:soseki"
    assert res.candidates[0].record.external_identifiers.get("gnd") == "118785737"


def test_work_resolution_across_languages():
    resolver = AuthorityResolver()
    res = resolver.resolve_work("純粋理性批判")
    assert res.candidates[0].record.authority_id == "work:kritik-reinen-vernunft"
    assert res.candidates[0].record.canonical_name == "Kritik der reinen Vernunft"
    res2 = resolver.resolve_work("Über die Entstehung der Arten",
                                 author_hint="Charles Darwin")
    assert res2.candidates[0].record.authority_id == "work:origin-of-species"
    assert "author_hint_match" in res2.candidates[0].signals


def test_editions_never_merge():
    a = identify_edition("work:kritik-reinen-vernunft", 1781)
    b = identify_edition("work:kritik-reinen-vernunft", 1787)
    assert a["edition_code"] == "A" and b["edition_code"] == "B"
    assert a["edition_id"] != b["edition_id"]
    assert a["shares_pages_with_other_editions"] is False
    assert identify_edition("work:kritik-reinen-vernunft", 1783) is None
    assert identify_edition("work:origin-of-species", 1859)["edition_code"] == "1"
    assert identify_edition("work:origin-of-species", 1872)["edition_code"] == "6"
    assert len(editions_of("work:origin-of-species")) == 6


def test_wikidata_fixture_parse():
    payload = {"search": [{"id": "Q180903", "label": "Natsume Sōseki",
                           "aliases": ["夏目漱石"]}]}
    src = WikidataSource(fetch=lambda url: payload)
    records = src.search_person("夏目漱石")
    assert records[0].authority_id == "wikidata:Q180903"


def test_viaf_fixture_parse():
    payload = {"result": [{"nametype": "personal",
                           "term": "Kant, Immanuel, 1724-1804",
                           "viafid": "73913242"}]}
    src = ViafSource(fetch=lambda url: payload)
    records = src.search_person("Immanuel Kant")
    assert records[0].birth_year == 1724 and records[0].death_year == 1804


def test_source_failure_is_unavailable_not_crash():
    def boom(url):
        raise RuntimeError("network down")

    resolver = AuthorityResolver(live_sources=[GndSource(fetch=boom)])
    res = resolver.resolve_person("Nonexistent Person Zzz")
    assert res.status in ("unavailable", "insufficient_metadata")
    assert any("unavailable" in n for n in res.notes)
