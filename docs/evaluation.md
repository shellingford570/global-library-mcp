# Answer-quality evaluation

Evaluation harness: `eval/run_evaluation.py` over `eval/questions.json`
(30 questions: Japanese history, history of science/technology,
hydroelectric/electrical engineering, history of medicine,
geography/culture, and deliberately unanswerable questions).
Raw results: `eval/results-phase3.json`.

## What is measured — and what is not

The default run uses the deterministic **MockProvider**. It measures the
*pipeline* (discovery, OCR capture, citation resolution, claim-grounding
screening, insufficient-evidence behaviour, cost) — **not** the prose
quality of a real LLM. Mock claims quote OCR sentences verbatim, so a
100% claim-supported rate is expected by construction and proves only
that the checker accepts genuinely grounded text. Real-LLM answer
quality requires an operator-approved API key and has **not** been
measured yet.

## Live run, 2026-11-22 (NDL, mock provider)

| Metric | Result |
|---|---|
| Questions | 30 |
| Discovery rate (expected-evidence questions with ≥1 verified page) | **1.00** (25/25) |
| OCR capture rate (verified / attempted pages) | 0.94 |
| Original-image reachability (10 sampled evidence pages, full IIIF verify) | 1.00 |
| Citation resolution rate | 1.00 |
| Claims screened | 87, all `supported` (see caveat above) |
| Insufficient-evidence correctness (5 unanswerable questions) | **0.20** (1/5) |
| Average time per question | 6.5 s |
| Total external API requests | 444 |

## Findings

1. **Grounding holds; topical relevance is the weak point.** Four of the
   five "unanswerable" questions (smartphones in the Meiji era, the
   history of the Internet, quantum computing, the exact population of
   Yokohama village in 1853) still produced answers, because term
   extraction falls back to generic terms (通信, 歴史, 原理, 人口) that
   match loosely related period documents. The answers were grounded in
   real pages — citations resolved and claims were lexically supported —
   but the pages do not actually answer the question. A citation being
   real is not the same as an answer being right.
2. **Run-to-run variance is material.** A duplicate run on the same day
   scored discovery 0.84 and insufficient-correctness 0.6 with 620
   requests: live catalog results and term fallbacks fluctuate, so
   single-run numbers should be read as samples, not constants.
3. **OCR misrecognition propagates into evidence excerpts** (e.g. mixed
   old/new character forms, broken tokens in Meiji-era print). The
   quality gate filters empty/broken pages, not subtle misreadings;
   claims screening is lexical, so a misread token can pass. The
   original image link is therefore kept on every citation.

## Improvement backlog (in order)

1. Relevance gate: require the question's most specific term(s) to
   appear in a page's OCR before the page can ground an answer, and
   expose a per-evidence relevance signal next to the grounding status.
2. Real-LLM evaluation with an approved key, scoring claim support on
   paraphrased (not quoted) claims.
3. Era-mismatch checks: compare the question's era tokens with the
   document's publication era and flag answers that bridge them silently.

## Unit-level coverage of the failure cases

The brief's failure cases are covered deterministically in tests:
no matching documents, page-id mismatch, missing OCR, low-quality OCR
(`tests/test_evidence.py`, `tests/test_verify.py`); claims with no
citation, unrelated claims, unverified date tokens, provider-flagged
conflicts (`tests/test_claims.py`); invented citation keys withheld at
the service layer (`tests/test_research.py`).

---

# Phase 4 evaluation — reliability (2026-11-22)

Phase 4 added question understanding (`question.py`), a relevance
gate (`relevance.py`) between the OCR quality gate and answer
generation, and claim-based answer withholding. The dataset grew
from 30 to **70 questions** (27 labelled unanswerable: anachronisms,
nonexistent technologies/people/places, over-specific numeric and
causal demands, similar-word traps; 43 labelled answerable, incl.
old-orthography questions, a comparison, a causal question, and two
English questions). Labels follow the environment standard: a
question is "answerable" only if directly supporting OCR evidence
is confirmable in this corpus — not because the topic is real.

