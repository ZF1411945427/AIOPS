"""组件商店全量 54 个 docker 组件批量真实部署测试 (11.0.1.133, 代理 11.0.1.1:7897)

逐个: 真实部署(带正确 compose/env) → 全面体检 → 记录 → 卸载。
结果实时写 docs/组件商店全量测试_明细.json, 可续跑, 防中断丢数据。

用法: python scripts/store_batch_test.py [组件名...不带则全量]
"""
import sys
import os
import json
import time
import urllib.request
import urllib.parse
import http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
ASSET_ID = 193
HTTP_PROXY = "http://11.0.1.1:7897"
NO_PROXY = "127.0.0.1,localhost,.local,11.0.1.133"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
OUT_JSON = os.path.join(OUT_DIR, "组件商店全量测试_明细.json")
STATE_DB = os.path.join(OUT_DIR, "组件商店全量测试_状态.json")
BASE_DIR = "/data/aiops-components"

# 组件专属 compose 覆盖(补必要环境变量/参数, 否则很多默认起不来)
COMPOSE_OVERRIDES = {
    "mysql": ("mysql:8.0", 3306, {"MYSQL_ROOT_PASSWORD": "root123"}),
    "mariadb": ("mariadb:11", 3306, {"MARIADB_ROOT_PASSWORD": "root123"}),
    "redis": ("redis:7", 6379, None),
    "valkey": ("valkey/valkey:8", 6379, None),
    "nginx": ("nginx:latest", 80, None),
    "rabbitmq": ("rabbitmq:3-management", 5672, {"RABBITMQ_DEFAULT_USER": "admin", "RABBITMQ_DEFAULT_PASS": "admin123"}),
    "kafka": ("bitnami/kafka:latest", 9092, {
        "KAFKA_CFG_NODE_ID": "0",
        "KAFKA_CFG_PROCESS_ROLES": "controller,broker",
        "KAFKA_CFG_LISTENERS": "PLAINTEXT://:9092,CONTROLLER://:9093",
        "KAFKA_CFG_ADVERTISED_LISTENERS": "PLAINTEXT://localhost:9092",
        "KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP": "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
        "KAFKA_CFG_CONTROLLER_QUORUM_VOTERS": "0@localhost:9093",
        "KAFKA_CFG_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE": "true",
    }),
    "mongodb": ("mongo:7", 27017, {"MONGO_INITDB_ROOT_USERNAME": "root", "MONGO_INITDB_ROOT_PASSWORD": "root123"}),
    "postgresql": ("postgres:16", 5432, {"POSTGRES_PASSWORD": "postgres123"}),
    "elasticsearch": ("docker.elastic.co/elasticsearch/elasticsearch:8.12.2", 9200, {
        "discovery.type": "single-node", "xpack.security.enabled": "false",
        "ES_JAVA_OPTS": "-Xms256m -Xmx256m",
    }),
    "clickhouse": ("clickhouse/clickhouse-server:24", 8123, None),
    "memcached": ("memcached:1.6", 11211, None),
    "zookeeper": ("zookeeper:3.9", 2181, {"ZOO_4LW_COMMANDS_WHITELIST": "*"}),
    "etcd": ("bitnami/etcd:3.5", 2379, {"ALLOW_NONE_AUTHENTICATION": "yes"}),
    "prometheus": ("prom/prometheus:v2.50.0", 9090, None),
    "grafana": ("grafana/grafana:10.4.0", 3000, {"GF_SECURITY_ADMIN_PASSWORD": "admin123", "GF_INSTALL_PLUGINS": ""}),
    "influxdb": ("influxdb:2.7", 8086, {"DOCKER_INFLUXDB_INIT_MODE": "setup",
                 "DOCKER_INFLUXDB_INIT_USERNAME": "admin", "DOCKER_INFLUXDB_INIT_PASSWORD": "admin123",
                 "DOCKER_INFLUXDB_INIT_ORG": "aiops", "DOCKER_INFLUXDB_INIT_BUCKET": "aiops"}),
    "minio": ("minio/minio:latest", 9000, {"MINIO_ROOT_USER": "minioadmin", "MINIO_ROOT_PASSWORD": "minioadmin"},
              ["server", "/data"]),
    "nats": ("nats:2.10", 4222, None),
    "consul": ("hashicorp/consul:1.19", 8500, {"CONSUL_BIND_INTERFACE": "eth0"}),
    "loki": ("grafana/loki:3.0", 3100, None),
    "jaeger": ("jaegertracing/all-in-one:1.55", 16686, {"COLLECTOR_OTLP_ENABLED": "true"}),
    "alertmanager": ("prom/alertmanager:v0.27.0", 9093, None),
    "victoriametrics": ("victoriametrics/victoria-metrics:v1.100.0", 8428, None),
    "otel": ("otel/opentelemetry-collector:0.102.0", 4317, None),
    "mosquitto": ("eclipse-mosquitto:2", 1883, None),
    "emqx": ("emqx/emqx:5", 18083, None),
    "traefik": ("traefik:v3.0", 80, None),
    "haproxy": ("haproxy:2.9", 80, None),
    "registry": ("registry:2", 5000, None),
    "activemq": ("rmohr/activemq:5.18.0", 8161, None),
    "cassandra": ("cassandra:4.1", 9042, {"CASSANDRA_SINGLE_NODE": "true"}),
    "neo4j": ("neo4j:5", 7474, {"NEO4J_AUTH": "neo4j/neo4j123"}),
    "nacos": ("nacos/nacos-server:v2.2.3", 8848, {"MODE": "standalone", "NACOS_AUTH_ENABLE": "false"}),
    "rocketmq": ("apache/rocketmq:5.1", 9876, {"JAVA_OPT_EXT": "-Xms256m -Xmx256m"}),
    "keycloak": ("quay.io/keycloak/keycloak:24.0", 8080, {
        "KEYCLOAK_ADMIN": "admin", "KEYCLOAK_ADMIN_PASSWORD": "admin123",
        "KC_DB": "dev-mem", "KC_HEALTH_ENABLED": "true"}),
    "vault": ("hashicorp/vault:1.17", 8200, {"VAULT_DEV_ROOT_TOKEN_ID": "root", "VAULT_DEV_LISTEN_ADDRESS": "0.0.0.0:8200"}),
    "tdengine": ("tdengine/tdengine:3", 6030, None),
    "kibana": ("docker.elastic.co/kibana/kibana:8.12.2", 5601, {"ELASTICSEARCH_HOSTS": "http://localhost:9200"}),
    "logstash": ("docker.elastic.co/logstash/logstash:8.12.2", 9600, {"xpack.monitoring.enabled": "false"}),
    "openvpn": ("kylemanna/openvpn:latest", 1194, None, ["ovpn_genconfig", "-u", "udp://localhost"]),
    "gitlab": ("gitlab/gitlab-ce:16.11.0", 80, {
        "GITLAB_OMNIBUS_CONFIG": "external_url 'http://localhost'"},
        ["/bin/sh", "-c", "gitlab-ctl reconfigure && gitlab-ctl start && tail -f /dev/null"]),
    "hbase": ("harisekhon/hbase:2.5", 16010, None),
    "redis-cluster": ("bitnami/redis-cluster:7.0", 6379, {
        "REDIS_CLUSTER_REPLICAS": "0", "REDIS_NODES": "localhost", "REDIS_CLUSTER_CREATOR": "yes",
        "ALLOW_EMPTY_PASSWORD": "yes", "REDIS_DATABASE": "0"}),
    "mysql-cluster": ("bitnami/mysql:8.0", 3306, {
        "MYSQL_ROOT_PASSWORD": "root123", "MYSQL_REPLICATION_MODE": "primary"}),
    "doris": ("apache/doris:2.1.0", 8030, None),
    "starrocks": ("starrocks/starrocks:3.2", 9030, None),
    "tidb": ("pingcap/tidb:v7.5.0", 4000, None),
    "dameng": ("dameng/dameng:8", 5236, None),
    "kingbase": ("kingbase/kbase:v8", 54321, {"MODE": "chinese"}),
    "opengauss": ("enmotech/opengauss:5.0", 5432, {"GS_PASSWORD": "openGauss@123", "GS_NODENAME": "gaussdb"}),
    "oceanbase": ("oceanbase/oceanbase-ce:4.2.1", 2881, {"OB_CLUSTER_NAME": "test", "OB_ROOT_PASSWORD": "root123"}),
    "apisix": ("apache/apisix:3.9", 9080, None),
    "jenkins": ("jenkins/jenkins:lts", 8080, None),
}


