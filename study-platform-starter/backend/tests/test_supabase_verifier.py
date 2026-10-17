from __future__ import annotations

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.supabase import AuthenticationError, SupabaseTokenVerifier

ISSUER = "https://supabase.example.com"
JWKS_URL = "https://supabase.example.com/.well-known/jwks.json"
AUDIENCE = "authenticated"


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_key, private_pem


def encode_token(private_pem: bytes, **overrides) -> str:
    now = dt.datetime.now(tz=dt.timezone.utc)
    claims = {
        "sub": "user_123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
        "name": "Test User",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-kid"})


def build_verifier(public_key, **overrides) -> SupabaseTokenVerifier:
    params = dict(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        audience=AUDIENCE,
        key_resolver=lambda _token: public_key,
    )
    params.update(overrides)
    return SupabaseTokenVerifier(**params)


def test_valid_token_is_accepted(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = build_verifier(private_key.public_key())
    identity = verifier.verify(encode_token(private_pem))
    assert identity.user_id == "user_123"
    assert identity.claims.get("aud") == AUDIENCE
    assert identity.claims["name"] == "Test User"


def test_expired_token_is_rejected(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = build_verifier(private_key.public_key())
    past = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=2)
    token = encode_token(private_pem, iat=int(past.timestamp()), exp=int((past + dt.timedelta(minutes=1)).timestamp()))
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_wrong_issuer_is_rejected(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = build_verifier(private_key.public_key())
    token = encode_token(private_pem, iss="https://evil.example.com")
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_wrong_audience_is_rejected(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = build_verifier(private_key.public_key())
    token = encode_token(private_pem, aud="evil-aud")
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_missing_audience_is_rejected(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = build_verifier(private_key.public_key())
    token = jwt.encode(
        {
            "sub": "user_123",
            "iss": ISSUER,
            "iat": int(dt.datetime.now(tz=dt.timezone.utc).timestamp()),
            "exp": int((dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(minutes=5)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    with pytest.raises(AuthenticationError):
        verifier.verify(token)


def test_invalid_signature_is_rejected(rsa_keypair):
    _private_key, private_pem = rsa_keypair
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = build_verifier(other_key.public_key())
    with pytest.raises(AuthenticationError):
        verifier.verify(encode_token(private_pem))


def test_unconfigured_verifier_rejects(rsa_keypair):
    private_key, private_pem = rsa_keypair
    verifier = SupabaseTokenVerifier(issuer="", jwks_url="", audience=AUDIENCE)
    assert verifier.configured is False
    with pytest.raises(AuthenticationError):
        verifier.verify(encode_token(private_pem))


def test_key_resolver_failure_is_normalized():
    def broken_resolver(_token: str):
        raise RuntimeError("jwks unavailable")

    verifier = SupabaseTokenVerifier(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        audience=AUDIENCE,
        key_resolver=broken_resolver,
    )
    with pytest.raises(AuthenticationError):
        verifier.verify("not-a-real-token")
