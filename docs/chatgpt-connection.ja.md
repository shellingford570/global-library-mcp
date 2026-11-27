# Global Library MCP を ChatGPT へ接続する手順書

状態：**準備完了・接続未実施。** Secure MCP Tunnel は未作成、
ChatGPT への接続は未実施、APIキーは未発行です。リポジトリ外に
何かを作成する各手順には、末尾に列挙した個別承認が必要です。
公式情報の確認日：2026-11-27（出典は
docs/b9-openai-compatibility.md）。

## 1. 必要なもの

| 要件 | 内容 |
|---|---|
| ChatGPTプラン | フルMCPは Business または Enterprise/Edu。Pro は読み取り/取得のカスタム接続が可能。**Plus/Go/Free には公式のカスタムMCP接続経路が確認できていません（2026-11-27時点）** |
| 利用画面 | Web版（モバイルでは接続を作成できません） |
| OpenAI Platform | ChatGPTワークスペースと関連付けられた Platform 組織 |
| Platform権限 | Tunnels Read + Manage（作成）、Read + Use（実行・選択） |
| ワークスペース権限 | カスタムMCPサーバーの追加・公開には管理者/オーナー（Enterprise/Edu では RBAC 付与可） |
| APIキー | トンネル実行用キー（最小権限）。接続時にのみ作成し、本リポジトリには保存しません |
| ローカルマシン | tunnel-client と外部プロファイルを実行し、api.openai.com:443 への外向きHTTPSが可能であること |

## 2. 費用（2026-11-27確認。詳細は調査文書）

- ChatGPT契約：利用者単位・月額（公式料金ページで確認。金額は
  ページ側で動的に表示されるため転記しません）。
- Secure MCP Tunnel：公式ガイドにトンネル自体の別料金の記載は
  ありません。実行用キーは通常の Platform キーです。
- Responses API 経路（ChatGPT接続には不使用）：モデルトークン
  のみで、MCP呼び出し自体の追加料金はありません。
- 図書館API：無料。本プロジェクトはキーを発行していません。
- 公開HTTPS運用を選ぶ場合のホスティング・認証サービス費用は
  **未調査（unknown）** です（b9では公開サーバーを構築しないため）。

## 3. ローカルで外部プロファイル��起動する

```sh
# 認証設定（値はローカルで入力すること）：
export GLM_EXTERNAL_ISSUER="https://<認可サーバー>"
export GLM_EXTERNAL_AUDIENCE="http://127.0.0.1:8002/mcp"
export GLM_EXTERNAL_JWKS_URL="https://<認可サーバー>/.well-known/jwks.json"
export GLM_EXTERNAL_CONTINUATION_SECRET="<ローカルのランダム秘密>"
# 初回接続では抜粋送信を有効化しない（GLM_EXTERNAL_EXCERPTS は設定しない）

global-library-mcp doctor
global-library-mcp mcp --profile external-research \
  --transport streamable-http --host 127.0.0.1 --port 8002
```

サーバーはループバックのみに bind し、全呼び出しに有効な
Bearer トークンを要求します。認証設定が不完全な場合は起動を
拒否します（fail-closed）。Research Workspace はこのプロセスに
含まれず、外部へ公開されることはありません。

## 4. トンネルを作成する

docs/secure-mcp-tunnel.md の手順1〜5に従ってください
（Platform のトンネル設定 → tunnel-client の init/doctor/run）。
トンネルプロファイルの MCP コマンドは stdio 形式です：

```sh
global-library-mcp mcp --profile external-research --transport stdio
```

## 5. ChatGPT で接続する

ChatGPT Web → Plugins → + → Add custom MCP server → 名前を付け
（例：「Global Library MCP」）→ Connection: Tunnel → トンネルを
選択 → サーバーの OAuth 認証を設定 → リスク警告を確認 →
Create as a plugin → プラグインをインストール。

## 6. 初回利用前の確認

1. 発見されるツールが次の9件ちょうどであること：search、
   fetch、list_libraries、get_library_capabilities、
   get_document_rights、verify_original_reference、
   get_allowed_excerpt、research_materials_external、
   compare_documents_external。これ以外があれば切断すること。
2. 初回呼び出しは list_libraries。
3. 安全な初回検索はパブリックドメインの主題（例：ダーウィン）。
4. 権利制限のある資料が参照情報のみを返すことを確認する
   （これはポリシーが機能している証拠であり、エラーではない）。
5. ワークスペースに到達できないこと（プロジェクト、ノート、
   引用、バックアップ、ローカル履歴はどのツールからも見えない）。

## 7. トラブルシューティング

| 症状 | 想定原因 |
|---|---|
| トンネルが ChatGPT に表示されない | トンネルが対象ワークスペースに関連付けられていない、または作成者に Tunnels Read + Use がない |
| MCPサーバーが 401 を返す | トークンの issuer/audience 不一致、期限切れ、または認可サーバーが offline_access を広告せず更新に失敗 |
| ツール一覧が §6 と異なる | 承認後にサーバー側プロファイルが変化した。ChatGPT は凍結されたスナップショットを使うため、管理者による更新・再公開が必要 |
| 呼び出しがタイムアウトする | トンネルの期限はキュー時間込みで120秒。tunnel-client とローカルサーバーの健全性を保つこと |
| consent_required で全て拒否される | その利用者・データ区分へのサーバー側同意が未付与（仕様どおり。ツール引数では付与できない） |

## 8. 停止方法

docs/secure-mcp-tunnel.md（Stopping and revocation）と
docs/external-mcp-incident-response.md を参照。外部接続を止めても
ローカルの full/research プロファイルは動作し続けます。

## 9. 実接続の前に必要な個別承認

1. Secure MCP Tunnel の作成（Platform）。
2. トンネル実行用 API キーの発行。
3. ChatGPT プランとワークスペースの選択・契約。
4. OAuth 認可サーバーの登録（または外部 IdP の選定）と実利用者
   資格情報の発行。
5. ChatGPT へのプラグイン接続とワークスペースへの公開。
6. 抜粋送信の有効化（`GLM_EXTERNAL_EXCERPTS=1`）。書誌フェーズの
   検証後に、デプロイごとに個別承認。
7. トンネルではなく公開 HTTPS デプロイを選ぶこと。

## 10. OS について

tunnel-client と本サーバーは各ベンダーの文書上 Windows / macOS /
Linux に対応しますが、**本プロジェクトではいずれの OS も未検証**
です。ローカルサーバー自体は Linux で開発・テストされています。
