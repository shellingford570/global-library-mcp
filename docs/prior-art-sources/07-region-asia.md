# Phase 0調査メモ: アジア地域の公式図書館・デジタルアーカイブAPI／検索基盤

- **確認日:** 2026-11-19
- **担当対象:** アジア地域（日本、インド、中国、韓国、台湾、東南アジアを重点確認）
- **目的:** Global Library MCPの新規実装前の事実確認
- **調査方針:** 公式機関サイト・公式API仕様・政府オープンデータを優先。GitHub実装は公式サービスと分離して評価。検索結果の断片だけでは断定せず、原ページ本文を確認した。

## 1. 日本：国立国会図書館サーチ（NDL Search）／NDLデータ

### 公式に確認できた事実
国立国会図書館（NDL）のLODページは、NDL Searchが書籍、雑誌、記事、新聞、デジタルコンテンツ（デジタル化資料、音声、ウェブページ等）のメタデータを扱うと説明している。図書館所蔵情報、識別子、デジタルコンテンツへのURL、著作権関連情報も含む。NDL SearchのAPIとして **SRU、OpenSearch、OpenURL、OAI-PMH** が明記されている。メタデータ記述にはDC-NDLが使われる。利用目的により申請が必要な場合がある。

NDLの公開データは、NDL Search、国立国会図書館デジタルコレクション、公共・大学図書館等のデータを含む。検索対象にはNDL自身の書誌、全国書誌、雑誌記事索引、デジタルコレクション等があると公式説明から確認できる。

### 機能/API判定
- 全文検索：**一部可能性はあるが、NDL Search API全体について全文検索を明記した仕様は今回確認できず。unknown**。雑誌記事索引など記事レコード検索は確認できるが、OCR全文インデックスを意味しない。
- OCR：**unknown**。デジタル化資料があることは確認できるが、APIでOCRテキストを取得できるかは今回未確認。
- 画像：デジタルコレクションにはデジタル資料が含まれ、Japan Searchの個別項目からIIIFマニフェスト／画像URLが確認できる。ただしNDL Search APIの全レコードで画像取得を保証する仕様は**unknown**。
- ページ単位取得：IIIFマニフェストが存在する個別資料では可能性が高いが、NDL Search一般APIの機能としては**unknown**。
- 標準：SRU、OpenSearch、OpenURL、OAI-PMH、RDF/LOD、DC-NDL。IIIFは少なくとも一部デジタルコンテンツで確認。
- ライセンス：NDL Search APIは目的により許可申請が必要。データごとの利用条件に従う。オープンデータは別途「公共データ利用規約」等の確認が必要。
- 保守状況：公式サイトとAPI案内は現行運用を示す。更新頻度・SLA・レート制限の数値は**unknown**。

### Global Library MCPとの差分
NDLは日本語書誌・全国書誌・雑誌記事索引・NDLデジタル資料への一次アクセスを提供する基盤。Global Library MCPが横断検索・統一レスポンス・説明可能な出典管理を担うなら、NDLをデータソースとして接続する価値が高い。一方、NDL固有の申請、規約、レート制限、資料ごとの権利条件をMCP側で保持する必要がある。NDL自身の検索APIの代替として実装するのではなく、公式APIを尊重した薄いアダプタが妥当。

## 2. 日本：ジャパンサーチ（Japan Search）

### 公式に確認できた事実
ジャパンサーチ公式の開発者向けページは、利活用スキーマ概説、SPARQLエンドポイント解説、簡易Web API概説を提供し、SPARQLエンドポイントとEasySparqlを公開している。公式ガイドラインはIIIFを国際的な画像相互運用仕様として扱う。検索結果の個別項目にはNDLデジタルコレクションのIIIFマニフェストURLとサムネイル画像URLが表示される例を確認できる。

### 機能/API判定
- 全文検索：SPARQLや簡易Web APIによるメタデータ検索は確認できるが、加盟館のOCR全文を横断検索する仕様は**unknown**。
- OCR：**unknown**。
- 画像：IIIFマニフェストおよび画像URLが提供される項目がある。全収録機関・全項目での提供は**unknown**。
- ページ単位取得：IIIF Presentation/Image API対応マニフェストがある資料では可能。全資料への適用は**unknown**。
- 標準：RDF/Linked Data、SPARQL、IIIF。簡易Web APIも提供。
- ライセンス：データセット・提供機関ごとに異なる。個別利用条件の確認が必要。サイト全体を一律オープンと断定不可。
- 保守状況：APIページおよびガイドラインは運用中。SPARQLのSLA、更新頻度、レート制限は**unknown**。