**Label change, disclosed:** q27 (インターネットの歴史) was relabelled
from `insufficient` to `evidence`. The corpus contains modern
publications and the question carries no era constraint; the system
found genuine, on-topic evidence. Keeping the old label would have
punished correct behaviour. All other labels are unchanged.

Two reproducible layers:

- **Fixture evaluation** (`tests/test_eval_fixtures.py`, no network):
  10 fixed question/OCR pairs pinning the gate's required behaviour
  (smartphone trap, old-form hydroelectric, EN-JA synonym, numeric
  cap, invented person, era retrospective). All pass.
- **Live evaluation** (`eval/run_evaluation.py`, NDL, MockProvider):
  two runs — before and after the generic gate fixes diagnosed from
  run 1. Raw data: `eval/results-phase4-run1.json` and
  `eval/results-phase4.json`.

## Run 1 (gate as first implemented) — what it exposed

| Metric | Run 1 |
|---|---|
| Insufficient-evidence correctness (27 unanswerable) | 0.815 (22/27) |
| Answerable success rate (43) | 0.558 (24/43) |
| False answers | 5 (q27 — see relabel; q33 原子力, q49 地下鉄, q51 プラスチック, q52 電気洗濯機) |
| False refusals | 19 |
| Citation resolution | 1.00 |
| Claims | 78, all supported (mock construction; see caveat) |
| Requests | 1,825 (26.1/question; Phase 3: 14.8/question) |

Run 1 proved the gate works mechanically (refusals rose from 0.20
to 0.815) but also that it was **too blunt in both directions**.
Failure analysis (each fix is a general rule, not a per-question
patch):

False refusals:
- Process/intent nouns （開発, 違い, 原因） and term-splitting debris
  （よう, 行われた, めぐる議論, 流行した原因） were treated as core
  concepts and vetoed real matches → generic-term list extended and
  a debris filter added (hiragana-led fragments, verb-form tails).
- The era requirement never reached the gate (missing `era` key),
  so era-name signals were invisible → fixed; era distance is now
  scored: no era mention in the page **and** publication > era
  end + 40 years caps the page at partially relevant; > +20 years
  without a mention costs score. Publication year alone never
  excludes (retrospective histories stay eligible, and a fixture
  pins that).
- Period orthography gap: 燈 was not folded to 灯， hiding 電燈/ガス燈
  matches → variant table extended.
- Long compounds split in period prose （横浜の開港） missed verbatim
  matching → both-halves co-occurrence now counts for ≥4-character
  compounds.
- Multi-concept questions were vetoed by any single missing
  secondary concept → anchor rule: when the primary concept matches
  and at least half the concept families match, the page is relevant
  (numeric and era caps still apply).
- Retrieval order: broad survey volumes from the full-question
  search crowded out on-topic monographs → merged candidates are
  re-ranked so documents whose titles carry a core concept are
  tried first.
- The refusal message blamed the union of all related pages'
  missing concepts → it now names what the *closest* candidate
  lacked.

False answers:
- q51 （プラスチック, 1956 trade-statistics table): concept present in
  a commodity list, no era relation → the era-distance cap now
  refuses it.
- q33 （原子力発電所, Meiji): modern general treatment, no era
  mention → same cap, when the publication year is far.
- q52 （電気洗濯機, Taisho; 1947 appliance book): publication inside
  the +40 window; run 2 still answers it (an in-range year mention
  on the answering page counts as an era signal). It belongs to the
  residual retrospective class described under Run 2.
- q49 （地下鉄, Meiji; 『東京地下鉄道史』1934): a genuine retrospective
  whose sampled pages discuss Meiji-era background. With the era-key
  fix the pages *do* carry an era signal, so the gate accepts them.
  This remains a known hard case: the source supports a corrective
  answer ("construction was Showa; plans existed in Meiji"), but
  framing that correctly is the answer generator's job, not the
  gate's. Recorded as a residual false answer, not hidden.

