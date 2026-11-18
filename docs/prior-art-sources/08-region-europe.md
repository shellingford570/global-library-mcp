# Phase 0調査メモ：欧州地域の公式図書館・デジタルアーカイブAPI／検索基盤

- **調査ID**: 08-region-europe
- **担当対象**: 欧州地域の公式図書館・デジタルアーカイブAPI／検索基盤（Europeana、Deutsche Digitale Bibliothek、BnF/Gallica、British Library、Archives Portal Europe）
- **確認日**: 2026-11-19
- **調査方針**: 公式サイト、公式API仕様・利用条件、公式の標準仕様ページを優先。検索結果の断片ではなく、原ページ本文を確認した。Global Library MCPの既存仕様・実装・レジストリ登録内容は本調査資料内で与えられていないため、重複判定は確認可能な範囲と推測を分離した。

## 1. 結論

欧州の単一基盤として最も再利用しやすいのは、広域横断検索・レコード取得・IIIF表示・大規模メタデータ収集を一つの公開API群にまとめる **Europeana** である。ドイツ国内の機関横断データでは **Deutsche Digitale Bibliothek（DDB）** が検索・レコード・機関・バイナリ・IIIF manifestを提供する。ただしDDB API v1は2026-12-31に終了予定で、新規実装はAPI v2を前提にすべきである。

**BnF/Gallica** は全文検索、OCR（ALTO XML）、ページ単位画像、IIIF Image／Presentationの確認可能な仕様が最も具体的で、図書・新聞・画像資料を深く扱う機関別コネクタの候補である。**British Library（BL）** は公式ページでBNB、Z39.50 MARC 21、linked data、公開メタデータの提供を確認できるが、今回確認した公式メタデータページだけでは、BL全体に対する公開全文検索・OCR・IIIF・ページ取得APIの一貫した仕様は確認できなかった。**Archives Portal Europe（APE）** は欧州のアーカイブ記述（finding aid、holdings/source guide、機関・人物・日付・デジタルオブジェクト種別）の横断検索に強いが、今回の公式トップページでは外部向けAPIの仕様を確認できず、デジタル本体画像の取得は所蔵機関側リンクに依存する。

## 2. 共通比較（確認できた事実）

### Europeana

**機能・範囲（事実）**
- Europeanaは欧州の数千の文化遺産機関から提供された、書籍・写本・美術品・写真・新聞・動画・3D等を横断する基盤と公式APIページで説明している。
- 公式APIページは、Search API、Record API、IIIF APIによる検索・レコード取得・高解像度画像のIIIF表示を明記している。
- 新聞については「数百万ページの検索可能な全文」を公式ページが説明している。ただし、全コレクション・全レコードが全文検索可能とは記載されていない。
- 大規模利用の経路としてSPARQL、OAI-PMH、データセットダウンロードを明記している。OAI-PMHは高スループットの全データ収集経路として説明されている。

**API・標準（事実）**
- API利用には無料アカウントで申請するAPIキーが必要。APIキー発行と利用規約への同意が公式開発者ページに記載されている。
- IIIF APIはIIIF manifestを用いた表示経路。OAI-PMH、SPARQLも公式APIページに明記される。
- OAI-PMH自体はHTTPで6つのverbを使うメタデータ収集プロトコルであり、画像・OCR本体を直接提供する規格ではない。
- 全文検索の具体的なエンドポイント、OCRの返却形式、ページ単位レコードの詳細、IIIF Content Search／Full Text APIの現行仕様は、今回確認したAPIトップページだけでは断定しない。

**画像・ページ・OCR判定**
- 画像: **可（IIIF API／高解像度画像表示を公式記載）**。
- ページ単位取得: **一部可と判断できるが、具体的な全レコードのページ取得仕様は今回未確認**。IIIF manifestにページ／canvasが含まれるケースは公式のIIIF説明から合理的だが、実装対象の全レコードへの適用はunknown。
- 全文検索: **新聞等で可**（数百万ページの検索可能な全文）。コレクション横断の全文検索仕様・網羅率はunknown。
- OCR: **OCRまたは全文テキストが存在する対象があることは確認できるが、現行APIでのOCR原文・座標・ALTO等の返却仕様はunknown**。

