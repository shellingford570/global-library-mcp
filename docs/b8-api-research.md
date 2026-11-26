# b8 公式API・利用条件調査（Stage 1）

調査日：2026-11-26。方法：各機関の公式ドキュメント・公式サイトの確認と、
許可された通常ネットワークからの少数の実地プローブ。アクセス制限の回避
（プロキシ・VPN・User-Agent偽装・非公式ミラー）は一切行っていない。
到達できなかった機関については、その事実をそのまま記録する。

凡例（実装状態）：**実装**＝b8でアダプター実装、**認証待ち実装**＝フィクスチャ
先行でキー未設定時は `authentication_required`、**調査のみ**＝b8では実装しない。

## 概要表

| 機関 | 公式API | 認証 | 費用 | メタデータ権利 | 原文/画像権利 | ページOCR | b8状態 |
|---|---|---|---|---|---|---|---|
| Finna（フィンランド） | REST API v1（search/record） | 不要 | 無料 | CC0 1.0 | レコード毎（usageRights） | Finna自体はなし（提供元IIIF経由の可能性） | 実装（Stage 2） |
| フィンランド国立図書館 Digi | digi.kansalliskirjasto.fi（IIIF導入済） | 公開範囲は不要／権利存続資料はHaka制限 | 無料 | 機関方針 | 1911年以前の新聞は権利消滅扱い（機関案内） | 具体エンドポイント未確認 | Stage 3で確認できた範囲のみ |
| DPLA（米国） | API v2（items） | **APIキー必須**（全リクエスト） | 無料（自己発行） | CC0方針 | RightsStatements.org等、資料毎 | なし（メタデータ集約） | 認証待ち実装（Stage 4） |
| KB / Delpher（オランダ） | SRU（jsru.kb.nl）＋ resolver.kb.nl | 不要（公開コレクション） | 無料 | CC0 | 資料毎（CC BY-NC-ND等）。1618–1879年新聞は権利フリー（KB案内） | resolver `:ocr` サフィックス | 条件適合→実装（Stage 4） |
| Japan Search（日本） | SPARQLエンドポイント＋資料JSON-LD | 不要 | 無料 | 提供DB毎 | jps:accessInfoのlicense（資料毎） | 資料依存（IIIFリンクあり） | 条件適合→実装（Stage 4） |
| Gallica（フランス） | SRU / IIIF / ALTO | 不要 | 無料 | BnF方針 | 資料毎 | あり（仕様確認済） | 実装済（b5）。実地検証は403継続で未達成 |
| BNE（スペイン） | datos.bne.es SPARQL | 不要 | 無料 | CC0（Linked Data） | 資料毎 | 確認できず | 調査のみ |
| ÖNB / ANNO（オーストリア） | **公式APIなし** | — | — | — | — | Webアプリ内部RESTのみ（非公式） | 調査のみ |
| HathiTrust（米国） | Bibliographic API／Data API | Bib不要／Data APIはOAuthキーセット必須 | 無料 | 書誌は利用可 | 資料毎（rights属性） | Data APIのみ（要キー） | 調査のみ |
| Trove（オーストラリア） | API v3 | **APIキー必須**（X-API-KEY） | 無料（12ヶ月で失効） | NLA条件 | 資料毎 | 新聞記事テキストあり | 調査のみ |
| 韓国国立中央図書館 | LOD SPARQL／Data4Library／国家書誌OpenAPI | SPARQL不要／他はキー発行＋承認必須 | 無料 | 機関方針 | 資料毎 | 確認できず | 調査のみ |
| 台湾国家図書館 | 統合APIは確認できず（個別DBのWeb検索のみ） | — | — | data.gov.tw掲載分はOGDL | 資料毎 | 確認できず | 調査のみ |

## 1. Finna（最優先・Stage 2で実装）

- 公式API：`https://api.finna.fi/api/v1/search`、`https://api.finna.fi/api/v1/record`。
  OpenAPI定義は `https://api.finna.fi/api/v1/?openapi`、Swagger UIあり。
  公式ドキュメント：https://www.kiwi.fi/display/Finna/Finna+API
  （Kiwi Wiki。Swaggerへの移行が案内されている）。利用条件：
  Finna API Terms of Use（Kiwi Wiki）。
- 認証：APIキー不要。費用：無料。公開されたレート制限は確認できなかった
  （未確認と記録する。過剰なリクエストは行わない）。
