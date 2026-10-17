"""Supabase Auth token verification.

Verifies Supabase-issued session JWTs server-side: signature via JWKS (Supabase
uses asymmetric signing keys, ES256 by default), issuer, audience, expiry /
issued-at, and subject. The signing-key resolver is injectable so tests can
verify against locally generated keys without network access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

SigningKeyResolver = Callable[[str], Any]

DEFAULT_AUDIENCE = "authenticated"
ALLOWED_ALGORITHMS = ("ES256", "RS256")


class AuthenticationError(Exception):
    """Raised when a token cannot be verified. Message is safe to expose."""


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: str
    claims: dict[str, Any]
    email: str | None = None


class SupabaseTokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: str,
        audience: str = DEFAULT_AUDIENCE,
        key_resolver: SigningKeyResolver | None = None,
        leeway_seconds: int = 60,
    ) -> None:
        self.issuer = issuer.strip()
        self.jwks_url = jwks_url.strip()
        self.audience = audience.strip()
        self._key_resolver = key_resolver
        self._jwks_client: PyJWKClient | None = None
        self.leeway_seconds = leeway_seconds

    @property
    def configured(self) -> bool:
        return bool(self.issuer and self.jwks_url)

    def _resolve_key(self, token: str) -> Any:
        if self._key_resolver is not None:
            return self._key_resolver(token)
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self.jwks_url)
        return self._jwks_client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> VerifiedIdentity:
        if not self.configured:
            raise AuthenticationError("Authentication provider is not configured.")
        if not token or not token.strip():
            raise AuthenticationError("Missing authentication token.")

        try:
            key = self._resolve_key(token)
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize all resolver failures
            raise AuthenticationError("Unable to resolve the token signing key.") from exc

        decode_kwargs: dict[str, Any] = {
            "algorithms": list(ALLOWED_ALGORITHMS),
            "issuer": self.issuer,
            "leeway": self.leeway_seconds,
            "options": {"require": ["exp", "iat", "sub"], "verify_aud": bool(self.audience)},
        }
        if self.audience:
            decode_kwargs["audience"] = self.audience

        try:
            claims = jwt.decode(token, key, **decode_kwargs)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired token.") from exc

        user_id = claims.get("sub")
        if not user_id:
            raise AuthenticationError("Token is missing a subject.")

        email = claims.get("email")
        return VerifiedIdentity(
            user_id=str(user_id),
            claims=dict(claims),
            email=email if isinstance(email, str) and email.strip() else None,
        )


__all__ = [
    "ALLOWED_ALGORITHMS",
    "AuthenticationError",
    "DEFAULT_AUDIENCE",
    "SigningKeyResolver",
    "SupabaseTokenVerifier",
    "VerifiedIdentity",
]