**ライセンス・保守・品質（事実／注意）**
- Terms & Policiesに利用規約、メタデータ利用ガイドライン、Public Domain Usage Guidelines等が整理されている。個々のデジタルオブジェクトの権利表示は提供元ごとに確認が必要。
- 公式開発者ページはGitHubのEuropeana組織を案内し、WebサイトのソースコードがGitHubにあると説明している。
- API利用にキーが必要で、レート・利用条件・サポート窓口がある。キーをコードへ直書きしない、権利メタデータをレコード単位で保持する、API障害・レート制限に備えてキャッシュ／バックオフする必要がある。
- 最終更新日時や各APIリポジトリのリリース頻度は、今回確認したページだけでは統一的に確認できずunknown。

**Global Library MCPとの差分（確認範囲）**
- Europeanaは既存のGlobal Library MCPが単一図書館検索を主目的とする場合、欧州機関横断の統合検索・IIIF表示・OAI-PMH/SPARQL収集が差分になり得る。
- 既存Global Library MCPの機能・コネクタ一覧が未提示のため、実際の重複（Search／Record／IIIF／全文）はunknown。

### Deutsche Digitale Bibliothek（DDB）

**機能・範囲（事実）**
- DDB APIはDDBが提供するデータへのプログラムアクセスを提供する。OpenAPIページにInstitutions API、Item API、Search API、Version API等がある。
- Item APIにはバイナリ、子・親、source、view、EDM、IIIF Presentation manifest取得の項目がある。
- Search APIはApache Solr検索インデックスへのアクセスとしてDDBpro公式ページが説明している。検索、メタデータ、デジタルオブジェクト（プレビュー、派生物、原本）へのアクセスが可能と説明される。
- DDBはドイツの文化遺産機関を横断する協働プロジェクトで、データ範囲は参加機関から提供された文化データ。参加機関数・総件数は今回の仕様ページからは記録しない。

**API・標準（事実）**
- API v2のベースアドレスは `https://api.deutsche-digitale-bibliothek.de/2`。API v2のOpenAPI仕様と対話的ドキュメントが公開されている。
- DDBpro公式ページは、従来のOAI-PMHインターフェースは終了したと明記する。OAI-PMHはDDBがデータを取り込む側のHarvesting経路としては説明されるが、DDBの現行外部APIとして提供されるとは断定できない。
- API v1は2026-12-31に停止予定。既存APIキーで停止日までは利用可能だが、新規キーは発行しない。新規開発はv2を使用する。
- API v2の主要公開機能はAPIキーなしで利用可能と公式に記載される。なお、ドキュメントが実際の挙動を完全・明確に反映しない可能性も公式に注意書きされている。

**画像・ページ・OCR判定**
- 画像／デジタルオブジェクト: **可（バイナリ、プレビュー、派生物、原本へのアクセスを公式FAQが記載）**。権利・アクセス制限は個別レコード確認が必要。
- ページ単位取得: **新聞等の項目ではページZIPダウンロードAPIがあることをOpenAPIに記載**。全資料型に対するページ取得はunknown。
- IIIF: **可（Item APIの `/items/{id}/iiif` がPresentation manifestを返す）**。
- 全文検索: **DDBのSolr検索インデックスへの検索は可**。ただしOCR全文を意味するか、全文フィールドの対象範囲・言語・精度はunknown。
- OCR: **unknown**。OpenAPIの一般ページでOCR全文／ALTO取得を断定できず、検索結果がOCR由来かメタデータ由来かは資料種別ごとに検証が必要。

