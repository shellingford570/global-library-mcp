# Phase 0調査メモ: オセアニアと国際アーカイブの公式API/検索基盤

確認日: 2026-11-19
対象: Trove（National Library of Australia）、DigitalNZ（National Library of New Zealand / New Zealand Department of Internal Affairs）、Internet Archive、Open Library
目的: Global Library MCPに組み込む前の機能・範囲・API/標準・ライセンス・保守・安全性・再利用性・重複差分の事実確認。

## 結論

4基盤は同じ「図書館検索」ではなく、Troveは豪州中心の統合発見サービス、DigitalNZはニュージーランドのメタデータ集約検索、Internet Archiveは大規模デジタル保存庫とファイル/API群、Open Libraryは編集可能な書誌カタログと書籍発見APIである。したがってGlobal Library MCPの横断検索層と機能が部分的に重複する一方、原資料・全文/OCR・画像/ファイル取得は各公式APIへ委譲する設計が適切である。

## 1. Trove

### 公式に確認できた事実

- National Library of AustraliaのTrove API v3は、`category`を必須にして新聞、雑誌、画像、研究、図書、日記、音楽、人・組織、リスト等を検索できる。検索結果はXMLまたはJSONで、カーソル型の`nextStart`、最大100件/カテゴリ、ファセット、関連性/日付ソート、収穫用`bulkHarvest=true`がある。[1][2]
- APIのレコード取得では、Work、新聞/官報記事、雑誌タイトル、List、People等の種別を指定できる。新聞記事レコードには記事ID、見出し、タイトル、日付、ページ、ページ順序、ページラベル等がある。[2]
- 全文検索は公式仕様で確認できる。新聞カテゴリには`fulltext:`検索インデックスがあり、一般のデジタル/ボーンデジタル資料には`fullTextInd:y`がある。`include=all`を使うと記事等の全文が`description[@type='open_fulltext']`に入る旨が明記される。[2]
- 画像については、画像・地図・工芸品等の検索カテゴリと、サムネイル画像の有無を絞る`imageInd:thumbnail`がある。API規約上、サムネイルおよび`viewcopy`で参照できる画像・デジタルオブジェクトはメタデータ再利用許諾の対象外で、別途権利確認が必要。[3]
- API規約は、APIキー取得者による自サイト/アプリでのメタデータのコピー・利用・配布を認めるが、投稿者由来のUser ContentはCC-BY-NC-SAでの再利用に限定される。表示時にはTroveと第三者ソースの帰属、リンクが必要。通常キャッシュは最大30日。キーは秘密管理が必要。[3]
- 技術ガイド上、標準API quotaは200m API calls/minuteと記載され、増量はTrove Supportへ相談できる。[1]
- National Library of AustraliaのGitHub組織ページで複数の公開コード（ArcLight、Blacklight、pywb等）は確認できるが、同ページだけではTrove API実装本体の保守状態を断定できない。[4]

### API/標準の判定

- 全文検索: yes（新聞`fulltext`、一部資料の`fullTextInd`）。
- OCR: partially confirmed。新聞の全文検索・全文返却は確認できるが、現行API文書でOCRエンジン名、OCR品質、OCR専用エンドポイントまでは確認できない。したがって「OCRを直接取得できる」はunknown。
- 画像: yes（画像カテゴリ、thumbnail/imageInd、viewcopy等のリンク情報）。画像本体の再利用可否は個別権利依存。
- ページ単位取得: partially confirmed。新聞記事にページ番号・ページ順序・ページラベルとTrove閲覧リンクがあるが、任意のページ画像/ページ本文をAPIから安定したページ単位で取得する仕様は確認できない。
- IIIF: unknown。今回確認したTrove API公式技術ガイドでIIIF対応の明示を確認できなかった。
- SRU: unknown。今回確認したTrove API公式技術ガイドでSRU対応の明示を確認できなかった。
- OAI-PMH: unknown。今回確認したTrove API公式資料でOAI-PMH対応の明示を確認できなかった。

### Global Library MCPとの差分・再利用性

