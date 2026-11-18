# Phase 0調査メモ：中東・アフリカの公式図書館・デジタルアーカイブAPI／検索基盤

- **対象ID**: 10-region-mideast-africa
- **確認日**: 2026-11-19
- **対象**: Qatar Digital Library（QDL）、National Library of Israel（NLI）、National Library of South Africa（NLSA）の公開デジタルコレクション／API基盤
- **調査方針**: 公式機関ページ、公式API仕様、標準仕様提供元を優先。検索結果の断片だけでは断定せず、原ページ本文または実エンドポイントを確認した。

## 1. Qatar Digital Library（QDL）

### 機能・データ範囲（確認済み）
QDLは湾岸・中東の近現代史・文化を対象とするオンラインリポジトリで、アーカイブ、地図、写本、音声、視覚資料、写真、絵葉書、歴史書等を英語・アラビア語の文脈付きで公開している。British LibraryのIndia Office Records、私文書、湾岸・アラビア半島の地図、アラビア語科学写本などを含み、公式Aboutページは「2 million超のデジタル化ページ」「新規コンテンツを定期追加」と記載する。[1]

2014年開始で、Qatar Foundation、Qatar National Library、British Libraryのパートナーシップで開発された。[1]

### API／標準規格（確認済み）
- 実記録のmanifest URLを確認でき、IIIF Presentation API 2系の`sc:Manifest`を返す。manifestには`viewingHint: paged`、多数のCanvas、各Canvasの画像ID・width・heightが含まれ、**ページ単位取得**が可能。[2]
- IIIF Image APIの画像サービスURLを確認できる。例として`https://iiif.qdl.qa/iiif/images/...jp2/full/!1200,1200/0/default.jpg`が実記録ページに埋め込まれており、画像をサイズ指定して取得できる。[2]
- manifestの`service`にIIIF Search API相当の検索サービス（`/en/annos/search/...`、profile `http://iiif.io/api/search/0/search`）が記載され、**記録内全文検索／OCRまたは転記検索**のための入口が明示されている。[2] ただし、確認できた原ページだけでは、すべての資料にOCRが存在すること、OCR精度、検索対象言語、検索APIの現行バージョンまでは断定不可。
- QDLの実記録ページにはUniversal ViewerとMirador IIIF viewerへの導線がある。[2]
- **OAI-PMH、SRU**: QDL公式ページで提供を確認できず、unknown。
- **独自REST/GraphQL API、全文横断検索API仕様**: 公開された正式仕様ページは今回の確認範囲で特定できず、unknown。Web UIの検索フォームは存在する。[1]

### ライセンス・再利用（確認済み）
QDLトップは「free to use and reuse」と明記する。[3] 一方、実記録ごとにUsage termsが表示され、確認した地図はUK National ArchivesのOpen Government Licence v2であった。[2] よって、**再利用条件はアイテム単位の権利表示を優先して判定すべき**。全収録物が一律にOGLであるとは確認できず、画像・音声等を含む全データのライセンス一覧はunknown。

### 保守・コード品質・セキュリティ注意
公式Aboutページは新規コンテンツの定期追加を記載するが、APIのリリース履歴、SLA、レート制限、認証要件、脆弱性対応方針は確認できずunknown。[1] 取得側は、manifest／Canvas URLを信頼しすぎず、許可されたホストのHTTPS、タイムアウト、サイズ上限、レート制御、Content-Type検証を実装すべき。これは実装上の推奨であり、QDLの公式仕様ではない。

### Global Library MCPとの重複・差分（評価）
重複は「デジタル資料の検索、メタデータ取得、画像・ページ閲覧、全文検索への接続」という機能層。差分は、QDLが湾岸・中東史料に特化し、IIIF manifest／Canvas／Image API／記録内Searchサービスを機械利用可能な形で公開し、アイテム単位の権利表示を持つ点。QDLは汎用の統合横断APIではないため、Global Library MCP側でQDL固有のコネクタを実装する価値がある。

## 2. National Library of Israel（NLI）

### 機能・データ範囲（確認済み）
NLI公式開発者ページは、コレクションを検索し、デジタルコピー（画像・動画・音声）をストリーミングで取得するAPIを案内する。APIは国際的なオープンデータ標準に準拠すると説明されるが、標準名の網羅的な列挙はない。[4]

