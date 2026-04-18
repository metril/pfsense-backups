"""Read-only access to the Job history (manual runs, scheduled runs, tests)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from pfsense_shared.models import Job
from pfsense_shared.schemas import JobRead

from ..dependencies import DbSession

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
async def list_jobs(
    db: DbSession,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    instance_id: int | None = None,
) -> list[JobRead]:
    stmt = select(Job).order_by(Job.requested_at.desc()).limit(limit).offset(offset)
    if instance_id is not None:
        stmt = stmt.where(Job.instance_id == instance_id)
    rows = (await db.scalars(stmt)).all()
    return [JobRead.model_validate(r) for r in rows]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: int, db: DbSession) -> JobRead:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobRead.model_validate(job)
