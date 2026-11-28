#!/usr/bin/env bash
# Mandatory fixture smoke (b10 final review section 3): runs
# against a server whose ONLY fixed layer is upstream HTTP
# (GLM_UPSTREAM_FIXTURE_DIR). Real Docker image, real web server,
# real LibraryService, real adapters, real BudgetedTransport.
# Fixture success is NOT live verification.
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

health="$(curl -fsS "$BASE_URL/health")"
grep -q '"ok": true' <<<"$health"
html="$(curl -fsS "$BASE_URL/")"
grep -q 'Global Library MCP' <<<"$html"

# Bibliographic search over fixed fixtures (IA + NDL).
search="$(curl --max-time 60 -fsS "$BASE_URL/api/search?q=species&libraries=internet-archive")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p["results"]) > 0, p' "$search"
search_ndl="$(curl --max-time 60 -fsS "$BASE_URL/api/search?q=%E7%99%BA%E9%9B%BB&libraries=ndl")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p["results"]) > 0, p' "$search_ndl"

# Document detail (IA metadata fixture).
doc="$(curl --max-time 60 -fsS "$BASE_URL/api/document?library=internet-archive&id=onoriginofspecie1859darw")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert p.get("record_id") == "onoriginofspecie1859darw", p' "$doc"

# Page OCR + page mapping verification (NDL page fixture).
page="$(curl --max-time 30 -fsS "$BASE_URL/api/page?library=ndl&id=974405_2")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert p["verified_mapping"] is True, p; assert p["contents"], p; assert p["image_url"].endswith("/974405/R0000002/full/full/0/default.jpg"), p' "$page"

# IIIF manifest + canvas + original image verification.
verify="$(curl --max-time 60 -fsS "$BASE_URL/api/verify?library=ndl&id=974405_2")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); c=p["checks"]; assert c["manifest"]["ok"] is True, p; assert c["canvas"]["ok"] is True, p; assert c["canvas_image_match"]["ok"] is True, p; assert c["image_reachable"]["ok"] is True, p' "$verify"

# Comparison (citation-bearing excerpts come from the compare path).
compare="$(curl --max-time 90 -fsS "$BASE_URL/api/compare?docs=internet-archive:onoriginofspecie1859darw;ndl:974405&aspects=contents" || true)"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p.get("documents") or []) == 2, p; assert p.get("status"), p' "$compare"

# Cancellation endpoint responds for an unknown operation.
cancel="$(curl --max-time 30 -fsS "$BASE_URL/api/cancel?op=fixture-nonexistent-op")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert p.get("op_id") == "fixture-nonexistent-op", p' "$cancel"

# Upstream error -> partial results, never a hard failure:
# gallica has no fixture route, so it errors while IA succeeds.
partial="$(curl --max-time 60 -fsS "$BASE_URL/api/search?q=species&libraries=internet-archive,gallica")"
python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p["results"]) > 0, p; assert p.get("errors"), p' "$partial"

printf '%s\n' 'Fixture smoke passed: health, HTML, fixture search (IA+NDL), document detail, NDL OCR/IIIF page verification, compare, cancel, partial results on upstream error.'
