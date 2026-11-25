# MCPクライアント接続ガイド / MCP client guide

Global Library MCP は stdio 型の MCP サーバーです
（起動コマンド：`global-library-mcp mcp`）。

**検証状況の区別**：本リポジトリの開発環境では、MCPプロトコル
レベルでの接続（initialize／ツール一覧15件／実ツール呼び出し）を
公式Python SDKクライアントで検証済みです。下記の各GUIクライアントは
**設定例のみ**で、各クライアント上での接続確認は行っていません。

The server speaks MCP over stdio (`global-library-mcp mcp`).
Protocol-level connection (initialize, 15 tools listed, a real tool
call) is verified with the official Python SDK client. The GUI
clients below are **configuration examples only** — not individually
connection-tested.

先にインストールを済ませてください
（[quickstart.md](quickstart.md)）。以下の例では、インストールした
仮想環境の絶対パスを使います。`which global-library-mcp`
（Windowsは `where global-library-mcp`）で確認できます。

## Claude Desktop

設定ファイル：

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "global-library": {
      "command": "/path/to/.venv/bin/global-library-mcp",
      "args": ["mcp"]
    }
  }
}
```

## Claude Code

```sh
claude mcp add global-library /path/to/.venv/bin/global-library-mcp mcp
```

## Cursor

`~/.cursor/mcp.json`（グローバル）またはプロジェクトの
`.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "global-library": {
      "command": "/path/to/.venv/bin/global-library-mcp",
      "args": ["mcp"]
    }
  }
}
```

## Google Antigravity

設定ファイル：`~/.gemini/config/mcp_config.json`
（ワークスペース単位は `.agents/mcp_config.json`）。
`mcpServers` の下に `command`（stdio）で登録します
（公式ドキュメント：https://antigravity.google/docs/ide/mcp/）。

```json
{
  "mcpServers": {
    "global-library": {
      "command": "/path/to/.venv/bin/global-library-mcp",
      "args": ["mcp"]
    }
  }
}
```

## その他の stdio 対応クライアント

`command` に上記の実行ファイル、`args` に `["mcp"]` を指定する
形式のクライアントであれば同じ設定で接続できます。

## ChatGPT について

ChatGPT はローカル stdio サーバーを直接登録できません。
ChatGPT が接続できるのは、公開 HTTPS で到達できるリモート MCP
サーバー（Plugins／開発者モードのカスタムコネクタ）のみです。

そのため本サーバーを ChatGPT から使うには、次のいずれかが必要です。

1. サーバーを Streamable HTTP トランスポートで公開ホスティングする
   （本リリースにはリモート公開機能は含まれていません）
2. OpenAI の Secure MCP Tunnel でローカルサーバーを中継する

現時点では ChatGPT からの直接接続は **未対応** です。

## 利用できるツール（15件）

`search_catalog`、`research_materials`、`get_page_text`、
`verify_original_page`、`compare_documents` ほか。
AI回答系ツールは Research Beta の初期設定では無効です。
