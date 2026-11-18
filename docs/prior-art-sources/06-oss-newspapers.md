# Phase 0 OSS調査メモ: raphink/newspapers-mcp

- 対象: https://github.com/raphink/newspapers-mcp
- 確認日: 2026-11-19
- 調査目的: Global Library MCPの新規実装前に、既存OSSの機能、対象機関、API/標準規格、ライセンス、保守状況、コード品質・セキュリティ、再利用可能性、重複と差分を事実確認する。
- 事実と推測を分離し、実装コードで確認できない機能はunknownとした。

## 1. 公式情報の要約

READMEは「複数国・地域のオンライン新聞アーカイブをMCP経由で検索するサーバ」と説明している。対応先として Europeana、Gallica、Deutsche Digitale Bibliothek（DDB）、digiPress（BSB）、ANNO（オーストリア国立図書館）、Delpher（KB Netherlands）、Chronicling America（米国議会図書館）、eLuxemburgensia、Trove（NLA）、Norwegian National Library、DigitalNZ/Papers Past、Internet Archive、British Library、South African Collectionsを挙げる。入力はquery、任意のdate_from/date_to、page、rowsである。実装上の主機能は単一MCPツール `search_newspapers` と、画像をbase64で返す `newspapers_get_snippet` である。READMEにある個別名の検索ツール群や `search_all_archives` という名称は、現行コードで確認できず、READMEと実装の差分である。

リポジトリのGitHub APIメタデータでは、公開・TypeScript・default branchはmaster・archived=false・open issues=0・forks=1・stars=8（確認時点）である。リポジトリ作成日は2026-04-20、最終pushは2026-04-21。最新コミットは2026-04-21T15:44:24Zの「Fix DDB doc links」。GitHub Releasesは空。MCP Registry検索（`newspapers-mcp`）は0件だった。

READMEはMITと記載するが、ファイル一覧にLICENSEはなく、GitHub APIのlicenseもnullである。package.jsonにもlicenseフィールドはない。したがって「作者READMEの主張としてMIT」と「再利用に必要な正式ライセンスファイルが確認できる」は分けるべきで、後者は未確認である。

## 2. MCP/API設計と標準規格

MCP SDK `@modelcontextprotocol/sdk` 1.29系を使い、stdio transportとStreamable HTTP endpoint `/mcp`を実装する。HTTP側にはExpress、CORS、NoOpOAuthProviderがある。MCPの返却は検索結果をtext、画像取得をimage/base64で返す。入力のsource enumには重複項目（norwegian、digitalnz、internet_archive）がある。

機関APIの呼び出しは以下の通り。ここで「MCP実装」はこのリポジトリが実際に呼び出すURLと返却する内容、「標準/API」はコードから確認できるプロトコル名である。上流機関が一般に提供する追加機能は、コードで利用されていない限りunknownとした。