### Global Library MCPとの差分
日本の博物館・図書館・文書館等を横断したGLAMメタデータ発見基盤であり、単一館APIより横断性が強い。Global Library MCPとは検索・メタデータ統合で重複しうるが、ジャパンサーチは日本固有のデータ供給・語彙・IIIFリンクを提供する一次ソースとして差別化できる。MCP側はSPARQL／簡易Web APIを使い、出典機関・権利・IIIF有無をそのまま返すのが安全。

## 3. インド：National Digital Library of India（NDLI）

### 公式に確認できた事実
NDLI公式サイトは、教育、研究、文化、学術資源の統合的な検索・発見基盤であり、学校教育、高等教育、研究、文化アーカイブ、新聞、司法、特許・標準等の区分を持つ。多数の機関からメタデータを集約し、実コンテンツの多くは元の機関・出版社・リポジトリにホストされる。インド工科大学カラグプルが開発・運用し、教育省のNMEICTがスポンサーである。

公式FAQは、タイトル・著者・主題・機関・出版社等による検索、多様なフィルタ、多言語検索、書籍・論文・学位論文・音声動画・講義ノート・写本・報告書等を記載している。公式規約は、データマイニング・データハーベスティング・データ抽出を禁止し、コンテンツは原権利者・提供組織の条件に従うとしている。商用利用、再配布、複製は原則として許諾が必要である。

### 機能/API判定
- 全文検索：ポータル内の検索・フィルタは確認できるが、公開APIで全文検索する仕様は**unknown**。
- OCR：写本・デジタル資料の存在は確認できるが、NDLI APIでOCRテキストを取得できるかは**unknown**。
- 画像：画像・写本等のリソースが対象に含まれるが、統一画像APIやIIIFの公開は**unknown**。
- ページ単位取得：**unknown**。
- IIIF/SRU/OAI-PMH：今回確認した公式ページではNDLI自身の公開エンドポイントとして確認できず、**unknown**。NDLIの収集元リポジトリ単位では別仕様の可能性がある。
- ライセンス：NDLIポータルの規約は商用利用・抽出・再配布を制限し、各コンテンツの権利者・提供機関の条件が優先。
- 保守状況：公式サイト、FAQ、規約、複数サービスが稼働。API仕様の公開性、更新履歴、SLAは**unknown**。

### Global Library MCPとの差分
NDLIは横断検索・学習資源発見には有用だが、コンテンツの多くを直接配信する恒久的なオープンAPIとは言えない。Global Library MCPが無断収集や再配布を行わず、検索結果の出典URLへ誘導する設計なら接続候補になり得る。ただし公式規約上、スクレイピング、データマイニング、抽出は禁止されているため、公開APIまたは明示的な提携なしに自動収集する実装は避ける。

## 4. 中国：National Library of China（NLC）および中国家谱知识服务平台の事例

### 公式に確認できた事実
中国国家図書館公式サイトの「中国家谱知识服务平台」事例は、上海図書館（上海科学技術情報研究所）のプラットフォームについて、世界630館の所蔵機関の家譜書誌データ、10万種超の家譜、上海図書館所蔵3万7千種超、うち7千種超をオンライン公開していると説明する。家譜メタデータ、全文画像、人物・地名・時代・事件、系譜図等を提供し、検索、可視化、統計、地理探索、ユーザー投稿・識譜・修譜機能を持つ。

同公式ページは、データ公開においてHTTP URIのコンテンツネゴシエーション、RESTful API、SPARQL Endpointを用いると記載し、RDF、Linked Data、既存の語彙・標準の再利用を説明する。機関横断データ、機械可読性、継続的な運用・改良、専門開発チーム、年次の運用費用も説明している。

### 機能/API判定
- 全文検索：平台が家譜原文内容を再構成し、検索・知識サービスを提供することは確認できる。ただし公開REST APIで全文検索を行う具体的なパラメータ・エンドポイントは**unknown**。
- OCR：内容抽出・機械学習・知識化は説明されるが、OCRエンジンまたはOCRテキストAPIの明示は**unknown**。
- 画像：全文影像图片（全文画像）と一部全文画像の公開を公式に確認。画像のページ単位URL・IIIF準拠は**unknown**。
- ページ単位取得：**unknown**。
- 標準：HTTP URI、RESTful API、SPARQL、RDF、Linked Data、BIBFRAMEを含む既存標準の再利用方針。IIIF、SRU、OAI-PMHは今回の公式ページでは**unknown**。
- ライセンス：書誌・規範データ・一部画像を公開するとあるが、統一ライセンス文言・商用再利用条件は**unknown**。画像は権利確認が必要。
- 保守状況：2016年開始、公式事例では7年間安定運用、専門チームと定期的な運用費・改修が記載される。ただし現在のAPI稼働状況、変更履歴、SLAは**unknown**。

