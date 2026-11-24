# Global Library MCP

Global Library MCPは、公式の図書館・デジタルアーカイブAPIに対する「根拠優先」のMCPゲートウェイです。複数機関の目録を横断検索し、実際のOCRページ本文を読み、同一性照合に合格したページだけを根拠に回答します。引用はすべて資料ID・ページID・IIIF原本画像まで解決できます。検証できないものは隠さず「未確認」として表示し、引用には使いません。

アダプターは国立国会図書館（NDL）、米国議会図書館、Internet Archive、Gallica/BnF、DDB、Europeanaに実装済みです。NDLは書誌検索→書籍内検索→ページOCR→IIIF原本検証までの全経路に対応します。機関ごとのライブ状況は [libraries.yaml](libraries.yaml) と [docs/implementation-status.md](docs/implementation-status.md) に記録しています。

## クイックスタート

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

`http://127.0.0.1:8000` を開いてください。MCPサーバー（stdio）は `global-library-mcp mcp` で起動し、MCPクライアントにそのコマンドを設定します。

Web UIのエンドポイント: `/health`、`/api/libraries`、`/api/search?q=...`、`/api/evidence?q=...`、`/api/answer?q=...`、`/api/verify?library=ndl&id=...`、`/api/compare?docs=ndl:994120;ndl:1018770&aspects=...`、`/api/document`、`/api/page`。MCPツール: `list_libraries`、`get_library_capabilities`、`search_catalog`、`search_across_libraries`、`get_document`、`search_in_document`、`get_page_text`、`get_page_image`、`get_citation`、`get_rights`、`get_verified_evidence`、`verify_original_page`、`research_question`、`compare_documents`。

## 回答と根拠

`research_question`（Web UIでは「AI回答」ボタン）は根拠パイプラインを実行します: 書誌検索 → 書籍内ページ検索 → 同一性照合とOCR品質ゲート付きのページOCR取得 → 回答生成 → 引用のホワイトリスト検証。検証済みOCRページが1件も集まらなければ結果は `insufficient_evidence` となり、回答は生成されません。書誌情報だけを根拠に回答することはありません。回答には主張ごとの根拠スクリーニングも付き、`compare_documents` は2つの文献を検証済みページだけで観点別に比較します。Internet Archiveの資料もNDLと同等のページ根拠経路（djvu.xmlのleaf単位OCR）を持ち、アクセス制限つき資料は取得を拒否します。

AI回答はデフォルト無効で、LLMなしでも全機能が動作します。OpenAI互換プロバイダを使う場合は `LLM_ENABLED=true`、`LLM_API_KEY`、任意で `LLM_API_BASE`/`LLM_MODEL` を設定してください。オフラインのデモやテストには `LLM_PROVIDER=mock`（最初の根拠ページから決定的に回答するモック）も使えます。検索・根拠取得・原本リンクにLLMキーは不要です。

## 根拠と制限

検索は資料発見のため、根拠パイプラインは引用のためです。引用・再配布の前に原本ページと資料単位の権利表示を確認してください。権利をソースコードのライセンスから推定することはしません。不明な能力は `unknown` のままにします。詳細は [実装状況](docs/implementation-status.md)、[根拠検証](docs/evidence-verification.md)、[コードレビュー](docs/code-review.md)、[API調査](docs/api-research.md)、[図書館レジストリ](libraries.yaml) を参照してください。

CIはPythonテスト、Dockerビルド/起動、Playwright Chromium E2E、Docker経由のAPIスモークテストを含みます。外部APIの成否は提供機関と資格情報に依存するため、機関ごとのライブ結果は推定せず日付つきでレジストリに記録します。
