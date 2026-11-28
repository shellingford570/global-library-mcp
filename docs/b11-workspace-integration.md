# b11 Workspace Integration (sections 49-54)

## Local Web API (inside the existing workspace boundary)
New routes under `/api/workspace/projects/<pid>/research/` -
same loopback/Host/Origin/CSRF/session machinery as every
workspace route; mutations are POST with the session CSRF
token; unknown projects return 404:

- GET `progress` - research progress (server-generated counts
  only; untrusted artefacts counted separately)
- GET `artefacts` - artefacts with their trust state
- GET `graph?limit&offset` - Evidence Graph (paged)
- GET `timeline` - timeline built from timeline artefacts
- POST `questions` {question} - structure + save a research
  question artefact
- POST `claims` {statement} - structure a claim (with the
  per-field extraction states) + save
- POST `reports` - generate a research report (Markdown+JSON),
  also saved as a `research_report` artefact
- GET `reports` - list saved report artefacts
- POST `revalidate` - rebuild graph/progress from current
  store state

New artefact kinds (b11): `timeline`, `research_report`,
`semantic_search` join the b10 kinds under the same recursive
allowlist schema.

## UI
A 「研究検証」 tab in the workspace: progress counts, question /
claim structuring forms (unextracted fields are reported back),
graph summary with edge states, timeline, report generation
with Markdown/JSON download, revalidation, and the artefact
list with trust states. All rendering uses textContent/DOM
APIs (no stored-XSS surface), as in the rest of the workspace.

## State expression (section 52)
Candidate/unconfirmed states are labelled as candidates in
text; no green "verified" styling is used for anything the
server has not verified; independence-unknown is shown as
unknown; NLI/semantic scores are never rendered as
probabilities of correctness (the tab shows counts and states,
not scores-as-truth).

## Zotero format compatibility (section 53)
The b7/b10 format checks (13/13) are unchanged. Export
improvements: BibTeX gains `origtitle` (BibLaTeX, read by
Zotero) when an original title distinct from the display title
is recorded; RIS gains explicit `Translator:` and
`Original title:` notes; CSL JSON gains `original-title`.
Author/translator roles and the deterministic stable citation
keys are unchanged. The Zotero APPLICATION was not installed
or run: real-machine import verification remains an
additional-approval item (needs tana's machine + Zotero
install), exactly as recorded since b7.

## MCP profiles (section 54)
Unchanged: full 15 / research 14 / external 5 tools.
Research artefacts, the Evidence Graph and reports are NOT
exposed through the external MCP profile; they exist only in
the local workspace (store + local Web API).
