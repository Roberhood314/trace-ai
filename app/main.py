import base64
import hashlib
import asyncio
import json
import os
import hmac
import io
import re
import secrets
import unicodedata
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageFilter, ImageStat
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

try:
    import redis.asyncio as redis_async
except Exception:  # Redis remains optional for local/dev fallback.
    redis_async = None

from .database import SessionLocal, engine, get_db
from .models import AccountDeletionRequest, AuditEvent, Case, ConnectorDevice, Evidence, MissingPerson, OperationalJob, SearchZone, TimelineEvent, UASGeofence, UASObservation, UASReview, UASTrack, UASTrackPoint, User, WantedRecord, WantedRecordHistory
from .schemas import (
    AISummaryOut, AuditOut, AuthOut,
    CaseCreate, CaseOut, EvidenceOut,
    MissingPersonCreate, MissingPersonOut,
    SearchZoneCreate, SearchZoneOut,
    TimelineEventCreate, TimelineEventOut,
    UserOut, UserRoleUpdate,
    WantedRecordOut, WantedSyncOut,
)
from .security import CurrentUser, Role, _secret, get_current_user, issue_token, require_role
from .services.wanted_sync import OFFICIAL_SUSPENDED_URL, OFFICIAL_WANTED_URL, SOURCE_NAME, fetch_official_wanted, iter_official_list_pages, parse_wanted_detail, record_checksum, utcnow_naive
from .services.gateway import public_gateway_signals, public_gateway_status, response_units_snapshot, weather_snapshot
from .services.uas_fusion import fusion_status, ingest_observation as fusion_ingest_observation, review_track as fusion_review_track, track_snapshot
from .observability import JOB_QUEUE_DEPTH, metrics_middleware, metrics_response
from .job_queue import enqueue_job
from .rate_limit import enforce as enforce_rate_limit
from .integrations import ConnectorHeartbeat, MobileUASObservation, UASEvent, clear_simulated_uas_tracks, ingest_heartbeat, ingest_mobile_uas_observation, ingest_uas_event, integration_status, recent_mobile_uas_observations, recent_uas_tracks, set_simulated_uas_track

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
REDIS_URL = os.getenv("REDIS_URL", "").strip()
CACHE_TTL_SECONDS = max(5, min(int(os.getenv("TRACE_CACHE_TTL_SECONDS", "30") or 30), 600))
EVENT_CHANNEL = os.getenv("TRACE_EVENT_CHANNEL", "trace:events")
_redis_client = None
EVENT_SUBSCRIBERS: set[asyncio.Queue] = set()

async def get_redis_client():
    global _redis_client
    if not REDIS_URL or redis_async is None:
        return None
    if _redis_client is None:
        _redis_client = redis_async.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    try:
        await _redis_client.ping()
        return _redis_client
    except Exception:
        return None

async def cache_get_json(key: str):
    client = await get_redis_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

async def cache_set_json(key: str, value, ttl: int = CACHE_TTL_SECONDS):
    client = await get_redis_client()
    if client is None:
        return
    try:
        await client.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        pass

async def cache_delete_prefix(prefix: str):
    client = await get_redis_client()
    if client is None:
        return
    try:
        async for key in client.scan_iter(match=f"{prefix}*"):
            await client.delete(key)
    except Exception:
        pass

async def publish_event(kind: str, payload: dict):
    event = {
        "type": kind,
        "at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    client = await get_redis_client()
    if client is not None:
        try:
            await client.publish(EVENT_CHANNEL, json.dumps(event, ensure_ascii=False, default=str))
            return
        except Exception:
            pass
    dead = []
    for queue in tuple(EVENT_SUBSCRIBERS):
        try:
            queue.put_nowait(event)
        except Exception:
            dead.append(queue)
    for queue in dead:
        EVENT_SUBSCRIBERS.discard(queue)

async def redis_event_listener():
    client = await get_redis_client()
    if client is None:
        return
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(EVENT_CHANNEL)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("data"):
                try:
                    event = json.loads(message["data"])
                except Exception:
                    event = None
                if isinstance(event, dict):
                    dead = []
                    for queue in tuple(EVENT_SUBSCRIBERS):
                        try:
                            queue.put_nowait(event)
                        except Exception:
                            dead.append(queue)
                    for queue in dead:
                        EVENT_SUBSCRIBERS.discard(queue)
            await asyncio.sleep(0.05)
    finally:
        await pubsub.close()

IMAGE_CACHE_MAX = max(16, min(int(os.getenv("WANTED_IMAGE_CACHE_ITEMS", "128") or 128), 512))
IMAGE_CACHE: OrderedDict[int, tuple[str, bytes]] = OrderedDict()
THUMB_CACHE_MAX = max(32, min(int(os.getenv("WANTED_THUMB_CACHE_ITEMS", "256") or 256), 1024))
THUMB_CACHE: OrderedDict[int, bytes] = OrderedDict()
WANTED_SYNC_LOCK = asyncio.Lock()
UAS_TEST_TASK: asyncio.Task | None = None
UAS_TEST_STATE = {
    "running": False,
    "started_at": None,
    "completed_at": None,
    "tracks": 0,
    "duration_seconds": 0,
}

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
    version="2.0.0-rc1",
    description="TRACE AI X: operational command platform with wanted intelligence, UAS fusion, geospatial workflows and human-verified analysis.",
)

allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
for origin in (
    "https://tracevnid.fyi",
    "https://www.tracevnid.fyi",
    "https://localhost",
    "capacitor://localhost",
):
    if origin not in allowed_origins:
        allowed_origins.append(origin)

configured_origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip()
pi_browser_origin_regex = r"https://([a-z0-9-]+\.)*(pinet\.com|minepi\.com)"
origin_regex = (
    f"(?:{configured_origin_regex})|(?:{pi_browser_origin_regex})"
    if configured_origin_regex
    else pi_browser_origin_regex
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Role"],
    max_age=600,
)

app.middleware("http")(metrics_middleware)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    # Pi's domain verifier is strict and should receive a minimal plain-text
    # response without browser-only framing or resource-policy headers.
    if request.url.path == "/validation-key.txt":
        return response
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
    image_public_path = (
        request.url.path.startswith("/public/wanted/")
        and (
            request.url.path.endswith("/image")
            or request.url.path.endswith("/thumbnail")
            or request.url.path.endswith("/image-data")
        )
    )
    if image_public_path:
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    else:
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' https://sdk.minepi.com; connect-src 'self' https://api.minepi.com; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'")
    return response

