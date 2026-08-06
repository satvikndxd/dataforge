"""Authentication and authorization primitives.

- Password hashing: PBKDF2-HMAC-SHA256 (stdlib; no external deps).
- Tokens: HS256 JWTs (stdlib hmac implementation, RFC 7519 subset).
- API keys: `df_live_<random>`; only the SHA-256 digest is stored.
- RBAC: Owner > Admin > Builder > Reviewer > Viewer (+ BillingAdmin).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum

from backend.core.config import get_settings

# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    BILLING_ADMIN = "billing_admin"


_ROLE_RANK = {
    Role.VIEWER: 0,
    Role.BILLING_ADMIN: 0,
    Role.REVIEWER: 1,
    Role.BUILDER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


def role_at_least(role: Role | str, minimum: Role) -> bool:
    role = Role(role)
    return _ROLE_RANK.get(role, -1) >= _ROLE_RANK[minimum]


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# JWT (HS256)
# --------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


@dataclass
class TokenClaims:
    sub: str          # user id
    org: str          # organization id
    role: str
    kind: str         # access | refresh
    exp: int
    iat: int


def create_token(user_id: str, org_id: str, role: str, kind: str = "access") -> str:
    settings = get_settings()
    ttl = (
        settings.access_token_ttl_seconds
        if kind == "access"
        else settings.refresh_token_ttl_seconds
    )
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "org": org_id, "role": role, "kind": kind, "iat": now, "exp": now + ttl}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}." \
                    f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(settings.secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_token(token: str) -> TokenClaims | None:
    settings = get_settings()
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(settings.secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return TokenClaims(
            sub=payload["sub"],
            org=payload["org"],
            role=payload.get("role", Role.VIEWER.value),
            kind=payload.get("kind", "access"),
            exp=payload["exp"],
            iat=payload.get("iat", 0),
        )
    except (ValueError, KeyError, TypeError):
        return None


# --------------------------------------------------------------------------
# API keys
# --------------------------------------------------------------------------


def generate_api_key() -> tuple[str, str]:
    """Return (plaintext_key, sha256_digest). Plaintext is shown once."""
    plaintext = f"df_live_{secrets.token_urlsafe(32)}"
    return plaintext, hashlib.sha256(plaintext.encode()).hexdigest()


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