- 重複: 書誌/資料横断検索、全文キーワード検索、ファセット、レコード詳細取得。
- 差分: Trove固有の豪州新聞・官報・豪州機関の人/組織、新聞記事のページ/全文、Troveの収穫用カーソルは汎用MCPにない可能性が高い。Global Library MCPはTrove APIキー、quota、帰属、30日キャッシュ、オブジェクト権利を透過的に扱う必要がある。
- 推奨: Troveを専用コネクタとして追加し、検索対象カテゴリを明示的に選ばせる。全文はメタデータとデジタルオブジェクトを別扱いにし、権利情報・Trove/原提供機関リンクを必ず返す。

## 2. DigitalNZ

### 公式に確認できた事実

- DigitalNZ API v3は、DigitalNZ自身が資料コピーを保有するのではなく、他コレクションのメタデータとコンテンツへのポインタを持つ検索エンジン型集約サービスである。[5]
- APIはSearch recordsとGet metadataの2エンドポイント。GETでJSON/XML/RSSを返し、全文クエリ、AND/OR/withoutによるファセット条件、ページ番号、最大100件/ページ、ファセット、日付ソート、地理的bounding box等を提供する。[6]
- 結果には、カテゴリ、content_partner（所蔵機関）、説明、source_url/landing_url、thumbnail_url、large_thumbnail_url、rights_url、著作権、Dublin Core type、コレクション等が含まれ得る。画像・音声・動画・雑誌・文書などのNZ関連デジタル資料を対象とすることが開発者ページに明記される。[5][6]
- 公開コンテンツへのAPIキーは必須ではない。未認証アクセスには共有上限があり、APIキー利用者は通常1日10,000 calls/key。高負荷利用者はキー取得・増量相談が推奨される。[5][7]
- API利用規約は、条件遵守の下でメタデータのコピー、利用、配布を非商用・商用の自サイト/アプリに認める。ただし商用利用可能なものは`is_commercial_use=true`のレコードに限定され、デジタルオブジェクトやlarge thumbnailの権利はAPI規約に含まれない。表示時は第三者のオンラインソースを識別し、source_urlでリンクする必要がある。[6][7]
- 非商用APIでリアルタイム取得が原則。オフライン利用・性能上の理由などでは30日までキャッシュ可。削除または公開不能になったメタデータは速やかに除去する必要がある。[7]
- DigitalNZ GitHub組織はSupplejackのharvester、API、worker、manager、client等を公開しており、集約技術の再利用候補となる。ただし各リポジトリの最新コミット、依存関係、脆弱性状態はこの確認だけでは網羅していない。[8]

### API/標準の判定

- 全文検索: yes（APIの`text`検索。ただし検索対象がメタデータ全文か、提供機関の原資料OCR全文まで含むかはフィールド仕様上断定しない）。
- OCR: unknown。結果に説明・メタデータ・権利等はあるが、DigitalNZ APIがOCRを生成/提供すること、OCR専用フィールド、OCRファイル取得は今回の公式仕様で確認できない。
- 画像: yes（thumbnail_url、large_thumbnail_url、画像カテゴリ）。大きなサムネイルや原画像の権利は提供機関ごとに確認が必要。
- ページ単位取得: unknown。DigitalNZは原資料のコピーを持たずsource_urlへ誘導するため、ページAPIの有無は各content_partner側に依存する。
- IIIF: unknown。DigitalNZ API v3公式文書にIIIFエンドポイント/マニフェストの明示を確認できなかった。
- SRU: unknown。DigitalNZ API v3公式文書にSRU対応の明示を確認できなかった。
- OAI-PMH: unknown。DigitalNZ API v3公式文書にOAI-PMH対応の明示を確認できなかった。なお内部の収集方式や個別提供機関のOAI-PMHは別問題である。

### Global Library MCPとの差分・再利用性

- 重複: 多機関横断のNZ資料検索、ファセット、メタデータ詳細取得。
- 差分: DigitalNZ固有のcontent_partner、商用利用フラグ、source_urlクリック計測、NZ政府/教育/文化機関の集約範囲、地理bboxが強み。原資料本文やページ/画像は提供元へリダイレクトする。
- 推奨: DigitalNZは「メタデータ検索コネクタ」として実装し、原資料取得はsource_urlへのリンクに限定。各レコードのrights_url、is_commercial_use、content_partnerを返し、30日キャッシュ・10,000/day・APIキー秘密管理を設定に反映する。Supplejackコードを再利用する場合はライセンス、依存関係、脆弱性を別途監査する。

## 3. Internet Archive

### 公式に確認できた事実

