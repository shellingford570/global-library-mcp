# Global Library MCP v1.0.0b3 — Research Beta（リリースノート / Release Notes）

## 日本語

v1.0.0b3は、実利用で見つかった検索速度の問題と、外部レビューの
指摘を修正するリリースです。新機能はありません。

### 性能

- 書誌検索が全体の約8割を占めていた原因（遅い図書館が全バリアント
  をブロック）を特定し、図書館ごとの期限（10秒）とサーキット
  ブレーカーを導入。代表5分野で調査合計時間が約3–10倍に改善
  （例：明治の水力発電 255秒→24秒前後。ライブラリ側の変動あり）。
- Quick（書誌のみ）／Standard／Deepの3モードと段階的表示を実装。

### 外部レビュー修正（安全性）

- HTTP予算を「送信前の原子的確保」に変更し、同時実行でも上限を
  超えないことをテストで保証。応答サイズはストリーミング中に
  強制し、巨大応答（圧縮爆弾を含む）を安全に打ち切ります。
- MCPの `research_materials` が実行不能だった不具合を修正し、
  公式SDKクライアントからの実呼び出しで検証。
- キャンセルをサーバー側で実効化（操作ID、状態の区別、
  サーバー確認後のみ「キャンセル」表示）。
- 全経路への予算適用、Retry-Afterの完全尊重、キャッシュの
  TTL・上限・貸出制限の再確認を実装。

### 既知の制約

- 検索速度は各図書館APIに依存します。Gallicaはネットワークに
  より403、LoCは遅延による部分失敗があり得ます（理由を表示）。
- AI回答は実験機能のままです。

## English

v1.0.0b3 fixes the search-speed problems found in real use and
the findings of an external code review. No new features.

### Performance

- Root-caused the bibliographic phase consuming ~80% of total
  time (one slow library gating every query variant) and added
  per-library deadlines (10s) plus a circuit breaker. On five
  representative topics, total investigation time improved
  roughly 3–10x (e.g. Meiji hydroelectric power: 255s to ~24s;
  upstream variance applies).
- Quick (bibliographic only) / Standard / Deep modes with
  staged result display.

### Review fixes (safety)

- The HTTP budget now reserves attempts atomically before
  sending; concurrency tests prove the cap cannot be exceeded.
  Response sizes are enforced while streaming, aborting
  oversized responses (including compression bombs) safely.
- Fixed an MCP `research_materials` tool that could not execute
  at all; verified by actually calling it from the official
  Python SDK client.
- Server-side cancellation with operation ids and distinct
  states; "cancelled" is shown only after the server confirms.
- Budgets on every path, full Retry-After honoring, and cache
  TTLs/bounds with access-restriction re-checks.

### Known limitations

- Speed depends on each library's API. Gallica may return 403
  from some networks and LoC may partial-fail on the deadline;
  both are reported with reasons.
- AI answering remains experimental.
