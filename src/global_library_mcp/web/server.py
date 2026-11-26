from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from global_library_mcp.registry import Registry
from global_library_mcp.service import LibraryService
from global_library_mcp.http import sanitize_error

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parent / "static"


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def structured_kwargs(qs: dict) -> dict:
    """The structured research options shared by /api/search and
    /api/materials. (b7 final-review catch: /api/materials used
    to reference a variable that only existed inside the
    /api/search branch, so every real HTTP materials call failed
    with a NameError masked as an upstream 502 - the mocked
    Playwright route never exercised the real handler.)"""
    kwargs: dict = {}
    if qs.get("author"):
        kwargs["author"] = qs["author"][0][:200]
    if qs.get("title"):
        kwargs["title"] = qs["title"][0][:200]
    if qs.get("languages"):
        kwargs["languages"] = [x for x in qs["languages"][0].split(",")
                               if x in ("ja", "en", "de", "fr")][:4] or None
    if qs.get("expand") is not None:
        kwargs["expand_multilingual"] = qs["expand"][0] != "0"
    if qs.get("historical") is not None:
        kwargs["expand_historical"] = qs["historical"][0] != "0"
    for key in ("year_from", "year_to"):
        if qs.get(key) and qs[key][0].isdigit():
            kwargs[key] = int(qs[key][0])
    if qs.get("ocr", [""])[0] == "1":
        kwargs["ocr_required"] = True
    return kwargs


class RateLimiter:
    """Per-client sliding-window limiter for the API routes.

    In-memory and per-process by design (the web UI is a local /
    single-instance tool); a multi-instance deployment should enforce
    quotas at its gateway instead. The limit is configurable with the
    GLM_RATE_LIMIT_PER_MINUTE environment variable (default 120).
    """

    def __init__(self, limit_per_minute: int | None = None) -> None:
        import os
        import threading
        import time

        if limit_per_minute is None:
            try:
                limit_per_minute = int(os.environ.get("GLM_RATE_LIMIT_PER_MINUTE", "120"))
            except ValueError:
                limit_per_minute = 120
        self.limit = max(limit_per_minute, 1)
        self.window = 60.0
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._now = time.monotonic

    def allow(self, client: str) -> bool:
        now = self._now()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(client, []) if now - stamp < self.window]
            if len(hits) >= self.limit:
                self._hits[client] = hits
                return False
            hits.append(now)
            self._hits[client] = hits
            return True


RATE_LIMITER = RateLimiter()


class ServiceRuntime:
    """b3: one long-lived LibraryService on its own event-loop thread.

    Previously every API request built a fresh client and service, so
    the search/page caches and the circuit breaker were reset on
    every request and never actually helped. The runtime owns one
    budgeted client (make_client) and one service; handler threads
    submit coroutines to its loop. Cancellation: if the handler's
    wait times out, the coroutine is cancelled on the loop, which
    stops its in-flight HTTP work.
    """

    def __init__(self) -> None:
        import threading

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        from global_library_mcp.http import make_client

        async def _make_service():
            return LibraryService(make_client(timeout=30))

        self.service = asyncio.run_coroutine_threadsafe(_make_service(), self._loop).result(timeout=30)
        self._ops: dict[str, dict] = {}
        # b7: workspace runtime (WorkspaceWebRuntime) when the
        # research workspace is enabled; None in the stateless
        # search-only mode, which behaves exactly as before.
        self.ws = None

    def run(self, coro, timeout: float = 600):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception:
            future.cancel()
            raise

    # b3.1 (Section 5): server-side cancellation. Each investigation
    # runs under a client-chosen operation id (a random UUID only
    # the initiating browser knows, so another user cannot cancel
    # it). States are distinguished: running / completed / failed /
    # cancelled / timeout. A state is reported as cancelled only
    # after the task has actually ended cancelled.
    _OP_TIMEOUT_S = 300

    async def _op_main(self, op_id: str, coro, timeout_s: float):
        op = self._ops[op_id]
        op["task"] = asyncio.current_task()
        try:
            result = await asyncio.wait_for(coro, timeout_s)
            op["state"] = "completed"
            return result
        except asyncio.TimeoutError:
            op["state"] = "timeout"
            raise
        except asyncio.CancelledError:
            op["state"] = "cancelled"
            raise
        except Exception:
            op["state"] = "failed"
            raise

    def run_op(self, op_id: str, coro, timeout_s: float = _OP_TIMEOUT_S):
        self._ops[op_id] = {"state": "running", "task": None}
        future = asyncio.run_coroutine_threadsafe(self._op_main(op_id, coro, timeout_s), self._loop)
        return future.result(timeout=timeout_s + 30)

    def op_state(self, op_id: str) -> str:
        op = self._ops.get(op_id)
        return op["state"] if op else "unknown"

    def cancel_op(self, op_id: str, wait_s: float = 15) -> str:
        import time as _time

        op = self._ops.get(op_id)
        if op is None:
            return "unknown"
        task = op.get("task")
        if op["state"] == "running" and task is not None:
            self._loop.call_soon_threadsafe(task.cancel)
            deadline = _time.monotonic() + wait_s
            while op["state"] == "running" and _time.monotonic() < deadline:
                _time.sleep(0.05)
        return op["state"]


