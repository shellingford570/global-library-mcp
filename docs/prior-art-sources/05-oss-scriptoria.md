# 既存OSS調査: nikazzio/scriptoria

- **確認日:** 2026-11-19
- **対象:** https://github.com/nikazzio/scriptoria
- **調査方針:** 公式GitHub、公式ドキュメント、公式リリース、公式MCP Registry、PyPI/npmの原ページを確認。公式記載・実装で確認できた事実と、確認できなかった事項を分離した。

## 1. 結論

Scriptoriaは、IIIF原稿資料を対象にしたローカルファーストの研究ワークベンチである。Discovery、ローカルLibrary、MiradorベースのStudio、ページ修復・PDF/画像出力を一体化し、複数のデジタル図書館プロバイダを共通のプロバイダレジストリ／リゾルバで扱う。公開コード上のプロジェクト名・PyPI配布メタデータ名は `universal-iiif`、CLIは `scriptoria-cli` である。[1][2][3]

Global Library MCPとの重複は、図書館・デジタルコレクションの横断的な発見、IIIFマニフェストの解決、ページ画像の取得、ページ単位の閲覧・OCR補助にある。一方、ScriptoriaはMCPサーバではなく、ローカルUI/CLI、ローカルSQLite保管庫、ダウンロード・PDF出力・ページ修復を中心とした利用者向けアプリである。Global Library MCPが目指す機関横断の統一MCP API、検索・全文・画像・ページ取得のツール契約、機関別プロトコル統合までは、Scriptoriaの公開資料から確認できない。

## 2. 確認できた機能

- Webアプリの4面構成は Discovery / Library / Studio / Output。DiscoveryはURL、ID、shelfmark、プロバイダ固有の検索語をマニフェストへ正規化し、LibraryはローカルSQLiteのカタログ、StudioはMirador・ローカル/リモート読取・OCR/転写、Outputはページ検査、修復、PDF/画像出力とジョブ監視を担う。[1][4]
- 直接のIIIFマニフェストURLは汎用入力として受け付ける。CLI例は Vaticana の `manifest.json` URLで、既知のプロバイダURL・識別子・shelfmarkも共通リゾルバでマニフェストURLへ変換する。[1][5]
- ダウンロードは、設定次第で上流のネイティブPDFを優先し、なければIIIF画像取得へフォールバックする。中央HTTPクライアントがリトライ、指数バックオフ、レート制御、プロバイダ別ネットワークポリシーを担う。[3][4]
- OCR/転写はページ・原稿コンテキストに紐づく非同期ジョブ。アーキテクチャ文書はローカルKrakenとリモートOpenAI/Anthropicエンジンを共通ワークフローで抽象化すると記載する。CLIの `--ocr MODEL` は設定済みローカルモデルディレクトリのKrakenモデルを想定する。[4][5]
- ローカル先行で、クラウド依存なし。マニフェスト、スキャン、OCR/スニペット、出力を設定ディレクトリに保持し、部分ダウンロード・再開・ステージングからのページ昇格を扱う。[1][3][4]

## 3. 対応機関・データ範囲と機関別API確認

公式Provider Supportは次のプロバイダを列挙している（generic direct IIIFを含む）。Vaticana/BAV、Gallica/BnF、Institut de France/Bibnum、Bodleian/Oxford、Universitätsbibliothek Heidelberg、Cambridge University Digital Library、e-codices、Biblioteca Estense、Harvard、Library of Congress、Internet Archive、Internet Culturale/ICCU（BETA）。約50のイタリア系図書館を束ねるICC​​Uゲートウェイについても説明がある。[2]

下表の「Scriptoriaで確認した機能」はScriptoriaの統合レベルであり、各機関の公式API全体の能力を意味しない。SRU/OAI-PMHは、Scriptoria公式文書・レジストリ・取得コードの確認範囲では実装または対応の明記を確認できなかったため、全機関について `unknown` とした。OCRも各機関の提供APIではなく、Scriptoria側のOCR機能として確認できる範囲に限定した。

