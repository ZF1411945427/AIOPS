"""Integration & external system tests."""


class TestDataSources:
    def test_datasources_page(self, auth_client):
        resp = auth_client.get("/datasources")
        assert resp.status_code == 200

    def test_create_datasource_prometheus(self, auth_client):
        resp = auth_client.post("/datasources/create", data={
            "name": "test-prom", "type": "prometheus",
            "api_url": "http://prometheus.example.com:9090",
            "auth_config": "{}",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_create_datasource_kubernetes(self, auth_client):
        resp = auth_client.post("/datasources/create", data={
            "name": "test-k8s", "type": "kubernetes",
            "api_url": "https://k8s.example.com:6443",
            "auth_config": '{"in_cluster": false}',
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestESIntegration:
    def test_es_integration_page(self, auth_client):
        resp = auth_client.get("/es-integration")
        assert resp.status_code == 200


class TestKafkaPipeline:
    def test_kafka_page(self, auth_client):
        resp = auth_client.get("/kafka")
        assert resp.status_code == 200

    def test_create_kafka_pipeline(self, auth_client):
        resp = auth_client.post("/kafka/create", data={
            "name": "test-kafka", "brokers": "localhost:9092",
            "topic": "test-logs", "group_id": "aiops-test",
            "pipeline_type": "log", "transform": "raw",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_toggle_kafka_pipeline(self, auth_client):
        auth_client.post("/kafka/create", data={
            "name": "kafka-tog", "brokers": "localhost:9092",
            "topic": "test", "group_id": "aiops",
            "pipeline_type": "log", "transform": "raw",
        })
        resp = auth_client.post("/kafka/toggle/1", follow_redirects=False)
        assert resp.status_code == 303

    def test_delete_kafka_pipeline(self, auth_client):
        auth_client.post("/kafka/create", data={
            "name": "kafka-del", "brokers": "localhost:9092",
            "topic": "test", "group_id": "aiops",
            "pipeline_type": "log", "transform": "raw",
        })
        resp = auth_client.post("/kafka/delete/1", follow_redirects=False)
        assert resp.status_code == 303


class TestEventSources:
    def test_event_sources_page(self, auth_client):
        resp = auth_client.get("/event-sources")
        assert resp.status_code == 200

    def test_create_event_source(self, auth_client):
        resp = auth_client.post("/event-sources/create", data={
            "name": "test-zabbix", "source_type": "zabbix",
            "api_url": "http://zabbix.example.com/zabbix",
            "auth_json": '{"user":"Admin","password":"zabbix"}',
            "sync_interval": 60,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_toggle_event_source(self, auth_client):
        auth_client.post("/event-sources/create", data={
            "name": "es-tog", "source_type": "zabbix",
            "api_url": "http://zabbix.example.com",
            "auth_json": "{}", "sync_interval": 60,
        })
        resp = auth_client.post("/event-sources/toggle/1", follow_redirects=False)
        assert resp.status_code == 303


class TestServiceMesh:
    def test_service_mesh_page(self, auth_client):
        resp = auth_client.get("/service-mesh")
        assert resp.status_code == 200

    def test_create_service_mesh(self, auth_client):
        resp = auth_client.post("/service-mesh/create", data={
            "name": "test-istio", "mesh_type": "istio",
            "api_url": "http://localhost:15090",
            "auth_json": "{}",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_toggle_service_mesh(self, auth_client):
        auth_client.post("/service-mesh/create", data={
            "name": "sm-tog", "mesh_type": "istio",
            "api_url": "http://localhost:15090", "auth_json": "{}",
        })
        resp = auth_client.post("/service-mesh/toggle/1", follow_redirects=False)
        assert resp.status_code == 303


class TestNetFlow:
    def test_netflow_page(self, auth_client):
        resp = auth_client.get("/netflow")
        assert resp.status_code == 200

    def test_create_netflow_collector(self, auth_client):
        resp = auth_client.post("/netflow/collectors/create", data={
            "name": "test-sflow", "collector_type": "sflow",
            "listen_host": "0.0.0.0", "listen_port": 6343,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_ingest_flow(self, auth_client):
        resp = auth_client.post("/netflow/ingest", data={
            "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2",
            "src_port": 8080, "dst_port": 443,
            "protocol": "TCP", "bytes_sent": 1024, "bytes_rcvd": 2048,
        })
        assert resp.status_code == 200

    def test_toggle_netflow_collector(self, auth_client):
        auth_client.post("/netflow/collectors/create", data={
            "name": "nf-tog", "collector_type": "sflow",
            "listen_host": "0.0.0.0", "listen_port": 6343,
        })
        resp = auth_client.post("/netflow/collectors/toggle/1", follow_redirects=False)
        assert resp.status_code == 303


class TestExternalCMDB:
    def test_toggle_ext_cmdb(self, auth_client):
        auth_client.post("/ext-cmdb/create", data={
            "name": "cmdb-tog", "cmdb_type": "generic",
            "api_url": "http://cmdb.test/api", "auth_json": "{}", "sync_interval": 60,
        })
        resp = auth_client.post("/ext-cmdb/toggle/1", follow_redirects=False)
        assert resp.status_code == 303


class TestFeatureStore:
    def test_feature_store_page(self, auth_client):
        resp = auth_client.get("/feature-store")
        assert resp.status_code == 200

    def test_add_feature(self, auth_client):
        resp = auth_client.post("/feature-store/add", data={
            "feature_name": "cpu_avg_7d", "entity_type": "asset",
            "entity_id": 1, "feature_value": 65.5,
            "feature_json": '{"unit":"%"}', "source": "test",
        }, follow_redirects=False)
        assert resp.status_code == 303
