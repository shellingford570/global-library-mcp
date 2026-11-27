# b10 Stage 2 — Authority resolution

Date: 2026-11-28. Brief sections 11–15. All live checks were
key-free, read-only and small in number, as approved.

## Live verification of authority APIs (2026-11-28)

| Source | Route | Result |
|---|---|---|
| GND via lobid (hbz) | `lobid.org/gnd/search` JSON-LD | **Works.** Kant = GND 118559796 (d. 1804-02-12). Surname search "Darwin" returns 123 persons — disambiguation is genuinely required. 夏目漱石 present (118785737). |
| Wikidata | `wikidata.org/w/api.php` wbsearchentities | **Works.** 夏目漱石 = Q180903. Auxiliary cross-check source only. |
| VIAF | `viaf.org/viaf/AutoSuggest` | **Blocked**: Cloudflare bot page from this network. Client implemented from the documented response shape and fixture-tested; live status unverified, source off by default. No evasion attempted. |
| NDL Search SRU | `ndlsearch.ndl.go.jp/api/sru` | **Rate-limited (429)** at check time (concurrent-access cap). NDL authority terms were verified from provider pages in b6 (see `docs/authority-data-research.md`); the resolver does not depend on live NDL calls. |

Name-only GND searches did NOT surface the famous bearers for
Weber/Rousseau in the top results (three "Max Weber" entries,
none the sociologist). Year-filtered queries resolved them:
Max Weber 118629743 (1864–1920), Alfred Weber 118765787
(1868–1958), Rousseau 118603426 (1712–1778) — and even the
1864-filtered Weber query returned a second 1864-born namesake
(d. 1884), separated only by death year. This is the empirical
basis for the resolver's signal design.

GND identifiers live-verified and recorded in the lexicon:
Kant 118559796, Charles Darwin 118523813, Erasmus Darwin
118671049, Newton 118587544, Max Weber 118629743, Alfred Weber
118765787, Rousseau 118603426, Fukuzawa 118952633, Natsume
118785737 (+ Wikidata Q180903), Mori Ōgai 118736957.

Terms summary (checked 2026-11-26 in b6, re-stated): NDL
authority data — free use with attribution requested, edited
data must be marked as edited. VIAF — ODC-By attribution.
GND/lobid — GND data is public-domain dedication (CC0) per DNB;
lobid is an hbz service. Wikidata — CC0. No API keys required
for any of them; no registration was performed.

## AuthorityResolver (`src/global_library_mcp/authority.py`)

- Records follow brief section 12 (authority_id, source,
  canonical/variant names, life years, associated works,
  external identifiers, source URL, verification status).
- Sources: local lexicon (always), lobid GND and Wikidata
  clients (injectable fetch; live use opt-in), VIAF client
  (implemented, off by default — see above).
- Records describing the same person (shared external
  identifier, or same canonical name + birth year) are merged
  before scoring, so two sources for one person never compete
  as rivals; cross-source year disagreement on the same
  identifier yields `conflicting_authorities`.
- Scoring signals: exact name form (+3), surname only (+1),
  birth/death year match (+2 each), associated-work match (+2).
  `authority_verified` requires score ≥ 4, a margin ≥ 2 over
  the runner-up, and an official source or a live-verified
  identifier — reaching an authority record alone never
  certifies identity (section 12).
- Life-year conflicts hard-exclude, EXCEPT a one-year
  difference, which is treated as a calendar/era-boundary
  ambiguity (Newton 1642 Old Style vs 1643 New Style is the
  motivating case): the match points are withheld and the
  ambiguity is recorded as a signal, but the candidate is not
  excluded. Larger differences always exclude (the 1758
  "Charles Darwin" namesake is excluded by the 1809 query).
- Works: `resolve_work` maps original and translated titles
  across languages (純粋理性批判 → Kritik der reinen Vernunft,
  with author-hint signal). `identify_edition` answers only on
  an exact year match (Kritik A 1781 / B 1787; Origin 1859–1872
  six editions; Principia 1687/1713/1726; Faust parts 1808/1832
  — distinct texts under the same never-merge rule) and every
  edition record states `shares_pages_with_other_editions:
  false`.

## Evaluation (local resolver, frozen b10 dataset)

`eval/b10_authority_eval.py`; labels are the dataset's own
(agent_assigned / bibliographic_source_supported) — a proxy
evaluation, not human verification.

| Split | identify | from variant | work titles | editions | traps scored | must-not-merge | false verified |
|---|---|---|---|---|---|---|---|
| dev | 1/1 | 4/4 | 6/6 | 4/4 | 1/1 | 1/1 | **0** |
| fixed | 4/4 | 3/3 | 16/16 | 9/9 | 3/3 | 2/2 | **0** |
| holdout | 5/5 | 3/3 | 8/8 | 5/5 | 3/3 | — | **0** |

Role-based traps (translator-as-author, editor-as-chapter-author,
about-vs-by, corporate author) are not resolver questions; they
are scored with the ranking/claim work in Stages 3–4 (deferred:
dev 10, fixed 10, holdout 2).

Disclosure: the first evaluation run exposed generic coverage
gaps (katakana name forms, hiragana readings, old/new-script
forms, real names such as 夏目金之助， short titles such as
"Principia", the full Faust title forms, and four canonical
works/authors absent from the lexicon). These were added as
general bibliographic data — failure analysis covered all three
splits, so the final rates above are not a clean holdout
measurement; they demonstrate behaviour on the frozen set, and
the durable guarantees are the zero false verifications and the
exclusion/ambiguity rules, which the unit tests pin directly
(`tests/test_b10_authority.py`, 10 tests).

## Kant original-work discovery (section 15)

Resolver side: 純粋理性批判 resolves to `work:kritik-reinen-
vernunft` with original title Kritik der reinen Vernunft and
the A/B edition split. Whether the original reaches the Top 10
of live search results depends on upstream retrieval and the
Stage 3 ranker; it is measured as scenario A in Stage 6, not
claimed here.
