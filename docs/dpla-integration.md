# DPLA統合（b8 Stage 4・認証待ち実装）

確認日：2026-11-26。調査詳細は `docs/b8-api-research.md` §3。

## 認証状態

DPLA API v2 は全リクエストに32文字のAPIキー（`api_key`
クエリパラメータ）を要求する。キーは無料・自己発行だが、
**b8ではキー発行を承認されていないため発行していない**。

- 環境変数 `DPLA_API_KEY` 未設定時：アダプターの全操作は
  `authentication_required` を明示した AdapterError で失敗する
  （リトライ不可）。HTTPリクエスト自体を行わない。
  レジストリの capability_status も `authentication_required`。
- キーが運用者により設定された場合：公式エンドポイントで
  検索・詳細が動作する（フィクスチャで検証済）。

## 実装（`adapters/dpla.py`、library_id: `dpla`、オプトイン）

- 検索：`GET /v2/items?q=&page_size=&page=`。詳細：`GET /v2/items/<id>`、
  応答IDの完全一致で同一性を確認。
- 機関の区別：`provider`（DPLAへの集約ハブ）と `dataProvider`
  （原資料の提供機関）を別フィールドで保持し、混同しない。
- 権利：`sourceResource.rights`（RightsStatements.org URI等）を
  構造分類する（InC／NoC／CC／PDM／CC0を区別）。URIをライセンス
  許諾へ言い換えない。
- DPLAはメタデータ集約であり全文・ページOCRはない。ページ系
  メソッドは未対応のまま。`isShownAt`／`object` は提供元URLとして
  保持するのみで取得しない。

## 実地検証状態

キー未発行のため実地検証は行っていない（フィクスチャのみ）。
キーなしで `authentication_required` が返ることは実地に確認済
（2026-11-26、HTTP未発生）。
