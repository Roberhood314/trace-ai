import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import AuditEvent, Case, Evidence, MissingPerson, SearchZone, TimelineEvent, User, WantedRecord
from .schemas import (
    AISummaryOut, AuditOut, AuthOut,
    CaseCreate, CaseOut, EvidenceOut,
    MissingPersonCreate, MissingPersonOut,
    SearchZoneCreate, SearchZoneOut,
    TimelineEventCreate, TimelineEventOut,
    UserOut, UserRoleUpdate,
    WantedRecordOut, WantedSyncOut,
)
from .security import CurrentUser, Role, issue_token, require_role
from .services.wanted_sync import OFFICIAL_WANTED_URL, SOURCE_NAME, fetch_official_wanted, parse_wanted_detail, utcnow_naive
from .services.gateway import public_gateway_signals, public_gateway_status, response_units_snapshot, weather_snapshot

def validate_runtime_config():
    if os.getenv("APP_ENV", "development") == "production":
        secret = os.getenv("APP_SECRET", "")
        if not secret or secret.startswith("change-") or secret == "dev-only-change-me":
            raise RuntimeError("APP_SECRET must be replaced before production")
        if os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true":
            raise RuntimeError("DEV_AUTH_BYPASS must be false in production")

validate_runtime_config()
Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"}

app = FastAPI(
    title="TRACE-AI",
    version="1.4.1-rc1",
    description="Pi-ready MVP: hồ sơ vụ việc, timeline, vùng tìm kiếm, chứng cứ và trợ lý phân tích.",
)

allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Role"],
)

@app.middleware("http")
async def public_read_cors(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/public/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
        response.headers["Vary"] = "Origin"
    return response

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

async def _system_sync_wanted():
    interval = int(os.getenv("WANTED_AUTO_SYNC_MINUTES", "0") or 0)
    if interval < 30:
        return
    pages = max(1, min(int(os.getenv("WANTED_AUTO_SYNC_PAGES", "3") or 3), 10))
    detail_limit = max(0, min(int(os.getenv("WANTED_DETAIL_LIMIT", "40") or 40), 100))
    while True:
        try:
            records, fetched_pages = await fetch_official_wanted(max_pages=pages, detail_limit=detail_limit)
            now = utcnow_naive()
            with SessionLocal() as db:
                inserted = 0
                updated = 0
                for item in records:
                    row = db.scalar(select(WantedRecord).where(WantedRecord.source_key == item["source_key"]))
                    if row is None:
                        db.add(WantedRecord(**item, imported_at=now, last_seen_at=now))
                        inserted += 1
                    else:
                        for field, value in item.items():
                            setattr(row, field, value)
                        row.last_seen_at = now
                        updated += 1
                db.add(AuditEvent(
                    actor="system",
                    action="wanted_auto_sync",
                    resource_type="wanted_source",
                    detail=f"pages={fetched_pages};records={len(records)};inserted={inserted};updated={updated}",
                ))
                db.commit()
        except Exception:
            pass
        await asyncio.sleep(interval * 60)

@app.on_event("startup")
async def start_wanted_auto_sync():
    if int(os.getenv("WANTED_AUTO_SYNC_MINUTES", "0") or 0) >= 30:
        asyncio.create_task(_system_sync_wanted())

@app.get("/health")
def health():
    return {"status": "ok", "service": "trace-ai", "version": "1.4.1-rc1"}

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
    bootstrap_names = {x.strip().lower() for x in os.getenv("BOOTSTRAP_ADMIN_PI_USERNAMES", "").split(",") if x.strip()}
    is_bootstrap_admin = uid in bootstrap_admins or (username or "").lower() in bootstrap_names
    first_user_admin = os.getenv("SOLOHOST_FIRST_USER_ADMIN", "false").lower() == "true" and db.scalar(select(User.id).limit(1)) is None
    if not user:
        user = User(pi_uid=uid, username=username, role="admin" if (is_bootstrap_admin or first_user_admin) else "viewer")
        db.add(user)
    else:
        user.username = username
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
    clauses = [((AuditEvent.resource_type == "case") & (AuditEvent.resource_id == str(case_id)))]
    person = db.scalar(select(MissingPerson).where(MissingPerson.case_id == case_id))
    if person:
        clauses.append((AuditEvent.resource_type == "missing_person") & (AuditEvent.resource_id == str(person.id)))
    event_ids = [str(x) for x in db.scalars(select(TimelineEvent.id).where(TimelineEvent.case_id == case_id)).all()]
    zone_ids = [str(x) for x in db.scalars(select(SearchZone.id).where(SearchZone.case_id == case_id)).all()]
    evidence_ids = [str(x) for x in db.scalars(select(Evidence.id).where(Evidence.case_id == case_id)).all()]
    if event_ids:
        clauses.append((AuditEvent.resource_type == "timeline_event") & AuditEvent.resource_id.in_(event_ids))
    if zone_ids:
        clauses.append((AuditEvent.resource_type == "search_zone") & AuditEvent.resource_id.in_(zone_ids))
    if evidence_ids:
        clauses.append((AuditEvent.resource_type == "evidence") & AuditEvent.resource_id.in_(evidence_ids))
    from sqlalchemy import or_
    rows = list(db.scalars(select(AuditEvent).where(or_(*clauses)).order_by(AuditEvent.occurred_at.desc())).all())
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



@app.get("/public/gateway/status")
def gateway_status_public(db: Session = Depends(get_db)):
    return public_gateway_status(db)

@app.get("/public/gateway/signals")
def gateway_signals_public(q: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    return public_gateway_signals(db, q=q, limit=limit)

@app.get("/public/gateway/response-units")
async def gateway_response_units_public():
    try:
        return await response_units_snapshot()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"response-unit gateway unavailable: {exc.__class__.__name__}")

@app.get("/public/gateway/weather")
async def gateway_weather_public(lat: float, lon: float):
    try:
        return await weather_snapshot(lat, lon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"weather gateway unavailable: {exc.__class__.__name__}")

@app.get("/public/wanted/{wanted_id}/image")
async def public_wanted_image(wanted_id: int, db: Session = Depends(get_db)):
    row = db.get(WantedRecord, wanted_id)
    if not row:
        raise HTTPException(status_code=404, detail="wanted record not found")

    image_url = row.image_url
    headers = {
        "User-Agent": "TRACE-AI/1.4 (+official public-data image proxy)",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": OFFICIAL_WANTED_URL,
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        if not image_url and row.detail_url:
            detail_host = (urlparse(row.detail_url).hostname or "").lower()
            if detail_host != "truyna.bocongan.gov.vn":
                raise HTTPException(status_code=400, detail="unsupported official detail host")
            detail = await client.get(row.detail_url)
            detail.raise_for_status()
            parsed = parse_wanted_detail(detail.text, str(detail.url))
            image_url = parsed.get("image_url")
            if image_url:
                row.image_url = image_url
                if parsed.get("danger_level"):
                    row.danger_level = parsed["danger_level"]
                db.commit()

        if not image_url:
            raise HTTPException(status_code=404, detail="official image not available")

        image_host = (urlparse(image_url).hostname or "").lower()
        if image_host != "truyna.bocongan.gov.vn":
            raise HTTPException(status_code=400, detail="unsupported official image host")

        response = await client.get(image_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=502, detail="official source did not return an image")

    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-TRACE-Image-Source": "truyna.bocongan.gov.vn",
        },
    )

