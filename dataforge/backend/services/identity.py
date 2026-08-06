"""Identity service: registration, login, API keys (spec §16.1–16.3)."""
from __future__ import annotations

import re

from backend.core.ids import new_id
from backend.core.security import (
    Role,
    create_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from backend.db.base import session_scope
from backend.db.models import ApiKey, Organization, User
from backend.events.bus import get_event_bus


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    return slug


class IdentityError(Exception):
    pass


def register(org_name: str, email: str, password: str, user_name: str = "") -> dict:
    """Bootstrap an organization with an Owner user."""
    if len(password) < 8:
        raise IdentityError("password must be at least 8 characters")
    with session_scope() as session:
        if session.query(User).filter_by(email=email.lower()).one_or_none():
            raise IdentityError("email already registered")
        slug = _slugify(org_name)
        n = 1
        while session.query(Organization).filter_by(slug=slug).one_or_none():
            n += 1
            slug = f"{_slugify(org_name)}-{n}"
        org = Organization(id=new_id("org"), name=org_name, slug=slug)
        user = User(
            id=new_id("usr"), org_id=org.id, email=email.lower(), name=user_name,
            password_hash=hash_password(password), role=Role.OWNER.value,
        )
        session.add_all([org, user])
        org_id, user_id, role = org.id, user.id, user.role

    get_event_bus().emit("org.created", tenant_id=org_id, actor=f"user:{user_id}",
                         payload={"resource_type": "organization", "resource_id": org_id})
    return _token_pair(user_id, org_id, role)


def login(email: str, password: str) -> dict:
    with session_scope() as session:
        user = session.query(User).filter_by(email=email.lower()).one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise IdentityError("invalid credentials")
        return _token_pair(user.id, user.org_id, user.role)


def refresh(user_id: str, org_id: str, role: str) -> dict:
    return _token_pair(user_id, org_id, role)


def _token_pair(user_id: str, org_id: str, role: str) -> dict:
    return {
        "access_token": create_token(user_id, org_id, role, "access"),
        "refresh_token": create_token(user_id, org_id, role, "refresh"),
        "token_type": "bearer",
        "user_id": user_id,
        "org_id": org_id,
        "role": role,
    }


def create_key(org_id: str, user_id: str, name: str, scopes: list[str] | None = None) -> dict:
    plaintext, digest = generate_api_key()
    key_id = new_id("key")
    with session_scope() as session:
        session.add(ApiKey(id=key_id, org_id=org_id, user_id=user_id, name=name,
                           key_hash=digest, scopes=scopes or ["*"]))
    return {"id": key_id, "name": name, "key": plaintext,
            "note": "store this key now; it is not retrievable later"}


def resolve_api_key(plaintext: str) -> dict | None:
    digest = hash_api_key(plaintext)
    with session_scope() as session:
        key = session.query(ApiKey).filter_by(key_hash=digest, revoked=False).one_or_none()
        if key is None:
            return None
        user = session.get(User, key.user_id)
        return {"user_id": key.user_id, "org_id": key.org_id,
                "role": user.role if user else Role.BUILDER.value}
