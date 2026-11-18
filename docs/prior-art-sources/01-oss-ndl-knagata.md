# Phase 0 既存OSS調査: knagata/ndl-mcp

- **対象**: https://github.com/knagata/ndl-mcp
- **確認日**: 2026-11-19
- **調査言語**: 日本語・英語の一次情報を確認
- **判定上の原則**: 公式ページおよび対象リポジトリで確認できた事実と、Global Library MCPとの比較上の推測を分離した。確認できない事項は `unknown` とした。

## 1. 結論

`knagata/ndl-mcp` は、国立国会図書館（NDL）の複数のHTTP APIをFastMCPのstdioサーバーとしてラップする小規模なPython実装である。確認できるツールは、NDLサーチの書誌検索（OpenSearch）、CQL検索（SRU）、次世代デジタルライブラリーの全文検索、資料内ページ検索、OCR全文のページ範囲取得、図版のテキスト検索、ISBN書影URL取得の7種である。

実装はNDL固有のデータ源に限定され、複数国・複数機関を横断する抽象化や、一般的な図書館プロトコルの統合層ではない。したがってGlobal Library MCPにとっては、NDLコネクタおよび全文・図版検索の実装例として再利用価値がある一方、機関横断、認証・レート制御、権利情報、画像取得、IIIF/SRU/OAI-PMHの汎用操作をそのまま代替するものではない（Global Library MCPの正式仕様は本調査資料だけでは提示されていないため、重複・差分の一部は `unknown`）。

## 2. リポジトリと機能（確認できた事実）

GitHubリポジトリのREADMEおよび`server.py`に次の7ツールが記載・実装されている。[1][2]

1. `ndl_search`: NDLサーチ OpenSearch APIによるキーワード、書名、著者、出版者、ISBN、出版年、NDC、資料種別等の書誌検索。READMEでは取得件数の最大を200としている。
2. `ndl_search_cql`: NDLサーチ SRU APIによるCQL検索。`dc`または`dcndl`スキーマ、開始位置、件数を受け取る。READMEでは最大500件としている。
3. `ndl_fulltext_search`: 次世代デジタルライブラリーの資料単位全文検索。キーワード、NDC、対象フィールド、古典籍限定、スニペット等に対応するとREADMEにある。
4. `ndl_book_page_search`: PIDで指定した資料内をページ単位で全文検索。
5. `ndl_get_fulltext`: PIDで指定した資料のOCR全文を取得し、`page_from`/`page_to`でページ範囲を絞る。
6. `ndl_search_illustrations`: 図版周辺テキストを用いた図版検索。地図、グラフ、イラスト、写真等のタグフィルタを実装している。
7. `ndl_get_thumbnail_url`: ISBNからNDL書影URLを組み立て、画像の存在を確認する。

実装が参照する固定エンドポイントは、NDLサーチ OpenSearch (`https://ndlsearch.ndl.go.jp/api/opensearch`)、NDLサーチ SRU (`https://ndlsearch.ndl.go.jp/api/sru`)、次世代デジタルライブラリーの資料検索、ページ検索、図版検索、ISBN書影URLである。OCR全文取得は`https://lab.ndl.go.jp/dl/api/book/fulltext-json/{pid}`を使う。[2]

依存関係はPython 3.10以上、`fastmcp>=2.0.0`、`httpx>=0.27.0`である。[1][3] `pyproject.toml`のプロジェクトバージョンは1.0.0で、Hatchlingビルドと`ndl-mcp = "server:main"`のエントリポイントを定義する。[3]

## 3. 対応機関・データ範囲

### 3.1 実装が直接対象にする機関・サービス

確認できる直接対象は、国立国会図書館が運営する以下のサービスである。

- **国立国会図書館サーチ**: 書誌・所蔵等の検索。NDL公式説明では、API対象データは許諾が得られたデータに限られ、データプロバイダごとに利用条件が異なる。[4][5]
- **国立国会図書館 次世代デジタルライブラリー**: NDLデジタルコレクションのうち、インターネット公開可能な著作権保護期間満了資料を中心に、約35万資料（英語ページ記載時点）を対象とする実験的サービス。全文OCR検索、図版・画像検索、IIIFを利用するビューア等を提供する。[6][7]