def make_compose(name, image, port, env=None, cmd=None):
    env_block = ""
    if env:
        env_block = "\n".join(f"      - {k}={v}" for k, v in env.items())
    cmd_block = ""
    if cmd:
        cmd_block = "    command: [" + ", ".join(f'"{c}"' for c in cmd) + "]"
    lines = [
        "services:",
        f"  {name}:",
        f"    image: {image}",
        f"    container_name: aiops-{name}",
        f"    ports:",
        f'      - "{port}:{port}"',
    ]
    if env_block:
        lines.append("    environment:")
        lines.append(env_block)
    if cmd_block:
        lines.append(cmd_block)
    lines.append("    restart: unless-stopped")
    lines.append("    mem_limit: 1g")
    lines.append("")
    return "\n".join(lines)


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    form = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/login", data=form,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        op.open(req, timeout=10)
    except Exception as e:
        print("login err", e)
    return op


def api_get(op, path):
    return json.loads(op.open(urllib.request.Request(f"{BASE}{path}"), timeout=30).read().decode(errors="replace"))


def api_post(op, path, body, timeout=600):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(op.open(req, timeout=timeout).read().decode(errors="replace"))


def ssh(asset_obj, cmd, timeout=200):
    from app.services.remediation_service import _ssh_connect
    cli = _ssh_connect(asset_obj, timeout=20)
    try:
        stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        return (out + "\n" + err).strip()
    finally:
        try:
            cli.close()
        except Exception:
            pass