|機関/プロバイダ|全文検索|OCR API|画像取得|ページ単位取得|IIIF/SRU/OAI-PMHの確認|
|---|---|---|---|---|---|
|Vaticana (BAV)|`fallback`。shelfmark/マニフェストが主|機関OCR APIはunknown。Scriptoria側OCRは可|直接IIIFマニフェストから取得可|IIIFマニフェストのcanvas/page相当を前提に可|IIIF: Scriptoriaの直接解決/取得を確認。Presentation/Imageの機関別バージョンはunknown。SRU/OAI-PMH: unknown|
|Gallica (BnF)|`search_first`。ARK、レコードURL、テキスト検索、資料種別フィルタ|機関OCR APIはunknown。Scriptoria側OCRは可|IIIFまたはネイティブPDF優先/画像フォールバック|マニフェスト・ページ画像ワークフローとして可|IIIF統合は確認。Presentation/Imageの版、全文API、SRU/OAI-PMHはunknown|
|Institut de France (Bibnum)|`fallback`。数値ID、viewer URL、テキスト検索|unknown（機関OCR API）；Scriptoria側OCRは可|IIIFマニフェスト経由の取得|ページ単位のローカル作業は可|IIIF直接解決は確認。その他の機関API仕様はunknown|
|Bodleian/Oxford|`direct` with search handler。UUID/レコードURLが主|unknown；Scriptoria側OCRは可|IIIFマニフェスト経由|可（マニフェストのページ単位処理）|IIIF統合は確認。SRU/OAI-PMH、全文検索APIの詳細はunknown|
|Heidelberg|`fallback`。レコードID/URL、自由語は不安定|unknown；Scriptoria側OCRは可|IIIFマニフェスト経由|可（ページ処理）|IIIF統合は確認。その他はunknown|
|Cambridge University Digital Library|`fallback`。shelfmark/CUDL URLが主|unknown；Scriptoria側OCRは可|IIIFマニフェスト経由|可（ページ処理）|IIIF統合は確認。その他はunknown|
|e-codices|`direct` with search handler。複合ID/URLが主|unknown；Scriptoria側OCRは可|IIIFマニフェスト経由|可（ページ処理）|IIIF統合は確認。その他はunknown|
|Biblioteca Estense (Modena)|`search_first`。Jarvisの `findBySgttOrAutnOrPressmark`（短タイトル・著者・請求記号）をScriptoriaが利用すると公式文書に明記|機関OCR APIはunknown；Scriptoria側OCRは可|JarvisのネイティブIIIF v2/v3、Image API level-2（タイル・ズーム・リスケール）|マニフェストのページ単位取得を前提に可|IIIF Presentation v2/v3とImage API level-2を公式文書で明記。SRU/OAI-PMHはunknown|
|Harvard|`fallback`。DRSを含むアイテムURLが主|unknown；Scriptoria側OCRは可|IIIFマニフェスト/URL解決|ページ処理可|IIIF統合は確認。Presentation/Imageの詳細、全文、SRU/OAI-PMHはunknown|
|Library of Congress|`fallback`。`loc.gov/item/...` URLが主|unknown；Scriptoria側OCRは可|IIIFマニフェスト/公開アイテムURLから取得|ページ処理可|IIIF統合は確認。LOC APIの全文/OAI/SRUについてScriptoria連携はunknown|
|Internet Archive|`search_first`。アイテムURL/テキスト検索|機関OCR APIはunknown；Scriptoria側OCRは可|アイテム/IIIF経由、ネイティブPDF優先の可能性|ページ処理可|IIIF統合は確認。機関の全文検索/OAI-PMH等をScriptoriaが使うかはunknown|
|Internet Culturale (ICCU, BETA)|`search_first`。テキスト、OAI ID、magparser/viewresource URL。公式文書は不完全レコード・画像品質を注意|機関OCR APIはunknown；Scriptoria側OCRは可|上流/ゲートウェイのIIIFまたはURL経由。ただし品質・完全性は不安定|ページ処理可だが上流依存|IIIF連携の統合は確認。ICCUのOAI-PMH/SRU/全文/OCRをScriptoriaが直接使うかはunknown|
|Generic direct IIIF manifest|検索なし（`direct`）。正確なマニフェストURLのみ|機関OCR APIは該当なし。Scriptoria側OCRは可|IIIFマニフェストから画像取得|canvas/page相当のページ処理可|IIIF直接入力を確認。SRU/OAI-PMHは対象外|

### API仕様についての境界

