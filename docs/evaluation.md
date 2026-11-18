# Global Library MCP Phase 0：評価

- **確認日**：2026-11-19
- **結論**：本番採用判断は保留。Phase 1の小規模検証へ進む前提条件のみ定義した。

## 評価軸

|軸|確認方法|合格目安|
|---|---|---|
|機能|検索、record、全文/OCR、IIIF、ページ、権利のツール別テスト|能力をtrue/false/unknownで正確に返す|
|出典性|原URL、ID、manifest/canvas、取得時刻、OCR座標|全結果に追跡可能な根拠|
|正確性|fixtureとライブサンプルの契約テスト|主要フィールド欠落・型崩れなし|
|回復性|429、5xx、timeout、空結果、schema変更|構造化エラーと安全な再試行|
|権利|license、rights、access、attributionの保持|unknownを許諾扱いしない|
|安全性|SSRF、XXE、サイズ、URL、APIキー、ログ|危険入力を拒否し秘密を漏らさない|
|保守性|依存固定、CI、SBOM、API変更監視|再現可能なビルドと警告|

## 既存候補の評価

`heritage-research-mcp`は7資料源、Record/Rights/Media正規化、キーredaction、download安全層を備える設計参考として高評価だが、Alphaで公式MCP Registry登録は確認できず、機関APIの全能力は不均一である。[1] ScriptoriaはIIIFプロバイダ解決とページ取得が強い一方、GPL-3.0-or-laterで直接採用に制約がある。[2] NDL系OSSはNDL専用コネクタのたたき台に適するが、LICENSE不一致、実装不足、テスト／保守の不確実性がある。[3][4]

公式API候補では、LoCが書誌、OCR、IIIF、SRUを同一機関で確認できるため最初の評価対象とする。[5] Europeanaは横断探索、GallicaはALTO/OCR/IIIF、DDBは機関横断とmanifestで補完的だが、認証・レート・権利・適用範囲は別途評価する。[6][7][8]

## Phase 1の試験ケース

1. 通常のタイトル検索とゼロ件検索。
2. 多言語・Unicode・RTL・ダイアクリティカルマーク。
3. OCRスニペットと座標の原ページ対応。
4. IIIF manifestからCanvasとImage API URLの解決。
5. rights unknown、restricted、knownの表示。
6. APIキーなし／期限切れ／429／Retry-After。
7. XMLの外部エンティティ、巨大レスポンス、悪意あるURL。
8. 同一資料が複数ソースに出る場合の重複・provenance。

## 未確定事項
Global Libraryの現行ツール・対象機関・スキーマ・利用者数・SLA・予算・認証・保守責任者、各機関の数値レート制限、全コレクションのOCR適用範囲、画像・本文の再配布権はunknownである。したがって現時点で「重複率」「既存OSSで置換可能」「本番SLA達成」を数値化しない。

## References
[1]: https://github.com/magicianmarty/heritage-research-mcp "heritage-research-mcp"
[2]: https://github.com/nikazzio/scriptoria "Scriptoria"
[3]: https://github.com/knagata/ndl-mcp "knagata/ndl-mcp"
[4]: https://github.com/sho0318/ndl-mcp "sho0318/ndl-mcp"
[5]: https://www.loc.gov/apis/ "Library of Congress APIs"
[6]: https://api.europeana.eu/ "Europeana APIs"
[7]: https://api.bnf.fr/fr/api-document-de-gallica "Gallica API"
[8]: https://labs.deutsche-digitale-bibliothek.de/app/ddbapi/ "DDB API"
