# MCPクライアント接続ガイド / MCP client guide

Global Library MCP は stdio 型の MCP サーバーです
（起動コマンド：`global-library-mcp mcp`）。

**検証状況の区別**：
- **実接続検証済み**：
  - 公式Python SDKクライアント（MCPプロトコルレベル：
    initialize／ツール一覧15件／実ツール呼び出し）
  - **Claude Code**（2026-11-25）：`claude mcp add` で登録し、
    アプリのヘルスチェックで `✔ Connected` を確認。アプリ内
    セッションからのツール実行は Anthropic ログインが必要なため
    本環境では未実施。
  - 公式Python SDKクライアントから `research_materials`
    （quick／standard）、`search_catalog` を実際に呼び出し、
    正常な応答を確認（2026-11-25、b3.1修正後）。
- **設定例のみ（未検証）**：Claude Desktop、Cursor、
  Google Antigravity — 各アプリ上での接続確認は行っていません。
  動作を保証するものではありません。

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
OpenAI公式ドキュメント（https://platform.openai.com/docs/guides/developer-mode）
によれば、ChatGPT が接続できるのは Server URL で指定するリモート
MCP サーバー（Plugins のカスタムMCPサーバー）で、対応プロトコルは
SSE と streaming HTTP のみです。stdio は対象外です。

そのため本サーバーを ChatGPT から使うには、次のいずれかが必要です。

1. サーバーを Streamable HTTP トランスポートで公開ホスティングする
   （本リリースにはリモート公開機能は含まれていません）
2. OpenAI の Secure MCP Tunnel でローカルサーバーを中継する
   （公式に用意された方式ですが、本プロジェクトでは未検証であり、
   動作を保証しません）

現時点では ChatGPT からの直接接続は **未対応** です。

## 利用できるツール（15件）

`search_catalog`、`research_materials`、`get_page_text`、
`verify_original_page`、`compare_documents` ほか。
AI回答系ツールは Research Beta の初期設定では無効です。

## b4追補：Streamable HTTPと検証状況（2026-11-25）

- **Streamable HTTP（ローカル）実装済み・実接続検証済み**:
  `global-library-mcp mcp --transport streamable-http --host 127.0.0.1 --port 8001`
  で起動し、公式Python SDKクライアントとMCP Inspector CLIの両方から
  initialize／tools/list／tools/callを確認した。stdioと同じ
  LibraryServiceを共有する。初期バインドは127.0.0.1で、DNS
  リバインディング対策（Host/Origin許可リスト）が有効。
  認証機能は内蔵されていないため、外部公開には使わないこと。
- **読み取り専用プロファイル**: `--profile research` で実験的
  ツール `research_question` を公開対象から外す（14ツール）。
  全ツールに読み取り専用アノテーション（readOnlyHint）が付いた。
- **MCP Inspector**: CLIモードで検証済み（stdioのtools/list・
  tools/call、HTTPのtools/list）。
- **ChatGPT**: 接続準備は `docs/chatgpt-connectivity.md` に分離
  した。Secure MCP Tunnel方式なら既存のstdioサーバーをそのまま
  使える（tunnel-clientがstdioコマンドを中継できる）ことが公式
  文書で確認できたが、トンネルの作成自体は未実施であり、
  **ChatGPT接続は引き続き未対応（準備のみ）**。
- **Google Antigravity**: stdioの設定例のみ（未検証）。

## b6: multilingual options on research_materials

`research_materials` accepts optional `languages`,
`expand_multilingual`, `expand_historical`, `author`,
`title`, `year_from`, `year_to` and `ocr_required`. The
response gains a `discovery` block (query language, every
variant used with kind/relation/reason, skipped candidates
with reasons, ambiguous authors) and per-material
`matched_variant`, `discovery_reasons`, `work_link`,
`author_link`, `duplicate_group` and, for DDB records,
`bsb_handoff`. Tool counts are unchanged (15 full / 14
research profile).