| 対象 | MCP実装上の検索/API | 全文検索 | OCR本文 | 画像 | ページ単位取得 | IIIF | SRU | OAI-PMH | 事実・注意 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Europeana Collections | `api.europeana.eu/record/v2/search.json`, profile=rich、TYPE:TEXT、issued filter | yes（外部APIのquery） | 検索レスポンスのdescription等のみ。OCR本文取得はunknown | yes（thumbnail endpointへの導線） | unknown | unknown（thumbnail JSONで画像URL） | unknown | unknown | APIキーは環境変数。既定値`api2demo`。実装の画像switchはEuropeana caseにbreakがなく、後続eluxemburgensia caseへfall-throughするため、実際の画像取得は不具合の可能性が高い。 |
| Gallica/BnF | `gallica.bnf.fr/SRU` version 1.2 searchRetrieve、`services/ContentSearch` | yes（SRU text all） | yes、上位5 issueについてContentSearchから最大3ページの抜粋 | yes、`gallica.bnf.fr/iiif/ark:/...` | yes（ページ番号fNを使った画像） | yes（IIIF URLを生成） | yes（実装で明示） | unknown | ページ本文全体の取得ではなく抜粋。XMLを正規表現で解析。 |
| DDB | `api.deutsche-digitale-bibliothek.de/search/index/newspaper-issues/newspaper-search` JSON | query検索。全文検索かメタデータ検索かはAPI仕様上の厳密な意味をこのコードだけではunknown | no。検索結果にOCR本文を出さない | yes、binary UUID endpoint。ただしthumbnail導線 | issuepageリンクでページ表示 | unknown | unknown | unknown | READMEのOCR欄は—。ページ画像取得は実装されるが、全文OCR取得はない。 |
| digiPress/BSB | `digipress.digitale-sammlungen.de/search/simple` HTML | yes（検索フォーム/API相当のsimple query） | yes、HTMLのsnippet-highlightから抜粋 | yes、snippet画像のIIIF URLとsnippet proxy | snippetのpage/region。全ページ取得はunknown | yes、`api.digitale-sammlungen.de/iiif/image/v2/...` | unknown | unknown | HTMLを正規表現で解析。 |
| ANNO/ONB | `anno.onb.ac.at/anno-suche/rest/search/simple` JSON、snippet endpoint | yes（query） | yes、検索上位5件のsnippet APIから最大2ページ/1 snippet | yes、snippet.imageURLを返し、許可ドメインのみproxy | snippetページのみ。全ページ取得unknown | unknown（画像URLをそのまま使う。IIIFと断定不可） | unknown | unknown | 28M+ pages/1600+ titlesはコードの表示文言であり、確認時点の上流実数としては別途要検証。 |
| Delpher/KB | `jsru.kb.nl/sru/sru` version 1.2、recordSchema=ddd、x-collection=DDD_artikel | yes（SRU/CQL、記事レコード） | yes、上位5件の`resolver.kb.nl/...:ocr`からpタグを最大400字 | yes、pageurlをsnippet proxyへ | page番号を表示、画像URNを取得。全ページ取得unknown | unknown（JP2 image resolverでありIIIFとは断定不可） | yes（実装で明示） | unknown | CQLのdate within。XMLを正規表現で解析。 |
| Chronicling America/LoC | `www.loc.gov/collections/chronicling-america/` JSON（fo=json） | yes（q） | 検索descriptionのみ。OCR全文取得はunknown | yes、LoC IIIF image-services | resultの画像IDをページ画像として取得。全文ページAPIはunknown | yes（IIIF URLを生成） | unknown | unknown | 日付は年単位に丸める。 |
| eLuxemburgensia/BnL | `viewer.eluxemburgensia.lu/api/viewer2/search` JSON | yes（query） | 座標付きOCRヒットを受けるが、本文テキストは返さず座標のみ | yes、`iiif.eluxemburgensia.lu/iiif/2` | page IDを使う。ページ画像取得は実装される | yes | unknown | unknown | coordinatesからsnippet regionを計算。 |
| Trove/NLA | `api.trove.nla.gov.au/v3/result` JSON、category=newspaper、include=articletext | yes（q、APIの検索） | yes、articleTextまたはsnippetを最大400字 | no（URLは返すが画像proxyは対象外） | ページ番号を表示するが、ページ画像取得はunknown | unknown | unknown | unknown | APIキー必須。Troveのcursor paginationに対して、実装はpage>1でoffset相当を`s`に入れており、公式仕様と不整合の可能性。 |
| Norwegian National Library | `api.nb.no/catalog/v1/items` JSON、mediatype=aviser、searchType=FULL_TEXT_SEARCH | yes（APIパラメータで明示） | 検索結果本文を返さない | no | itemリンクのみ。ページ単位取得unknown | unknown | unknown | unknown | README/コードの説明上は全文検索だが、OCR本文・画像取得は未実装。 |
| DigitalNZ/Papers Past | `api.digitalnz.org/v3/records.json` JSON、category=Newspapers | query検索。全文検索の厳密な範囲はunknown | レコードのfulltextを最大400字 | no（landing/source URLのみ） | unknown | unknown | unknown | unknown | DigitalNZ APIキーを使わない実装だが、利用条件・レート制限はunknown。 |
| Internet Archive | `archive.org/advancedsearch.php` Solr JSON、collection=newspapers | yes（Solr q） | no。descriptionのみ | no（itemリンクのみ） | itemリンクのみ。ページ単位取得unknown | unknown | unknown | unknown | 実装表示の「2.9M+」はコードの固定文言。 |
| British Library | 外部APIを呼ばず、BL catalogueとBritish Newspaper Archiveの検索URLを生成 | no（MCP自身は検索しない） | no | no | no、リンクのみ | unknown | unknown | unknown | コードはPrimo VE APIに機関APIキーが必要と注記し、subscription serviceへのリンクを返すのみ。 |
| South African Collections | 外部APIを呼ばず、Sabinet/NLSA/British Newspaper Archiveのリンクを返す | no | no | no | no、リンクのみ | unknown | unknown | unknown | 「free public API is available」はコード上の説明。機関ごとのAPI仕様を確認した事実ではない。 |

