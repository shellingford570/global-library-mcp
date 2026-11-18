from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from global_library_mcp.registry import Registry
from global_library_mcp.service import LibraryService

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parent / "static"


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "GlobalLibrary/0.1"

    def _send(self, body: bytes, content_type: str = "application/json; charset=utf-8", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
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
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                self._send(json_bytes({"error": "q is required"}), status=400)
                return
            raw_libraries = parse_qs(parsed.query).get("libraries", [""])[0]
            libraries = [item for item in raw_libraries.split(",") if item] or None
            try:
                async def execute():
                    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"User-Agent": "global-library-mcp/0.1 (+https://github.com/shellingford570/global-library-mcp)"}) as client:
                        return await LibraryService(client).search(query, libraries, 10)
                response = asyncio.run(execute())
                self._send(json_bytes(response.to_dict()))
            except Exception as exc:
                self._send(json_bytes({"error": str(exc)}), status=502)
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if parsed.path == "/app.css":
            self._send((STATIC / "app.css").read_bytes(), "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send((STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
            return
        self._send(json_bytes({"error": "not found"}), status=404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {format % args}")


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Global Library MCP Web UI: http://{host}:{port}")
    server.serve_forever()
