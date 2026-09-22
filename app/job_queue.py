from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OperationalJob


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_job(db: Session, job_type: str, payload: dict | None = None, max_attempts: int = 3) -> OperationalJob:
    now = utcnow_naive()
    job = OperationalJob(
        job_type=job_type,
        payload_json=json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
        status="queued",
        attempts=0,
        max_attempts=max(1, max_attempts),
        run_after=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_job(db: Session) -> OperationalJob | None:
    now = utcnow_naive()
    stmt = (
        select(OperationalJob)
        .where(OperationalJob.status == "queued", OperationalJob.run_after <= now)
        .order_by(OperationalJob.id.asc())
        .limit(1)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = db.scalar(stmt)
    if not job:
        return None
    job.status = "running"
    job.attempts += 1
    job.locked_at = now
    job.updated_at = now
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job: OperationalJob) -> None:
    job.status = "done"
    job.locked_at = None
    job.last_error = None
    job.updated_at = utcnow_naive()
    db.commit()


def fail_job(db: Session, job: OperationalJob, exc: Exception) -> None:
    job.last_error = f"{exc.__class__.__name__}: {str(exc)[:500]}"
    job.locked_at = None
    job.updated_at = utcnow_naive()
    job.status = "failed" if job.attempts >= job.max_attempts else "queued"
    db.commit()
