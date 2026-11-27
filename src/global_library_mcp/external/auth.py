"""OAuth 2.1 resource-server validation (b9 brief sections
17-18), following the MCP authorization specification
(2025-11-25): the server validates access tokens issued by an
external authorization server - signature against the AS JWKS,
issuer, audience (the token must be bound to THIS resource),
expiry and scopes. Signing and issuance stay with the AS; no
cryptography is invented here (PyJWT does the verification).

Local verification uses either a pinned JWKS document or, in
local test mode only, an HS256 secret shared with the
synthetic test authorization server. Neither is a production
credential.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import jwt as _jwt

from global_library_mcp.external.control import ExternalConfig

# Tool -> required scope (section 18). tools/list filtering is
# cosmetic; every tools/call re-checks here server-side.
TOOL_SCOPES: dict[str, str] = {
    "search": "catalog:search",
    "fetch": "metadata:read",
    "list_libraries": "libraries:read",
    "get_library_capabilities": "libraries:read",
    "get_document_rights": "references:read",
    "verify_original_reference": "originals:verify",
    "get_allowed_excerpt": "excerpts:read",
    "research_materials_external": "catalog:search",
    "compare_documents_external": "comparisons:read",
}
ALL_SCOPES = sorted(set(TOOL_SCOPES.values()))


@dataclass
class Principal:
    user_id: str
    scopes: set[str] = field(default_factory=set)
    client_id: str = ""
    expires_at: int = 0


class AuthError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind   # stable, secret-free error class


class TokenValidator:
    def __init__(self, config: ExternalConfig):
        self.config = config
        self._jwks_client = None

    def _key_for(self, token: str):
        cfg = self.config
        if cfg.test_hs_secret:
            return cfg.test_hs_secret
        if cfg.jwks:
            client = _jwt.PyJWKClient.__new__(_jwt.PyJWKClient)
            from jwt import PyJWKSet
            jwk_set = PyJWKSet.from_dict(cfg.jwks)
            header = _jwt.get_unverified_header(token)
            for key in jwk_set.keys:
                if key.key_id == header.get("kid"):
                    return key.key
            raise AuthError("unknown_signing_key")
        if cfg.jwks_url:
            if self._jwks_client is None:
                self._jwks_client = _jwt.PyJWKClient(cfg.jwks_url)
            return self._jwks_client.get_signing_key_from_jwt(token).key
        raise AuthError("no_key_source_configured")

    def validate(self, token: str) -> Principal:
        if not token or not isinstance(token, str):
            raise AuthError("missing_token")
        cfg = self.config
        algorithms = ["HS256"] if cfg.test_hs_secret else ["RS256", "ES256"]
        try:
            key = self._key_for(token)
            claims = _jwt.decode(
                token, key, algorithms=algorithms,
                audience=cfg.audience, issuer=cfg.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]})
        except AuthError:
            raise
        except _jwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired") from exc
        except _jwt.InvalidAudienceError as exc:
            raise AuthError("wrong_audience") from exc
        except _jwt.InvalidIssuerError as exc:
            raise AuthError("wrong_issuer") from exc
        except _jwt.InvalidSignatureError as exc:
            raise AuthError("bad_signature") from exc
        except _jwt.InvalidTokenError as exc:
            raise AuthError("invalid_token") from exc
        scope_text = claims.get("scope") or ""
        scopes = set(scope_text.split()) if isinstance(scope_text, str) \
            else set(claims.get("scp") or [])
        return Principal(
            user_id=str(claims["sub"]), scopes=scopes,
            client_id=str(claims.get("client_id") or claims.get("azp") or ""),
            expires_at=int(claims.get("exp") or 0))


def protected_resource_metadata(resource_url: str, issuer: str,
                                scopes: list[str]) -> dict[str, Any]:
    """RFC 9728 Protected Resource Metadata document."""
    return {
        "resource": resource_url,
        "authorization_servers": [issuer] if issuer else [],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_documentation": "https://github.com/shellingford570/global-library-mcp",
    }


def www_authenticate(resource_metadata_url: str, scopes: list[str]) -> str:
    scope = " ".join(scopes)
    return (f'Bearer resource_metadata="{resource_metadata_url}", '
            f'scope="{scope}"')


def check_scope(principal: Principal, tool: str) -> None:
    required = TOOL_SCOPES.get(tool)
    if required is None:
        raise AuthError("unknown_tool")
    if required not in principal.scopes:
        raise AuthError("insufficient_scope")