### API／標準規格（確認済み）
- **Search API**: `https://api.nli.org.il/openlibrary/search?api_key={USER_KEY}&{search_string}`。個人APIキーが必須。基本クエリは検索属性上の3文字以上で、material_type、output_format、availability_type、sort_field、items_per_page、result_page等を指定可能。ゲストキーは限定アクセス。[5]
- Search APIはNLI collectionsの検索用であり、メタデータ検索は確認済み。ただし、**OCR本文を検索する全文検索**であるとの明記はなく、OCR／全文検索対応はunknown。
- **IIIF Presentation API**: `http://iiif.nli.org.il/IIIFv21/{RecordId}/manifest`またはPrimo DOCID形式。manifestはデジタルオブジェクトのタイトル、メタデータ、複数画像のsequence/canvasを返す。サンプルでは複数画像を含むpaged objectを確認できる。[6]
- **IIIF Image API**: `http://iiif.nli.org.il/IIIFv21/{identifier}/{region}/{size}/{rotation}/{quality}.{format}`。region（全体またはx,y,w,h）、size、rotation、quality（カラー／grey）、format（公式ページでは現在JPEGのみ）を指定できる。**画像取得、ページ／Canvas単位の取得、領域切り出し**は確認済み。[7]
- **動画・音声**: 開発者ページはストリーミング取得を説明するが、公開APIの具体的なエンドポイント・仕様は今回確認できず、unknown。[4]
- **OAI-PMH、SRU**: NLI公式開発者ページおよび確認したAPIページでは確認できず、unknown。
- Presentation APIはIIIF Presentation 2系のコンテキスト／`sc:Manifest`例を使用。NLIページが「IIIF APIs」と明記する。[6][7]

### ライセンス・再利用（確認済み）
NLI開発者ページは無料コンテンツ利用を促す一方、「場合によってはアイテムの利用が著作権条件に従う」と明記する。[4] よって、NLI全体に一括適用できるライセンスは確認できず、**アイテム単位の権利確認が必要**。APIキーの利用条件、商用利用、ダウンロードの大量利用条件はunknown。

### 保守・コード品質・セキュリティ注意
APIポータルはAPI Umbrella（オープンソースAPI管理基盤）で稼働し、Web Service DocumentationとAPI key signupを提供する。[8] これは運用基盤の確認であり、NLI API実装自体のソースコード品質を示すものではない。レート制限・鍵の有効期限・廃止ポリシー・SLA・脆弱性開示はunknown。鍵をサーバ側で保持し、ログ・URL・キャッシュに露出させないこと、APIキーなしでの無断試行を避けることが必要。

### Global Library MCPとの重複・差分（評価）
重複は検索、メタデータ取得、画像・ページ表示。差分は、NLIがAPIキー付きの検索APIと、RecordId／Primo DOCIDからIIIF manifestおよび画像領域を取得する明確な構造を持つ点。NLIはイスラエル／ユダヤ・イスラエル文化遺産の専門コレクションで、QDLとは地域・資料範囲が異なる。Global Library MCPでは、NLI用にAPIキー管理、ページ画像のIIIF変換、権利表示の保持を分離実装するのが適切。

## 3. National Library of South Africa（NLSA）／CONTENTdm公開コレクション

### 機能・データ範囲（確認済み）
NLSA公式サイトは、南アフリカの国民的遺産資料の保管者であり、出版物の収集・保存・公開を担うと説明する。[9] NLSAの「National Library of South Africa Digital Collections」はCONTENTdm上で公開されている。[10] 実APIのコレクション一覧には、Postcards、Afrikaans Books、Bleek Collection drawings、Mandela、各種南アフリカ新聞等、多数のコレクションが返る。Postcardsコレクションは実検索で542件を返した。[11]

### API／標準規格（確認済み）
- **CONTENTdm Website API**の実エンドポイント`/digital/api/search/collection/{alias}/...`はJSONを返し、コレクション別検索、件数、ファセット、タイトル・説明・主題などのメタデータを取得できる。[11]
- OCLC公式仕様はCONTENTdm APIを「read-only web service」とし、コレクション／レコードをJSONまたはXMLで取得できると説明する。旧dmwebservices形式の入口も文書化されている。[12]
- CONTENTdm公式ドキュメントは、画像ベースのレコードについてIIIF Image APIおよびIIIF Presentation APIをサポートすると案内し、Image API 2（Level 1）とPresentation API 2.1.1のmanifest例を示す。[13]
- 実検索結果には`filetype: pdf`等のファイル種別とitemIdが返り、API経由のレコード取得の存在を確認できる。[11]
- **全文検索**: CONTENTdm検索APIの`field/all`検索と説明・主題等のメタデータ検索は確認できるが、NLSAコレクションでOCR本文を検索できることは確認できず、unknown。
- **OCR**: unknown。新聞コレクションが存在することは確認できるが、OCR本文フィールド／OCR APIは原ページで確認できない。
- **ページ単位取得**: CONTENTdmはcompound object／IIIF Presentationの一般機能を持つが、今回確認したNLSAの具体的レコードで複数Canvasを検証しておらず、NLSAでのページ単位取得はunknown（一般仕様上は実装可能性あり）。
- **OAI-PMH、SRU**: NLSA公開コレクションの原ページで確認できず、unknown。

### ライセンス・再利用（確認済み／未確認）
NLSA公式デジタルコレクションのページは、今回の原ページ抽出範囲では包括的な利用許諾を示していない。CONTENTdm／OCLCのAPI仕様は技術仕様であり、NLSA所蔵資料の著作権許諾を意味しない。従って、ライセンス、商用利用、画像再配布、APIデータの再利用条件はunknown。アイテム表示の権利・著作権注記を都度確認すべき。

