# フィンランド国立図書館 Digi 統合（b8 Stage 3）

確認日：2026-11-26。調査詳細は `docs/b8-api-research.md` §2、
引き継ぎ規則は `docs/provider-handoff.md`。

## 対象とアクセスモデル

Digi（https://digi.kansalliskirjasto.fi）は国立図書館のデジタル
資料サービス（歴史的新聞・雑誌・古書・公的刊行物）。文書化された
インターフェース（ヘルシンキ大学研究Wiki「Interfaces of
digi.kansalliskirjasto.fi」、Digi利用条件へのリンク付き）に基づく：

| 機能 | 経路 |
|---|---|
| 書誌同一性（バインディング単位） | OAI-PMH GetRecord（qdc_finna）、識別子 `oai:digi.kansalliskirjasto.fi:<binding_id>` |
| ページOCR | `/<genre>/binding/<id>/page-<n>.xml`（ALTO）。プレーンテキスト版 `page-<n>.txt` |
| 原本画像 | `/<genre>/binding/<id>/image/<n>`（JPEG）。サムネイル `/thumbnail/<n>` |
| 全体 | `/<genre>/binding/<id>/pdf`、`/mets.xml` |

`<genre>` は sanomalehti（新聞）／aikakauslehti（雑誌）／teos（書籍）。

## 実装（`adapters/digi.py`、library_id: `finland-nl-digi`）

- **キーワード検索は実装しない**。Digiにバインディング横断の
  公式キーワード検索はなく（OAI-PMHは収穫用、JSONはタイトル一覧）、
  発見はFinna経由、解決は引き継ぎ経由が公式モデル。存在しない
  検索能力を主張しない。
- `get_document(binding_id)`：OAIヘッダ識別子の完全一致で同一性を
  確立（不一致・削除レコードは拒否）。dc:title/date/publisher/
  language/rights を保持。ページ数は kk:checksum の最大ページ番号。
- **ジャンルは推測しない**：レコード自身の kk:file リンク（公式
  ホスト完全一致＋パス構造）から復元する。復元できない場合は
  ページアクセスを拒否する。
- `get_page_text(<binding>@<page>)`：ALTOを取得し、共有モジュールで
  テキスト化。ページ同一性はALTO内部信号でのみ認定する
  （§10：URL構築可能性やHTTP 200では認定しない）。
  **最終レビューで厳格化**：候補段階の「`PHYSICAL_IMG_NR` の
  一致、または fileName への含有」という OR 条件は、別資料の
  同じページ番号のALTOを誤認し得たため廃止した。現在は
  単一Pageであること、fileName にバインディングIDが完全な
  区切りトークンとして含まれ外国のバインディングトークンが
  無いこと、ページ信号に矛盾が無いこと、kk:checksum の
  ページ集合があればその集合に属すること、の全てを要求する。
  資料同一性とページ同一性は別々に保持する
  （`document_identity_confirmed`／`page_identity_confirmed`）。
  信号が無い／矛盾する場合は本文は研究材料として返すが
  `verified_mapping=false` とする。範囲外ページにエラー画像を返す
  Digiの挙動への対策でもある。
  ページ数は kk:checksum のページ**集合の要素数**であり、
  最大ページ番号からの連番推定はしない。ジャンル信号が
  無い／矛盾する場合は landing_url を作らない（新聞への
  推測フォールバックは削除した）。
- `verify_original`：同じページ結果を再利用し、画像URLの応答が
  実画像（マジックバイト／Content-Type）であることを確認する。
  HTMLのアクセスページは原本ではない。
- `search_in_document`：ページ数がOAIで確立したバインディングのみ、
  上限20ページの範囲検索。カバレッジ（examined/page_count/complete）
  を常時報告する。
- 権利：dc:rights を逐語保持（例「Tekijänoikeuden alainen」＝
  著作権存続）。ライセンス分類は発明しない。権利存続で
  ソース側制限（Haka等）のかかる資料は取得しない。

## 実地検証状態（正直な記録）

2026-11-26、開発ネットワークから digi.kansalliskirjasto.fi へは
接続自体が成立しなかった（プロキシ経由で空応答）。**回避は
行っていない**。したがって本アダプターは **fixture_verified**
であり、実地検証（目標：3資料・5ページ程度）は未達成。
到達可能なネットワークが得られれば、同じ検証手順
（OAI同一性→ALTO信号→画像実在）で実地確認する。