### Global Library MCPとの差分
中国語圏の家譜・知識グラフ・全文画像を、単なる書誌検索以上に人物・地名・時代・系譜へ展開している点が差分。Global Library MCPの標準的な書誌検索とは重複するが、知識グラフ・可視化・家譜特化は補完的。エンドポイントの実在と利用条件を個別に確認できるまでは、実装候補ではなく「公式仕様候補／要接続試験」と扱う。

## 5. 韓国：National Library of Korea（NLK）Open API／デジタルコレクション

### 公式に確認できた事実
韓国国立中央図書館のOpen API案内は、所蔵資料と国家資料総合目録等をアプリケーションから利用できるXMLプロトコルのインターフェースと説明する。会員登録、認証キー申請、担当者承認が必要。利用方法ページには所蔵資料検索のAPIがある。公式サイトは国家資料総合目録、韓国古典籍総合目録、外部連携を含む統合検索を案内している。

デジタルコレクションページは、国立中央図書館がデジタル化した所蔵資料から、古典籍、近現代資料、新聞・雑誌、写真、映画・音源等をテーマ別に編成していることを確認できる。個別コレクションには登録日が表示されるが、APIでの画像・全文の統一取得仕様は確認できない。

### 機能/API判定
- 全文検索：公式Open APIは所蔵資料検索を提供。本文全文検索かは**unknown**。画面上の目次・抄録等の検索項目は確認できるが、APIの全文仕様は未確認。
- OCR：**unknown**。
- 画像：デジタルコレクションの存在は確認できるが、Open APIの画像取得・IIIFは**unknown**。
- ページ単位取得：**unknown**。
- 標準：XMLベースのOpen API。KDC等の分類、ISBN/ISSN/UCI/ISNI等の識別子を画面で確認。IIIF、SRU、OAI-PMHは今回**unknown**。
- ライセンス：公式サイトの著作権政策と公共누리（KOGL）へのリンクを確認したが、API返却データ・デジタル画像の一律ライセンスは**unknown**。
- 保守状況：公式サイト、API、デジタルコレクションは稼働。キー発行・承認制で、レート制限・更新履歴・SLAは**unknown**。

### Global Library MCPとの差分
韓国語書誌・全国共同目録・韓国古典籍をカバーする公式ソース。Global Library MCPが多言語横断を目指す場合、韓国語検索、認証、XMLレスポンス、著作権表示を扱う国別アダプタが必要。APIキーをMCPに内蔵せず、利用者側の資格情報と規約同意を明示する設計が必要。

## 6. 台湾：National Central Library（NCL）

### 公式に確認できた事実
台湾国立中央図書館の公式英語サイトは、Discovery System、台湾の学位論文デジタルライブラリ、台湾期刊文献、NBINet総合目録、Taiwan Memory、中国古籍善本目録、中文研究資料等を案内する。トップページには図書館カタログ、電子資源、NBINet検索があり、サイトは2026-11-13更新と表示される。Collectionsページは2026-11-07更新と表示される。

### 機能/API判定
- 全文検索：学位論文、台湾期刊、Taiwan Memory等の各サービスで検索機能は確認できるが、横断的な公開全文検索APIは**unknown**。
- OCR：**unknown**。
- 画像：台湾の稀覯書・記憶資源等のデジタル資源の存在は確認できるが、公式NCLの統一画像API・IIIFは**unknown**。
- ページ単位取得：**unknown**。
- 標準：Discoveryは商用図書館システム（Primo）URLを使用していることが確認できる。OAI-PMH、SRU、IIIF、SPARQL等の公開仕様は今回**unknown**。
- ライセンス：サイトはAll rights reserved、別途プライバシー・情報セキュリティ・Open Government Declarationを掲載。データ・画像の再利用ライセンスは**unknown**。
- 保守状況：公式サイトは2026年11月にもニュース更新があり、現行運用を確認。各データベースのAPI更新・SLAは**unknown**。

### Global Library MCPとの差分
台湾の国立書誌、学位論文、期刊、台湾記憶、古籍目録を束ねるが、サービスが複数基盤に分散している。Global Library MCPでは、NCLを一つのエンドポイントとみなさず、サービスごとに検索・リンク・権利を分離する必要がある。API未確認のままスクレイピング実装するのは避ける。

