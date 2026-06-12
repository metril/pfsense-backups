"""IPC dispatch failure paths: a Job created by the web service must not
stay "queued" forever when its command dies before the manager marks it.

Before this guard, a schema-validation failure (web/worker version skew)
or any handler exception raised before ``backup_instance`` ran left the
Job row in "queued" until the next worker boot's ``_mark_stale_jobs``
sweep. ``_dispatch`` now rescues the job into "failure" — but only when
it's still in a non-terminal state, so handler-resolved jobs keep their
original status and message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pfsense_shared.crypto import Crypto
from pfsense_shared.models import Base, Job
from worker.ipc_listener import IpcListener


def _make_listener(session_factory, manager=None) -> IpcListener:
    return IpcListener(
        bind_url="tcp://127.0.0.1:0",
        session_factory=session_factory,
        manager=manager or MagicMock(),
        scheduler=MagicMock(),
        notifier=MagicMock(),
        publisher=MagicMock(),
        instance_locks=MagicMock(),
        crypto=Crypto(Fernet.generate_key()),
    )


def _seed_job(session_factory, status: str = "queued") -> int:
    with session_factory() as s:
        job = Job(
            instance_id=None,
            kind="manual",
            requested_by="op@example.test",
            requested_at=datetime.now(UTC),
            status=status,
        )
        s.add(job)
        s.commit()
        return job.id


def _job_status(session_factory, job_id: int) -> tuple[str, str | None]:
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job is not None
        return job.status, job.message


def _setup() -> sessionmaker:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_validation_error_marks_job_failed() -> None:
    session_factory = _setup()
    listener = _make_listener(session_factory)
    job_id = _seed_job(session_factory)

    # run_backup without instance_id fails RunBackupCommand validation.
    listener._dispatch({"cmd": "run_backup", "job_id": job_id})

    status, message = _job_status(session_factory, job_id)
    assert status == "failure"
    assert "rejected" in (message or "")


def test_handler_exception_marks_job_failed() -> None:
    session_factory = _setup()
    manager = MagicMock()
    manager.backup_instance.side_effect = RuntimeError("boom")
    listener = _make_listener(session_factory, manager=manager)
    job_id = _seed_job(session_factory)

    listener._dispatch(
        {"cmd": "run_backup", "job_id": job_id, "instance_id": 1}
    )

    status, message = _job_status(session_factory, job_id)
    assert status == "failure"
    assert "boom" in (message or "")


def test_terminal_job_is_not_overwritten() -> None:
    session_factory = _setup()
    listener = _make_listener(session_factory)
    job_id = _seed_job(session_factory, status="success")

    listener._dispatch({"cmd": "run_backup", "job_id": job_id})

    status, message = _job_status(session_factory, job_id)
    assert status == "success"
    assert message is None


def test_missing_job_id_is_harmless() -> None:
    session_factory = _setup()
    listener = _make_listener(session_factory)
    # Must not raise — reload_schedule carries no job_id.
    listener._dispatch({"cmd": "reload_schedule", "bogus": True})
