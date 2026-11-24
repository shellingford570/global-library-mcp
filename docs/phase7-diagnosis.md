# Phase 7-A — the eight Phase 6 false answers, reproduced

Fixtures: `eval/phase7-fixtures.json` (built by
`eval/build_phase7_fixtures.py` from the pages the Phase 6 runs
actually cited; verdicts recomputed on the fixture text with
`publication_year=None`, the year-less path). Each case records
the question, the cited page, its kind, both gate verdicts and
the promotion path that admitted it. No question-ID-specific
handling anywhere — the mechanisms below are general.

| Case | Question (demand) | Page kind | Relevance | Semantics | Path |
|---|---|---|---|---|---|
| q31 | 大正のテレビ放送 (occurrence) | body (a contents listing in fact) | relevant | supports | direct |
| q35 | 大正の新幹線開業 (occurrence) | body | partially_relevant | supports | semantic promotion |
| q40 | 明治43年の発電水力調査・滝の数 (numeric) | front_matter | partially_relevant | supports | semantic promotion |
| q52 | 大正の電気洗濯機普及 (diffusion) | body (contents page) | relevant | mentions_only | direct pass-through |
| h03 | 昭和のインターネット普及 (diffusion) | body (index-like OCR) | relevant | mentions_only | direct pass-through |
| h05 | 江戸の蒸気機関車運行 (occurrence) | body | relevant | insufficient (compound halves) | direct pass-through |
| h22 | 大正の電気冷蔵庫普及 (diffusion) | body | relevant | mentions_only | direct pass-through |
| h31 | 明治の日本人による宇宙飛行 (occurrence) | body | relevant | supports | direct |

## Mechanisms (generalised)

1. **Mention treated as assertion** (q52, h03, h22). A relevant
   page whose checker verdict is `mentions_only` was admitted
   whenever the source was not provably retrospective. A
   contents page or index page *naming* the topic is not a
   source *asserting* anything about it in the asked era.
2. **Unanchored supports** (q31, h31, q35). The checker's
   `supports` counted occurrence cues in discourse units with
   no in-era anchor: a 1950s contents page listing
   「テレビ放送開始記念式典祝辞」 (q31 — the "occurrence" stance
   sentence is name-index OCR noise); a JR business-analysis
   page whose 操業 cue concerns line management, not a Taishō
   opening (q35); an emigration history whose anchored
   occurrence sentences describe consulates and shipping
   routes while the asked topic (spaceflight) never appears in
   the page at all (h31 — the stance units bind to the modifier
   family 日本人， not to 宇宙飛行）.
3. **Promotion of an enumerative page** (q40). A front-matter
   調査要項 page (staffing rules) was promoted on partial
   relevance + supports; its numbers （職員数） are real but are
   not the asked quantity （滝の数）.
4. **Compound-halves relevance with no assertion** (h05).
   Relevance passed on the halves of 蒸気機関車； the checker
   itself said `insufficient`, yet the page was admitted.

## What Phase 7 changes (7-B…7-E)

- One admission rule for era-bound questions across all paths:
  evidence requires `supports` that is *anchored* (in-era
  textual anchor, or a contemporary source), or an out-of-scope
  `uncertain` verdict on a body/table page. `mentions_only` and
  `insufficient` never ground an era-bound answer.
- Promotion paths additionally require a narrative page kind
  (body/table) and, for unions, at least one member page that
  individually satisfies the supports+anchor condition —
  coverage across pages is not an assertion (brief §4.2), and
  the union's era condition must hold on the promoted page
  itself, not on any page of the document (§4.1).
- Demonym modifiers （日本人による…) stop binding stance units.
- Numeric demands get quantity binding (7-C): a number grounds
  an answer only near the asked target/unit.
- Page kinds gain index/colophon/admin-list/damaged and a
  per-demand usage policy (7-D).
- Every admitted page carries a structured promotion record
  (path + the §4.3 checks) into the answer payload.
