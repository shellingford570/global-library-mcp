# b10 — Multilingual routing: allocation comparison and adoption

Stage 1 of v1.0.0b10 (brief sections 9 and 43). All numbers are
fixture/simulation proxy metrics with agent-assigned labels —
not live-catalogue recall, and not human-verified ground truth.

## The problem

When b8 added fi/sv/nl labels to the lexicon, the concept
translations of all seven languages began competing for the
same variant cap (quick 3 / standard 8 / deep 14). Re-measured
at the b10 starting point (master `66f2867` + Stage 0), the b6
fixed simulation stood at Recall@10 **0.8819** (b6 release:
0.9097) and the challenge set at **0.8611** (release: 0.9167),
while the b8 fixed evaluation held 0.7500.

## Policies compared

Implemented as the `allocation` parameter of
`QueryExpansionEngine.expand` (evaluation hook:
`GLM_EXPANSION_ALLOCATION`), changing only the ORDER in which
concept-translation candidates compete for the unchanged cap:

- **A — legacy**: the b6-release concept-major order (concept,
  then lexicon language order ja/en/de/fr/fi/sv/nl, then label).
- **B — diagonal**: the b8/b9 interleave (label round, then
  concept+language diagonal).
- **C — user priority**: requested languages first. In the b6/b8
  corpora no per-case language request exists, so C is
  numerically identical to B there; it is exercised through
  `target_languages` in production paths instead.
- **D — per-library priority**: a dispatch-layer policy; not
  expressible in the shared expansion ordering. Not simulated
  (recorded, not silently dropped); the routing layer already
  dispatches variants to libraries by language.
- **E — hierarchy**: concept-major with all label rounds of the
  primary concept before secondary concepts.
- **F — adaptive**: needs result feedback; evaluated with the
  Stage 3 adaptive planner on the service evaluation, not in
  this simulation.
- **G — minimum guarantee**: the b8 section-19 experiment
  (primary concept's first label in every language first).
- **H — compound/authority priority**: compounds and authority
  forms already sit at priorities 1–2, above translations (3),
  and the cap applies after the priority sort — so H is
  structurally guaranteed and, as predicted, numerically
  identical to B in the translation ordering.

## Results (config F; `eval/results-b10-allocation.json`)

| policy | b6 fixed R@10 | b6 challenge R@10 | b8 std R@10 | b8 cross-lang | b6 fixed MRR | attempts |
|---|---|---|---|---|---|---|
| A legacy | 0.8819 | **0.9167** | **0.7667** | **0.7500** | **0.8519** | 40.1 |
| B diagonal (b8/b9) | 0.8819 | 0.8611 | 0.7500 | 0.6667 | 0.8426 | 40.2 |
| C user priority | 0.8819 | 0.8611 | 0.7500 | 0.6667 | 0.8426 | 40.2 |
| E hierarchy | 0.8542 | 0.8611 | **0.8583** | **0.9167** | 0.8426 | 40.5 |
| G guarantee | 0.8542 | 0.8611 | **0.8583** | **0.9167** | 0.8426 | 40.5 |
| H authority | 0.8819 | 0.8611 | 0.7500 | 0.6667 | 0.8426 | 40.2 |

Dev/holdout cross-check for the two finalists: dev R@10 1.0000
for both (MRR 0.9263 A vs 0.9254 B); holdout R@10 0.9375 for
both (MRR 0.8594 A vs 0.8281 B). b8 quick R@10 0.4583 under
every policy. HTTP attempts are unchanged within noise — no
policy buys recall with budget, and none raises the cap.

## Adoption decision

**A (legacy concept-major order) is the default again.** It is
the only policy that is at least as good as the status quo on
every corpus and better on the challenge set (+0.0556), the b8
set (+0.0167 R@10, +0.0833 cross-language) and MRR — the
brief's rule against one-sided trade-offs is satisfied.
E/G are **not adopted**: their large b8 gain (+0.1083) comes
with a b6-fixed regression (−0.0278), exactly the one-sided
pattern section 9 prohibits adopting unconditionally. They
remain available as named policies for future corpora.

With A adopted, the section-43 targets stand at: challenge
0.9167 ✓ recovered; b8 standard 0.7667 ✓ above the 0.7500
floor; b8 cross-language 0.7500 ✓ above 0.6667; **b6 fixed
0.8819 ✗ still below 0.9097** — see the diagnosis.

## Diagnosis: the remaining b6-fixed gap is ranking, not allocation

Per-case analysis of the fixed set under A (each missed
relevant record classified against the uncapped candidate
pool):

- **ranked low (5 cases)**: `ddb:dampfmaschine-1850` is
  retrieved but ranks below 10 for four different queries
  (F05, F06, F11, F16), and `gallica:moniteur-1789` for F07.
  Discovery succeeds; the ranker undervalues the exact
  original-language title/concept match against a flood of
  partial matches.
- **cut by the cap (1 case)**: F01 loses the 電気 label
  variant to the cap.
- **not generated (1 case)**: F19 (hydroelectric power
  development) never generates a variant matching
  `ddb:wasserkraft-1908` — a lexicon/discovery gap for the
  German Wasserkraft label, addressed with the Stage 2/3
  lexicon and authority work, not by allocation.
- F38 is a false-premise case whose dataset entry stores an
  explanation string in place of a record-id list; it scores 0
  under every configuration including the b6 release
  measurement. The frozen dataset is not altered.

Consequence: allocation is closed as the primary lever for the
fixed set. The remaining recovery path is the Stage 3
ResearchRanker (brief sections 20–21), evaluated against these
same corpora under the same no-one-sided-regression rule.

## Addendum (Stage 3, 2026-11-28): the gap was routing, not ranking

Per-case diagnosis of the remaining fixed-set shortfall showed
the relevant records were **not retrieved at all**, and the
cause was in the simulation harness, not the allocation policy:
`eval/b6_engine_configs.py` routed each engine variant by
running `detect_language()` on the variant TEXT. Single-word
variants misroute: the German compound "Dampfmaschine" was
detected as English and dispatched to loc/internet-archive —
never to ddb, the German library holding the record — while
the Finnish "höyrykone" was detected as German and sent to ddb.
Production routing (service.py) never had this defect: it reads
the expansion plan's own `language` field per variant. The
simulation now does the same for engine variants (legacy
variants keep text detection), restoring the harness's stated
intent ("routing mirrors the production service"). A lexicon
gap was also fixed: `Wasserkraft` added as a German label of
concept:hydroelectric-power (it was only under water-power).

Re-measured comparison (same runner, `eval/results-b10-allocation.json`
regenerated at the Stage 3 head):

| Policy | b6 fixed | b6 challenge | b8 std | b8 cross | attempts |
|---|---|---|---|---|---|
| A legacy (adopted) | **0.9167** | **1.0000** | 0.7667 | 0.7500 | 33.4 |
| B diagonal | 0.9005 | 0.9444 | 0.7500 | 0.6667 | 32.6 |
| E/G hierarchy/guarantee | 0.8819 | 0.9444 | 0.8583 | 0.9167 | 34.0 |

All section-43 multilingual targets are now met under the
adopted policy A: fixed ≥ 0.9097 ✓, challenge ≥ 0.9167 ✓,
b8 standard ≥ 0.7500 ✓, b8 cross-language ≥ 0.6667 ✓. E/G
remain unadopted (they still trade b6-fixed recall for b8
gains). Attempts fell from ~40 to 33.4 because variants now go
to the libraries that can actually answer them. The frozen
datasets were not modified; F38's dataset defect stands as
recorded in Stage 1.
