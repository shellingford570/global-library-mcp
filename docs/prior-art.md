# Global Library MCP Phase 0：既存プロジェクト調査

- **確認日**：2026-11-19
- **状態**：Phase 0調査成果物。実装完了を意味しない。
- **調査範囲**：既存MCP、公式図書館・アーカイブAPI、IIIF/SRU/OAI-PMH等の標準。

## 結論
最も合理的なのは、既存OSSの全面採用ではなく、**公式APIを優先した新規の薄いアダプタ／オーケストレーション層**を実装し、成熟したOSSから設計パターンだけを採用する案である。特にLoC、Gallica、Europeana、DDB v2、NDL/Japan Searchを初期候補とし、IIIF、SRU、OAI-PMHを能力別に分離する。既存コードは機関固有APIの疎通・XML/JSONマッピングの参考にはなるが、ライセンス欠落、機能不均一、テスト不足、権利情報の欠落があるため、そのまま依存しない。

## 既存利用・拡張・新規開発の比較

|案|利点|問題|判断|
|---|---|---|---|
|既存利用|短期に検索・OCR・IIIFを得られる。`heritage-research-mcp`はRecord/Rights/Media正規化、APIキー秘匿、ダウンロード安全策を示す。[1] |対象機関とツールが限定され、機関横断スキーマや権利モデルがGlobal Libraryと一致する保証がない。|限定的な参考利用のみ|
|既存OSSの拡張|`ndl-mcp`群はNDLのSRU/OpenSearch、OCR、ページ検索の足場になる。[2][3] `newspapers-mcp`はGallica/DelpherのSRUと複数IIIFパターンを示す。[4] |MIT表記とLICENSE欠落の不一致、URLエンコード欠落、実装とREADMEの不一致、テスト・レート制御不足がある。[2][4] |権利確認後に独立アダプタへ限定移植|
|新規開発|共通スキーマ、capabilities、rights、出典、レート制御を最初から設計できる。 |初期工数と公式API個別検証が必要。 |推奨|

ScriptoriaはIIIFマニフェスト解決、プロバイダレジストリ、ページ取得の設計参考として有用だが、GPL-3.0-or-laterであるため直接コード取り込みは法務確認を先行する。[5] `MCP-ndl-search`はSRU書誌検索の参考になるが、npm auditで脆弱性報告、テスト失敗、LICENSE実体欠落が確認された。[6]

## 8つの判断事項

1. **近いプロジェクト**：機能面では`heritage-research-mcp`が横断検索・権利・メディアに最も近い。IIIF深掘りはScriptoria、NDL専用は`knagata/ndl-mcp`、`sho0318/ndl-mcp`、新聞は`newspapers-mcp`が近い。[1][2][3][4][5]
2. **既存OSSで可能な範囲**：書誌検索、SRU/CQL、NDL OCR全文・ページ検索、Gallica/DelpherのOCR抜粋、IIIFマニフェストからのCanvas/画像解決、権利フィールドの正規化パターンは再現可能。ただし各OSSの実装範囲をGlobal Library全体の能力とみなしてはならない。
3. **独自開発部分**：機関共通`Record/Rights/Media/Page/TextEvidence`モデル、能力表、検索統合、引用・出典、rights unknown優先、認証・レート制御・キャッシュ、SSRF/XXE対策、監査ログ、契約テストが独自領域となる。
4. **最初の図書館**：第一候補は**米国議会図書館（LoC）**。公式JSON/YAML、Text Services、IIIF Image Services、SRU/CQLが一つの機関で確認できる。[7] 並行してNDLまたはGallicaを比較用コネクタにする。
5. **期間／費用**：Phase 0では見積を確定しない。Phase 1の目安はLoC1機関、検索・レコード・IIIF・OCR証拠の最小垂直スライスを2–4週間、APIキー・有料サービス費は原則未定／公式無料枠中心とする。実際の工数・費用は認証、利用規約、SLA、テストデータ確認後に再見積する。
6. **技術スタック**：Python 3.11+、FastMCP、httpx、Pydantic、defusedxml等を推奨。XMLはSRU/OAI-PMH/ALTO/METS、JSONは機関固有API、非同期HTTP、pytest/respx、ruff/pyright、SBOM・脆弱性スキャンを採用する。これは推奨であり実装済みではない。
7. **ライセンス**：Global Library本体は別途選定する。MIT OSSはLICENSE実体を確認できたものだけ利用し、GPL-3.0-or-laterのScriptoriaはプロセス分離または仕様参照を基本とする。上流資料のメタデータ、OCR、画像はコードライセンスと別にアイテム単位の権利・利用条件を保持する。[5]
8. **Phase 1計画**：LoCを対象に、(a) capability discovery、(b) JSON/SRU検索、(c) record正規化、(d) IIIF manifest/image link、(e) Text ServicesのOCRスニペットと座標、(f) rights/provenance、(g) fixture契約テスト、(h)レート制御・監査ログを実装する。完了条件はライブ疎通、失敗時の構造化エラー、権利表示、出典URL、unknownの保持である。

## 確認済み事実とunknown

確認済み事実は各既存調査のrawメモおよび下記Referencesに基づく。Global Library MCP自体の正式ツール、既存コネクタ、共通スキーマ、認証方式、保守者は入力資料から未確認であり、重複率・置換可否は**unknown**である。各機関の全文・OCR・画像・ページ取得も、公式に確認できたAPI以外は機関ごとにunknownとする。

## References

[1]: https://github.com/magicianmarty/heritage-research-mcp "heritage-research-mcp"
[2]: https://github.com/knagata/ndl-mcp "knagata/ndl-mcp"
[3]: https://github.com/sho0318/ndl-mcp "sho0318/ndl-mcp"
[4]: https://github.com/raphink/newspapers-mcp "newspapers-mcp"
[5]: https://github.com/nikazzio/scriptoria "Scriptoria"
[6]: https://github.com/kazunori-Ohashi/MCP-ndl-search "MCP-ndl-search"
[7]: https://www.loc.gov/apis/ "APIs at the Library of Congress"
