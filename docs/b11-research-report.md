# b11 Research Report (sections 46-48)

`generate_research_report` in `src/global_library_mcp/synthesis.py`
produces a report as a JSON dict plus a rendered Markdown form
(both mandatory). Sections: summary (with research progress and
graph counts), research questions, claims by state, comparisons,
timeline, rights state, unresolved references, reproducibility.

Reproducibility fields (section 47): report_id, schema_version
(`b11-report-1`), project_id, snapshot_id (SHA-256 over the
project's documents/citations/artefacts state - it changes when
the state changes), generated_at, code_version, git_commit,
ranking_mode, model_id/model_revision (null when no model was
involved), evidence_policy_version (`b11-evidence-policy-1`),
rights_policy_version (`b11-rights-policy-1`), source_count,
unresolved_count.

Reference integrity: every record/citation reference drawn from
artefacts is checked against the project's own documents and
citations. Unresolvable references are excluded from the
evidence sections, listed under unresolved references, and
counted in `unresolved_count`. Note-envelope (user_asserted)
artefacts never feed a report.

Rights (section 48): the report contains metadata and the
researcher's own claim/question text only - no upstream OCR
text is inserted, so nothing bypasses the citation/rights
machinery; rights state is read from the current store at
generation time (a rights change after saving is reflected on
regeneration). Already-downloaded external files cannot be
retroactively recalled; the report makes no such claim.
