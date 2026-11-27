# Global Library MCP

Global Library MCP は、公的図書館・デジタルアーカイブの
API を横断する研究資料検索サービス／MCP ゲートウェイです。
機関を横断して書誌を検索し、ページ単位の OCR を読み、
質問に関係する箇所を抽出して、すべての抜粋に原本ページ
画像（IIIF）へのリンクを付け、利用者自身が検証できるよう
にします。検索結果は「回答の証明」ではなく、利用者が調査
するための研究資料として表示されます。

**Research Beta が製品本体**です。資料検索・OCR・原本閲覧・
文献比較・引用コピーが、**LLM なし・有料 API なし**で動作
します。AI 回答機能は分離された**実験トラック**であり、
初期設定では無効です。

## 対応図書館と実装状態

状態の定義：**動作確認済み**＝実環境で一貫動作を確認、
**実装済み**＝アダプタあり・実確認は部分的、**未検証**＝
コードはあるが当ネットワークから確認できていない、
**調査中**＝レジストリ記録のみでアダプタなし。
詳細は [libraries.yaml](libraries.yaml) と
[docs/implementation-status.md](docs/implementation-status.md)。

| 機関 | 状態 | 検索 | ページOCR | 原本画像 |
|---|---|---|---|---|
| 国立国会図書館（NDL） | 動作確認済み | ○ | ○ | ○（IIIF） |
| Internet Archive | 動作確認済み | ○ | ○（公開資料） | ○ |
| Library of Congress | 実装済み | ○ | 新聞のみ（Chronicling America、検証済み） | ○ |
| BSB / MDZ（バイエルン州立図書館） | 動作確認済み | ID指定（公式検索APIなし） | ○（hOCR） | ○（IIIF） |
| e-rara（ETHライブラリ） | 実装済み | ID指定（OAI-PMH） | × | × |
| Gallica / BnF | 未検証（当ネットワークで上流403） | ○ | ○ | ○（IIIF） |
| DDB | 実装済み | ○（集約） | × | リンク |
| Europeana | 実装済み | ○（集約） | × | リンク |
| KB / Delpher（オランダ） | 動作確認済み（検索・記事OCR取得、2026-11-26実地。ページ同一性は未確認＝OCRは記事単位でタイトル対応のみ） | ○（SRU） | 記事OCR（resolver） | 未検証（:image は実地で404） |
| Japan Search（NDL） | 動作確認済み（検索・詳細、2026-11-26実地） | ○（SPARQL） | ×（集約） | × |
| Finna（フィンランド） | 実装済み・当ネットワーク未検証（上流ボットチェック403） | ○ | ×（基盤） | × |
| フィンランド国立図書館 Digi | 実装済み・実地検証未達成（最終レビューの再検証でOAIはプロトコルレベルでは応答。実資料の検証は未達成） | ID指定（Finna引き継ぎ経由） | ○（ALTO） | ○ |
| DPLA（米国） | 実装済み・認証必須（キー未発行） | ○（APIキー時） | ×（集約） | × |
| その他16機関 | 調査中 | - | - | - |

「世界中のすべての図書館に対応」しているわけではありま
せん。対応範囲は上表がすべてです。

### 多言語ディスカバリ（1.0.0b6）

自分の言語で質問すると、ローカル辞書が検索語を他言語の主題語・
著者名表記・原題と翻訳題・歴史的表記（旧字体、歴史的仮名遣い、
ウムラウトやアクセントの別表記）へ展開し、資料がありそうな
図書館へ振り分け、展開の理由をすべて表示します。資料には
作品・著者の候補リンク（同一性が確認できない場合はその旨の
拒否理由つき）が付き、DDBの資料は公式URNからBSBの原本へ
引き継げ、LoCの新聞はLCCNから号を発見できます。展開は
資料発見専用で、根拠採用条件は従来どおり、翻訳やLLMは
使いません。詳細は docs/b6-multilingual-research.md と
docs/b6-evaluation.md を参照してください。最終レビュー
（docs/b6-final-review.md）では、構造化条件をQuickを含む
全モードで適用し、フィルターをOCR取得の前に移し、著者・
作品・版の識別とDDB→BSB識別子検証を厳密化し、評価を
シミュレーションと実サービス・フィクスチャ評価に分離
しました。

