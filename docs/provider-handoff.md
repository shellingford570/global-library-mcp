# 提供元への引き継ぎ（Provider Handoff）

横断検索プラットフォームのレコードから提供元の原典へ到達する
ための規則。b6のDDB→BSB連携を原型とし、b8でFinna→Digiを追加した。
実装は `src/global_library_mcp/handoff.py`。

## 共通原則（§6）

1. **公式提供機関識別子と正確な資料ID**でのみ引き継ぐ。タイトルや
   著者の類似でIDを推測しない。
2. URLは**構造解析**する：スキームはhttps、ホストは完全一致の
   許可リスト、パスは提供元の文法に一致すること。別ホストのURLに
   埋め込まれた提供元風文字列は識別子ではない。
3. **複数候補**（異なるIDが複数）は曖昧として拒否する。
4. 上流応答に含まれる任意URLを**サーバーから自動取得しない**。
   引き継ぎ先アダプター自身の公式エンドポイントだけを使う。
5. 候補は候補にすぎない。引き継ぎ先での同一性検証（マニフェスト／
   OAIヘッダ等の構造一致）と、書誌情報の対応確認
   （`titles_correspond`、年・著者の矛盾確認）を経て初めて
   「引き継ぎ成立」と記録する。各段階の成否は独立に記録する。

## DDB → BSB（b6）

- 条件：DDBレコード自身が公式URN
  （`urn:nbn:de:bvb:12-bsbXXXXXXXX-N`、完全トークン）または公式
  ホスト上のMDZオブジェクトURLを持ち、かつ提供者が構造化
  フィールドでBSB（provider_id／データセットラベルの提供者
  コード `00005860`）と確立できること。
- 状態：`candidate` / `no_candidate` / `refused_provider_mismatch` /
  `refused_ambiguous`。
- 成立はBSBアダプターの厳密なマニフェスト同一性検証が決める。

## Finna → フィンランド国立図書館 Digi（b8）

- 条件：Finnaレコードの `provider_links` に、完全一致ホスト
  （digi.kansalliskirjasto.fi／英語別名 digi.nationallibrary.fi）上の
  `/<genre>/binding/<数字ID>` パスを持つhttpsリンクが存在すること。
  genre ∈ {sanomalehti, aikakauslehti, teos}。
- 状態：`candidate` / `no_candidate` / `refused_ambiguous`。
  類似ホスト（サフィックス偽装）、http、パス文法不一致は候補にしない。
- 成立条件：DigiアダプターのOAI同一性検証（ヘッダ識別子完全一致）に
  加え、FinnaタイトルとDigiタイトルの対応（`titles_correspond`）と
  年の矛盾がないこと。ジャンルは候補側とOAIレコード自身の
  ファイルリンク側で一致を取る。
- 実地状態（2026-11-26）：両ホストとも開発ネットワークから
  到達できず、フィクスチャ上の引き継ぎ連結（Finna詳細→候補抽出→
  Digi書誌→ページ検証）のみ確認済。実地の引き継ぎ成功は未達成として
  `docs/b8-live-verification.md` に記録する。
