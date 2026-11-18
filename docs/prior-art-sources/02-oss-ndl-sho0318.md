# Phase 0 既存OSS調査: sho0318/ndl-mcp

- **対象**: https://github.com/sho0318/ndl-mcp
- **確認日**: 2026-11-19
- **調査目的**: 新規 Global Library MCP 実装前の事実確認
- **結論**: 小規模な Python 製 MCP サーバーで、NDL 次世代デジタルライブラリーの3機能（資料横断検索、資料内全文検索、ページ取得）を直接呼び出す最小実装。MIT で再利用しやすいが、配布パッケージや公式 MCP Registry 登録は確認できず、保守・テスト・入力検証・障害処理・URLエンコードに弱点がある。NDL の対応範囲は日本の国立国会図書館デジタルコレクション由来のインターネット公開・著作権保護期間満了資料に限られ、Global Library MCP の他機関横断機能が想定される場合は置換ではなく一機関コネクタ候補である。

## 公式リポジトリの事実

GitHub README（ページタイトル: `sho0318/ndl-mcp`）は、NDL の「次世代デジタルライブラリー」APIを利用した MCP サーバーであると説明する。実装ツールは以下の3つ。

1. `search_books(keyword)`: `/dl/api/book/search?keyword=...` を呼び、資料ID、タイトル、巻、責任表示、出版年を文字列化する。README は資料の横断検索と説明する。
2. `search_in_book(book_id, keyword)`: `/dl/api/page/search?f-book=...&q-contents=...` を呼び、ヒットしたページID、ページ番号、本文スニペットを返す。README は指定資料内の全文検索と説明する。
3. `get_page(book_id, page_number)`: `/dl/api/page/{book_id}_{page_number}` を呼び、`coordjson` を JSON として解析し、各文字列の `contenttext` を連結して返す。README は指定ページのデータ取得と説明する。

実装は `FastMCP("ndl")` と stdio transport を使い、HTTP クライアントは `httpx.AsyncClient`、タイムアウトは10秒。トップレベルは `.gitignore`, `.python-version`, `LICENSE`, `README.md`, `ndl.py`, `pyproject.toml`, `uv.lock` のみで、GitHub の表示上コミット数は6、言語はPythonのみ（2,181 bytes）。Python 3.13以上、依存は `httpx>=0.28.1` と `mcp[cli]>=1.6.0`。

GitHub API（ページタイトル: repository metadata）は、公開・非アーカイブ・非fork、default branch は `master`、作成日時は 2025-04-19、`pushed_at` は 2025-04-19T02:44:12Z、GitHub上の `updated_at` は 2026-04-08T07:55:29Z。コミット履歴で確認できる最後のコード/README更新は 2025-04-19。stars 2、forks 0、open issues 0、releases は空配列。`updated_at` は GitHub上のメタデータ更新時刻であり、コード保守の証拠とはみなさない。

ライセンスファイル（ページタイトル: `LICENSE`）は MIT License、Copyright (c) 2025 ishii sho。著作権表示保持を条件に使用、改変、配布が可能で、無保証・免責条項がある。

## NDL公式情報とデータ範囲

NDL Lab の「次世代デジタルライブラリー」ページ（ページタイトル: `次世代デジタルライブラリー`）は、実験的検索サービスで、全文テキスト検索、機械学習による自動処理、IIIF API等の有効性検証を目的とする。対象は国立国会図書館デジタルコレクションでインターネット公開されている、著作権保護期間満了の図書・古典籍のデジタル化資料で、ページ記載の規模は約35万点。内訳として、図書約28万点、古典籍約8万点のOCR成果物が説明されている。OCRテキストは機械的処理された検索用データで、誤りを含み得る。

公式API仕様（ページタイトル: `次世代デジタルライブラリーのAPIについて`）は、Book API、Page API、Illustration APIを定義する。

