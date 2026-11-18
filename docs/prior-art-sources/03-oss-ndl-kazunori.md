# Phase 0 OSS調査メモ: MCP-ndl-search

- **対象**: [kazunori-Ohashi/MCP-ndl-search](https://github.com/kazunori-Ohashi/MCP-ndl-search)
- **ページタイトル**: MCP-ndl-search / NDL-MCP Pipeline
- **確認日**: 2026-11-19
- **調査目的**: Global Library MCPの新規実装前に、既存OSSの機能、データ範囲、API・標準、ライセンス、保守状況、コード品質・セキュリティ、再利用可能性、重複・差分を事実確認する。

## 1. 結論

本OSSは、TypeScriptで実装されたローカル実行型のMCPサーバー／HTTPブリッジで、国立国会図書館サーチ（NDL Search）の**SRU検索API**を呼び出し、自然言語・タイトル・件名・説明・直接CQL検索をMCPツールとして公開する小規模な統合実装である。README上はOpenAIによる任意の自然言語→CQL変換、結果のスコアリング、図書館所蔵情報のオプション取得、キャッシュ・レート制限・メトリクス等を掲げている。

一方、実コードで確認できたNDL接続はSRUに限定される。OAI-PMHハーベスト、OpenSearch/OpenURL、NDL書影API、IIIF、画像ページ取得、全文取得、OCRサービスを呼び出す実装は確認できない。したがって、**NDLの書誌・一部所蔵情報検索の参考実装としては再利用候補だが、Global Library MCPの機関横断検索・全文／画像／ページ取得基盤の代替にはならない**。

package.jsonにはMITと記載されるが、GitHubリポジトリのトップレベルにLICENSEファイルは存在せず、GitHub APIの`license`もnullだった。このため、法的な再利用判断では著作権者によるライセンス付与を別途確認する必要がある。リポジトリは2025-08-20以降コミットがなく、2026-05-08のGitHubメタデータ更新はコード更新を意味しない。npm公開パッケージおよびMCP Registry登録は確認できなかった。

## 2. 公式リポジトリで確認した事実

### 機能・MCPツール

READMEは以下のMCPツールを記載する。

- `ndl_search_by_description`: 内容・テーマ中心の検索。
- `ndl_search_by_subject`: 件名検索。
- `ndl_search_by_title`: 書名検索。
- `ndl_search_books`: 自然言語の総合検索。OpenAI APIが設定されている場合にLLMでクエリ最適化。
- `ndl_sru_search`: 実装内の`src/mcp/tools/sruSearch.ts`で確認できる、直接CQLを渡すSRU検索。

READMEは、タイトル・件名・内容説明・著者、最大件数、言語、出力形式（JSON/YAML）、`includeHoldings`による所蔵情報取得を説明する。コード上も`src/core/ndlConnector.ts`は`https://ndlsearch.ndl.go.jp/api/sru`をデフォルトURLとし、AxiosでSRUリクエストを送信し、XMLを`xml2js`で解析する。リトライ、タイムアウト、ログがある。

実装のアーキテクチャとして、自然言語入力→（任意のOpenAIアダプタによる）CQL生成→バリデーション→NDL SRU→XMLマッピング→フィルタ／スコアリング→MCP公開、という流れが確認できる。`includeHoldings`はDC-NDL XML内の所蔵要素を抽出する設計で、NDL APIに別の図書館横断APIを呼ぶコードは確認できない。

### 対応機関・データ範囲

公式NDL資料上、NDL Search APIは許諾を得たデータプロバイダのメタデータを提供する。プロバイダ一覧には国立国会図書館蔵書、全国書誌、NDL新着書誌、NDL雑誌記事索引（通常／オンライン）、NDLデジタルコレクション等に加え、青空文庫、J-STAGE、WARP、IRDB、大学・公共図書館の各種データベース等が掲載されている。ただし、対象OSS自身はSRUのデータプロバイダを固定して網羅的に選択する機能をREADMEで説明しておらず、実際の対応範囲はNDL Search SRUの設定と検索対象に依存する。

`includeHoldings`について、READMEは「全国の図書館の所蔵状況」と説明する。コードは返却XMLの所蔵要素をマッピングするが、全機関・全所蔵の網羅性、最新性、利用可否の意味はこの調査では確認できない。これは「NDL Searchに返った所蔵情報を整形する機能」と評価するのが安全である。

### API・標準規格

NDL公式仕様で確認できるAPIは以下のとおり。

- 検索API: SRU、OpenSearch、OpenURL。
- ハーベストAPI: OAI-PMH。
- 書影API: ISBNまたはJP-eコードからJPEG書影を取得。
- データ形式: DC-NDL（RDF）を基本とし、RDF/XMLで出力。DC-NDLはDublin Coreを基礎にNDL拡張を加えた仕様。
- OAI-PMHのメタデータ形式: `oai_dc`、`dcndl`、`dcndl_v3`。`ListRecords`の1回あたり上限は200件で、`resumptionToken`により継続取得する。

対象OSSのコードで確認できる直接利用はSRUのみ。CQLのフィールドとしてタイトル、著者、件名、ISBN、発行日、言語等を扱う設計が見える。MCP自体は`@modelcontextprotocol/sdk`依存で実装されているが、MCP仕様の対応バージョンや機能（リソース、サンプリング等）の詳細適合性は未確認。

### 全文・OCR・画像・ページ単位取得（機関／API別）

以下は、対象OSSの実装確認とNDL公式API仕様を分けて記録したもの。

- **NDL Search／国立国会図書館蔵書**: 対象OSSはSRUによる書誌検索のみ確認。全文取得、全文検索、OCRテキスト取得、画像取得、ページ単位取得、IIIF、機関別SRU以外の取得は**対象OSSでは未実装**。NDL公式Search API仕様にも、一般の検索APIとして全文本文やページ画像を返す記載は確認できない。全文／OCRの可否は資料・デジタルコレクション側のサービス条件に依存し、対象OSSから利用できることは**unknown**。
- **NDLデジタルコレクション**: NDL公式にはデジタル資料の閲覧サービスがあること、NDL SearchのOAI-PMHで`ndl-dl`／`ndl-dl-online`の書誌メタデータを取得できることは確認できる。ただし、対象OSSはOAI-PMH、IIIF、ページ画像・本文・OCRエンドポイントを実装していない。NDL Search APIだけで全文・OCR・ページ単位取得が可能かは**unknown**。
- **NDL Searchの書影API／JPRO**: ISBNまたはJP-eコードからJPEGの表紙画像を返す公式APIがある。ただし対象OSSのコードに書影API呼び出しは確認できず、返却型に`thumbnail_url`項目はあるものの、実装で生成・取得する経路は**未確認**。ページ画像ではなく表紙画像である。
- **その他のNDL Searchデータプロバイダ（青空文庫、J-STAGE、WARP、IRDB、大学・公共図書館等）**: NDL公式プロバイダ一覧で検索／ハーベスト対応の有無や利用条件がプロバイダ別に掲載されるが、対象OSSはそれらを機関別に切り替えて全文・画像・IIIF等を取得する機能を持たない。各プロバイダの全文、OCR、画像、ページ単位、IIIF、SRU、OAI-PMHの可否を対象OSSから一律に断定する根拠はなく、**unknown**。

## 3. ライセンス・再利用可能性

### 確認できた事実

- `package.json`: `license: "MIT"`。
- README: MIT Licenseと記載。
- GitHub API: `license: null`。
- `git clone`したmainブランチのトップレベルに`LICENSE`ファイルなし。
- npm Registryの`ndl-mcp-pipeline`は404で、公開npmパッケージは確認できない。
- MCP Registry APIの`search=kazunori-Ohashi`は`servers: []`で、掲載を確認できない。

### 法的・運用上の評価

package.json／READMEの記載だけならMIT意図は読み取れるが、LICENSE本文がないため、第三者が安心して再配布・改変できる状態かは**未確認**。再利用する場合は、著作権者にLICENSEの補充または明示的な許諾を得て、NDL各データプロバイダのメタデータ利用条件、NDL Search APIのクレジット要件、継続利用時の申請要否を別途満たす必要がある。コードのライセンスとNDLメタデータ／画像／本文の利用条件は別物である。

## 4. 最終更新・保守状況

- GitHubリポジトリ作成: 2025-08-18。
- GitHub上のコードコミット: 5件。
- 最終コミット（main確認）: 2025-08-20頃（`22cb479`, 収蔵図書館に関するバグ修正）。
- GitHub APIの`updated_at`: 2026-05-08。ただし`pushed_at`は2025-08-20であり、前者をコード更新とは解釈しない。
- スター6、フォーク1、Issue 0、アーカイブではない（確認日現在のGitHub API値）。
- リリース、継続的な更新、脆弱性対応、CIの実行成功はこの調査では確認できない。

保守は「活動が少なく、公開後の更新は確認できない」と評価する。Issueが0件であることは品質保証や利用者不在を意味しない。

## 5. コード品質・セキュリティ上の注意

### 確認できた良い点

- TypeScript、`strict`設定、Zodによる環境値・入力の検証、CQLバリデーション、最大レコード数上限、リトライ・タイムアウト、キャッシュ・レート制限・ログの実装がある。
- XMLマッパー、NDLコネクタ、クエリ生成、MCPツール等の単体テストがある。
- OpenAI APIキーは任意設定で、未設定時にルールベース経路を持つ設計。

### 確認できた懸念

- `npm ci --ignore-scripts`後の`npm test -- --runInBand`は、56テスト中55成功・1失敗で、7スイート中2スイート失敗。`xmlMapper.spec.ts`は型定義とテスト期待（`pub_date`、`identifiers`、`raw_record`、`source.provider`等）の不整合でコンパイル失敗。E2Eは期待件数1に対し0件。
- package.jsonの`lint`は実質的に`echo`のみで、READMEの「ESLint + Prettier」方針を実際のLint検査として実行しない。`lint:fix`も実処理なし。
- npmインストール時の監査出力は21 vulnerabilities（low 1、moderate 3、high 16、critical 1）を報告。これは依存解決時点のローカル監査結果であり、個別脆弱性・到達可能性・修正版適用後の状態は未精査。再利用前に`npm audit`を再実行し、lockfileと依存更新を行うべき。
- OpenAIへ自然言語クエリを送る場合、利用者の検索文が外部LLMに送信される。データ保護・ログ・プロンプトインジェクション耐性・キー管理は導入側で確認が必要。
- `NDL_BASE_URL`を環境変数で変更できるため、運用環境では許可先を制限しないと意図しない外部接続先を指定できる可能性がある。実際の脅威成立性はデプロイ形態次第であり、ここは注意事項（推測）とする。
- NDL公式は大量・連続アクセスで制限・ブロックの可能性を説明している。対象OSSのレート制限が複数インスタンスや共有IP全体を保護するかは未確認。
- READMEの所蔵・95%以上削減・85%+カバレッジ等の数値は、確認した現行コード・テスト実行結果からは裏付けられない、または目標値として記載された主張である。

## 6. Global Library MCPとの重複と差分

Global Library MCP側の詳細仕様は本調査対象資料に含まれていないため、厳密な差分表は**unknown**。それでも、既存OSSから確実に言える重複候補は以下である。

- NDL Searchを検索バックエンドとして使う場合のSRU接続、CQL生成、XML/DC-NDLマッピング、書誌検索MCPツール。
- タイトル／著者／件名／発行年等の書誌検索と、任意の所蔵情報フィールド。
- MCP stdioサーバーおよびHTTPブリッジの基本パターン。

差分候補（対象OSSにないもの、または少なくとも確認できないもの）は以下である。

- 複数の国・機関を横断する正規化・重複排除・出典／権利情報の統合。
- API種別の統合（SRU、OpenSearch、OpenURL、OAI-PMH、IIIF等）。
- 全文・OCR・画像・ページ単位取得、取得権限／利用条件の機関別表示。
- NDL Search以外の機関へ直接接続するコネクタと、機関別の能力表。
- 継続的保守、依存脆弱性管理、統合テスト、ライセンス証跡。

したがって、再利用するならSRUコネクタ・DC-NDL XMLマッピング・CQL安全化の一部を参考にし、Global Library MCPの共通スキーマ、機関別能力宣言、権利・出典メタデータ、全文／画像抽象化は新たに設計するのが妥当。ただしMITライセンスの法的確認が前提である。

## 7. 未確認事項（unknown）

- 著作権者がpackage.jsonのMIT記載を正式なライセンス付与として意図しているか、LICENSE欠落が一時的か。
- 対象OSSの実運用時のNDL Search検索対象DP、所蔵情報の網羅性・更新頻度・利用可否の正確性。
- NDLデジタルコレクションおよび各プロバイダの全文、OCR、画像、ページ単位、IIIFの利用可否を、このOSS経由で提供できるか（コード上は未実装）。
- MCP Registry以外のマーケットプレイス、Docker、バイナリ配布、非公開利用実績。
- CIの履歴、未公開ブランチ、実運用での性能・レート制限・セキュリティ評価。
- Global Library MCPの現行コネクタ、共通スキーマ、機能要件との厳密な重複度。

## 8. 推奨事項

1. そのまま依存するのではなく、まずLICENSE本文または著作権者の明示許諾を取得する。
2. 再利用範囲をNDL SRU書誌検索・DC-NDLマッピング・所蔵フィールド抽出に限定し、全文/OCR/画像/ページ取得が必要な機関は別コネクタとして設計する。
3. NDL公式の最新API仕様、データプロバイダ別利用条件、クレジット、継続利用時の申請要否を実装・運用設計に組み込む。
4. 依存を更新し、`npm audit`の21件報告を個別に解消・受容判断したうえで、型エラーとE2E失敗を修正し、実際に有効なlint・CIを導入する。
5. OpenAI利用をオプトインとして明示し、検索文の外部送信、機密情報、ログ、プロンプトインジェクションを扱うポリシーを追加する。
6. Global Library MCPへ取り込む場合は、元OSSを丸ごと組み込むより、ライセンス確認後にコネクタとマッパーの設計を参考にし、共通の能力表・出典・権利・ページ／全文モデルを別実装する。

## References

[1]: https://github.com/kazunori-Ohashi/MCP-ndl-search "MCP-ndl-search GitHub repository"
[2]: https://api.github.com/repos/kazunori-Ohashi/MCP-ndl-search "MCP-ndl-search GitHub repository metadata API"
[3]: https://raw.githubusercontent.com/kazunori-Ohashi/MCP-ndl-search/main/package.json "MCP-ndl-search package.json"
[4]: https://ndlsearch.ndl.go.jp/en/help/api "NDL Search API: How to use"
[5]: https://ndlsearch.ndl.go.jp/en/help/api/specifications "NDL Search API specifications overview"
[6]: https://ndlsearch.ndl.go.jp/en/help/api/provider "NDL Search API-providing databases"
[7]: https://ndlsearch.ndl.go.jp/en/help/api/oai_pmh "NDL Search OAI-PMH"
[8]: https://ndlsearch.ndl.go.jp/en/help/api/thumbnail "NDL Search cover-image API"
[9]: https://ndlsearch.ndl.go.jp/en/renkei/dcndl "DC-NDL RDF format specification"
[10]: https://www.ndl.go.jp/en/dlib/ "National Diet Library digital library projects"
[11]: https://registry.modelcontextprotocol.io/v0.1/servers?search=kazunori-Ohashi "MCP Registry search for kazunori-Ohashi"
