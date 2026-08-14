"""FastAPI TestClient 集成测试: 覆盖 main.py 路由层 + 公开/认证端点。

不走子进程, 在 pytest 进程内起 app 实例, 覆盖率计入 pytest-cov。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPublicEndpoints:
    def test_healthz(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200

    def test_readyz(self, client):
        r = client.get("/readyz")
        # 无 Milvus 环境返回 503(DB 正常), 有 Milvus 返回 200
        assert r.status_code in (200, 503)
        data = r.json()
        assert data.get("db") == "ok"

    def test_db_mode(self, client):
        r = client.get("/api/system/db-mode")
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data

    def test_login_page_html(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_login_json(self, client):
        r = client.post("/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("token")

    def test_login_bad_credentials(self, client):
        r = client.post("/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
        assert r.json().get("ok") is False


class TestAuthenticatedEndpoints:
    @pytest.fixture
    def token(self, client):
        r = client.post("/login", json={"username": "admin", "password": "admin123"})
        return r.json()["token"]

    def test_system_overview(self, client, token):
        r = client.get("/api/system/overview", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "assets" in data

    def test_reload_menu(self, client, token):
        r = client.get("/api/system/reload-menu", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"

    def test_assets_list(self, client, token):
        r = client.get("/assets/api/list", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    def test_slo(self, client, token):
        r = client.get("/api/sre/slo", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        # SLO 可能空列表, 但应返回 JSON 数组
        assert isinstance(r.json(), list)

    def test_correlation_analyze(self, client, token):
        r = client.get("/observability/correlation/analyze",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "time_range_hours" in data

    def test_agent_chat_send(self, client, token):
        r = client.post("/agent/chat/send",
                       json={"message": "你好", "stream": False},
                       headers={"Authorization": f"Bearer {token}"})
        # Agent 端点可能在无 AI 提供商时返回 422/400, 但不应该 404
        assert r.status_code in (200, 201, 400, 422, 500)

    def test_token_refresh(self, client, token):
        r = client.post("/refresh", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("token")