**ライセンス・保守・品質（事実／注意）**
- API仕様ページは、API経由のメタデータは一般にCC0と説明する。画像・動画等のバイナリは参加機関ごとのライセンス束から選ばれ、再利用可否はメタデータの権利表示を個別確認する必要がある。
- Apache 2.0の表記もAPI仕様ページにあるが、これは仕様・関連ソフトウェア等の対象範囲を明確化せず、デジタルコンテンツ全体のライセンスと解釈してはならない。
- 最重要の保守情報はv1廃止日。v2への移行、ドキュメントと実挙動の差異、APIキー方式の違いを実装前にテストすべき。
- OpenAPIがGitHub等のコード品質・脆弱性スキャン結果を示すかは今回未確認。認証なし公開エンドポイントではレート制限、入力検証、巨大バイナリ取得、SSRF／URL追跡をMCP側で制限する。

**Global Library MCPとの差分（確認範囲）**
- DDBの機関一覧、Solr検索、EDM／source／binary／IIIF manifest、ドイツ国内の参加機関データを組み込める点が差分候補。
- Global Library MCPの既存検索・画像・IIIFコネクタ情報がないため、重複はunknown。

### BnF / Gallica

**機能・範囲（事実）**
- BnFの公式APIポータルは、Gallica（数百万の閲覧・無料ダウンロード可能なデジタル資料）、BnF総合目録、Mandragore、data.bnf.fr、CCFr、Webアーカイブ、BnF Archives et Manuscrits等を情報源として列挙する。
- GallicaのAPI文書は、文書のページネーション、画像表示、全文検索の出現箇所、OCR抽出を説明している。

**API・標準（事実）**
- ページ単位OCR取得: `RequestDigitalElement?O=id&E=ALTO&Deb=x`。OCRはXML ALTO形式。BnFのALTOは標準とわずかに異なると公式記載がある。
- 文書内全文検索・出現箇所: `https://gallica.bnf.fr/services/ContentSearch`。ark、query、任意のpage、startResultパラメータが説明され、ページID・抜粋・OCR座標（altoidstringの矩形）が返る例がある。1回の返却件数を10に制限する説明もある。
- ページ画像: thumbnail、lowres、medres、highresのページ表示URLが公式文書に記載される。
- IIIF Image APIとPresentation API: 公式ページはGallica全体の画像をIIIFで提供し、例として画像URLとmanifest URLを示す。IIIFページの技術欄はVersion 2、最終更新2025、JPEG/JPG/TIFF、ライセンスはGallicaコンテンツ利用条件と記載する。
- IIIF Image APIの一般仕様はregion、size、rotation、quality、formatのURIパラメータを定義し、Gallicaの画像切り出しに再利用可能。

**画像・ページ・OCR判定**
- 画像: **可（IIIF Image、JPEG/JPG/TIFF、複数解像度）**。
- ページ単位取得: **可（ページ番号を指定するGallica URL、Pagination、画像表示、OCR取得）**。
- 全文検索: **可（ContentSearch。ただし全文検索可能な文書に限る）**。
- OCR: **可（ALTO XML、ページ番号指定、座標情報）**。OCR対象や品質は資料・時期により異なり、全資料一律ではない。

**ライセンス・保守・品質（事実／注意）**
- IIIFページはGallicaコンテンツ利用条件へのリンクを示す。コンテンツの再利用は資料ごとの権利表示・利用条件確認が必要で、APIの存在をパブリックドメイン許諾と解釈してはならない。
- 公式APIトップは2026年時点で、Gallica APIへのアクセスに一時的制限があること、2026年6月のBnF目録システム変更がデータ・インターフェース・サービスに数か月影響しうることを告知している。これは保守・可用性リスクとして記録する。
- 公式ページはGitHubのIIIF例とPython/R wrapperを案内している。ただし、今回確認した範囲では公式組織が保守責任を負うSDKか、脆弱性対応状況はunknown。
- API利用前にアクセス制限・利用規約・User-Agent／レート条件を再確認し、MCPでは大量OCR取得をキュー化する。

