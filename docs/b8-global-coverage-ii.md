# Global Library MCP v1.0.0b8 — Global Coverage II

ブランチ：`feat/global-coverage-b8`（起点 master `ab1274b` =
v1.0.0b7）。本書は b8 の総括記録。各論は個別文書へ：
Stage 0 は `docs/b8-b7-regression-hardening.md`、API調査は
`docs/b8-api-research.md`、実地検証は `docs/b8-live-verification.md`、
評価は `docs/b8-evaluation.md`、性能は
`docs/b8-performance-evaluation.md`、ワークスペース統合は
`docs/b8-workspace-integration.md`。

## Stage 0：b7残存問題の修正

インポート／復元された権利申告が原文保存を許可しない信頼
モデル（server_observed のみが許可側に働く）、最新権利観測の
新規保存への適用、CC BY-NC の目的未確認時の確認フロー、
機関横断ID衝突の複合キー化、復元の静止化（quiesce）と
復元時信頼降格、スキーマ v3。詳細は上記文書。

## 新規機関

| 機関 | 種別 | 状態 | 実地検証 |
|---|---|---|---|
| Finna | 横断検索（FI） | 実装（検索・詳細・権利正規化） | 応答形状のみ利用者ブラウザで確認。サーバーからは403で未達成 |
| フィンランド国立図書館 Digi | 提供元（FI） | 実装（OAI同一性・ALTO OCR・原本検証・文書内検索） | 到達不可のため未達成（フィクスチャのみ） |
| KB / Delpher | 新聞（NL） | 実装（SRU検索・resolver OCR・文書内検索） | **検索・ページOCR・ページ同一性を実地確認**。画像は404で未達成 |
| Japan Search | 横断検索（JP） | 実装（SPARQL検索・JSON-LD詳細・NDL引き継ぎ候補） | **検索・詳細を実地確認** |
| DPLA | 横断検索（US） | 認証待ち実装 | キー未発行のため未実施（authentication_required を実地確認） |
| BNE／ÖNB-ANNO | — | 調査のみ | BNEはSPARQL＋CC0を確認。ANNOは公式APIなし |

## 機関能力レジストリ集計（§16、libraries.yaml 実数）

- レジストリ登録数：**31**
- 実装アダプター数：**13**
- キーワード検索：実装10（うち実地検証済5＝loc／ndl／
  internet-archive／kb-delpher／japan-search、フィクスチャ
  検証済1＝finna、認証待ち1＝dpla、残りは既存機関）
- ID指定取得：実地検証済7、フィクスチャ2、認証待ち1
- ページOCR：実装あり（実地検証済5、フィクスチャ1＝Digi）
- 原本画像：実地検証済4、フィクスチャ2（Digi／KB）
- ページ対応：実地検証済5、フィクスチャ1（Digi）
- 検索→引用／根拠採用／ワークスペース保存までの実地検証は
  機関別に `docs/b8-live-verification.md` と既存の b5–b7 記録に
  分散しており、合算した宣伝数値は作らない。登録数を
  「使える図書館数」として提示しない。

## 多言語（§11）

- 言語正規化に fi／sv を追加（nl は既存）。資料言語フィルターと
  検索ルーティングで利用可能。
- 概念辞書：18概念に fi/sv/nl ラベルを追加、新規に
  independence 概念を追加。全て verification_status は
  **unverified**（典拠検証済とは主張しない）。出典・ライセンスは
  辞書ファイルの従来方針（プロジェクト独自編纂、著作権のある
  辞書データの複写なし）を継承し、b8追加分はその旨を各概念の
  source に追記。nl の waterkracht は KB 実レコードで観測した。
- 概念翻訳の対角インターリーブで、新規言語がバリアント上限に
  構造的に届かない問題を修正（`docs/b8-evaluation.md`）。

## 根拠採用条件（§22）

evidence admission／temporal anchoring／numeric binding／
page kind／relevance gate／citation・claim verification／
insufficient_evidence／answer_withheld は一切変更していない。
資料発見数の増加をAI回答の正確性向上とは主張しない。
有料API呼び出し：0。APIキー発行：0。外部AIへの資料送信：0。
研究データの外部公開：なし。
