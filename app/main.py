import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import AuditEvent, Case, Evidence, MissingPerson, SearchZone, TimelineEvent, User
from .schemas import (
    AISummaryOut, AuditOut, AuthOut,
    CaseCreate, CaseOut, EvidenceOut,
    MissingPersonCreate, MissingPersonOut,
    SearchZoneCreate, SearchZoneOut,
    TimelineEventCreate, TimelineEventOut,
    UserOut, UserRoleUpdate,
)
from .security import CurrentUser, Role, issue_token, require_role

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"}

app = FastAPI(
    title="TRACE-AI",
    version="1.0.0-rc1",
    description="Pi-ready MVP: hồ sơ vụ việc, timeline, vùng tìm kiếm, chứng cứ và trợ lý phân tích.",
)

allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Role"],
)

class PiVerifyRequest(BaseModel):
    access_token: str

def add_audit(db: Session, user: CurrentUser, action: str, resource_type: str, resource_id=None, detail=None):
    row = AuditEvent(
        actor=user.uid,
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        detail=detail,
    )
    db.add(row)

def ensure_case(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case

@app.get("/health")
def health():
    return {"status": "ok", "service": "trace-ai", "version": "1.0.0-rc1"}

@app.post("/auth/pi/verify", response_model=AuthOut)
async def verify_pi_user(payload: PiVerifyRequest, db: Session = Depends(get_db)):
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
    uid = data.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Pi response missing uid")
    username = data.get("username")

    user = db.scalar(select(User).where(User.pi_uid == uid))
    bootstrap_admins = {x.strip() for x in os.getenv("BOOTSTRAP_ADMIN_PI_UIDS", "").split(",") if x.strip()}
    if not user:
        user = User(pi_uid=uid, username=username, role="admin" if uid in bootstrap_admins else "viewer")
        db.add(user)
    else:
        user.username = username
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return AuthOut(token=issue_token(user), username=user.username, role=user.role, verified=True)

@app.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ADMIN))):
    return list(db.scalars(select(User).order_by(User.created_at.asc())).all())

@app.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserRoleUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ADMIN))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
    add_audit(db, user, "user_role_update", "user", user_id, f"role={target.role};active={target.is_active}")
    db.commit(); db.refresh(target)
    return target

@app.post("/cases", response_model=CaseOut)
def create_case(payload: CaseCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ANALYST))):
    if db.scalar(select(Case).where(Case.case_code == payload.case_code)):
        raise HTTPException(status_code=409, detail="case_code already exists")
    obj = Case(**payload.model_dump(), created_by=user.uid)
    db.add(obj); db.flush()
    add_audit(db, user, "case_create", "case", obj.id, obj.case_code)
    db.commit(); db.refresh(obj)
    return obj

@app.get("/cases", response_model=list[CaseOut])
def list_cases(db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    return list(db.scalars(select(Case).order_by(Case.started_at.desc())).all())

@app.post("/cases/{case_id}/person", response_model=MissingPersonOut)
def add_person(case_id: int, payload: MissingPersonCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ANALYST))):
    ensure_case(db, case_id)
    if db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id)):
        raise HTTPException(status_code=409, detail="person profile already exists for case")
    obj = MissingPerson(case_id=case_id, **payload.model_dump())
    db.add(obj); db.flush()
    add_audit(db, user, "person_create", "missing_person", obj.id, f"case={case_id}")
    db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/person", response_model=MissingPersonOut | None)
def get_person(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    ensure_case(db, case_id)
    return db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id))

@app.post("/cases/{case_id}/timeline", response_model=TimelineEventOut)
def add_timeline_event(case_id: int, payload: TimelineEventCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ANALYST))):
    ensure_case(db, case_id)
    if (payload.latitude is None) != (payload.longitude is None):
        raise HTTPException(status_code=422, detail="latitude and longitude must be supplied together")
    obj = TimelineEvent(case_id=case_id, created_by=user.uid, **payload.model_dump())
    db.add(obj); db.flush()
    add_audit(db, user, "timeline_create", "timeline_event", obj.id, f"case={case_id}")
    db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/timeline", response_model=list[TimelineEventOut])
def get_timeline(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    ensure_case(db, case_id)
    return list(db.scalars(select(TimelineEvent).where(TimelineEvent.case_id == case_id).order_by(TimelineEvent.event_time.asc())).all())

@app.post("/cases/{case_id}/search-zones", response_model=SearchZoneOut)
def add_search_zone(case_id: int, payload: SearchZoneCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.ANALYST))):
    ensure_case(db, case_id)
    obj = SearchZone(case_id=case_id, created_by=user.uid, **payload.model_dump())
    db.add(obj); db.flush()
    add_audit(db, user, "zone_create", "search_zone", obj.id, f"case={case_id}")
    db.commit(); db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/search-zones", response_model=list[SearchZoneOut])
