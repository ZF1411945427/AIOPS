"""Container & K8s management tests."""


class TestContainerDashboard:
    def test_container_overview(self, auth_client):
        resp = auth_client.get("/containers")
        assert resp.status_code == 200

    def test_docker_list(self, auth_client):
        resp = auth_client.get("/containers/docker")
        assert resp.status_code == 200

    def test_container_topology(self, auth_client):
        resp = auth_client.get("/containers/topology")
        assert resp.status_code == 200


class TestK8sResources:
    def test_k8s_overview(self, auth_client):
        resp = auth_client.get("/k8s/overview")
        assert resp.status_code == 200

    def test_pod_list(self, auth_client):
        resp = auth_client.get("/containers/pods")
        assert resp.status_code == 200

    def test_deployment_list(self, auth_client):
        resp = auth_client.get("/containers/deployments")
        assert resp.status_code == 200

    def test_k8s_configmaps(self, auth_client):
        resp = auth_client.get("/k8s/configmaps")
        assert resp.status_code == 200

    def test_k8s_secrets(self, auth_client):
        resp = auth_client.get("/k8s/secrets")
        assert resp.status_code == 200

    def test_k8s_services(self, auth_client):
        resp = auth_client.get("/k8s/services")
        assert resp.status_code == 200

    def test_k8s_ingresses(self, auth_client):
        resp = auth_client.get("/k8s/ingresses")
        assert resp.status_code == 200

    def test_k8s_hpas(self, auth_client):
        resp = auth_client.get("/k8s/hpas")
        assert resp.status_code == 200

    def test_k8s_statefulsets(self, auth_client):
        resp = auth_client.get("/k8s/statefulsets")
        assert resp.status_code == 200

    def test_k8s_daemonsets(self, auth_client):
        resp = auth_client.get("/k8s/daemonsets")
        assert resp.status_code == 200

    def test_k8s_pvcs(self, auth_client):
        resp = auth_client.get("/k8s/pvcs")
        assert resp.status_code == 200

    def test_k8s_pvs(self, auth_client):
        resp = auth_client.get("/k8s/pvs")
        assert resp.status_code == 200


class TestDeployCreate:
    def test_deploy_create_page(self, auth_client):
        resp = auth_client.get("/containers/deploy/create")
        assert resp.status_code == 200


class TestK8sMonitor:
    def test_k8s_monitor(self, auth_client):
        resp = auth_client.get("/k8s-monitor")
        assert resp.status_code == 200


class TestClusterEvents:
    def test_events_page(self, auth_client):
        resp = auth_client.get("/events")
        assert resp.status_code == 200

    def test_events_stats(self, auth_client):
        resp = auth_client.get("/events/stats")
        assert resp.status_code == 200


class TestBlueGreen:
    def test_blue_green_page(self, auth_client):
        resp = auth_client.get("/blue-green")
        assert resp.status_code == 200

    def test_create_blue_green(self, auth_client):
        resp = auth_client.post("/blue-green/create", data={
            "name": "test-bg", "namespace": "default",
            "active_label": "blue", "standby_label": "green",
            "active_replicas": 3, "standby_replicas": 1,
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_switch_blue_green(self, auth_client):
        auth_client.post("/blue-green/create", data={
            "name": "bg-switch", "namespace": "default",
            "active_label": "blue", "standby_label": "green",
            "active_replicas": 3, "standby_replicas": 1,
        })
        resp = auth_client.post("/blue-green/switch/1", follow_redirects=False)
        assert resp.status_code == 303
