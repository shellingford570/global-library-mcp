# b11 Live Verification (sections 56/70)

Live checks on 2026-11-28 from the development VM (existing
key-free APIs only, small request counts, no crawling):

## Kant (section 56)
Query "Kritik der reinen Vernunft", DDB only, exact title:
- #1 `IFETABGFTVCC7E7FQOYD7XFZY73GAXD4` "Immanuel Kant's
  Kritik der reinen Vernunft" (the German original candidate).
- #7 `KA4K7RVTIMAUOUIOJ63NSNO6UBOWFWDL` "Kritik der reinen
  Vernunft, zweite Auflage".
- DDB returned NO year for any of the top-10 records, so no
  edition year is confirmed for either candidate; the
  "zweite Auflage" record remains an edition CANDIDATE and is
  never asserted to be the 1787 edition.

Cross-library (ddb + internet-archive + loc + gallica),
"Immanuel Kant Kritik der reinen Vernunft 1781": the German
original candidate ranked #7 this run; an IA record titled
"Text der Ausgabe 1781" ranked #2. The materials list showed
the same IA record twice (positions #1/#4 and #2/#3 pairs) -
per-variant material listings are not deduplicated at that
layer (deduplication applies in evidence collection); recorded
as an observation, not changed in b11. Conclusion unchanged
from b10: DDB-only ranking is strong (#1), cross-library
ranking of the German original is unstable across runs.

## GND confirmations (Stage 1)
lobid GND exact-name + birth-year: 6 confirmed (Marx, Descartes,
Spencer, Adam Smith, Hugo, Nishida), 7 attempted authors not
confirmed by this method. See docs/b11-dataset-design.md.

## Upstream state
- NDL page API: still returning HTTP 500 upstream (observed
  since b10; surfaced honestly as 502 by the service, never
  rewritten as success).
- VIAF: still Cloudflare-blocked from this network; client
  remains off by default; no evasion attempted.
- Gallica / Finna live from this network: not re-attempted in
  b11 beyond the Kant/DDB and lobid checks above; their b8/b10
  status (403 from this network) stands unretested rather than
  re-claimed.

## External session residual constraints (section 70)
Re-checked by the unchanged b9/b10 suites in the full pytest
run: session caps, atomic reservation, idle TTL, per-user
budgets and consent re-checks all pass as at b10. The external
profile remains 5 tools with no real-library text transfer
(the shipped consent matrix still marks every library
`ocr_rights: "unknown"`).
