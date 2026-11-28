# b12 Candidates - DESIGN ONLY (section 80)

Candidate theme: **"Research Agent & Investigation
Orchestration"**. Nothing in this document is implemented,
scheduled or approved; b12 implementation requires tana's
separate approval, exactly as b11 did.

## Candidate areas (design notes only)

1. **Investigation orchestration**: multi-step research plans
   (question decomposition -> searches -> evidence collection
   -> synthesis) executed inside the existing HTTP budget and
   consent machinery, with every step recorded as a
   server-generated artefact and resumable state. The agent
   proposes; the frozen admission gates still decide.
2. **Reviewer workflow completion**: if tana approves
   recruiting or designates reviewers, run the b11 blind
   review package for real and publish agreement metrics
   (kappa / alpha) with the review protocol.
3. **NLI model acquisition** (from the b11 approval
   proposal): download mDeBERTa-v3-base-mnli-xnli under the
   section-25 terms, run shadow evaluation on the b11 proxy
   set plus ja/fi-focused cases, and report before any
   governing use is even considered.
4. **Zotero real-machine verification**: with tana's
   environment, import the b11 exports into a real Zotero and
   record field-level fidelity (roles, original titles, keys).
5. **Coverage expansion II**: revisit blocked sources
   (Gallica 403, Finna live 403 from this network, DPLA key)
   only through legitimate channels; no evasion.
6. **External profile blockers**: DNS pinning implementation
   design, production IdP design - prerequisites for any real
   external connection, which itself stays separately gated.

## Explicitly not authorised by this document
Implementation of any item above, model downloads, paid API
use, public deployment, reviewer recruitment, Zotero
installation, tunnel creation, or a ChatGPT connection.
