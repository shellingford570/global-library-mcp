# Global Library MCP

図書館・デジタルアーカイブの公式APIを、出典と権利情報を保持したまま横断検索するMCPサーバーです。現在はPhase 1の実装で、LoC、NDL、Gallicaの検索アダプターと、APIキー不要の最小Web UIを提供します。

## ローカル起動

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開きます。MCPクライアントからは `global-library-mcp mcp` をstdioサーバーとして起動します。

## 現在の制限

ライブAPIの利用条件、レート制限、資料単位の権利を尊重してください。検索結果は発見用であり、引用の前に原本ページと権利表示を確認してください。IIIFの詳細なページ解析、OCR座標の対応付け、AI回答生成、DDB/Europeana等の追加アダプターは未完了です。未確認情報は `unknown` として扱います。

詳細な調査は [`docs/prior-art.md`](docs/prior-art.md)、レジストリは [`libraries.yaml`](libraries.yaml) を参照してください。
