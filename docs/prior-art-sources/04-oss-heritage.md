# Phase 0 OSS調査: heritage-research-mcp

- **対象**: https://github.com/magicianmarty/heritage-research-mcp
- **ページタイトル**: GitHub - magicianmarty/heritage-research-mcp
- **確認日**: 2026-11-19
- **調査対象**: 既存OSSの機能、データ範囲、API/標準、ライセンス、更新・保守、品質/セキュリティ、再利用可能性、Global Library MCPとの重複・差分
- **判定の原則**: 公式ページ・公式API仕様・リポジトリ実装を事実として記録した。推測は「推測」、確認できないものは `unknown` と記録した。

## 結論

`heritage-research-mcp` は、歴史研究向けの Python 製 MCP stdio サーバーで、7つの資料源を一つの正規化された Record/Rights/Media 形式にまとめる。対象は Internet Archive、Wikimedia Commons、Digital Public Library of America (DPLA)、米国国立公文書館 NARA、Smithsonian Open Access、Library of Congress の Chronicling America、Richmond Daily Dispatch である。[1][2]

実装上の強みは、(a) ソース横断検索と各ソース固有ツール、(b) 権利情報を `unknown` を含む統一語彙で返すこと、(c) APIキーの秘匿、リトライ/レート制御、ダウンロード時のHTTPS・公開アドレス・サイズ制限・リダイレクト再検査、(d) OCR/全文検索とローカル索引を含むことにある。[2][3]

一方、確認できた公開リポジトリは作成日が2026-10-06、最新確認コミットは2026-10-27、PyPI/npmへの公開は確認できず、公式MCP Registryの検索結果は0件である。[1][4][5] PyPIのHTMLページはCAPTCHAで内容取得できなかったため、PyPI掲載は `unknown` とする。Global Library MCPの既存仕様・実装は本調査資料に与えられていないため、具体的なツール単位の重複判定は `unknown` とし、一般的な機能差分だけを「比較可能な範囲」として記す。

## 機能と実装範囲（リポジトリで確認できた事実）

- 共通ツールは `search`、`get_record`、`list_sources`、`download_media`。検索結果は短い説明と先頭2ファイル程度に抑え、詳細取得は `get_record` またはソース固有の get ツールで行う。[1][2]
- Internet Archive には通常検索、`fulltext=true`、`ia_grep_text`、`ia_read_text` がある。書籍・回顧録・連隊史・公式報告などのOCR全文を探す用途である。[1][2]
- Commons はファイルのライセンス情報を読み、DPLA/NARA/Smithsonian 等と同じ正規化 Record にする。Wikimedia の追跡パラメータを削る処理もリリースノートに記載される。[1][4]
- DPLA、NARA、Smithsonian は無料APIキーが必要で、キー未設定のソースだけをスキップし、他ソースの検索は継続する。[1][2]
- NARA 固有ツールは `nara_search`、`nara_get_record`、`nara_extracted_text` 等。記録群/シリーズ、資料種別・場所・作成者等の情報、OCRとパートナー転写を返す。[1][4]
- Chronicling America 固有ツールは `chronam_search`、`chronam_page_text`、バルクOCRの計画・構築・ローカル検索。loc.gov API は1リクエスト/3秒の設定で、429またはbot challenge時にはクールダウンする。[1][2]
- Richmond Daily Dispatch はリモート検索APIではなく、公開される約92MBのTEIデータを checked downloader で取得し、SQLite FTS5 ローカル索引を構築して検索する。機関側のSolr検索はHTTP資格情報の背後にあり、本OSSは利用しないと設計文書にある。[2]
- ダウンロードは `download_media` とCLI `heritage-research-mcp download`。ダウンロード物には provenance sidecar が付く。ホスト型MCPでは `HERITAGE_MCP_DISABLE_DOWNLOADS=1` でMCPツールを無効化する設計である。[1][2]

## 機関/API/標準の確認

### Internet Archive

公式Developer Portalは、Itemが複数ファイルを持つこと、メタデータAPIと各種API/サービスが存在することを説明する。[6] リポジトリREADME/設計は、メタデータ検索、ファイル一覧、OCR全文検索、ファイル取得を実装範囲としている。[1][2]

