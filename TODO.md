# TODO

## 完了したv1.0コア条件

- [x] Pythonと公式MCP SDKを用いた共通MCPサーバーを起動できる。
- [x] 図書館アダプターインターフェース、共通書誌データモデル、図書館レジストリを実装する。
- [x] API通信にタイムアウト、リトライ、レート制御、キャッシュ、構造化エラーを適用する。
- [x] NDLのBook/Page API、OCR座標復元、コマ番号、IIIF画像URLを実装し、実APIで対応関係を検証する。
- [x] NDLとInternet Archiveの2機関ライブ横断検索を成功させる。
- [x] 複数図書館の並列検索、重複資料の簡易排除、部分障害時の結果返却を実装する。
- [x] 機関固有ID、提供元、原本URL、取得日時、rightsを検索結果に保持する。
- [x] APIキーなしで通常検索、出典表示、原本URLへの遷移をWeb UIから利用できる。
- [x] 日本語・英語のUI、レスポンシブな検索画面、図書館フィルター、Internet Archive選択を提供する。
- [x] LLMプロバイダー交換層、根拠付きJSON回答、原文・翻訳・制限の分離を実装する。LLMは明示的オプトイン制。
- [x] DDB、Europeana、Internet Archiveアダプターを追加する。未設定資格情報は成功扱いにしない。
- [x] 単体テスト、fixtureを使ったアダプター契約テスト、部分障害、NDL OCR復元、LLMモックテストを追加する。
- [x] README、README.ja、Apache-2.0 LICENSE、SECURITY、CI、Docker設定を整備する。

## ライブ検証・環境依存の未完了項目

- [ ] LoCライブ検索を成功させる。公式APIの利用条件は確認済みだが、現環境はCloudflare challenge付き403。再試行で回避せず、許可された別ネットワークまたは機関側条件の確認後に再検証する。
- [ ] Gallicaライブ検索を成功させる。BnF公式告知でSRU・IIIF・Document APIへの一時的制限が継続中。制限解除後に再検証する。
- [x] DDB Search APIの正規パスでライブ検索を検証する。公式ドキュメント上はAPIキーを取得し、`DDB_API_KEY`をBearerで設定することを本番条件とする。
- [ ] Europeanaライブ検索を`EUROPEANA_API_KEY`の提供後に検証する。
- [ ] LLM実プロバイダー呼び出し。費用・資格情報のため、`LLM_ENABLED=true`の明示承認なしでは実行しない。
- [x] Docker実ビルドと起動。GitHub Actions run 44378302864でDocker build、起動、health checkを成功させた。ローカルDocker CLIは未導入。
- [x] Playwright Chromium E2E。Dockerコンテナを対象に検索カード表示とLLM無効時のUIを検証した。
- [ ] 本番Web公開。公開デプロイは別途承認が必要。