**Global Library MCPとの差分（確認範囲）**
- Gallicaは文書内全文検索、OCR語座標、ALTO XML、ページ単位画像、IIIF manifestを一体で扱える機関特化コネクタ候補。
- Global Library MCPが一般的なメタデータ検索しか持たない場合、OCR本文・座標・ページ画像が実質的な差分になり得る。既存仕様が不明なため重複はunknown。

### British Library（BL）

**機能・範囲（事実）**
- BL公式のCollection metadata servicesページは、BNB（英国・アイルランドの出版活動を1950年以降記録）、Share Family beta portal上のlinked data、Z39.50 MARC 21 free data service、ISNI、ISSN、MARC organization code／ISILを案内する。
- Z39.50 MARC 21サービスは認証（パスワード）制で、図書館が非商用目的でBLカタログ／BNBのMARC 21レコードをダウンロードできる。利用条件への同意と登録が必要。
- BLはMARC 21、RDA、DDC、FAST等のメタデータ標準に関与している。
- 2023-2030 Collection Metadata Strategyでメタデータを開き、アクセス障壁を減らす方針を示す。Researcher Format CSVデータセットはBL Research Repositoryで提供される。

**API・標準（確認できた範囲）**
- Z39.50: **可（MARC 21、認証制、非商用条件）**。
- linked data／CSV: **可（BNBのlinked data、Researcher Format CSV）**。
- 公開REST APIの仕様: **今回確認した公式ページではunknown**。
- SRU／OAI-PMH: **今回のBL公式メタデータページではunknown**。
- IIIF: **BL全体を対象にした公式API仕様は今回unknown**。個別の新デジタルコレクションでIIIF manifestが表示される例は検索で見つかったが、今回の一次資料確認範囲では全体仕様として断定しない。

**画像・ページ・OCR判定**
- 画像: **unknown（BL全体の公式APIとしては未確認）**。
- ページ単位取得: **unknown**。
- 全文検索: **unknown**。デジタルコレクションの個別サイト・個別プロジェクトでは検索可能な場合があるが、BL共通APIの仕様は未確認。
- OCR: **unknown**。BLの特定デジタルコレクションにはOCRがある可能性があるが、共通APIとしての返却形式・対象範囲は未確認。

**ライセンス・保守・品質（事実／注意）**
- BL公式ページは、本文は別段の表示がない限りCC BYで利用可能とする。ただしこれはBLサイト本文・メタデータページの記述であり、個別データ・画像の権利を一律に決めるものではない。
- Z39.50はパスワード認証と非商用条件があるため、MCPの公開サービスに組み込む場合は資格情報保管、利用者単位のアクセス制御、利用規約確認が必要。
- BLのメタデータ戦略は2023-2030で、方針上の継続性は確認できる。API・個別コレクションのリリース／障害情報は別途追跡が必要。

**Global Library MCPとの差分（確認範囲）**
- 書誌メタデータに限れば、BNB、Z39.50 MARC 21、ISNI／ISSN／ISILが差分候補。画像・OCR・ページ取得は今回unknownで、差分を断定できない。
- 既存Global Library MCPがZ39.50やMARC 21を実装済みかはunknown。

### Archives Portal Europe（APE）

**機能・範囲（事実）**
- APEは欧州の多数の文化機関が保有するアーカイブに関する情報を単一アクセスポイントで検索・閲覧するポータルである。
- 公式トップページは、アーカイブ記述、作成者・人物・組織名、所蔵機関を分けて検索できると説明する。
- finding aidはコレクション／fondsの構造化記述で、item levelまであり得る。holdings guideは機関のコレクション概要、source guideはテーマ別の概要と説明される。
- タイトル、内容要約、参照コード、人物・組織、場所、日付、機関、国、デジタルオブジェクト有無・種別（text/image/sound/video/3D等）で絞り込みできる。