### 標準規格についての整理

確実にコードから確認できる標準・仕様は、MCP（SDK、stdio/Streamable HTTP）、GallicaとDelpherのSRU 1.2、digiPress・LoC・eLuxemburgensiaで生成するIIIF画像URLである。OAI-PMHを実装するプロバイダはなく、全機関でunknown（未確認）である。SRUはGallicaとDelpher以外ではunknown。全文検索・OCR・画像・ページ単位取得は機関の能力ではなく、本リポジトリの実装範囲と混同しないこと。

## 3. コード品質・セキュリティ上の注意

- テストファイルはツリー上確認できず、package.jsonの`test`は`node --test`のみ。CI設定も確認できない。実運用の回帰テスト、API fixture、統合テストはunknown。
- HTML/XMLを正規表現で処理する箇所が多く、タグ構造・エンティティ・名前空間変更に弱い。Gallica、Delpher、digiPressの結果が壊れる可能性がある。
- `newspapers_get_snippet`のEuropeana caseはbreak欠落で、eluxemburgensiaへfall-throughする。さらにeluxemburgensia caseが重複している。Europeana画像取得の欠陥とみられるが、実行テストは未実施なので動作影響は要検証。
- `search_newspapers`のsource enumが重複し、READMEの`search_all_archives`と現行API名が不一致。`all`検索配列にはSouth Africanを含めず、British Libraryは実検索せずリンクのみ。`rows`はall検索で多くのプロバイダに最大5件へ制限される。
- Troveのコメントはcursor paginationを認識しつつ、実装はページ番号からoffsetを推測して`s`に設定する。結果重複・欠落の可能性がある。
- HTTP transportはCORSを広く許可し、NoOpOAuthProviderを使う。認証・認可の実効性は確認できない。公開配置では検索APIとAPIキーの保護を別途設計する必要がある。
- Europeana/TroveのAPIキーはURLクエリに含めて送信されるため、プロキシやアクセスログへの漏えいリスクがある。環境変数に置く設計自体はREADMEにあるが、ログ・運用保護はunknown。
- axiosのtimeoutは設定されるが、リトライ、指数バックオフ、明示的レート制限、キャッシュ、サーキットブレーカは実装されていない。all検索はPromise.allSettledで部分失敗を許容する。
- ANNOでは画像URLのhostnameを許可リスト検証している。一方、他のID/URL生成箇所は外部レスポンス値をURLへ組み立てるため、外部データの検証範囲は限定的。依存関係の脆弱性状態はこの調査では監査していない（unknown）。
- OAuth provider、Express HTTP endpoint、GCP Cloud Functions向けコードが含まれるが、認証構成・本番デプロイ設定の安全性はunknown。

## 4. ライセンス・再利用可能性

README上はMIT、TypeScriptソースとpackage-lockを含むため、技術的にはfork/部分再利用しやすい構造である。プロバイダがファイル単位で分離され、各実装は単純な検索関数である点は再利用上の利点。MCPサーバの骨格、入力スキーマ、並列検索、部分失敗処理、IIIF画像proxyはGlobal Library MCPの実装参考になる。

ただしLICENSEファイルがないため、MITの法的許諾を確定できない。採用・コードコピー前に作者へライセンス確認、または正式なLICENSE追加を要求すべきである。上流アーカイブのメタデータ、OCR、画像には機関ごとの著作権・利用規約・APIキー・レート制限が別途適用されるため、OSS本体のREADMEがMITでもコンテンツ再配布まで許諾するものではない。

## 5. Global Library MCPとの重複・差分

Global Library MCP側の既存仕様・対応機関・ツール一覧は本調査対象の入力に含まれておらず、直接照合できない部分はunknownとする。機能カテゴリとしては、歴史新聞アーカイブの横断キーワード/日付検索、機関別ソース指定、結果の外部リンク、OCR抜粋、IIIF等による画像スニペット取得が重複候補である。

