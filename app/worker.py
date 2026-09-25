from __future__ import annotations

import asyncio
import json
import os

from .database import SessionLocal
from .job_queue import claim_job, complete_job, fail_job, recover_stale_jobs


async def handle(job_type: str, payload: dict) -> None:
    if job_type == "wanted_sync":
        from .main import _run_wanted_sync
        await _run_wanted_sync(full=bool(payload.get("full", False)), actor="worker")
        return
    if job_type == "wanted_image_sync":
        from .main import _run_wanted_image_sync
        await _run_wanted_image_sync(limit=int(payload.get("limit", 250) or 250), actor="worker")
        return
    if job_type == "health_probe":
        return
    raise RuntimeError(f"unsupported job type: {job_type}")


async def run_worker() -> None:
    poll_seconds = max(1.0, float(os.getenv("WORKER_POLL_SECONDS", "3")))
    lease_seconds = max(30, int(os.getenv("WORKER_LEASE_SECONDS", "300")))
    with SessionLocal() as db:
        recover_stale_jobs(db, lease_seconds)
    while True:
        with SessionLocal() as db:
            job = claim_job(db)
            if job is None:
                await asyncio.sleep(poll_seconds)
                continue
            try:
                payload = json.loads(job.payload_json or "{}")
                await handle(job.job_type, payload)
                complete_job(db, job)
            except Exception as exc:
                fail_job(db, job, exc)
        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(run_worker())