- 全文検索: **確認済み**。READMEの `fulltext=true` と `ia_grep_text`/`ia_read_text` が明記され、公式HelpもOCR済みテキストの全文検索を説明する。[1][7]
- OCR: **確認済み（利用可能なアイテムに限る）**。サーバーはIAのOCR/テキストファイルを読む。全アイテムにOCRがあるとは確認できない。
- 画像/ファイル: **確認済み**。IA Itemは複数ファイルを持てるという公式仕様と、OSSのファイル情報・ダウンロード機能が一致する。[1][6]
- ページ単位取得: **部分確認**。`ia_read_text` は書籍内の位置周辺のテキストを読むが、画像ページをページ番号で取得する機能は設計文書で未実装（IIIF画像fetchingは「Ideas not built」）とされる。[2]
- IIIF/SRU/OAI-PMH: **unknown**（このOSSがこれらを利用することは確認できない）。IAの公式Developer Portalで一般API/メタデータ/ファイルAPIは確認したが、対象OSSのIAアダプタがIIIF、SRU、OAI-PMHを使う証拠は確認できなかった。[2][6]

### Wikimedia Commons

公式Commons APIページは MediaWiki API によるカテゴリ、ファイルの `imageinfo`、埋込メタデータ、ファイルページメタデータ（`extmetadata`）、カテゴリ内ファイル取得を例示する。[8]

- 全文検索: **unknown**。MediaWiki APIのページ/ファイル検索はあるが、OCR全文検索を対象OSSが提供するとは確認できない。
- OCR: **unknown**（対象OSSのCommonsアダプタにOCR実装の事実なし）。
- 画像: **確認済み**。`imageinfo` とファイルURL/メタデータを使う。権利情報は各ファイルページから読む。[1][8]
- ページ単位取得: **unknown**。画像ファイルの取得は確認できるが、冊子/資料をページ集合として取得する機能は確認できない。
- IIIF/SRU/OAI-PMH: **unknown**。対象OSSがこれらを利用する根拠は確認できない。Commons APIとして公式に確認できたのはMediaWiki APIである。[8]

### Digital Public Library of America (DPLA)

DPLA公式APIはREST APIで、`/v2/items?q=...` によるアイテムの全文（全フィールド）検索を提供する。DPLA APIはアイテム/コレクションのメタデータを返し、APIキーが必要である。[9] DPLA MAP 3.1はEDMを基礎に、Dublin Core、MODS、ORE等とクロスウォークする。[10]

- 全文検索: **確認済み（メタデータ全文）**。公式仕様の「all fields associated with items」の検索であり、資料本文OCR全文とは異なる。[9]
- OCR: **unknown**。DPLA APIは集約メタデータと元レコードを返すが、全プロバイダのOCRを提供する仕様は確認できない。対象OSSのDPLAアダプタにもOCR本文取得の記載は確認できない。[1][10]
- 画像: **部分確認**。DPLA MAPの `object`/`hasView` はプレビュー/デジタルオブジェクトのURLや権利情報を表すが、すべての提供者で原画像が取得できるとは限らない。[10]
- ページ単位取得: **unknown**。DPLA自体のAPIでページ単位取得を保証する仕様は確認できない。元提供者のURLへ委譲される。
- IIIF/SRU/OAI-PMH: **部分確認/unknown**。DPLAの元レコード例にはOAI由来の識別子が現れるが、DPLA APIそのものがSRU/OAI-PMH/IIIFエンドポイントであることは確認できない。対象OSSがそれらを直接利用することは未確認。[9][10]

### U.S. National Archives Catalog (NARA)

NARA公式API仕様は、`GET /records/search`、`/records/{parentNaId}/{parentNaId}`、`/extractedText/{naId}`、`/other-extracted-text/search` 等を列挙する。APIキーを `x-api-key` ヘッダで送る必要がある。[11]

