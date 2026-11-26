"""Real-use scenarios 1-9 for b8 (brief section 20).

Composition: the REAL web server, REAL WorkspaceApi, REAL
LibraryService, REAL adapters (Finna / Digi / KB / DPLA) and
REAL SQLite run together; upstream library APIs are fixed
fixtures (the same composition as section 23's integration
tests), EXCEPT where a stage is marked live - the KB live
results and the Finna/Gallica live failures are recorded in
docs/b8-live-verification.md and are not re-run here. Two
clearly-labelled stub adapters stand in for (7) a
rights-permitting source and (8) two institutions sharing one
record_id; the mechanisms exercised are source-agnostic.

Each scenario records its stages independently: a failed
stage is reported, never smoothed over.

Usage:
  .venv/bin/python eval/b8_scenarios.py --out eval/results-b8-scenarios.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx  # noqa: E402

from global_library_mcp.service import LibraryService  # noqa: E402  (import order)
import global_library_mcp.web.server as server_mod  # noqa: E402
from global_library_mcp.adapters.base import LibraryAdapter  # noqa: E402
from global_library_mcp.adapters.digi import DigiAdapter  # noqa: E402
from global_library_mcp.adapters.dpla import DplaAdapter  # noqa: E402
from global_library_mcp.adapters.finna import FinnaAdapter  # noqa: E402
from global_library_mcp.adapters.kb import KbDelpherAdapter  # noqa: E402
from global_library_mcp.handoff import extract_digi_candidate, titles_correspond  # noqa: E402
from global_library_mcp.models import Rights, SearchResult  # noqa: E402
from global_library_mcp.web.workspace_api import WorkspaceWebRuntime  # noqa: E402
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402

KB_SRU = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcx="http://krait.kb.nl/coop/tel/handbook/telterms.html">
<srw:version>1.2</srw:version><srw:numberOfRecords>1</srw:numberOfRecords>
<srw:records><srw:record><srw:recordPacking>xml</srw:recordPacking>
<srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
<srw:recordData><dc:date>1937/08/28 00:00:00</dc:date><dc:identifier>http://resolver.kb.nl/resolve?urn=ddd:010286065:mpeg21:a0141:ocr</dc:identifier><dc:publisher>[ s.n.]</dc:publisher><dc:source>KB C 248</dc:source><dc:title>Waterkracht-centrale.</dc:title><dc:type>artikel</dc:type><dcx:issued>1921</dcx:issued></srw:recordData>
<srw:recordPosition>1</srw:recordPosition></srw:record></srw:records>
</srw:searchRetrieveResponse>
"""
KB_OCR = """<?xml version="1.0" encoding="UTF-8"?>
<text><title>Waterkracht-centrale.</title><p>Deze centrale werkt met waterkracht en irrigatie.</p></text>
"""
DIGI_OAI = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <responseDate>2026-11-26T00:00:00Z</responseDate>
 <GetRecord><record>
  <header><identifier>oai:digi.kansalliskirjasto.fi:123456</identifier><datestamp>2024-01-01</datestamp></header>
  <metadata><qdc xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:kk="http://www.kansalliskirjasto.fi/kk">
   <dc:title>Uusi Suometar 1900-01-02</dc:title><dc:date>1900-01-02</dc:date>
   <dc:language>fin</dc:language><dc:rights>Tekijänoikeuden alainen</dc:rights>
   <kk:file bundle="ORIGINAL" href="https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456/pdf" type="application/pdf" />
   <kk:checksum filetype="application/xml+alto" pagenumber="1" value="abc123" />
   <kk:checksum filetype="application/xml+alto" pagenumber="2" value="def456" />
  </qdc></metadata>
 </record></GetRecord>
