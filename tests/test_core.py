"""Core system tests: auth, dashboard, settings, users, tokens."""


class TestAuth:
    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        # 前端已迁移到 Vue SPA，HTML 壳含 <div id="app">
        assert "app" in resp.text or "AIOPS" in resp.text

    def test_login_success(self, client):
        resp = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        assert resp.status_code == 303

    def test_login_fail(self, client):
        resp = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 200
        assert "login-error" in resp.text or "用户名或密码错误" in resp.text

    def test_logout(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303

    def test_auth_redirect(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 303
        assert "/login" in resp.headers.get("location", "")


class TestDashboard:
    def test_dashboard_page(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        # 前端已迁移到 Vue SPA，HTML 壳含 <div id="app">
        assert "app" in resp.text or "AIOPS" in resp.text

    def test_dashboard_data(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        # Dashboard should load without errors
        assert resp.status_code == 200

    def test_dashboard_config(self, auth_client):
        resp = auth_client.get("/dashboard-config")
        assert resp.status_code == 200


class TestSettings:
    def test_settings_page(self, auth_client):
        resp = auth_client.get("/settings")
        assert resp.status_code == 200

    def test_update_settings(self, auth_client):
        resp = auth_client.post("/settings/update", data={
            "key": "escalation_minutes", "value": "10",
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestUsers:
    def test_users_page(self, auth_client):
        resp = auth_client.get("/users")
        assert resp.status_code == 200

    def test_create_user(self, auth_client):
        resp = auth_client.post("/users/create", data={
            "username": "testuser", "password": "test123", "role": "viewer",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_user_duplicate(self, auth_client):
        auth_client.post("/users/create", data={"username": "dup", "password": "p", "role": "viewer"})
        resp = auth_client.post("/users/create", data={"username": "dup", "password": "p", "role": "viewer"})
        # Should handle duplicate gracefully
        assert resp.status_code in (200, 303)


class TestTokens:
    def test_tokens_page(self, auth_client):
        resp = auth_client.get("/api-tokens")
        assert resp.status_code == 200

    def test_create_token(self, auth_client):
        resp = auth_client.post("/api-tokens/create", data={
            "name": "test-token", "permissions": "read",
        }, follow_redirects=False)
        assert resp.status_code in (200, 303)


class TestPublicPaths:
    """Verify public paths don't require auth."""
    def test_static_files(self, client):
        resp = client.get("/static/css/style.css")
        assert resp.status_code in (200, 404)  # 404 if file missing but no redirect

    def test_login_public(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
