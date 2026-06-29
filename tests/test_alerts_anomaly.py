"""Alerts, anomaly detection, incidents, notifications."""


class TestAlerts:
    def test_alerts_page(self, auth_client):
        resp = auth_client.get("/alerts")
        assert resp.status_code == 200

    def test_create_alert_rule_and_check(self, auth_client):
        resp = auth_client.post("/alerts/rules/create", data={
            "name": "cpu-rule", "metric_name": "cpu_usage",
            "condition": ">", "threshold": 90, "severity": "critical",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_alert_list_has_data(self, auth_client):
        auth_client.post("/alerts/check")
        resp = auth_client.get("/alerts")
        assert resp.status_code == 200

    def test_alert_rules_page(self, auth_client):
        resp = auth_client.get("/alerts/rules")
        assert resp.status_code == 200

    def test_create_alert_rule(self, auth_client):
        resp = auth_client.post("/alerts/rules/create", data={
            "name": "cpu-rule", "metric_name": "cpu_usage",
            "condition": ">", "threshold": 90, "severity": "critical",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_alert_console(self, auth_client):
        resp = auth_client.get("/alert-console")
        assert resp.status_code == 200

    def test_storm_suppression(self, auth_client):
        resp = auth_client.get("/alert-storm")
        assert resp.status_code == 200


class TestAnomalyDetection:
    def test_anomaly_page(self, auth_client):
        resp = auth_client.get("/anomaly")
        assert resp.status_code == 200

    def test_create_anomaly_config_sigma(self, auth_client):
        resp = auth_client.post("/anomaly/configs/create", data={
            "name": "3sigma-cpu", "metric_name": "cpu_usage",
            "algorithm": "sigma", "sensitivity": 3.0,
            "window_size": 20, "period": 12,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_anomaly_config_mad(self, auth_client):
        resp = auth_client.post("/anomaly/configs/create", data={
            "name": "mad-cpu", "metric_name": "cpu_usage",
            "algorithm": "mad", "sensitivity": 3.0,
            "window_size": 20, "period": 12,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_anomaly_config_prophet(self, auth_client):
        resp = auth_client.post("/anomaly/configs/create", data={
            "name": "prophet-test", "metric_name": "cpu_usage",
            "algorithm": "prophet", "sensitivity": 3.0,
            "window_size": 20, "period": 12,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_anomaly_config_lstm(self, auth_client):
        resp = auth_client.post("/anomaly/configs/create", data={
            "name": "lstm-test", "metric_name": "cpu_usage",
            "algorithm": "lstm", "sensitivity": 3.0,
            "window_size": 20, "period": 12,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_anomaly_config_transformer(self, auth_client):
        resp = auth_client.post("/anomaly/configs/create", data={
            "name": "transformer-test", "metric_name": "cpu_usage",
            "algorithm": "transformer", "sensitivity": 3.0,
            "window_size": 20, "period": 12,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_toggle_anomaly_config(self, auth_client):
        auth_client.post("/anomaly/configs/create", data={
            "name": "tog-test", "metric_name": "cpu_usage",
            "algorithm": "sigma", "sensitivity": 3.0, "window_size": 20, "period": 12,
        })
        resp = auth_client.post("/anomaly/configs/1/toggle", follow_redirects=False)
        assert resp.status_code == 303

    def test_delete_anomaly_config(self, auth_client):
        auth_client.post("/anomaly/configs/create", data={
            "name": "del-test", "metric_name": "cpu_usage",
            "algorithm": "sigma", "sensitivity": 3.0, "window_size": 20, "period": 12,
        })
        resp = auth_client.post("/anomaly/configs/1/delete", follow_redirects=False)
        assert resp.status_code == 303


class TestIncidents:
    def test_incidents_page(self, auth_client):
        resp = auth_client.get("/incidents")
        assert resp.status_code == 200


class TestNotifications:
    def test_notifications_page(self, auth_client):
        resp = auth_client.get("/notifications")
        assert resp.status_code == 200

    def test_create_notification_channel(self, auth_client):
        resp = auth_client.post("/notifications/channels/create", data={
            "name": "test-email", "type": "email",
            "config_host": "smtp.example.com", "config_recipients": "admin@example.com",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_notification_templates(self, auth_client):
        resp = auth_client.get("/notification-templates")
        assert resp.status_code == 200


class TestSilence:
    def test_silence_page(self, auth_client):
        resp = auth_client.get("/alert-silence")
        assert resp.status_code == 200


class TestWebhooks:
    def test_webhooks_page(self, auth_client):
        resp = auth_client.get("/alert-webhooks")
        assert resp.status_code == 200

    def test_create_webhook(self, auth_client):
        resp = auth_client.post("/alert-webhooks/create", data={
            "name": "test-webhook", "url": "https://hook.example.com/alert",
            "secret": "mysecret",
        }, follow_redirects=False)
        assert resp.status_code == 303