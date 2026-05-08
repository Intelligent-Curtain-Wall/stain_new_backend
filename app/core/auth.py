from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=True)


def _decode_local_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
    except Exception:  # noqa: BLE001
        return None

    user_id = payload.get("sub")
    if not user_id:
        user_id = payload.get("id") or payload.get("email")
    return str(user_id) if user_id else None


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    token = credentials.credentials

    user_id = _decode_local_jwt(token)
    if user_id:
        return user_id

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
