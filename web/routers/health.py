"""Liveness + worker-reachability probe."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dependencies import Events

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(bus: Events) -> dict[str, Any]:
    return {"ok": True, "worker_alive": bus.worker_alive()}