- Internet Archiveはアイテムのメタデータ、CLI、Python library、S3-like API、Item Metadata API、Changes API、REST microservices、Reviews API、OCR module、PDF generation module、Wayback APIs等を公式Developer Portalで一覧化している。[9]
- Item Metadata APIはアイテム全体のメタデータ取得、Read APIはメタデータ取得、Changes APIは期間内の変更識別子取得に使える。公式一覧にはXMLメタデータ、REST API、JSON patch等がある。[9]
- OCRモジュールはTesseractを使用し、hOCRを標準出力形式として採用。1アイテムの画像集合ごとに`*_hocr.html`（ページ、単語の座標、信頼度）、`*_chocr.html.gz`、ページ開始位置を示す`*_hocr_pageindex.json.gz`、全文検索エンジン用`*_hocr_searchtext.txt.gz`を生成する。PDF、DjVu XML、DjVu textも生成される。[10]
- hOCRは全ページを含む。pageindexにより個別ページへの高速移動が可能で、ページ単位のOCR処理に利用できる。ただしこれらはアイテム派生ファイルへのアクセスであり、今回の公式ページでは単一の安定REST「page get」APIとして定義されているとは確認していない。[10]
- Internet Archiveは自動アクセスに識別可能なUser-Agent（ツール/ボット名、バージョン、AIの場合モデル名）を要求し、429/Retry-After、遅延、キャッシュ、並列数制限を推奨する。[11]
- OCR文書の最終更新は2023-02-23、文書版1.2。Tesseract移行完了は2020年末と記載される。[10]
- Open Libraryとは別プロジェクトだが、Open Libraryの公式API文書はInternet Archiveへの所属を明記し、IAの書籍スキャン可用性を返す機能を案内している。[12]

### API/標準の判定

- 全文検索: yes（公式API一覧に検索系APIがあり、OCR検索用`*_hocr_searchtext.txt.gz`が検索エンジンへ取り込まれる）。Advanced Searchの全フィールド仕様ページは今回の抽出では取得不能だったため、具体的なクエリ構文・全フィールドは要追加確認。
- OCR: yes（Tesseract/hOCR、ページ・単語座標・信頼度、検索用テキスト）。
- 画像: yes（アイテムファイル/派生ファイル、PDF等。画像配信の具体的APIはアイテム/ファイル仕様に依存）。
- ページ単位取得: partially confirmed。hOCR pageindexによるページ位置情報とページ番号/座標は確認できるが、標準RESTページ取得エンドポイントは今回確認できず、実装時はBookReader/IIIF/ファイル派生仕様を個別確認する必要がある。
- IIIF: unknown for the core Developer Portal. IIIF公式ガイドにはInternet Archive連携資料があるが、今回のInternet Archive公式API一覧で標準IIIFエンドポイントの明示を確認できなかった。採用判断にはアイテム実例とManifest確認が必要。
- SRU: unknown。公式API一覧でSRU対応の明示を確認できなかった。
- OAI-PMH: unknown。公式API一覧でOAI-PMH対応の明示を確認できなかった。

### ライセンス・安全性・再利用

- Internet Archive全体の個々のアイテム、ファイル、派生物の権利は一律ではない。今回確認した公式API一覧/ボット方針だけでは、全データに共通する再利用ライセンスを断定できない。アイテムごとのrights/licenseメタデータ確認が必要。
- 実装ではUser-Agent、キャッシュ、429処理、指数バックオフ、同一データの再取得回避を必須化する。アップロード/書込みAPIをGlobal Library MCPに公開する必要がない限り、読み取り専用に限定する。

### Global Library MCPとの差分・再利用性

- 重複: 国際的な書籍・音声・動画・画像・ウェブアーカイブ等の検索、メタデータ取得、全文/OCR検索、ファイルリンク。
- 差分: 大規模な原資料ファイル/派生ファイル、OCR座標・ページインデックス、Wayback、変更API、CLI/Pythonライブラリ、アイテム単位の多様なメディア。
- 推奨: Global Library MCPは検索・メタデータ・OCR抜粋・ページ参照を統合し、ファイル本体は明示的なURL/権利情報とともに返す。高負荷の一括取得はIA APIではなく公式bulk/ダンプや対象コレクションの許可を検討する。

## 4. Open Library

### 公式に確認できた事実

