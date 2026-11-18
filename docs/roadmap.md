# Global Library MCP Phase 0：ロードマップ

- **確認日**：2026-11-19
- **現状態**：Phase 0で停止。以下は提案計画であり、実装完了ではない。

## Phase 1：1機関の垂直スライス
**候補**：LoC。公式JSON/YAML、Text Services、IIIF Image、SRU/CQLが確認済み。[1][2]

実装項目：
- source registryとcapability manifest
- `search_catalog`、`get_record`
- Text ServicesのOCRスニペット・座標
- IIIF manifest/image link（画像の直接保存は既定でしない）
- Record/Rights/Media/TextEvidenceモデル
- タイムアウト、リトライ、バックオフ、レート制御、サイズ上限
- fixture、契約テスト、構造化エラー、出典・取得時刻

完了条件：正常検索、空結果、認証／レート制限、schema変更想定、権利unknownを再現でき、原URL・record ID・証拠ページを返す。

## Phase 2：比較用コネクタ
NDL（SRU/OpenSearch/OAI-PMH、次世代DL OCR）とGallica（ContentSearch、ALTO、IIIF）を追加する。[3][4] NDLはデータプロバイダ別条件、営利利用、クレジット、大量アクセス制限を先に確認する。[5] Gallicaはアクセス制限告知と利用条件の再確認を行う。

## Phase 3：横断探索
Europeana、DDB v2、Japan Searchを追加し、provider/institution/source URL/rightsを保持して重複排除・ランキングを導入する。[6][7][8] DDB v1は2026-12-31停止予定のため採用しない。[7]

## Phase 4：画像・ページ・全文の拡張
QDL、NLI、NLSA/CONTENTdm、Trove、Internet Archive、Open Libraryを、各アイテム権利とAPI制限を満たす範囲で追加する。QDL/NLIはIIIF-first、NLSAはCONTENTdmテナント設定、Internet ArchiveはOCR/hOCRとUser-Agent・429対応、Open Library Search insideはexperimental表示とする。[9][10][11][12]

## Phase 5：運用硬化
CI、依存固定、SBOM、SAST、脆弱性スキャン、監査ログ、メトリクス、API変更監視、負荷試験、障害時のdegrade-and-continueを追加する。公開HTTPブリッジを提供する場合は認証、許可オリジン、APIキー秘匿を既定にする。

## 実装前ゲート
- 各機関の公式利用規約・robots・rate limit・認証を記録
- アイテム単位のrights/licenseと再利用範囲を確認
- LICENSE実体がない既存OSSは権利者確認まで直接依存しない
- GPLコードはライセンス影響を法務確認
- APIサンプルをfixture化し、公式仕様との差分を検出
- Phaseごとに停止基準（権利不明、規約違反、安定性不足）を設定

## 期間・費用の扱い
Phase 0では確定見積を出さない。Phase 1の2–4週間は小規模垂直スライスの目安であり、担当者数、認証、試験データ、SLA、APIキー費用を確定した後に再見積する。無料APIでも運用費、監視、ストレージ、法務レビューは発生し得る。

## References
[1]: https://www.loc.gov/apis/ "Library of Congress APIs"
[2]: https://www.loc.gov/standards/sru/ "LoC SRU"
[3]: https://ndlsearch.ndl.go.jp/help/api/specifications "NDL API specifications"
[4]: https://api.bnf.fr/fr/api-document-de-gallica "Gallica API"
[5]: https://ndlsearch.ndl.go.jp/help/api/provider "NDL provider conditions"
[6]: https://api.europeana.eu/ "Europeana APIs"
[7]: https://labs.deutsche-digitale-bibliothek.de/app/ddbapi/ "DDB API"
[8]: https://jpsearch.go.jp/api "Japan Search API"
[9]: https://www.qdl.qa/en/about "Qatar Digital Library"
[10]: https://www.nli.org.il/en/research-and-teach/open-library/presentation-api "NLI Presentation API"
[11]: https://help.oclc.org/Metadata_Services/CONTENTdm/Advanced_website_customization/API_Reference/CONTENTdm_API "CONTENTdm API"
[12]: https://archive.org/developers/ocr.html "Internet Archive OCR"