NDLサーチの公式データプロバイダ一覧には、NDL蔵書、雑誌記事索引、NDLデジタルコレクション、青空文庫、J-STAGE、WARP、IRDB、大学・自治体等のデジタルアーカイブなど多数のプロバイダが載っている。しかし、`ndl-mcp`の実装はプロバイダごとのAPIを個別にラップせず、NDLサーチの横断検索APIを呼ぶ構造である。従って「検索可能なデータ範囲」はNDLサーチ側のAPI提供対象と、その時点の検索インデックスに依存する。[5]

### 3.2 NDL公式が示す主なプロバイダ範囲

NDL公式の詳細説明によれば、NDL蔵書には国内刊行図書、洋図書、博士論文、地図資料等の多様な所蔵資料と雑誌巻号レベル書誌が含まれる。雑誌記事索引、オンライン資料、NDLデジタルコレクション、電子書籍・電子雑誌は別プロバイダであるため、NDL蔵書プロバイダに自動的に含まれるわけではない。[5]

## 4. API・標準規格の確認

### 4.1 機関ごとの可否マトリクス

| 機関/サービス | 書誌全文検索 | OCR全文 | ページ単位取得/検索 | 画像・図版 | IIIF | SRU | OAI-PMH |
|---|---|---|---|---|---|---|---|
| NDLサーチ | **可**。OpenSearch、SRU、OpenURL | **不可/unknown**。NDLサーチ書誌API自体はメタデータ検索であり、`ndl-mcp`もここから本文を取得しない | **不可/unknown**。NDLサーチAPIとしての本文ページ取得は確認できない | **書影URLのみ実装**。一般の資料ページ画像取得はunknown | **unknown**。NDLサーチAPI仕様ページでこの実装の対象としては確認できない | **可**。公式ベースURLとCQL仕様あり | **可**。公式OAI-PMHエンドポイントあり |
| 次世代デジタルライブラリー | **可**。キーワードによるOCR全文検索 | **可**。資料のOCR全文JSONをページ範囲付きで取得する実装 | **可**。資料内ページ検索、および全文取得のページ範囲指定 | **部分的に可**。図版のテキスト検索・タグ検索とISBN書影URL。任意ページ画像の直接取得は`ndl-mcp`に実装なし | **可（サービス側）**。公式説明がIIIF-powered viewer / IIIF APIの利用を明記。ただし`ndl-mcp`のツールとしては未実装 | **該当なし/unknown**。次世代デジタルライブラリーAPIの実装はSRUではない | **該当なし/unknown**。NDLサーチのOAI-PMHとは別サービスで、`ndl-mcp`は呼ばない |

### 4.2 全文検索・OCR

次世代デジタルライブラリー公式ページは、OCR生成された書籍全文のキーワード検索を提供し、約28万冊の2021年度OCRテキストと約6万件の古典籍OCRテキストを説明している。[7] 英語の利用案内は、対象がインターネット公開可能なNDLデジタルコレクション資料であること、全文検索と自動画像抽出を提供することを示している。[6] `ndl-mcp`は資料検索、ページ検索、`fulltext-json/{pid}`のページ範囲取得を実装している。[2]

### 4.3 画像・ページ単位取得

`ndl-mcp`の`ndl_get_fulltext`はページ番号範囲のOCRテキストを返すが、画像バイナリやIIIF Image APIのURLを返すツールではない。`ndl_search_illustrations`も図版の検索結果（PID、ページ、座標、タグ、周辺テキスト等）を整形する実装で、画像取得処理は確認できない。`ndl_get_thumbnail_url`はISBN書影URLの存在確認に限定される。[2]

次世代デジタルライブラリーの公式説明には、IIIF-powered book viewer、見開き・ページ単位表示、画像処理等がある。[7] ただし、`ndl-mcp`がそのIIIFマニフェストや画像エンドポイントを呼ぶ事実は確認できない。したがって「サービス側のIIIF提供」は事実だが、「このOSSでIIIF画像を取得できる」は誤りである。

### 4.4 SRU・OAI-PMH・DC-NDL

