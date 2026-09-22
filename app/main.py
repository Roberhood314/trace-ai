import base64
import hashlib
import asyncio
import json
import os
import hmac
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .models import AuditEvent, Case, Evidence, MissingPerson, OperationalJob, SearchZone, TimelineEvent, User, WantedRecord, WantedRecordHistory
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
from .services.wanted_sync import OFFICIAL_SUSPENDED_URL, OFFICIAL_WANTED_URL, SOURCE_NAME, fetch_official_wanted, iter_official_list_pages, parse_wanted_detail, record_checksum, utcnow_naive
from .services.gateway import public_gateway_signals, public_gateway_status, response_units_snapshot, weather_snapshot
from .observability import metrics_middleware, metrics_response
from .job_queue import enqueue_job
from .rate_limit import enforce as enforce_rate_limit

def validate_runtime_config():
    if os.getenv("APP_ENV", "development") == "production":
        secret = os.getenv("APP_SECRET", "")
        if not secret or secret.startswith("change-") or secret == "dev-only-change-me":
            raise RuntimeError("APP_SECRET must be replaced before production")
        if len(secret) < 32:
            raise RuntimeError("APP_SECRET must be at least 32 characters in production")
        if os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true":
            raise RuntimeError("DEV_AUTH_BYPASS must be false in production")

validate_runtime_config()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"}

IMAGE_FETCH_SEMAPHORE = asyncio.Semaphore(6)
IMAGE_CACHE_MAX = max(16, min(int(os.getenv("WANTED_IMAGE_CACHE_ITEMS", "128") or 128), 512))
IMAGE_CACHE: OrderedDict[int, tuple[str, bytes]] = OrderedDict()
WANTED_SYNC_LOCK = asyncio.Lock()
WANTED_SYNC_STATE = {
    "running": False,
    "mode": None,
    "source_status": None,
    "page": 0,
    "total_pages": 0,
    "records_seen": 0,
    "started_at": None,
    "completed_at": None,
    "last_error": None,
}

app = FastAPI(
    title="TRACE-AI",
    version="1.5.0-rc2",
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

app.middleware("http")(metrics_middleware)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'self'")
    return response

@app.middleware("http")
async def public_read_cors(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/public/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
        response.headers["Vary"] = "Origin"
    return response

@app.middleware("http")
async def rate_limit(request, call_next):
    # Sensitive and expensive endpoints are protected even when a proxy limit
    # is accidentally removed.  A distributed WAF remains required at scale.
    path = request.url.path
    if path == "/auth/pi/verify":
        enforce_rate_limit(request, int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "12")))
    elif request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        enforce_rate_limit(request, int(os.getenv("WRITE_RATE_LIMIT_PER_MINUTE", "60")))
    elif path.startswith("/public/"):
        enforce_rate_limit(request, int(os.getenv("PUBLIC_RATE_LIMIT_PER_MINUTE", "240")))
    return await call_next(request)

class PiVerifyRequest(BaseModel):
    access_token: str