</OAI-PMH>
"""
DIGI_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description><sourceImageInformation><fileName>123456_0001.jp2</fileName></sourceImageInformation></Description>
 <Layout><Page ID="Page1" PHYSICAL_IMG_NR="1"><PrintSpace>
 <TextBlock ID="b1"><TextLine ID="l1"><String CONTENT="Suomen" /><String CONTENT="historia" /></TextLine></TextBlock>
 <TextBlock ID="b2"><TextLine ID="l2"><String CONTENT="vesivoima" /><String CONTENT="ja" /><String CONTENT="teollisuus" /></TextLine></TextBlock>
 </PrintSpace></Page></Layout>
</alto>
"""
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
FINNA_SEARCH = {
    "resultCount": 1, "status": "OK",
    "records": [{"id": "helle.687105", "title": "Suomen historia", "usageRights": [],
                 "languages": ["fin"], "formats": [{"value": "0/Book/", "translated": "Kirja"}],
                 "buildings": [{"value": "0/Helle/", "translated": "Helle-kirjastot"}],
                 "authors": {"primary": {"Historiankirjoittaja, Esimerkki": {}}}, "year": 2020}],
}
FINNA_RECORD = {
    "resultCount": 1, "status": "OK",
    "records": [{"id": "kansalliskirjasto.123456", "title": "Uusi Suometar", "usageRights": [],
                 "languages": ["fin"], "formats": [{"value": "0/Journal/", "translated": "Lehti"}],
                 "buildings": [{"value": "0/Kansalliskirjasto/", "translated": "Kansalliskirjasto"}],
                 "onlineUrls": [{"url": "https://digi.kansalliskirjasto.fi/sanomalehti/binding/123456", "text": "Digi"}],
                 "year": 1900}],
}


def upstream_handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "jsru.kb.nl":
        return httpx.Response(200, text=KB_SRU, headers={"content-type": "text/xml"})
    if host == "resolver.kb.nl":
        if request.url.params.get("urn", "").endswith(":ocr"):
            return httpx.Response(200, text=KB_OCR, headers={"content-type": "text/xml"})
        return httpx.Response(404, text="no")
    if host == "api.finna.fi":
        return httpx.Response(200, json=FINNA_RECORD if path == "/api/v1/record" else FINNA_SEARCH)
    if host == "digi.kansalliskirjasto.fi":
        if path == "/interfaces/OAI-PMH":
            return httpx.Response(200, text=DIGI_OAI, headers={"content-type": "text/xml"})
        if path.endswith("/page-1.xml"):
            return httpx.Response(200, text=DIGI_ALTO, headers={"content-type": "text/xml"})
        if "/image/" in path:
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404, text="not found")
    return httpx.Response(404, text="not found")


class StubAdapter(LibraryAdapter):
    """Fixed-data stub (scenarios 7-8 only; labelled as such)."""

    supports_in_document_search = True

    def __init__(self, library_id: str, name: str, text: str, statement: str = "Public Domain"):
        self.library_id = library_id
        self.library_name = name
        self._text = text
        self._statement = statement

    async def search(self, query, limit=10):
        return [SearchResult(library_id=self.library_id, library_name=self.library_name,
                             record_id="rec", title=f"Stub {self.library_id}",
                             landing_url=f"https://example.org/{self.library_id}/rec",
                             rights=Rights(statement=self._statement))]

    async def get_document(self, record_id):
        return {"library_id": self.library_id, "record_id": record_id,
                "title": f"Stub {self.library_id}",
                "landing_url": f"https://example.org/{self.library_id}/rec",
                "rights": {"statement": self._statement},
                "pages": [{"page_id": f"{record_id}@1"}]}

    async def get_page_text(self, page_id):
        return {"page_id": page_id, "record_id": page_id.split("@")[0],
                "library_id": self.library_id, "contents": self._text,
                "verified_mapping": True,
                "image_url": "https://example.org/img.jpg",
                "rights": {"statement": self._statement}}

    async def search_in_document(self, record_id, query, limit=20):
        # Fixture behaviour (like the b7 fixture adapter): the
        # single fixed page is always returned as the match.
        return {"matches": {"list": [{"id": f"{record_id}@1", "page_id": f"{record_id}@1"}]}}

    async def verify_original(self, page_id):
        return {"status": "verified", "checks": {"image_reachable": {"ok": True}}}