### 研究ワークスペース（1.0.0b7）

検索結果をローカルの研究ワークスペースへつなげられます。
プロジェクト、保存資料、出所情報付きの引用と再検証、
研究ノート、任意保存の検索履歴、比較結果の保存、タグと
コレクションを、OSのユーザーデータ領域にあるSQLite
データベースに保存します（`GLM_WORKSPACE_PATH`で変更可）。
有効化は `global-library-mcp web --workspace`。
ワークスペース有効時はループバック接続限定で、それ以外の
バインドは起動時に拒否されます。出力形式はBibTeX、RIS、
CSL JSON、Markdownレポート、移行用JSONプロジェクト形式、
オンラインバックアップ・復元に対応します。権利は保守的に
扱い、OCR全文と画像バイト列は保存せず、抜粋の保存・出力は
権利区分が許可する場合に限ります。MCPツールは従来どおりで、
ワークスペースにはアクセスしません。詳細は
docs/b7-research-workspace.md と
docs/workspace-user-guide.md を参照してください。
最終レビューで引用と資料の同一性検証、fail-closedな権利ポリシー、インポート・復元の安全性、セッション安全性を強化しました。詳細は docs/b7-final-review.md を参照してください。

### Global Coverage II（1.0.0b8）

新規アダプター5件はいずれもオプトインで、既定検索は新規
ホストへ一切アクセスしません。Finna（フィンランドの横断
検索。提供元・所蔵機関・Finnaレコードを区別し、メタデータ
CC0と資料の権利を混同しない）、フィンランド国立図書館Digi
（OAI同一性・ALTOページOCR・構造的ページ同一性。Finnaから
検証済み引き継ぎで到達）、KB / Delpher（オランダ歴史新聞、
SRU＋resolver OCR、検索と記事OCR取得を実地確認。OCR単位は
記事でありページ同一性は厳密には未検証）、Japan
Search（SPARQL検索・JSON-LD詳細、アクセス制限を逐語表示、
NDL引き継ぎ候補）、DPLA（認証待ち実装。キーは発行してお
らず、呼び出しは authentication_required を返す）。
多言語展開辞書にフィンランド語・スウェーデン語・オランダ
語を追加。ワークスペースには権利の信頼モデルを導入し、
インポート／復元された権利申告は制限方向にのみ働きます。
実地検証の状態は docs/b8-live-verification.md に正直に
記録しています（FinnaとDigiは開発ネットワークから到達
できずフィクスチャ検証のみ）。詳細は
docs/b8-global-coverage-ii.md。

### External MCP Readiness（1.0.0b9）

外部AIクライアント向けの専用プロファイル
**external-research** を新設しました。専用の FastMCP
サーバーが、allowlist で承認された読み取り専用ツール
9件（OpenAI 形式の search/fetch、図書館一覧・能力、権利、
原典検証、ポリシーでゲートされた抜粋、外部向け資料・
比較プロジェクション）のみを公開します。OAuth 2.1
トークン検証とツール別スコープ、サーバー側の利用者同意、
利用者別予算と期限、そしてワークスペースの保存ポリシー
から独立した**外部送信権利ポリシー**（OCR全文と原本画像
バイナリは送信せず、抜粋は既定無効）を備えます。
Research Workspace には構造的に到達できません。
ChatGPT 接続（Secure MCP Tunnel）の手順書は
docs/chatgpt-connection.ja.md に用意しましたが、**トンネルは
未作成で ChatGPT へは未接続**です。公式プラン調査
（2026-11-27）では、フルMCPは Business / Enterprise・Edu、
読み取り/取得のカスタム接続は Pro に記載があり、Plus には
公式経路が確認できませんでした。詳細は
docs/b9-external-mcp-readiness.md。

## クイックスタート（ローカル）

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
global-library-mcp web --port 8000
```

`http://127.0.0.1:8000` を開きます（日本語／英語 UI）。

## Docker

```bash
docker compose up --build
```

非 root ユーザーで動作し、同じ Web UI と API を
ポート 8000 で提供します。

## MCP 接続

