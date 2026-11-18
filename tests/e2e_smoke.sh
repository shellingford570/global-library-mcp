#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

health="$(curl -fsS "$BASE_URL/health")"
grep -q '"ok": true' <<<"$health"
routes="$(curl -fsS "$BASE_URL/manus-routes.json")"
grep -q 'Global Library MCP' <<<"$routes"
html="$(curl -fsS "$BASE_URL/")"
grep -q 'Global Library MCP' <<<"$html"
search="$(curl --max-time 60 -fsS "$BASE_URL/api/search?q=railway&libraries=ndl,internet-archive")"
python -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p["results"]) > 0; assert {x["library_id"] for x in p["results"]} == {"ndl", "internet-archive"}' "$search"
page="$(curl --max-time 30 -fsS "$BASE_URL/api/page?library=ndl&id=974405_2")"
python -c 'import json,sys; p=json.loads(sys.argv[1]); assert p["verified_mapping"] is True; assert p["contents"]; assert p["image_url"].endswith("/974405/R0000002/full/full/0/default.jpg")' "$page"
answer="$(curl --max-time 60 -fsS "$BASE_URL/api/answer?q=%E7%99%BA%E9%9B%BB&libraries=ndl")"
python -c 'import json,sys; p=json.loads(sys.argv[1]); assert p["available"] is False; assert p["search"]["results"]' "$answer"
printf '%s\n' 'E2E smoke passed: health, routes, HTML, two-library live search, NDL OCR/IIIF page, disabled AI path.'
