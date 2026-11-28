#!/usr/bin/env bash
# LIVE upstream smoke (INFORMATIONAL job only, b10 final review
# section 3). Failures are recorded verbatim in the output -
# an upstream 500 is reported as an upstream failure, never
# rewritten into a success. This script is NOT part of the
# mandatory CI path; the mandatory equivalent is
# tests/e2e_smoke_fixture.sh over fixed fixtures.
set -uo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
echo "live-smoke target: $BASE_URL"
echo "run_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fail=0
step() { echo "STEP $1: $2"; }
step health "GET /health"
health="$(curl -fsS "$BASE_URL/health")" || { echo "RESULT health: FAILED (application)"; exit 1; }
grep -q '"ok": true' <<<"$health" || { echo "RESULT health: FAILED (application)"; exit 1; }
echo "RESULT health: ok"
step search "GET /api/search?q=railway&libraries=ndl,internet-archive (live)"
search="$(curl --max-time 60 -fsS "$BASE_URL/api/search?q=railway&libraries=ndl,internet-archive")" || { echo "RESULT search: FAILED (upstream or application - see log)"; fail=1; }
if [ -n "${search:-}" ]; then
  python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert len(p["results"]) > 0; assert {x["library_id"] for x in p["results"]} == {"ndl", "internet-archive"}' "$search" && echo "RESULT search: ok" || { echo "RESULT search: FAILED (unexpected payload)"; fail=1; }
fi
step page "GET /api/page?library=ndl&id=974405_2 (live NDL page API)"
page_status="$(curl --max-time 30 -s -o /tmp/live-page.json -w '%{http_code}' "$BASE_URL/api/page?library=ndl&id=974405_2")"
echo "RESULT page http_status: $page_status"
if [ "$page_status" = "200" ]; then
  python3 -c 'import json; p=json.load(open("/tmp/live-page.json")); assert p["verified_mapping"] is True; assert p["contents"]; assert p["image_url"].endswith("/974405/R0000002/full/full/0/default.jpg")' && echo "RESULT page: ok" || { echo "RESULT page: FAILED (payload)"; fail=1; }
else
  echo "RESULT page: FAILED (upstream unavailable or application error - NOT rewritten)"
  fail=1
fi
step answer "GET /api/answer (AI disabled path, live search)"
answer="$(curl --max-time 60 -fsS "$BASE_URL/api/answer?q=%E7%99%BA%E9%9B%BB&libraries=ndl")" || { echo "RESULT answer: FAILED"; fail=1; }
if [ -n "${answer:-}" ]; then
  python3 -c 'import json,sys; p=json.loads(sys.argv[1]); assert p["available"] is False; assert p["search"]["results"]' "$answer" && echo "RESULT answer: ok" || { echo "RESULT answer: FAILED (payload)"; fail=1; }
fi
if [ "$fail" = "0" ]; then echo "LIVE SMOKE: all steps ok"; else echo "LIVE SMOKE: failures recorded above (informational job)"; fi
exit "$fail"
