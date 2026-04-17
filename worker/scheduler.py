"""APScheduler wrapper: one cron job per enabled Instance with a cron_expression."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import sessionmaker

from pfsense_shared.models import Instance, Job
from pfsense_shared.schemas import ScheduleReloaded

from .ipc_publisher import IpcPublisher

log = logging.getLogger(__name__)


def _job_id(instance_id: int) -> str:
    return f"instance-{instance_id}"


class Scheduler:
    """Per-instance cron scheduling. Backup execution delegates to a provided callable
    so this module stays free of HTTP/DB concerns beyond triggering."""

    def __init__(
        self,
        session_factory: sessionmaker,
        db_url: str,
        publisher: IpcPublisher,
        run_backup: callable,  # type: ignore[valid-type]  (instance_id:int, job_id:int) -> None
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._run_backup = run_backup
        jobstore = SQLAlchemyJobStore(url=db_url, tablename="apscheduler_jobs")
        self._scheduler = BackgroundScheduler(
            jobstores={"default": jobstore},
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
        self._scheduler.shutdown(wait=False)

    # -------------------------------------------------------------- #
    # job management
    # -------------------------------------------------------------- #

    def load_all_jobs(self) -> None:
        """(Re)install APScheduler jobs for every enabled instance with a cron_expression."""
        with self._session_factory() as s:
            instances = s.query(Instance).filter(Instance.enabled.is_(True)).all()
            for inst in instances:
                self._add_or_update(inst.id, inst.cron_expression, inst.cron_timezone)

    def reload_instance(self, instance_id: int) -> None:
        with self._session_factory() as s:
            inst = s.get(Instance, instance_id)
        if inst is None or not inst.enabled or not inst.cron_expression:
            self._remove(instance_id)
        else:
            self._add_or_update(inst.id, inst.cron_expression, inst.cron_timezone)
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

    def _add_or_update(self, instance_id: int, cron: str | None, tz: str) -> None:
        if not cron:
            self._remove(instance_id)
            return
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=tz)
        except Exception as exc:
            log.error("Invalid cron for instance %s: %s (%s)", instance_id, cron, exc)
            return
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=_job_id(instance_id),
            kwargs={"instance_id": instance_id},
            replace_existing=True,
        )
        log.info("Scheduled instance %s with cron='%s' tz=%s", instance_id, cron, tz)

    def _remove(self, instance_id: int) -> None:
        try:
            self._scheduler.remove_job(_job_id(instance_id))
            log.info("Unscheduled instance %s", instance_id)
        except Exception:
            pass

    def _fire(self, instance_id: int) -> None:
        """APScheduler callback: creates a Job row then delegates to run_backup."""
        with self._session_factory() as s:
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
        self._run_backup(instance_id=instance_id, job_id=job_id)