- 権利の分離（§13）：
  - メタデータ：**CC0 1.0**（Finna公式案内・フィンランド国立図書館の告知）。
  - 個別資料：レコードの `usageRights` フィールド（文字列配列。例：
    `"0/Paikalliskokoelma"`＝地域コレクション）。空配列は「権利表明なし」
    であり、自由利用可能を意味しない。
  - 画像・視覚資料：資料毎に異なるCCライセンス等。**メタデータCC0は
    原本画像・OCR本文のCC0を意味しない**。
- レコード構造（2026-11-26、利用者の通常ブラウザ経由で実応答を確認）：
  - 検索 `lookfor=Suomen historia&type=AllFields&limit=2` →
    `status: "OK"`、`resultCount: 530965`。
  - フィールド：`id`（例 `helle.687105`、`helka.997595663506253`。
    ドット前がデータソース）、`title`、`usageRights`（文字列配列）、
    `languages`（ISOコード配列、例 `["fin"]`）、`formats`、`buildings`。
  - **観測の不一致に関する注意**：同一URLへの2回の観測（20:26／20:27 JST）で
    先頭レコードと `formats`／`buildings` の表現形が異なった
    （文字列配列として報告された観測と、`{value, translated}` オブジェクト
    配列として報告された観測がある。`resultCount` は一致）。
    アダプターは両形状を防御的に処理する。
- 到達性：開発VM（サーバーネットワーク）からは **Cloudflareのボット
  チェックにより403**（2026-11-26にcurl／プロジェクトHTTPクライアント／
  テキスト取得の3経路で確認）。利用者の通常ブラウザからはチャレンジ通過後
  に生JSONが表示された。**回避は行わない**。したがってアダプターは
  フィクスチャ先行で実装し、LibraryService経由の実地検証は
  「サーバーネットワークからは未達成」と正直に記録する。
- Finnaは横断検索プラットフォームであり単一の所蔵機関ではない。
  `buildings` は所蔵機関階層（例：`0/Helle/` → `1/Helle/PNK/` →
  `2/Helle/PNK/PK/`）、`institutions` は提供機関。FinnaレコードID、
  提供元資料ID、所蔵機関、原本識別子を区別して保持する。
- ランディングURL：`https://www.finna.fi/Record/<id>`。

## 2. フィンランド国立図書館 Digi（Stage 3）

- 公式デジタル資料サービス：`https://digi.kansalliskirjasto.fi`
  （英語別名 digi.nationallibrary.fi）。歴史的新聞・雑誌・古書・公的刊行物。
  新聞ページは1,300万ページ超、フィンランド語・スウェーデン語。
- IIIF：国立図書館はDigiへのIIIF API導入を実施済（Images in Dialogue
  プロジェクト 2025–2026、kansalliskirjasto.fi）。FinnaレコードがIIIF
  マニフェストを持つ場合がある（IIIFガイドのFinna項）。
- 権利：Digiの案内では1911-01-01以前発行の新聞・雑誌は著作権消滅扱い。
  権利存続資料（例：1930–2018年の新聞）はHakaログイン制限の対象であり、
  **制限資料は取得しない**。
- 未確認事項：Digiの具体的なページOCR／ページ一覧エンドポイントの形状は
  実応答から確認できていない。開発VMからdigi.kansalliskirjasto.fiへの
  接続はプローブ時に空応答で失敗した。Stage 3では公式に確認できた経路
  （Finnaレコード経由のIIIFマニフェスト等）のみを実装し、確認できない
  機能は未実装として報告する。

## 3. DPLA（Stage 4で認証待ち実装）

- 公式API：`https://api.dp.la/v2/items`、`https://api.dp.la/v2/items/{id}`。
  開発者ドキュメント：https://pro.dp.la/developers
- 認証：**全リクエストに32文字の `api_key` クエリパラメータが必須**。
  キーは無料・自己発行（`POST /v2/api_key/<email>`）だが、**b8ではキー
  発行を承認されていない**ため発行しない。キー未設定時は
  `authentication_required` を明示する（Europeanaと同じ環境変数方式：
  `DPLA_API_KEY`）。
- 応答：JSON-LD。`count`／`start`／`limit`／`docs[]`。各docは
  `sourceResource`（title／creator／date／subject／rights等）、
  `provider`（集約ハブ）と `dataProvider`（原資料の提供機関）を別々に
  持ち、**両者を混同しない**。`isShownAt`／`object` は提供元資料への
  リンクであり、上流URLをサーバーから自動取得しない。
- DPLAはメタデータ集約であり全文・ページOCRは提供しない。権利は
  RightsStatements.org URI等が `sourceResource.rights` に入る。
- 公開されたレート制限は本調査では確定できなかった（未確認）。

## 4. KB / Delpher（Stage 4で条件適合を確認し実装）

