"""Asset management & CMDB tests."""


class TestAssetCRUD:
    def test_assets_page(self, auth_client):
        resp = auth_client.get("/assets")
        assert resp.status_code == 200

    def test_create_asset(self, auth_client):
        resp = auth_client.post("/assets/create", data={
            "name": "test-server", "ip": "10.0.0.1",
            "ci_type": "server", "type": "host", "tags": "test",
        }, follow_redirects=False)
        assert resp.status_code == 303
        resp2 = auth_client.get("/assets")
        assert "test-server" in resp2.text

    def test_edit_asset(self, auth_client):
        auth_client.post("/assets/create", data={"name": "s1", "ip": "1.1.1.1", "ci_type": "server", "type": "host"})
        resp = auth_client.post("/assets/1/edit", data={
            "name": "s1-renamed", "ip": "1.1.1.1", "ci_type": "server",
            "type": "host", "tags": "updated",
        }, follow_redirects=False)
        assert resp.status_code == 303
        resp2 = auth_client.get("/assets")
        assert "s1-renamed" in resp2.text

    def test_delete_asset(self, auth_client):
        auth_client.post("/assets/create", data={"name": "del-me", "ip": "9.9.9.9", "ci_type": "server", "type": "host"})
        resp = auth_client.post("/assets/1/delete", follow_redirects=False)
        assert resp.status_code == 303

    def test_asset_with_tags(self, auth_client):
        auth_client.post("/assets/create", data={
            "name": "tagged", "ip": "2.2.2.2", "ci_type": "server",
            "type": "host", "tags": "prod,db,critical",
        })
        resp = auth_client.get("/assets")
        assert "prod" in resp.text


class TestTagManagement:
    def test_tags_page(self, auth_client):
        resp = auth_client.get("/tags")
        assert resp.status_code == 200

    def test_assign_tag(self, auth_client):
        auth_client.post("/assets/create", data={"name": "t1", "ip": "3.3.3.3", "ci_type": "server", "type": "host"})
        resp = auth_client.post("/tags/assign", data={"tag": "critical", "asset_id": 1}, follow_redirects=False)
        assert resp.status_code in (200, 303)


class TestLifecycle:
    def test_lifecycle_page(self, auth_client):
        resp = auth_client.get("/lifecycle")
        assert resp.status_code == 200

    def test_lifecycle_change(self, auth_client):
        auth_client.post("/assets/create", data={"name": "lc-test", "ip": "4.4.4.4", "ci_type": "server", "type": "host"})
        resp = auth_client.post("/lifecycle/transition/1", data={
            "new_status": "active", "comment": "go live",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_lifecycle_history(self, auth_client):
        auth_client.post("/assets/create", data={"name": "lc-hist", "ip": "5.5.5.5", "ci_type": "server", "type": "host"})
        auth_client.post("/lifecycle/transition/1", data={"new_status": "active", "comment": "start"})
        resp = auth_client.get("/lifecycle")
        assert "start" in resp.text or "active" in resp.text


class TestChangeTracking:
    def test_changes_page(self, auth_client):
        resp = auth_client.get("/asset-changes")
        assert resp.status_code == 200


class TestBedAPI:
    def test_ci_models(self, auth_client):
        resp = auth_client.get("/ci-models")
        assert resp.status_code == 200


class TestDiscovery:
    def test_discovery_page(self, auth_client):
        resp = auth_client.get("/discovery")
        assert resp.status_code == 200

    def test_create_discovery_job(self, auth_client):
        resp = auth_client.post("/discovery/create", data={
            "name": "test-scan", "job_type": "ssh",
            "target": "10.0.0.1", "config_json": '{"username":"root"}',
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestExternalCMDB:
    def test_ext_cmdb_page(self, auth_client):
        resp = auth_client.get("/ext-cmdb")
        assert resp.status_code == 200

    def test_create_ext_cmdb(self, auth_client):
        resp = auth_client.post("/ext-cmdb/create", data={
            "name": "test-cmdb", "cmdb_type": "generic",
            "api_url": "http://cmdb.example.com/api",
            "auth_json": '{"token":""}', "sync_interval": 60,
        }, follow_redirects=False)
        assert resp.status_code == 303