`global-library-mcp mcp`（stdio）を MCP クライアントに
設定します。ローカル向けの Streamable HTTP も利用できます
（`global-library-mcp mcp --transport streamable-http`、
127.0.0.1 にバインド）。外部AIクライアント向けには
`--profile research` で読み取り専用ツール群を公開できます。
詳細は `docs/mcp-clients.md` を参照してください。主要ツール：`research_materials`（Beta の
主機能）、`search_across_libraries`、`search_catalog`、
`get_document`、`search_in_document`、`get_page_text`、
`get_page_image`、`get_citation`、`get_rights`、
`get_verified_evidence`、`verify_original_page`、
`compare_documents`、および実験機能の `research_question`。

## AI 機能（実験）

AI 回答は**初期設定で無効**であり、Beta は AI なしで
完全に動作します。研究用に用意されているもの：

- 主張単位の検証：引用した特定の箇所に対して「支持」
  と判定された主張だけが公開されます。不確実・未検証の
  主張は保留され、矛盾する主張は別表示されます
  （Phase 10-B）。
- 交換可能な主張検証器（語彙／NLI／LLM 判定／ハイブリッド）
  をシャドーモードで比較。LLM が自分の主張を自分で支持
  しても独立検証とはみなしません。
- 抽出型回答（原文引用）と生成型回答を分けて評価。
- 実測：初回の承認済み実 LLM 評価（xAI grok-4.3、20問）
  では LLM の回答成功 4/20 に対し、決定的モックは同一
  条件下で 12/20 でした。律速はモデルではなく主張検証
  です。詳細：[docs/evaluation-phase9.md](docs/evaluation-phase9.md)、
  [docs/phase10-llm-audit.md](docs/phase10-llm-audit.md)、
  [docs/phase10-experiment-plan.md](docs/phase10-experiment-plan.md)。

実験する場合は `LLM_ENABLED=true`、`LLM_API_KEY`、
任意で `LLM_API_BASE`／`LLM_MODEL`（OpenAI 互換）を
設定するか、決定的デモ用の `LLM_PROVIDER=mock`
（UI にデモと明示）を使います。有料評価には実験計画書の
予算承認手続きが別途必要で、自己承認用のフラグは
ありません。

## 権利と出典

権利は資料ごとに各機関の表示をそのまま示します。権利が
不明な資料を再配布可能とは表示しません。Beta の基本は
短い抜粋と原本へのリンクです。貸出限定などアクセス制限
のある資料は取得しません。調査結果：
[docs/phase10-library-terms.md](docs/phase10-library-terms.md)。

## プライバシーとセキュリティ

検索語は選択した図書館 API にのみ送られます。アカウント
や個人情報は不要で、Beta 構成ではいかなる LLM にも利用者
データは送られません（トラップルートのテストで、Beta の
経路が LLM を一切呼ばないことを証明しています）。エラー
情報はサニタイズされ、キーは環境変数からのみ読み、記録
しません。監査：
[docs/phase9-security-audit.md](docs/phase9-security-audit.md)、
[docs/phase10-security-audit.md](docs/phase10-security-audit.md)。

## 既知の制約

- 検索品質は各図書館の索引と OCR に依存します。検索予算
  （初期設定 Standard 25）内で根拠が見つからなかった場合
  はその旨を表示しますが、それはその事実が存在しない
  ことを意味しません。
- 歴史資料の OCR には誤認識が含まれます。引用は OCR の
  逐語であり、真実は原本画像にあります。
- 意味的検証（NLI）は標準環境では利用できません
  （モデル重みなし）。推測せず `not_checked` と正直に
  報告します。
- Gallica はネットワークによっては到達できません
  （上流 403）。アクセス制御を回避することはしません。

## コントリビューション

Issue と Pull Request を歓迎します。根拠第一の規則
（解決可能な引用のない主張を出さない、権利を推測しない、
黙ってフォールバックしない）を守り、提出前に `pytest`
と Playwright（`npm run test:e2e`）を実行してください。

## ドキュメント

- クイックスタート: [docs/quickstart.md](docs/quickstart.md) /
  [docs/quickstart.en.md](docs/quickstart.en.md)
- MCPクライアントガイド: [docs/mcp-clients.md](docs/mcp-clients.md)
- リリースノート（1.0.0b2）: [docs/release-notes-1.0.0b2.md](docs/release-notes-1.0.0b2.md)

## ライセンス等

[LICENSE](LICENSE) と [SECURITY.md](SECURITY.md) を参照。
英語 README：[README.md](README.md)。