**API・標準（確認できた範囲）**
- 公式サイト上のポータル検索: **可**。
- 外部向けREST／GraphQL／SRU／SPARQL API: **今回の公式トップページではunknown**。
- OAI-PMH: 公式検索結果にOAI Harvester manualがあり、コンテンツ提供者向けにOAI-PMHリポジトリへの接続テスト等を説明するが、APEポータルの現行公開APIとしての仕様は今回unknown。OAI-PMHは少なくともデータ提供・収集の周辺ワークフローで使われる。
- デジタル本体は所蔵機関側にリンクされる場合があり、APEの検索記述と画像／ファイル提供を同一視してはならない。

**画像・ページ・OCR判定**
- 画像・デジタルオブジェクト: **デジタルオブジェクト有無と種別で検索可能**。実体取得の共通APIはunknown。
- ページ単位取得: **unknown**。
- 全文検索: **アーカイブ記述のタイトル／内容要約等の全文相当検索は可**。デジタル画像内OCRの全文検索はunknown。
- OCR: **unknown**。

**ライセンス・保守・品質（事実／注意）**
- APEに収録されたアーカイブ記述、デジタルオブジェクト、リンク先の利用条件は提供機関・資料ごとに異なる。今回確認ページでは横断的な単一再利用ライセンスを確認できず、unknown。
- ポータルの検索結果・外部リンクはリンク切れや所蔵機関側の変更の影響を受ける。公式トップにもデジタルオブジェクトリンクが動作しない場合のヘルプがある。
- コード品質・脆弱性情報・GitHub/GitLabの現行リポジトリは今回unknown。

**Global Library MCPとの差分（確認範囲）**
- 図書館書誌よりも、欧州アーカイブのfinding aid／fonds階層／所蔵機関・作成者・日付・デジタル有無を横断する discovery コネクタとして差別化できる。
- 既存Global Library MCPにアーカイブ階層検索があるかはunknown。

## 3. 標準規格と実装上の含意

- **IIIF Image API**: 画像全体だけでなく、region（x,y,w,h）、size、rotation、quality、formatをURIで指定できる。GallicaとDDBのIIIF manifest／画像取得で中核になる。画像URLは権利表示と切り離さず、MCPのレスポンスに出典・権利・帰属を含める。
- **IIIF Presentation**: ページ／canvas単位の順序・構造を表現する。Europeana、DDB、Gallicaで確認できるが、Europeanaは今回トップページで詳細仕様を確認していないため、対象レコードごとのmanifest有無を検証する。
- **ALTO XML**: Gallica OCRのページ単位形式。標準ALTOとの差異が公式に記載されるため、厳密なスキーマ依存を避け、BnF固有差分を吸収するパーサーが必要。
- **OAI-PMH**: メタデータの収集プロトコルであり、画像・OCR全文の直接取得規格ではない。Europeanaの大規模収集、APE周辺のデータ提供、DDBの取り込み文脈を分けて実装する。
- **SRU／Z39.50／MARC 21**: BLの書誌連携では有力。SRUはDNBで確認できるが、今回のBL公式ページでは確認できない。BLのZ39.50は認証・非商用条件を実装上の制約とする。

## 4. セキュリティ・コード品質上の注意

1. APIキー（Europeana）や認証情報（BL Z39.50、旧DDB v1）をMCPクライアントやログに露出させない。環境変数・秘密管理・最小権限を使う。
2. 外部レコードの権利URL、画像URL、manifest URLをそのままサーバー側で取得する機能を作る場合はSSRF対策、許可ホスト、リダイレクト制限、サイズ上限、タイムアウトを設ける。
3. IIIF画像・OCRの大量取得はレート制限、キャッシュ、指数バックオフ、同時実行数制限を設ける。BnFは2026年にAPIアクセス制限を告知しており、可用性が変わり得る。
4. DDB v1は2026-12-31で終了予定。v2の公開機能を使い、OpenAPIドキュメントと実際のレスポンスの差異を契約テストで検出する。
5. 権利は基盤単位で一律適用しない。Europeana・DDB・BnF・APEは個別レコード／提供機関のrightsフィールドを保持し、BLもメタデータと画像を分ける。
6. OCRは検索用途と引用用途を分ける。誤認識・言語・旧字体・レイアウトを明示し、Gallica ALTOの座標は原画像サイズに依存するため、画像変換後の座標と混同しない。

