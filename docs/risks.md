# Global Library MCP Phase 0：リスク登録簿

- **確認日**：2026-11-19
- **状態**：リスク識別。対策は提案であり実装済みではない。

|リスク|影響|軽減策|状態|
|---|---|---|---|
|権利条件の混同|本文・画像の不適切な再配布|record単位rights、license URL、attribution、access_rightsを必須化し、unknownを拒否寄りに扱う。NDLIは抽出・ハーベスト制限を明記。[1] |要対応|
|API規約・大量アクセス違反|遮断・契約違反|機関別rate policy、同時実行数、最小間隔、Retry-After、キャッシュ期限を設定。NDLも大量・継続アクセスを注意喚起。[2] |要対応|
|API仕様変更|検索停止・誤マッピング|Explain/Identify/manifest/schemaの契約テスト、version pin、変更監視、degrade-and-continue。[3] |要対応|
|OSSライセンス不備|無断コード利用|LICENSE実体、著作権者、依存ライセンス、SBOMを確認。READMEだけのMIT表記は採用根拠にしない。|要対応|
|GPL伝播|配布形態・法務問題|Scriptoriaは独立プロセスまたは仕様参照を基本に法務レビュー。[4] |要対応|
|SSRF/リダイレクト|内部資源・認証情報漏えい|許可ホスト、HTTPS、DNS/redirect再検査、プライベートIP拒否、サイズ/MIME上限。[4] |要対応|
|XML XXE/巨大XML|情報漏えい・DoS|defusedxml相当、外部エンティティ無効化、深さ・サイズ・時間制限、XPath入力分離。|要対応|
|APIキー漏えい|不正利用・費用|secret store、URLへ埋め込まない、ログredaction、ローテーション。NLI等はAPI key必須。[5] |要対応|
|OCR誤読|誤引用・研究上の誤り|OCR/transcriptionを区別、座標・ページ・confidence・原画像リンクを返し、重要引用は原資料確認を促す。|要対応|
|能力の過大表示|利用者の誤認|機関別capabilitiesをtrue/false/unknownで返す。標準対応を全文・画像対応と推論しない。[6] |要対応|
|外部サービス停止|横断検索の可用性低下|source単位タイムアウト、部分結果、構造化エラー、キャッシュ、手動停止フラグ。|要対応|
|依存脆弱性|実行環境侵害|依存固定、SBOM、SCA、SAST、最小権限、定期更新。対象OSSではnpm auditの高リスク報告例もある。[7] |要対応|
|個人情報・検索語漏えい|プライバシー侵害|検索語の最小ログ、PII redaction、外部LLMへ送らない既定、保持期間制限。|要対応|

## 重要なunknown
各APIの現行SLA、厳密な数値レート制限、全資料の権利境界、機関別OCR品質、Global Libraryの本番脅威モデル、利用規模、運用責任者はunknownである。Phase 1開始前に対象機関ごとの公式条件とサンプル疎通を再確認する。

## References
[1]: https://www.ndl.gov.in/terms "NDLI Terms"
[2]: https://ndlsearch.ndl.go.jp/help/api/provider "NDL API provider conditions"
[3]: https://www.openarchives.org/OAI/openarchivesprotocol.html "OAI-PMH"
[4]: https://nikazzio.github.io/scriptoria/explanation/security-and-path-safety "Scriptoria security"
[5]: https://www.nli.org.il/en/research-and-teach/open-library/search-api "NLI Search API"
[6]: https://iiif.io/technical-details/ "IIIF technical details"
[7]: https://github.com/kazunori-Ohashi/MCP-ndl-search "MCP-ndl-search"