## Run 2 (after the generic fixes)

| Metric | Run 2 | Run 1 | Phase 3 (30-question dataset) |
|---|---|---|---|
| Insufficient-evidence correctness | 0.808 (21/26) | 0.815 (22/27) | 0.20 (1/5) |
| Answerable success rate | **0.682** (30/44) | 0.558 (24/43) | discovery 1.00 (25/25) |
| False answers | 5 | 5 | 4 of 5 unanswerable |
| False refusals | 14 | 19 | n/a (no gate) |
| Citation resolution | 1.00 | 1.00 | 1.00 |
| Claims | 94, all supported (mock) | 78 | 87 |
| Requests | 1,318 (18.8/question) | 1,825 (26.1) | 444 (14.8) |
| Avg seconds/question | 7.2 | 13.5 | 6.5 |

Denominators differ because q27 was relabelled (see above). On the
original Phase 3 subsets, run 2 answers 17/25 evidence questions and
refuses 4/4 unanswerable ones: the gate visibly trades raw discovery
for refusal correctness. Neither Phase 4 target (insufficient-
correctness ≥ 0.90, answerable success ≥ 0.90) is met; the numbers
below are reported as measured, and live runs in this environment
have shown material run-to-run variance (a Phase 3 duplicate run
scored discovery 0.84 against 1.00), so ±2 questions is within noise.

What run 2 fixed: q33 （原子力） and q51 （プラスチック） are now
refused by the era-distance cap; false refusals fell 19 → 14
(q01 発電水力， q08 活版印刷， q11 ガス燈， q59 電燈， q65 EN hydro
among them); requests per question fell 26.1 → 18.8 from title
re-ranking and early failure termination.

What run 2 did **not** fix — the residual false-answer class: all
five remaining false answers (q31 テレビ放送/大正， q32 ラジオ放送/明治，
q39 自動車レース/明治， q49 地下鉄/明治， q52 電気洗濯機/大正） are
retrospective sources that genuinely mention both the concept and
the asked era on the same page — as background ("in the Meiji era
there was no broadcasting yet") or as later-era coverage. A lexical
gate cannot distinguish *mentioning* the era from *covering the
topic in* the era; three of the five were refused in run 1 only
because the era-key bug made era signals invisible everywhere.
Separating this class needs semantic checking (does the page assert
the topic existed/happened in the era?) — the documented next step,
not something to fake with tighter lexical thresholds, which the
false-refusal side (still 14, mostly retrieval misses where the
right book is never reached inside the document budget) shows
would cut both ways.

## Internet Archive regression (live, 2026-11-22)

Adapter level, identical to Phase 3: `hydroelectricdev00koesrich`
metadata OK; in-document search "dam" → leaves 11/14/20; leaf text
verified (3,648 chars, djvu.xml); `verify_original` all checks pass.
Two Phase 4 changes: catalog search now excludes the lending-only
`inlibrary` collection (restricted items can never yield evidence,
so they only wasted downstream requests), and English function
words (how/did/develop/…) no longer become search terms or core
concepts. End-to-end generic English questions still depend on IA's
catalog ranking, which surfaces noisy items first for broad terms —
recorded as a known limitation, not an adapter regression.

## Cost note

Requests per question rose when the gate first landed (14.8 →
26.1 in run 1) because questions with no relevant page scan up to
6 documents instead of 3 — the price of not answering from the
first loose match. Title re-ranking, query deduplication,
early termination on document-level search failure, and per-instance
page caching brought run 2 back to 18.8/question and 7.2 s/question.
Search quality was not traded away for the savings.

## What is still not measured

Real-LLM answer quality (needs an approved paid key). The mock
provider's claims quote OCR, so claim-supported rates remain a
pipeline check, not a prose-quality measure. Semantic relevance
beyond lexical screening (e.g. whether a retrospective page's
*framing* answers the question as asked — the q49 case) needs a
semantic checker, which is the natural next step after a relevance
gate exists to integrate it with.