- Open Libraryは公開の書籍発見・照会APIをJSON、YAML、RDF/XMLで提供する。対象はWork/Edition、著者、主題、表紙、貸出/availability等の書誌中心のサービスで、月次データダンプも提供する。[12]
- Search API（`/search.json`）はSolrクエリ、fields、sort、言語、offset/page/limitを受け、WorkレベルとEditionレベルの情報、著者ID、表紙、IA availabilityを返せる。レスポンス例には`has_fulltext`、`ia`、`public_scan_b`等がある。[13]
- Search inside individual book APIは実験的API。OCR済み書籍内を検索し、`page_count`、マッチした本文、ページ番号、ページ幅/高さ、単語矩形座標を返す。データノードのホスト/パスをArchive metadataから解決する方式で、仕様変更リスクが明示されている。[14]
- Covers APIはISBNまたはOpen Library IDで表紙/著者写真を取得することが公式API一覧に明記されている。[12]
- 利用ガイドでは、通常1 request/sec、User-Agentと連絡先を付けた識別済みリクエストは3 request/sec。APIは高トラフィック商用バックエンドや大量ダウンロード用ではなく、bulk accessには月次dumpを使うよう求める。キャッシュ、batch search、HTMLスクレイピング禁止、分散IP禁止、違反時のrate limit/blockを記載。[12]
- Open LibraryソースコードはGitHubでAGPL-3.0。リポジトリにはtests、SECURITY.md、依存管理ファイル等があり、取得確認時のコミット数は23,893と表示された。これは活動量の目安であり、全依存の安全性を保証しない。[15]
- Open Libraryのデータライセンスページは、Internet Archiveがデータベース資料について新たな著作権/専有権を主張しないが、投稿物には既存権利問題があり得ると説明する。[16]
- APIページの最終編集表示は2026-11-08、Search APIページは2025-05-07、Search insideは2022-03-15、Licensingは2021-06-27。ページ編集日と実装のリリース/稼働保証は同一ではない。[12][13][14][16]

### API/標準の判定

- 全文検索: yes（書誌検索、Search insideによる個別書籍内のOCR全文検索）。
- OCR: partially confirmed。Search insideはOCR本文・ページ座標を返すが、Open Library自身がOCR生成するサービスか、IA側の派生OCRを参照するかは仕様上の実装詳細として扱うべき。OCRファイルそのものの一般取得APIは今回確認できずunknown。
- 画像: yes（Covers API、著者写真、IA availabilityリンク）。表紙画像の権利は個別確認が必要。
- ページ単位取得: partially confirmed。Search insideレスポンスにはページ番号/座標があるが、任意ページ画像を直接返す公式Open Library APIは今回確認できない。
- IIIF: unknown。Open Library API文書でIIIF対応の明示を確認できなかった。
- SRU: unknown。Open Library API文書でSRU対応の明示を確認できなかった。
- OAI-PMH: unknown。Open Library API文書でOAI-PMH対応の明示を確認できなかった。

### Global Library MCPとの差分・再利用性

- 重複: 書誌検索、作品/版・著者・主題の取得、表紙画像、本文内検索。
- 差分: Work/Editionモデル、巨大な書誌カタログ、IA availability連携、Search insideのページ座標、月次dump、API利用上限と人間中心の用途制限。
- 推奨: Open Libraryは書誌検索・識別子正規化・表紙・IAリンク用コネクタとして優先度が高い。全文/ページ情報を返す場合はexperimental APIであることを明示し、1〜3 req/sec、User-Agent、キャッシュ、非商用/ミッション整合の方針を守る。大量同期はdump利用を検討する。

## 5. 標準規格とMCP Registryの横断確認

- IIIFは画像/プレゼンテーション/Content Search等の標準としてGlobal Library MCPに有用だが、今回の各対象公式API文書からはTrove、DigitalNZ、Internet ArchiveのコアAPI、Open LibraryのAPIについて一律のIIIF対応を確認できなかった。実装時は機関ごとのManifest URL、Image API、Presentation APIをサンプルアイテムで個別検証する。
- SRUとOAI-PMHは今回の各サービスの公式APIページで対応を確認できず、すべてunknownと扱う。個別の参加機関が対応していても、集約サービスAPIが透過提供するとは限らない。
- MCP Registry公式サイトを確認したが、取得できたトップページ情報だけでは対象4サービスの特定公式MCPサーバー、提供者、ツール範囲、ライセンス、保守状態を検証できなかった。該当なしと断言せず、registry API/検索機能でサービス名・GitHub組織名を照合する追加確認が必要。[17]