差分候補は、(1) newspapers-mcpは新聞に特化し14系統の検索先を束ねる、(2)検索結果の正規化は最小限で、共通レコード型・出典 provenance・権利メタデータ・信頼度はない、(3)全文/OCR/画像/ページ取得が機関ごとに不均一、(4)British Libraryと南アフリカはリンク案内のみ、(5)OAI-PMHや汎用図書館検索、書誌横断、所蔵・権利・永続識別子を統合する層はない、である。Global Library MCPが汎用図書館メタ検索、標準規格の統一、ページ取得・OCR・画像・権利情報の整合を目的とするなら、直接置換より新聞プロバイダの候補または限定的なコード参考と見るのが妥当。ただしGlobal Library MCPの実仕様未提示のため、これは推測である。

## 6. 推奨判断

1. そのまま依存・再公開する前に、MITライセンスの正式確認、上流API利用規約、APIキー/レート制限、画像/OCRの再利用条件を確認する。
2. コードを再利用する場合は、プロバイダ単位で取り込むのではなく、共通の`SearchResult`（source、institution、identifier、date、page、ocr、image/IIIF、landing URL、rights、retrieved_at）へ正規化する。
3. SRU/IIIFを使うGallica、Delpher、digiPress、LoC、eLuxemburgensiaのパターンは参考になるが、URL生成と画像proxyはテストを追加し、Europeana fall-throughを修正する。
4. Global Library MCPでは全文検索とOCR抜粋、画像スニペット、ページ単位取得を能力フラグで表し、未対応機関を全文検索可能と表示しない。
5. XML/HTMLは正規表現でなくXML/HTMLパーサを使い、API失敗・空結果・レート制限・再試行・ページネーションを機関ごとにテストする。
6. HTTP公開時はNoOpOAuth/CORSワイルドカードを本番既定にせず、認証、許可オリジン、APIキー秘匿、監査ログ、外部URL検証を設計する。

## 7. 主要ソース（URL、タイトル、確認日）

- https://github.com/raphink/newspapers-mcp/blob/master/README.md — “README.md - raphink/newspapers-mcp”, 確認日2026-11-19。機能、対応アーカイブ、README上のMIT、使用法。
- https://api.github.com/repos/raphink/newspapers-mcp — GitHub Repository API metadata、確認日2026-11-19。日時、言語、archived、license=null、統計。
- https://api.github.com/repos/raphink/newspapers-mcp/git/trees/master?recursive=1 — Git tree API、確認日2026-11-19。ソース構成、LICENSE不在、テスト不在。
- https://api.github.com/repos/raphink/newspapers-mcp/commits?per_page=20 — GitHub Commits API、確認日2026-11-19。最新コミット日時と内容。
- https://api.github.com/repos/raphink/newspapers-mcp/releases — GitHub Releases API、確認日2026-11-19。リリースなし。
- https://registry.modelcontextprotocol.io/v0.1/servers?search=newspapers-mcp — MCP Registry API search、確認日2026-11-19。該当0件。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/index.ts — “newspapers-mcp src/index.ts”, 確認日2026-11-19。MCPツール、HTTP/stdio、画像proxy、セキュリティ上の実装。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/package.json — “newspapers-mcp package.json”, 確認日2026-11-19。依存、scripts、licenseフィールド不在。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/index.ts — “newspapers-mcp providers/index.ts”, 確認日2026-11-19。プロバイダ一覧。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/europeana.ts — “Europeana provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/gallica.ts — “Gallica provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/ddb.ts — “DDB provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/digipress.ts — “digiPress provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/anno.ts — “ANNO provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/delpher.ts — “Delpher provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/chronicling-america.ts — “Chronicling America provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/eluxemburgensia.ts — “eLuxemburgensia provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/trove.ts — “Trove provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/norwegian.ts — “Norwegian National Library provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/digitalnz.ts — “DigitalNZ provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/internet-archive.ts — “Internet Archive provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/british-library.ts — “British Library provider”, 確認日2026-11-19。
- https://raw.githubusercontent.com/raphink/newspapers-mcp/master/src/providers/south-african.ts — “South African provider”, 確認日2026-11-19。

## 結論

newspapers-mcpは、新聞に限定した14系統の検索先と、機関ごとに一部のOCR/画像/IIIFをMCPへ接続する小規模なTypeScript実装である。Global Library MCPが新聞横断検索を必要とする場合の候補実装・対応先リストとしては有用だが、ライセンス正式性、テスト不足、READMEとコードの不一致、機関別能力の不均一、HTTP認証・キー管理、ページネーション/画像proxyの不具合リスクがあり、そのまま本番依存するより、能力を明示したプロバイダ層として再設計・部分再利用するのが妥当である。