- **全文検索**: Book API の資料検索は書誌データとOCR全文を横断検索し、キーワード周辺スニペットを最大3箇所取得可能。Page API の資料内検索は資料PIDを必須とし、ヒットしたコマごとにスニペットを返す。実測でも `book/search` と `page/search` は JSON の `list`, `hit`, `from` 等を返した。
- **全文取得**: Book API に資料全体のOCR全文を JSON (`fulltext-json/{PID}`) または ZIP (`fulltext/{PID}`) で取得するAPIがある。実測した JSON 形式は `application/octet-stream` で、ページごとの `contents` と座標付き `coordjson` を含んだ。なお、対象PIDや利用条件により403となり得ることを公式仕様が明記する。
- **画像**: Page API のページ取得はページメタデータ、本文、座標JSON等を返す。画像ファイルは次世代APIのJSONから得た情報をもとに、NDLデジタルコレクションの IIIF Image API URL を組み立てて取得できる。画像全体だけでなく、パーセント座標による領域切り出し例が公式仕様にある。
- **ページ単位取得**: `/api/page/{PID}_{ページ番号}` があり、`coordjson` 等を返す。2025-08-26追加のレイアウト付きXMLページAPI `/api/page/layout/{PID}_{ページ番号}` も公式仕様に記載される。
- **図版・画像検索**: Illustration API は図版メタデータ、テキストからの類似画像検索、画像IDからの類似画像検索、ランダム取得等を提供する。対象は自動抽出された挿絵、写真、図表等。
- **標準規格**: NDL公式ページはIIIF Image APIの利用を明記する。NDL Searchの別サービス公式APIページはメタデータ検索にSRU、OpenSearch、OpenURL、収穫にOAI-PMH、サムネイルAPIを提供すると説明する。ただし、対象OSS `ndl-mcp` のコードはこれらNDL Search APIを呼ばず、`lab.ndl.go.jp/dl/api/...` の次世代デジタルライブラリーAPIだけを呼ぶ。対象OSSについてSRU/OAI-PMH/OpenSearch/OpenURLのMCPツール対応は**未確認（実装上は非対応と判断できる）**。IIIFは機関側で利用可能だが、対象OSSに画像取得ツールはなく、MCP経由での画像返却は**未実装**。
- **OCR**: OCR全文検索・OCRテキスト取得は公式APIで可。独立したOCR実行、OCR画像アップロード、OCR品質保証は提供されず、既存NDL OCR成果物を使う。

## コード品質・セキュリティ上の注意

以下はソースコードから直接確認できる注意点であり、脆弱性が実際に悪用されたことを示すものではない。

- `keyword` と `book_id` はURLへ直接文字列補間され、`urllib.parse`等によるURLエンコードがない。`&`, `?`, `#`, 日本語、特殊文字を含む入力でクエリ解釈が変わる可能性があり、入力の意図しないパラメータ混入や検索失敗に注意が必要。
- `httpx.AsyncClient`を各呼出しごとに生成し、再利用、接続上限、リトライ、バックオフ、レスポンスサイズ上限、User-Agent、レート制御がない。NDL公式は大量・継続アクセスで制限・ブロックの可能性を注意喚起している。
- HTTPステータスが200以外の場合は単にNoneを返す。エラー種別、レスポンス本文、再試行可能性をMCP利用者へ示さない。
- `get_page` の `if not data and data["coordjson"] is None:` は、`data` がNoneのとき右辺で添字アクセスするため、None応答時に例外を起こす不具合がある。`coordjson`が空・不正JSONの場合の扱いもない。
- `search_books` / `search_in_book` の戻り型注釈は `dict[str, Any] | None` だが、実際には文字列を返す。READMEやMCPスキーマ利用者との型整合性に注意。
- ページ取得は座標JSONの `contenttext` を単純連結するだけで、段組み・読み順・改行の意味を保証しない。レイアウトXML等の新APIを利用しない。
- テスト、CI、静的解析、依存脆弱性スキャン、認証、監査ログはリポジトリ上で確認できない。これは「存在しない」と断定せず、公開ファイル上**未確認**とする。
- APIは外部のNDL Labに依存し、仕様・URL・データが予告なく変更・削除され得る。NDL公式が実験的サービスと説明しているため、可用性・後方互換性は保証されない。

## 再利用可能性

