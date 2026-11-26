# Multilingual search architecture (b6)

## Layers

1. **DiscoveryQueryAnalysis** (discovery.py) - query language
   (value/confidence/mixed/unknown/user_override), requested
   document languages, terms, matched lexicon concepts,
   authors (specific vs ambiguous), works, era. Discovery
   only; admission keeps using QuestionAnalysis.
2. **Lexicon** (lexicon.py + data/search_lexicon.json) -
   concepts/authors/works with per-language labels, historical
   variants, related terms and excluded confusions, sources
   and verification status. Validated at load; malformed data
   fails loudly.
3. **QueryExpansionEngine** (expansion.py) - turns an analysis
   into a bounded plan: variants with kind, relation
   (synonym/near-synonym/translation/spelling/related),
   reason, source, priority; skipped candidates with reasons;
   budget report. Not a translator: it expands search terms
   from dictionary entries, never sentences.
4. **Service integration** (service.py) - the plan merges
   into the bibliographic variant loop (engine variants right
   after the full query), routes by language when the user
   has not pinned libraries, tracks the matched variant per
   record, and post-processes materials with resolution links,
   filters, grouping and reasons. The evidence pipeline is
   downstream and unchanged.
5. **Presentation** - MCP options + discovery block; Web API
   parameters; Web UI advanced fields and discovery panel.

## Invariants

- Original text is never rewritten for quotation, citation or
  OCR; normalisation exists only inside search variants.
- A dictionary association (work/author/concept) is a
  candidate with a stated basis, never an identity proof.
- Expansion can be disabled per kind (multilingual /
  historical); the original query always runs first.
- Every variant is deduplicated and capped per mode; the
  HTTP budget, response caps, concurrency and cancellation
  from b3 are unchanged.
- Document language and holding-institution country are
  separate fields throughout; a German library's English book
  is an English document.

## Adding a language later

1. Add labels to lexicon entries for the new language code.
2. Add stopwords + a detection signal set in discovery.py.
3. Add a routing entry for the language in service.py and in
   the evaluation harness.
4. Add evaluation cases in the new language before claiming
   quality.