- 全文検索: **確認済み（カタログ・抽出テキスト検索）**。公式仕様に通常レコード検索、`by-other-extracted-text`、抽出テキスト関連エンドポイントがある。[11]
- OCR: **確認済み**。対象OSSは `nara_extracted_text` で機械OCRとパートナー転写をラベル付きで返すと説明し、公式APIにも `/extractedText/{naId}` がある。[2][4][11]
- 画像/デジタルファイル: **確認済み（記録のオンライン可用性・media情報の範囲）**。公式仕様にオンライン可用性エンドポイントとファイル/デジタルオブジェクトのスキーマがある。対象OSSはメディア情報を返し、ダウンロードする。[2][11]
- ページ単位取得: **unknown**。抽出テキストやデジタルオブジェクトは取得できるが、NARA API仕様から対象OSSのページ番号単位の画像/本文取得を断定できない。
- IIIF/SRU/OAI-PMH: **unknown**。確認した公式Catalog API仕様と対象OSS実装から、これらの利用は確認できない。[2][11]

### Smithsonian Open Access

Smithsonian公式ページは、Open Access API、APIキー登録、JSONデータ、公開対象画像の対応画像URLを説明する。データは週次更新とされる。[12] API仕様は、`/search`、`/category/:cat/search`、`/content/:id`、`/terms/:category` を定義し、検索はフィールド指定・ページング・最大1000行、contentはID/URLで取得する。[13]

- 全文検索: **確認済み（メタデータ検索）**。`q` はfielded/non-fielded queryに対応するが、資料本文全文検索とは書かれていない。[13]
- OCR: **unknown**。公式API仕様と対象OSS説明から、OCR本文の提供を確認できない。
- 画像: **確認済み（CC0対象のデジタル画像）**。公式ページは公開対象物の画像URLを提供し、著作権等の制約があるものはメディアファイルを出さないと説明する。[12]
- ページ単位取得: **unknown**。`content/:id` の単一レコード取得は確認できるが、冊子をページ単位で取得する仕様は確認できない。[13]
- IIIF/SRU/OAI-PMH: **unknown**。Open Access APIがこれらの標準を使うことは確認できない。

### Library of Congress: Chronicling America

Library of Congress公式技術情報は、JSON/YAML API、Text Services API（全文・単語座標・コンテキストスニペット）、Image Services API（IIIF Image API）、OCRの検索利用、OCRバルクダウンロードを明記する。[14]

- 全文検索: **確認済み**。対象OSSの `chronam_search` と公式Text Services API/検索が対応する。[2][14]
- OCR: **確認済み**。ページのraw OCRとバルクOCRデータセットを対象OSSが扱い、公式もOCRバルク提供を明記する。[1][14]
- 画像: **確認済み**。Image Services APIはIIIF Image API準拠である。[14]
- ページ単位取得: **確認済み**。`chronam_page_text` はページのOCRを取得し、公式のページAPI/Text Services APIがページ単位アクセスを支える。[1][14]
- IIIF/SRU/OAI-PMH: **IIIF確認済み、SRU/OAI-PMHはunknown**。IIIF Image APIは公式明記。対象OSSは画像のIIIF fetchingを未実装アイデアとしているため、接続しているのは主にLOC JSON/Text APIとOCRバルクである。[2][14]

### Richmond Daily Dispatch

対象OSSの設計文書によると、サイトの検索ボックスはSolr coreだがHTTP資格情報の背後にあり、利用可能な公開検索APIはない。そのため、公開TEI一括データを取得し、ローカルSQLite FTS5索引を構築する。[2]

- 全文検索: **確認済み（ローカル索引のみ）**。リモートAPI検索ではない。[2]
- OCR: **unknown**。TEI全文を扱うが、それがOCRか校訂テキストかは対象OSS資料から断定できない。
- 画像: **unknown**。このアダプタの主目的はTEI本文で、画像取得の仕様は確認できない。
- ページ単位取得: **unknown**。`dispatch_issue`/`dispatch_get_article` の記事・号単位はあるが、画像ページ単位取得は確認できない。
- IIIF/SRU/OAI-PMH: **unknown**。公開標準APIの利用は確認できない。

## 標準規格・データモデル

対象OSS自身のMCPインターフェースはPython MCP SDKに依存し、SDK 1.x/2.xの差を `compat.py` で吸収すると設計文書にある。[2] 内部の正規化モデルは独自の `Record`、`Rights`、`Media` であり、権利は `free`、`attribution`、`share_alike`、`non_commercial`、`no_derivatives`、`restricted`、`unknown` を使う。`unknown` を「自由利用可」と解釈しない点は明示的である。[1][2]

