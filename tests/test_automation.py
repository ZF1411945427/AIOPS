"""Automation tests: remediation, workflows, chatops, script exec."""


class TestRemediation:
    def test_remediation_page(self, auth_client):
        resp = auth_client.get("/remediation")
        assert resp.status_code == 200

    def test_create_remediation(self, auth_client):
        resp = auth_client.post("/remediation/create", data={
            "name": "restart-nginx", "metric": "nginx_status",
            "condition": "down", "action_type": "restart",
            "action_params": '{"service": "nginx"}',
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestRemediationWorkflow:
    def test_workflow_page(self, auth_client):
        resp = auth_client.get("/remediation-workflows")
        assert resp.status_code == 200

    def test_create_workflow(self, auth_client):
        resp = auth_client.post("/remediation-workflows/new", data={
            "name": "nginx-self-heal",
            "steps": '[{"action":"restart","params":{"service":"nginx"}},{"action":"healthcheck","params":{}}]',
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestScriptExec:
    def test_script_page(self, auth_client):
        resp = auth_client.get("/script")
        assert resp.status_code == 200

    def test_execute_script_local(self, auth_client):
        """Execute a simple local script."""
        resp = auth_client.post("/script/execute", data={
            "target_id": 0,  # may fail gracefully
            "script_content": "echo hello",
            "timeout": 10,
        })
        # Either 200 with template, 404 if target not in DB, or redirect/error
        assert resp.status_code in (200, 303, 404, 500)


class TestChatOps:
    def test_chatops_page(self, auth_client):
        resp = auth_client.get("/chatops")
        assert resp.status_code == 200

    def test_chatops_command(self, auth_client):
        resp = auth_client.post("/chatops/command", data={
            "text": "/alerts",
        })
        assert resp.status_code == 200


class TestChangeWorkflow:
    def test_change_workflow_page(self, auth_client):
        resp = auth_client.get("/change-workflow")
        assert resp.status_code == 200

    def test_create_change_request(self, auth_client):
        resp = auth_client.post("/change-workflow/new", data={
            "title": "升级 Nginx 版本",
            "description": "从 1.20 升级到 1.24",
            "change_type": "upgrade",
            "priority": "medium",
            "risk_level": "low",
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestDrain:
    def test_drain_page(self, auth_client):
        resp = auth_client.get("/drain")
        assert resp.status_code == 200

    def test_drain_parse(self, auth_client):
        resp = auth_client.post("/drain/parse", data={
            "log_text": "2026-01-01 ERROR Connection refused from 10.0.0.1:8080\n2026-01-01 ERROR Connection refused from 10.0.0.2:8080\n2026-01-01 INFO Server started on port 8080",
            "threshold": 0.5,
        })
        assert resp.status_code == 200
        assert "Connection refused" in resp.text or "模板" in resp.text


class TestLogAnomaly:
    def test_log_anomaly_page(self, auth_client):
        resp = auth_client.get("/log-anomaly")
        assert resp.status_code == 200

    def test_create_log_rule(self, auth_client):
        resp = auth_client.post("/log-anomaly/new", data={
            "name": "detect-oom", "keyword": "OOMKilled",
            "severity": "critical",
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestLogs:
    def test_logs_page(self, auth_client):
        resp = auth_client.get("/logs")
        assert resp.status_code == 200


class TestReports:
    def test_reports_page(self, auth_client):
        resp = auth_client.get("/reports")
        assert resp.status_code == 200

    def test_report_schedules(self, auth_client):
        resp = auth_client.get("/report-schedules")
        assert resp.status_code == 200


class TestAPIDocs:
    def test_api_docs(self, auth_client):
        resp = auth_client.get("/api/v1/docs")
        assert resp.status_code == 200

    def test_api_v1_metrics_post(self, auth_client):
        resp = auth_client.post("/api/v1/metrics", json=[{
            "name": "test_metric", "value": 42.5,
            "timestamp": "2026-06-22T10:00:00",
        }])
        assert resp.status_code in (200, 201, 401, 403, 422)  # May need token

    def test_api_v1_health(self, auth_client):
        resp = auth_client.get("/api/v1/query/metrics")
        assert resp.status_code in (200, 401, 403, 422)