### 保守・コード品質・セキュリティ注意
OCLC公式APIリファレンスのCONTENTdm API文書は2026-09-18更新、IIIFサポート概要は2026-05-04更新と表示され、仕様文書の保守は確認できる。[12][13] ただし、NLSAテナントの更新頻度、APIレート制限、認証、SLA、脆弱性対応はunknown。read-only APIであることは確認済みで、書き込みによる破壊リスクは低いが、外部URLから取得する画像・PDFのサイズ制限、Content-Type検証、タイムアウト、PDF/OCR処理のサンドボックス化は必要。

### Global Library MCPとの重複・差分（評価）
重複はメタデータ検索、JSON/XML取得、画像ベース資料のIIIF取得。差分は、NLSAが独自APIではなくCONTENTdmのホスティング／API層に依存し、コレクションごとにaliasが異なる点。Global Library MCPにはCONTENTdm汎用アダプタを実装し、NLSAはテナントURL・collection alias・権利表示を設定として登録するのが再利用性の高い設計。NLSA固有のOCR／SRU／OAI-PMHは確認できないため、対応済みと宣言しない。

## 4. 機能マトリクス（確認日 2026-11-19）

| 機関／基盤 | 横断・属性検索 | 全文検索／OCR | 画像 | ページ単位 | IIIF | SRU | OAI-PMH | ライセンス | 認証 |
|---|---|---|---|---|---|---|---|---|---|
| QDL | Web検索を確認。正式APIはunknown | manifest内Search serviceを確認。全資料のOCRはunknown | IIIF Image API確認 | IIIF Canvas確認 | Presentation 2系、Image、Search service | unknown | unknown | トップはfree to use/reuse、アイテム単位条件 | unknown |
| NLI | Search API確認、API key必須 | OCR全文はunknown | IIIF Image API確認 | manifestのCanvas確認 | Presentation 2系、Image | unknown | unknown | アイテムごとに著作権条件の可能性 | API key |
| NLSA/CONTENTdm | CONTENTdm JSON検索確認 | OCRはunknown | CONTENTdm/IIIF一般仕様確認 | NLSA具体例はunknown | IIIF Image 2、Presentation 2.1.1の一般仕様 | unknown | unknown | NLSAデジタルコレクションの包括条件はunknown | API検索は実証、鍵要否unknown |

## 5. Global Library MCPへの推奨

1. QDLとNLIは「IIIF-first」コネクタとして、manifest→Canvas→Image URLの順で正規化する。ページ単位の取得と領域切り出しはIIIF URLを直接利用する。
2. QDLはmanifestのSearch serviceをオプション機能として扱う。OCR／転記がない資料もある前提で、`full_text_status=unknown/not_available`を返せるデータモデルにする。
3. NLIはAPI keyを必須シークレットとして扱い、検索のページネーション、レート制限、鍵失効を実装上の設定にする。NLIの無料利用表示だけから再配布権を推定しない。
4. NLSAはCONTENTdm汎用アダプタを優先する。テナント／collection aliasを外部設定化し、JSON/XMLメタデータ、IIIF manifest、権利フィールドを統一スキーマに写像する。
5. 3機関ともOAI-PMHとSRUは今回確認できなかったため、対応表では`unknown`とし、実装・ドキュメントで提供済みと断定しない。
6. 取得処理はHTTPS、許可ホスト、リクエストサイズ、タイムアウト、リトライ、レート制御、MIME検証、画像/PDF解析のサンドボックスを共通化する。これは安全な再利用のための推奨であり、各機関の公式要件ではない。

## References

[1]: https://www.qdl.qa/en/about "About Qatar Digital Library"
[2]: https://www.qdl.qa/en/archive/81055/vdc_100023518692.0x000002 "QDL archive item and IIIF details"
[3]: https://www.qdl.qa/en "Qatar Digital Library home"
[4]: https://www.nli.org.il/en/research-and-teach/open-library "The National Library of Israel for Developers"
[5]: https://www.nli.org.il/en/research-and-teach/open-library/search-api "NLI Search API"
[6]: https://www.nli.org.il/en/research-and-teach/open-library/presentation-api "NLI Presentation API (Manifest)"
[7]: https://www.nli.org.il/en/research-and-teach/open-library/image-api "NLI Image API"
[8]: https://api.nli.org.il/ "NLI API site"
[9]: https://www.nlsa.ac.za/ "National Library of South Africa home"
[10]: https://cdm21048.contentdm.oclc.org/ "National Library of South Africa Digital Collections"
[11]: https://cdm21048.contentdm.oclc.org/digital/api/search/collection/p21048coll115/searchterm/%20/field/all/maxRecords/1 "NLSA CONTENTdm API search result"
[12]: https://help.oclc.org/Metadata_Services/CONTENTdm/Advanced_website_customization/API_Reference/CONTENTdm_API "CONTENTdm API Reference"
[13]: https://help.oclc.org/Metadata_Services/CONTENTdm/Advanced_website_customization/API_Reference/IIIF_API_reference/IIIF_API_support_summary "CONTENTdm IIIF API support summary"