NDLサーチ公式仕様は検索用APIとしてSRU、OpenSearch、OpenURL、ハーベスト用APIとしてOAI-PMHを提供すると記載する。返却メタデータはDC-NDLを基本とし、OAI-PMHでは`oai_dc`、`dcndl`、`dcndl_v3`を選べる。[4][8] `ndl-mcp`はSRUをCQL検索に利用するが、OAI-PMHクライアントやハーベストツールは実装していない。[2]

`ndl-mcp`のREADMEはAPIを「認証不要で無償」と説明するが、NDL公式は営利利用、継続的アクセス、大量アクセス、データプロバイダごとの許諾・クレジット表示に条件を設けている。[1][9] 実運用ではREADMEより公式条件を優先すべきである。

## 5. ライセンスと再利用可能性

READMEは本プロジェクトのライセンスをMITと記載している。[1] しかし、GitHubのトップレベルファイル一覧には`LICENSE`が見当たらず、`https://raw.githubusercontent.com/knagata/ndl-mcp/main/LICENSE`も2026-11-19確認時点で404だった。従って「README上の主張」はMITだが、リポジトリ内のライセンスファイルによる明示は確認できず、法的な再利用判断には著作権者への確認が必要である。依存ライブラリのライセンス、NDL由来メタデータ・本文・画像の個別利用条件も別途確認が必要である。

コードは小さく、固定エンドポイント、`httpx.AsyncClient`、30秒タイムアウト、XML/RSSレスポンスの変換という構成で、NDLコネクタのたたき台としては再利用しやすい。特にOpenSearch/SRUレスポンス解析と、PIDを介した全文検索→ページ検索→ページ範囲取得の流れは、NDL向けアダプタの実装例として有用である。[2]

一方、再利用前に必要な作業は、ライセンスファイルの確認、NDLの利用申請・クレジット条件への対応、プロバイダ別権利表示、レート制御・指数バックオフ、キャッシュ、レスポンススキーマ検証、テスト追加、IIIF画像取得の追加である。

## 6. 最終更新・保守状況

GitHubのコミット履歴では、リポジトリ作成は2026-02-27、確認できる最終コミットは2026-03-04の`minor update`で、確認日時点のコミット数は6件と表示される。[1][10] Releasesページ、Issues、Pull Requests、Actions、Securityページへのナビゲーションはあるが、今回確認できた一次情報だけでは、継続的なリリース、CI、脆弱性対応、メンテナー人数、SLAを確認できない。保守活性は「短期間に初期コミット後、2026-03-04以降の更新は確認できない」と評価し、長期保守はunknownとする。

## 7. コード品質・セキュリティ上の注意

確認できた実装上のプラス要素は、ログをstderrに出してMCP stdioのstdoutを汚さない設計、HTTPタイムアウト30秒、入力の一部バリデーション、XML名前空間を使ったパーサ、固定のHTTPSエンドポイントである。[2]

注意点は以下のとおりである。

- `server.py`は標準の`xml.etree.ElementTree`で外部APIのXMLを解析する。呼び出し先を固定した通常運用では直ちに脆弱性と断定できないが、将来の外部XML入力やプロキシ化を考えるなら、defusedxml等とサイズ制限を検討すべきである。
- 取得失敗、HTTPステータス、JSON/XMLの形式不一致に対する処理は限定的に見える。NDL APIの仕様変更や一時障害時に、利用者へ安定した構造化エラーを返す仕組みは不十分である可能性がある（網羅的テストは未確認）。
- レート制御、リトライ、キャッシュ、同時実行数制限は確認できない。NDL公式は同時リクエスト制限、大量アクセス時の遮断可能性を明記している。[9]
- `FULLTEXT_URL`はユーザー指定PIDをパスへ埋め込む。接続先ホスト自体は固定だが、PIDの文字種・長さ・パス区切りを厳格に検証する方が安全である。
- リポジトリのトップレベルに`__pycache__`が含まれる。テスト、型チェック、CI、Dependabot、署名付きリリース、セキュリティポリシーは確認できず、コード品質の自動保証はunknownである。
- 依存指定が`fastmcp>=2.0.0`、`httpx>=0.27.0`と下限のみで、ロックファイルやハッシュ固定は確認できない。再現可能ビルド・サプライチェーン管理の観点で注意が必要である。[3]

