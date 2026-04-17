"""CRUD + actions on pfSense instances."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from pfsense_shared.models import Instance, Job
from pfsense_shared.schemas import (
    InstanceCreate,
    InstanceRead,
    InstanceUpdate,
    ReloadScheduleCommand,
    RunBackupCommand,
    TestConnectionCommand,
)

from ..dependencies import CryptoDep, CurrentUser, DbSession, Ipc
from ..services import audit
from ..services.cron_utils import validate as validate_cron

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _to_read(inst: Instance, crypto) -> InstanceRead:
    return InstanceRead.model_validate(
        {
            "id": inst.id,
            "name": inst.name,
            "url": inst.url,
            "username": crypto.decrypt(inst.username_ct),
            "subfolder": inst.subfolder,
            "backup_prefix": inst.backup_prefix,
            "verify_ssl": inst.verify_ssl,
            "timeout_seconds": inst.timeout_seconds,
            "cron_expression": inst.cron_expression,
            "cron_timezone": inst.cron_timezone,
            "enabled": inst.enabled,
            "retention_count": inst.retention_count,
            "compress": inst.compress,
            "created_at": inst.created_at,
            "updated_at": inst.updated_at,
        }
    )


@router.get("", response_model=list[InstanceRead])
async def list_instances(db: DbSession, crypto: CryptoDep) -> list[InstanceRead]:
    rows = db.execute(select(Instance).order_by(Instance.name)).scalars().all()
    return [_to_read(r, crypto) for r in rows]


@router.get("/{instance_id}", response_model=InstanceRead)
async def get_instance(instance_id: int, db: DbSession, crypto: CryptoDep) -> InstanceRead:
    inst = db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    return _to_read(inst, crypto)


@router.post("", response_model=InstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: InstanceCreate, db: DbSession, crypto: CryptoDep, user: CurrentUser, ipc: Ipc
) -> InstanceRead:
    if payload.cron_expression:
        try:
            validate_cron(payload.cron_expression)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    inst = Instance(
        name=payload.name,
        url=payload.url,
        username_ct=crypto.encrypt(payload.username),
        password_ct=crypto.encrypt(payload.password),
        subfolder=payload.subfolder,
        backup_prefix=payload.backup_prefix,
        verify_ssl=payload.verify_ssl,
        timeout_seconds=payload.timeout_seconds,
        cron_expression=payload.cron_expression,
        cron_timezone=payload.cron_timezone,
        enabled=payload.enabled,
        retention_count=payload.retention_count,
        compress=payload.compress,
    )
    db.add(inst)
    db.flush()
    audit.record(
        db, actor_email=user["email"], action="create", resource="instance",
        resource_id=inst.id, details={"name": inst.name},
    )
    db.commit()
    # Register the cron if one was provided.
    if inst.cron_expression:
        await ipc.send(ReloadScheduleCommand(instance_id=inst.id))
    return _to_read(inst, crypto)


@router.put("/{instance_id}", response_model=InstanceRead)
async def update_instance(
    instance_id: int,
    payload: InstanceUpdate,
    db: DbSession,
    crypto: CryptoDep,
    user: CurrentUser,
    ipc: Ipc,
) -> InstanceRead:
    inst = db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")

    if payload.cron_expression is not None and payload.cron_expression:
        try:
            validate_cron(payload.cron_expression)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    changed: dict[str, Any] = {}
    for field in (
        "name", "url", "subfolder", "backup_prefix", "verify_ssl",
        "timeout_seconds", "cron_expression", "cron_timezone",
        "enabled", "retention_count", "compress",
    ):
        val = getattr(payload, field)
        if val is not None and getattr(inst, field) != val:
            setattr(inst, field, val)
            changed[field] = val
    if payload.username is not None:
        inst.username_ct = crypto.encrypt(payload.username)
        changed["username"] = "<updated>"
    if payload.password:
        inst.password_ct = crypto.encrypt(payload.password)
        changed["password"] = "<updated>"

    if not changed:
        return _to_read(inst, crypto)

    inst.updated_at = datetime.now(UTC)
    audit.record(
        db, actor_email=user["email"], action="update", resource="instance",
        resource_id=inst.id, details=changed,
    )
    db.commit()

    # Any schedule-relevant change → tell the worker to reload.
    if {"cron_expression", "cron_timezone", "enabled"} & changed.keys():
        await ipc.send(ReloadScheduleCommand(instance_id=inst.id))

    return _to_read(inst, crypto)


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> None:
    inst = db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(404, "instance not found")
    name = inst.name
    db.delete(inst)
    audit.record(
        db, actor_email=user["email"], action="delete", resource="instance",
        resource_id=instance_id, details={"name": name},
    )
    db.commit()
    await ipc.send(ReloadScheduleCommand(instance_id=instance_id))


@router.post("/{instance_id}/test-connection")
async def test_connection(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if db.get(Instance, instance_id) is None:
        raise HTTPException(404, "instance not found")
    job = Job(instance_id=instance_id, kind="test_connection", requested_by=user["email"])
    db.add(job)
    db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="test_connection",
        resource_id=instance_id,
    )
    db.commit()
    await ipc.send(TestConnectionCommand(instance_id=instance_id, job_id=job.id))
    return {"job_id": job.id}


@router.post("/{instance_id}/backup-now")
async def backup_now(
    instance_id: int, db: DbSession, user: CurrentUser, ipc: Ipc
) -> dict[str, int]:
    if db.get(Instance, instance_id) is None:
        raise HTTPException(404, "instance not found")
    job = Job(instance_id=instance_id, kind="manual", requested_by=user["email"])
    db.add(job)
    db.flush()
    audit.record(
        db, actor_email=user["email"], action="trigger", resource="backup",
        resource_id=instance_id,
    )
    db.commit()
    await ipc.send(RunBackupCommand(instance_id=instance_id, job_id=job.id))
    return {"job_id": job.id}
