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

- KB/Delpher検索→資料保存→ページ取得（verified_mapping=true）
  →引用保存。KBレコードに権利表明がないため、抜粋本文は保存
  されず参照（ハッシュ＋オフセット）のみが残ることを、画面表示
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
  KBのページOCRは live_page_verified 等）が返る。
- 研究ノートや保存データは外部MCPへ公開していない（従来どおり
  MCPはワークスペースへアクセスしない）。
