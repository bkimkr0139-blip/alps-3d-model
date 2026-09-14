from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError

from app.config import settings

bearer_scheme = HTTPBearer()

_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        resp = httpx.get(settings.keycloak_jwks_url, timeout=5.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


@dataclass(frozen=True)
class CurrentUser:
    subject: str
    username: str
    roles: frozenset[str]


def _decode(token: str) -> dict:
    jwks = _get_jwks()
    unverified_header = jwt.get_unverified_header(token)
    key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
    if key is None:
        # key rotated on the Keycloak side — refresh once and retry
        global _jwks_cache
        _jwks_cache = None
        jwks = _get_jwks()
        key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown signing key")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=None,
            options={"verify_aud": False, "verify_iss": False},
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    # Keycloak stamps `iss` from the Host header it was reached on — accept
    # any of the known ways to reach this deployment (see config.py).
    if claims.get("iss") not in settings.keycloak_accepted_issuers:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"unrecognized issuer: {claims.get('iss')}")
    return claims


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    claims = _decode(credentials.credentials)
    roles = frozenset(claims.get("realm_access", {}).get("roles", []))
    return CurrentUser(
        subject=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        roles=roles,
    )


def require_role(*allowed_roles: str):
    """RBAC gate: run BEFORE any handler touches the DB (§10.1 step 1)."""

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "platform_admin" in user.roles:
            return user
        if not user.roles.intersection(allowed_roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"requires one of roles: {sorted(allowed_roles)}",
            )
        return user

    return _dependency