def add_audit(db: Session, user: CurrentUser, action: str, resource_type: str, resource_id=None, detail=None):
    previous = db.scalar(select(AuditEvent).where(AuditEvent.event_hash.is_not(None)).order_by(AuditEvent.id.desc()))
    occurred_at = datetime.now(timezone.utc).replace(tzinfo=None)
    previous_hash = previous.event_hash if previous else None
    canonical = "|".join([str(previous_hash or ""), user.uid, action, resource_type, str(resource_id or ""), str(detail or ""), occurred_at.isoformat()])
    row = AuditEvent(
        actor=user.uid,
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        detail=detail,
        occurred_at=occurred_at,
        previous_hash=previous_hash,
        event_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    db.add(row)

def ensure_case(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case

def _wanted_snapshot(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)


def _apply_wanted_records(db: Session, records: list[dict], actor: str, action: str, fetched_pages: int):
    now = utcnow_naive()
    inserted = updated = unchanged = 0
    active_records = suspended_records = 0

    for item in records:
        item = dict(item)
        item["checksum"] = item.get("checksum") or record_checksum(item)
        if item.get("status") == "dinh_na":
            suspended_records += 1
        else:
            active_records += 1

        row = db.scalar(select(WantedRecord).where(WantedRecord.source_key == item["source_key"]))
        if row is None and item.get("source_record_id"):
            row = db.scalar(select(WantedRecord).where(WantedRecord.source_record_id == item["source_record_id"]))
        if row is None and item.get("detail_url"):
            row = db.scalar(select(WantedRecord).where(WantedRecord.detail_url == item["detail_url"]))

        if row is None:
            row = WantedRecord(**item, imported_at=now, last_seen_at=now, source_updated_at=now)
            db.add(row)
            db.flush()
            db.add(WantedRecordHistory(
                wanted_record_id=row.id,
                source_key=item["source_key"],
                change_type="insert",
                old_checksum=None,
                new_checksum=item["checksum"],
                snapshot_json=_wanted_snapshot(item),
                changed_at=now,
            ))
            inserted += 1
            continue

        old_checksum = row.checksum
        old_status = row.status
        changed = old_checksum != item["checksum"]
        # last_seen_at proves the public source still contained this record.
        row.last_seen_at = now
        if changed:
            for field, value in item.items():
                setattr(row, field, value)
            row.source_updated_at = now
            db.add(WantedRecordHistory(
                wanted_record_id=row.id,
                source_key=item["source_key"],
                change_type="status_change" if old_status != item.get("status") else "update",
                old_checksum=old_checksum,
                new_checksum=item["checksum"],
                snapshot_json=_wanted_snapshot(item),
                changed_at=now,
            ))
            updated += 1
        else:
            # Backfill stable source id/status without rewriting unchanged source data.
            if not row.source_record_id and item.get("source_record_id"):
                row.source_record_id = item["source_record_id"]
            if not row.checksum:
                row.checksum = item["checksum"]
            unchanged += 1

    db.add(AuditEvent(
        actor=actor,
        action=action,
        resource_type="wanted_source",
        detail=(
            f"pages={fetched_pages};records={len(records)};inserted={inserted};"
            f"updated={updated};unchanged={unchanged};active={active_records};"
            f"suspended={suspended_records}"
        ),
    ))
    db.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "active_records": active_records,
        "suspended_records": suspended_records,
    }


async def _run_wanted_sync(full: bool, actor: str = "system"):
    if full:
        pages = max(50, min(int(os.getenv("WANTED_FULL_SYNC_PAGES", "250") or 250), 500))
        action = "wanted_full_sync_page"
        mode = "full"
    else:
        pages = max(1, min(int(os.getenv("WANTED_DELTA_PAGES", "5") or 5), 25))
        action = "wanted_delta_sync_page"
        mode = "delta"

    totals = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "active_records": 0,
        "suspended_records": 0,
        "parsed_records": 0,
        "fetched_pages": 0,
    }

    async with WANTED_SYNC_LOCK:
        WANTED_SYNC_STATE.update({
            "running": True,
            "mode": mode,
            "source_status": None,
            "page": 0,
            "total_pages": 0,
            "records_seen": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "last_error": None,
        })
        try:
            sources = [
                (OFFICIAL_WANTED_URL, "active"),
                (OFFICIAL_SUSPENDED_URL, "dinh_na"),
            ]
            for source_url, source_status in sources:
                WANTED_SYNC_STATE["source_status"] = source_status
                async for page_number, total_pages, records in iter_official_list_pages(
                    source_url, source_status, max_pages=pages
                ):
                    WANTED_SYNC_STATE.update({
                        "page": page_number,
                        "total_pages": total_pages,
                    })
                    with SessionLocal() as db:
                        stats = _apply_wanted_records(
                            db,
                            records,
                            actor,
                            action,
                            page_number,
                        )
                    totals["inserted"] += stats["inserted"]
                    totals["updated"] += stats["updated"]
                    totals["unchanged"] += stats["unchanged"]
                    totals["active_records"] += stats["active_records"]
                    totals["suspended_records"] += stats["suspended_records"]
                    totals["parsed_records"] += len(records)
                    totals["fetched_pages"] += 1
                    WANTED_SYNC_STATE["records_seen"] = totals["parsed_records"]

            WANTED_SYNC_STATE.update({
                "running": False,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
            })
            return totals
        except Exception as exc:
            WANTED_SYNC_STATE.update({
                "running": False,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "last_error": f"{exc.__class__.__name__}: {str(exc)[:240]}",
            })
            raise


