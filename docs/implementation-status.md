# Phase 1 実装・検証状況

確認日: 2026-11-19

このブランチでは、Phase 0の調査成果物を基に、共通データモデル、図書館レジストリ、LoC・NDL・Gallicaのアダプター、横断検索サービス、公式MCP SDKによるstdioサーバー、APIキー不要のWeb UI、Docker、GitHub Actions、テストを実装した。

`pytest` は5件すべて通過した。Webサーバーの `/health` と `/manus-routes.json` はHTTP 200を返し、`/api/libraries` はレジストリを返す。NDL OpenSearchは実APIに接続し、2026-11-19の検証で「発電」に対して8件の書誌結果を取得した。

LoCとGallicaは実装上のHTTPクライアントまで完成しているが、この実行環境からのライブ呼び出しはCloudflare等の403（challenge or policy restriction）で拒否された。これは成功扱いにせず、Web APIは機関単位の部分エラーとして返す。別ネットワーク、公式の許可された認証・利用経路、または機関側のアクセス条件を確認した後に再検証が必要である。

未完了は、DDB・Europeana・Internet Archive等の追加アダプター、IIIF Manifestの詳細ページ解析、OCR座標の厳密な対応付け、LLMによる根拠付き回答、多言語翻訳、完全な受け入れテストA〜E、本番公開デプロイである。未実装機能を完成済みとは記載しない。
