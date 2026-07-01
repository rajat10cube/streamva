"""Liveness endpoint (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "streamva", "version": __version__}