@app.middleware("http")
async def reviewer_read_only(request, call_next):
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = jwt.decode(token, _secret(), algorithms=["HS256"])
            except jwt.PyJWTError:
                payload = {}
            if payload.get("sub") == "play-reviewer":
                return JSONResponse(status_code=403, content={"detail": "Google Play reviewer account is read-only"})
    return await call_next(request)

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

class PiPaymentRequest(BaseModel):
    payment_id: str
    txid: str | None = None

class DeviceRegisterRequest(BaseModel):
    name: str
    integration_id: str
    platform: str
    capabilities: list[str] = []

class DeviceUpdateRequest(BaseModel):
    is_active: bool

class ReviewerLoginRequest(BaseModel):
    username: str
    password: str

class AccountDeletionRequestCreate(BaseModel):
    pi_username: str
    contact_email: str

class UASTestRequest(BaseModel):
    center_latitude: float = 10.7769
    center_longitude: float = 106.7009
    tracks: int = 3
    duration_seconds: int = 60

class UASGeofenceCreate(BaseModel):
    name: str
    center_latitude: float
    center_longitude: float
    radius_m: float
    severity: str = "warning"

class UASReviewRequest(BaseModel):
    decision: str
    note: str | None = None


class WantedPageOut(BaseModel):
    items: list[WantedRecordOut]
    total: int
    limit: int
    offset: int
    has_more: bool


def _payment_enabled():
    if os.getenv("PI_TEST_PAYMENT_ENABLED", "false").lower() != "true" or not os.getenv("PI_API_KEY"):
        raise HTTPException(status_code=503, detail="Pi test payments are not configured")

async def _pi_payment(method: str, path: str, body: dict | None = None):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.request(method, f"https://api.minepi.com/v2/payments/{path}",
                headers={"Authorization": f"Key {os.environ['PI_API_KEY']}"}, json=body)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="Pi payment service unavailable") from None

def _check_test_payment(payment: dict, user: CurrentUser):
    metadata = payment.get("metadata") or {}
    if (payment.get("user_uid") != user.uid or payment.get("direction") != "user_to_app"
        or payment.get("network") != "Pi Testnet"
        or not isinstance(metadata, dict) or metadata.get("purpose") != "trace_ai_test"
        or payment.get("amount") != 0.01):
        raise HTTPException(status_code=403, detail="payment does not match test purchase")
    if payment.get("status", {}).get("cancelled") or payment.get("status", {}).get("user_cancelled"):
        raise HTTPException(status_code=409, detail="payment cancelled")

@app.post("/public/account-deletion-request")
def request_account_deletion(payload: AccountDeletionRequestCreate, db: Session = Depends(get_db)):
    username = payload.pi_username.strip()
    email = payload.contact_email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,128}", username):
        raise HTTPException(status_code=422, detail="invalid Pi username")
    if not re.fullmatch(r"[^@\s]{1,128}@[^@\s]{1,128}\.[^@\s]{2,63}", email):
        raise HTTPException(status_code=422, detail="invalid contact email")
    token = secrets.token_hex(24)
    row = AccountDeletionRequest(
        pi_username=username,
        contact_email=email,
        status="pending",
        request_token=token,
    )
    db.add(row)
    db.commit()
    return {
        "accepted": True,
        "request_id": row.id,
        "message": "Yêu cầu xóa tài khoản đã được tiếp nhận. Chủ tài khoản sẽ được xác minh trước khi dữ liệu bị xóa.",
    }


@app.get("/pi/test-payment/config")
def test_payment_config():
    return {"enabled": os.getenv("PI_TEST_PAYMENT_ENABLED", "false").lower() == "true" and bool(os.getenv("PI_API_KEY"))}

@app.post("/pi/test-payment/approve")
async def approve_test_payment(payload: PiPaymentRequest, user: CurrentUser = Depends(get_current_user)):
    _payment_enabled()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", payload.payment_id):
        raise HTTPException(status_code=400, detail="invalid payment id")
    payment = await _pi_payment("GET", payload.payment_id)
    _check_test_payment(payment, user)
    if payment.get("status", {}).get("developer_approved"):
        return {"status": "approved"}
    await _pi_payment("POST", f"{payload.payment_id}/approve", {})
    return {"status": "approved"}

@app.post("/pi/test-payment/complete")
async def complete_test_payment(payload: PiPaymentRequest, user: CurrentUser = Depends(get_current_user)):
    _payment_enabled()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", payload.payment_id) or not re.fullmatch(r"[A-Za-z0-9]{1,128}", payload.txid or ""):
        raise HTTPException(status_code=400, detail="invalid payment data")
    payment = await _pi_payment("GET", payload.payment_id)
    _check_test_payment(payment, user)
    transaction = payment.get("transaction") or {}
    if transaction.get("txid") != payload.txid or not transaction.get("verified") or not payment.get("status", {}).get("transaction_verified"):
        raise HTTPException(status_code=409, detail="transaction not verified by Pi")
    if payment.get("status", {}).get("developer_completed"):
        return {"status": "completed"}
    completed = await _pi_payment("POST", f"{payload.payment_id}/complete", {"txid": payload.txid})
    if not completed.get("status", {}).get("developer_completed"):
        raise HTTPException(status_code=502, detail="Pi has not completed payment")
    return {"status": "completed"}

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
            await cache_delete_prefix("wanted:")
            await publish_event("wanted.sync.completed", totals)
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

@app.on_event("startup")
async def start_realtime_listener():
    if REDIS_URL:
        asyncio.create_task(redis_event_listener())




def _hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _device_auth(request: Request, db: Session) -> ConnectorDevice:
    device_id = request.headers.get("X-TRACE-Device-ID", "").strip()
    authorization = request.headers.get("Authorization", "").strip()
    if not device_id or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="device authentication required")
    token = authorization.split(" ", 1)[1].strip()
    if len(token) < 24:
        raise HTTPException(status_code=401, detail="invalid device credential")
    row = db.scalar(select(ConnectorDevice).where(ConnectorDevice.device_id == device_id))
    if not row or not row.is_active:
        raise HTTPException(status_code=403, detail="device disabled or unknown")
    if not hmac.compare_digest(row.token_hash, _hash_device_token(token)):
        raise HTTPException(status_code=401, detail="invalid device credential")
    row.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return row

