"""FastAPI dependencies: async DB session, current user, IPC client, event bus, crypto."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pfsense_shared.crypto import Crypto

from .services.event_bus import EventBus
from .services.ipc_client import IpcClient


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        yield session


def get_ipc_client(request: Request) -> IpcClient:
    return request.app.state.ipc_client


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_crypto(request: Request) -> Crypto:
    return request.app.state.crypto


def get_current_user(request: Request) -> dict[str, Any]:
    user = request.session.get("user")
    if user:
        return user
    # Bearer-token requests (F7): the middleware stashed the resolved
    # token identity on request.state — audit attribution and every
    # CurrentUser-consuming route see ``token:<name>`` as the actor.
    api_user = getattr(request.state, "api_user", None)
    if api_user:
        return dict(api_user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
Ipc = Annotated[IpcClient, Depends(get_ipc_client)]
Events = Annotated[EventBus, Depends(get_event_bus)]
CryptoDep = Annotated[Crypto, Depends(get_crypto)]
