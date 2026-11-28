"""Human-review package for the b11 evaluation set (section 20).

Produces a BLIND review CSV: reviewers see the case material and
the system's output, never the expected label or the label
provenance.  Judgement options follow the brief: correct /
partially_correct / incorrect / insufficient_evidence /
cannot_judge / out_of_scope.  Blank judgements are NEVER counted
as reviewed (see b11_agreement.py).  Also emits a standalone local
HTML review page (no network, no expected labels embedded) that
exports the filled judgements as JSON in the browser.

No reviewer has been recruited and no human evaluation exists at
b11 submission time; this tooling only prepares the package.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

JUDGEMENTS = ["correct", "partially_correct", "incorrect",
              "insufficient_evidence", "cannot_judge", "out_of_scope"]

COLUMNS = ["case_id", "category", "material", "system_output",
           "reviewer_id", "judgement", "comment", "reviewed_at"]


def blind_rows(cases: list[dict]) -> list[dict]:
    rows = []
    for c in cases:
        rows.append({
            "case_id": c["case_id"],
            "category": c.get("category") or "",
            "material": json.dumps(c.get("task"), ensure_ascii=False)[:2000],
            "system_output": "",   # filled by the evaluation runner
            "reviewer_id": "", "judgement": "", "comment": "",
            "reviewed_at": "",
        })
    return rows


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def review_html(rows: list[dict]) -> str:
    data = json.dumps(rows, ensure_ascii=False)
    options = "".join(f'<option value="{j}">{j}</option>' for j in JUDGEMENTS)
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>b11 blind review (local only)</title></head>
<body><h1>b11 人手レビュー（ブラインド・ローカル専用）</h1>
<p>期待ラベルは含まれていません。空欄の判定はレビュー済みとして数えられません。</p>
<div id="app"></div>
<button id="dl">判定をJSONでダウンロード</button>
<script>
const ROWS = {data};
const OPTS = `{options}`;
const state = {{}};
const app = document.getElementById('app');
ROWS.forEach(r => {{
  const d = document.createElement('div');
  d.style.border = '1px solid #888'; d.style.margin = '8px'; d.style.padding = '8px';
  d.innerHTML = '<b>' + r.case_id + '</b> [' + r.category + ']<pre>' +
    r.material.replace(/</g, '&lt;') + '</pre>';
  const sel = document.createElement('select');
  sel.innerHTML = '<option value=""></option>' + OPTS;
  sel.onchange = () => {{ state[r.case_id] = sel.value; }};
  d.appendChild(sel); app.appendChild(d);
}});
document.getElementById('dl').onclick = () => {{
  const blob = new Blob([JSON.stringify(state, null, 1)],
    {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'b11-review.json';
  a.click();
}};
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/b11-cases.json")
    ap.add_argument("--out-dir", default="eval/b11-review")
    args = ap.parse_args()
    payload = json.loads(Path(args.dataset).read_text())
    rows = blind_rows(payload["cases"])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "b11-review.csv").write_text(to_csv(rows))
    (out / "b11-review.html").write_text(review_html(rows))
    print("review rows:", len(rows), "->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
