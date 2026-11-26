# Research Workspace・Web UI・MCP統合（b8 Stage 5）

## Research Workspace

新規機関は既存の共通経路（SearchResult／document payload／
ページpayload）に乗るため、資料保存・引用・再検証・ノート・
タグ・コレクション・検索履歴・比較・全エクスポート形式
（BibTeX／RIS／CSL JSON／Markdown／プレーンテキスト／JSON）が
そのまま利用できる。機関固有の分岐は追加していない。

実HTTP統合テスト（`tests/test_b8_workspace.py`、§23の構成：
実Webサーバー＋実WorkspaceApi＋実LibraryService＋実アダプター
＋実SQLite、上流のみフィクスチャ）で新規機関ジャーニーを固定：

- KB/Delpher検索→資料保存→ページ取得→引用保存。
  **最終レビューで変化**：KBの `verified_mapping` は常時
  false（タイトル対応のみでは同一性を認定しない）ため、
  引用は原典未検証の参照として保存される。KBレコードに
  権利表明がないため、抜粋本文は保存されず参照
  （ハッシュ＋オフセット）のみが残ることを、画面表示
  とDB行の両方で確認。
- Finna資料保存（横断プラットフォームのレコードも版を混同せず
  そのまま保存）。
- KB×Finna の文献比較保存（`semantic_status=not_checked` 維持、
  機関横断IDはStage 0の複合キーで分離）。
- BibTeX／プロジェクトJSONエクスポートに両機関が現れること。

横断プラットフォーム資料（Finna／DPLA／Japan Search）と提供元
資料は無条件に統合しない：保存は常に (library_id, record_id)
単位で、引き継ぎは候補として別に保持される。

## Web UI（§17）

- 検索対象チェックボックスに Finna／KB・Delpher／Japan Search／
  DPLA（APIキー必須と明記）を追加（いずれも既定オフ＝オプトイン）。
- 資料言語フィルターに fi／sv／nl を追加。
- ID指定ルックアップに Finna／フィンランド国立図書館Digi／
  KB・Delpher／Japan Search／DPLA を追加。
- 検索結果カードに資料言語を表示。
- 資料詳細カードに所蔵機関・提供機関・集約機関・プラット
  フォーム・アクセス制限・引き継ぎ候補件数を表示（payloadに
  ある場合のみ）。
- 機関ディレクトリ（レジストリ駆動）に認証要件（auth）を表示。
  国・地域・言語・能力別検証状態は従来どおりレジストリから表示
  されるため、新規機関も自動で載る。

Playwright：ワークスペース6ジャーニー（新規のKBジャーニーを
含む）がローカル実サーバー（KB実トークン使用）で全通過。
KBジャーニーはCIでも実トークンが得られれば実行され、得られ
なければスキップされる（従来のIAジャーニーと同じ方式）。
これとは別に、上記のpytest実HTTPジャーニーはCIワークス
ペースジョブのpytest一覧に追加され、スキップなしで常に実行
される。

## MCP（§18）

- ツール構成は不変：full 15／research 14（research_question拒否、
  readOnlyHint、data_notice、search_scope、stdio、ローカル
  Streamable HTTP）。`tests/test_b8_mcp.py` で固定。
- 新規機関は既存の共通ツールから `library_id` 指定で利用可能
  （search_catalog で Finna を引くテストで確認）。
- レジストリは31件。`list_libraries`／`get_library_capabilities`
  で新規機関とその検証状態（DPLAは authentication_required、
  KBのページOCRは live_article_ocr_fetched、ページ対応と
  原本画像は unverified）が返る。
- 研究ノートや保存データは外部MCPへ公開していない（従来どおり
  MCPはワークスペースへアクセスしない）。

## 最終レビュー：シナリオA〜Hの対応（2026-11-26、§24）

実HTTP統合（上流のみフィクスチャ）での対応付け：

| シナリオ | 実施場所 | 結果 |
|---|---|---|
| A Finna | シナリオ1（`eval/b8_scenarios.py`） | 検索・詳細・提供機関・保存・BibTeX 全段階成功（フィクスチャ） |
| B Digi | シナリオ2 | 厳格化後の基準でも整形式ALTOは検証成功。引用は権利のため参照のみ |
| C KB | 必須Playwright KBジャーニー＋`tests/test_b8_workspace.py` | 記事検索・記事OCR・記事単位の引用（参照のみ）。原本画像は未確認と表示 |
| D Japan Search | `tests/test_b8_stage4.py`＋候補段階の実地確認 | 検索・詳細・提供機関・権利・NDL引き継ぎ候補（候補は同一性確認と分離） |
| E 同一record_id | シナリオ8＋Stage 0回帰 | 混同なし |
| F 権利変更 | `tests/test_b7_final_review.py`／`test_b8_final_review.py` 実HTTP | 保存・再保存・表示・検索・出力を拒否 |
| G 未確認バックアップ | `tests/test_b8_final_review.py` 実HTTP | 復元後は全観測が restored_claim、再検証まで原文差し止め |
| H 復元失敗 | 同上（降格失敗の注入）＋検証失敗テスト | 元データを回復し読み書き継続 |

フィクスチャ結果と実地結果は混同しない。実地の範囲は
`docs/b8-live-verification.md` のとおり。
