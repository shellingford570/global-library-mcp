# Global Library MCP

図書館・デジタルアーカイブの公式APIを、出典と権利情報を保持したまま横断検索するMCPサーバーです。NDLのBook/Page API・OCR座標・IIIF画像リンク、Internet Archive、LoC、Gallica、DDB、Europeanaのアダプターと、APIキー不要のWeb UIを提供します。

## ローカル起動

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開きます。MCPクライアントからは `global-library-mcp mcp` をstdioサーバーとして起動します。

## APIとAI回答

Web APIは `/api/search`、`/api/document`、`/api/page`、`/api/answer` を提供します。AI回答はデフォルト無効です。明示的に利用する場合だけ `LLM_ENABLED=true`、`LLM_API_KEY`、必要に応じて `LLM_API_BASE` と `LLM_MODEL` を設定してください。モデルは検索結果以外を根拠にせず、出典と制限を返します。

ライブAPIの利用条件、レート制限、資料単位の権利を尊重してください。検索結果は発見用であり、引用の前に原本ページと権利表示を確認してください。LoCとGallicaはこの環境で403となっており、成功扱いにしていません。未確認情報は `unknown` として扱います。

詳細な調査は [`docs/prior-art.md`](docs/prior-art.md)、レジストリは [`libraries.yaml`](libraries.yaml) を参照してください。