## 5. Global Library MCPへの再利用提案

- 共通内部モデルを `provider`, `institution`, `record_id`, `title`, `date`, `language`, `rights`, `landing_url`, `manifest_url`, `image_services`, `fulltext`, `ocr_format`, `page_id`, `source_updated_at` に分ける。
- コネクタ優先順位は、(1) Europeana Search/Record/IIIF、(2) Gallica ContentSearch＋ALTO＋IIIF、(3) DDB API v2＋IIIF、(4) BL書誌（Z39.50／BNB linked data）、(5) APE記述検索とリンク解決の順が妥当。ただしBLとAPEは今回のAPI不明点を解消してから実装する。
- 応答に `capabilities` を明示し、`full_text_search`, `ocr`, `page_fetch`, `image`, `iiif`, `sru`, `oai_pmh` をprovider／record単位で `true/false/unknown` とする。存在しない機能を推測で補完しない。
- Global Library MCPの既存ツール一覧・レジストリ・リポジトリが提供されれば、重複・差分を機能マトリクスで再判定できる。現時点の重複判定はunknown。

## 6. 未確認事項（unknown）

- Europeanaの現行API詳細（全文検索エンドポイント、OCR／ALTO返却、Content Search／Full Textの現行仕様、レート制限、各GitHubリポジトリの最新リリース・脆弱性情報）。
- DDBの全文検索がOCR本文をどの程度含むか、対象コレクション・言語・ランキング、v2のレート制限と正式なライセンス境界。
- BnFの2026年アクセス制限の具体的条件、全APIの認証・レート制限、Gallica OCR対象率・品質指標、各wrapperの保守状況。
- BLの共通REST／SRU／OAI-PMH／IIIF仕様、デジタルコレクション横断の全文検索・OCR・ページ単位取得、画像権利の共通ポリシー、現行GitHub／GitLabコードとセキュリティ状況。
- APEの現行外部API、データダンプ、API利用条件、OAI-PMHのポータル側提供範囲、共通ライセンス、画像・OCR・ページ取得機能。
- Global Library MCPの既存ツール、データモデル、認証、APIコネクタ、MCP Registry登録、テスト・脆弱性スキャン状況。したがって本メモの重複・差分は暫定である。

## References

1. https://api.europeana.eu/ "Europeana APIs"
2. https://www.europeana.eu/en/for-developers "Europeana For Developers"
3. https://www.europeana.eu/rights "Europeana Terms & Policies"
4. https://labs.deutsche-digitale-bibliothek.de/app/ddbapi/ "API der Deutschen Digitalen Bibliothek"
5. https://pro.deutsche-digitale-bibliothek.de/node/530 "DDB Schnittstellen"
6. https://api.bnf.fr/fr "api.bnf.fr BnF data and API portal"
7. https://api.bnf.fr/fr/api-document-de-gallica "API Document de Gallica"
8. https://api.bnf.fr/api-iiif-de-recuperation-des-images-de-gallica "API IIIF de récupération des images de Gallica"
9. https://www.bl.uk/services/collection-metadata-services "British Library Collection metadata services"
10. https://www.archivesportaleurope.net/ "Archives Portal Europe Homepage"
11. https://iiif.io/api/image/3.0/ "IIIF Image API 3.0"
12. https://www.openarchives.org/pmh/ "OAI-PMH Core Resources"
13. https://www.dnb.de/EN/Professionell/Metadatendienste/Datenbezug/LDS/lds_node.html "DNB Linked Data Service and access options"