- Scriptoriaの公開資料は「IIIFマニフェストを解決し、画像を取得してローカル作業する」ことを主に規定する。共通MCPや公開REST APIのエンドポイント仕様、JSON Schema、認証、ページ単位レスポンス契約は確認できない。
- `providers.py`の実装は各プロバイダにresolverと、存在する場合のsearch strategy/search handlerを割り当てる設計である。列挙されたsearch strategyは archive_org、bodleian、cambridge、ecodices、estense、gallica、harvard、heidelberg、institut、internetculturale、loc、vatican。これはScriptoria内部のアダプタ名であり、各機関の公式プロトコル名ではない。[6]
- 文書上、全文検索に相当するのはプロバイダ固有のfree-text discoveryである。OCR全文を検索インデックス化する機能、外部機関のOCR全文API、検索結果の恒久URL/ページアンカーは確認できず、`unknown` とする。
- 画像取得はIIIF画像取得またはネイティブPDF取得が中心。機関ごとの認証要件、利用規約、robots/rate limit、IIIF Presentation 2/3やImage APIレベルの完全な実測一覧は未確認。

## 4. 標準規格・API

確認できた標準はIIIF Presentation/Image系である。特にEstenseについては公式Scriptoria文書がPresentation v2・v3とImage API level-2を明記する。一般プロバイダについては「IIIFマニフェストURLを直接入力できる」「IIIFプロバイダ」とする実装・文書上の確認に留まり、各機関の採用バージョンを推測してはいけない。

SRU、OAI-PMH、OpenAPI、MCP Tools仕様の実装は、対象リポジトリのREADME、公式Docs、provider registry、CLI docs、MCP Registry検索で確認できなかった。これは各機関がそれらを提供していないことの証明ではなく、Scriptoriaの統合対象として未確認という意味である。

## 5. ライセンス、配布、保守

- GitHub表示と`pyproject.toml`はGPL-3.0-or-later。LICENSE本文はGNU GPL version 3（2007-06-29）である。再利用・組込み時はGPLのコピーレフト、ソース提供、変更表示等を法務確認すべき。[1][3][7]
- Python 3.10以上。配布メタデータのproject nameは `universal-iiif`、versionはリポジトリmainの`pyproject.toml`では0.27.2だが、GitHubの最新releaseはv0.30.1（2026-05-20）である。mainとタグ付けリリースのメタデータに差があるため、採用時はタグ固定・依存ロックが必要。[3][8]
- GitHub repositoryは2026-01-15作成、確認時に350 commits、29 open issues。最終確認できたコミットとv0.30.1は2026-05-20で、同日にCI/Docs CI/Release成功記録がある。[1][8][9]
- SECURITY.mdは最新リリースのみをサポートし、GitHub Private Vulnerability Reporting、72時間以内のacknowledgement、7日以内の初期評価、通常90日程度の協調開示を掲げる。[10]
- PyPI検索では `universal-iiif` の明確な該当プロジェクトを確認できず、公式配布経路としてGitHub clone + `pip install -e .` がREADMEに記載される。npm検索でもScriptoria/universal-iiifの明確なパッケージは確認できなかった。[1][11][12]
- Official MCP Registry API検索 `search=scriptoria` は空配列。ScriptoriaがMCPサーバとして登録されている事実は確認できない。[13]

## 6. コード品質・セキュリティ上の注意

確認できた品質面は、pytest、ruff、pyright、Codecovバッジ/coverage、GitHub Actions（CI、Docs CI、Release、PR Governance等）、Python 3.10+の型・Lint設定、テストマーカー（unit/integration/slow）である。ruff設定にはBandit系`S`、複雑度C90、命名・docstring等が含まれる一方、pyrightは`basic`、テストでは一部ルールを除外している。これは一定の静的検査・CIがあることを示すが、包括的な第三者監査、依存脆弱性ゼロ、実運用のセキュリティ保証を意味しない。[1][3][9]

セキュリティ設計として、設定ルート配下のパス封じ込め（resolve/is_relative_to）、ファイル名サニタイズ、SQLパラメータ化、入力境界での検証、中央HTTPクライアント、制限的CORS、秘密情報を環境/設定に置く方針が文書化されている。外部URLからのダウンロード、AI APIキー、ローカルSQLite、リモート/ローカル画像の混在は攻撃・漏えい・容量・利用規約リスクを残すため、Global Library MCPへ機能を取り込む場合はURL allowlist、SSRF防止、MIME/サイズ/ページ数上限、タイムアウト、レート制御、保存領域隔離、供給網スキャンを別途設計する必要がある。[4][14]

## 7. 再利用可能性

再利用候補は、(a) provider registry/resolverの概念とプロバイダ別search strategy、(b) IIIFマニフェストからの画像・ページ取得とPDFフォールバック、(c)中央HTTPのリトライ/バックオフ/レートポリシー、(d)ページ単位OCR/転写状態、(e)ローカル保管庫・ジョブ再開・ステージングである。特に、同一レジストリをWebとCLIで共有する設計はGlobal Library MCPのコネクタ層の参考になる。[4][6]