@app.get("/public/wanted", response_model=list[WantedRecordOut])
def public_wanted_records(q: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 250))
    stmt = select(WantedRecord).order_by(WantedRecord.last_seen_at.desc(), WantedRecord.id.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            WantedRecord.full_name.ilike(term),
            WantedRecord.registered_address.ilike(term),
            WantedRecord.offense.ilike(term),
            WantedRecord.warrant_reference.ilike(term),
            WantedRecord.issuing_unit.ilike(term),
        ))
    return list(db.scalars(stmt.limit(limit)).all())

@app.get("/public/wanted/source-status")
def public_wanted_source_status(db: Session = Depends(get_db)):
    latest = db.scalar(select(WantedRecord).order_by(WantedRecord.last_seen_at.desc()).limit(1))
    count = len(list(db.scalars(select(WantedRecord.id)).all()))
    return {
        "source_name": SOURCE_NAME,
        "source_url": OFFICIAL_WANTED_URL,
        "records": count,
        "last_sync": latest.last_seen_at if latest else None,
    }

@app.get("/wanted", response_model=list[WantedRecordOut])
def list_wanted_records(
    q: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    limit = max(1, min(limit, 250))
    stmt = select(WantedRecord).order_by(WantedRecord.last_seen_at.desc(), WantedRecord.id.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            WantedRecord.full_name.ilike(term),
            WantedRecord.registered_address.ilike(term),
            WantedRecord.offense.ilike(term),
            WantedRecord.warrant_reference.ilike(term),
            WantedRecord.issuing_unit.ilike(term),
        ))
    return list(db.scalars(stmt.limit(limit)).all())

@app.get("/wanted/source-status")
def wanted_source_status(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    latest = db.scalar(select(WantedRecord).order_by(WantedRecord.last_seen_at.desc()).limit(1))
    count = len(list(db.scalars(select(WantedRecord.id)).all()))
    return {
        "source_name": SOURCE_NAME,
        "source_url": OFFICIAL_WANTED_URL,
        "records": count,
        "last_sync": latest.last_seen_at if latest else None,
    }

@app.post("/wanted/sync", response_model=WantedSyncOut)
async def sync_wanted_records(
    pages: int = 3,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    try:
        records, fetched_pages = await fetch_official_wanted(max_pages=pages, detail_limit=int(os.getenv("WANTED_DETAIL_LIMIT", "40") or 40))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"official wanted source unavailable: {exc.__class__.__name__}")

    now = utcnow_naive()
    inserted = 0
    updated = 0
    for item in records:
        row = db.scalar(select(WantedRecord).where(WantedRecord.source_key == item["source_key"]))
        if row is None:
            row = WantedRecord(**item, imported_at=now, last_seen_at=now)
            db.add(row)
            inserted += 1
        else:
            for field, value in item.items():
                setattr(row, field, value)
            row.last_seen_at = now
            updated += 1

    add_audit(
        db, user, "wanted_sync", "wanted_source", None,
        f"source={OFFICIAL_WANTED_URL};pages={fetched_pages};records={len(records)}"
    )
    db.commit()
    return WantedSyncOut(
        source=OFFICIAL_WANTED_URL,
        fetched_pages=fetched_pages,
        parsed_records=len(records),
        inserted=inserted,
        updated=updated,
        synced_at=datetime.now(timezone.utc),
    )


# SoloHost/production web UI: API routes above keep precedence; static UI is mounted last.
WEB_DIST_DIR = Path(os.getenv("WEB_DIST_DIR", "/app/web-dist"))
if WEB_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="web")
