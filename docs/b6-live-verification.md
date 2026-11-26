# b6 live verification (2026-11-26)

Small, representative live runs only; fixture evaluation is
in docs/b6-evaluation.md. All runs used the standard mode
and the production HTTP budget. Paid LLM calls: 0.

## Multilingual materials search

- "カントの認識論" (NDL/LoC/IA/DDB): expansion produced
  Immanuel Kant name forms, "Kritik der reinen Vernunft",
  "epistemology", "theory of knowledge"; top materials were
  NDL Kant studies. Cross-language variants fire live.
- "19世紀ドイツの蒸気機関" (NDL/DDB/IA), BEFORE the variant
  ordering fix: 13 materials, all found by the baseline term
  "19世紀ドイツ", mostly irrelevant (politics lectures,
  port records) - the engine variants were starved by the
  standard-mode early stop. AFTER the fix: 10 materials, all
  steam-engine records (IA treatises, DDB steam-engine
  objects) found by the engine variants "steam-engine" /
  "steam engine"; 36 HTTP requests, 44s, inside the budget.
  Remaining gap, stated plainly: DDB's own ranking for the
  English variant returns object records first, and no
  German-language Dampfmaschine monograph reached the top 10
  in this run.

## DDB -> BSB handoff (section 17)

Live end-to-end: DDB search "Kurzgefaßte Geschichte der
Dampfmaschine Reuleaux" returned record EV4P6SXQBJWI whose
official URN (urn:nbn:de:bvb:12-bsb11650472-5, provider
00005860) yielded candidate bsb11650472; the BSB document
was fetched (50 pages, title "Reuleaux, Franz: Kurzgefaßte
Geschichte der Dampfmaschine" - titles correspond), and
get_page_text(bsb11650472@5) returned verified_mapping true
under the strict b5 checks. A plain "Dampfmaschine" DDB
search did not surface a BSB record in its first 10 results;
the handoff depends on the record being found, which is a
DDB ranking matter, not an extraction gap.

## LoC newspaper discovery (section 18, scenario 6)

newspaper_issues("sn83030214") live: title anchored
("New-York Tribune (New York [N.Y.]) 1866-1924"), 45 issue
ids on the first search page, each structurally
<lccn>/<date>/ed-<n> and directly usable by the strict b5
page pipeline (whose page-level verification was live-proven
in b5). The response states the list is one page, not a
complete enumeration. The retired Chronicling America title
JSON (308 into loc.gov, then 404) is documented in the
adapter; discovery uses the LoC search API instead.

## Gallica (section 30)

One limited re-check from this network: search returned the
same upstream 403 as in b3-b5. No retries, no evasion.
Gallica remains fixture-verified / live-unverified; French
discovery is covered by the fixture evaluation and by IA
holdings in the live runs above.

## MCP

- stdio: 15 tools; research_materials quick and standard
  calls succeed with the new optional parameters defaulted.
- Streamable HTTP with --profile research on 127.0.0.1: 14
  tools, research_question absent, all read-only,
  research_materials succeeds. (list_libraries emits one
  content block per library, as established in b5.)
