"""FastAPI dependencies: DB session, current user, IPC client, event bus, crypto."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from pfsense_shared.crypto import Crypto

from .services.event_bus import EventBus
from .services.ipc_client import IpcClient


def get_db(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_ipc_client(request: Request) -> IpcClient:
    return request.app.state.ipc_client


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_crypto(request: Request) -> Crypto:
    return request.app.state.crypto


def get_current_user(request: Request) -> dict[str, Any]:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
Ipc = Annotated[IpcClient, Depends(get_ipc_client)]
Events = Annotated[EventBus, Depends(get_event_bus)]
CryptoDep = Annotated[Crypto, Depends(get_crypto)]
