# Phase 0調査メモ: 北米・中南米の公式図書館・デジタルアーカイブAPI/検索基盤

- **対象ID:** 09-region-americas
- **確認日:** 2026-11-19
- **対象:** Library of Congress (LoC)、HathiTrust、Library and Archives Canada (LAC)、ブラジル Fundação Biblioteca Nacional / BNDigital・Hemeroteca
- **調査方針:** 公式サイト・公式API仕様を優先し、検索スニペットだけで断定しない。MCP実装は公開GitHubで補足確認。事実と推測を分離し、確認できない点は `unknown` とした。

## 1. Library of Congress (米国)

### 公式ページ
- [APIs at the Library of Congress](https://www.loc.gov/apis/)（ページタイトル: APIs at the Library of Congress、確認日: 2026-11-19）
- [Search/Retrieval via URL](https://www.loc.gov/apis/additional-apis/search-retrieval-via-url/)（ページタイトル: Search/Retrieval via URL、確認日: 2026-11-19）

### 確認できた事実
LoCは公開APIを、(a) loc.gov JSON/YAML API、(b) sitemap、(c) Microservicesに整理している。JSON APIはコレクションの構造化データ、検索結果のページング、フィルタ、ファセット、並び替え等に使える。対象はBooks/Printed Material、Films/Videos、Maps、Manuscripts/Mixed Material、Photos/Prints/Drawings、Newspapers、Web Archives等、loc.gov上の広いコレクションである。[1]

Text ServicesはLoC上のOCR全文、単語座標、コンテキスト・スニペットへのAPIアクセスを提供する。Image ServicesはIIIF準拠APIで、画像へのアクセスと操作を提供する。したがって、全文/OCR=confirmed、画像=confirmed、IIIF=confirmedである。[1]

SRUサーバーはカタログおよび一部authority fileを対象に、CQLを用いた標準XML検索を提供する。LoCはSRUサービス一覧とZ39.50 gatewayを案内している。SRU=confirmed、Z39.50=confirmed。[2]

### ページ単位取得・標準・権利
ページ単位の画像取得について、LoCのIIIF Image Servicesが画像操作・配信を提供することは確認できるが、今回確認したページだけでは全コレクションでのページ単位エンドポイントの適用範囲までは断定できない（`unknown`）。OAI-PMH対応は今回の公式API一覧・SRUページでは確認できず `unknown`。API利用規約・個別デジタルオブジェクトの著作権は資料ごとに異なるため、包括的な再利用ライセンスは `unknown`。コード品質は公式サービスの公開仕様だけからは評価不能。

### 保守・再利用性
現行の公式API文書が公開され、複数のAPIカテゴリが整理されているため、現行利用可能性は高いと推測できる。ただし、今回取得したページには明確な最終更新日やSLAがないため、保守期限・変更通知の詳細は `unknown`。Global Library MCPでは、LoC JSON/SRU/IIIF/Text Servicesをそれぞれツール化できるが、単純な検索ラッパーだけでは全文OCR、座標、IIIF画像、SRU/CQLというLoC固有機能を取りこぼす。重複は「メタデータ検索・レコード取得」、差分は「OCR/座標、画像配信、SRU、authority/Z39.50」である。

## 2. HathiTrust Digital Library

### 公式ページ
- [Bibliographic API](https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/bibliographic-api/)（ページタイトル: Bibliographic API、確認日: 2026-11-19）
- [How to Use HathiTrust Data Resources](https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/)（ページタイトル: How to Use HathiTrust Data Resources、確認日: 2026-11-19）
- [HathiTrust Data API](https://old.www.hathitrust.org/data_api.html)（ページタイトル: HathiTrust Data API、アーカイブサイト。確認日: 2026-11-19）

### 確認できた事実
Bibliographic APIはISBN、LCCN、OCLC、ISSN、HathiTrust volume ID、record number等の識別子で、brief/full JSONを返す。fullではMARC-XMLを含む。1回のマルチIDリクエストで最大20件のrecordを要求でき、volumeごとにoriginating institution、HTID、rights code、lastUpdate、米国でのrights表示（Full View / Limited search-only）を返す。[3]

HathiTrustの資料は60以上の図書館（米国および世界各地）から提供され、コレクションは日々追加され、デジタル項目・書誌・権利状態が更新されうる。HathiTrustはメタデータをOAI feed/HathiFiles等で提供し、メタデータ共有方針上、契約上の制限がない範囲で独立ユーザー・機関・第三者による収集、改変、利用を認める。HathiTrust自身の寄与メタデータはCC0 Public Domain Dedicationに置かれている。[4]

旧公式Data APIページは、ページ画像、OCR、場合によってはwhole-volume packageとメタデータを取得できると説明する。プログラム利用にはaccess key、Web clientには認証が必要で、Version 2が最新と記載されている。ただし同ページは「2023年7月に新サイトへ移行した旧サイトのアーカイブ」であり、仕様書の記載は改めて現行性を確認すべきである。[5]

### API機能・標準・制約
全文検索=HathiTrustウェブ検索/インデックスとしてはconfirmedだが、Bibliographic API自体の全文検索APIではない。OCR=Data APIに関してconfirmed（現行性は要注意）。画像=Data APIに関してconfirmed（現行性は要注意）。ページ単位取得=Data APIの説明から取得可能と読めるが、現行エンドポイントの適用範囲は `unknown`。IIIF=今回確認した公式APIページでは `unknown`。SRU= `unknown`。OAI-PMH=HathiTrust OAI feedとして公式に存在するが、今回取得した現行ページではプロトコル詳細を確認していないため、メタデータフィード=confirmed、厳密なOAI-PMH仕様・全エンドポイント= `unknown`。

アクセスは権利コードに依存し、Full Viewとsearch-onlyが混在する。API・コンテンツ利用の包括ライセンスは資料・メタデータ種別ごとに分かれるため、取得した画像/OCRの再配布権は `unknown`。書誌メタデータはCC0方針が明確で再利用性が高い。[4]

### MCP/コード品質・セキュリティ
公開GitHubの非公式MCP実装 [pipeworx-io/mcp-hathitrust](https://github.com/pipeworx-io/mcp-hathitrust) はMIT、2026-06-10作成、12 commits、Node/npm構成で、Bibliographic APIの識別子検索・レコード取得・Full View判定を提供する。ただし上流HathiTrust非所属・非公認である。READMEには、匿名アクセス制限、Pipeworxアカウント/Bearer token、ゲートウェイ経由、ネットワーク依存、過去の大量列挙（住宅プロキシ約17.1万IP、約60万calls/hour）と上流エグレス遮断リスクへの対策が明記される。よって、Global Library MCPへコードを直接取り込むより、上流APIのレート制限、識別子入力の列挙耐性、認証情報の秘密管理、利用規約順守を設計要件にすべきである。[6]

### Global Library MCPとの重複・差分
重複は識別子ベースの書誌検索、レコード取得、権利状態表示。差分候補はHathiTrust固有のvolume単位・originating institution・rights code、OAI feed/HathiFiles、権利により分岐するOCR/画像取得である。公開MCP実装はBibliographic API中心で、Data APIのOCR/画像を提供することはREADMEから確認できない（`unknown`）。

## 3. Library and Archives Canada (LAC、カナダ)

### 公式ページ
- [Search the collections](https://www.canada.ca/en/library-archives/collection/search.html)（ページタイトル: Search the collections、ページ詳細: 2026-09-22、確認日: 2026-11-19）
- [Collection search](https://recherche-collection-search.bac-lac.gc.ca/)（ページタイトル: Collection search、確認日: 2026-11-19）
- [Search the collection](https://library-archives.canada.ca/eng/collection/search-collections/pages/search-the-collection.aspx)（ページタイトル: Library and Archives Canada、ページ詳細: 2026-11-18、確認日: 2026-11-19）

### 確認できた事実
政府公式案内は、LACのCollection searchでlibrary/archive digital records、published material、他機関の資料、web archiveを検索できると説明する。Collection searchは政治・軍事・系譜等のrecords、publications、documentsを対象とし、別にCensus search、Published material search（Aurora）、Voilà、Theses Canada、Government of Canada Web Archiveがある。[7]

Collection searchページには「most of the collections held by LAC」を横断検索するとあり、mass-digitized archivesへのリンクもある。2026-09-22の新しいCollection data export tool、2026-10-29のtechnical issues更新、2026-11-18のページ更新が確認でき、保守活動は継続中と判断できる。[8]

### API機能・標準・権利
公式に確認できる公開Web検索の範囲は広いが、今回確認した公式ページでは公開JSON/XML API仕様、SRU、OAI-PMH、IIIF、API認証仕様は見つからなかった（すべて `unknown`）。検索フォームの機能は確認できるが、全文検索かメタデータ検索か、OCRの有無はコレクション/画面ごとに異なる可能性があり、包括的には `unknown`。画像表示はデジタルレコードの存在から推測できるが、画像API・ページ単位取得は `unknown`。ライセンス・再利用条件も個別資料・画像クレジット・政府利用条件の確認が必要で、包括ライセンスは `unknown`。

### コード品質・再利用性・Global Library MCP差分
公式UIの利用は可能だが、実装可能なAPI契約が今回確認できないため、Global Library MCPの直接コネクタ化は要追加調査。現時点の重複は「LACコレクションを検索・レコードへリンクする機能」に限定して設計すべきで、スクレイピング前提の実装は非推奨。技術的には、公式export toolの仕様、robots/利用規約、データダンプ、個別デジタルビューアのネットワークAPIを追加確認する必要がある。

## 4. Fundação Biblioteca Nacional / BNDigital・Hemeroteca (ブラジル)

### 公式ページ
- [Fundação Biblioteca Nacional](https://www.gov.br/bn/pt-br)（ページタイトル: Página Inicial — Fundação Biblioteca Nacional、確認日: 2026-11-19）
- [BNDigital / Sophia](https://acervobndigital.bn.gov.br/sophia/)（ページタイトル: Sophia Biblioteca - Terminal Web、確認日: 2026-11-19）
- [Hemeroteca Digital Brasileira](https://memoria.bn.gov.br/hdb/periodico.aspx)（ページタイトル: HEMEROTECA DIGITAL BRASILEIRA、確認日: 2026-11-19）
- [Direitos Autorais](https://www.gov.br/bn/pt-br/atuacao/direitos-autorais-1)（ページタイトル: Direitos Autorais、確認日: 2026-11-19）

### 確認できた事実
BN公式トップはBNDigital、Hemeroteca Digital、Brasilianaへの入口を提供し、あわせてRede da Memória、BDLB等の検索先を掲示する。BNDigitalのSophia画面は、タイトル、著者、主題、全フィールド、年、コレクション、資料種別、言語、電子コンテンツ有無等で検索でき、書籍、写本、地図、写真、楽譜、定期刊行物、音声、動画等の多様な資料タイプを列挙している。[9]

Hemerotecaの公式ページは今回の静的取得ではロゴ/入口以外の検索仕様を返さず、全文検索、OCR、画像、ページ単位取得の実装詳細は確認不能である（各項目 `unknown`）。BNDigital Sophia画面に「Registros com conteúdo digital」（デジタルコンテンツを含む記録）の検索条件はあるが、OCR・IIIF・APIの有無や公開エンドポイントは確認できない。[10]

BNの著作権ページは、登録業務がブラジル法 Lei nº 9.610/98に基づくことを案内するが、デジタルコレクション全体の一括再利用ライセンスを示すページではない。資料ごとの著作権・パブリックドメイン・画像利用条件は `unknown`。[11]

### API機能・標準・保守
公開公式ページから、BNDigital/HemerotecaのJSON API、SRU、OAI-PMH、IIIF、ページ画像API、OCR APIのいずれも断定できない（すべて `unknown`）。公式トップは2026年のニュース（BNDigital 20周年関連告知等）を掲載しており、機関サイト自体の更新は確認できるが、APIの保守状況は `unknown`。Sophiaは第三者製品（画面にSoluciones Sophiaと表示）だが、製品の公開API契約・ライセンス・脆弱性情報は未確認。

### Global Library MCPとの差分
重複候補は書誌検索、資料種別/言語/コレクション絞り込み、デジタル記録へのリンク。差分候補はブラジル・ポルトガル語圏の新聞、写本、写真、地図、音声、動画等の地域資料である。API契約が確認できるまでは、公式Web画面をAPIとみなして実装しない。HemerotecaのOCR/ページ取得は利用者価値が高い可能性があるが、現時点では `unknown` とする。

## 横断評価と実装勧告

1. **優先度:** LoCは公開JSON、Text Services、IIIF、SRUが明示されており、Global Library MCPの公式コネクタ候補として最も実装しやすい。HathiTrustは書誌APIとメタデータ共有が明確で、権利コードを必須の返却値とする。LACとブラジルBNは、公開仕様を追加発見できるまでUIリンク/検索導線として扱う。
2. **標準規格:** IIIF/SRU/OAI-PMHを一律に全機関へ仮定しない。LoCはIIIF/SRU confirmed、HathiTrustはOAI feed confirmedだが厳密な現行OAI-PMH仕様・IIIF/SRUはunknown、LAC/BNはunknown。
3. **OCRと画像:** LoCのOCR/座標/スニペットとIIIF画像はconfirmed。HathiTrustのData APIは旧公式資料上、OCR/画像/page contentを説明するが、現行性を要検証。LAC/BNはunknown。
4. **権利:** HathiTrustのメタデータはCC0方針が強い一方、本文・画像・OCRはrights code/著作権により制限される。LoC、LAC、BNも資料単位の権利を保持し、MCPはURL・rights表示・利用規約を返すだけに留め、本文再配布を既定にしない。
5. **セキュリティ:** 上流APIキー、MCP gatewayのBearer token、ログへの識別子/検索語、レート制限、列挙攻撃、SSRF、巨大画像/OCRレスポンス、XML外部エンティティ（SRU/OAI-PMH）の対策が必要。HathiTrustの公開MCP事例は大量列挙と上流遮断リスクを具体的に示す。
6. **再利用:** 既存のpipeworx MCPはHathiTrust Bibliographic APIの参照実装候補だが、非公式・ゲートウェイ依存であり、ライセンス（MIT）と上流利用条件を分けて評価する。LoC/LAC/BNの公式コード品質は、今回のWeb仕様からは評価不能。

## 未確認事項一覧（unknown）

- LoC: 全コレクションでのIIIFページ単位適用範囲、OAI-PMH、包括的APIライセンス、SLA/明示最終更新日。
- HathiTrust: 現行Data APIの稼働エンドポイントとpage/OCR/imageレスポンス、IIIF、SRU、厳密な現行OAI-PMH仕様、本文/画像/OCRの再配布権。
- LAC: 公開API・exportの機械可読仕様、全文/OCR、IIIF、SRU、OAI-PMH、画像/ページAPI、包括ライセンス。
- ブラジルBN: BNDigital/Hemerotecaの公開API、全文/OCR、IIIF、SRU、OAI-PMH、画像/ページAPI、個別資料の再利用条件、Sophia製品のAPI/脆弱性/保守契約。
- MCP Registry、PyPI、npmでの公式機関運営の実装は今回確認できず、非公式実装以外は `unknown`。

## References

[1]: https://www.loc.gov/apis/ "APIs at the Library of Congress"
[2]: https://www.loc.gov/apis/additional-apis/search-retrieval-via-url/ "Search/Retrieval via URL"
[3]: https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/bibliographic-api/ "HathiTrust Bibliographic API"
[4]: https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/ "How to Use HathiTrust Data Resources"
[5]: https://old.www.hathitrust.org/data_api.html "HathiTrust Data API"
[6]: https://github.com/pipeworx-io/mcp-hathitrust "pipeworx-io/mcp-hathitrust"
[7]: https://www.canada.ca/en/library-archives/collection/search.html "Search the collections"
[8]: https://recherche-collection-search.bac-lac.gc.ca/ "Collection search"
[9]: https://www.gov.br/bn/pt-br "Fundação Biblioteca Nacional"
[10]: https://acervobndigital.bn.gov.br/sophia/ "Sophia Biblioteca - Terminal Web"
[11]: https://www.gov.br/bn/pt-br/atuacao/direitos-autorais-1 "Direitos Autorais"
