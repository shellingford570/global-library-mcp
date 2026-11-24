# Global Library MCP Phase 0：API調査

- **確認日**：2026-11-19
- **状態**：仕様調査。実装・全面疎通完了ではない。

## 共通方針
MCPはツール面、IIIFは画像・Canvas・Annotation検索、SRUはCQL書誌検索、OAI-PMHはメタデータ収集、DC/MARCはメタデータ表現、ALTOはOCR座標・レイアウト、METSはデジタルオブジェクト構造として分離する。[1][2][3][4][5][6] 標準自身が全文・画像・ページ配信を保証するわけではなく、機関別能力を返す必要がある。

## 優先機関

### LoC（米国）
公式サイト：https://www.loc.gov/ 。JSON/YAML API、Text Services（OCR全文・単語座標・スニペット）、IIIF準拠Image Services、SRU/CQLが確認済み。[7][8][9] 言語は英語中心だが資料単位で多言語。資料種別は書籍、新聞、写真、地図等。書誌・全文/OCR・画像・ページは能力あり（コレクション横断の適用範囲はunknown）。認証は公開APIの範囲ではキー不要と確認したが、レート上限・SLAはunknown。権利はレコード・画像単位に確認し、再配布可否を推測しない。既存MCPは公式実装を確認できずunknown。実装/動作検証は公式仕様読解まで、ライブ契約テストはPhase 1。

### NDL Search／次世代デジタルライブラリー（日本）
公式サイト：https://ndlsearch.ndl.go.jp/ 、https://lab.ndl.go.jp/dl/ 。NDL SearchはSRU、OpenSearch、OpenURL、OAI-PMH、Thumbnail API、DC-NDLを提供。[10][11] 次世代デジタルライブラリーは約35万点、OCR全文検索、ページ検索、fulltext JSON、IIIF-powered viewer/APIを公式説明する。[12] NDL専用OSSにはSRU、OpenSearch、OCR全文、ページ単位取得を実装するものがあるが、IIIF画像・OAI-PMHは未実装の例がある。[13][14] 言語は日本語中心、資料は図書・古典籍・デジタル資料。認証不要・無償の説明だけでは不十分で、プロバイダ別条件、営利利用、クレジット、継続アクセス、大量アクセス制限を保持する。[15] 既存MCPは`knagata/ndl-mcp`等（非公式）。実装検証はraw調査でのJSON/XML実測、運用検証は未実施。

### Japan Search（日本）
公式サイト：https://jpsearch.go.jp/ 、API：https://jpsearch.go.jp/api 。SPARQL、EasySPARQL、簡易Web APIを提供し、個別項目からNDLデジタルコレクションのIIIF manifest／画像URLを確認できる。[16] 言語・資料種別は多様。書誌は確認済み、全文/OCR/画像/ページはレコード・提供機関単位でunknown。認証・レート・権利はAPI仕様と提供機関条件を個別確認する。既存MCPはunknown。実装/動作検証は仕様確認まで。

## 初期候補レジストリ（調査済み／未確認を含む）

