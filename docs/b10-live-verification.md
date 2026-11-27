# b10 live verification

Date: 2026-11-28. All live checks were key-free, read-only and
small in number, within the brief's approval.

## Authority APIs (Stage 2)

See `docs/b10-authority-resolution.md`: lobid GND works
(identifiers live-verified for ten focus authors), Wikidata
works, VIAF bot-blocked from this network (not evaded), NDL
Search SRU rate-limited (429) at check time.

## Scenario A — Kant original-work discovery (section 15/40)

Live run of `LibraryService.research_materials("純粋理性批判",
mode="standard")` over the default libraries, 2026-11-28:

- **#1 — Internet Archive: "Critique de la raison pure par
  Emmanuel Kant"** (the French translation of the original
  work).
- **#10 — DDB: "Immanuel Kant's Kritik der reinen Vernunft"**
  (the German original, Erdmann edition).
- 10 materials returned; LoC and Gallica errored during the run
  (Gallica's 403 from this network is a long-standing known
  state; no evasion attempted).

So in this live run the original-work candidates reached the
Top 10 — positions 1 and 10 — meeting the section-43 goal for
this scenario. Caveats, stated plainly: this is a single run;
the Internet Archive's full-text search contributes unrelated
records to the pool (positions 3–9 are mostly noise), so the
result depends on the day's upstream responses; and the #10
item is Erdmann's edition — the work is Kant's, the edition is
a later scholarly one, which the edition layer keeps distinct
from the 1781/1787 printings.

## Library regression

No new live library verification was attempted in b10 beyond
the above and the authority APIs; the b8/b9 live states stand
(Finna 403 from the server network, Digi unverified, Gallica
403, KB article-OCR only, DPLA/Europeana awaiting keys that
were not requested).
