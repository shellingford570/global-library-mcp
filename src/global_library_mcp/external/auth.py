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

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import jwt as _jwt

from global_library_mcp.external.control import ExternalConfig

# Tool -> required scope (section 18). tools/list filtering is
# cosmetic; every tools/call re-checks here server-side. The
# final-review round reduced the external profile to five
# tools, so only four scopes exist; there is deliberately no
# workspace, excerpt, verification or comparison scope.
TOOL_SCOPES: dict[str, str] = {
    "search": "catalog:search",
    "fetch": "metadata:read",
    "list_libraries": "libraries:read",
    "get_library_capabilities": "libraries:read",
    "get_document_rights": "references:read",
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


JWKS_MAX_BYTES = 256 * 1024
JWKS_TIMEOUT_S = 5.0
JWKS_CACHE_TTL_S = 600.0


class _JwksUrlCache:
    """JWKS fetched from the configured URL under explicit
    limits (final review P0): https-only public destinations
    validated like any other upstream URL (loopback http only
    in local test mode), a 5-second fetch deadline, a 256 KiB
    size cap, and a 10-minute cache. The fetch never follows
    redirects and never carries credentials."""

    def __init__(self, url: str, *, local_test_mode: bool):
        self._url = url
        self._local_test = local_test_mode
        self._fetched_at = 0.0
        self._jwk_set = None
        self._lock = threading.Lock()

    def _validate_url(self) -> None:
        parts = urlsplit(self._url)
        host = (parts.hostname or "").lower()
        if self._local_test and parts.scheme == "http" \
                and host in ("127.0.0.1", "localhost", "::1"):
            return  # synthetic test AS on loopback only
        from global_library_mcp.http import validate_fetch_url

        validate_fetch_url(self._url)

    def _load(self):
        import httpx
        from jwt import PyJWKSet

        try:
            self._validate_url()
        except AuthError:
            raise
        except Exception as exc:  # AdapterError from URL validation
            raise AuthError("jwks_destination_refused") from exc
        try:
            with httpx.Client(timeout=JWKS_TIMEOUT_S,
                              follow_redirects=False) as client:
                with client.stream("GET", self._url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes(65536):
                        body.extend(chunk)
                        if len(body) > JWKS_MAX_BYTES:
                            raise AuthError("jwks_too_large")
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError("jwks_unavailable") from exc
        try:
            document = json.loads(bytes(body))
        except ValueError as exc:
            raise AuthError("jwks_invalid") from exc
        self._jwk_set = PyJWKSet.from_dict(document)
        self._fetched_at = time.time()

    def key_for(self, token: str):
        with self._lock:
            if self._jwk_set is None \
                    or time.time() - self._fetched_at > JWKS_CACHE_TTL_S:
                self._load()
            header = _jwt.get_unverified_header(token)
            for key in self._jwk_set.keys:
                if key.key_id == header.get("kid"):
                    return key.key
            raise AuthError("unknown_signing_key")


class TokenValidator:
    def __init__(self, config: ExternalConfig):
        self.config = config
        self._jwks_url_cache = None

    def _key_for(self, token: str):
        cfg = self.config
        if cfg.test_hs_secret:
            return cfg.test_hs_secret
        if cfg.jwks:
            from jwt import PyJWKSet
            jwk_set = PyJWKSet.from_dict(cfg.jwks)
            header = _jwt.get_unverified_header(token)
            for key in jwk_set.keys:
                if key.key_id == header.get("kid"):
                    return key.key
            raise AuthError("unknown_signing_key")
        if cfg.jwks_url:
            if self._jwks_url_cache is None:
                self._jwks_url_cache = _JwksUrlCache(
                    cfg.jwks_url, local_test_mode=cfg.local_test_mode)
            return self._jwks_url_cache.key_for(token)
        raise AuthError("no_key_source_configured")

    def validate(self, token: str) -> Principal:
        if not token or not isinstance(token, str):
            raise AuthError("missing_token")
        cfg = self.config
        # HS256 exists ONLY for the synthetic local test AS; a
        # production (JWKS) configuration never accepts it.
        algorithms = ["HS256"] if (cfg.test_hs_secret and cfg.local_test_mode) \
            else ["RS256", "ES256"]
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
        if not str(claims.get("sub") or "").strip():
            raise AuthError("invalid_token")
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
