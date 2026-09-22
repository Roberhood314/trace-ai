import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_trace_ai.db")

from app.database import Base, SessionLocal, engine
from app.job_queue import claim_job, complete_job, enqueue_job
from app.models import OperationalJob


def test_queue_lifecycle():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.query(OperationalJob).delete()
        db.commit()
        job = enqueue_job(db, "health_probe", {"ok": True})
        assert job.status == "queued"
        claimed = claim_job(db)
        assert claimed is not None
        assert claimed.status == "running"
        assert claimed.attempts == 1
        complete_job(db, claimed)
        db.refresh(claimed)
        assert claimed.status == "done"
