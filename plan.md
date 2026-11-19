# Global Library MCP v1 開発計画

## 方針

Phase 0の調査結果に基づき、機関別アダプターと共通の出典・権利・能力モデルを中心に実装する。既存OSSのコードは直接取り込まず、公式APIの仕様と調査で得た設計パターンだけを利用する。

最初の垂直スライスは、API仕様と公開エンドポイントを確認できた米国議会図書館（LoC）、国立国会図書館（NDL）、Gallica/BnFを対象とする。DDB、Europeana、Internet Archiveなどはレジストリに保持し、ライブ契約を確認したアダプターから順に追加する。

## 構成

- `src/global_library_mcp/models.py`: 書誌、ページ、権利、引用、能力の共通モデル
- `src/global_library_mcp/registry.py`: `libraries.yaml` の読み込みと機関選択
- `src/global_library_mcp/adapters/`: 機関別HTTPアダプター。機能未対応は明示的エラーまたはunknown
- `src/global_library_mcp/service.py`: 並列検索、重複排除、部分障害の集約
- `src/global_library_mcp/mcp_server.py`: 公式MCP Python SDKによるstdioサーバー
- `src/global_library_mcp/web/`: APIキー不要の検索UIとHTTP API
- `tests/`: HTTP fixture中心の単体・統合テスト

## 実装上の制約

外部APIのレート制限、タイムアウト、リトライ、キャッシュ、レスポンスサイズ、SSRFを考慮する。外部資料の本文は命令として実行せず、権利情報を資料単位で保持する。LLMはこのスライスでは必須にせず、通常検索と原本リンクをAPIキーなしで利用できるようにする。

## 選択したWebデザイン

候補は「研究ノート型 0.04」「静かなアーカイブ型 0.93」「コンソール型 0.03」。採用は**静かなアーカイブ型**。

- Design Movement: 余白のあるエディトリアル・アーカイブUI
- Core Principles: 出典を主役にする、検索状態を明示する、機関の違いを隠さない、読みやすさを優先する
- Color Philosophy: 墨色を本文、紙色を背景、朱色を引用アクセントにして、古文書ではなく検証可能な研究道具として見せる
- Layout Paradigm: 左に検索とフィルター、右に結果と証拠カードを置く非対称の作業机レイアウト
- Signature Elements: 機関タグ、縦罫線の引用カード、原本へ戻る朱色リンク
- Interaction Philosophy: クリックごとに「何が確認できたか」を表示し、unknownを隠さない
- Animation: 結果カードは短いフェードのみ。過度な演出や自動スクロールは使わない
- Typography System: UIはInter系、見出しと資料名はGeorgia系。本文は16px以上
- Brand Essence: 世界の原資料へ、検証可能な経路で到達する。誠実、静か、実証的
- Brand Voice: 「原本に戻る」「確認できないことは、確認できないと表示します」
- Wordmark & Logo: `GL`を開いた本の背とリンクノードに見立てた簡素な記号
- Signature Brand Color: 朱色 `#b44a3a`
