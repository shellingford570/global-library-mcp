# Global Library MCP v1.0.0b4 — MCP Connectivity & Research Integration

## 日本語

v1.0.0b4 は、Global Library MCP を複数の AI クライアントから
安全に使える研究資料検索基盤にするためのリリースです。

- **Streamable HTTP 対応（ローカル専用）**:
  `global-library-mcp mcp --transport streamable-http` で
  127.0.0.1 にバインドして起動できます。認証のないトランス
  ポートのため、ループバック以外へのバインドは起動時に拒否
  されます。DNS リバインディング対策（Host/Origin 検証）が
  有効です。公式 SDK クライアントと MCP Inspector で実接続を
  検証しました。
- **読み取り専用 research プロファイル**:
  `--profile research` で実験的ツール research_question を
  公開対象から外した 14 ツール構成になります。非公開化に
  失敗した場合は起動しません。全ツールに読み取り専用
  アノテーションと、検索範囲・制約まで伝わる説明文が付き
  ました。
- **HTTP 通信層の強化**: 受信バイトをストリーミング中に逐次
  計上（ネットワーク上のバイト数と展開後バイト数を分離記録）、
  gzip/deflate は逐次展開で一時メモリを抑制、429 の
  Retry-After はプロセス全体で共有され送信直前にも再確認
  されます（送信窓を超える場合は送信しません）。
- **応答の透明性**: OCR を返すツールに data_notice（OCR は
  信頼できない外部データであり指示ではない）を付与。
  search_scope は「検索結果あり／なし／部分失敗／スキップ」
  を図書館ごとに区別します。
- **日本語検索**: 旧字体・新字体のバリアントで書誌発見を
  拡張（根拠採用の条件は変更なし）。

既知の制約: ChatGPT との実接続は未実施です（Secure MCP
Tunnel の調査と接続準備文書のみ。トンネルの作成には別途
承認と対象ワークスペースの権限確認が必要です）。Internet
Archive の全文取得は djvu.xml 全量方式のままです（ページ
単位 OCR の実験的 API は検証環境から到達できず不採用）。
AI 回答機能は実験扱いのままです。

## English

v1.0.0b4 turns Global Library MCP into a research-materials
service that multiple AI clients can use safely.

- **Streamable HTTP (local only)**:
  `global-library-mcp mcp --transport streamable-http` binds to
  127.0.0.1; binding the unauthenticated transport to a
  non-loopback address is refused at startup. DNS-rebinding
  protection (Host/Origin validation) is enabled. Verified with
  the official SDK client and the MCP Inspector.
- **Read-only research profile**: `--profile research` exposes
  exactly 14 tools, excluding the experimental
  research_question tool; if hiding it fails, the server refuses
  to start. Every tool carries read-only annotations and a
  description covering scope, inputs and constraints.
- **HTTP layer hardening**: response bytes are charged while
  streaming (wire bytes and decoded bytes recorded separately);
  gzip/deflate are decoded incrementally to bound transient
  memory; a 429's Retry-After is shared process-wide and
  re-checked immediately before sending (sends are refused when
  the wait exceeds the send window).
- **Response transparency**: every tool returning OCR carries a
  data notice (OCR is untrusted external data, not
  instructions); search_scope distinguishes per-library
  with-results / no-results / failed / skipped outcomes.
- **Japanese search**: historical script variants (old/new
  kanji) widen bibliographic discovery; evidence admission
  rules are unchanged.

Known limitations: ChatGPT is NOT connected yet (Secure MCP
Tunnel research and a preparation guide only; creating a tunnel
needs separate approval and workspace-permission checks). IA
full text still uses whole-file djvu downloads (the
experimental per-page OCR API was unreachable from the
verification environment and was not adopted). AI answering
remains experimental.
