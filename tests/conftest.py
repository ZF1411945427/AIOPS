"""Shared fixtures and test configuration."""
import hashlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.models import User, NotificationChannel, SystemConfig, Asset, Alert, Incident, AlertRule, AlertEscalation, AlertEventLink, AlertSuppression, AlertSilence, AlertWebhook, AnomalyConfig, ApiToken, AssetLifecycle, AssetChangeLog, BlueGreenDeploy, ChangeRequest, ClusterAnomalyEvent, DashboardCardConfig, DataSource, DiscoveryJob, ExtCmdbConfig, ExtEventSource, FeatureStoreItem, HotSpotAnalysis, IncidentAlert, K8sEvent, KafkaPipeline, KnowledgeBase, LogAnomalyRule, MetricRecord, NetFlowCollector, NetFlowRecord, NotificationLog, NotificationTemplate, PredictionModel, RemediationLog, RemediationWorkflow, Report, ReportSchedule, Runbook, ScriptTask, ServiceMeshConfig, Span, TraceAnomalyConfig, AssetRelation, CiAttribute, CiModel, SavedFilter, ChangeTask, AutoRemediation
from app.services import config_service


TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        admin = User(username="admin", password_hash=hashlib.sha256(b"admin123").hexdigest(), role="admin")
        db.add(admin)
        db.add(NotificationChannel(name="系统日志", type="log", config="{}", enabled=True))
        db.commit()
        config_service.init_configs(db)
    db.close()
    yield
    db = TestingSessionLocal()
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass
    db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    client.post("/login", data={"username": "admin", "password": "admin123"})
    return client