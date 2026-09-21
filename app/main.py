from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Case, MissingPerson, SearchZone, TimelineEvent
from .schemas import (
    CaseCreate, CaseOut,
    MissingPersonCreate, MissingPersonOut,
    SearchZoneCreate, SearchZoneOut,
    TimelineEventCreate, TimelineEventOut,
)
from .security import Role, require_role

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TRACE-AI",
    version="0.2.0",
    description="MVP hỗ trợ quản lý vụ việc, timeline và vùng tìm kiếm.",
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "trace-ai"}

@app.post("/cases", response_model=CaseOut)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.ANALYST)),
):
    if db.scalar(select(Case).where(Case.case_code == payload.case_code)):
        raise HTTPException(status_code=409, detail="case_code already exists")
    obj = Case(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/cases", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.VIEWER)),
):
    return list(db.scalars(select(Case).order_by(Case.started_at.desc())).all())

@app.post("/cases/{case_id}/person", response_model=MissingPersonOut)
def add_person(
    case_id: int,
    payload: MissingPersonCreate,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.ANALYST)),
):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    obj = MissingPerson(case_id=case_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.post("/cases/{case_id}/timeline", response_model=TimelineEventOut)
def add_timeline_event(
    case_id: int,
    payload: TimelineEventCreate,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.ANALYST)),
):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    obj = TimelineEvent(case_id=case_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/timeline", response_model=list[TimelineEventOut])
def get_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.VIEWER)),
):
    return list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.case_id == case_id)
            .order_by(TimelineEvent.event_time.asc())
        ).all()
    )

@app.post("/cases/{case_id}/search-zones", response_model=SearchZoneOut)
def add_search_zone(
    case_id: int,
    payload: SearchZoneCreate,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.ANALYST)),
):
    if not db.get(Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    obj = SearchZone(case_id=case_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@app.get("/cases/{case_id}/search-zones", response_model=list[SearchZoneOut])
def get_search_zones(
    case_id: int,
    db: Session = Depends(get_db),
    _role = Depends(require_role(Role.VIEWER)),
):
    return list(
        db.scalars(
            select(SearchZone)
            .where(SearchZone.case_id == case_id)
            .order_by(SearchZone.score.desc())
        ).all()
    )