def get_search_zones(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    ensure_case(db, case_id)
    return list(db.scalars(select(SearchZone).where(SearchZone.case_id == case_id).order_by(SearchZone.score.desc())).all())

@app.post("/cases/{case_id}/evidence", response_model=EvidenceOut)
async def upload_evidence(
    case_id: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    person_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    ensure_case(db, case_id)
    if person_id is not None:
        person = db.get(MissingPerson, person_id)
        if not person or person.case_id != case_id:
            raise HTTPException(status_code=422, detail="person_id does not belong to case")
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail="unsupported media type")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    extension_by_type = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/webm": ".webm",
    }
    stored_name = f"{uuid.uuid4().hex}{extension_by_type[file.content_type]}"
    (UPLOAD_DIR / stored_name).write_bytes(content)

    obj = Evidence(
        case_id=case_id, person_id=person_id,
        original_name=(file.filename or "evidence")[:255],
        stored_name=stored_name, media_type=file.content_type,
        size_bytes=len(content), note=note, created_by=user.uid,
    )
    db.add(obj); db.flush()
    add_audit(db, user, "evidence_upload", "evidence", obj.id, f"case={case_id};type={file.content_type}")
    db.commit(); db.refresh(obj)
    return EvidenceOut.model_validate(obj).model_copy(update={"url": f"/evidence/{obj.id}/content"})

@app.get("/cases/{case_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    ensure_case(db, case_id)
    items = list(db.scalars(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.created_at.desc())).all())
    return [EvidenceOut.model_validate(x).model_copy(update={"url": f"/evidence/{x.id}/content"}) for x in items]

@app.get("/evidence/{evidence_id}/content")
def get_evidence_content(evidence_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    item = db.get(Evidence, evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="evidence not found")
    path = UPLOAD_DIR / item.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="evidence file missing")
    add_audit(db, user, "evidence_view", "evidence", item.id, f"case={item.case_id}")
    db.commit()
    return FileResponse(path, media_type=item.media_type, filename=item.original_name)

@app.get("/cases/{case_id}/audit", response_model=list[AuditOut])
def case_audit(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.COMMANDER))):
    ensure_case(db, case_id)
    resource_ids = {str(case_id)}
    person = db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id))
    if person: resource_ids.add(str(person.id))
    event_ids = [str(x) for x in db.scalars(select(TimelineEvent.id).where(TimelineEvent.case_id == case_id)).all()]
    zone_ids = [str(x) for x in db.scalars(select(SearchZone.id).where(SearchZone.case_id == case_id)).all()]
    evidence_ids = [str(x) for x in db.scalars(select(Evidence.id).where(Evidence.case_id == case_id)).all()]
    resource_ids.update(event_ids + zone_ids + evidence_ids)
    rows = list(db.scalars(select(AuditEvent).where(AuditEvent.resource_id.in_(resource_ids)).order_by(AuditEvent.occurred_at.desc())).all())
    return rows

@app.get("/cases/{case_id}/ai-summary", response_model=AISummaryOut)
def ai_summary(case_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    ensure_case(db, case_id)
    events = list(db.scalars(select(TimelineEvent).where(TimelineEvent.case_id == case_id).order_by(TimelineEvent.event_time.desc())).all())
    zones = list(db.scalars(select(SearchZone).where(SearchZone.case_id == case_id).order_by(SearchZone.score.desc())).all())
    latest = events[0] if events else None
    zone_order = [z.name for z in zones]
    summary_parts = [f"Vụ việc có {len(events)} sự kiện timeline và {len(zones)} vùng tìm kiếm."]
    if latest:
        summary_parts.append(f"Dấu vết mới nhất: {latest.event_type} lúc {latest.event_time.isoformat()}.")
        if latest.confidence is not None:
            summary_parts.append(f"Độ tin cậy ghi nhận: {latest.confidence:.2f}.")
    if zones:
        summary_parts.append(f"Vùng đang có điểm ưu tiên cao nhất: {zones[0].name} ({zones[0].score:.0f}/100).")
    checks = [
        "Xác minh lại nguồn của dấu vết mới nhất trước khi điều chỉnh kế hoạch.",
        "Đối chiếu các mốc thời gian và tọa độ để phát hiện mâu thuẫn dữ liệu.",
        "Chỉ mở rộng vùng tìm kiếm khi có căn cứ mới hoặc khoảng thời gian mất liên lạc tăng.",
    ]
    return AISummaryOut(
        case_id=case_id,
        generated_at=datetime.now(timezone.utc),
        summary=" ".join(summary_parts),
        recommended_checks=checks,
        zone_order=zone_order,
    )
