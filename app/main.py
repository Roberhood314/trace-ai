import os
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Case, Evidence, MissingPerson, SearchZone, TimelineEvent
from .schemas import (
    CaseCreate, CaseOut,
    EvidenceOut,
    MissingPersonCreate, MissingPersonOut,
    SearchZoneCreate, SearchZoneOut,
    TimelineEventCreate, TimelineEventOut,
)
from .security import Role, require_role

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_MEDIA_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/webm",
}

app = FastAPI(
    title="TRACE-AI",
    version="0.5.0",
    description="MVP hỗ trợ quản lý vụ việc, timeline, chứng cứ và vùng tìm kiếm.",
)

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in allowed_origins if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

class PiVerifyRequest(BaseModel):
    access_token: str

@app.get("/health")
def health():
    return {"status": "ok", "service": "trace-ai", "version": "0.5.0"}

@app.post("/auth/pi/verify")
async def verify_pi_user(payload: PiVerifyRequest):
    if not payload.access_token:
        raise HTTPException(status_code=400, detail="missing access token")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.minepi.com/v2/me",
            headers={"Authorization": f"Bearer {payload.access_token}"},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid Pi access token")
    data = response.json()
    return {"uid": data.get("uid"), "username": data.get("username"), "verified": True}

@app.post("/cases", response_model=CaseOut)
def create_case(payload: CaseCreate, db: Session = Depends(get_db), _role = Depends(require_role(Role.ANALYST))):
    if db.scalar(select(Case).where(Case.case_code == payload.case_code)):
        raise HTTPException(status_code=409, detail="case_code already exists")
    obj = Case(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.get("/cases", response_model=list[CaseOut])
def list_cases(db: Session = Depends(get_db), _role = Depends(require_role(Role.VIEWER))):
    return list(db.scalars(select(Case).order_by(Case.started_at.desc())).all())

@app.post("/cases/{case_id}/person", response_model=MissingPersonOut)
def add_person(case_id: int, payload: MissingPersonCreate, db: Session = Depends(get_db), _role = Depends(require_role(Role.ANALYST))):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    existing = db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id))
    if existing:
        raise HTTPException(status_code=409, detail="person profile already exists for case")
    obj = MissingPerson(case_id=case_id, **payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/person", response_model=MissingPersonOut | None)
def get_person(case_id: int, db: Session = Depends(get_db), _role = Depends(require_role(Role.VIEWER))):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    return db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id))

@app.post("/cases/{case_id}/timeline", response_model=TimelineEventOut)
def add_timeline_event(case_id: int, payload: TimelineEventCreate, db: Session = Depends(get_db), _role = Depends(require_role(Role.ANALYST))):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    obj = TimelineEvent(case_id=case_id, **payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/timeline", response_model=list[TimelineEventOut])
def get_timeline(case_id: int, db: Session = Depends(get_db), _role = Depends(require_role(Role.VIEWER))):
    return list(db.scalars(
        select(TimelineEvent).where(TimelineEvent.case_id == case_id).order_by(TimelineEvent.event_time.asc())
    ).all())

@app.post("/cases/{case_id}/search-zones", response_model=SearchZoneOut)
def add_search_zone(case_id: int, payload: SearchZoneCreate, db: Session = Depends(get_db), _role = Depends(require_role(Role.ANALYST))):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    obj = SearchZone(case_id=case_id, **payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/search-zones", response_model=list[SearchZoneOut])
def get_search_zones(case_id: int, db: Session = Depends(get_db), _role = Depends(require_role(Role.VIEWER))):
    return list(db.scalars(
        select(SearchZone).where(SearchZone.case_id == case_id).order_by(SearchZone.score.desc())
    ).all())

@app.post("/cases/{case_id}/evidence", response_model=EvidenceOut)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    person_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.ANALYST)),
):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail="unsupported media type")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    suffix = Path(file.filename or "").suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (UPLOAD_DIR / stored_name).write_bytes(content)

    obj = Evidence(
        case_id=case_id,
        person_id=person_id,
        original_name=file.filename or stored_name,
        stored_name=stored_name,
        media_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        note=note,
    )
    db.add(obj); db.commit(); db.refresh(obj)
    return EvidenceOut.model_validate(obj).model_copy(update={"url": f"/uploads/{stored_name}"})

@app.get("/cases/{case_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(case_id: int, db: Session = Depends(get_db), _role = Depends(require_role(Role.VIEWER))):
    items = list(db.scalars(
        select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.created_at.desc())
    ).all())
    return [
        EvidenceOut.model_validate(x).model_copy(update={"url": f"/uploads/{x.stored_name}"})
        for x in items
    ]
