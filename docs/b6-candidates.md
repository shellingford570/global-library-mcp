# Next-phase candidates after b5 (planning only - not started)

Prepared under the b5 final brief (section 28). Nothing here
is approved or started; it is the comparison the next brief
will decide from.

## Candidate A - Multilingual Research
Deeper Japanese/English/German/French search quality:
author-name and original-title search, historical-spelling
normalisation, cross-language discovery, and filters for era,
region and material type, plus deeper per-document research.
- Researcher value: high - search quality is the daily pain.
- Difficulty: medium (builds on the b5 variant foundation).
- API terms: unchanged; no new providers.
- Safety: unchanged surface; no new external calls.
- Cost: none (no paid APIs).
- Impact on existing features: improves search/materials;
  admission rules must stay frozen while ranking improves.
- External approval: none needed beyond a normal brief.

## Candidate B - Global Coverage II
Gallica live verification (from an allowed network), then
Finna (Finland), DPLA, KB/Delpher, BNE, ONB, Japan Search -
each only where an official API offers page-level OCR with
provable mapping.
- Researcher value: high for European newspaper/book corpora.
- Difficulty: medium-high (one adapter at a time, each with
  live verification and terms review).
- API terms: varies; Trove-like key issuance would need its
  own approval; DPLA needs a free key (approval step).
- Safety: same SSRF/mapping discipline as b5-final.
- Cost: none expected.
- Impact: additive; opt-in routing protects defaults.
- External approval: per-provider key issuance only.

## Candidate C - Research Workspace
Project-scoped material organisation: research history,
bookmarks, saved citations and comparisons, BibTeX/RIS/
CSL-JSON export, a Zotero-integration study.
- Researcher value: high for repeated real research use.
- Difficulty: medium (local state, export formats).
- API terms: none new.
- Safety: local-only data; export is user-initiated.
- Cost: none.
- Impact: additive UI/API surface; search core untouched.
- External approval: Zotero write access would need approval.

## Candidate D - External MCP Readiness
Rights-policy-gated external transmission rules, an external
read-only profile, per-tool time/response caps, per-user
budgets, authentication/authorisation design, Secure MCP
Tunnel connection preparation.
- Researcher value: medium now, high later (ChatGPT etc.).
- Difficulty: high (auth and policy are the hard parts).
- API terms: depends on the receiving platform's terms.
- Safety: this IS the safety work - nothing external ships
  before the policy layer exists.
- Cost: possible platform plans (not approved here).
- Impact: must not weaken the local research profile.
- External approval: required (tunnel creation, plan changes
  and any external transmission are all separately approved).

## Recommendation
**Candidate A (Multilingual Research), with one B item
(Gallica live verification) folded in when an allowed network
is available.** Rationale: b5 widened coverage; the measured
bottleneck for real research is still finding the right
material across languages and historical spellings, and A
improves every existing institution at once without new
external dependencies or approvals. B remains the follow-up
once A lands; C compounds value after search quality rises;
D should wait until the rights-policy design can be its own
focused phase.