## 8. Global Library MCPとの重複・差分

Global Library MCPの正式なツール一覧、対応機関、標準プロトコル、権利モデルは本調査対象の提示情報だけでは確認できないため、厳密な重複率や置換可否はunknownとする。

ただし、今回確認できた`ndl-mcp`の性質から、事実に基づく比較軸は次のとおりである。

- **重複しうる領域**: NDL書誌キーワード検索、著者・タイトル・ISBN・NDC検索、CQL/SRU検索、NDLデジタル資料の全文検索、資料内ページ検索、OCRテキスト取得、図版検索、書影URL取得。
- **ndl-mcp固有の強み**: NDLの次世代デジタルライブラリーAPIに直接対応し、OCR全文、ページ検索、図版タグ検索を一連のMCPツールにしている。これは一般的な書誌検索だけのMCPより深いNDLデジタル資料アクセスである。
- **Global Library MCPに期待される差分（ただし仕様未確認）**: 複数機関を統合する抽象化、機関別のAPI能力・権利条件の明示、IIIF画像/マニフェスト、SRU/OAI-PMHの汎用操作、結果の出典・ライセンスを共通形式で返す能力があれば、`ndl-mcp`より広い。これらが実装済みかはunknown。
- **再利用方針**: 全体をそのまま採用するより、NDL専用コネクタとしてレスポンス解析、PIDワークフロー、ツールの粒度を取り込むのが適切。ライセンスファイル不在、NDL利用条件、レート制御、画像取得未実装を解消してから統合する。

## 9. 未確認事項（unknown）

- Global Library MCPの正式仕様と、上記各機能との実際の重複率。
- `ndl-mcp`のMITライセンスが著作権者により別途許諾されているか。README以外のLICENSEファイルは確認できない。
- NDLサーチの全データプロバイダが各APIで同一に検索できるか。公式一覧上のAPI可否・利用条件はプロバイダごとに異なる。
- NDLサーチ自体の画像、ページ画像、IIIFマニフェストの公開URLを、このOSSの未実装エンドポイント以外でどう取得するか。
- 次世代デジタルライブラリーの公開APIの完全な仕様、レート上限、安定性、将来互換性。
- 自動テスト、CI実行結果、依存脆弱性スキャン、実運用でのエラー率。
- MCP Registryに登録されているか（公式Registry APIの`search=ndl-mcp`は`servers: []`、件数0だった）。
- PyPI/npmで本リポジトリの正式配布物が存在するか。PyPI検索では`ndl-mcp`の正式一致パッケージを確認できず、GitHubからの直接利用がREADMEの主な導線である。

## References

[1]: https://github.com/knagata/ndl-mcp "knagata/ndl-mcp GitHub repository"
[2]: https://raw.githubusercontent.com/knagata/ndl-mcp/main/server.py "ndl-mcp server.py"
[3]: https://raw.githubusercontent.com/knagata/ndl-mcp/main/pyproject.toml "ndl-mcp pyproject.toml"
[4]: https://ndlsearch.ndl.go.jp/help/api/specifications "NDLサーチ API仕様の概要"
[5]: https://ndlsearch.ndl.go.jp/help/api/provider "NDLサーチ API提供対象データプロバイダ一覧"
[6]: https://lab.ndl.go.jp/service/tsugidigi/tsugidigi_en/ "Next Digital Library (English)"
[7]: https://lab.ndl.go.jp/dl/ "次世代デジタルライブラリー"
[8]: https://ndlsearch.ndl.go.jp/help/api/oai_pmh "国立国会図書館サーチが提供するOAI-PMH"
[9]: https://ndlsearch.ndl.go.jp/help/api "APIのご利用について"
[10]: https://github.com/knagata/ndl-mcp/commits/main "ndl-mcp commit history"
[11]: https://registry.modelcontextprotocol.io/v0.1/servers?search=ndl-mcp "Official MCP Registry search for ndl-mcp"
[12]: https://pypi.org/search/?q=ndl-mcp "PyPI search for ndl-mcp"
