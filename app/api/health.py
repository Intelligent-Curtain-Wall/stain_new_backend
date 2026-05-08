from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.response import ok

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check() -> dict:
    return ok({
        "status": "ok",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "version": "0.1.0"
    })