## 7. シンガポール：National Library Board（NLB）／data.gov.sg公開データ

### 公式に確認できた事実
NLB公式トップは、視聴覚、書籍、電子ジャーナル、画像、雑誌・記事、新聞、物理資料、記録・文書、ウェブサイトを横断するコレクション選択を提供する。Archives Online、National Library Online、SPH Media Newspapersへの入口がある。

シンガポール政府data.gov.sgのNLBデータセット「National Library Singapore Digital Collection by Subject - Communications 2024」は、NLBデジタルコレクションの主題別資料一覧で、30列の識別子、タイトル、著者、日付、説明、主題、言語、コレクション、資料種別、権利、アクセス権等を含む。2025-03-28更新。CSVダウンロードとdata.gov.sgのDatastore API/OpenAPIクエリが提供され、Open Data Licenceの下で個人・商用利用可と表示される。ただし個別アイテムのrights/access rightsが優先する。

### 機能/API判定
- 全文検索：data.gov.sg APIは公開メタデータの検索・取得向け。NLBデジタル本文の全文検索APIは**unknown**。
- OCR：**unknown**。
- 画像：NLBコレクションに画像資料があるが、統一IIIF画像APIは**unknown**。
- ページ単位取得：**unknown**。
- 標準：data.gov.sgのデータセットAPI/OpenAPI。IIIF、SRU、OAI-PMHは今回NLBについて**unknown**。
- ライセンス：データセット自体はOpen Data Licence。ただしレコード中にAll rights reserved等のrights/access rightsがあるため、メタデータ公開ライセンスと資料本体の利用権を分ける必要がある。
- 保守状況：データセットは2025-03-28更新、NLBサイトは稼働。全コレクションの更新頻度・SLAは**unknown**。

### Global Library MCPとの差分
公開メタデータは低摩擦で統合候補。ただしNLBの実資料本文・画像・新聞は権利・アクセス条件が強く異なる。MCPではdata.gov.sgのメタデータ検索と、NLB/NASの原ページリンクを提供し、本文の取得・再配布を既定で行わない構成が安全。

## 8. 東南アジアその他：インドネシア、マレーシア

今回、公式検索でインドネシア国立図書館（Perpusnas）についてOAI-PMHを使う統合システム（IOS）への言及を含む公式PDFを確認したが、現行の公開エンドポイント仕様、認証、データ範囲、レート制限を原APIページで確認できなかった。マレーシア国立図書館については公式ポータルやオンラインデータベース入口は確認できたが、公開API／IIIF／SRU／OAI-PMHの仕様を確認できなかった。したがって両国のAPI可否は**unknown**とする。

## 9. 再利用可能な実装・MCPエコシステムの確認

### NDL MCP（非公式）
GitHubの`ckgerteis/ndl-mcp`は、NDL SearchのSRUを検索するMITライセンスのFastMCPサーバー。書誌、全国書誌、雑誌記事索引、オンライン資料編、オープンデータデジタルコレクション等の検索とレコード取得を提供する。READMEには、逐次リクエスト、最低1秒間隔、検索上限100件、OAI-PMH非実装、レスポンスへの出典表示、キャッシュ・ローカル蓄積なし等、NDLの利用条件を意識した実装が記載される。レート制限、予約語、ローマ字検索不足を診断する設計もある。82コミット、テスト、SECURITY.md、依存固定用ファイルが確認でき、コード品質・安全配慮は比較的高い。ただしGitHub実装はNDL公式MCPではなく、Global Library MCPへそのまま取り込まず、設計上の参考・コード監査対象とする。

### 韓国情報ナ루MCP（非公式）
GitHubの`isnow890/data4library-mcp`は、韓国の図書館情報ナ루APIを使う独立Node.js MCPサーバー。図書館、書籍、所蔵、貸出可否、人気、統計、推薦、地域・分類コード等27ツールを提供する。MITライセンス、35コミット、TypeScript/Node.js構成。README自身が「公式MCPではない」と明記し、API遅延・タイムアウト、APIキー、IP登録、前日基準の貸出可否、距離計算の限界を注意している。自動回帰テスト未構成。秘密情報は環境変数で渡す設計だが、依存更新・外部API入力検証・タイムアウト等は導入時に監査が必要。

### MCP Registry
MCP Registryの存在自体は公式ブログで確認したが、今回の検索ではアジア国立図書館公式が公開した登録済みMCPは確認できなかった。NDL・韓国の上記サーバーは第三者実装であり、公式機関の運営・保証とは切り分ける。台湾、中国、インド、シンガポール、インドネシア、マレーシアの公式図書館MCPは**unknown**。

