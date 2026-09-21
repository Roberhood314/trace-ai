from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import WantedRecord
from app.services.gateway import public_gateway_signals, public_gateway_status, response_units_snapshot


def test_public_gateway_reads_official_wanted_records():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(WantedRecord(
            source_key="k1",
            full_name="Nguyen Van Test",
            birth_year=1990,
            registered_address="Ha Noi",
            parents=None,
            offense="Demo offense",
            warrant_reference="QD-001",
            issuing_unit="Demo unit",
            detail_url="https://truyna.bocongan.gov.vn/detail",
            image_url=None,
            danger_level="cao",
            source_url="https://truyna.bocongan.gov.vn/",
            source_name="Cổng thông tin truy nã - Bộ Công an",
            imported_at=datetime(2026, 1, 1),
            last_seen_at=datetime(2026, 1, 2),
        ))
        db.commit()

        status = public_gateway_status(db)
        assert status["enabled"] is True
        assert status["sources"][0]["records"] == 1

        rows = public_gateway_signals(db, q="Nguyen", limit=10)
        assert len(rows) == 1
        assert rows[0]["sourceKind"] == "public_official"
        assert rows[0]["confidence"] == 1.0
        assert rows[0]["referenceUrl"].startswith("https://truyna.bocongan.gov.vn/")


def test_response_units_empty_without_authorized_gateway(monkeypatch):
    monkeypatch.delenv("RESPONSE_UNIT_GATEWAY_URL", raising=False)
    import asyncio
    assert asyncio.run(response_units_snapshot()) == []