ただし、GPL-3.0-or-laterのため、Global Library MCP本体へコードを直接取り込む場合はライセンス互換性と派生物要件を先に確認する。安全な初期案は、Scriptoriaを独立プロセス/外部コネクタとして扱い、必要なIIIF/HTTP挙動を仕様化して新規実装するか、GPLの法務条件を満たす分離統合にすることである。依存するPyPI/npm成果物、各機関の利用規約、OCRエンジンの個別ライセンスも未精査である。

## 8. Global Library MCPとの重複・差分

**重複:** 複数図書館の入口統一、機関別識別子からマニフェストへの解決、free-text discovery、IIIF画像/ページ取得、OCR・転写補助、ページ単位の状態管理。

**Scriptoria固有:** 人間向けのローカルWebワークベンチ、Mirador、SQLiteのLibrary、ローカル-firstダウンロード、ページ修復、PDF/画像出力、CLI、プロバイダ別の閲覧/ネットワーク方針。

**Global Library MCP側で補うべき差分:** MCP Tools/Resourcesの正式契約、機関横断の統一検索結果とページ取得スキーマ、全文検索とOCR検索の区別、IIIF Presentation/Imageのバージョン差異の正規化、SRU/OAI-PMH等の収集プロトコル、認証・利用規約・レート制御、エビデンスURL/ページアンカー、サーバー型の権限・監査・キャッシュ。

## 9. 未確認事項（unknown）

1. Scriptoriaが各機関の公式SRUまたはOAI-PMH endpointを呼び出すか、またはそれらを完全に未使用か。
2. 各機関の全文検索がOCR全文検索なのか、書誌メタデータ検索だけなのか。Scriptoria内でOCR結果を横断検索できるか。
3. 各機関のOCR API、OCR XML/ALTO/TEI/IIIF Annotation取得、全文ダウンロードの直接対応。
4. Vaticana、Gallica、Institut de France、Bodleian、Heidelberg、Cambridge、e-codices、Harvard、LOC、Internet Archive、ICCUのIIIF Presentation/Image APIの正確なバージョン、level、認証、ページ取得制約。
5. ScriptoriaをPyPI/npmから直接インストールできる公式公開版の有無（確認時の検索結果では明確な該当なし）。
6. 外部セキュリティ監査、SBOM、依存脆弱性の現在値、リリースタグとmainの差分の理由。
7. 29件のIssueのうち未解決のものが本番利用を阻害するか。Issueの全件トリアージは本調査の範囲外。
8. Global Library MCPの既存実装詳細との機能重複率。親プロジェクト側の仕様・実装を本調査では参照していないため、差分は公開Scriptoria側から比較可能な範囲に限定した。

## References

[1]: https://github.com/nikazzio/scriptoria "nikazzio/scriptoria GitHub repository and README"
[2]: https://nikazzio.github.io/scriptoria/reference/provider-support "Scriptoria Provider Support"
[3]: https://github.com/nikazzio/scriptoria/blob/main/pyproject.toml "Scriptoria pyproject.toml"
[4]: https://nikazzio.github.io/scriptoria/explanation/architecture "Scriptoria Architecture Summary"
[5]: https://nikazzio.github.io/scriptoria/reference/cli "Scriptoria CLI Reference"
[6]: https://raw.githubusercontent.com/nikazzio/scriptoria/main/src/universal_iiif_core/providers.py "Scriptoria provider registry source"
[7]: https://github.com/nikazzio/scriptoria/blob/main/LICENSE "GNU GPL v3 license in Scriptoria"
[8]: https://github.com/nikazzio/scriptoria/releases "Scriptoria GitHub Releases"
[9]: https://github.com/nikazzio/scriptoria/actions "Scriptoria GitHub Actions"
[10]: https://github.com/nikazzio/scriptoria/blob/main/SECURITY.md "Scriptoria Security Policy"
[11]: https://pypi.org/search/?q=universal-iiif "PyPI search for universal-iiif"
[12]: https://www.npmjs.com/search?q=scriptoria%20universal-iiif "npm search for Scriptoria universal-iiif"
[13]: https://registry.modelcontextprotocol.io/v0.1/servers?search=scriptoria "Official MCP Registry search for Scriptoria"
[14]: https://nikazzio.github.io/scriptoria/explanation/security-and-path-safety "Scriptoria Security and Path Safety"