外部メタデータ標準は接続先依存である。DPLAはMAP 3.1を基礎にEDM、Dublin Core、MODS、ORE等へクロスウォークする。[10] Chronicling AmericaはIIIF Image APIを使用する。[14] RichmondはTEIデータを扱うとされるが、対象OSSが外部TEI仕様のどのプロファイルに準拠するかは `unknown`。SRU/OAI-PMHの利用は、今回確認した対象OSS実装では一般に `unknown` とした。

## ライセンス、配布、保守

- リポジトリライセンスは **MIT**。ただし返却される記録・ファイルは各ホルダーの利用条件に従う。[1]
- `pyproject.toml` のパッケージ名は `heritage-research-mcp`、バージョンは **0.2.0**、Python **>=3.11**、依存は `mcp>=1.2.0`、`httpx>=0.27.0`、`pydantic>=2.0.0`。開発依存にはpytest、respx、ruff、pyright等がある。[15]
- GitHubは2026-10-06作成、2026-10-07公開のv0.2.0がNARAの実レスポンス検証を含む。最新取得コミットは2026-10-27で、GitHub Actionsのsetup-python更新。リポジトリ表示上のコミット数は18。[1][4][5]
- CIはPython 3.11/3.13、MCP SDK 1.x/2.xを対象にし、pytest、ruff、pyrightを実行する。テストはrespxモック中心で、live smoke/doctor --live も用意されるが、設計文書はloc.gov challengeのため開発マシンからのlive実行ができていないと記す。[2]
- 公式MCP Registry APIの `search=heritage-research-mcp` は `{"servers":[],"metadata":{"count":0}}` だった。[4]
- PyPIページは確認時にCAPTCHAで本文取得に失敗し、PyPI掲載は `unknown`。npmパッケージは検索で該当公式ページを確認できず、**unknown（未掲載と断定しない）**。READMEはgit URLを `uvx --from` でインストールする方式である。[1]

## コード品質・セキュリティ上の注意

肯定的な確認事項として、設計文書はアダプタをMCPから分離したasync関数とし、オフラインfixtureによるテスト、ruff/pyright、2世代SDK CIを説明する。[2] HTTP層はペーシング、リトライ、サイズ上限、キーのredactionを持つ。ダウンロード層はHTTPS限定、公開アドレス限定、認証情報/非標準ポート拒否、リダイレクトごとの再検査、サイズ制限、atomic writeを行う。[2][3]

注意点は次のとおり。

1. リポジトリ自身の分類はPyPI上で `Development Status :: 3 - Alpha`。実運用前に依存関係を固定し、タグ（v0.2.0）等の再現可能な参照を使うべきである。[15]
2. NARA、DPLA、SmithsonianのAPIキーを扱う。キーは環境変数または設定ファイルで保持し、結果・ログへ出さない設計だが、利用者側で秘密管理と最小権限を確保する必要がある。[2][3]
3. ダウンロードURLは第三者データ由来であり、設計上SSRF対策をしているが、DNS再解決競合について設計文書自身が完全排除ではなく「露出を限定」と説明する。sandbox/ホスト権限で実行する際は、ダウンロード無効化を検討する。[2]
4. TEIは外部DTD/SGML entityのためXMLパーサーではなく正規表現で処理する設計である。安全性・互換性の意図は合理的だが、複雑なTEI変形に対する取りこぼしリスクは残る（これはコード品質上の推測）。[2]
5. Chronicling Americaのbulk shortcutは全アーカイブを完全検証しない経路があり、設計文書が未検証の並び順リスクを明記する。厳密性が必要なら `--verify` 相当の完全検証を使うべきである。[2]
6. live APIの将来変更、レート制限、Cloudflare/bot challenge、キー発行条件、各ホルダーの権利変更により、検索可用性と再利用可否は変わる。これは実装の保証ではない。[2][14]

脆弱性の報告方法は、公開issueではなくGitHub SecurityタブのReport a vulnerabilityを使うようSECURITY.mdに記載される。[3]

## Global Library MCPとの重複・差分

Global Library MCPのツール一覧、接続先、データモデル、標準規格方針が本調査依頼には含まれていないため、**具体的な重複判定はunknown**。比較可能な範囲で言えることは以下である。