- 公式SRU検索API：`https://jsru.kb.nl/sru/sru`（SRU 1.2、CQLクエリ、
  コレクション指定 `x-collection`。新聞記事は `DDD_artikel`）。
  登録不要で公開コレクションにアクセスできる（KBのAPI入門資料
  KBNLresearch/intro-kb-apis が利用法を公開）。
- 実地確認（2026-11-26、開発VM）：HTTP 200、SRU XML応答。
  テストクエリで `numberOfRecords` 32,487件、Dublin Core系レコードと
  resolver URN（`:ocr` サフィックス付き）を確認。
- OCR・画像：KBリゾルバ `https://resolver.kb.nl/resolve?urn=<URN>:ocr`
  （OCRテキスト）、`:image`（画像）、`:mpeg21`。
- 権利：メタデータはCC0。画像・全文は資料毎（CC BY-NC-ND等）。
  1618–1879年の新聞は著作権フリー（KBのデータセット案内）。
  Delpherサイト自体はrobotsで閉じられているため、対象はSRU APIと
  リゾルバのみとする。
- 一部データセットは dataservices@kb.nl 経由の法的アクセス付与が前提と
  案内されている。本アダプターは登録不要の公開SRU経路のみを使う。

## 5. Japan Search（Stage 4で条件適合を確認し実装）

- 公式SPARQLエンドポイント：`https://jpsearch.go.jp/rdf/sparql`
  （EasySPARQL UIあり）。資料毎JSON-LD：`https://jpsearch.go.jp/data/<id>.json`。
  開発者向け案内：https://jpsearch.go.jp/static/developer/introduction/en.html
- 認証：不要。費用：無料。約1,700万件／310DB中240DBがAPI利用可（2026-03時点、
  jpsearch.go.jp）。
- スキーマ：JPS-RDF。`jps:accessInfo` に提供者（schema:provider）、
  ライセンス（schema:license、CC BY URI等）、URL、IIIFマニフェストへの
  リンク（資料による）が入る。権利は資料・提供DB毎に異なる。
- 実装方針：固定テンプレートSPARQL＋リテラル厳密エスケープによる
  キーワード検索。利用条件は提供DB毎の表示に従い、権利不明は保守的に扱う。

## 6. Gallica（再検証結果）

- 2026-11-26、開発VMからSRUへ1回だけ再検証：**HTTP 403が継続**。
  §8に従いここで停止した。プロキシ・VPN・UA偽装・ミラー等の回避は
  行っていない。b8の必須条件にはしない（ブリーフ§8どおり）。

## 7. スペイン国立図書館 BNE（調査のみ）

- datos.bne.es：カタログ全体（900万件超、デジタル資料約15万件）を
  Linked Dataとして公開。SPARQLエンドポイント
  `http://datos.bne.es/sparql`、コンテンツネゴシエーション（JSON-LD等）。
  データは **CC0（Public Domain dedication）** で公開（BNE/OEGの発表）。
  APIキー不要。
- ページ単位OCRの公式APIは本調査で確認できなかった。SPARQLベースの
  書誌アダプターは将来候補とし、b8では調査のみ。

## 8. オーストリア国立図書館 ANNO（調査のみ）

- **ANNOは公式APIを公開していない**（サードパーティ製ANNOクライアントの
  ドキュメントが明記）。存在するのはWebアプリ（AnnoSearch）の内部REST
  バックエンドと、ビューアの `annoshow` CGIであり、いずれも公式に
  仕様が保証されたAPIではない。
- ÖNB Labsは別途データダンプ／SPARQL等の研究向けサービスを提供するが、
  ANNO新聞のページOCR取得経路としては公式APIに当たらない。
- 結論：§9の「公式API」条件を満たさないため、b8では実装しない。

## 9. HathiTrust（調査のみ）

- Bibliographic API：`https://catalog.hathitrust.org/api/volumes/brief|full/<idtype>/<id>.json`。
  キー不要だが、**識別子（ISBN/LCCN/OCLC/ISSN/htid/recordnumber）による
  参照専用でキーワード検索はない**。応答に rights 情報（usRightsString等）。
- Data API（ページ画像・ページOCR）：OAuth 1.0aキーセットが必須で、
  HathiTrustへの申請・発行が必要。b8では発行を承認されていない。
- 結論：キーワード検索アダプターの形では実装できず、調査のみ。

## 10. Trove（調査のみ）

- API v3：`https://api.trove.nla.gov.au/v3/result`。**無料APIキーが必須**
  （`X-API-KEY` ヘッダ）。キーはTroveアカウントから発行、12ヶ月で失効。
  新聞記事の全文テキスト取得も可能だが、2025年2月以降、全
...[truncated 2085 chars]