@app.post("/devices/register")
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    integration_id = payload.integration_id.strip().lower()
    platform = payload.platform.strip().lower()
    if integration_id not in {"vision", "geo", "air", "satellite", "mobility", "iot", "fusion"}:
        raise HTTPException(status_code=422, detail="unsupported integration")
    if platform not in {"windows", "linux", "macos", "android", "ios", "gateway", "embedded"}:
        raise HTTPException(status_code=422, detail="unsupported platform")
    device_id = f"dev_{uuid.uuid4().hex[:20]}"
    token = secrets.token_urlsafe(32)
    row = ConnectorDevice(
        device_id=device_id,
        name=payload.name.strip()[:255] or device_id,
        integration_id=integration_id,
        platform=platform,
        token_hash=_hash_device_token(token),
        capabilities_json=json.dumps(payload.capabilities[:32], ensure_ascii=False),
        is_active=True,
        created_by=user.uid,
    )
    db.add(row)
    add_audit(db, user, "device_register", "connector_device", device_id, f"integration={integration_id};platform={platform}")
    db.commit()
    return {
        "device_id": device_id,
        "device_token": token,
        "integration_id": integration_id,
        "platform": platform,
        "note": "Store this token securely; it is only returned at registration.",
    }

@app.get("/devices")
def list_devices(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    rows = list(db.scalars(select(ConnectorDevice).order_by(ConnectorDevice.created_at.desc())).all())
    return [{
        "device_id": row.device_id,
        "name": row.name,
        "integration_id": row.integration_id,
        "platform": row.platform,
        "capabilities": json.loads(row.capabilities_json or "[]"),
        "is_active": row.is_active,
        "created_at": row.created_at,
        "last_seen_at": row.last_seen_at,
    } for row in rows]

@app.patch("/devices/{device_id}")
def update_device(
    device_id: str,
    payload: DeviceUpdateRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    row = db.scalar(select(ConnectorDevice).where(ConnectorDevice.device_id == device_id))
    if not row:
        raise HTTPException(status_code=404, detail="device not found")
    row.is_active = payload.is_active
    add_audit(db, user, "device_enable" if payload.is_active else "device_disable", "connector_device", device_id)
    db.commit()
    return {"device_id": device_id, "is_active": row.is_active}

@app.post("/device/heartbeat")
def device_heartbeat(
    payload: ConnectorHeartbeat,
    request: Request,
    db: Session = Depends(get_db),
):
    row = _device_auth(request, db)
    if payload.device_id != row.device_id:
        raise HTTPException(status_code=403, detail="device identity mismatch")
    if payload.platform != row.platform:
        raise HTTPException(status_code=403, detail="device platform mismatch")
    return ingest_heartbeat(row.integration_id, payload)

@app.post("/device/uas/events")
def device_uas_ingest(
    payload: UASEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    row = _device_auth(request, db)
    if row.integration_id != "air":
        raise HTTPException(status_code=403, detail="device is not authorized for UAS ingestion")
    capabilities = set(json.loads(row.capabilities_json or "[]"))
    if capabilities and payload.source not in capabilities:
        raise HTTPException(status_code=403, detail="UAS source not allowed for this device")
    event = ingest_uas_event(payload)
    event["device_id"] = row.device_id
    event["platform"] = row.platform
    return event

def _require_gateway_key(request: Request):
    expected = os.getenv("TRACE_GATEWAY_KEY", "").strip()
    supplied = request.headers.get("X-TRACE-Gateway-Key", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="UAS gateway is not configured")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid gateway credential")

@app.get("/public/integrations/status")
async def public_integrations_status():
    return await integration_status()

@app.post("/integrations/{integration_id}/heartbeat")
def connector_heartbeat(integration_id: str, payload: ConnectorHeartbeat, request: Request):
    _require_gateway_key(request)
    try:
        return ingest_heartbeat(integration_id, payload)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown integration") from None

@app.post("/integrations/uas/events")
def uas_ingest_event(payload: UASEvent, request: Request, db: Session = Depends(get_db)):
    _require_gateway_key(request)
    live = ingest_uas_event(payload)
    observation_key = f"{payload.source}:{payload.track_id}:{payload.timestamp.isoformat()}"
    obs, track = fusion_ingest_observation(
        db,
        observation_key=observation_key,
        source=payload.source,
        source_track_id=payload.track_id,
        observed_at=payload.timestamp,
        created_by="gateway",
        latitude=payload.latitude,
        longitude=payload.longitude,
        altitude_m=payload.altitude_m,
        speed_mps=payload.speed_mps,
        heading_deg=payload.heading_deg,
        classification=payload.classification,
        confidence=min(payload.sensor_confidence, payload.classification_confidence),
        metadata={"source_reference": payload.source_reference},
    )
    return {
        "live": live,
        "fusion_observation_id": obs.id,
        "fusion_track": track_snapshot(track) if track else None,
        "verification_required": True,
    }

@app.post("/uas/mobile/observations")
def mobile_uas_observation(
    payload: MobileUASObservation,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    item = ingest_mobile_uas_observation(user.uid, payload)
    mobile_heartbeat = ConnectorHeartbeat(
        device_id=f"mobile:{user.uid}:{payload.session_id}"[:128],
        platform="gateway",
        version="mobile-scan-v1",
        capabilities=["camera", "gps", "heading", "uas_observation"],
    )
    ingest_heartbeat("vision", mobile_heartbeat)
    ingest_heartbeat("geo", mobile_heartbeat)
    ingest_heartbeat("air", mobile_heartbeat)
    observation_key = f"mobile:{user.uid}:{payload.session_id}:{payload.observation_id}"
    obs, track = fusion_ingest_observation(
        db,
        observation_key=observation_key,
        source="mobile_camera",
        source_track_id=None,
        observed_at=payload.observed_at,
        created_by=user.uid,
        observer_latitude=payload.observer_latitude,
        observer_longitude=payload.observer_longitude,
        observer_heading_deg=payload.device_heading_deg,
        classification=payload.classification,
        confidence=payload.confidence,
        metadata={
            "session_id": payload.session_id,
            "bbox": [payload.bbox_x, payload.bbox_y, payload.bbox_w, payload.bbox_h],
            "gps_accuracy_m": payload.gps_accuracy_m,
            "device_pitch_deg": payload.device_pitch_deg,
            "frame_width": payload.frame_width,
            "frame_height": payload.frame_height,
        },
    )
    return {
        "accepted": True,
        "mode": "mobile_camera",
        "verification_required": True,
        "observation": item,
        "fusion_observation_id": obs.id,
        "fusion_track": track_snapshot(track) if track else None,
    }

@app.get("/uas/mobile/observations")
def mobile_uas_observations(
    limit: int = 100,
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    return {
        "items": recent_mobile_uas_observations(limit),
        "source": "mobile_camera",
        "location_semantics": "observer_position_plus_bearing",
        "verification_required": True,
    }

@app.get("/uas/tracks")
def uas_tracks(
    limit: int = 100,
    include_simulation: bool = False,
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    return {
        "items": recent_uas_tracks(limit, include_simulation=include_simulation),
        "classification": "decision-support",
        "verification_required": True,
        "simulation_included": include_simulation,
    }


async def _run_uas_test(center_latitude: float, center_longitude: float, tracks: int, duration_seconds: int):
    UAS_TEST_STATE.update({
        "running": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "tracks": tracks,
        "duration_seconds": duration_seconds,
    })
    try:
        steps = max(1, min(duration_seconds, 300))
        for step in range(steps):
            now = datetime.now(timezone.utc).isoformat()
            for i in range(tracks):
                angle = ((step * 7) + (i * 120)) % 360
                lat = center_latitude + 0.0025 * ((i + 1) / max(1, tracks)) * (1 if (step + i) % 2 == 0 else -1)
                lon = center_longitude + 0.0025 * (((step % 10) - 5) / 5.0)
                set_simulated_uas_track(
                    f"SIM-UAV-{i+1}",
                    {
                        "source": "simulation",
                        "timestamp": now,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude_m": 60 + i * 35 + (step % 20),
                        "speed_mps": 8 + i * 3,
                        "heading_deg": angle,
                        "classification": "uav",
                        "sensor_confidence": 0.95,
                        "classification_confidence": 0.9,
                        "source_reference": "TRACE UAV TEST MODE",
                    },
                )
            await asyncio.sleep(1)
    finally:
        UAS_TEST_STATE.update({
            "running": False,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

@app.post("/uas/test/start")
async def start_uas_test(
    payload: UASTestRequest,
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    global UAS_TEST_TASK
    if UAS_TEST_TASK and not UAS_TEST_TASK.done():
        raise HTTPException(status_code=409, detail="UAS test is already running")
    if not (-90 <= payload.center_latitude <= 90 and -180 <= payload.center_longitude <= 180):
        raise HTTPException(status_code=422, detail="invalid test center")
    tracks = max(1, min(int(payload.tracks), 5))
    duration = max(10, min(int(payload.duration_seconds), 300))
    clear_simulated_uas_tracks()
    UAS_TEST_TASK = asyncio.create_task(
        _run_uas_test(payload.center_latitude, payload.center_longitude, tracks, duration)
    )
    return {
        "mode": "simulation",
        "running": True,
        "tracks": tracks,
        "duration_seconds": duration,
        "warning": "SIMULATION ONLY - not live UAV detection",
    }

@app.post("/uas/test/stop")
async def stop_uas_test(
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    global UAS_TEST_TASK
    if UAS_TEST_TASK and not UAS_TEST_TASK.done():
        UAS_TEST_TASK.cancel()
        try:
            await UAS_TEST_TASK
        except asyncio.CancelledError:
            pass
    removed = clear_simulated_uas_tracks()
    UAS_TEST_STATE.update({
        "running": False,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"mode": "simulation", "running": False, "removed_tracks": removed}

@app.get("/uas/test/status")
def uas_test_status(
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    return {"mode": "simulation", **UAS_TEST_STATE}

@app.get("/fusion/status")
def uas_fusion_status(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    return fusion_status(db)

@app.get("/fusion/tracks")
def uas_fusion_tracks(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    rows = list(db.scalars(
        select(UASTrack).order_by(UASTrack.last_seen_at.desc()).limit(max(1, min(limit, 500)))
    ).all())
    return {"items": [track_snapshot(row) for row in rows]}

@app.get("/fusion/tracks/{track_id}/trajectory")
def uas_fusion_trajectory(
    track_id: int,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    track = db.get(UASTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="track not found")
    points = list(db.scalars(
        select(UASTrackPoint)
        .where(UASTrackPoint.track_id == track_id)
        .order_by(UASTrackPoint.observed_at.asc())
        .limit(max(1, min(limit, 1000)))
    ).all())
    return {
        "track": track_snapshot(track),
        "points": [{
            "observed_at": p.observed_at,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "altitude_m": p.altitude_m,
            "speed_mps": p.speed_mps,
            "heading_deg": p.heading_deg,
            "confidence": p.confidence,
        } for p in points],
    }

@app.post("/fusion/geofences")
def create_uas_geofence(
    payload: UASGeofenceCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.COMMANDER)),
):
    if not (-90 <= payload.center_latitude <= 90 and -180 <= payload.center_longitude <= 180):
        raise HTTPException(status_code=422, detail="invalid geofence coordinates")
    if payload.radius_m <= 0 or payload.radius_m > 100000:
        raise HTTPException(status_code=422, detail="invalid geofence radius")
    if payload.severity not in {"warning", "critical"}:
        raise HTTPException(status_code=422, detail="invalid severity")
    row = UASGeofence(
        name=payload.name[:128],
        center_latitude=payload.center_latitude,
        center_longitude=payload.center_longitude,
        radius_m=payload.radius_m,
        severity=payload.severity,
        is_active=True,
        created_by=user.uid,
    )
    db.add(row)
    add_audit(db, user, "uas_geofence_create", "uas_geofence", None, payload.name[:128])
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "severity": row.severity, "radius_m": row.radius_m}

@app.post("/fusion/tracks/{track_id}/review")
def review_uas_fusion_track(
    track_id: int,
    payload: UASReviewRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.ANALYST)),
):
    try:
        track = fusion_review_track(db, track_id, payload.decision, user.uid, payload.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="track not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    add_audit(db, user, "uas_track_review", "uas_track", track.id, f"decision={payload.decision}")
    db.commit()
    return track_snapshot(track)

@app.get("/uas/status")
async def uas_status(user: CurrentUser = Depends(require_role(Role.VIEWER))):
    air = next(x for x in await integration_status() if x["id"] == "air")
    return air

@app.get("/validation-key.txt", include_in_schema=False)
def pi_domain_validation_key():
    # Return the Pi Developer Portal validation key exactly, without a BOM or newline.
    return Response(
        content=b"daf9e8ccfb57f1861b9d986fc6c8b9aec8ae95d01766627062dc5ad131206304034979f296a1e9c36b374f9e5a3f3b80a95e905dc09af21b3b883ca26f9bda7e",
        headers={
            "Content-Type": "text/plain",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@app.get("/", include_in_schema=False)
def pi_checkout_entry(request: Request):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host != "tracevnid.fyi":
        index_path = Path(os.getenv("WEB_DIST_DIR", "/app/web-dist")) / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="web app not built")

    html = """<!doctype html>
<html lang="vi" translate="no">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="google" content="notranslate">
  <title>TRACE-AI · Pi Payment</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#0d1726;color:#eef4ff;margin:0;padding:24px}
    .card{max-width:560px;margin:40px auto;background:#14233b;border:1px solid #29456f;border-radius:22px;padding:24px}
    h1{margin:0 0 8px;font-size:30px} p{color:#b8c7dd;line-height:1.5}
    button{width:100%;border:0;border-radius:14px;padding:16px 18px;font-size:18px;font-weight:700;margin-top:12px}
    #login{background:#7a3fa0;color:white} #pay{background:#f6b83f;color:#24183a;display:none}
    #status{margin-top:18px;min-height:48px;color:#d8e6f8;white-space:pre-wrap}
    .ok{color:#70e0ad}.err{color:#ff9d9d}
  </style>
  <script src="https://sdk.minepi.com/pi-sdk.js"></script>
</head>
<body class="notranslate">
  <div class="card">
    <h1>TRACE-AI</h1>
    <p>Hoàn tất xác thực Pi và giao dịch User-to-App 0,01 Test Pi cho bước 10.</p>
    <button id="login">Đăng nhập Pi</button>
    <button id="pay">Thanh toán 0,01 Test Pi</button>
    <div id="status">Đang khởi tạo Pi SDK…</div>
  </div>
  <script src="/pi-checkout.js"></script>
</body>
</html>"""
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Language": "vi",
        },
    )

@app.get("/pi-checkout.js", include_in_schema=False)
def pi_checkout_script():
    script = r"""
(function () {
  const status = document.getElementById('status');
  const login = document.getElementById('login');
  const pay = document.getElementById('pay');
  let token = '';

  function msg(text, cls) {
    status.textContent = text;
    status.className = cls || '';
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type':'application/json', ...(token ? {'Authorization':'Bearer '+token} : {})},
      body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('HTTP '+res.status));
    return data;
  }

  try {
    if (!window.Pi) throw new Error('Pi SDK chưa tải được. Hãy mở bằng Pi Browser.');
    window.Pi.init({version:'2.0', sandbox:false});
    msg('Pi SDK sẵn sàng. Bấm “Đăng nhập Pi”.');
  } catch (e) {
    msg(e.message || 'Không thể khởi tạo Pi SDK.', 'err');
  }

  login.addEventListener('click', async function () {
    login.disabled = true;
    msg('Đang mở xác thực Pi…');
    try {
      const incomplete = [];
      const auth = await window.Pi.authenticate(['username','payments'], function (payment) {
        if (payment && payment.identifier && payment.transaction && payment.transaction.txid) incomplete.push(payment);
      });
      const verified = await api('/auth/pi/verify', {access_token: auth.accessToken});
      token = verified.token;
      for (const p of incomplete) {
        await api('/pi/test-payment/complete', {payment_id:p.identifier, txid:p.transaction.txid});
      }
      login.textContent = 'Đã đăng nhập: ' + (verified.username || 'Pi User');
      pay.style.display = 'block';
      msg('Đăng nhập thành công. Bấm “Thanh toán 0,01 Test Pi”.', 'ok');
    } catch (e) {
      login.disabled = false;
      msg('Đăng nhập thất bại: ' + (e.message || e), 'err');
    }
  });

  pay.addEventListener('click', function () {
    if (!token) return msg('Hãy đăng nhập Pi trước.', 'err');
    pay.disabled = true;
    msg('Đang tạo giao dịch 0,01 Test Pi…');
    try {
      window.Pi.createPayment({
        amount: 0.01,
        memo: 'TRACE-AI - Step 10 User-to-App payment',
        metadata: {purpose:'trace_ai_test'}
      }, {
        onReadyForServerApproval: async function (paymentId) {
          try {
            await api('/pi/test-payment/approve', {payment_id:paymentId});
            msg('Backend đã approve. Hãy xác nhận giao dịch trong Pi Wallet.');
          } catch (e) {
            pay.disabled = false;
            msg('Approve thất bại: '+(e.message || e), 'err');
          }
        },
        onReadyForServerCompletion: async function (paymentId, txid) {
          try {
            await api('/pi/test-payment/complete', {payment_id:paymentId, txid:txid});
            msg('GIAO DỊCH HOÀN TẤT ✓\nQuay lại Pi Developer để kiểm tra Step 10.', 'ok');
          } catch (e) {
            pay.disabled = false;
            msg('Complete thất bại: '+(e.message || e), 'err');
          }
        },
        onCancel: function () {
          pay.disabled = false;
          msg('Bạn đã hủy giao dịch.');
        },
        onError: function (e) {
          pay.disabled = false;
          msg('Pi Payment lỗi: '+((e && e.message) || e), 'err');
        }
      });
    } catch (e) {
      pay.disabled = false;
      msg('Không thể tạo giao dịch: '+(e.message || e), 'err');
    }
  });
})();"""
    return Response(script, media_type="application/javascript", headers={"Cache-Control":"no-store"})

@app.get("/privacy", include_in_schema=False)
def privacy_alias():
    path = Path(os.getenv("WEB_DIST_DIR", "/app/web-dist")) / "privacy.html"
    if path.exists():
        return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="privacy policy not found")

@app.get("/terms", include_in_schema=False)
def terms_alias():
    path = Path(os.getenv("WEB_DIST_DIR", "/app/web-dist")) / "terms.html"
    if path.exists():
        return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="terms of service not found")

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

@app.post("/auth/reviewer", response_model=AuthOut)
def reviewer_login(payload: ReviewerLoginRequest, db: Session = Depends(get_db)):
    expected_user = os.getenv("PLAY_REVIEWER_USERNAME", "").strip()
    expected_password = os.getenv("PLAY_REVIEWER_PASSWORD", "")
    if not expected_user or not expected_password:
        raise HTTPException(status_code=404, detail="reviewer login disabled")
    if not (secrets.compare_digest(payload.username.strip(), expected_user) and secrets.compare_digest(payload.password, expected_password)):
        raise HTTPException(status_code=401, detail="invalid reviewer credentials")
    reviewer_uid = "play-reviewer"
    user = db.scalar(select(User).where(User.pi_uid == reviewer_uid))
    if not user:
        user = User(pi_uid=reviewer_uid, username="Google Play Reviewer", role="reviewer")
        db.add(user)
    else:
        user.username = "Google Play Reviewer"
        user.role = "reviewer"
        user.is_active = True
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(user)
    return AuthOut(token=issue_token(user), username=user.username, role=user.role, verified=True)


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

@app.delete("/account")
def delete_account(db: Session = Depends(get_db), user: CurrentUser = Depends(require_role(Role.VIEWER))):
    uid = user.uid
    if uid == "play-reviewer":
        raise HTTPException(status_code=403, detail="reviewer account cannot be deleted")
    target = db.scalar(select(User).where(User.pi_uid == uid))
    if not target:
        raise HTTPException(status_code=404, detail="user not found")

    deleted_actor = f"deleted-user-{secrets.token_hex(8)}"

    evidence_rows = list(db.scalars(select(Evidence).where(Evidence.created_by == uid)).all())
    for evidence in evidence_rows:
        path = UPLOAD_DIR / evidence.stored_name
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        db.delete(evidence)

    for model in (Case, TimelineEvent, SearchZone, ConnectorDevice, UASObservation, UASGeofence):
        db.execute(update(model).where(model.created_by == uid).values(created_by=deleted_actor))
    db.execute(update(UASReview).where(UASReview.reviewer_uid == uid).values(reviewer_uid=deleted_actor))
    db.execute(update(AuditEvent).where(AuditEvent.actor == uid).values(actor=deleted_actor))

    db.delete(target)
    db.commit()
    return {"deleted": True}


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
                "Cross-Origin-Resource-Policy": "cross-origin",
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
            if image_url:
                with SessionLocal() as image_db:
                    image_row = image_db.get(WantedRecord, wanted_id)
                    if image_row:
                        image_row.image_url = image_url
                        if parsed.get("danger_level") and not image_row.danger_level:
                            image_row.danger_level = parsed.get("danger_level")
                        image_row.source_updated_at = utcnow_naive()
                        image_row.checksum = record_checksum({
                            "source_record_id": image_row.source_record_id,
                            "full_name": image_row.full_name,
                            "birth_year": image_row.birth_year,
                            "registered_address": image_row.registered_address,
                            "parents": image_row.parents,
                            "offense": image_row.offense,
                            "warrant_reference": image_row.warrant_reference,
                            "issuing_unit": image_row.issuing_unit,
                            "detail_url": image_row.detail_url,
                            "image_url": image_row.image_url,
                            "danger_level": image_row.danger_level,
                            "status": image_row.status,
                        })
                        image_db.commit()

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
                "Cross-Origin-Resource-Policy": "cross-origin",
        },
    )

@app.get("/public/wanted/{wanted_id}/thumbnail")
async def public_wanted_thumbnail(wanted_id: int, db: Session = Depends(get_db)):
    cached = THUMB_CACHE.get(wanted_id)
    if cached:
        THUMB_CACHE.move_to_end(wanted_id)
        return Response(
            content=cached,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800", "X-TRACE-Thumbnail": "memory-cache", "Cross-Origin-Resource-Policy": "cross-origin"},
        )

    client = await get_redis_client()
    redis_key = f"wanted:thumb:{wanted_id}"
    if client is not None:
        try:
            raw_client = redis_async.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=2, socket_timeout=2)
            raw = await raw_client.get(redis_key)
            await raw_client.aclose()
            if raw:
                THUMB_CACHE[wanted_id] = raw
                return Response(content=raw, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800", "X-TRACE-Thumbnail": "redis-cache", "Cross-Origin-Resource-Policy": "cross-origin"})
        except Exception:
            pass

    image_response = await public_wanted_image(wanted_id, db)
    try:
        with Image.open(io.BytesIO(image_response.body)) as image:
            image = image.convert("RGB")
            image.thumbnail((180, 220), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="WEBP", quality=78, method=4)
            thumb = out.getvalue()
    except Exception:
        raise HTTPException(status_code=502, detail="thumbnail generation failed")

    THUMB_CACHE[wanted_id] = thumb
    THUMB_CACHE.move_to_end(wanted_id)
    while len(THUMB_CACHE) > THUMB_CACHE_MAX:
        THUMB_CACHE.popitem(last=False)

    if REDIS_URL and redis_async is not None:
        try:
            raw_client = redis_async.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=2, socket_timeout=2)
            await raw_client.setex(redis_key, 86400, thumb)
            await raw_client.aclose()
        except Exception:
            pass

    return Response(
        content=thumb,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800", "X-TRACE-Thumbnail": "generated", "Cross-Origin-Resource-Policy": "cross-origin"},
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

PROVINCE_LABELS = [
    "An Giang", "Bắc Ninh", "Cà Mau", "Cao Bằng", "Cần Thơ", "Đà Nẵng", "Đắk Lắk",
    "Điện Biên", "Đồng Nai", "Đồng Tháp", "Gia Lai", "Hà Nội", "Hà Tĩnh", "Hải Phòng",
    "Huế", "Hưng Yên", "Khánh Hòa", "Lai Châu", "Lâm Đồng", "Lạng Sơn", "Lào Cai",
    "Nghệ An", "Ninh Bình", "Phú Thọ", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị",
    "Sơn La", "Tây Ninh", "Thái Nguyên", "Thanh Hóa", "TP. Hồ Chí Minh",
    "Tuyên Quang", "Vĩnh Long",
]

PROVINCE_HISTORICAL_NAMES = {
    "An Giang": ["An Giang", "Kiên Giang"],
    "Bắc Ninh": ["Bắc Ninh", "Bắc Giang"],
    "Cà Mau": ["Cà Mau", "Bạc Liêu"],
    "Cao Bằng": ["Cao Bằng"],
    "Cần Thơ": ["Cần Thơ", "Hậu Giang", "Sóc Trăng"],
    "Đà Nẵng": ["Đà Nẵng", "Quảng Nam"],
    "Đắk Lắk": ["Đắk Lắk", "Đắc Lắk", "Phú Yên"],
    "Điện Biên": ["Điện Biên"],
    "Đồng Nai": ["Đồng Nai", "Bình Phước"],
    "Đồng Tháp": ["Đồng Tháp", "Tiền Giang"],
    "Gia Lai": ["Gia Lai", "Bình Định"],
    "Hà Nội": ["Hà Nội"],
    "Hà Tĩnh": ["Hà Tĩnh"],
    "Hải Phòng": ["Hải Phòng", "Hải Dương"],
    "Huế": ["Huế", "Thừa Thiên Huế"],
    "Hưng Yên": ["Hưng Yên", "Thái Bình"],
    "Khánh Hòa": ["Khánh Hòa", "Ninh Thuận"],
    "Lai Châu": ["Lai Châu"],
    "Lâm Đồng": ["Lâm Đồng", "Đắk Nông", "Đắc Nông", "Bình Thuận"],
    "Lạng Sơn": ["Lạng Sơn"],
    "Lào Cai": ["Lào Cai", "Yên Bái"],
    "Nghệ An": ["Nghệ An"],
    "Ninh Bình": ["Ninh Bình", "Nam Định", "Hà Nam"],
    "Phú Thọ": ["Phú Thọ", "Vĩnh Phúc", "Hòa Bình"],
    "Quảng Ngãi": ["Quảng Ngãi", "Kon Tum"],
    "Quảng Ninh": ["Quảng Ninh"],
    "Quảng Trị": ["Quảng Trị", "Quảng Bình"],
    "Sơn La": ["Sơn La"],
    "Tây Ninh": ["Tây Ninh", "Long An"],
    "Thái Nguyên": ["Thái Nguyên", "Bắc Kạn"],
    "Thanh Hóa": ["Thanh Hóa", "Thanh Hoá"],
    "TP. Hồ Chí Minh": ["TP. Hồ Chí Minh", "TP Hồ Chí Minh", "TP.HCM", "TP HCM", "Hồ Chí Minh", "Bình Dương", "Bà Rịa - Vũng Tàu", "Bà Rịa Vũng Tàu", "Vũng Tàu"],
    "Tuyên Quang": ["Tuyên Quang", "Hà Giang"],
    "Vĩnh Long": ["Vĩnh Long", "Bến Tre", "Trà Vinh"],
}

def _fold_location(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D").lower()

_PROVINCE_ALIAS_INDEX = sorted(
    [(_fold_location(alias), current) for current, aliases in PROVINCE_HISTORICAL_NAMES.items() for alias in aliases],
    key=lambda item: len(item[0]),
    reverse=True,
)

def _canonical_province_name(value: str | None) -> str | None:
    folded = _fold_location(value or "").strip()
    if not folded:
        return None
    for alias, current in _PROVINCE_ALIAS_INDEX:
        if folded == alias:
            return current
    return None

def _province_from_address(address: str | None) -> str:
    if not address:
        return "Chưa xác định"
    folded = _fold_location(address)
    for alias, current in _PROVINCE_ALIAS_INDEX:
        if alias and alias in folded:
            return current
    return "Chưa xác định"

def _wanted_query(q: str | None, status: str | None, province: str | None = None):
    stmt = select(WantedRecord)
    if status in {"active", "dinh_na"}:
        stmt = stmt.where(WantedRecord.status == status)
    elif status != "all":
        # Default public wanted views must match the Ministry's current wanted list.
        # Suspended records stay in the registry/history but are excluded from the
        # active wanted count unless explicitly requested.
        stmt = stmt.where(WantedRecord.status == "active")
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            WantedRecord.full_name.ilike(term),
            WantedRecord.registered_address.ilike(term),
            WantedRecord.offense.ilike(term),
            WantedRecord.warrant_reference.ilike(term),
            WantedRecord.issuing_unit.ilike(term),
        ))
    if province and province.strip():
        current = _canonical_province_name(province) or province.strip()
        terms = PROVINCE_HISTORICAL_NAMES.get(current, [current])
        stmt = stmt.where(or_(*[WantedRecord.registered_address.ilike(f"%{term}%") for term in terms]))
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
        "records": active,
        "registry_records": total,
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


@app.get("/public/wanted/page", response_model=WantedPageOut)
async def public_wanted_page(
    response: Response,
    q: str | None = None,
    status: str | None = None,
    province: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    cache_key = f"wanted:page:{status or 'all'}:{province or 'all'}:{q or ''}:{limit}:{offset}"
    cached = await cache_get_json(cache_key)
    if cached is not None:
        response.headers["X-TRACE-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, max-age=10, stale-while-revalidate=30"
        return cached

    stmt = _wanted_query(q, status, province)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    items = list(db.scalars(stmt.offset(offset).limit(limit)).all())
    payload = {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }
    serializable = {
        "items": [WantedRecordOut.model_validate(item).model_dump(mode="json") for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": payload["has_more"],
    }
    await cache_set_json(cache_key, serializable, ttl=20)
    response.headers["X-TRACE-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, max-age=10, stale-while-revalidate=30"
    return payload

@app.get("/public/wanted/stats/provinces")
async def public_wanted_province_stats(response: Response, db: Session = Depends(get_db)):
    cache_key = "wanted:stats:provinces"
    cached = await cache_get_json(cache_key)
    if cached is not None:
        response.headers["X-TRACE-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
        return cached

    addresses = list(db.scalars(
        select(WantedRecord.registered_address).where(WantedRecord.status == "active")
    ).all())
    counts: dict[str, int] = {}
    for address in addresses:
        label = _province_from_address(address)
        counts[label] = counts.get(label, 0) + 1
    provinces = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    payload = {
        "total": len(addresses),
        "unknown": counts.get("Chưa xác định", 0),
        "provinces": provinces,
    }
    await cache_set_json(cache_key, payload, ttl=120)
    response.headers["X-TRACE-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
    return payload

@app.get("/public/events")
async def public_event_stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    EVENT_SUBSCRIBERS.add(queue)

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            EVENT_SUBSCRIBERS.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

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



@app.get("/wanted/{wanted_id}/intelligence")
def wanted_record_intelligence(
    wanted_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    row = db.get(WantedRecord, wanted_id)
    if not row:
        raise HTTPException(status_code=404, detail="wanted record not found")

    source_host = (urlparse(row.detail_url or row.source_url or "").hostname or "").lower()
    official_source = source_host == "truyna.bocongan.gov.vn"
    fields = {
        "full_name": bool(row.full_name),
        "birth_year": row.birth_year is not None,
        "registered_address": bool(row.registered_address),
        "parents": bool(row.parents),
        "offense": bool(row.offense),
        "warrant_reference": bool(row.warrant_reference),
        "issuing_unit": bool(row.issuing_unit),
        "detail_url": bool(row.detail_url),
        "image_reference": bool(row.image_url or row.detail_url),
        "checksum": bool(row.checksum),
    }
    completeness = round(sum(1 for value in fields.values() if value) / len(fields) * 100)
    history_count = db.scalar(
        select(func.count(WantedRecordHistory.id)).where(WantedRecordHistory.wanted_record_id == wanted_id)
    ) or 0

    checks = []
    if not official_source:
        checks.append("Nguồn chi tiết cần được xác minh lại trước khi sử dụng nghiệp vụ.")
    if not row.image_url:
        checks.append("Ảnh chưa được lưu URL trực tiếp; hệ thống sẽ thử đọc ảnh từ hồ sơ nguồn chính thức khi mở.")
    if not row.warrant_reference:
        checks.append("Thiếu số/ngày quyết định truy nã trong bản ghi hiện tại.")
    if not row.registered_address:
        checks.append("Thiếu địa chỉ đăng ký thường trú trong bản ghi hiện tại.")
    if not checks:
        checks.append("Hồ sơ có độ đầy đủ cao; vẫn cần đối chiếu nguồn chính thức trước mọi quyết định.")

    return {
        "wanted_id": row.id,
        "generated_at": datetime.now(timezone.utc),
        "source": {
            "name": row.source_name,
            "url": row.detail_url or row.source_url,
            "official_host": official_source,
            "checksum_present": bool(row.checksum),
            "history_events": int(history_count),
            "last_seen_at": row.last_seen_at,
            "source_updated_at": row.source_updated_at,
        },
        "record": {
            "status": row.status,
            "danger_level": row.danger_level,
            "completeness_percent": completeness,
            "field_presence": fields,
        },
        "analysis": {
            "summary": (
                f"Hồ sơ {row.full_name} hiện có mức đầy đủ dữ liệu {completeness}%. "
                f"Trạng thái nguồn: {'chính thức' if official_source else 'cần xác minh'}. "
                f"Hệ thống ghi nhận {int(history_count)} sự kiện lịch sử thay đổi."
            ),
            "recommended_checks": checks,
            "identity_decision": "human_verification_required",
        },
        "disclaimer": "Phân tích hỗ trợ rà soát dữ liệu; không tự kết luận danh tính một người từ hình ảnh.",
    }


@app.get("/wanted/{wanted_id}/visual-analysis")
async def wanted_record_visual_analysis(
    wanted_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    row = db.get(WantedRecord, wanted_id)
    if not row:
        raise HTTPException(status_code=404, detail="wanted record not found")

    try:
        image_response = await public_wanted_image(wanted_id, db)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "wanted_id": wanted_id,
                "available": False,
                "quality_score": 0,
                "reason": "official image not available",
                "identity_decision": "human_verification_required",
            }
        raise

    try:
        with Image.open(io.BytesIO(image_response.body)) as image:
            image = image.convert("RGB")
            width, height = image.size
            gray = image.convert("L")
            stats = ImageStat.Stat(gray)
            brightness = float(stats.mean[0])
            contrast = float(stats.stddev[0])
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_mean = float(ImageStat.Stat(edges).mean[0])
    except Exception:
        raise HTTPException(status_code=502, detail="official image analysis failed") from None

    megapixels = (width * height) / 1_000_000
    resolution_score = min(100.0, megapixels / 0.5 * 100.0)
    brightness_score = max(0.0, 100.0 - abs(brightness - 128.0) / 128.0 * 100.0)
    contrast_score = min(100.0, contrast / 55.0 * 100.0)
    sharpness_score = min(100.0, edge_mean / 22.0 * 100.0)
    quality_score = round(
        resolution_score * 0.35
        + brightness_score * 0.20
        + contrast_score * 0.20
        + sharpness_score * 0.25
    )

    observations = []
    if resolution_score < 45:
        observations.append("Độ phân giải thấp; không nên phóng lớn để suy luận chi tiết khuôn mặt.")
    if brightness < 55:
        observations.append("Ảnh tối; chi tiết vùng tối có thể không đáng tin cậy.")
    elif brightness > 205:
        observations.append("Ảnh sáng mạnh; một số chi tiết có thể bị mất.")
    if contrast_score < 35:
        observations.append("Độ tương phản thấp.")
    if sharpness_score < 35:
        observations.append("Độ sắc nét thấp hoặc ảnh có thể bị mờ.")
    if not observations:
        observations.append("Ảnh đủ chất lượng cho đối chiếu trực quan thủ công.")

    return {
        "wanted_id": wanted_id,
        "available": True,
        "dimensions": {"width": width, "height": height, "megapixels": round(megapixels, 3)},
        "metrics": {
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "edge_sharpness": round(edge_mean, 1),
        },
        "quality_score": quality_score,
        "manual_comparison_ready": quality_score >= 55,
        "observations": observations,
        "identity_decision": "human_verification_required",
        "disclaimer": "Chỉ đánh giá chất lượng ảnh và khả năng đối chiếu thủ công; không thực hiện nhận dạng sinh trắc học tự động.",
    }


@app.get("/system/readiness")
async def system_readiness(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    integrations = await integration_status()
    by_id = {item["id"]: item for item in integrations}
    wanted_count = db.scalar(select(func.count(WantedRecord.id)).where(WantedRecord.status == "active")) or 0
    fusion = fusion_status(db)

    def connector_state(integration_id: str):
        item = by_id.get(integration_id)
        if not item:
            return {"state": "not_configured", "detail": "connector definition unavailable"}
        return {
            "state": item.get("status", "not_configured"),
            "detail": item.get("detail") or item.get("message"),
            "last_seen": item.get("last_seen"),
        }

    modules = {
        "wanted_registry": {
            "state": "operational" if wanted_count > 0 else "degraded",
            "records": int(wanted_count),
            "detail": "Official wanted registry data available" if wanted_count > 0 else "No active wanted records loaded",
        },
        "wanted_image_proxy": {
            "state": "operational",
            "detail": "Official-source image proxy, cache and thumbnail pipeline enabled",
        },
        "wanted_visual_analysis": {
            "state": "operational",
            "detail": "Image quality analysis enabled; no automatic biometric identity conclusion",
        },
        "fusion_core": {
            "state": "operational",
            "detail": fusion.get("engine", "TRACE Fusion Core"),
            "active_tracks": fusion.get("active_tracks", 0),
        },
        "vision_connector": connector_state("vision"),
        "geo_connector": connector_state("geo"),
        "airspace_connector": connector_state("air"),
    }
    return {
        "generated_at": datetime.now(timezone.utc),
        "modules": modules,
        "principle": "Preserve → Extend → Validate → Upgrade",
    }


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
