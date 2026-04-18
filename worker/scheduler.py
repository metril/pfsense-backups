"""APScheduler wrapper: one cron job per enabled Instance with a cron_expression."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
from sqlalchemy.orm import sessionmaker

from pfsense_shared.models import Instance, Job
from pfsense_shared.schemas import ScheduleReloaded

from .instance_locks import InstanceLocks
from .ipc_publisher import IpcPublisher

log = logging.getLogger(__name__)


def _job_id(instance_id: int) -> str:
    return f"instance-{instance_id}"


class Scheduler:
    """Per-instance cron scheduling.

    Backup execution delegates to a provided callable so this module stays free
    of HTTP/DB concerns beyond triggering. The per-instance lock is shared with
    the IPC listener so a scheduled run + a user-triggered "Backup Now" for
    the same instance serialize rather than racing (C2).
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        publisher: IpcPublisher,
        run_backup: Callable[..., object],
        instance_locks: InstanceLocks,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._run_backup = run_backup
        self._instance_locks = instance_locks
        # MemoryJobStore — not SQLAlchemyJobStore. The persistent store
        # pickles each job, which for bound methods like ``self._fire``
        # drags the Scheduler instance (and its SQLAlchemy engine, whose
        # ``create_engine.<locals>.connect`` closure is unpicklable) into
        # the pickle graph. We don't need persistence: ``load_all_jobs``
        # is called on ``start()`` and rebuilds every schedule directly
        # from the authoritative ``instances`` table, so a restart loses
        # nothing.
        self._scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "misfire_grace_time": 3600,
                "coalesce": True,
                "max_instances": 1,
            },
            timezone="UTC",
        )

    # -------------------------------------------------------------- #
    # lifecycle
    # -------------------------------------------------------------- #

    def start(self) -> None:
        self._scheduler.start()
        self.load_all_jobs()

    def shutdown(self) -> None:
        # Wait for any running trigger callback to finish so we don't leave
        # a Job row stuck in 'running'. Startup hook will clean up anything
        # abandoned by a hard kill.
        self._scheduler.shutdown(wait=True)

    # -------------------------------------------------------------- #
    # job management
    # -------------------------------------------------------------- #

    def load_all_jobs(self) -> None:
        """(Re)install APScheduler jobs for every enabled instance with a cron_expression."""
        with self._session_factory() as s:
            instances = s.query(Instance).filter(Instance.enabled.is_(True)).all()
            for inst in instances:
                self._add_or_update(inst.id, inst.name, inst.cron_expression, inst.cron_timezone)

    def reload_instance(self, instance_id: int) -> None:
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
        if inst is None or not inst.enabled or not inst.cron_expression:
            name = inst.name if inst is not None else None
            self._remove(instance_id, name=name)
        else:
            self._add_or_update(inst.id, inst.name, inst.cron_expression, inst.cron_timezone)
        self._publisher.publish(
            ScheduleReloaded(instance_id=instance_id, ts=datetime.now(UTC))
        )

    def reload_all(self) -> None:
        # Drop everything we own, then re-add from DB.
        for job in list(self._scheduler.get_jobs()):
            if job.id.startswith("instance-"):
                self._scheduler.remove_job(job.id)
        self.load_all_jobs()
        self._publisher.publish(ScheduleReloaded(instance_id=None, ts=datetime.now(UTC)))

    # -------------------------------------------------------------- #
    # internals
    # -------------------------------------------------------------- #

    def _add_or_update(
        self, instance_id: int, name: str, cron: str | None, tz: str
    ) -> None:
        if not cron:
            self._remove(instance_id, name=name)
            return
        # H10: validate cron + timezone up-front so we log a clear error and
        # never hand APScheduler something it will silently reject later.
        if not croniter.is_valid(cron):
            log.error(
                "Invalid cron expression for %r (id=%d): %r — job not scheduled",
                name, instance_id, cron,
            )
            return
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            log.error(
                "Invalid timezone for %r (id=%d): %r — job not scheduled",
                name, instance_id, tz,
            )
            return
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=tz)
        except Exception as exc:
            log.error(
                "APScheduler rejected cron for %r (id=%d): %s (%s)",
                name, instance_id, cron, exc,
            )
            return
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=_job_id(instance_id),
            kwargs={"instance_id": instance_id},
            replace_existing=True,
        )
        log.info(
            "Scheduled %r (id=%d) with cron=%r tz=%s", name, instance_id, cron, tz
        )

    def _remove(self, instance_id: int, *, name: str | None = None) -> None:
        try:
            self._scheduler.remove_job(_job_id(instance_id))
            label = f"{name!r} (id={instance_id})" if name else f"instance id={instance_id}"
            log.info("Unscheduled %s", label)
        except Exception:
            pass

    def _fire(self, instance_id: int) -> None:
        """APScheduler callback: verify instance still exists, create Job row,
        then run the backup under the shared per-instance lock."""
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
            if inst is None or not inst.enabled:
                # M16: instance was deleted or disabled between scheduling and
                # firing. Silently skip — no Job row, no event storm.
                name_or_id = (
                    f"{inst.name!r}" if inst is not None else f"id={instance_id}"
                )
                log.info("Scheduled run skipped: %s missing or disabled", name_or_id)
                return
            job = Job(
                instance_id=instance_id,
                kind="scheduled",
                requested_by=None,
                requested_at=datetime.now(UTC),
                status="queued",
            )
            s.add(job)
            s.commit()
            job_id = job.id
        # C2: serialize with user-triggered backups for the same instance.
        with self._instance_locks.for_instance(instance_id):
            self._run_backup(instance_id=instance_id, job_id=job_id)
