# Global Library MCP Phase 0：推奨アーキテクチャ

- **確認日**：2026-11-19
- **状態**：設計提案。実装済みとは主張しない。

## 設計原則
1. **公式API優先**：非公式MCPは疎通・変換の参考に限定し、公式仕様を実装根拠にする。LoCはJSON/YAML、Text Services、IIIF、SRUを一機関で確認できるため最初の垂直スライスに適する。[1]
2. **能力の明示**：`bibliographic_search`、`fulltext_search`、`ocr_evidence`、`image`、`page`、`iiif_manifest`、`harvest`を機関別に`true/false/unknown`で返す。SRU/OAI-PMH/IIIFは役割が異なる。[2][3]
3. **権利保守性**：権利不明は`unknown`とし、rights URL、表示文、provider、取得時刻を失わない。DDBのメタデータCC0説明やTroveのメタデータ条件は画像・本文の一括許諾を意味しない。[4][5]
4. **証拠優先**：検索結果は原URL、record ID、manifest/canvas/page、OCR形式、座標、取得時刻を保持し、引用可能な証拠を返す。
5. **安全な外部取得**：allowlist、HTTPS、SSRF防止、リダイレクト再検査、MIME/サイズ上限、タイムアウト、XML外部エンティティ無効化、監査ログを共通層に置く。[6]

## 論理構成

```text
MCP Client
  ↓
Tool facade / policy
  ├─ search_catalog(query, filters, sources)
  ├─ get_record(source, id)
  ├─ search_fulltext(source, id/query)
  ├─ get_text_evidence(source, id, page/region)
  ├─ get_iiif_manifest(source, id)
  ├─ get_page_image(source, canvas, region/size)
  └─ list_capabilities / explain_source
  ↓
Orchestrator（parallel fan-out, quota, dedupe, ranking, provenance）
  ↓
Provider adapters（LoC, NDL, Gallica, Europeana, DDB v2 …）
  ↓
HTTP/XML/JSON/IIIF/SRU/OAI-PMH clients
```

## 共通データモデル（提案）

- `Record`：`source_id`、`institution`、`record_id`、title、creator、date、language(BCP47)、type、landing_url、retrieved_at。
- `Rights`：`rights_uri`、license、access_rights、reuse_scope、attribution、evidence_url、status(`known/unknown/restricted`)。
- `Media`：media URL、MIME、IIIF service、manifest URL、size、is_downloadable。直接バイナリ返却はポリシーで制限する。
- `TextEvidence`：text、text_type(`ocr/transcription/fulltext/unknown`)、page_id、canvas_id、bbox、coordinates、confidence、source_url、retrieved_at。
- `Capabilities`：各機能を`true/false/unknown`、根拠URL、確認日、対象範囲付きで保持する。

## 検索・取得フロー

1. `list_capabilities`で機関・API標準・認証・利用条件を宣言する。
2. 検索語をUnicode正規化し、機関別アダプタへ渡す。SRUはCQLを安全に生成し、ユーザー入力を無検証で連結しない。[2]
3. JSON/XMLを共通`Record`へ変換し、重複は原IDとsourceを残して統合する。
4. recordからIIIF manifest、Canvas、Image APIを解決する。IIIF Image APIはregion/size/rotation/formatを標準化できる。[7]
5. OCRは原文と座標を`TextEvidence`として返し、OCRと転写を混同しない。GallicaのALTOはページOCR・座標の具体例である。[8]
6. 権利が未確認なら画像・本文をダウンロードせず、原ページリンクとunknownを返す。
7. 失敗は`source_unavailable`、`rate_limited`、`auth_required`、`rights_restricted`、`schema_changed`等の構造化エラーにする。

## キャッシュ・レート・認証
機関ごとに同時実行数、最小間隔、指数バックオフ、Retry-After、レスポンス上限を設定する。Internet Archiveは識別可能なUser-Agent、429/Retry-After、遅延、キャッシュ、並列数制限を推奨している。[9] Troveは帰属と通常30日以内のキャッシュ条件を示すため、共通の無期限キャッシュを採用しない。[10] APIキーは秘密ストアから注入し、URLクエリやログへ出さない。

## Phase 0の境界
未実装なのは、Global Libraryの本番MCP、ライブ全機関接続、完全なランキング、全機関の権利判定、画像・OCRの再配布、SLA、負荷試験、CI、SBOMである。これらはPhase 1以降の計画であり、Phase 0成果物は調査と設計提案で停止する。

## References
[1]: https://www.loc.gov/apis/ "Library of Congress APIs"
[2]: https://www.loc.gov/standards/sru/ "SRU"
[3]: https://www.openarchives.org/OAI/openarchivesprotocol.html "OAI-PMH"
[4]: https://pro.deutsche-digitale-bibliothek.de/node/530 "DDB interfaces"
[5]: https://trove.nla.gov.au/about/create-something/using-api/trove-api-terms-use "Trove API Terms"
[6]: https://nikazzio.github.io/scriptoria/explanation/security-and-path-safety "Scriptoria security and path safety"
[7]: https://iiif.io/api/image/3.0/ "IIIF Image API 3.0"
[8]: https://api.bnf.fr/fr/api-document-de-gallica "Gallica Content API"
[9]: https://archive.org/developers/bots.html "Internet Archive automated access"
[10]: https://trove.nla.gov.au/about/create-something/using-api/trove-api-terms-use "Trove API Terms of Use"

## Evidence pipeline (added 2026-11-22, `feat/global-library-evidence-v2`)

```
question
  -> catalog search (question, then extracted content terms as fallback)
  -> in-document page search (adapters that support it; NDL today)
  -> page OCR fetch + identity cross-check (verified_mapping)
  -> OCR quality gate (evidence.py)  => verified Evidence records
  -> provider payload (capped: 8 items x 1,500 chars, citation_key each)
  -> LLM or mock provider
  -> citation whitelist validation (provider layer AND service layer)
  -> answer + resolved citations (record id, page id, frame, IIIF image URL)
```

Separately, `verify_original` checks a page against its IIIF original:
manifest -> canvas for the digital frame -> canvas image URL equality ->
image range request. Each check is reported individually; the page is
`verified` only when all pass. Pages failing any step stay visible as
unverified with reasons, in the API, the MCP tools and the Web UI.