def load_state():
    if os.path.exists(STATE_DB):
        try:
            with open(STATE_DB, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_DB, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    targets = sys.argv[1:]
    op = make_opener()
    catalog = api_get(op, "/component-market/api/catalog")["items"]
    state = load_state()

    # 目标机资产对象(SSH + API 都用)
    from app.database import get_db
    from app.models import Asset as AssetModel
    db = next(get_db())
    aobj = db.query(AssetModel).filter(AssetModel.id == ASSET_ID).first()
    db.close()

    comp_list = catalog
    if targets:
        comp_list = [c for c in catalog if c["name"] in targets]

    print(f"待测组件: {len(comp_list)} 个")
    results = []
    for comp in comp_list:
        name = comp["name"]
        if state.get(name, {}).get("done"):
            print(f"跳过 {name}(已完成)")
            continue
        print("\n" + "=" * 70)
        print(f"测试 [{name}] {comp['display_name']}")
        rec = {"component": name, "display": comp["display_name"], "start": time.strftime("%H:%M:%S"),
               "deploy": None, "health": None, "config": None, "vuln": None, "ai": None, "overall": None}
        try:
            ov = COMPOSE_OVERRIDES.get(name)
            if ov:
                image, port = ov[0], ov[1]
                env = ov[2] if len(ov) > 2 else None
                cmd = ov[3] if len(ov) > 3 else None
            else:
                image = comp.get("docker_image") or name
                port = comp.get("default_port") or 8080
                env, cmd = None, None
            compose = make_compose(name, image, port, env, cmd)
            deploy_path = f"{BASE_DIR}/{name}"
            # 通过组件商店 deploy API 真部署(写代理+写compose+up+落安装记录)
            dr = api_post(op, "/component-market/api/deploy", {
                "component_id": comp["id"], "asset_id": ASSET_ID, "deploy_type": "docker",
                "deploy_path": deploy_path,
                "http_proxy": HTTP_PROXY, "https_proxy": HTTP_PROXY, "no_proxy": NO_PROXY,
                "compose": compose,
            }, timeout=600)
            ok = bool(dr.get("ok"))
            dl = (dr.get("deploy_log") or dr.get("message") or "")
            # 确认容器状态
            time.sleep(5)
            ps = ""
            try:
                ps = ssh(aobj, f"docker ps --filter name=aiops-{name} --format '{{{{.Names}}}} {{{{.Status}}}}' 2>&1 | head -3", timeout=30)
                ok = ok or ("Up" in ps)
            except Exception as e:
                ps = str(e)
            rec["deploy"] = {"ok": ok, "status": ps.strip(), "image": image, "log": dl[-300:]}
            print(f"  部署: {'✅' if ok else '❌'} {ps.strip()[:60]}")
            install_id = ((dr.get("install") or {}).get("id"))
            if ok and install_id:
                time.sleep(2)
                try:
                    fcr = None
                    for _ in range(2):
                        try:
                            fcr = api_post(op, f"/component-market/api/installs/{install_id}/full-check", {}, timeout=600)
                            if fcr and fcr.get("ok"):
                                break
                        except Exception as _e:
                            print(f"  体检调用重试: {_e}")
                            time.sleep(3)
                    res = (fcr or {}).get("result") or {}
                    rec["overall"] = res.get("overall_status")
                    rec["health"] = (res.get("health") or {}).get("health_status")
                    rec["config"] = (res.get("config") or {}).get("config_check_status")
                    vuln = res.get("vuln") or {}
                    rec["vuln"] = {"safe": vuln.get("safe"),
                                   "findings": [f.get("cve") for f in vuln.get("findings", [])]}
                    ai = res.get("ai") or {}
                    rec["ai"] = {"generated": ai.get("ai_generated"), "score": ai.get("health_score")}
                    print(f"  体检: overall={rec['overall']} health={rec['health']} config={rec['config']} "
                          f"vuln_safe={rec['vuln']} ai={rec['ai']}")
                except Exception as e:
                    rec["error"] = f"full-check fail: {e}"
                    print("  体检失败:", e)
            # 卸载(回滚容器释放内存)
            try:
                ssh(aobj, f"cd {deploy_path} && docker compose down >/dev/null 2>&1", timeout=60)
            except Exception as e:
                rec["uninstall_err"] = str(e)
            # 删除本次安装记录(避免 54 条堆积, 测试台账在 JSON 里记录)
            try:
                if install_id:
                    req = urllib.request.Request(f"{BASE}/component-market/api/installs/{install_id}", method="DELETE")
                    op.open(req, timeout=20)
            except Exception:
                pass
        except Exception as e:
            rec["error"] = str(e)
            print("  测试异常:", e)
            ssh(aobj, f"cd {BASE_DIR}/{name} && docker compose down >/dev/null 2>&1", timeout=60)
        state[name] = {"done": True, "result": rec}
        save_state(state)
        # 追加到明细
        results.append(rec)
        dump_all(state)

    print("\n" + "=" * 70)
    print("全部完成, 明细见 docs/组件商店全量测试_明细.json")


def dump_all(state):
    rows = []
    for name, d in state.items():
        r = d.get("result", {})
        if r:
            rows.append(r)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"total": len(rows), "results": rows}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
