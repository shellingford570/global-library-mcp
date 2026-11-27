# 権利と利用の目安 / Rights and use guide

各資料の権利は所蔵機関と資料ごとに異なります。このツールは権利情報を
原文のまま表示し、推測で「利用可能」とは表示しません。
**権利が不明な資料は、無条件に利用可能ではありません。**

Rights differ per holding library and per item. This tool shows rights
statements verbatim and never infers "free to use".
**Unknown rights do not mean free to use.**

b8 note: keep the layers separate - API terms, the metadata
licence, the item's rights, OCR text rights, image rights and
access restrictions are different things. Two aggregator
examples: Finna and KB metadata are CC0, but that says
nothing about the items, their OCR or their images; Japan
Search items carry the provider's own licence and access
restrictions (e.g. NDL-only) in their accessInfo, surfaced
verbatim. See docs/library-rights-normalization.md.

## ライセンス別の目安 / Guide by licence

| 表示 / Statement | 抜粋表示・引用 | 画像表示 | 再配布 | 翻訳 | 外部LLMへの送信 |
|---|---|---|---|---|---|
| Public Domain / CC0 | ○ | ○ | ○ | ○ | ○ |
| CC BY | ○（出典明示） | ○（出典明示） | ○（出典明示） | ○（出典明示） | ○（出典明示） |
| CC BY-SA | ○（出典明示） | ○ | ○（同一ライセンス） | ○（同一ライセンス） | ○ |
| CC BY-NC | ○（非商用のみ） | ○（非商用のみ） | ○（非商用のみ） | ○（非商用のみ） | △（非商用のみ） |
| CC BY-NC-ND | △（引用の範囲内） | ○（非商用・改変なし） | ×（改変物の配布不可） | ×（翻訳は改変） | ×（原則不可） |
| In Copyright 等（RightsStatements.org） | △（引用の範囲内） | △ | × | × | × |
| 不明 / Unknown | △（引用の範囲内） | △ | × | × | × |

○＝一般に可、△＝条件付き（法域の引用規定等に従うこと）、
×＝権利者の許諾が必要。

Notes:

- **CC BY-NC-ND は公有財産（パブリックドメイン）ではありません。**
  非商用かつ改変なしの利用に限られます。翻訳は改変にあたります。
  CC BY-NC-ND is **not** public domain: non-commercial, no
  derivatives — translation counts as a derivative.
- 引用（quotation）は各法域の引用規定（出典明示、主従関係、
  必要最小限など）を満たす場合に限られます。
- NDL資料は資料ごとの公開区分（例：「インターネット公開
  （保護期間満了）」）が利用範囲を決めます。
- このツール（Research Beta）は、初期設定では外部LLMへ資料を
  送信しません。AI回答（実験機能）を有効化する場合は、送信先と
  各資料のライセンスを必ず確認してください。
- 本表は目安です。最終的な判断は各資料の権利表示と所蔵機関の
  利用条件に従ってください。

This table is a guide only. Always follow the item's own rights
statement and the holding library's terms.

## b5 additions (2026-11-25)

| Source | Metadata | OCR text | Images | Notes |
|---|---|---|---|---|
| BSB/MDZ | API responses carry per-item data | Per-item license in the IIIF manifest (rightsstatements.org or CC) governs reuse | Same per-item license | Fetchability is not a licence; NoC-NC items are not freely reusable. OCR/Image downloads are rate-limited per 24h by MDZ. |
| LoC Chronicling America | LoC | LoC's advisory: newspapers are believed public domain (US, >95 years certainly; younger items may contain third-party material) | Same advisory | The advisory text is shown per item; it is not a guarantee for every page element. |
| e-rara | OAI record (institution-specific) | Not offered in this phase | Not offered in this phase | dc:rights is shown when present (e.g. "PDM 1.0"); e-rara is the platform, holding institutions own the items. |

## b5 final-review note (2026-11-26)

Rights values now carry a machine-readable classification:
"cc0", "public-domain-mark" and
"rightsstatements-noc-nc-noncommercial" are distinct. A
Public Domain Mark is a label applied by an institution, not
a licence and not a finding that copyright has expired in
every jurisdiction; NoC-NC is a non-commercial restriction
statement. None of these classes, by itself, authorises
sending a work to an external AI service.

## b7: storage policy in the research workspace (2026-11-26)

Being able to fetch a text is not the same as being allowed
to store or redistribute it. In the b7 workspace:

- Bibliographic metadata and links are always storable.
- Short excerpts are stored and exported only for public
  domain / CC0 and permissive CC categories (BY, BY-SA,
  BY-NC, BY-NC-SA). For copyrighted, access-restricted,
  unknown or unverified rights, the citation reference
  (source, page, offsets, hash) is kept but the excerpt
  text is withheld by default.
- OCR full text and original image bytes are never stored.
- A licence name alone does not decide every use; the
  policy is a conservative default, and the system does not
  guarantee that any particular quotation is legally
  permissible — that depends on purpose, jurisdiction and
  extent.
- Rights are snapshotted at save time; later observations
  are appended as history and never overwrite the snapshot.
  If access is later restricted, stored excerpts are not
  used to circumvent the restriction.

See docs/b7-research-workspace.md for the full policy
table.

## b9: external transfer is a separate question (2026-11-27)

What this guide says about local reading/storage does NOT
decide what may be sent to an external AI service. The
external-research profile applies its own transfer policy
(docs/b9-external-rights-policy.md) with a per-library
transfer matrix (docs/b9-library-transfer-matrix.md): OCR
full text and original-image binaries are never transferred,
CC BY-NC is not assumed to satisfy its NonCommercial
condition for transfer to an AI service, and short excerpts
are disabled by default and individually gated.