|機関ID|国/地域|公式サイト|API仕様URL|言語|資料種別|書誌|全文/OCR|画像|ページ|規格|認証|利用条件・権利|レート制限|既存MCP|実装/動作検証|最終確認|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|ndl|日本|ndlsearch.ndl.go.jp|https://ndlsearch.ndl.go.jp/help/api/specifications|ja、多言語|書籍・雑誌・記事・新聞・デジタル|確認済み|次世代DLで確認|書影、IIIFは資料依存|次世代DLで確認|SRU/OpenSearch/OpenURL/OAI-PMH/DC-NDL/IIIF|一部不要、条件は要確認|プロバイダ別、営利・クレジット・大量アクセス|数値上限unknown|非公式複数|XML/JSON実測、運用unknown|2026-11-19|
|jps|日本|jpsearch.go.jp|https://jpsearch.go.jp/api|多言語|文化資源横断|確認済み|unknown|個別項目でIIIF URL|unknown|SPARQL/EasySPARQL/IIIF|unknown|提供機関別|unknown|公式MCP unknown|仕様確認|2026-11-19|
|ndli|インド|https://www.ndl.gov.in/|https://www.ndl.gov.in/faq|多言語|書籍・論文・学位論文・音声動画等|統合検索を確認|unknown|unknown|unknown|統合検索基盤|unknown|商用利用・抽出・ハーベスト制限|unknown|unknown|未実装|2026-11-19|
|cn-genealogy|中国|https://www.nlc.cn/|公式事例URL: https://www.nlc.cn/web/shouye/zhongdianxiangmu/quanguozhihuitushuguantixi/chuangxinyingyonganli/|中国語|家譜・全文画像・系譜情報|確認済み|説明上あり|説明上あり|unknown|REST/RDF/Linked Data/SPARQL|unknown|統一条件unknown|unknown|unknown|現行endpoint未疎通|2026-11-19|
|kr-nlk|韓国|https://www.nl.go.kr/NL/|https://www.nl.go.kr/NL/contents/N31101010000.do|韓国語|所蔵資料・国家書誌|XML書誌API確認|OCR/全文unknown|画像/ページunknown|unknown|XML Open API|会員・認証キー・承認|利用条件・権利は要確認|unknown|非公式例あり|仕様確認|2026-11-19|
|tw-ncl|台湾|https://www.ncl.edu.tw/en|https://www.ncl.edu.tw/en/collections|繁体字中国語・英語|書誌・論文・期刊・古籍|検索基盤確認|unknown|unknown|unknown|統一規格unknown|unknown|unknown|unknown|unknown|未疎通|2026-11-19|
|sg-nlb|シンガポール|https://www.nlb.gov.sg/main/home|https://data.gov.sg/datasets/d_077b765202cd793a3757175d91fd2086/view|英語・多言語|書籍・新聞・画像・記録等|Datastore API確認|unknown|権利単位でunknown|unknown|Datastore/OpenAPI|API公開範囲は要確認|Open Data Licenceと個別All rights reserved|unknown|unknown|データセット確認|2026-11-19|
|europeana|欧州|https://www.europeana.eu/en/for-developers|https://api.europeana.eu/|多言語|書籍・写本・美術・新聞・動画・3D|確認済み|新聞full textの案内、形式は要確認|IIIF API確認|record依存|Search/Record/IIIF/SPARQL/OAI-PMH|無料API key|提供機関・Europeana条件|unknown|公式MCP unknown|仕様確認|2026-11-19|
|ddb|ドイツ|https://www.deutsche-digitale-bibliothek.de/|https://labs.deutsche-digitale-bibliothek.de/app/ddbapi/|独・多言語|文化遺産全般|v2確認|OCR範囲unknown|IIIF manifest・バイナリ|children/parents・record依存|OpenAPI/IIIF|unknown|メタデータCC0説明、媒体は機関別|unknown|unknown|v2仕様確認|2026-11-19|
|gallica|フランス|https://gallica.bnf.fr/|https://api.bnf.fr/fr/api-document-de-gallica|仏・多言語|書籍・新聞・写本等|確認済み|ContentSearch/ALTO確認|IIIF Image/Presentation|RequestDigitalElementで確認|SRU/IIIF/ALTO|条件unknown|BnF・資料別、アクセス制限告知あり|unknown|非公式新聞MCP|ContentSearch/ALTO仕様確認|2026-11-19|
|bl|英国|https://www.bl.uk/|https://www.bl.uk/services/collection-metadata-services|英・多言語|書誌・デジタル資料|BNB/linked data確認|unknown|unknown|unknown|MARC21/Z39.50/linked data|Z39.50認証制・非商用等|サービス・資料別|unknown|unknown|仕様確認|2026-11-19|
|ape|欧州|https://www.archivesportaleurope.net/|公式外部APIはunknown|多言語|アーカイブ記述・finding aid|横断検索確認|unknown|外部機関依存|unknown|unknown|unknown|機関別|unknown|unknown|ポータル確認|2026-11-19|
|loc|米国|https://www.loc.gov/apis/|https://www.loc.gov/apis/|英・多言語|書籍・新聞・写真・地図等|JSON/SRU|Text Services OCR|IIIF Image|ページ・座標|JSON/YAML/Text/IIIF/SRU|公開範囲はキー不要|資料単位rights|unknown|公式MCP unknown|仕様確認|2026-11-19|
|hathitrust|米国/国際|https://www.hathitrust.org/|https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/bibliographic-api/|英・多言語|図書・雑誌|Bibliographic API|旧Data APIの現行性unknown|unknown|unknown|JSON/MARC-XML/OAI feed|アクセスキー等|rightsCode・Full View地域条件|unknown|非公式MCP|書誌仕様確認|2026-11-19|
|lac|カナダ|https://www.canada.ca/en/library-archives/collection/search.html|公式公開APIはunknown|英・仏・多言語|デジタル記録・出版物・ウェブ|検索UI確認|unknown|unknown|unknown|unknown|unknown|資料別|unknown|unknown|UI確認のみ|2026-11-19|
|bn-br|ブラジル|https://www.gov.br/bn/pt-br|Sophia API unknown|葡・多言語|書籍・写本・地図・写真・音声動画|Sophia検索|unknown|unknown|unknown|unknown|unknown|著作権法・資料別|unknown|unknown|UI確認のみ|2026-11-19|
|qdl|カタール/中東|https://www.qdl.qa/en/about|manifest実例あり|英・アラビア語|アーカイブ・地図・写本・音声・視覚資料|manifest metadata|manifest Searchは確認、OCR品質unknown|IIIF Image|Canvas単位|IIIF Presentation v2/Image|公開閲覧、認証unknown|アイテムUsage terms|unknown|公式MCP unknown|manifest実測|2026-11-19|
|nli-il|イスラエル|https://www.nli.org.il/en/research-and-teach/open-library|https://www.nli.org.il/en/research-and-teach/open-library/search-api|ヘブライ語・英・多言語|書籍・画像・音声動画|Search API|OCR検索unknown|IIIF Image/Presentation|manifestで複数画像|IIIF/API|API key|アイテム著作権条件|unknown|公式MCP unknown|仕様確認|2026-11-19|
|nlsa|南アフリカ|https://www.nlsa.ac.za/|CONTENTdm API URLあり|英・多言語|写真等デジタルコレクション|CONTENTdm JSON/XML|OCR・compound page unknown|IIIF一般仕様|資料依存|CONTENTdm/IIIF|unknown|レコード権利|unknown|公式MCP unknown|検索API実測|2026-11-19|
|trove|豪州|https://trove.nla.gov.au/|公式API v3技術ガイド|英・多言語|新聞・雑誌・図書・画像等|JSON/XML|新聞fulltext検索|open_fulltext等、画像権利別|記事page metadata|cursor/facet/API v3|API key|帰属、30日キャッシュ、画像別|上限は要設定|MCP専用はunknown|仕様確認|2026-11-19|
|digitalnz|ニュージーランド|https://digitalnz.org/|https://digitalnz.org/developers/api-docs-v3|英・多言語|文化資源メタデータ|Search/Get metadata|原資料OCR unknown|thumbnail/source link|unknown|JSON/XML/RSS|未認証可、keyで拡張|is_commercial_use、rights_url|通常10,000 calls/day/key|unknown|仕様確認|2026-11-19|
|internet-archive|米国/国際|https://archive.org/|https://archive.org/developers/index-apis.html|多言語|保存資料・図書・音声動画|Metadata|OCR/hOCR/fulltext確認|派生ファイル・画像|pageindex/座標|Metadata/OCR/PDF/DjVu|原則公開、識別User-Agent|投稿物・アイテム別|429/Retry-After推奨|非公式例|仕様確認|2026-11-19|
|open-library|米国/国際|https://openlibrary.org/|https://openlibrary.org/developers/api|多言語|Work/Edition書誌・表紙|Search/Work/Edition|Search inside実験的OCR|表紙・IAリンク|実験APIでpage/座標|JSON/YAML/RDF/XML|不要、識別User-Agent|データ・原資料別|1 req/s、識別時3 req/s|公式MCP unknown|仕様確認|2026-11-19|
|dpla|米国|https://pro.dp.la/developers|https://pro.dp.la/developers/api-basics|英・多言語|米国文化資源|公開API|全文/OCR unknown|原資料依存|unknown|JSON API|API key要の範囲あり|提供機関別|unknown|heritage系OSSが利用|仕様確認|2026-11-19|
|worldcat|国際|https://developer.api.oclc.org/wcv2|https://developer.api.oclc.org/wcv2|多言語|書誌・所蔵|確認済み|unknown|unknown|unknown|WorldCat Search API v2|会員認証|OCLC・資料別|unknown|unknown|仕様確認|2026-11-19|