RUNTIME = ServiceRuntime()


class Handler(BaseHTTPRequestHandler):
    server_version = "GlobalLibrary/0.1"

    def _send(self, body: bytes, content_type: str = "application/json; charset=utf-8", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _workspace_dispatch(self, method: str) -> bool:
        if RUNTIME.ws is None:
            return False
        from global_library_mcp.web.workspace_api import WorkspaceApi

        return WorkspaceApi(RUNTIME.ws, RUNTIME).handle(self, method)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and not RATE_LIMITER.allow(self.client_address[0]):
            self._send(json_bytes({"error": "rate limit exceeded; slow down and retry shortly"}), status=429)
            return
        if parsed.path.startswith("/api/workspace") and self._workspace_dispatch("POST"):
            return
        self._send(json_bytes({"error": "not found"}), status=404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/workspace") and self._workspace_dispatch("PUT"):
            return
        self._send(json_bytes({"error": "not found"}), status=404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/workspace") and self._workspace_dispatch("DELETE"):
            return
        self._send(json_bytes({"error": "not found"}), status=404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and not RATE_LIMITER.allow(self.client_address[0]):
            self._send(json_bytes({"error": "rate limit exceeded; slow down and retry shortly"}), status=429)
            return
        if parsed.path.startswith("/api/workspace"):
            if RUNTIME.ws is None:
                self._send(json_bytes({"error": "workspace is not enabled"}), status=404)
                return
            if self._workspace_dispatch("GET"):
                return
        if parsed.path == "/health":
            self._send(json_bytes({"ok": True, "service": "global-library-mcp"}))
            return
        if parsed.path == "/manus-routes.json":
            self._send(json_bytes({"routes": [{"path": "/", "title": "Global Library MCP"}]}))
            return
        if parsed.path == "/api/libraries":
            registry = Registry(ROOT / "libraries.yaml")
            self._send(json_bytes({"libraries": registry.list()}))
            return
        if parsed.path == "/api/cancel":
            op_id = parse_qs(parsed.query).get("op", [""])[0]
            if not op_id:
                self._send(json_bytes({"error": "op is required"}), status=400)
                return
            state = RUNTIME.cancel_op(op_id)
            self._send(json_bytes({"op_id": op_id, "state": state}))
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send(json_bytes({"error": "q is required"}), status=400)
                return
            if len(query) > 500:
                self._send(json_bytes({"error": "q is too long"}), status=400)
                return
            raw_libraries = parse_qs(parsed.query).get("libraries", [""])[0]
            libraries = [item for item in raw_libraries.split(",") if item][:10] or None
            _mat_kwargs = structured_kwargs(parse_qs(parsed.query))
            try:
                if _mat_kwargs:
                    # b7 (brief section 35): the structured options
                    # parsed above used to be dead code - the plain
                    # search ignored them while /api/materials
                    # applied them, so the staged UI's first
                    # bibliographic results silently used different
                    # conditions. With any structured option present,
                    # stage-1 now runs the Quick research path (the
                    # bibliographic stage with the same conditions)
                    # and maps its materials into the search shape.
                    result = RUNTIME.run(RUNTIME.service.research_materials(
                        query, libraries, 10, mode="quick", **_mat_kwargs))
                    if RUNTIME.ws is not None:
                        RUNTIME.ws.annotate_search_results(result.get("materials", []))
                    self._send(json_bytes({
                        "query": query,
                        "results": result.get("materials", []),
                        "errors": result.get("errors", []),
                        "retrieved_at": result.get("retrieved_at"),
                        "search_kind": "structured_bibliographic",
                        "options_applied": True,
                        "filters": result.get("filters"),
                        "discovery": result.get("discovery"),
                        "search_scope": result.get("search_scope"),
                    }))
                else:
                    response = RUNTIME.run(RUNTIME.service.search(query, libraries, 10))
                    payload = response.to_dict()
                    payload["search_kind"] = "plain_bibliographic"
                    payload["options_applied"] = False
                    if RUNTIME.ws is not None:
                        RUNTIME.ws.annotate_search_results(payload.get("results", []))
                    self._send(json_bytes(payload))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/answer":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send(json_bytes({"error": "q is required"}), status=400)
                return
            if len(query) > 500:
                self._send(json_bytes({"error": "q is too long"}), status=400)
                return
            raw_libraries = parse_qs(parsed.query).get("libraries", [""])[0]
            libraries = [item for item in raw_libraries.split(",") if item][:10] or None
            try:
                self._send(json_bytes(RUNTIME.run(RUNTIME.service.answer(query, libraries, 10))))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/evidence":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send(json_bytes({"error": "q is required"}), status=400)
                return
            if len(query) > 500:
                self._send(json_bytes({"error": "q is too long"}), status=400)
                return
            raw_libraries = parse_qs(parsed.query).get("libraries", [""])[0]
            libraries = [item for item in raw_libraries.split(",") if item][:10] or None
            try:
                mode = parse_qs(parsed.query).get("mode", ["standard"])[0]
                op_id = parse_qs(parsed.query).get("op", [""])[0]
                if op_id:
                    import concurrent.futures as _cf

                    try:
                        result = RUNTIME.run_op(op_id, RUNTIME.service.collect_evidence(query, libraries, 10, mode=mode))
                        self._send(json_bytes({**result, "op_state": RUNTIME.op_state(op_id)}))
                    except (_cf.CancelledError, asyncio.CancelledError):
                        self._send(json_bytes({"op_state": "cancelled", "op_id": op_id, "evidence": []}))
                    except (TimeoutError, asyncio.TimeoutError):
                        self._send(json_bytes({"op_state": "timeout", "op_id": op_id, "evidence": []}))
                else:
                    self._send(json_bytes(RUNTIME.run(RUNTIME.service.collect_evidence(query, libraries, 10, mode=mode))))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/newspaper-issues":
            lccn = parse_qs(parsed.query).get("lccn", [""])[0].strip()
            if not lccn:
                self._send(json_bytes({"error": "lccn is required"}), status=400)
                return
            try:
                self._send(json_bytes(RUNTIME.run(RUNTIME.service.newspaper_issues(lccn))))
            except Exception as exc:
                self._send(json_bytes({"lccn": lccn, "error": str(exc)[:200], "issues": []}), status=200)
            return
        if parsed.path == "/api/materials":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send(json_bytes({"error": "q is required"}), status=400)
                return
            if len(query) > 500:
                self._send(json_bytes({"error": "q is too long"}), status=400)
                return
            raw_libraries = parse_qs(parsed.query).get("libraries", [""])[0]
            libraries = [item for item in raw_libraries.split(",") if item][:10] or None
            _mat_kwargs = structured_kwargs(parse_qs(parsed.query))
            try:
                mode = parse_qs(parsed.query).get("mode", ["standard"])[0]
                op_id = parse_qs(parsed.query).get("op", [""])[0]
                if op_id:
                    import concurrent.futures as _cf

                    try:
                        result = RUNTIME.run_op(op_id, RUNTIME.service.research_materials(query, libraries, 10, mode=mode, **_mat_kwargs))
                        if RUNTIME.ws is not None:
                            RUNTIME.ws.annotate_search_results(result.get("materials", []))
                        self._send(json_bytes({**result, "op_state": RUNTIME.op_state(op_id)}))
                    except (_cf.CancelledError, asyncio.CancelledError):
                        self._send(json_bytes({"op_state": "cancelled", "op_id": op_id, "materials": []}))
                    except (TimeoutError, asyncio.TimeoutError):
                        self._send(json_bytes({"op_state": "timeout", "op_id": op_id, "materials": []}))
                else:
                    result = RUNTIME.run(RUNTIME.service.research_materials(query, libraries, 10, mode=mode, **_mat_kwargs))
                    if RUNTIME.ws is not None:
                        RUNTIME.ws.annotate_search_results(result.get("materials", []))
                    self._send(json_bytes(result))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/verify":
            params = parse_qs(parsed.query)
            library_id = params.get("library", [""])[0]
            page_id = params.get("id", [""])[0]
            if not library_id or not page_id:
                self._send(json_bytes({"error": "library and id are required"}), status=400)
                return
            try:
                self._send(json_bytes(RUNTIME.run(RUNTIME.service.verify_page(library_id, page_id))))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/compare":
            params = parse_qs(parsed.query)
            raw_docs = params.get("docs", [""])[0]
            documents = []
            for pair in raw_docs.split(";"):
                pair = pair.strip()
                if not pair:
                    continue
                library_id, sep, record_id = pair.partition(":")
                if sep and library_id.strip() and record_id.strip():
                    documents.append({"library_id": library_id.strip(), "record_id": record_id.strip()})
            if not 2 <= len(documents) <= 4:
                self._send(json_bytes({"error": "docs must list 2 to 4 documents as library:record;library:record"}), status=400)
                return
            aspects = [item.strip() for item in params.get("aspects", [""])[0].split(",") if item.strip()][:8]
            question = params.get("q", [""])[0].strip()[:500] or None
            try:
                self._send(json_bytes(RUNTIME.run(RUNTIME.service.compare_documents(documents, aspects=aspects, question=question))))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/api/in-document":
            params = parse_qs(parsed.query)
            library_id = params.get("library", [""])[0]
            identifier = params.get("id", [""])[0]
            query = params.get("q", [""])[0][:500]
            try:
                start_page = int(params.get("start", ["1"])[0] or 1)
            except ValueError:
                start_page = 1
            try:
                end_raw = params.get("end", [""])[0]
                end_page = int(end_raw) if end_raw else None
            except ValueError:
                end_page = None
            try:
                detail = RUNTIME.run(
                    RUNTIME.service.search_in_document(
                        library_id, identifier, query, start_page=start_page, end_page=end_page
                    )
                )
                self._send(json_bytes(detail))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path in ("/api/document", "/api/page"):
            params = parse_qs(parsed.query)
            library_id = params.get("library", [""])[0]
            identifier = params.get("id", [""])[0]
            try:
                if parsed.path == "/api/document":
                    detail = RUNTIME.run(RUNTIME.service.get_document(library_id, identifier))
                    if RUNTIME.ws is not None and isinstance(detail, dict):
                        RUNTIME.ws.annotate_search_results([detail])
                        for page in detail.get("pages") or []:
                            if isinstance(page, dict) and page.get("page_id"):
                                RUNTIME.ws.annotate_page(library_id, page["page_id"], page)
                else:
                    detail = RUNTIME.run(RUNTIME.service.get_page_text(library_id, identifier))
                    if RUNTIME.ws is not None and isinstance(detail, dict):
                        RUNTIME.ws.annotate_page(library_id, identifier, detail)
                self._send(json_bytes(detail))
            except Exception as exc:
                self._send(json_bytes({"error": "upstream request failed", "detail": sanitize_error(exc)}), status=502)
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            html = (STATIC / "index.html").read_bytes()
            # b7: the CSRF token reaches the page only through
            # this meta tag (never a URL, log or export).
            token = RUNTIME.ws.csrf_token if RUNTIME.ws is not None else ""
            html = html.replace(b"__GLM_CSRF_TOKEN__", token.encode("utf-8"))
            html = html.replace(b"__GLM_WORKSPACE_ENABLED__",
                                b"1" if RUNTIME.ws is not None else b"0")
            self._send(html, "text/html; charset=utf-8")
            return
        if parsed.path == "/app.css":
            self._send((STATIC / "app.css").read_bytes(), "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send((STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        if parsed.path == "/workspace.js":
            self._send((STATIC / "workspace.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        self._send(json_bytes({"error": "not found"}), status=404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {format % args}")


def run(host: str = "127.0.0.1", port: int = 8000,
        workspace: bool = False, workspace_path: str | None = None) -> None:
    import os

    if workspace or workspace_path or os.environ.get("GLM_WORKSPACE_PATH"):
        # b7 (brief sections 6, 29, 30): the workspace holds
        # persistent research data, so it is loopback-only. The
        # stateless search-only mode keeps its previous bind
        # behaviour (e.g. Docker CI on 0.0.0.0).
        import ipaddress

        try:
            addr = ipaddress.ip_address(host)
            loopback = addr.is_loopback
        except ValueError:
            loopback = host in ("localhost",)
        if not loopback:
            raise SystemExit(
                "workspace mode refuses to bind a non-loopback address: "
                f"{host}. Use 127.0.0.1 (or disable the workspace).")
        from global_library_mcp.workspace.paths import ensure_parent, resolve_db_path
        from global_library_mcp.workspace.store import WorkspaceStore
        from global_library_mcp.web.workspace_api import WorkspaceWebRuntime

        db_path = ensure_parent(resolve_db_path(workspace_path))
        RUNTIME.ws = WorkspaceWebRuntime(WorkspaceStore(db_path))
        print(f"Research workspace enabled: {db_path}")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Global Library MCP Web UI: http://{host}:{port}")
    server.serve_forever()
