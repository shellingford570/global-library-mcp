# 権利情報の正規化（b8）

§13の分離原則を、機関横断でどう適用するかの記録。権利は常に
以下の層を分けて扱い、混同しない：

1. API利用条件（サービス自体の条件）
2. メタデータライセンス（書誌データのライセンス）
3. 個別資料の権利
4. OCR本文の権利
5. 原本画像の権利
6. アクセス制限（権利とは別。例：館内限定、ログイン制限）
7. 保存可否／表示可否／エクスポート可否／外部送信可否
   （ワークスペース側の判断。Stage 0の信頼モデルで決定）

## 機関別の出所と正規化

| 機関 | メタデータ | 資料権利の出所 | 正規化方針 |
|---|---|---|---|
| Finna | CC0 1.0（明示的に分離記録） | レコード `usageRights`（機関ラベル） | ラベルはライセンスではないのでCC分類を付けない。空＝不明 |
| NLF Digi | OAIメタデータ | OAI dc:rights（逐語。例「Tekijänoikeuden alainen」） | 分類を発明しない。アクセス制限はDigi側条件として分離 |
| DPLA | CC0指向 | `sourceResource.rights`（RightsStatements.org URI等） | URIを構造分類（InC／NoC／CC／PDM／CC0） |
| KB/Delpher | CC0 | SRU dc:rights（所蔵者表明が多い） | 逐語保持。表明をライセンスへ格上げしない。無ければ不明 |
| Japan Search | 提供DB毎 | accessInfo の `license`（RightsStatements.org URI） | 構造分類。`description` 内のアクセス制限は別フィールドで逐語保持 |

## 構造分類（URIベース）

`publicdomain/zero`／CC0、Public Domain Mark（ライセンスでは
ない）、`creativecommons.org/licenses/...`、RightsStatements
（InC／NoC-*／その他）を区別する。URIが無い・解釈できない場合は
分類なし＝不明として保守的に扱う。

## 保守原則

- 適用対象不明・矛盾・否定表現・未確認の権利は保守的に扱う
  （b7で確立した fail-closed 分類を維持）。
- 権利不明資料は参照情報のみ保存が既定。原文抜粋の保存は
  サーバー観測された権利表明と信頼モデル（Stage 0）が
  許可した場合のみ。
- 「取得できた」ことは「再利用できる」ことではない。到達性と
  ライセンスは常に別々に記録する。
- メタデータのCC0は、資料・OCR・画像のCC0を意味しない
  （FinnaとKBで特に明記）。

## 最終レビュー追記（2026-11-26、§15）

- 権利URIの分類は共有モジュール `rights_uri.py` に統一
  した。正確なホスト（creativecommons.org／
  rightsstatements.org）、パス文法、正式な版数を要求し、
  偽装ホスト・別URLへの埋め込み・資格情報・異常ポート・
  制御文字を拒否する。
- Japan Search／DPLA の表示用分類も同モジュールに委譲
  した。表示分類は保存許可判断には使わない。
- Finna の usageRights は機関独自ラベルとして保持し、
  正式ライセンスとは区別する（従来どおり）。
