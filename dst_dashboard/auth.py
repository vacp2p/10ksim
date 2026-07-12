"""JWT issuing and verification for admin (write) API access."""

import logging
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dst_dashboard.config.constants import INSECURE_DEFAULT_JWT_SECRET, Constants

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
JWT_SCOPE = "admin"

_bearer_scheme = HTTPBearer(auto_error=False)

if str(Constants.DST_JWT_SECRET) == INSECURE_DEFAULT_JWT_SECRET:
    logger.warning(
        "DST_JWT_SECRET is not set - using an insecure development-only default. "
        "Set DST_JWT_SECRET before deploying anywhere real."
    )


def create_admin_token(expires_days: int = 1) -> str:
    """Generate a fresh admin-scope JWT, signed with DST_JWT_SECRET."""
    now = int(time.time())
    payload = {
        "scope": JWT_SCOPE,
        "iat": now,
        "exp": now + expires_days * 86400,
    }
    return jwt.encode(payload, str(Constants.DST_JWT_SECRET), algorithm=JWT_ALGORITHM)


def require_admin_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency gating mutating routes behind a valid admin-scope JWT."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        payload = jwt.decode(
            credentials.credentials,
            str(Constants.DST_JWT_SECRET),
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("scope") != JWT_SCOPE:
        raise HTTPException(status_code=403, detail="Token does not have admin scope")
