# External MCP — incident response

## Suspected unauthorised use or token compromise

1. Set `GLM_EXTERNAL_DISABLED=1` and restart the external
   profile (local profiles are unaffected).
2. Revoke the affected users server-side; rotate
   `GLM_EXTERNAL_CONTINUATION_SECRET`.
3. At the authorization server: revoke the client/tokens,
   rotate signing keys (JWKS), and review issuance logs.
4. If a tunnel exists: stop tunnel-client, revoke the runtime
   API key, and remove the workspace association
   (docs/secure-mcp-tunnel.md).
5. Review the audit log (pseudonymised; correlate via the AS's
   own records, not by deanonymising the log).

## Suspected rights-violating transfer

1. Disable excerpts first (`GLM_EXTERNAL_EXCERPTS` unset) —
   bibliographic/reference traffic can continue.
2. Identify the item, library and decision inputs from the
   audit log's rights categories; reproduce the decision with
   `decide_transfer` locally.
3. If the matrix row is wrong, correct it with its official
   source and add a regression case to the security
   evaluation; if the item statement was misclassified, fix
   the classifier with a test.
4. Record the incident in the changelog of the affected doc.

## Suspected workspace exposure

The external profile has no code path to the workspace;
treat any such report as a potential boundary breach: stop
the external profile, verify the import boundary
(`global-library-mcp doctor` workspace_separation check and
tests/test_b9_external.py), and check whether a non-external
component (web UI, another profile) was the actual surface.

## Upstream abuse / rate-limit incident

Per-user budgets and the circuit breaker bound the blast
radius. Identify the pseudonym in the audit log, revoke that
user, and confirm upstream attempts returned to baseline
before re-enabling.
