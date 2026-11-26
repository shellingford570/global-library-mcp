# Multilingual comparison (b6, section 25)

compare_documents rows now separate, per aspect:

- `shared_terms` / `partial_terms` / `unique_terms` -
  lexical overlap of the verified OCR texts (unchanged).
- `dictionary_concept_overlap` - lexicon concepts whose
  labels appear in at least two documents' texts, e.g.
  English "steam engine" and German "Dampfmaschine" meeting
  at concept:steam-engine. A dictionary correspondence only.
- `possible_related_concepts` - the same list, named for
  what it is.
- `semantic_comparison: "not_checked"` - always. Two
  documents sharing a dictionary concept have NOT been shown
  to agree about anything; technical descriptions, claims
  and arguments are compared by the reader from the
  excerpts, which remain in the original language, untranslated.

Bibliographic comparison (authors, years, editions,
languages, holding institutions) rides on the per-document
entries and, for materials, on work_link / duplicate_group:
same work in different editions or translations is grouped
for presentation while every record keeps its own citation
identity.

## Final-review note

For 3-4 document comparisons, concept overlap is reported
as `shared_by_all_documents` vs `shared_by_some_documents`
so partial sharing is not presented as unanimity.
`semantic_comparison` remains `not_checked`: dictionary
concept overlap is a lexical signal, never a claim that the
documents agree in thought, argument or explanation.
