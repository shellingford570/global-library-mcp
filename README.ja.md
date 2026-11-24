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
| Library of Congress | 実装済み | ○ | 部分的 | ○ |
| Gallica / BnF | 未検証（当ネットワークで上流403） | ○ | ○ | ○（IIIF） |
| DDB | 実装済み | ○（集約） | × | リンク |
| Europeana | 実装済み | ○（集約） | × | リンク |
| その他20超の機関 | 調査中 | - | - | - |

「世界中のすべての図書館に対応」しているわけではありま
せん。対応範囲は上表がすべてです。

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
設定します。主要ツール：`research_materials`（Beta の
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

## ライセンス等

[LICENSE](LICENSE) と [SECURITY.md](SECURITY.md) を参照。
英語 README：[README.md](README.md)。