## 6. Global Library MCPへの統合判断

1. 共通抽象は`search(query, filters, page)`, `get_record(id)`, `get_rights(id)`, `get_fulltext(id)`, `get_image_or_manifest(id)`, `get_page(id,page)`とし、各サービスで未対応機能は`unknown`または明示的なnot_supportedとして返す。
2. 検索結果に必ず`source_service`, `source_url`, `content_partner/institution`, `rights_url/license`, `retrieved_at`, `api_terms_url`を含める。Trove/DigitalNZはメタデータと原資料を分け、source_url/原提供機関リンクを保持する。
3. OCR/全文は「検索可能」と「全文テキストをAPIで返せる」を分離する。Troveは新聞全文・一部open_fulltext、IAはhOCR/全文派生、Open Libraryはexperimental Search inside、DigitalNZはメタデータ検索のみと扱う。
4. 安全性は、APIキーをログ・URLに露出しない、秘密を環境変数/secret storeで管理、SSRF防止のため返却URLの取得を自動で行わない、外部ファイルをMCP経由で保存する際はサイズ/Content-Type/圧縮爆弾を制限する、User-Agentとrate limitを遵守する、読み取り専用を標準にする、を必須とする。
5. Global Library MCPとの重複を避けるには、横断検索・正規化・権利表示・引用整形をMCP側に置き、各サービス固有の全文/OCR/page/availabilityはアダプタに委譲する。原資料の再配布や恒久キャッシュはAPI規約と機関別rightsの確認なしに実装しない。

## 未確認事項（重要）

- 4サービスについて、本調査で公式APIがIIIF、SRU、OAI-PMHを直接提供することは確認できなかった。
- TroveのOCR専用取得、DigitalNZの原資料OCR、Internet ArchiveのコアIIIF/SRU/OAI-PMH、Open Libraryの任意ページ画像取得はunknown。
- Trove、DigitalNZ、Internet Archive本体のAPI実装リポジトリの正確な最新リリース、CI/依存脆弱性、セキュリティアドバイザリの網羅確認は未実施。
- MCP Registryでの対象サービス専用MCPサーバーの存在・公式性・保守状態は未確認。Registryトップページの目視だけで不存在とは判断しない。
- 各サービスの全データの著作権はAPI利用規約だけでは一括判断できない。アイテム/提供機関ごとのrights/licenseを優先する。

## References

[1]: https://trove.nla.gov.au/about/create-something/using-api/v3/api-technical-guide "Trove API technical guide"
[2]: https://trove.nla.gov.au/about/create-something/using-api/v3/api-technical-guide "Trove API v3 search and record structures"
[3]: https://trove.nla.gov.au/about/create-something/using-api/trove-api-terms-use "Trove API Terms of Use"
[4]: https://github.com/nla "National Library of Australia GitHub organization"
[5]: https://digitalnz.org/developers/api-docs-v3 "DigitalNZ API Docs v3"
[6]: https://digitalnz.org/developers/api-docs-v3/search-records-api-v3 "DigitalNZ Search Records API v3"
[7]: https://digitalnz.org/about/terms-of-use/developer-api-terms-of-use "DigitalNZ Developer API Terms of Use"
[8]: https://github.com/digitalnz "DigitalNZ GitHub organization"
[9]: https://archive.org/developers/index-apis.html "Internet Archive Tools and APIs"
[10]: https://archive.org/developers/ocr.html "OCR at the Internet Archive with Tesseract and hOCR"
[11]: https://archive.org/developers/bots.html "Internet Archive Bots, LLMs, and Automated Access"
[12]: https://openlibrary.org/developers/api "Open Library APIs and usage guidelines"
[13]: https://openlibrary.org/dev/docs/api/search "Open Library Search API"
[14]: https://openlibrary.org/dev/docs/api/search_inside "Open Library Search inside individual book API"
[15]: https://github.com/internetarchive/openlibrary "Internet Archive Open Library GitHub repository"
[16]: https://openlibrary.org/developers/licensing "Open Library Licensing"
[17]: https://registry.modelcontextprotocol.io/ "Official MCP Registry"