async def _system_sync_wanted():
    interval = max(30, int(os.getenv("WANTED_AUTO_SYNC_MINUTES", "60") or 60))
    full_hours = max(6, int(os.getenv("WANTED_FULL_SYNC_HOURS", "24") or 24))
    last_full = None

    # Bootstrap a full catalog only when the local registry is still small.
    try:
        with SessionLocal() as db:
            current_count = len(list(db.scalars(select(WantedRecord.id)).all()))
        if current_count < 1000:
            await _run_wanted_sync(full=True)
            last_full = datetime.now(timezone.utc)
    except Exception as exc:
        with SessionLocal() as db:
            db.add(AuditEvent(actor="system", action="wanted_sync_error", resource_type="wanted_source", detail=exc.__class__.__name__))
            db.commit()

    while True:
        try:
            now = datetime.now(timezone.utc)
            due_full = last_full is None or (now - last_full).total_seconds() >= full_hours * 3600
            await _run_wanted_sync(full=due_full)
            if due_full:
                last_full = now
        except Exception as exc:
            with SessionLocal() as db:
                db.add(AuditEvent(actor="system", action="wanted_sync_error", resource_type="wanted_source", detail=exc.__class__.__name__))
                db.commit()
        await asyncio.sleep(interval * 60)


@app.on_event("startup")
async def start_wanted_auto_sync():
    if int(os.getenv("WANTED_AUTO_SYNC_MINUTES", "60") or 60) >= 30:
        asyncio.create_task(_system_sync_wanted())


@app.get("/health")
def health():
    return {"status": "ok", "service": "trace-ai", "version": "1.5.0-rc2"}

@app.get("/health/ready")
def readiness():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with SessionLocal() as db:
            queued = db.scalar(select(func.count()).select_from(OperationalJob).where(OperationalJob.status == "queued")) or 0
            failed = db.scalar(select(func.count()).select_from(OperationalJob).where(OperationalJob.status == "failed")) or 0
        JOB_QUEUE_DEPTH.set(queued)
        return {
            "status": "ready",
            "database": "ok",
            "wanted_sync_running": bool(WANTED_SYNC_STATE.get("running")),
            "wanted_sync_last_error": WANTED_SYNC_STATE.get("last_error"),
            "queued_jobs": queued,
            "failed_jobs": failed,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc.__class__.__name__}")

