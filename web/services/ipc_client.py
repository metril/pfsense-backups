"""ZeroMQ client: PUSH commands to the worker; SUB the worker's PUB stream into the EventBus.

We use pyzmq's asyncio bindings so sending and receiving integrate with FastAPI's
event loop. PUSH sockets queue locally on disconnect and reconnect automatically,
so the worker being briefly down does not raise here.
"""

from __future__ import annotations

import asyncio
import json
import logging

import zmq
import zmq.asyncio
from pydantic import ValidationError

from pfsense_shared.schemas import IpcCommand

from .event_bus import EventBus

log = logging.getLogger(__name__)


class IpcClient:
    def __init__(self, push_url: str, sub_url: str, bus: EventBus) -> None:
        self._push_url = push_url
        self._sub_url = sub_url
        self._bus = bus

        self._ctx = zmq.asyncio.Context.instance()
        self._push: zmq.asyncio.Socket = self._ctx.socket(zmq.PUSH)
        self._push.setsockopt(zmq.LINGER, 0)
        self._push.setsockopt(zmq.SNDHWM, 1000)
        self._push.connect(push_url)

        self._sub: zmq.asyncio.Socket = self._ctx.socket(zmq.SUB)
        self._sub.setsockopt(zmq.LINGER, 0)
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")  # all topics
        self._sub.connect(sub_url)

        self._bridge_task: asyncio.Task | None = None

        log.info("IpcClient connecting push=%s sub=%s", push_url, sub_url)

    def start(self) -> None:
        if self._bridge_task is None or self._bridge_task.done():
            self._bridge_task = asyncio.create_task(self._bridge_loop(), name="zmq-sub-bridge")

    async def close(self) -> None:
        if self._bridge_task is not None:
            self._bridge_task.cancel()
            try:
                await self._bridge_task
            except asyncio.CancelledError:
                pass
        self._push.close()
        self._sub.close()

    async def send(self, command: IpcCommand | dict) -> None:
        """Serialize + push a command. Accepts a dict or a pydantic IpcCommand."""
        if isinstance(command, dict):
            # Round-trip through pydantic so unknown shapes fail loud here, not on the worker.
            try:
                model: IpcCommand = _validate_command(command)
            except ValidationError as exc:
                raise ValueError(f"invalid IPC command: {exc}") from exc
            payload = model.model_dump_json().encode("utf-8")
        else:
            payload = command.model_dump_json().encode("utf-8")
        await self._push.send(payload)

    async def _bridge_loop(self) -> None:
        while True:
            try:
                topic_bytes, payload_bytes = await self._sub.recv_multipart()
                topic = topic_bytes.decode("utf-8")
                try:
                    data = json.loads(payload_bytes.decode("utf-8"))
                except Exception as exc:
                    log.error("Non-JSON frame on topic %s: %s", topic, exc)
                    continue
                await self._bus.publish(topic, data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("ZMQ SUB bridge error: %s", exc)
                await asyncio.sleep(0.5)


def _validate_command(payload: dict) -> IpcCommand:
    """Dispatch a raw dict into the correct IpcCommand member by `cmd` key."""
    from pfsense_shared.schemas import (
        ReloadScheduleCommand,
        RunBackupAllCommand,
        RunBackupCommand,
        SendTestNotificationCommand,
        TestConnectionCommand,
    )

    kind = payload.get("cmd")
    cls_map = {
        "run_backup": RunBackupCommand,
        "run_backup_all": RunBackupAllCommand,
        "test_connection": TestConnectionCommand,
        "reload_schedule": ReloadScheduleCommand,
        "send_test_notification": SendTestNotificationCommand,
    }
    cls = cls_map.get(kind)
    if cls is None:
        raise ValueError(f"unknown command kind: {kind}")
    return cls.model_validate(payload)