MITライセンス、少数の依存、単一Pythonファイル、標準的なFastMCP stdio構成のため、コード断片・ツール設計・NDL API接続のたたき台として再利用しやすい。特に、NDL次世代デジタルライブラリーをGlobal Library MCPの一機関コネクタとして分離する場合、3ツールの概念は流用可能。

一方で、そのまま本番採用するには、URL/クエリの安全な組み立て、明示的な構造化戻り値、エラー分類、タイムアウトと再試行・レート制御、キャッシュ、レスポンス上限、API仕様変更への追随、テスト、依存固定・監査、利用規約とクレジット表示の実装確認が必要。NDL公式の利用条件では、非営利等を除きAPIの営利・継続利用で申請が必要となる場合があり、商用Global Library用途では個別確認が必要。

## Global Library MCPとの重複・差分

**確定できる重複**: Global Library MCPの正式な対象機関・ツール一覧・共通スキーマが本調査入力には提示されていないため、Global Library側との厳密な重複率は**unknown**。一般的な意味では、書誌検索、全文検索、ページ本文取得という機能領域がGlobal Libraryの図書館コネクタに含まれるなら、その部分は重複する可能性がある（推測）。

**確認できる差分**: `ndl-mcp` はNDL次世代デジタルライブラリーだけを対象とし、約35万点規模の日本語図書・古典籍、著作権保護期間満了・インターネット公開資料に依存する。一方、複数国・複数機関、統一メタデータ、機関横断検索、共通のページ/画像/全文抽象化、IIIF/SRU/OAI-PMH対応をGlobal Libraryが目指すなら、対象範囲と抽象化レベルが異なる（Global Library仕様未提示のため条件付き）。`ndl-mcp` は画像取得・図版検索・全文一括取得・IIIF URL生成・SRU/OAI-PMHをMCPツールとして公開していない。

## 未確認事項

- Global Library MCPの確定仕様、対象機関、既存NDLコネクタ、共通ツール名・戻り値・重複判定基準。
- sho0318/ndl-mcpのissue/PRの実質的な活動、作者の保守方針、利用実績、未公開ブランチ。
- `uv.lock`に記録された全推移依存の脆弱性状態と、依存ライセンスの完全な一覧。
- NDL APIのレート上限の数値、SLA、すべてのHTTPエラー形式。
- 次世代デジタルライブラリーが将来提供する全機関・全データ範囲の変更予定。
- 対象APIがSRU、OAI-PMH、OpenSearch、OpenURLのどれかを内部的に使っているか。公開MCPコードからは利用していないことだけ確認できる。

## References

[1]: https://github.com/sho0318/ndl-mcp "sho0318/ndl-mcp GitHub repository"
[2]: https://raw.githubusercontent.com/sho0318/ndl-mcp/master/ndl.py "ndl-mcp source file ndl.py"
[3]: https://raw.githubusercontent.com/sho0318/ndl-mcp/master/pyproject.toml "ndl-mcp pyproject.toml"
[4]: https://raw.githubusercontent.com/sho0318/ndl-mcp/master/LICENSE "ndl-mcp MIT License"
[5]: https://api.github.com/repos/sho0318/ndl-mcp "GitHub repository metadata API"
[6]: https://api.github.com/repos/sho0318/ndl-mcp/commits?per_page=20 "ndl-mcp commit history API"
[7]: https://api.github.com/repos/sho0318/ndl-mcp/releases "ndl-mcp releases API"
[8]: https://lab.ndl.go.jp/service/tsugidigi/ "NDL Lab 次世代デジタルライブラリー"
[9]: https://lab.ndl.go.jp/service/tsugidigi/apiinfo/ "次世代デジタルライブラリーのAPIについて"
[10]: https://lab.ndl.go.jp/service/tsugidigi/tsugidigi_en/ "Next Digital Library English page"
[11]: https://lab.ndl.go.jp/dl/v3/api-docs "Next Digital Library OpenAPI document"
[12]: https://ndlsearch.ndl.go.jp/en/help/api "NDL Search API official help"
[13]: https://registry.modelcontextprotocol.io/v0.1/servers?search=sho0318 "Official MCP Registry search for sho0318"
[14]: https://pypi.org/search/?q=ndl-mcp "PyPI search for ndl-mcp"
