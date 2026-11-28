"""b11 Stage 5 tests (sections 49-54): research Web API routes,
export improvements, MCP profile invariants."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from global_library_mcp import service as _LS  # noqa: F401,E402

from global_library_mcp.workspace.exports import (  # noqa: E402
    to_bibtex, to_csl_json, to_ris)
from global_library_mcp.workspace.store import WorkspaceStore  # noqa: E402


def _doc():
    return {"saved_document_id": "d1", "library_id": "ndl",
            "record_id": "R1", "title": "純粋理性批判（翻訳）",
            "original_title": "Kritik der reinen Vernunft",
            "author": "Kant, Immanuel", "translator": "Someone, T.",
            "publication_date": "1925", "material_type": "book"}


def test_exports_carry_original_title_and_roles():
    bib = to_bibtex([_doc()])
    assert "origtitle = {Kritik der reinen Vernunft}" in bib
    assert "translator = {Someone, T.}" in bib
    ris = to_ris([_doc()])
    assert "Original title: Kritik der reinen Vernunft" in ris
    assert "Translator: Someone, T." in ris
    csl = to_csl_json([_doc()])
    assert csl[0]["original-title"] == "Kritik der reinen Vernunft"
    assert csl[0]["translator"] == [{"family": "Someone", "given": "T."}]
    # stable key: same doc -> same key across calls
    assert to_bibtex([_doc()]).split("{")[1].split(",")[0] == \
        to_bibtex([_doc()]).split("{")[1].split(",")[0]


def test_research_routes_over_http(tmp_path):
    """Real HTTP journey through the b11 research routes inside
    the existing workspace security boundary."""
    import re
    import threading
    import urllib.error
    import urllib.request
    from http.cookiejar import CookieJar
    from http.server import ThreadingHTTPServer

    import global_library_mcp.web.server as server_mod
    from global_library_mcp.web.workspace_api import WorkspaceWebRuntime

    store = WorkspaceStore(str(tmp_path / "ws.db"))
    ws = WorkspaceWebRuntime(store)
    old_ws = server_mod.RUNTIME.ws
    server_mod.RUNTIME.ws = ws
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(base + "/", timeout=30) as res:
            html = res.read().decode()
        csrf = re.search(r'name="glm-csrf" content="([^"]+)"', html).group(1)

        def call(method, path, body=None):
            data = json.dumps(body).encode() if body is not None else None
            headers = {}
            if method in ("POST", "PUT", "DELETE"):
                headers["X-GLM-CSRF"] = csrf
            if data is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(base + path, data=data,
                                         method=method, headers=headers)
            try:
                with opener.open(req, timeout=60) as res:
                    return res.status, json.loads(res.read().decode() or "{}")
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode() or "{}")

        status, proj = call("POST", "/api/workspace/projects",
                            {"title": "b11-http"})
        assert status == 201
        pid = proj["project_id"]
        store.save_document(pid, "ndl", "R1", {"title": "Doc"})
        status, prog = call("GET", f"/api/workspace/projects/{pid}/research/progress")
        assert status == 200 and prog["found"] is True
        status, q = call("POST", f"/api/workspace/projects/{pid}/research/questions",
                         {"question": "蒸気機関はいつ導入されたか"})
        assert status == 201 and q["artefact"]["trust"] == "server_generated"
        status, cl = call("POST", f"/api/workspace/projects/{pid}/research/claims",
                          {"statement": "明治二十三年に東京で蒸気機関が導入されたとされる。"})
        assert status == 201
        assert cl["claim"]["extraction"]["event"] == "extracted"
        status, g = call("GET", f"/api/workspace/projects/{pid}/research/graph")
        assert status == 200 and g["node_count"] >= 2
        status, rep = call("POST", f"/api/workspace/projects/{pid}/research/reports", {})
        assert status == 201 and rep["report_id"].startswith("rep_")
        assert rep["source_count"] == 1 and "# Research Report" in rep["markdown"]
        status, reps = call("GET", f"/api/workspace/projects/{pid}/research/reports")
        assert status == 200 and len(reps["reports"]) == 1
        status, rv = call("POST", f"/api/workspace/projects/{pid}/research/revalidate", {})
        # Final review section 30: the legacy route is a refresh
        # (state rebuild) and must SAY so - it never refetched an
        # original and never revalidated references.
        assert status == 200 and rv["operation"] == "refresh"
        assert rv["original_refetched"] is False
        assert rv["references_revalidated"] is False
        # cross-project: unknown project id is a 404, not a leak
        status, _ = call("GET", "/api/workspace/projects/nope/research/progress")
        assert status == 404
        # mutation without CSRF is refused by the existing guard
        req = urllib.request.Request(
            base + f"/api/workspace/projects/{pid}/research/questions",
            data=json.dumps({"question": "x"}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            opener.open(req, timeout=30)
            raise AssertionError("CSRF-less mutation was accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code in (400, 403)
    finally:
        httpd.shutdown()
        server_mod.RUNTIME.ws = old_ws
        store.close()