- 重複候補: MCPサーバーとしてのstdio接続、キーワード検索、レコード詳細取得、メディアURL/ダウンロード、OCR/全文検索、出典・権利情報の返却。
- heritage側の固有差分: 米国歴史資料に特化した7ソースの直接アダプタ、Rightsの保守的正規化、NARAのrecord-group/抽出テキスト、Chronicling AmericaのOCRバルクとローカル索引、Richmond Daily DispatchのTEI→SQLite FTS5、ダウンロードprovenance sidecar。
- Global Library側が国際図書館横断、機関別ページ取得、IIIF/SRU/OAI-PMH、図書館典拠、全文/OCR/画像を標準化しているなら、heritageはそのサブセットと実装例になり得る。一方、Global Libraryが同じ米国7ソースを対象にするなら、機能重複は大きく、権利語彙・認証・レート制御・再現可能な取得を比較すべきである。これは仕様未提示のため推測。
- 再利用候補: MITコードのアダプタ分離、`Record/Rights/Media`正規化、権利をunknown優先で扱う方針、キーredaction、download安全層、sourceごとのdegrade-and-continue、offline fixture/live smokeのテスト構成。[2]
- そのままの採用には注意: 米国機関固有のAPIキー/レート制限、英語・米国資料中心、未確認のIIIF/SRU/OAI-PMH対応、Alpha段階、第三者レコードの権利条件。Global Libraryの一般化層には機関別アダプタとして移植するのが妥当で、全体基盤の直接置換と断定できない。

## 未確認事項（unknown）

- Global Library MCPの既存ツール、対象機関、データモデル、標準規格、ライセンスが本調査情報からは不明。
- `heritage-research-mcp` のPyPI公開状態はCAPTCHAにより確認不能。npm公開は該当公式ページ未確認。
- 公式MCP Registry以外のコミュニティレジストリ掲載、利用者数、実運用SLA、脆弱性の有無は未確認。
- Commons/DPLA/NARA/Smithsonian/Internet Archive/RichmondのIIIF、SRU、OAI-PMH対応は、接続先自体の機能と対象OSSの利用を混同しないよう、多くをunknownとした。
- 各アダプタの全ソースコードを行単位で監査したわけではなく、セキュリティ評価はリポジトリの公開設計・SECURITY.md・設定・API仕様の確認に基づく。独立した第三者監査、SAST、依存脆弱性スキャン結果はunknown。

## 参考URL

[1]: https://github.com/magicianmarty/heritage-research-mcp "GitHub repository README and metadata"
[2]: https://raw.githubusercontent.com/magicianmarty/heritage-research-mcp/main/docs/DESIGN.md "heritage-research-mcp Design"
[3]: https://raw.githubusercontent.com/magicianmarty/heritage-research-mcp/main/SECURITY.md "heritage-research-mcp Security"
[4]: https://api.github.com/repos/magicianmarty/heritage-research-mcp/releases "GitHub releases"
[5]: https://api.github.com/repos/magicianmarty/heritage-research-mcp/commits?per_page=10 "GitHub commits"
[6]: https://archive.org/developers/ "Internet Archive Developer Portal"
[7]: https://help.archive.org/help/search-a-basic-guide/ "Internet Archive Search – A Basic Guide"
[8]: https://commons.wikimedia.org/wiki/Commons:API/MediaWiki "Wikimedia Commons API/MediaWiki"
[9]: https://pro.dp.la/developers/api-basics "DPLA API Basics"
[10]: https://pro.dp.la/developers/field-reference "DPLA Field Reference and MAP"
[11]: https://catalog.archives.gov/api/v2/api-docs/ "NARA Catalog API v2 documentation"
[12]: https://www.si.edu/openaccess/devtools "Smithsonian Open Access Developer Tools"
[13]: https://edan.si.edu/openaccess/apidocs/ "Smithsonian Institution Open Access API documentation"
[14]: https://www.loc.gov/collections/chronicling-america/about-this-collection/technical-information/ "Chronicling America Technical Information"
[15]: https://raw.githubusercontent.com/magicianmarty/heritage-research-mcp/main/pyproject.toml "heritage-research-mcp pyproject.toml"
