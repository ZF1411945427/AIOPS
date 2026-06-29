"""Analysis & intelligence tests: knowledge, RCA, predictions, traces."""


class TestKnowledgeBase:
    def test_knowledge_page(self, auth_client):
        resp = auth_client.get("/knowledge")
        assert resp.status_code == 200

    def test_create_knowledge(self, auth_client):
        resp = auth_client.post("/knowledge/create", data={
            "title": "CPU troubleshooting",
            "symptom": "high load",
            "root_cause": "process spike",
            "solution": "1. top\n2. strace\n3. check logs",
            "tags": "cpu,troubleshooting",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_knowledge_graph(self, auth_client):
        resp = auth_client.get("/knowledge/graph")
        assert resp.status_code == 200


class TestRunbooks:
    def test_runbooks_page(self, auth_client):
        resp = auth_client.get("/runbooks")
        assert resp.status_code == 200

    def test_create_runbook(self, auth_client):
        resp = auth_client.post("/runbooks/new", data={
            "title": "Nginx down handling",
            "category": "web", "severity": "critical",
            "tags": "nginx,web", "symptom": "502 Bad Gateway",
            "diagnosis": "check nginx process and logs",
            "steps": "1. systemctl status nginx\n2. journalctl -u nginx",
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestHotSpot:
    def test_hotspot_page(self, auth_client):
        resp = auth_client.get("/hotspot")
        assert resp.status_code == 200


class TestIDice:
    def test_idice_page(self, auth_client):
        resp = auth_client.get("/idice")
        assert resp.status_code == 200


class TestPCADR:
    def test_pcadr_page(self, auth_client):
        resp = auth_client.get("/pcadr")
        assert resp.status_code == 200


class TestPageRankRCA:
    def test_pagerank_page(self, auth_client):
        resp = auth_client.get("/pagerank-rca")
        assert resp.status_code == 200


class TestLogRCA:
    def test_log_rca_page(self, auth_client):
        resp = auth_client.get("/log-rca")
        assert resp.status_code == 200


class TestPredictions:
    def test_capacity_prediction(self, auth_client):
        resp = auth_client.get("/predictions/capacity")
        assert resp.status_code == 200

    def test_life_prediction(self, auth_client):
        resp = auth_client.get("/predictions-enhanced/life")
        assert resp.status_code == 200

    def test_failure_prediction(self, auth_client):
        resp = auth_client.get("/predictions-enhanced/failure")
        assert resp.status_code == 200

    def test_prediction_models(self, auth_client):
        resp = auth_client.get("/prediction-models")
        assert resp.status_code == 200


class TestMetrics:
    def test_metrics_page(self, auth_client):
        resp = auth_client.get("/metrics")
        assert resp.status_code == 200

    def test_correlation_page(self, auth_client):
        resp = auth_client.get("/correlation")
        assert resp.status_code == 200

    def test_dtw_page(self, auth_client):
        resp = auth_client.get("/dtw")
        assert resp.status_code == 200

    def test_granger_page(self, auth_client):
        resp = auth_client.get("/granger")
        assert resp.status_code == 200

    def test_trend_prediction(self, auth_client):
        resp = auth_client.get("/trend-prediction")
        assert resp.status_code == 200


class TestTraces:
    def test_traces_page(self, auth_client):
        resp = auth_client.get("/traces")
        assert resp.status_code == 200

    def test_ingest_span(self, auth_client):
        resp = auth_client.post("/traces/ingest", data={
            "trace_id": "test-trace-001", "span_id": "span-001",
            "service_name": "api-gateway", "operation_name": "GET /users",
            "duration_ms": 150, "status": "OK",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True

    def test_trace_detail(self, auth_client):
        auth_client.post("/traces/ingest", data={
            "trace_id": "trace-detail-001", "span_id": "s1",
            "service_name": "svc-a", "operation_name": "op1",
            "duration_ms": 100, "status": "OK",
        })
        resp = auth_client.get("/traces/detail/trace-detail-001")
        assert resp.status_code == 200
        assert "svc-a" in resp.text

    def test_trace_rca_page(self, auth_client):
        resp = auth_client.get("/trace-rca")
        assert resp.status_code == 200


class TestTopology:
    def test_topology_page(self, auth_client):
        resp = auth_client.get("/topology")
        assert resp.status_code == 200

    def test_topology_path(self, auth_client):
        resp = auth_client.get("/topology/path")
        assert resp.status_code == 200

    def test_topo_graph(self, auth_client):
        resp = auth_client.get("/topo-graph")
        assert resp.status_code == 200

    def test_trace_view(self, auth_client):
        resp = auth_client.get("/trace-view")
        assert resp.status_code == 200


class TestSmartRecommend:
    def test_smart_recommend(self, auth_client):
        resp = auth_client.get("/smart-recommend")
        assert resp.status_code == 200


class TestClusterAnomaly:
    def test_cluster_anomaly_page(self, auth_client):
        resp = auth_client.get("/cluster-anomaly")
        assert resp.status_code == 200

    def test_cluster_anomaly_detect(self, auth_client):
        resp = auth_client.get("/cluster-anomaly/detect")
        assert resp.status_code == 200
