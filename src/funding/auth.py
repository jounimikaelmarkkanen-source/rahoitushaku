import re
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

bearer = HTTPBearer(auto_error=False, scheme_name="EntraID", bearerFormat="JWT")

@lru_cache(maxsize=8)
def key_client(tenant):
    return PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True)


def authorise(request: Request, permission="Funding.Read"):
    cfg = request.app.state.cfg
    if cfg.auth_mode == "local":
        if not request.client or request.client.host not in ("127.0.0.1", "::1", "testclient"):
            raise HTTPException(403, "Local mode accepts loopback requests only")
        return "local-operator"
    if cfg.auth_mode != "entra" or not re.fullmatch(r"[0-9a-fA-F-]{36}", cfg.entra_tenant_id) or not cfg.entra_audience:
        raise HTTPException(503, "Authentication is not configured")
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Microsoft Entra access token required", headers={"WWW-Authenticate": "Bearer"})
    token = header.removeprefix("Bearer ")
    try:
        signing_key = key_client(cfg.entra_tenant_id).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=cfg.entra_audience,
                            issuer=f"https://login.microsoftonline.com/{cfg.entra_tenant_id}/v2.0",
                            options={"require": ["exp", "iat", "nbf", "aud", "iss", "oid", "tid"]})
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid access token") from None
    permissions = set(claims.get("roles", [])) | set(claims.get("scp", "").split())
    if claims["tid"] != cfg.entra_tenant_id or permission not in permissions:
        raise HTTPException(403, "Required API permission is missing")
    return claims["oid"]


def reader(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    return authorise(request)


def reviewer(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    return authorise(request, "Funding.Review")