## 10. 標準仕様の実装上の意味

IIIF公式仕様ページは、Image API 3.0が領域、サイズ、回転、品質、形式をURIで指定して画像を返し、Presentation API 3.0が複合デジタルオブジェクトのオンライン表示情報を提供すると説明する。Content Search API 2.0はIIIFオブジェクト内のテキスト注釈検索の相互運用を定義する。これらは画像・ページ・OCR検索の実装候補だが、各国機関が実際に公開していることは機関ごとに別途確認が必要。

## 11. Global Library MCPへの総合評価

1. **最優先接続候補:** 日本のNDL Search（SRU/OpenSearch/OAI-PMH等が明示）とJapan Search（SPARQL/EasySparql/IIIFリンク）。公開仕様が比較的明確で、Global Library MCPの横断検索と相性がよい。
2. **条件付き候補:** 韓国NLK（XML Open API、認証キー・承認制）、シンガポールdata.gov.sgのNLBメタデータ（Open Data Licence、Datastore API）。資格情報・権利フィールド・原ページ誘導を実装条件とする。
3. **検索専用・慎重接続:** NDLI。公式規約が抽出・ハーベスティング・データマイニングを禁じるため、公開API・正式提携が確認できるまで自動収集はしない。
4. **要個別接続試験:** 中国家谱平台、台湾NCL。公式説明にREST/SPARQLや複数データベースの存在はあるが、現行エンドポイント、認証、利用規約、レート制限を別途疎通確認すべき。
5. **現時点で未実装:** インドネシア、マレーシアの公式APIは今回の範囲では確定できず、unknownとして保留。
6. **共通差分:** Global Library MCP側は、各機関の認証・規約・権利・更新日時・標準差を正規化し、検索結果の出典URL、原機関、取得日時、全文／画像／IIIFの可否を明示する必要がある。本文・画像のキャッシュや再配布はデフォルト無効とする。

## 12. 重要な未確認事項

- 各国機関のMCP Registry公式登録、公式GitHub/GitLabリポジトリ、公式SDKの有無。
- NDL/Japan Search以外で、OCR全文検索、IIIF Image/Presentation、ページ単位取得をAPIとして保証する現行仕様。
- すべての機関の詳細なレート制限、SLA、認証方式、APIバージョン、廃止予定。
- 画像・全文・OCR・メタデータを分けたライセンス一覧。特に中国・台湾・韓国・NDLIは一律ライセンスと断定不可。
- 各APIの実運用時のTLS、入力検証、依存脆弱性、監査ログ等のセキュリティ実装。第三者MCPは導入前に依存固定・秘密管理・SSRF／プロンプトインジェクション耐性・出力サイズ制限を監査すること。

## References

[1]: https://www.ndl.go.jp/en/dlib/standards/lod "National Diet Library LOD and API standards"
[2]: https://jpsearch.go.jp/api "Japan Search developer information"
[3]: https://jpsearch.go.jp/guideline/standard "Japan Search standards and guidelines"
[4]: https://www.ndl.gov.in/ "National Digital Library of India"
[5]: https://www.ndl.gov.in/terms "NDLI Terms and Conditions"
[6]: https://www.ndl.gov.in/faq "NDLI FAQ"
[7]: https://www.nlc.cn/web/shouye/zhongdianxiangmu/quanguozhihuitushuguantixi/chuangxinyingyonganli/20240924_2641331.shtml "National Library of China: Chinese Genealogy Knowledge Service Platform case"
[8]: https://www.nl.go.kr/NL/contents/N31101010000.do "National Library of Korea Open API guide"
[9]: https://www.nl.go.kr/NL/contents/N20103000000.do "National Library of Korea digital collections"
[10]: https://www.ncl.edu.tw/en "National Central Library Taiwan home"
[11]: https://www.ncl.edu.tw/en/collections "National Central Library Taiwan collections"
[12]: https://www.nlb.gov.sg/main/home "National Library Board Singapore collections"
[13]: https://data.gov.sg/datasets/d_077b765202cd793a3757175d91fd2086/view "NLB Singapore digital collection dataset"
[14]: https://iiif.io/technical-details/ "IIIF technical details"
[15]: https://github.com/ckgerteis/ndl-mcp "Unofficial NDL Search MCP server"
[16]: https://github.com/isnow890/data4library-mcp "Unofficial Korean Data4Library MCP server"
[17]: https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/ "MCP Registry preview announcement"