@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    if os.getenv("APP_ENV", "development") == "production":
        expected = os.getenv("METRICS_TOKEN", "")
        supplied = request.headers.get("X-Metrics-Token", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=404, detail="not found")
    return metrics_response()

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
    cached = IMAGE_CACHE.get(wanted_id)
    if cached:
        IMAGE_CACHE.move_to_end(wanted_id)
        content_type, image_bytes = cached
        return Response(
            content=image_bytes,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-TRACE-Image-Source": "cache",
                "X-TRACE-Image-Normalized": "true",
            },
        )

    row = db.get(WantedRecord, wanted_id)
    if not row:
        raise HTTPException(status_code=404, detail="wanted record not found")

    image_url = row.image_url
    detail_url = row.detail_url
    # Release the DB connection before any slow external network I/O.
    # This prevents bulk image loading from exhausting the SQLAlchemy pool
    # and blocking core endpoints such as /public/wanted and Radar data.
    db.close()

    headers = {
        "User-Agent": "TRACE-AI/1.4 (+official public-data image proxy)",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        if not image_url and detail_url:
            detail_host = (urlparse(detail_url).hostname or "").lower()
            if detail_host != "truyna.bocongan.gov.vn":
                raise HTTPException(status_code=400, detail="unsupported official detail host")
            detail = await client.get(detail_url)
            detail.raise_for_status()
            parsed = parse_wanted_detail(detail.text, str(detail.url))
            image_url = parsed.get("image_url")
            # Do not hold/reopen a DB transaction while proxying image bytes.
            # Source synchronization persists metadata separately.

        if not image_url:
            raise HTTPException(status_code=404, detail="official image not available")

        image_host = (urlparse(image_url).hostname or "").lower()
        if image_host != "truyna.bocongan.gov.vn":
            raise HTTPException(status_code=400, detail="unsupported official image host")

        try:
            async with IMAGE_FETCH_SEMAPHORE:
                image_response = await client.get(image_url)
                image_response.raise_for_status()
                image_bytes = image_response.content
                raw_content_type = image_response.headers.get("content-type", "image/jpeg")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"official image fetch failed: {exc.__class__.__name__}")

        content_type = raw_content_type.split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=502, detail="official source did not return an image")

        if content_type in {"image/jpeg", "image/jpg"}:
            if not image_bytes.startswith(b"\xff\xd8"):
                raise HTTPException(status_code=502, detail="official JPEG signature is invalid")
            end = image_bytes.find(b"\xff\xd9")
            if end >= 0:
                image_bytes = image_bytes[: end + 2]
        elif content_type == "image/png":
            marker = b"IEND\xaeB\x60\x82"
            end = image_bytes.find(marker)
            if end >= 0:
                image_bytes = image_bytes[: end + len(marker)]

    IMAGE_CACHE[wanted_id] = (content_type, image_bytes)
    IMAGE_CACHE.move_to_end(wanted_id)
    while len(IMAGE_CACHE) > IMAGE_CACHE_MAX:
        IMAGE_CACHE.popitem(last=False)

    return Response(
        content=image_bytes,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-TRACE-Image-Source": "truyna.bocongan.gov.vn",
            "X-TRACE-Image-Normalized": "true",
        },
    )

@app.get("/public/wanted/{wanted_id}/image-data")
async def public_wanted_image_data(wanted_id: int, db: Session = Depends(get_db)):
    image_response = await public_wanted_image(wanted_id, db)
    content_type = image_response.media_type or "image/jpeg"
    return {
        "id": wanted_id,
        "content_type": content_type,
        "data_url": f"data:{content_type};base64,{base64.b64encode(image_response.body).decode('ascii')}",
        "source": "truyna.bocongan.gov.vn",
    }

def _wanted_query(q: str | None, status: str | None):
    stmt = select(WantedRecord)
    if status in {"active", "dinh_na"}:
        stmt = stmt.where(WantedRecord.status == status)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            WantedRecord.full_name.ilike(term),
            WantedRecord.registered_address.ilike(term),
            WantedRecord.offense.ilike(term),
            WantedRecord.warrant_reference.ilike(term),
            WantedRecord.issuing_unit.ilike(term),
        ))
    return stmt.order_by(WantedRecord.last_seen_at.desc(), WantedRecord.id.desc())


