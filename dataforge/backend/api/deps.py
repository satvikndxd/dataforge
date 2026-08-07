"""API dependencies: auth (JWT + API keys), RBAC guards, rate limiting."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from backend.core.config import get_settings
from backend.core.security import Role, decode_token, role_at_least
from backend.services.identity import resolve_api_key


@dataclass
class Principal:
    user_id: str
    org_id: str
    role: str


def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    if x_api_key:
        resolved = resolve_api_key(x_api_key)
        if resolved:
            return Principal(**resolved)
        raise HTTPException(status_code=401, detail="invalid API key")
    if authorization and authorization.lower().startswith("bearer "):
        claims = decode_token(authorization.split(" ", 1)[1])
        if claims and claims.kind == "access":
            return Principal(user_id=claims.sub, org_id=claims.org, role=claims.role)
        raise HTTPException(status_code=401, detail="invalid or expired token")
    raise HTTPException(status_code=401, detail="authentication required")


def require_role(minimum: Role):
    def _guard(principal: Principal = Depends(get_principal)) -> Principal:
        if not role_at_least(principal.role, minimum):
            raise HTTPException(status_code=403,
                                detail=f"requires role >= {minimum.value}")
        return principal

    return _guard


# ---------------------------------------------------------------------------
# Sliding-window rate limiter (per principal); Redis-backed in production.
# ---------------------------------------------------------------------------

_windows: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    now = time.time()
    window = _windows[principal.org_id]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded",
                            headers={"Retry-After": "60",
                                     "X-RateLimit-Limit": str(limit),
                                     "X-RateLimit-Remaining": "0"})
    window.append(now)
    request.state.rate_limit = (limit, limit - len(window))
    return principal
