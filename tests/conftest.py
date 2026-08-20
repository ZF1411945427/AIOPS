"""Test infrastructure: in-memory SQLite, session fixture, sample data factories."""
import os
os.environ.setdefault("AIOPS_DB_URL", "sqlite:///:memory:")

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Asset, Alert, AlertRule, Incident, WorkflowTemplate

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)


@event.listens_for(TEST_ENGINE, "connect")
def _set_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.close()


TEST_SESSION = sessionmaker(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(TEST_ENGINE)
    yield
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def db() -> Session:
    session = TEST_SESSION()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_asset(db) -> Asset:
    a = Asset(
        name="test-server-01",
        ci_type="server",
        ip="192.168.1.100",
        status="online",
        connection_type="ssh",
        ci_attributes='{"os":"linux","cpu":4,"memory":8192}',
        created_at=datetime.utcnow(),
        last_checked_at=datetime.utcnow(),
        latency_ms=5.0,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture
def sample_alert(db) -> Alert:
    al = Alert(
        rule_id=1,
        asset_id=1,
        metric_name="cpu_usage",
        actual_value=95.0,
        threshold=80.0,
        severity="critical",
        status="triggered",
        message="CPU usage exceeded threshold: 95% > 80%",
        created_at=datetime.utcnow(),
        archived=False,
    )
    db.add(al)
    db.commit()
    db.refresh(al)
    return al


@pytest.fixture
def sample_incident(db) -> Incident:
    inc = Incident(
        title="[critical] test-server-01 异常",
        severity="critical",
        status="open",
        impact="服务不可用",
        description="测试故障单",
        alert_count=1,
        created_at=datetime.utcnow(),
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


@pytest.fixture
def sample_alert_rule(db) -> AlertRule:
    rule = AlertRule(
        name="svc_up 服务存活检测",
        kind="svc_up",
        metric_name="svc_up",
        threshold=1.0,
        severity="critical",
        enabled=True,
        condition="lt",
        cooldown=60,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def assert_ok(status: int):
    assert status == 200, f"Expected 200, got {status}"


def assert_fields(obj: Any, **expected):
    for k, v in expected.items():
        actual = getattr(obj, k, None)
        assert actual == v, f"Field {k}: expected {v!r}, got {actual!r}"