def _wanted_source_status(db: Session):
    latest = db.scalar(select(WantedRecord).order_by(WantedRecord.last_seen_at.desc()).limit(1))
    total = db.scalar(select(func.count()).select_from(WantedRecord)) or 0
    active = db.scalar(select(func.count()).select_from(WantedRecord).where(WantedRecord.status == "active")) or 0
    suspended = db.scalar(select(func.count()).select_from(WantedRecord).where(WantedRecord.status == "dinh_na")) or 0
    history = db.scalar(select(func.count()).select_from(WantedRecordHistory)) or 0
    return {
        "source_name": SOURCE_NAME,
        "source_url": OFFICIAL_WANTED_URL,
        "suspended_source_url": OFFICIAL_SUSPENDED_URL,
        "records": total,
        "active_records": active,
        "suspended_records": suspended,
        "history_events": history,
        "last_sync": latest.last_seen_at if latest else None,
        "sync_interval_minutes": max(30, int(os.getenv("WANTED_AUTO_SYNC_MINUTES", "60") or 60)),
        "full_sync_hours": max(6, int(os.getenv("WANTED_FULL_SYNC_HOURS", "24") or 24)),
        "image_cache_items": len(IMAGE_CACHE),
        "image_cache_limit": IMAGE_CACHE_MAX,
        "sync_progress": dict(WANTED_SYNC_STATE),
    }


@app.get("/public/wanted", response_model=list[WantedRecordOut])
def public_wanted_records(
    q: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return list(db.scalars(_wanted_query(q, status).offset(offset).limit(limit)).all())


@app.get("/public/wanted/sync-state")
def public_wanted_sync_state():
    return dict(WANTED_SYNC_STATE)

@app.get("/public/wanted/source-status")
def public_wanted_source_status(db: Session = Depends(get_db)):
    return _wanted_source_status(db)

@app.get("/wanted", response_model=list[WantedRecordOut])
def list_wanted_records(
    q: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return list(db.scalars(_wanted_query(q, status).offset(offset).limit(limit)).all())


@app.get("/wanted/source-status")
def wanted_source_status(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    return _wanted_source_status(db)


@app.get("/wanted/{wanted_id}/history")
def wanted_record_history(
    wanted_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    limit = max(1, min(limit, 500))
    return [
        {
            "id": h.id,
            "wanted_record_id": h.wanted_record_id,
            "source_key": h.source_key,
            "change_type": h.change_type,
            "old_checksum": h.old_checksum,
            "new_checksum": h.new_checksum,
            "snapshot_json": h.snapshot_json,
            "changed_at": h.changed_at,
        }
        for h in db.scalars(
            select(WantedRecordHistory)
            .where(WantedRecordHistory.wanted_record_id == wanted_id)
            .order_by(WantedRecordHistory.changed_at.desc())
            .limit(limit)
        ).all()
    ]


@app.post("/jobs/wanted-sync")
def enqueue_wanted_sync_job(
    full: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    job = enqueue_job(db, "wanted_sync", {"full": full})
    add_audit(db, user, "job_enqueue", "operational_job", job.id, f"type=wanted_sync;full={full}")
    db.commit()
    return {"id": job.id, "job_type": job.job_type, "status": job.status, "full": full}


@app.get("/jobs")
def list_jobs(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    limit = max(1, min(limit, 200))
    rows = list(db.scalars(select(OperationalJob).order_by(OperationalJob.id.desc()).limit(limit)).all())
    return [
        {
            "id": row.id,
            "job_type": row.job_type,
            "status": row.status,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "run_after": row.run_after,
            "locked_at": row.locked_at,
            "last_error": row.last_error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@app.post("/wanted/sync", response_model=WantedSyncOut)
async def sync_wanted_records(
    full: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    if WANTED_SYNC_LOCK.locked():
        raise HTTPException(status_code=409, detail="wanted sync already running")
    try:
        stats = await _run_wanted_sync(full=full, actor=user.uid)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"official wanted source unavailable: {exc.__class__.__name__}")
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return WantedSyncOut(
        source=OFFICIAL_WANTED_URL,
        fetched_pages=stats["fetched_pages"],
        parsed_records=stats["parsed_records"],
        inserted=stats["inserted"],
        updated=stats["updated"],
        unchanged=stats["unchanged"],
        active_records=stats["active_records"],
        suspended_records=stats["suspended_records"],
        synced_at=datetime.now(timezone.utc),
    )


# SoloHost/production web UI: API routes above keep precedence; static UI is mounted last.
WEB_DIST_DIR = Path(os.getenv("WEB_DIST_DIR", "/app/web-dist"))
if WEB_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="web")
