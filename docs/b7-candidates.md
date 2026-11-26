# b7 candidates - short comparison (plan only, not started)

Roadmap position (provisional): b7 Research Workspace &
Advanced Comparison; b8 Global Coverage II; b9 External MCP
Readiness; AI Experimental separate; then v1.0.0.

| Candidate area | What it adds | Cost / risk | Fit with b6 |
|---|---|---|---|
| Research projects + history | Saved investigations, resumable sessions | Needs a persistence design + privacy posture | High: discovery is now good enough to be worth saving |
| Bookmarks + saved citations/comparisons | Keep materials and comparisons with their provenance | Small; builds on citation keys | High |
| Bibliographic export (BibTeX / RIS / CSL JSON) | Interop with reference managers | Small, deterministic; CSL JSON needs a style subset decision | High, low risk |
| Zotero integration | Push saved items to a Zotero library | External account/API key decisions; write access to a user library needs explicit approval design | Medium |
| Literature notes | Free-text notes attached to records/projects | Needs storage + search | Medium |
| Relation graph between materials | Work/edition/author graphs from resolution links | Resolution is candidate-grade; graph must show confidence, not facts | Medium: powerful but easy to overstate |
| Chronological / thematic organisation | Timeline and topic views over saved sets | Presentation layer over projects | Medium |

Recommendation (for tana's decision, not a start order):
begin b7 with the workspace core - projects, history,
bookmarks, saved citations/comparisons - plus BibTeX/RIS/
CSL JSON export, since all of it is local, deterministic
and builds directly on b6's provenance model. Treat the
relation graph as an explicitly-labelled candidate view,
and defer Zotero write integration until its account and
approval design is decided separately.