## 標準の確認
IIIF Image API 3.0は領域・サイズ・回転・品質・形式、Presentation API 3.0は複合資料、Content Search API 2.0はOCR等のAnnotation検索を定義する。[1] SRUはCQL/XML検索、OAI-PMHは6 verbのハーベストで、全文・画像の配信標準ではない。[2][3] DC/MARC/ALTO/METS/Unicode/BCP47は正規化層に採用候補だが、個々の権利・仕様ライセンスは別確認する。

## References
[1]: https://iiif.io/api/ "IIIF APIs"
[2]: https://www.loc.gov/standards/sru/ "SRU"
[3]: https://www.openarchives.org/OAI/openarchivesprotocol.html "OAI-PMH"
[4]: https://www.dublincore.org/specifications/dublin-core/dcmi-terms/ "DCMI Metadata Terms"
[5]: https://www.loc.gov/standards/alto/ "ALTO"
[6]: https://www.loc.gov/standards/mets/ "METS"
[7]: https://www.loc.gov/apis/ "Library of Congress APIs"
[8]: https://www.loc.gov/apis/additional-apis/search-retrieval-via-url/ "LoC Search/Retrieval"
[9]: https://www.loc.gov/standards/sru/ "LoC SRU"
[10]: https://ndlsearch.ndl.go.jp/help/api/specifications "NDL API specifications"
[11]: https://ndlsearch.ndl.go.jp/help/api/oai_pmh "NDL OAI-PMH"
[12]: https://lab.ndl.go.jp/service/tsugidigi/tsugidigi_en/ "Next Digital Library"
[13]: https://github.com/knagata/ndl-mcp "knagata/ndl-mcp"
[14]: https://github.com/sho0318/ndl-mcp "sho0318/ndl-mcp"
[15]: https://ndlsearch.ndl.go.jp/help/api/provider "NDL data provider conditions"
[16]: https://jpsearch.go.jp/api "Japan Search API"

## ライブ検証結果（2026-11-22追記）

`feat/global-library-evidence-v2` 開発環境から公式APIへ実接続した結果。
詳細は `docs/evidence-verification.md` と `libraries.yaml` の各 verification 欄。

| 機関 | 結果 |
|---|---|
| NDL（次世代デジタルライブラリー Book/Page API + IIIF） | 書誌検索・書籍内検索・ページOCR・Manifest/Canvas/画像到達性すべて成功。基準ページ3件（994120_50、1018770_21、1886468_121）は全チェック verified |
| Library of Congress | 検索成功（"railway" で結果取得） |
| Internet Archive | 検索成功（"railway" で結果取得） |
| DDB | 検索成功（"Berlin" で結果取得、使用エンドポイントではキー不要だった） |
| Gallica / BnF | 上流が HTTP 403（challenge or policy restriction）を返し、このネットワークからは未検証 |
| Europeana | `EUROPEANA_API_KEY` が必要なため未実施（資格情報待ち） |