class Harness:
    def __init__(self, tmp: Path):
        server_mod.RATE_LIMITER._hits.clear()
        self.store = WorkspaceStore(tmp / "w.db")
        ws = WorkspaceWebRuntime(self.store)
        self.service = server_mod.RUNTIME.service
        self._old_ws = server_mod.RUNTIME.ws
        self._old_adapters = self.service.adapters
        self._old_defaults = self.service.default_libraries
        client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
        server_mod.RUNTIME.ws = ws
        self.service.adapters = {
            "finna": FinnaAdapter(client),
            "finland-nl-digi": DigiAdapter(client),
            "kb-delpher": KbDelpherAdapter(client),
            "dpla": DplaAdapter(client),
            "stub-pd": StubAdapter("stub-pd", "Stub PD", "alpha passage about water power and dams"),
            "stub-a": StubAdapter("stub-a", "Stub A", "passage from stub a about rivers"),
            "stub-b": StubAdapter("stub-b", "Stub B", "passage from stub b about rivers"),
        }
        self.service.default_libraries = ["finna"]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with self.opener.open(self.base + "/", timeout=30) as res:
            html = res.read().decode()
        self.csrf = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)

    def close(self):
        self.httpd.shutdown()
        server_mod.RUNTIME.ws = self._old_ws
        self.service.adapters = self._old_adapters
        self.service.default_libraries = self._old_defaults
        self.store.close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if method in ("POST", "PUT", "DELETE"):
            headers["X-GLM-CSRF"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=60) as res:
                payload = res.read()
                try:
                    return res.status, json.loads(payload.decode() or "{}")
                except (ValueError, UnicodeDecodeError):
                    return res.status, {"_text": payload.decode("utf-8", "replace")}
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                return exc.code, json.loads(payload.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return exc.code, {"_text": payload.decode("utf-8", "replace")}


def q(**params):
    return urllib.parse.urlencode(params)


async def _adapter_level(h: Harness) -> dict:
    """Scenario 3 and 5 stages that live below the HTTP layer."""
    out: dict = {}
    from global_library_mcp.discovery import analyze_discovery_query
    from global_library_mcp.expansion import QueryExpansionEngine

    plan = QueryExpansionEngine().expand(analyze_discovery_query("フィンランド語の新聞"), mode="deep")
    variants = {(v["language"], v["text"]) for v in plan["variants"]}
    plan2 = QueryExpansionEngine().expand(analyze_discovery_query("鉄道の歴史"), mode="deep")
    variants2 = {(v["language"], v["text"]) for v in plan2["variants"]}
    out["scenario3_expansion"] = {
        "fi_variant_for_newspaper_query": ("fi", "sanomalehti") in variants,
        "sv_variant_for_railway_query": ("sv", "järnväg") in variants2,
        "nl_variant_for_railway_query": ("nl", "spoorweg") in variants2,
    }
    finna = h.service.adapters["finna"]
    doc = await finna.get_document("kansalliskirjasto.123456")
    candidate = extract_digi_candidate(doc)
    digi = h.service.adapters["finland-nl-digi"]
    digidoc = await digi.get_document(candidate["binding_id"]) if candidate["status"] == "candidate" else {}
    out["scenario5_handoff"] = {
        "candidate_status": candidate["status"],
        "binding_id": candidate.get("binding_id"),
        "titles_correspond": titles_correspond(doc["title"], digidoc.get("title") or ""),
        "genre_matches": digidoc.get("genre") == candidate.get("genre"),
    }
    return out


def run(tmp: Path) -> dict:
    h = Harness(tmp)
    report: dict = {}
    try:
        # project shared by the HTTP scenarios
        status, project = h.call("POST", "/api/workspace/projects", {"title": "b8シナリオ"})
        pid = project["project_id"]

        # -- Scenario 1: Finna search -> save -> BibTeX ----------
        s, payload = h.call("GET", "/api/search?" + q(q="Suomen historia", libraries="finna"))
        token = payload["results"][0]["save_token"]
        s, doc = h.call("POST", "/api/workspace/documents", {"project_id": pid, "save_token": token})
        s, bib = h.call("GET", "/api/workspace/export/documents?" + q(project_id=pid, format="bibtex"))
        report["scenario1_finna_save_bibtex"] = {
            "search": bool(payload["results"]),
            "save": doc.get("title") == "Suomen historia",
            "bibtex_contains": "Suomen historia" in bib.get("_text", ""),
            "basis": "fixture (Finna live blocked by a bot challenge from the server network)",
        }
        finna_doc_id = doc["saved_document_id"]

        # -- Scenario 2: Digi newspaper OCR/original/citation ----
        s, detail = h.call("GET", "/api/document?" + q(library="finland-nl-digi", id="123456"))
        s, page = h.call("GET", "/api/page?" + q(library="finland-nl-digi", id="123456@1"))
        s, verify = h.call("GET", "/api/verify?" + q(library="finland-nl-digi", id="123456@1"))
        s, digi_doc = h.call("POST", "/api/workspace/documents",
                             {"project_id": pid, "save_token": detail["save_token"]})
        s, cit = h.call("POST", "/api/workspace/citations",
                        {"project_id": pid, "save_token": page["save_token"],
                         "saved_document_id": digi_doc["saved_document_id"],
                         "excerpt": "Suomen historia"})
        report["scenario2_digi_newspaper"] = {
            "document": detail.get("title") == "Uusi Suometar 1900-01-02",
            "page_verified_mapping": page.get("verified_mapping"),
            "verify_status": verify.get("status"),
            "citation_saved": bool(cit.get("citation_id")),
            "excerpt_stored": cit.get("excerpt_stored"),
            "note": "rights are in-copyright (dc:rights verbatim), so the citation is stored as a reference; the excerpt text is withheld by policy",
            "basis": "fixture (Digi unreachable from the development network)",
        }

        # -- Scenario 4: hydro comparison KB x Digi ---------------
        s, compared = h.call("GET", "/api/compare?" + q(
            docs="kb-delpher:ddd:010286065:mpeg21:a0141;finland-nl-digi:123456",
            aspects="waterkracht,vesivoima"))
        s, kb_search = h.call("GET", "/api/search?" + q(q="waterkracht", libraries="kb-delpher"))
        s, kb_doc = h.call("POST", "/api/workspace/documents",
                           {"project_id": pid, "save_token": kb_search["results"][0]["save_token"]})
        s, comp = h.call("POST", "/api/workspace/comparisons",
                         {"project_id": pid, "title": "水力比較",
                          "saved_document_ids": [kb_doc["saved_document_id"], digi_doc["saved_document_id"]]})
        rows4 = compared.get("rows") or []
        report["scenario4_hydro_comparison"] = {
            "compare_status": compared.get("status"),
            "documents": compared.get("documents"),
            "rows": [
                {"aspect": row.get("aspect"),
                 "found": {key: cell.get("found") for key, cell in (row.get("documents") or {}).items()},
                 "shared_terms": row.get("shared_terms"),
                 "semantic_comparison": row.get("semantic_comparison")}
                for row in rows4
            ],
            "comparison_saved": bool(comp.get("comparison_id")),
            "semantic_status": comp.get("semantic_status"),
            "note": "cross-language comparison: each document is found under its own language's aspect term; no shared surface terms exist between the Dutch and Finnish texts and none are invented. NDL/IA adapters are unchanged in b8 and their comparison participation is covered by the existing compare regression suites; the b8 run adds the Digi (Nordic) and KB documents",
            "basis": "fixture upstreams; KB search/OCR separately live-verified",
        }

        # -- Scenario 6: unknown-rights reference-only ------------
        s, kb_page = h.call("GET", "/api/page?" + q(library="kb-delpher", id="ddd:010286065:mpeg21:a0141"))
        s, kb_cit = h.call("POST", "/api/workspace/citations",
                           {"project_id": pid, "save_token": kb_page["save_token"],
                            "saved_document_id": kb_doc["saved_document_id"],
                            "excerpt": "Deze centrale werkt met waterkracht"})
        report["scenario6_unknown_rights_reference_only"] = {
            "page_verified_mapping": kb_page.get("verified_mapping"),
            "citation_saved": bool(kb_cit.get("citation_id")),
            "excerpt_stored": kb_cit.get("excerpt_stored"),
            "excerpt_hash_kept": bool(kb_cit.get("excerpt_hash")),
            "basis": "fixture upstream; KB search/OCR separately live-verified",
        }

        # -- Scenario 7: permitted excerpt + reverify -------------
        s, pd_search = h.call("GET", "/api/search?" + q(q="water", libraries="stub-pd"))
        s, pd_doc = h.call("POST", "/api/workspace/documents",
                           {"project_id": pid, "save_token": pd_search["results"][0]["save_token"]})
        s, pd_page = h.call("GET", "/api/page?" + q(library="stub-pd", id="rec@1"))
        s, pd_cit = h.call("POST", "/api/workspace/citations",
                           {"project_id": pid, "save_token": pd_page["save_token"],
                            "saved_document_id": pd_doc["saved_document_id"],
                            "excerpt": "alpha passage about water power"})
        s, reverify = h.call("POST", f"/api/workspace/citations/{pd_cit['citation_id']}/reverify", {})
        report["scenario7_permitted_excerpt_reverify"] = {
            "excerpt_stored": pd_cit.get("excerpt_stored"),
            "excerpt_verbatim": pd_cit.get("original_excerpt") == "alpha passage about water power",
            "reverify_status": reverify.get("status"),
            "basis": "labelled stub adapter with a Public Domain statement (the mechanism is source-agnostic; the same flow ran live for IA in b7)",
        }

        # -- Scenario 8: same record_id, two institutions ---------
        s, a_search = h.call("GET", "/api/search?" + q(q="rivers", libraries="stub-a"))
        s, b_search = h.call("GET", "/api/search?" + q(q="rivers", libraries="stub-b"))
        s, a_doc = h.call("POST", "/api/workspace/documents",
                          {"project_id": pid, "save_token": a_search["results"][0]["save_token"]})
        s, b_doc = h.call("POST", "/api/workspace/documents",
                          {"project_id": pid, "save_token": b_search["results"][0]["save_token"]})
        s, comp8 = h.call("POST", "/api/workspace/comparisons",
                          {"project_id": pid, "title": "同一ID比較",
                           "saved_document_ids": [a_doc["saved_document_id"], b_doc["saved_document_id"]]})
        excerpts8 = comp8.get("original_excerpts") or {}
        flat = json.dumps(excerpts8, ensure_ascii=False)
        report["scenario8_same_record_id_two_institutions"] = {
            "distinct_documents": a_doc["saved_document_id"] != b_doc["saved_document_id"],
            "both_record_id_rec": True,
            "excerpts_not_mixed": ("stub a" in flat and "stub b" in flat),
            "basis": "labelled stub adapters sharing record_id 'rec' (the Stage 0 regression tests cover the same collision for real IA/LoC-shaped data)",
        }

        # -- Scenario 9: partial failures --------------------------
        s, mixed = h.call("GET", "/api/search?" + q(q="historia", libraries="finna,dpla"))
        dpla_errors = [e for e in mixed.get("errors", []) if e.get("library_id") == "dpla"]
        report["scenario9_partial_failures"] = {
            "finna_results_despite_dpla": bool(mixed.get("results")),
            "dpla_authentication_required": any("authentication_required" in e.get("error", "") for e in dpla_errors),
            "gallica_403": "recorded live 2026-11-26 (docs/b8-live-verification.md); not re-run here",
            "finna_live_403": "recorded live 2026-11-26 (docs/b8-live-verification.md); not re-run here",
        }

        report.update(asyncio.run(_adapter_level(h)))
    finally:
        h.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        report = run(Path(tmp))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
