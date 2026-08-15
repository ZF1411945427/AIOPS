"""组件应用商店服务 (对标 Bitnami Catalog / Terraform Registry OOTB 组件目录)

能力:
  - 内置组件目录(官方组件: MySQL/Redis/Kafka/Nginx/ES/RabbitMQ/MongoDB/PostgreSQL), 每种支持
    多种部署方式: native(传统 yum/apt/脚本) / docker(compose) / helm(K8s) / ha(高可用)
  - CRUD + 命令行清单
  - 部署编排: 通过 deploy_service(docker/native) 或 helm 引擎执行
  - 配置优化检查: 复用 config_drift_service(基线+漂移+AI推荐)
  - 高可用/健康检查: SSH 探测组件运行状态与版本
  - 漏洞检查: 版本与已知 CVE 库对比(基础版) + AI 综合健康分析(复用 call_llm)
"""
import json
import re
import threading
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models import Asset, ComponentCatalog, ComponentInstall

# 内置官方组件目录种子
_BUILTIN_COMPONENTS = [
    {
        "name": "mysql", "display_name": "MySQL", "category": "database",
        "version": "8.0", "description": "开源关系型数据库", "icon": "🐬",
        "docker_image": "mysql:8.0", "helm_chart": "bitnami/mysql", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 3306, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y mysql-server || (apt-get update && apt-get install -y default-mysql-server)",
        "compose_yaml": "",
        "ha_config": json.dumps({"mode": "replication", "replicas": 1}, ensure_ascii=False),
        "config_keys": "my.cnf", "complexity": "medium", "sort_order": 1,
        "param_schema": [
            {"key": "mysql_root_password", "label": "Root 密码", "type": "password", "default": "root123", "required": True, "placeholder": "MySQL root 密码", "env": "MYSQL_ROOT_PASSWORD"},
            {"key": "mysql_database", "label": "初始化数据库", "type": "text", "default": "appdb", "placeholder": "如需自动建库填写", "env": "MYSQL_DATABASE"},
            {"key": "mysql_user", "label": "普通用户", "type": "text", "default": "app", "placeholder": "业务账号", "env": "MYSQL_USER"},
            {"key": "mysql_password", "label": "普通用户密码", "type": "password", "default": "app123", "placeholder": "业务账号密码", "env": "MYSQL_PASSWORD"},
            {"key": "db_port", "label": "端口", "type": "number", "default": 3306, "required": True, "hint": "宿主机映射端口"},
        ],
    },
    {
        "name": "redis", "display_name": "Redis", "category": "cache",
        "version": "7", "description": "高性能内存缓存/键值库", "icon": "🔴",
        "docker_image": "redis:7", "helm_chart": "bitnami/redis", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 6379, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y redis || (apt-get update && apt-get install -y redis-server)",
        "compose_yaml": "",
        "ha_config": json.dumps({"mode": "sentinel", "replicas": 1}, ensure_ascii=False),
        "config_keys": "redis.conf", "complexity": "simple", "sort_order": 2,
        "param_schema": [
            {"key": "redis_password", "label": "访问密码", "type": "password", "default": "redis123", "placeholder": "留空则无密码", "env": "REDIS_PASSWORD", "hint": "容器 command --requirepass"},
            {"key": "db_port", "label": "端口", "type": "number", "default": 6379, "required": True, "hint": "宿主机映射端口"},
            {"key": "maxmemory", "label": "最大内存", "type": "text", "default": "256mb", "placeholder": "如 256mb / 1gb", "hint": "对应 --maxmemory"},
        ],
    },
    {
        "name": "kafka", "display_name": "Apache Kafka", "category": "message",
        "version": "3.6", "description": "分布式消息/流平台", "icon": "📨",
        "docker_image": "bitnami/kafka:3.6", "helm_chart": "bitnami/kafka", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 9092, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "KAFKA_HOME=/data/kafka; VER=kafka_2.13-3.6.0; URL=https://archive.apache.org/dist/kafka/3.6.0/$VER.tgz; LOGD=$KAFKA_HOME/logs; DATADIR=$KAFKA_HOME/data; CFG=$KAFKA_HOME/config/kraft/server.properties; (command -v java >/dev/null 2>&1 || (command -v yum >/dev/null 2>&1 && (yum install -y java-11-openjdk-headless || dnf install -y java-11-openjdk-headless) || (apt-get update && apt-get install -y openjdk-11-jre-headless))); mkdir -p $KAFKA_HOME $LOGD $DATADIR; if [ ! -f $KAFKA_HOME/bin/kafka-server-start.sh ]; then if [ ! -f /tmp/$VER.tgz ] && [ ! -d $KAFKA_HOME/config ]; then (curl -fsSL -o /tmp/$VER.tgz $URL || wget -q -O /tmp/$VER.tgz $URL) >/dev/null 2>&1 || echo DL_FAIL; fi; if [ -f /tmp/$VER.tgz ] && [ ! -d $KAFKA_HOME/config ]; then tar -xzf /tmp/$VER.tgz -C $KAFKA_HOME --strip-components=1 >/dev/null 2>&1 || echo EXTRACT_FAIL; fi; fi; if ! (ss -ltn 2>/dev/null | grep -q ':9092 '); then grep -q '^log.dirs=/data/kafka/data' $CFG 2>/dev/null || sed -i 's#^log.dirs=.*#log.dirs=/data/kafka/data#' $CFG; CID=$(cat /data/kafka-cluster.id 2>/dev/null | tr -d '\\n'); [ -n \"$CID\" ] || CID=$($KAFKA_HOME/bin/kafka-storage.sh random-uuid 2>/dev/null | tr -d '\\n'); [ -n \"$CID\" ] && echo -n \"$CID\" > /data/kafka-cluster.id; if [ ! -f $DATADIR/meta.properties ]; then $KAFKA_HOME/bin/kafka-storage.sh format -t \"$CID\" -c $CFG >/dev/null 2>&1 || echo FORMAT_FAIL; fi; nohup $KAFKA_HOME/bin/kafka-server-start.sh $CFG >$LOGD/server.log 2>&1 & sleep 22; fi; ss -ltn 2>/dev/null | grep -q ':9092 ' && echo UP || { echo DOWN; tail -40 $LOGD/server.log 2>/dev/null; }",
        "compose_yaml": "",
        "ha_config": json.dumps({"mode": "cluster", "brokers": 3}, ensure_ascii=False),
        "config_keys": "server.properties", "complexity": "complex", "sort_order": 3,
        "param_schema": [
            {"key": "kafka_data_dir", "label": "数据目录", "type": "text", "default": "/data/kafka/data", "placeholder": "Kafka 数据目录", "hint": "对应 log.dirs"},
            {"key": "kafka_replication_factor", "label": "副本因子", "type": "number", "default": 1, "placeholder": "default.replication.factor", "hint": "主题默认副本数"},
            {"key": "kafka_broker_id", "label": "Broker ID", "type": "number", "default": 1, "placeholder": "broker.id", "hint": "唯一 broker 编号"},
            {"key": "db_port", "label": "端口", "type": "number", "default": 9092, "required": True, "hint": "Kafka 监听端口"},
        ],
    },
    {
        "name": "rabbitmq", "display_name": "RabbitMQ", "category": "message",
        "version": "3-management", "description": "消息队列(AMQP)", "icon": "🐇",
        "docker_image": "rabbitmq:3-management", "helm_chart": "bitnami/rabbitmq", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 5672, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y rabbitmq-server || (apt-get update && apt-get install -y rabbitmq-server)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "rabbitmq.conf", "complexity": "medium", "sort_order": 4,
        "param_schema": [
            {"key": "rabbitmq_user", "label": "管理用户", "type": "text", "default": "admin", "hint": "对应 RABBITMQ_DEFAULT_USER"},
            {"key": "rabbitmq_password", "label": "管理密码", "type": "password", "default": "admin123", "hint": "对应 RABBITMQ_DEFAULT_PASS"},
            {"key": "amqp_port", "label": "AMQP 端口", "type": "number", "default": 5672, "required": True, "hint": "消息端口 5672"},
            {"key": "mq_port", "label": "管理端口", "type": "number", "default": 15672, "hint": "Web 管理 15672"},
        ],
    },
    {
        "name": "nginx", "display_name": "Nginx", "category": "web",
        "version": "latest", "description": "高性能 Web/反向代理服务器", "icon": "🌐",
        "docker_image": "nginx:latest", "helm_chart": "bitnami/nginx", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 80, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y nginx || (apt-get update && apt-get install -y nginx)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "keepalived", "replicas": 2}, ensure_ascii=False),
        "config_keys": "nginx.conf", "complexity": "simple", "sort_order": 5,
        "param_schema": [
            {"key": "db_port", "label": "监听端口", "type": "number", "default": 80, "required": True, "hint": "宿主机映射端口"},
            {"key": "server_name", "label": "服务器名", "type": "text", "default": "localhost", "placeholder": "域名/ServerName", "hint": "对应 server_name"},
        ],
    },
    {
        "name": "elasticsearch", "display_name": "Elasticsearch", "category": "database",
        "version": "8.12", "description": "分布式搜索与分析引擎", "icon": "🔎",
        "docker_image": "docker.elastic.co/elasticsearch/elasticsearch:8.12.2", "helm_chart": "elastic/elasticsearch", "helm_repo": "https://helm.elastic.co",
        "default_port": 9200, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y elasticsearch || echo '需官方 repo'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "elasticsearch.yml", "complexity": "complex", "sort_order": 6,
        "param_schema": [
            {"key": "es_jvm_heap", "label": "JVM 堆内存", "type": "text", "default": "512m", "placeholder": "如 512m / 1g", "hint": "对应 ES_JAVA_OPTS -Xms/-Xmx"},
            {"key": "es_discovery", "label": "单机模式", "type": "bool", "default": True, "hint": "单节点 discovery.type=single-node"},
            {"key": "db_port", "label": "HTTP 端口", "type": "number", "default": 9200, "required": True, "hint": "REST 9200"},
        ],
    },
    {
        "name": "mongodb", "display_name": "MongoDB", "category": "database",
        "version": "7", "description": "文档型 NoSQL 数据库", "icon": "🍃",
        "docker_image": "mongo:7", "helm_chart": "bitnami/mongodb", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 27017, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y mongodb-org || (apt-get update && apt-get install -y mongodb)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "replicaset", "members": 3}, ensure_ascii=False),
        "config_keys": "mongod.conf", "complexity": "medium", "sort_order": 7,
        "param_schema": [
            {"key": "mongo_root_user", "label": "Root 用户", "type": "text", "default": "admin", "hint": "对应 MONGO_INITDB_ROOT_USERNAME"},
            {"key": "mongo_root_password", "label": "Root 密码", "type": "password", "default": "admin123", "hint": "对应 MONGO_INITDB_ROOT_PASSWORD"},
            {"key": "mongo_database", "label": "初始化数据库", "type": "text", "default": "appdb", "placeholder": "MONGO_INITDB_DATABASE"},
            {"key": "db_port", "label": "端口", "type": "number", "default": 27017, "required": True, "hint": "宿主机映射端口"},
        ],
    },
    {
        "name": "postgresql", "display_name": "PostgreSQL", "category": "database",
        "version": "16", "description": "开源关系型数据库(对象-关系)", "icon": "🐘",
        "docker_image": "postgres:16", "helm_chart": "bitnami/postgresql", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 5432, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y postgresql-server || (apt-get update && apt-get install -y postgresql)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "replication", "replicas": 1}, ensure_ascii=False),
        "config_keys": "postgresql.conf", "complexity": "medium", "sort_order": 8,
        "param_schema": [
            {"key": "pg_user", "label": "超级用户", "type": "text", "default": "postgres", "hint": "对应 POSTGRES_USER"},
            {"key": "pg_password", "label": "超级用户密码", "type": "password", "default": "postgres123", "hint": "对应 POSTGRES_PASSWORD"},
            {"key": "pg_database", "label": "初始化数据库", "type": "text", "default": "appdb", "hint": "对应 POSTGRES_DB"},
            {"key": "db_port", "label": "端口", "type": "number", "default": 5432, "required": True, "hint": "宿主机映射端口"},
        ],
    },
    {
        "name": "clickhouse", "display_name": "ClickHouse", "category": "database",
        "version": "24", "description": "列式分析数据库(OLAP)", "icon": "🟢",
        "docker_image": "clickhouse/clickhouse-server:24", "helm_chart": "bitnami/clickhouse", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 8123, "deploy_types": ["docker", "helm", "native"],
        "native_script": "curl https://clickhouse.com/ | sh || echo '需官方安装脚本'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "config.xml", "complexity": "complex", "sort_order": 9,
    },
    {
        "name": "tdengine", "display_name": "TDengine", "category": "database",
        "version": "3", "description": "时序数据库(TDengine)", "icon": "⏱️",
        "docker_image": "tdengine/tdengine:3", "helm_chart": "tdengine/tdengine", "helm_repo": "https://tdengine.github.io/helm-charts",
        "default_port": 6030, "deploy_types": ["docker", "helm"],
        "native_script": "echo 'TDengine 企业版需 license, 建议 docker/helm'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "taos.cfg", "complexity": "complex", "sort_order": 10,
    },
    {
        "name": "memcached", "display_name": "Memcached", "category": "cache",
        "version": "1.6", "description": "分布式内存缓存", "icon": "🧠",
        "docker_image": "memcached:1.6", "helm_chart": "bitnami/memcached", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 11211, "deploy_types": ["native", "docker", "helm"],
        "native_script": "yum install -y memcached || (apt-get update && apt-get install -y memcached)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "replicas": 2}, ensure_ascii=False),
        "config_keys": "memcached.conf", "complexity": "simple", "sort_order": 11,
    },
    {
        "name": "nacos", "display_name": "Nacos", "category": "middleware",
        "version": "2.2", "description": "服务发现与配置中心", "icon": "🧭",
        "docker_image": "nacos/nacos-server:v2.2.3", "helm_chart": "nacos/nacos", "helm_repo": "https://nacos.io/helm-charts",
        "default_port": 8848, "deploy_types": ["native", "docker", "helm"],
        "native_script": "echo 'Nacos 需 JDK, 建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "standalone"}, ensure_ascii=False),
        "config_keys": "application.properties", "complexity": "complex", "sort_order": 12,
    },
    {
        "name": "zookeeper", "display_name": "ZooKeeper", "category": "middleware",
        "version": "3.9", "description": "分布式协调服务", "icon": "🦁",
        "docker_image": "zookeeper:3.9", "helm_chart": "bitnami/zookeeper", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 2181, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y zookeeper || echo '需下载解压'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "ensemble", "nodes": 3}, ensure_ascii=False),
        "config_keys": "zoo.cfg", "complexity": "medium", "sort_order": 13,
    },
    {
        "name": "etcd", "display_name": "etcd", "category": "middleware",
        "version": "3.5", "description": "分布式键值存储(K8s 底层)", "icon": "🔑",
        "docker_image": "bitnami/etcd:3.5", "helm_chart": "bitnami/etcd", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 2379, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y etcd || echo '需二进制'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "etcd.conf.yml", "complexity": "complex", "sort_order": 14,
    },
    {
        "name": "rocketmq", "display_name": "RocketMQ", "category": "message",
        "version": "5.1", "description": "分布式消息队列(阿里)", "icon": "🚀",
        "docker_image": "apache/rocketmq:5.1", "helm_chart": "storyofhis/rocketmq", "helm_repo": "https://apache.github.io/rocketmq-helm",
        "default_port": 9876, "deploy_types": ["docker", "helm"],
        "native_script": "echo 'RocketMQ 需 JDK+多组件, 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "brokers": 2}, ensure_ascii=False),
        "config_keys": "broker.conf", "complexity": "complex", "sort_order": 15,
    },
    {
        "name": "prometheus", "display_name": "Prometheus", "category": "observability",
        "version": "2.50", "description": "监控与告警系统", "icon": "📈",
        "docker_image": "prom/prometheus:v2.50.0", "helm_chart": "prometheus-community/prometheus", "helm_repo": "https://prometheus-community.github.io/helm-charts",
        "default_port": 9090, "deploy_types": ["native", "docker", "helm"],
        "native_script": "yum install -y prometheus || echo '需二进制'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "prometheus.yml", "complexity": "complex", "sort_order": 16,
    },
    {
        "name": "grafana", "display_name": "Grafana", "category": "observability",
        "version": "10.4", "description": "可视化监控面板", "icon": "📊",
        "docker_image": "grafana/grafana:10.4.0", "helm_chart": "grafana/grafana", "helm_repo": "https://grafana.github.io/helm-charts",
        "default_port": 3000, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "grafana.ini", "complexity": "medium", "sort_order": 17,
    },
    {
        "name": "influxdb", "display_name": "InfluxDB", "category": "database",
        "version": "2.7", "description": "时序数据库(Influx)", "icon": "🌊",
        "docker_image": "influxdb:2.7", "helm_chart": "influxdata/influxdb2", "helm_repo": "https://helm.influxdata.com",
        "default_port": 8086, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "influxdb.conf", "complexity": "medium", "sort_order": 18,
    },
    {
        "name": "kibana", "display_name": "Kibana", "category": "observability",
        "version": "8.12", "description": "ES 可视化(日志/指标/检索)", "icon": "📉",
        "docker_image": "docker.elastic.co/kibana/kibana:8.12.2", "helm_chart": "elastic/kibana", "helm_repo": "https://helm.elastic.co",
        "default_port": 5601, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "kibana.yml", "complexity": "medium", "sort_order": 19,
    },
    {
        "name": "logstash", "display_name": "Logstash", "category": "observability",
        "version": "8.12", "description": "日志采集与处理管道", "icon": "🧩",
        "docker_image": "docker.elastic.co/logstash/logstash:8.12.2", "helm_chart": "elastic/logstash", "helm_repo": "https://helm.elastic.co",
        "default_port": 5044, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "logstash.yml", "complexity": "medium", "sort_order": 20,
    },
    {
        "name": "openvpn", "display_name": "OpenVPN", "category": "middleware",
        "version": "2.6", "description": "VPN 服务", "icon": "🔐",
        "docker_image": "kylemanna/openvpn:latest", "helm_chart": "", "helm_repo": "",
        "default_port": 1194, "deploy_types": ["docker"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "openvpn.conf", "complexity": "medium", "sort_order": 21,
    },
    {
        "name": "gitlab", "display_name": "GitLab", "category": "platform",
        "version": "16", "description": "代码托管与 CI/CD", "icon": "🦊",
        "docker_image": "gitlab/gitlab-ce:16.11.0", "helm_chart": "gitlab/gitlab", "helm_repo": "https://charts.gitlab.io",
        "default_port": 80, "deploy_types": ["docker", "helm"],
        "native_script": "echo '资源占用高, 建议 docker/helm'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "gitlab.rb", "complexity": "complex", "sort_order": 22,
    },
    {
        "name": "activemq", "display_name": "ActiveMQ", "category": "message",
        "version": "5.18", "description": "消息代理(Java)", "icon": "🐜",
        "docker_image": "rmohr/activemq:5.18.0", "helm_chart": "", "helm_repo": "",
        "default_port": 61616, "deploy_types": ["docker", "native"],
        "native_script": "echo '需 JDK, 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 2}, ensure_ascii=False),
        "config_keys": "activemq.xml", "complexity": "medium", "sort_order": 23,
    },
    {
        "name": "cassandra", "display_name": "Cassandra", "category": "database",
        "version": "4.1", "description": "分布式 NoSQL 宽列存储", "icon": "🗄️",
        "docker_image": "cassandra:4.1", "helm_chart": "bitnami/cassandra", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 9042, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker/helm'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "ring", "nodes": 3}, ensure_ascii=False),
        "config_keys": "cassandra.yaml", "complexity": "complex", "sort_order": 24,
    },
    {
        "name": "hbase", "display_name": "HBase", "category": "database",
        "version": "2.5", "description": "Hadoop 分布式数据库", "icon": "🎓",
        "docker_image": "harisekhon/hbase:2.5", "helm_chart": "", "helm_repo": "",
        "default_port": 16010, "deploy_types": ["docker"],
        "native_script": "echo 'HBase 依赖 Hadoop, 建议容器化部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "hbase-site.xml", "complexity": "complex", "sort_order": 25,
    },
    {
        "name": "neo4j", "display_name": "Neo4j", "category": "database",
        "version": "5", "description": "图数据库", "icon": "🕸️",
        "docker_image": "neo4j:5", "helm_chart": "neo4j/neo4j", "helm_repo": "https://neo4j-contrib.github.io/helm-charts",
        "default_port": 7474, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "neo4j.conf", "complexity": "complex", "sort_order": 26,
    },
    {
        "name": "redis-cluster", "display_name": "Redis Cluster", "category": "cache",
        "version": "7", "description": "Redis 高可用集群(3主3从)", "icon": "🔴",
        "docker_image": "bitnami/redis-cluster:7.0", "helm_chart": "bitnami/redis-cluster", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 6379, "deploy_types": ["docker", "helm", "ha"],
        "native_script": "", "compose_yaml": "",
        "ha_config": json.dumps({"mode": "cluster", "masters": 3, "replicas": 1}, ensure_ascii=False),
        "config_keys": "redis.conf", "complexity": "complex", "sort_order": 27,
    },
    {
        "name": "mysql-cluster", "display_name": "MySQL 高可用", "category": "database",
        "version": "8.0", "description": "MySQL 主从高可用(二进制日志)", "icon": "🐬",
        "docker_image": "bitnami/mysql:8.0", "helm_chart": "bitnami/mysql", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 3306, "deploy_types": ["docker", "helm", "ha"],
        "native_script": "", "compose_yaml": "",
        "ha_config": json.dumps({"mode": "replication", "replicas": 2}, ensure_ascii=False),
        "config_keys": "my.cnf", "complexity": "complex", "sort_order": 28,
    },
    {
        "name": "mosquitto", "display_name": "Mosquitto(MQTT)", "category": "message",
        "version": "2", "description": "MQTT 物联网消息代理", "icon": "📡",
        "docker_image": "eclipse-mosquitto:2", "helm_chart": "", "helm_repo": "",
        "default_port": 1883, "deploy_types": ["docker"],
        "native_script": "yum install -y mosquitto || (apt-get update && apt-get install -y mosquitto)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "mosquitto.conf", "complexity": "simple", "sort_order": 29,
    },
    {
        "name": "doris", "display_name": "Apache Doris", "category": "database",
        "version": "2.1", "description": "MPP 分析数据库", "icon": "🐬",
        "docker_image": "apache/doris:2.1.0", "helm_chart": "", "helm_repo": "",
        "default_port": 8030, "deploy_types": ["docker"],
        "native_script": "echo '建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "fe.conf", "complexity": "complex", "sort_order": 30,
    },
    {
        "name": "starrocks", "display_name": "StarRocks", "category": "database",
        "version": "3.2", "description": "极速分析型 MPP 数据库", "icon": "⭐",
        "docker_image": "starrocks/starrocks:3.2", "helm_chart": "starrocks/starrocks", "helm_repo": "https://starrocks.github.io/helm-charts",
        "default_port": 8030, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker/helm'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "fe.conf", "complexity": "complex", "sort_order": 31,
    },
    {
        "name": "mariadb", "display_name": "MariaDB", "category": "database",
        "version": "11", "description": "MySQL 兼容开源关系库", "icon": "🍂",
        "docker_image": "mariadb:11", "helm_chart": "bitnami/mariadb", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 3306, "deploy_types": ["native", "docker", "helm"],
        "native_script": "yum install -y mariadb-server || (apt-get update && apt-get install -y mariadb-server)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "replication", "replicas": 1}, ensure_ascii=False),
        "config_keys": "my.cnf", "complexity": "medium", "sort_order": 32,
    },
    {
        "name": "tidb", "display_name": "TiDB", "category": "database",
        "version": "7.5", "description": "MySQL 兼容分布式 HTAP 数据库", "icon": "🅱️",
        "docker_image": "pingcap/tidb:v7.5.0", "helm_chart": "pingcap/tidb", "helm_repo": "https://charts.pingcap.org",
        "default_port": 4000, "deploy_types": ["docker", "helm"],
        "native_script": "echo 'TiDB 建议 docker/helm'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "tikv": 3}, ensure_ascii=False),
        "config_keys": "tidb.toml", "complexity": "complex", "sort_order": 33,
    },
    {
        "name": "dameng", "display_name": "达梦 DM", "category": "database",
        "version": "8", "description": "国产关系型数据库(信创)", "icon": "🇨🇳",
        "docker_image": "dameng/dameng:8", "helm_chart": "", "helm_repo": "",
        "default_port": 5236, "deploy_types": ["native", "docker"],
        "native_script": "echo '达梦需官方安装包/授权, 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "dm.ini", "complexity": "complex", "sort_order": 34,
    },
    {
        "name": "kingbase", "display_name": "人大金仓", "category": "database",
        "version": "V8", "description": "国产关系型数据库(信创, PostgreSQL 系)", "icon": "🇨🇳",
        "docker_image": "kingbase/kbase:v8", "helm_chart": "", "helm_repo": "",
        "default_port": 54321, "deploy_types": ["native", "docker"],
        "native_script": "echo '金仓需官方安装包, 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "standby", "replicas": 1}, ensure_ascii=False),
        "config_keys": "kingbase.conf", "complexity": "complex", "sort_order": 35,
    },
    {
        "name": "opengauss", "display_name": "openGauss", "category": "database",
        "version": "5", "description": "华为开源数据库(信创)", "icon": "🇨🇳",
        "docker_image": "enmotech/opengauss:5.0", "helm_chart": "", "helm_repo": "",
        "default_port": 5432, "deploy_types": ["docker"],
        "native_script": "echo 'openGauss 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "primary_standby", "replicas": 1}, ensure_ascii=False),
        "config_keys": "postgresql.conf", "complexity": "complex", "sort_order": 36,
    },
    {
        "name": "oceanbase", "display_name": "OceanBase", "category": "database",
        "version": "4.2", "description": "国产分布式关系库(信创)", "icon": "🌊",
        "docker_image": "oceanbase/oceanbase-ce:4.2.1", "helm_chart": "", "helm_repo": "",
        "default_port": 2881, "deploy_types": ["docker"],
        "native_script": "echo 'OceanBase 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "zones": 3}, ensure_ascii=False),
        "config_keys": "observer.xml", "complexity": "complex", "sort_order": 37,
    },
    {
        "name": "minio", "display_name": "MinIO", "category": "database",
        "version": "RELEASE", "description": "对象存储(S3 兼容)", "icon": "🗂️",
        "docker_image": "minio/minio:latest", "helm_chart": "minio/minio", "helm_repo": "https://charts.min.io",
        "default_port": 9000, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "distributed", "nodes": 4}, ensure_ascii=False),
        "config_keys": "minio.env", "complexity": "medium", "sort_order": 38,
    },
    {
        "name": "valkey", "display_name": "Valkey", "category": "cache",
        "version": "8", "description": "Redis 替代(开源键值, Linux 基金会)", "icon": "🔑",
        "docker_image": "valkey/valkey:8", "helm_chart": "bitnamilegacy/valkey", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 6379, "deploy_types": ["docker", "helm"],
        "native_script": "yum install -y valkey || (apt-get update && apt-get install -y valkey-server)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "sentinel", "replicas": 1}, ensure_ascii=False),
        "config_keys": "valkey.conf", "complexity": "simple", "sort_order": 39,
    },
    {
        "name": "emqx", "display_name": "EMQX(MQTT)", "category": "message",
        "version": "5", "description": "云原生 MQTT 物联网消息服务器", "icon": "📡",
        "docker_image": "emqx/emqx:5", "helm_chart": "emqx/emqx", "helm_repo": "https://repos.emqx.io/charts",
        "default_port": 1883, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "emqx.conf", "complexity": "medium", "sort_order": 40,
    },
    {
        "name": "nats", "display_name": "NATS", "category": "message",
        "version": "2.10", "description": "高性能云原生消息系统", "icon": "✈️",
        "docker_image": "nats:2.10", "helm_chart": "nats/nats", "helm_repo": "https://nats-io.github.io/k8s/helm/charts",
        "default_port": 4222, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "nats-server.conf", "complexity": "medium", "sort_order": 41,
    },
    {
        "name": "consul", "display_name": "Consul", "category": "middleware",
        "version": "1.19", "description": "服务发现与配置(Networking)", "icon": "🧩",
        "docker_image": "hashicorp/consul:1.19", "helm_chart": "hashicorp/consul", "helm_repo": "https://helm.releases.hashicorp.com",
        "default_port": 8500, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "consul.hcl", "complexity": "complex", "sort_order": 42,
    },
    {
        "name": "loki", "display_name": "Grafana Loki", "category": "observability",
        "version": "3", "description": "日志聚合系统(CNCF)", "icon": "🦉",
        "docker_image": "grafana/loki:3.0", "helm_chart": "grafana/loki", "helm_repo": "https://grafana.github.io/helm-charts",
        "default_port": 3100, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "microservices"}, ensure_ascii=False),
        "config_keys": "loki-config.yaml", "complexity": "complex", "sort_order": 43,
    },
    {
        "name": "jaeger", "display_name": "Jaeger", "category": "observability",
        "version": "1.55", "description": "分布式链路追踪(CNCF)", "icon": "🕵️",
        "docker_image": "jaegertracing/all-in-one:1.55", "helm_chart": "jaegertracing/jaeger", "helm_repo": "https://jaegertracing.github.io/helm-charts",
        "default_port": 16686, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "all-in-one"}, ensure_ascii=False),
        "config_keys": "jaeger-config.yaml", "complexity": "medium", "sort_order": 44,
    },
    {
        "name": "alertmanager", "display_name": "Alertmanager", "category": "observability",
        "version": "0.27", "description": "Prometheus 告警管理", "icon": "🚨",
        "docker_image": "prom/alertmanager:v0.27.0", "helm_chart": "prometheus-community/alertmanager", "helm_repo": "https://prometheus-community.github.io/helm-charts",
        "default_port": 9093, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster"}, ensure_ascii=False),
        "config_keys": "alertmanager.yml", "complexity": "medium", "sort_order": 45,
    },
    {
        "name": "victoriametrics", "display_name": "VictoriaMetrics", "category": "observability",
        "version": "1.100", "description": "高性能时序数据库(Prom 兼容)", "icon": "⚡",
        "docker_image": "victoriametrics/victoria-metrics:v1.100.0", "helm_chart": "victoriametrics/victoria-metrics", "helm_repo": "https://victoriametrics.github.io/helm-charts",
        "default_port": 8428, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster"}, ensure_ascii=False),
        "config_keys": "victoriametrics-scrape.config", "complexity": "medium", "sort_order": 46,
    },
    {
        "name": "otel", "display_name": "OpenTelemetry Collector", "category": "observability",
        "version": "0.102", "description": "可观测数据采集器(CNCF)", "icon": "📡",
        "docker_image": "otel/opentelemetry-collector:0.102.0", "helm_chart": "open-telemetry/opentelemetry-collector", "helm_repo": "https://open-telemetry.github.io/opentelemetry-helm-charts",
        "default_port": 4317, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "agent"}, ensure_ascii=False),
        "config_keys": "otel-collector-config.yaml", "complexity": "medium", "sort_order": 47,
    },
    {
        "name": "keycloak", "display_name": "Keycloak", "category": "middleware",
        "version": "24", "description": "身份认证与授权(OIDC/SAML)", "icon": "🛡️",
        "docker_image": "quay.io/keycloak/keycloak:24.0", "helm_chart": "codecentric/keycloakx", "helm_repo": "https://codecentric.github.io/helm-charts",
        "default_port": 8080, "deploy_types": ["docker", "helm"],
        "native_script": "echo '需 JDK, 建议 docker'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster"}, ensure_ascii=False),
        "config_keys": "kc.conf", "complexity": "complex", "sort_order": 48,
    },
    {
        "name": "apisix", "display_name": "APISIX", "category": "middleware",
        "version": "3.9", "description": "云原生 API 网关(CNCF)", "icon": "🚪",
        "docker_image": "apache/apisix:3.9", "helm_chart": "apache/apisix", "helm_repo": "https://charts.apiseven.com",
        "default_port": 9080, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "config.yaml", "complexity": "complex", "sort_order": 49,
    },
    {
        "name": "traefik", "display_name": "Traefik", "category": "middleware",
        "version": "3", "description": "云原生反向代理/API 网关", "icon": "🐛",
        "docker_image": "traefik:v3.0", "helm_chart": "traefik/traefik", "helm_repo": "https://helm.traefik.io/traefik",
        "default_port": 80, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster"}, ensure_ascii=False),
        "config_keys": "traefik.yml", "complexity": "medium", "sort_order": 50,
    },
    {
        "name": "haproxy", "display_name": "HAProxy", "category": "middleware",
        "version": "2.9", "description": "高性能负载均衡/代理", "icon": "⚖️",
        "docker_image": "haproxy:2.9", "helm_chart": "haproxytech/kubernetes-ingress", "helm_repo": "https://haproxytech.github.io/helm-charts",
        "default_port": 8080, "deploy_types": ["native", "docker", "helm"],
        "native_script": "yum install -y haproxy || (apt-get update && apt-get install -y haproxy)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 2}, ensure_ascii=False),
        "config_keys": "haproxy.cfg", "complexity": "medium", "sort_order": 51,
    },
    {
        "name": "vault", "display_name": "HashiCorp Vault", "category": "middleware",
        "version": "1.17", "description": "机密管理/密钥保护", "icon": "🔐",
        "docker_image": "hashicorp/vault:1.17", "helm_chart": "hashicorp/vault", "helm_repo": "https://helm.releases.hashicorp.com",
        "default_port": 8200, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "vault.hcl", "complexity": "complex", "sort_order": 52,
    },
    {
        "name": "jenkins", "display_name": "Jenkins", "category": "platform",
        "version": "2.450", "description": "CI/CD 持续集成平台", "icon": "🤖",
        "docker_image": "jenkins/jenkins:lts", "helm_chart": "jenkins/jenkins", "helm_repo": "https://charts.jenkins.io",
        "default_port": 8080, "deploy_types": ["docker", "helm"],
        "native_script": "yum install -y jenkins || echo '需官方 repo'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "jenkins.yaml", "complexity": "complex", "sort_order": 53,
    },
    {
        "name": "registry", "display_name": "Docker Registry", "category": "platform",
        "version": "2", "description": "容器镜像仓库(Docker)", "icon": "📦",
        "docker_image": "registry:2", "helm_chart": "twuni/docker-registry", "helm_repo": "https://helm.twun.io",
        "default_port": 5000, "deploy_types": ["docker", "helm"],
        "native_script": "echo '建议 docker 部署'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "single"}, ensure_ascii=False),
        "config_keys": "config.yml", "complexity": "simple", "sort_order": 54,
    },
]


def build_default_compose(name: str, image: str, port: int) -> str:
    """为组件生成默认单节点 docker compose 内容"""
    return f"""version: '3.8'
services:
  {name}:
    image: {image}
    container_name: aiops-{name}
    ports:
      - "{port}:{port}"
    volumes:
      - {name}_data:/data
    restart: unless-stopped
volumes:
  {name}_data:
"""


def _param_value(schema_item: dict, params: dict):
    """取参数最终值: 用户传参优先, 否则默认值。key 不在 params 时回退 default。"""
    key = schema_item.get("key")
    if params and key in params and params.get(key) is not None and params.get(key) != "":
        return params.get(key)
    return schema_item.get("default")


def render_compose(comp: dict, params: dict, port: int = 0, offline_image: str = "") -> str:
    """按组件 param_schema + 用户定制参数渲染 docker compose。

    参数经 schema 的 env 字段映射到容器环境变量; db_port 覆盖宿主机映射端口;
    组件特殊命令(redis --requirepass / es ES_JAVA_OPTS 等)按 name 分支生成。
    offline_image 非空时用其替换镜像(离线私有仓库地址), 否则用组件默认镜像。
    """
    name = comp["name"]
    image = offline_image or (comp.get("docker_image") or "")
    schema = comp.get("param_schema") or []
    p = params or {}
    service_port = int(p.get("db_port") or port or comp.get("default_port") or 0) or 0

    env_lines = []
    for item in schema:
        env_name = item.get("env")
        if not env_name:
            continue
        val = _param_value(item, p)
        if val is None or val == "":
            continue
        if item.get("type") == "bool":
            _v = "true" if val else "false"
        else:
            _v = str(val)
        env_lines.append(f"      {env_name}: {json.dumps(_v, ensure_ascii=False)}")

    # 组件特殊处理: 容器启动命令 / 额外环境变量
    extra_env = []
    command = None
    if name == "redis":
        pw = _param_value({"key": "redis_password", "default": ""}, p) or ""
        args = ["redis-server"]
        if pw:
            args.append(f"--requirepass {pw}")
        mm = _param_value({"key": "maxmemory", "default": ""}, p) or ""
        if mm:
            args.append(f"--maxmemory {mm}")
        command = " ".join(args)
    elif name == "elasticsearch":
        heap = _param_value({"key": "es_jvm_heap", "default": "512m"}, p) or "512m"
        extra_env.append(f"      ES_JAVA_OPTS: {json.dumps('-Xms%s -Xmx%s' % (heap, heap), ensure_ascii=False)}")

    env_block = "\n".join(env_lines + extra_env)

    # 端口列表: 主端口 + 可选附加端口(如 rabbitmq 管理端口)
    port_lines = [f'      - "{service_port}:{service_port}"']
    if name == "rabbitmq":
        mq = _param_value({"key": "mq_port", "default": "15672"}, p) or "15672"
        port_lines.append(f'      - "{int(mq)}:15672"')

    ports_block = "\n".join(port_lines)
    cmd_block = f"\n    command: {json.dumps(command, ensure_ascii=False)}" if command else ""

    return f"""version: '3.8'
services:
  {name}:
    image: {image}
    container_name: aiops-{name}
    ports:
{ports_block}
{env_block}
    volumes:
      - {name}_data:/data
    restart: unless-stopped{cmd_block}
volumes:
  {name}_data:
"""


def _offline_native_block(script: str) -> str:
    """离线二次强制校验: native 安装脚本若引用公网软件源则返回拦截原因, 否则空串放行。"""
    script = script or ""
    low = script.lower()
    for hint in _OFFLINE_PUBLIC_SOURCES:
        if hint in low:
            return f"离线模式禁止 native 安装使用公网软件源 {hint}(请改用本地/内网包源)"
    return ""


_OFFLINE_PUBLIC_SOURCES = [
    "archive.ubuntu.com", "security.ubuntu.com", "download.fedoraproject.org",
    "mirrors.aliyun.com", "repo.huaweicloud.com", "mirrors.tuna.tsinghua.edu.cn",
    "mirrors.cloud.tencent.com", "dl.fedoraproject.org", "mirrors.ustc.edu.cn",
]


def _inject_native_params(script: str, comp: dict, params: dict) -> str:
    """把定制参数注入 native 脚本。
    支持 {{key}} 占位符替换(脚本引用时用); 同时把参数以环境变量前缀注入。
    """
    params = params or {}
    schema = comp.get("param_schema") or []
    out = script or ""
    for item in schema:
        key = item.get("key")
        if not key:
            continue
        val = _param_value(item, params)
        out = out.replace("{{%s}}" % key, str(val) if val is not None else "")
    env_prefix = " ".join(
        f"{item.get('env', item['key'])}={_shell_quote(str(_param_value(item, params)))}"
        for item in schema if item.get("env") and _param_value(item, params) is not None
    )
    if env_prefix:
        out = f"export {env_prefix} && {out}"
    return out


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def seed_builtin_components(db: Session) -> int:
    """启动时播种内置组件目录(upsert: 存在则刷新字段, 不存在则新增)"""
    added = 0
    for item in _BUILTIN_COMPONENTS:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.name == item["name"]).first()
        if not comp:
            comp = ComponentCatalog(name=item["name"])
            db.add(comp)
            added += 1
        comp.display_name = item["display_name"]
        comp.category = item["category"]
        comp.version = item["version"]
        comp.description = item["description"]
        comp.icon = item["icon"]
        comp.docker_image = item["docker_image"]
        comp.helm_chart = item["helm_chart"]
        comp.helm_repo = item["helm_repo"]
        comp.default_port = item["default_port"]
        comp.deploy_types = json.dumps(item["deploy_types"], ensure_ascii=False)
        comp.native_script = item["native_script"]
        comp.compose_yaml = item["compose_yaml"] or build_default_compose(item["name"], item["docker_image"], item["default_port"])
        comp.ha_config = item["ha_config"]
        comp.config_keys = item["config_keys"]
        comp.complexity = item["complexity"]
        comp.sort_order = item["sort_order"]
        comp.enabled = True
        comp.param_schema = json.dumps(item.get("param_schema") or [], ensure_ascii=False)
    db.commit()
    return added


# ───────────── CRUD ─────────────

def list_components(db: Session, category: str = "", keyword: str = "") -> List[dict]:
    q = db.query(ComponentCatalog).filter(ComponentCatalog.enabled == True)  # noqa: E712
    if category:
        q = q.filter(ComponentCatalog.category == category)
    if keyword:
        q = q.filter(ComponentCatalog.name.like(f"%{keyword}%") | ComponentCatalog.display_name.like(f"%{keyword}%"))
    rows = q.order_by(ComponentCatalog.sort_order, ComponentCatalog.id).all()
    return [_comp_to_dict(c) for c in rows]


def get_component(db: Session, component_id: int) -> Optional[dict]:
    c = db.query(ComponentCatalog).filter(ComponentCatalog.id == component_id).first()
    return _comp_to_dict(c) if c else None


def _comp_to_dict(c: ComponentCatalog) -> dict:
    try:
        deploy_types = json.loads(c.deploy_types) if c.deploy_types else []
    except Exception:
        deploy_types = []
    try:
        ha_config = json.loads(c.ha_config) if c.ha_config else {}
    except Exception:
        ha_config = {}
    try:
        param_schema = json.loads(c.param_schema) if c.param_schema else []
    except Exception:
        param_schema = []
    install_count = 0
    return {
        "id": c.id, "name": c.name, "display_name": c.display_name,
        "category": c.category, "version": c.version, "description": c.description,
        "icon": c.icon, "docker_image": c.docker_image, "helm_chart": c.helm_chart,
        "helm_repo": c.helm_repo, "default_port": c.default_port,
        "deploy_types": deploy_types, "native_script": c.native_script,
        "compose_yaml": c.compose_yaml, "ha_config": ha_config,
        "param_schema": param_schema,
        "config_keys": c.config_keys, "complexity": c.complexity,
        "sort_order": c.sort_order, "install_count": install_count,
    }


# ───────────── 部署 ─────────────

def get_deploy_render(comp: dict, deploy_type: str, params: dict, db: Session = None) -> dict:
    """渲染部署配方内容(不执行): 返回 compose/native 脚本/helm 命令, 供前端确认。
    comp 为 get_component 的 dict。db 用于可选离线镜像解析(get_deploy_render 无 db 时跳过离线)。"""
    allowed = comp.get("deploy_types") or []
    if deploy_type not in allowed:
        return {"ok": False, "error": f"组件不支持部署方式 {deploy_type}(支持: {allowed})"}

    host = params.get("host") or ""
    ns = params.get("namespace") or "default"
    release = params.get("release") or f"{comp['name']}-{datetime.now().strftime('%m%d%H%M')}"
    port = comp.get("default_port") or 0
    image = comp.get("docker_image") or ""

    if deploy_type == "docker":
        schema_keys = {item.get("key") for item in (comp.get("param_schema") or [])}
        custom_params = {k: v for k, v in params.items() if k in schema_keys}
        offline_image = ""
        if params.get("use_offline") and db:
            from app.services.offline_repo_service import resolve_offline_image as _roi
            offline_image = _roi(db, image, True)["image"] if image else ""
        if custom_params:
            compose = render_compose(comp, custom_params, port, offline_image=offline_image)
        else:
            compose = comp.get("compose_yaml") or build_default_compose(comp["name"], offline_image or image, port)
        content = f"# {comp.get('display_name')} Docker 部署 (docker compose)\n# 目标机: {host}\n{compose}\n# 命令: docker compose up -d\n"
        meta = {"kind": "docker", "release": release}
    elif deploy_type == "native":
        script = comp.get("native_script") or f"echo '暂未提供 {comp['name']} 原生安装脚本'"
        schema_keys = {item.get("key") for item in (comp.get("param_schema") or [])}
        custom_params = {k: v for k, v in params.items() if k in schema_keys}
        if custom_params:
            script = _inject_native_params(script, comp, custom_params)
        content = f"# {comp.get('display_name')} 传统部署\n# 目标机: {host}\n{script}\n# 启动: systemctl start {comp['name']}\n"
        meta = {"kind": "native"}
    elif deploy_type == "helm":
        content = (f"# {comp.get('display_name')} K8S/Helm 部署\n"
                   f"# Chart: {comp.get('helm_chart')} (repo: {comp.get('helm_repo')})\n"
                   f"# 命名空间: {ns} | Release: {release}\n"
                   f"# 命令: helm repo add bitnami {comp.get('helm_repo')} && "
                   f"helm install {release} {comp.get('helm_chart')} -n {ns} --create-namespace\n")
        meta = {"kind": "helm", "namespace": ns, "release": release}
    else:  # ha
        ha = comp.get("ha_config") or {}
        nodes = ha.get("replicas") or ha.get("brokers") or ha.get("nodes") or ha.get("members") or "1"
        content = (f"# {comp.get('display_name')} 高可用部署\n"
                   f"# 模式: {ha.get('mode', 'cluster')} | 节点/副本: {nodes}\n"
                   f"# 提示: 高可用建议通过 helm/K8s 多副本或 docker 多实例 + 负载均衡实现。\n")
        meta = {"kind": "ha", "mode": ha.get("mode", "cluster")}
    return {"ok": True, "content": content, "meta": meta}


# ───────────── 安装记录 ─────────────

def list_installs(db: Session, asset_id: Optional[int] = None) -> List[dict]:
    q = db.query(ComponentInstall)
    if asset_id:
        q = q.filter(ComponentInstall.asset_id == asset_id)
    rows = q.order_by(ComponentInstall.created_at.desc()).limit(200).all()
    return [_install_to_dict(r, db) for r in rows]


def get_install(db: Session, install_id: int) -> Optional[dict]:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    return _install_to_dict(r, db) if r else None


def _install_to_dict(r: ComponentInstall, db: Session) -> dict:
    asset_name = db.query(Asset.name).filter(Asset.id == r.asset_id).scalar() or f"资产#{r.asset_id}"
    return {
        "id": r.id, "component_id": r.component_id, "component_name": r.component_name,
        "asset_id": r.asset_id, "asset_name": asset_name, "deploy_type": r.deploy_type,
        "name_space": r.name_space, "release_name": r.release_name, "deploy_path": r.deploy_path,
        "port": r.port, "status": r.status, "config_check_status": r.config_check_status,
        "health_status": r.health_status, "config_result": r.config_result,
        "health_result": r.health_result, "vuln_result": r.vuln_result,
        "ai_analysis": r.ai_analysis, "report_json": r.report_json or "",
        "deploy_params": r.deploy_params or "{}",
        "deploy_log": (r.deploy_log or "")[-2000:],
        "deploy_plan_id": r.deploy_plan_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def record_install(db: Session, component_id: int, component_name: str, asset_id: int,
                   deploy_type: str, deploy_path: str = "", release_name: str = "",
                   name_space: str = "", port: int = 0, deploy_params: dict = None) -> dict:
    inst = ComponentInstall(
        component_id=component_id, component_name=component_name, asset_id=asset_id,
        deploy_type=deploy_type, deploy_path=deploy_path, release_name=release_name,
        name_space=name_space, port=port, status="running",
        deploy_params=json.dumps(deploy_params or {}, ensure_ascii=False),
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return _install_to_dict(inst, db)


def update_install_status(db: Session, install_id: int, status: str, log: str = "") -> None:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return
    r.status = status
    if log:
        r.deploy_log = (r.deploy_log or "") + "\n" + log
    r.updated_at = datetime.now()
    db.commit()


def _append_install_event(db: Session, install_id: int, event: dict) -> None:
    """把单个结构化部署事件追加到安装记录 events_json(供历史回放/续 AI 对话)。"""
    try:
        r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
        if not r:
            return
        existing = json.loads(r.events_json) if r.events_json else []
        existing.append(event)
        r.events_json = json.dumps(existing, ensure_ascii=False)
        r.updated_at = datetime.now()
        db.commit()
    except Exception:
        pass


def get_install_events(db: Session, install_id: int) -> list:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r or not r.events_json:
        return []
    try:
        evs = json.loads(r.events_json)
        return evs if isinstance(evs, list) else []
    except Exception:
        return []


def delete_install(db: Session, install_id: int) -> bool:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return False
    db.delete(r)
    db.commit()
    return True


# ───────────── 真实部署(代理注入 + docker compose) ─────────────

def _apply_docker_proxy(asset: Asset, http_proxy: str, https_proxy: str, no_proxy: str) -> str:
    """把代理写入目标机 docker daemon 的 systemd drop-in, 使 docker pull 走代理。
    返回执行日志; 若三个代理都为空则跳过。"""
    logs = []
    http_p = (http_proxy or "").strip()
    https_p = (https_proxy or http_p or "").strip()
    no_proxy_p = (no_proxy or "127.0.0.1,localhost,.local").strip()
    if not http_p and not https_p:
        return ""
    unit = (
        "mkdir -p /etc/systemd/system/docker.service.d && "
        "cat > /etc/systemd/system/docker.service.d/http-proxy.conf <<'AIOPS_PROXY'\n"
        "[Service]\n"
        f"Environment=\"HTTP_PROXY={http_p}\"\n"
        f"Environment=\"HTTPS_PROXY={https_p}\"\n"
        f"Environment=\"NO_PROXY={no_proxy_p}\"\n"
        f"Environment=\"no_proxy={no_proxy_p}\"\n"
        "AIOPS_PROXY\n"
        "systemctl daemon-reload && systemctl restart docker && sleep 3 && systemctl is-active docker"
    )
    ok, out = _exec_ssh(asset, unit)
    logs.append(f"[proxy] 写入 docker 代理 {http_p or https_p} (no_proxy={no_proxy_p}): {out}")
    if not ok:
        logs.append("[proxy] docker 重启后未 active, 请检查代理")
    return "\n".join(logs)


def deploy_docker(asset: Asset, comp: dict, port: int, deploy_path: str,
                  http_proxy: str = "", https_proxy: str = "", no_proxy: str = "",
                  compose: str = "") -> tuple:
    """在目标机真实部署 docker 组件: 写代理 → 写 compose → docker compose up -d。
    可用 compose 传入完整覆盖配置(含必要环境变量/启动参数), 否则用组件默认配方。
    返回 (ok: bool, log: str)。"""
    logs = []
    name = comp["name"]
    image = comp.get("docker_image") or ""
    if http_proxy or https_proxy:
        logs.append(_apply_docker_proxy(asset, http_proxy, https_proxy, no_proxy))
    # 生成 compose(优先显式传入覆盖)
    compose = (compose or comp.get("compose_yaml") or build_default_compose(name, image, port))
    cn = f"aiops-{name}"
    # 组合远程执行命令
    remote = (
        f"mkdir -p '{deploy_path}'; "
        f"cat > '{deploy_path}/docker-compose.yml' <<'AIOPS_COMPOSE'\n{compose}\nAIOPS_COMPOSE\n"
        f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; "
        f"OUT=$(docker compose up -d 2>&1); RC=$?; "
        f"echo \"$OUT\" | tail -20; echo __RC__=$RC"
    )
    ok, out = _exec_ssh(asset, remote, timeout=300)
    logs.append(f"[deploy] 写入 compose 并 docker compose up -d:\n{out}")
    # 判断是否起来
    ok2, ps = _exec_ssh(asset, f"docker ps --filter name={cn} --format '{{{{.Names}}}} {{{{.Status}}}}' 2>&1 | head -5")
    running = "Up" in ps
    if ok and running:
        logs.append(f"[deploy] 容器 {cn} 已启动: {ps}")
        return True, "\n".join(logs) + f"\n[result] {cn} Up"
    logs.append("[deploy] 容器未启动, 部署失败")
    return False, "\n".join(logs) + f"\n[result] 容器状态: {ps}"


def component_to_asset(db: Session, install_id: int) -> dict:
    """把部署成功的组件实例自动登记为一条子资产(挂在目标机下)。

    复用目标机 SSH 连接 + 记住容器名(aiops-<name>)与端口; 去重(同组件同名资产已存在则不重复建)。
    返回: {ok, asset} 或 {ok, already}。
    """
    from app.services.asset_service import create_asset
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    if r.status != "running":
        raise ValueError("仅运行中的组件实例可登记为资产")
    parent = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not parent:
        raise ValueError("目标机资产不存在")

    comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
    name = r.component_name
    # 组件→CI 类型映射
    db_cats = {"mysql", "redis", "mongodb", "postgresql", "elasticsearch", "mariadb", "tidb",
               "clickhouse", "influxdb", "cassandra", "neo4j", "hbase", "tdengine", "dameng",
               "kingbase", "opengauss", "oceanbase", "doris", "starrocks", "memcached", "valkey"}
    ci_type = "database" if name in db_cats else "middleware"
    cname = f"aiops-{name}"

    # 去重: 同组件名且同父(目标机)已有的不重复建
    dup = db.query(Asset).filter(
        Asset.name == name, Asset.parent_id == parent.id,
        Asset.ci_type.in_(("database", "middleware")),
    ).first()
    if dup:
        return {"ok": True, "already": True, "asset_id": dup.id, "asset": _asset_brief(db, dup)}

    # 复用目标机 SSH + 记住容器名与端口
    parent_cfg = {}
    try:
        parent_cfg = json.loads(parent.connection_config) if parent.connection_config else {}
    except Exception:
        pass
    cfg = {
        "ssh_user": parent_cfg.get("ssh_user", "root"),
        "ssh_password": parent_cfg.get("ssh_password", ""),
        "ssh_port": int(parent_cfg.get("ssh_port", 22)),
        "container_name": cname,
        "component": name,
        "deploy_type": r.deploy_type,
        "app_port": r.port,
    }
    attrs = {
        "source": "component-store",
        "component": name,
        "install_id": r.id,
        "deploy_type": r.deploy_type,
        "container": cname,
    }
    data = {
        "name": name,
        "ci_type": ci_type,
        "ip": parent.ip,
        "status": "online",
        "tags": f"component:{name}",
        "parent_id": parent.id,
        "connection_type": parent.connection_type or "ssh",
        "connection_config": json.dumps(cfg, ensure_ascii=False),
        "ci_attributes": json.dumps(attrs, ensure_ascii=False),
    }
    asset = create_asset(db, data)
    return {"ok": True, "asset_id": asset.id, "asset": _asset_brief(db, asset)}


def _asset_brief(db: Session, a) -> dict:
    return {"id": a.id, "name": a.name, "ci_type": a.ci_type, "ip": a.ip,
            "status": a.status, "parent_id": a.parent_id, "connection_type": a.connection_type}


# ───────────── SSH 执行与探测(复用底座) ─────────────

def _exec_ssh(asset: Asset, command: str, timeout: int = 30) -> tuple:
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=15)
    except Exception as e:
        return (False, f"SSH 连接失败: {e}")
    try:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        ssh.close()
        text = (out or err)
        # 若命令含 __RC__=N 标记, 以其为真实退出码判断成功; 否则退回"有输出即 ok"旧逻辑
        import re as _re
        m = _re.search(r"__RC__\s*=\s*(\d+)", text)
        if m:
            ok = (m.group(1) == "0")
        else:
            ok = (out != "" or err == "")
        return (ok, text)
    except Exception as e:
        try:
            ssh.close()
        except Exception:
            pass
        return (False, f"命令执行失败: {e}")


# 简化版 CVE 库(仅作演示/基础检查; 生产应接 Trivy/Clair/Grype)
_MIN_CVE_RULES = [
    {"component": "redis", "max_safe": "7.0.0", "cve": "CVE-2021-32761", "severity": "critical", "desc": "Redis 命令注入(旧版)"},
    {"component": "nginx", "max_safe": "1.20.0", "cve": "CVE-2021-23017", "severity": "high", "desc": "Nginx DNS 解析器堆溢出"},
    {"component": "mysql", "max_safe": "5.7.10", "cve": "CVE-2016-6662", "severity": "critical", "desc": "MySQL 提权(旧版)"},
]


def _version_less(a: str, b: str) -> bool:
    def key(s):
        return [int(x) for x in re.findall(r"\d+", s)]
    return key(a or "") < key(b or "")


def check_vuln(db: Session, install_id: int) -> Optional[dict]:
    """检查组件实例漏洞.

    优先使用 **Trivy 镜像级扫描**(生产级, SBOM + CVE 全网数据库);
    若目标机无 Trivy 或无 SSH, 回退到内置版对比 CVE 库(基础版)。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return None
    component_name = r.component_name

    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    # 该组件对应的 docker 镜像(catalog 里取, 用于 trivy image 扫描)
    image = ""
    try:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
        image = comp.docker_image or "" if comp else ""
    except Exception:
        image = ""

    result = None
    if asset and asset.connection_type == "ssh":
        result = _trivy_scan(asset, image)

    if result is None:
        # 回退: 版对比 CVE 库
        version = _probe_version(db, r)
        findings = []
        for rule in _MIN_CVE_RULES:
            if rule["component"] == component_name:
                if _version_less(version, rule["max_safe"]) if version else True:
                    findings.append({
                        "cve": rule["cve"], "severity": rule["severity"], "desc": rule["desc"],
                        "found_version": version or "unknown",
                    })
        result = {
            "component": component_name, "version": version or "未知",
            "scan_type": "version-based (基础版, 生产建议接 Trivy)",
            "findings": findings, "safe": len(findings) == 0,
            "scanned_at": datetime.now().isoformat(),
        }
    else:
        result["component"] = component_name

    r.vuln_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


def _trivy_scan(asset: Asset, image: str) -> Optional[dict]:
    """在目标机上用 Trivy 扫描镜像漏洞(生产级 SBOM+CVE)。返回 None 表示无法使用 Trivy。"""
    if not image:
        return None
    # 1. 检测目标机是否有 trivy
    ok, out = _exec_ssh(asset, "command -v trivy 2>/dev/null && trivy --version 2>/dev/null | head -1 || echo NO_TRIVY")
    if not ok or "NO_TRIVY" in out or "trivy" not in out.lower():
        return None
    # 2. 用 trivy image 扫描(只输出 JSON 摘要, 限制时间避免卡死)
    cmd = f"trivy image --severity CRITICAL,HIGH,MEDIUM --no-progress --exit-code 0 --timeout 180s -f json {image} 2>/dev/null"
    ok2, raw = _exec_ssh(asset, cmd, timeout=200)
    if not ok2 or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        try:
            # 截取第一个 { 到最后一个 } 
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
        except Exception:
            return None
    # 聚合处理结果
    vulns = data.get("Results", []) if isinstance(data, dict) else []
    total = {"critical": 0, "high": 0, "medium": 0}
    findings = []
    for res in vulns:
        for v in (res.get("Vulnerabilities") or []):
            sev = (v.get("Severity") or "").lower()
            if sev in ("critical", "high", "medium"):
                total[sev] = total.get(sev, 0) + 1
            findings.append({
                "cve": v.get("VulnerabilityID", ""),
                "severity": v.get("Severity", ""),
                "desc": (v.get("Title") or "")[:120],
                "pkg": v.get("PkgName", ""),
                "installed": v.get("InstalledVersion", ""),
                "fixed": v.get("FixedVersion", "") or None,
            })
    target = data.get("ArtifactName", image) if isinstance(data, dict) else image
    safe = total["critical"] == 0 and total["high"] == 0
    return {
        "image": target,
        "scan_type": "trivy-image (生产级 SBOM+CVE)",
        "summary": total,
        "findings": findings[:50],
        "safe": safe,
        "count_critical": total["critical"],
        "count_high": total["high"],
        "scanned_at": datetime.now().isoformat(),
    }


def _probe_version(db: Session, r: ComponentInstall) -> str:
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not asset or asset.connection_type != "ssh":
        return ""
    cmds = {
        "redis": "redis-cli --version 2>/dev/null | head -1",
        "nginx": "nginx -v 2>&1 | head -1",
        "mysql": "mysql --version 2>/dev/null | head -1",
    }
    cmd = cmds.get(r.component_name, f"{r.component_name} --version 2>/dev/null | head -1")
    ok, out = _exec_ssh(asset, cmd)
    return (out or "").strip()[:60]


# ───────────── AI 综合分析 ─────────────

def ai_analyze(db: Session, install_id: int) -> dict:
    """对组件实例做 AI 综合健康分析: 配置/高可用/漏洞 => 健康结论与建议"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    asset_name = asset.name if asset else f"资产#{r.asset_id}"

    config = {}
    try:
        config = json.loads(r.config_result) if r.config_result else {}
    except Exception:
        config = {}
    health = {}
    try:
        health = json.loads(r.health_result) if r.health_result else {}
    except Exception:
        health = {}
    vuln = {}
    try:
        vuln = json.loads(r.vuln_result) if r.vuln_result else {}
    except Exception:
        vuln = {}

    from app.services.agent_service import call_llm
    from app.models import AIProvider
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    if not provider:
        return {
            "ai_generated": False,
            "summary": f"{r.component_name} 实例健康分析(无 AI provider, 基于探测) 状态={r.status} 配置={r.config_check_status} 健康={r.health_status}",
            "severity": "medium", "health_status": r.health_status,
        }

    system = """你是 SRE 组件健康专家。根据组件实例的配置/高可用/漏洞检查结果, 输出综合健康分析。只输出 JSON:
{"summary":"总体结论","health_score":0-100,"issues":[{"item":"...","level":"info|warning|critical","advice":"..."}],
 "recommendations":["建议1","建议2"],"severity":"low|medium|high"}"""
    user = f"""组件: {r.component_name} (资产: {asset_name}, 部署: {r.deploy_type})
运行状态: {r.status}
配置检查: {json.dumps(config, ensure_ascii=False, default=str)[:1200]}
高可用/健康: {json.dumps(health, ensure_ascii=False, default=str)[:1200]}
漏洞检查: {json.dumps(vuln, ensure_ascii=False, default=str)[:1200]}
请输出综合健康分析 JSON。"""
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["health_status"] = r.health_status
    except Exception:
        parsed = {
            "ai_generated": False,
            "summary": f"{r.component_name} 综合分析完成(规则模式) 状态={r.status}",
            "severity": "medium", "health_status": r.health_status,
            "recommendations": [],
        }
    r.ai_analysis = json.dumps(parsed, ensure_ascii=False)
    db.commit()
    return parsed


def get_stats(db: Session) -> dict:
    total = db.query(ComponentCatalog).count()
    by_cat = {}
    for c in db.query(ComponentCatalog).all():
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    installs = db.query(ComponentInstall).count()
    running = db.query(ComponentInstall).filter(ComponentInstall.status == "running").count()
    return {
        "total_components": total,
        "by_category": by_cat,
        "total_installs": installs,
        "running_installs": running,
    }


# ───────────── 配置优化 & 高可用 检查 ─────────────

# 各组件的健康探测命令(SSH)
_HEALTH_CMDS = {
    "redis": "redis-cli ping 2>/dev/null || docker exec aiops-redis redis-cli ping 2>/dev/null",
    "nginx": "nginx -t 2>&1 >/dev/null; curl -s -o /dev/null -w '%{http_code}' http://localhost/ 2>/dev/null",
    "mysql": "mysqladmin ping 2>/dev/null || docker exec aiops-mysql mysqladmin ping 2>/dev/null",
    "kafka": "ss -ltn 2>/dev/null | grep 9092 >/dev/null && echo LISTEN || echo DOWN",
    "rabbitmq": "rabbitmqctl status 2>/dev/null | head -1 || curl -s -o /dev/null -w '%{http_code}' http://localhost:15672/",
    "elasticsearch": "curl -s http://localhost:9200/_cluster/health 2>/dev/null | head -1",
    "mongodb": "mongosh --eval 'db.runCommand({ping:1})' 2>/dev/null | grep -q ok && echo OK || echo DOWN",
    "postgresql": "pg_isready 2>/dev/null || docker exec aiops-postgresql pg_isready 2>/dev/null",
}
_CONFIG_FILES = {
    "redis": "redis.conf", "nginx": "nginx.conf", "mysql": "my.cnf",
    "postgresql": "postgresql.conf", "elasticsearch": "elasticsearch.yml",
    "rabbitmq": "rabbitmq.conf", "mongodb": "mongod.conf",
}

# native 安装后验证: name -> (探测命令, 判定为成功的关键字)
_NATIVE_VERIFY = {
    "redis": ("redis-cli ping 2>/dev/null | grep -q PONG && echo UP || systemctl is-active redis 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "mysql": ("mysqladmin ping 2>/dev/null | grep -q alive && echo UP || systemctl is-active mysqld 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "nginx": ("(nginx -t 2>&1 | grep -q 'syntax is ok') && echo UP || echo DOWN", ["UP"]),
    "rabbitmq": ("rabbitmqctl status 2>/dev/null | grep -q RabbitMQ && echo UP || echo DOWN", ["UP"]),
    "kafka": ("ss -ltn 2>/dev/null | grep -q 9092 && echo UP || echo DOWN", ["UP"]),
    "elasticsearch": ("curl -s http://localhost:9200 2>/dev/null | grep -q cluster_name && echo UP || echo DOWN", ["UP"]),
    "mongodb": ("ss -ltn 2>/dev/null | grep ':27017 ' >/dev/null && echo UP || echo DOWN", ["UP"]),
    "postgresql": ("pg_isready 2>/dev/null | grep -qi accepting && echo UP || systemctl is-active postgresql 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "memcached": ("pidof memcached >/dev/null 2>&1 && echo UP || echo DOWN", ["UP"]),
}


def check_config(db: Session, install_id: int) -> dict:
    """配置优化检查: 复用 config_drift_service(基线+漂移+AI推荐)"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    component_name = r.component_name
    cfg_key = _CONFIG_FILES.get(component_name, f"{component_name}.conf")

    from app.services import config_drift_service as cds
    result = {"component": component_name, "config_key": cfg_key, "checks": [], "ai": None}

    # 1. 基线采集(capture) 若已有基线则检测漂移
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not asset:
        result["error"] = "目标机资产不存在"
        return result
    try:
        # 尝试建立/检测基线
        baseline = cds.capture_baseline(db, r.asset_id, cfg_key, config_name=f"{component_name} 配置", category=component_name)
        result["baseline_version"] = baseline.get("version")
        drift = cds.detect_drift(db, r.asset_id, cfg_key)
        if drift.get("drifted"):
            result["checks"].append({"item": cfg_key, "status": "drift", "detail": drift.get("diff_text")})
            record_id = drift.get("record_id")
            if record_id:
                try:
                    result["ai"] = cds.ai_assess(db, record_id)
                except Exception:
                    pass
        else:
            result["checks"].append({"item": cfg_key, "status": "pass", "detail": "配置与基线一致, 无漂移"})
    except Exception as e:
        result["checks"].append({"item": cfg_key, "status": "error", "detail": f"配置检查失败: {e}"})

    if result["checks"]:
        sts = [c["status"] for c in result["checks"]]
        if all(s == "pass" for s in sts):
            cfg_status = "pass"
        elif any(s == "error" for s in sts):
            cfg_status = "error"
        elif any(s in ("drift", "warn") for s in sts):
            cfg_status = "drift"
        else:
            cfg_status = "drift"
    else:
        cfg_status = "pending"
    r.config_check_status = cfg_status
    r.config_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


def check_health(db: Session, install_id: int) -> dict:
    """高可用/健康检查: SSH 探测组件运行状态 + 版本"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    results = []
    healthy = True
    deploy_type = r.deploy_type or ""
    if asset and asset.connection_type == "ssh":
        if deploy_type == "docker":
            # docker 部署: 直接探测容器运行状态(权威), 再叠加组件专属命令
            cn = f"aiops-{r.component_name}"
            cok, cout = _exec_ssh(asset, f"docker ps --filter name={cn} --filter status=running --format '{{{{.Names}}}}' | grep -q '{cn}' && echo OK || echo DOWN")
            c_up = "ok" in cout.lower()
            results.append({"check": "容器运行状态", "command": f"docker ps --filter name={cn}", "output": (cout or "")[:150], "healthy": c_up})
            spec_cmd = _HEALTH_CMDS.get(r.component_name)
            if spec_cmd:
                sok, sout = _exec_ssh(asset, spec_cmd)
                s_up = any(k in sout.lower() for k in ("ok", "pong", "alive", "listen", "ready", "200", "green", "yellow", "running", "up"))
                results.append({"check": "组件探测", "command": spec_cmd, "output": (sout or "")[:150], "healthy": s_up})
                healthy = c_up and s_up
            else:
                healthy = c_up
        else:
            cmd = _HEALTH_CMDS.get(r.component_name, f"systemctl is-active {r.component_name} 2>/dev/null || echo DOWN")
            ok, out = _exec_ssh(asset, cmd)
            up = "ok" in out.lower() or "pong" in out.lower() or "alive" in out.lower() or "listen" in out.lower() or "ready" in out.lower() or "200" in out or "green" in out.lower() or "yellow" in out.lower()
            healthy = ok and up
            results.append({"check": "组件运行状态", "command": cmd, "output": (out or "")[:200], "healthy": healthy})
    else:
        results.append({"check": "目标机连通", "healthy": False, "output": "资产非 SSH 或不存在"})
        healthy = False
    # 高可用模式检查
    ha = {}
    try:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
        ha = json.loads(comp.ha_config) if comp and comp.ha_config else {}
    except Exception:
        pass
    status = "healthy" if healthy else "unhealthy"
    result = {
        "component": r.component_name, "deploy_type": r.deploy_type,
        "ha_mode": ha.get("mode", "single"), "health_status": status,
        "checks": results, "checked_at": datetime.now().isoformat(),
    }
    r.health_status = status
    r.health_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


def full_health_check(db: Session, install_id: int) -> dict:
    """四合一体检闭环: 一键同时执行 健康→配置→漏洞→AI综合分析, 返回整合报告。
    对应组件商店「一句话/一键全面体检」。"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    component_name = r.component_name
    result = {
        "component": component_name,
        "asset_id": r.asset_id,
        "deploy_type": r.deploy_type,
        "checked_at": datetime.now().isoformat(),
        "health": None, "config": None, "vuln": None, "ai": None,
        "overall_status": "pending",
    }
    # 1. 高可用/健康
    try:
        result["health"] = check_health(db, install_id)
        result["health_status"] = result["health"].get("health_status")
    except Exception as e:
        result["health"] = {"error": str(e)}
    # 2. 配置优化
    try:
        result["config"] = check_config(db, install_id)
        result["config_check_status"] = result["config"]["checks"][0]["status"] if result["config"].get("checks") else "pending"
    except Exception as e:
        result["config"] = {"error": str(e)}
    # 3. 漏洞
    try:
        result["vuln"] = check_vuln(db, install_id)
    except Exception as e:
        result["vuln"] = {"error": str(e)}
    # 4. AI 综合分析
    try:
        result["ai"] = ai_analyze(db, install_id)
    except Exception as e:
        result["ai"] = {"error": str(e), "ai_generated": False}
    # overall 判定
    health_ok = result["health"] and result["health"].get("health_status") == "healthy"
    config_ok = result.get("config_check_status") in ("pass", None)
    vuln_ok = result["vuln"] and result["vuln"].get("safe") is True
    if health_ok and config_ok and vuln_ok:
        result["overall_status"] = "healthy"
    elif health_ok or config_ok is None:
        result["overall_status"] = "degraded"
    else:
        result["overall_status"] = "unhealthy"
    return result


def batch_full_check(db: Session, limit: int = 50) -> dict:
    """批量四合一体检: 对所有 running 组件实例执行 健康+配置+漏洞+AI 分析。
    用于组件商店「一键体检全部实例」/ 定时巡检任务。"""
    installs = db.query(ComponentInstall).filter(
        ComponentInstall.status == "running",
    ).order_by(ComponentInstall.updated_at.desc()).limit(limit).all()

    results = []
    for r in installs:
        try:
            res = full_health_check(db, r.id)
            results.append({
                "install_id": r.id, "component": r.component_name,
                "asset_id": r.asset_id, "overall_status": res.get("overall_status"),
                "health_status": res.get("health_status"),
                "config_check_status": res.get("config_check_status"),
                "vuln_safe": (res.get("vuln") or {}).get("safe"),
                "ai_generated": (res.get("ai") or {}).get("ai_generated", False),
            })
        except Exception as e:
            results.append({"install_id": r.id, "component": r.component_name, "error": str(e)})

    healthy = sum(1 for x in results if x.get("overall_status") == "healthy")
    degraded = sum(1 for x in results if x.get("overall_status") == "degraded")
    unhealthy = sum(1 for x in results if x.get("overall_status") == "unhealthy")
    return {
        "total": len(results),
        "healthy": healthy, "degraded": degraded, "unhealthy": unhealthy,
        "results": results,
        "scanned_at": datetime.now().isoformat(),
    }


def generate_ai_health_report(db: Session, install_id: int) -> dict:
    """为安装记录生成**可读的 AI 全面体检报告**(对标 AI 部署报告版式)。

    运行四合一体检(健康/配置/漏洞/AI)后, 把原始 JSON 组织成结构化、可直接阅读的
    报告字段: title/status/executive_summary/kpi/各维度小节/issues/recommendations/risk_assessment。
    AI provider 可用时用 AI 润色总体结论, 否则基于检查结果规则兜底。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    asset_name = asset.name if asset else f"资产#{r.asset_id}"
    res = full_health_check(db, install_id)
    overall = res.get("overall_status") or "unknown"

    health = res.get("health") or {}
    config = res.get("config") or {}
    vuln = res.get("vuln") or {}
    ai = res.get("ai") or {}

    # KPI 卡片
    health_checks = health.get("checks") or []
    ok_count = sum(1 for c in health_checks if c.get("healthy"))
    bad_count = sum(1 for c in health_checks if not c.get("healthy"))
    vuln_findings = (vuln.get("findings") or [])
    vuln_crit = vuln.get("count_critical") or 0
    vuln_high = vuln.get("count_high") or 0
    config_checks = (config.get("checks") or [])
    config_pass = sum(1 for c in config_checks if str(c.get("status")) in ("pass", "ok", "healthy", "通过"))
    config_bad = len(config_checks) - config_pass
    ai_issues = (ai.get("issues") or [])
    ai_recs = (ai.get("recommendations") or [])

    # 汇总各维度中文描述
    health_desc = []
    for c in health_checks:
        health_desc.append(f"{'✅' if c.get('healthy') else '❌'} {c.get('check') or ''}: {(c.get('output') or '').strip()[:80]}")
    config_desc = []
    for c in config_checks:
        st = c.get("status") or ""
        config_desc.append(f"[{st}] {c.get('name') or c.get('key') or ''} {c.get('recommendation') or ''}".strip())
    vuln_desc = []
    for f in vuln_findings:
        vuln_desc.append(f"[{f.get('severity') or ''}] {f.get('cve') or f.get('desc') or ''} ({f.get('pkg') or ''})")
    if not vuln_findings:
        vuln_desc.append("未发现中高危漏洞" if vuln.get("safe") else "存在中高危漏洞, 详见漏洞明细")

    status_map = {"healthy": "健康", "degraded": "亚健康", "unhealthy": "不健康", "pending": "待评估"}
    ai_summary = (ai.get("summary") or "") if isinstance(ai, dict) else ""
    overall_text = {
        "healthy": "整体健康", "degraded": "部分健康(亚健康)", "unhealthy": "存在风险", "pending": "待评估",
    }.get(overall, overall)

    # 汇总 issues(健康异常 + 漏洞 + AI issues)
    issues = []
    for c in health_checks:
        if not c.get("healthy"):
            issues.append({"severity": "high", "description": f"健康检查未通过: {c.get('check') or ''} - {(c.get('output') or '').strip()[:80]}", "resolution": ""})
    for f in vuln_findings:
        sev = (f.get("severity") or "").lower()
        if sev in ("critical", "high"):
            issues.append({"severity": "high", "description": f"镜像漏洞 {f.get('cve') or f.get('desc') or ''} ({f.get('pkg') or ''})", "resolution": f"升级至 {f.get('fixed') or '最新版'}" if f.get("fixed") else ""})
    for it in ai_issues:
        issues.append({"severity": (it.get("level") or "info"), "description": (it.get("item") or "")[:160], "resolution": (it.get("advice") or "")})

    recommendations = list(ai_recs)
    if not recommendations:
        health_ok = bool(health_checks) and all(c.get("healthy") for c in health_checks)
        if not health_ok:
            recommendations.append("请检查目标机组件进程/容器运行状态并恢复正常")
        if vuln_crit or vuln_high:
            recommendations.append("请优先修复镜像高危/严重漏洞(升级或加固)")
        if config_bad:
            recommendations.append("请按配置优化建议调整组件配置")
        if not recommendations:
            recommendations.append("检查结果正常, 建议定期巡检保持健康")

    report = {
        "type": "ai_health",
        "title": f"{r.component_name} AI 全面体检报告",
        "status": overall,
        "overall_assessment": f"{overall_text}({asset_name} · {r.deploy_type} 部署 · 端口 {r.port or '-'})",
        "executive_summary": (ai_summary or f"{r.component_name} 体检完成, 总体状态 {overall_text}。健康检查 {ok_count}/{len(health_checks) or 1} 项通过, 配置 {config_pass}/{len(config_checks) or 1} 项通过, 漏洞 {len(vuln_findings)} 项。")[:500],
        "kpi": {
            "overall_status": overall,
            "health_passed": ok_count, "health_total": len(health_checks),
            "config_passed": config_pass, "config_total": len(config_checks),
            "vuln_count": len(vuln_findings),
            "vuln_critical": vuln_crit, "vuln_high": vuln_high,
            "ai_issues": len(ai_issues), "ai_recs": len(ai_recs),
            "ai_generated": bool((ai or {}).get("ai_generated")),
            "checked_at": (res.get("checked_at") or "")[:16].replace("T", " "),
        },
        "health_section": {"title": "高可用/健康检查", "status": (health.get("health_status") or "unknown"), "rows": health_desc},
        "config_section": {"title": "配置优化检查", "status": (res.get("config_check_status") or "pending"), "rows": config_desc},
        "vuln_section": {"title": "漏洞检查", "status": ("安全" if vuln.get("safe") else "存在风险"), "rows": vuln_desc, "safe": vuln.get("safe") is True},
        "issues": issues,
        "recommendations": recommendations,
        "risk_assessment": ("存在中高危漏洞或健康异常, 建议尽快处理" if issues else "当前未发现明显风险, 状态良好")[:200],
    }
    return report


# ───────────── 实时流式部署(AI 辅助, 对标 K8s 集群部署 WS) ─────────────

# 部署取消标记容器: {install_id: threading.Event}
_DEployStop = {}


def register_deploy_stop(install_id: int):
    _DEployStop[install_id] = threading.Event()
    return _DEployStop[install_id]


def cancel_deploy(install_id: int) -> bool:
    """请求停止指定 install 的部署(幂等)。返回是否存在该部署流。"""
    ev = _DEployStop.get(install_id)
    if ev:
        ev.set()
        return True
    return False


# 部署决策门控注册表: {install_id: {"id": decision_id, "event": Event, "result": None}}
_DECISION_REG = {}


def register_decision(install_id: int, decision_id: str) -> dict:
    entry = _DECISION_REG.setdefault(install_id, {"id": decision_id, "event": threading.Event(), "result": None})
    entry["id"] = decision_id
    entry["event"] = threading.Event()
    entry["result"] = None
    return entry


def resolve_decision(install_id: int, decision_id: str, choice: str) -> bool:
    """前端回传决策选择: 写入结果并唤醒等待的部署流。返回是否命中。"""
    entry = _DECISION_REG.get(install_id)
    if not entry or entry.get("id") != decision_id:
        return False
    entry["result"] = choice
    entry["event"].set()
    return True


def _ai_decision_options(db, comp_name, asset_name, context, question, deploy_type="docker", system="", opts_hint=2, deploy_path="", port=0) -> list:
    """由 AI 生成部署决策候选方案(默认 2 个, 严格按当前部署方式/系统)。失败/无 provider 时返回规则方案。"""
    provider = _get_deploy_provider(db)
    pm_tip = {"rhel": "dnf/yum", "debian": "apt-get", "alpine": "apk"}.get(system or "", "")
    fallback = [
        {"key": "opt1", "title": "保持默认重试", "detail": "重试当前步骤(clean 后重跑)"},
        {"key": "opt2", "title": "改用降级方案", "detail": "跳过当前步骤, 标记为已处理并继续"},
    ]
    if not provider:
        return fallback
    from app.services.agent_service import call_llm
    _path_hint = (f", 部署路径/数据目录: {deploy_path}" if deploy_path else "") + (f", 端口: {port}" if port else "")
    system_msg = (f"你是资深 SRE。当前正在以【{deploy_type}】方式部署组件 {comp_name}"
                  f"({'目标机系统 ' + system if system else ''}){_path_hint}。请给出 2 个不同的可执行处置方案。\n"
                  f"⚠ 重要: 必须严格围绕【{deploy_type}】方式进行处置, 不要混用其他方式。"
                  f"({deploy_type} 时用 {pm_tip or '系统包管理器'} 安装/管理服务; docker 时才用 docker 命令)。\n"
                  f"⚠ 若已提供部署路径 {deploy_path or '(如 /opt/kafka)'}, 生成的命令必须基于该真实部署路径(用其绝对路径、cd 到该目录、systemd 单元指向它), 禁止臆造不存在的路径/包名。\n"
                  "只输出 JSON: {\"options\":[{\"title\":\"方案名\",\"detail\":\"具体命令/动作\"}, {\"title\":\"...\",\"detail\":\"...\"}]}")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type};"
            f" 部署路径: {deploy_path or '(默认)'}; 端口: {port or '(默认)'};\n"
            f"需要决策的问题: {question}\n当前部署上下文日志:\n{(context or '')[-1200:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system_msg}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content)
        opts = parsed.get("options") or []
        result = []
        for i, o in enumerate(opts[:opts_hint]):
            title = str(o.get("title", "")).strip()
            detail = str(o.get("detail", "")).strip()
            if not title and not detail:
                continue
            result.append({"key": f"opt{i+1}", "title": title or f"方案{i+1}", "detail": detail})
        # 不足 opts_hint 个方案时用通用 fallback 补足, 保证用户始终有 ≥2 个可选
        for j in range(len(result), opts_hint):
            fb = fallback[j] if j < len(fallback) else fallback[-1]
            result.append({"key": f"opt{j+1}", "title": fb["title"], "detail": fb["detail"]})
        return result
    except Exception:
        pass
    return fallback


def _ai_intent_to_command(db, comp_name, intent_text, context="") -> str:
    """把用户的自定义处置意图(可能是中文描述)转成可执行 shell 命令。
    返回命令字符串; 无法转换/无 provider 时原样返回(仍尝试执行)。"""
    text = (intent_text or "").strip()
    if not text:
        return text
    # 看起来已经是命令(含 / 空格 且无中文)则直接用
    if not _contains_cn(text):
        return text
    provider = _get_deploy_provider(db)
    if not provider:
        return text
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE。用户用自然语言描述了一个部署处置意图, 请把它转成**一行可直接在目标机 root shell 执行的命令**(可含 ; 或 &&)。"
              "只输出 JSON: {\"command\":\"转换后的命令\"}")
    user = (f"处置意图: {text}\n部署上下文:\n{(context or '')[:1200]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        cmd = json.loads(content).get("command", "").strip()
        if cmd and not _contains_cn(cmd):
            return cmd
    except Exception:
        pass
    return text


def _contains_cn(s: str) -> bool:
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)


def _ai_generate_plan(db, comp: dict, deploy_type: str, system: str, target: str = "", port=0, deploy_path: str = "") -> dict:
    """按目标机系统类型 + 组件生成可直接执行的部署方案。
    返回: {ai_generated, kind, system, plan(多行命令/步骤文本), title}。
    无 provider/失败时降级为规则生成的方案。"""
    provider = _get_deploy_provider(db)
    name = comp.get("name", "")
    disp = comp.get("display_name", name)
    image = comp.get("docker_image") or ""
    ns = "default"
    release = f"{name}-{datetime.now().strftime('%m%d%H%M')}"
    pm_cmd = {"rhel": "yum install -y", "debian": "apt-get update && apt-get install -y",
              "alpine": "apk add --no-cache", "unknown": "yum install -y"}.get(system, "yum install -y")

    def _fallback():
        if deploy_type == "docker":
            compose = comp.get("compose_yaml") or build_default_compose(name, image, port)
            return {"ai_generated": False, "kind": "docker", "system": system,
                    "title": f"{disp} Docker 部署方案",
                    "plan": f"# 目标机: {target} (系统: {system or 'unknown'})\n# 部署路径: {deploy_path or '(默认)'}\n{compose}\n# 执行: docker compose up -d"}
        if deploy_type == "native":
            script = comp.get("native_script") or f"echo '暂未提供 {name} 原生脚本'"
            return {"ai_generated": False, "kind": "native", "system": system,
                    "title": f"{disp} 传统部署方案",
                    "plan": f"# 目标机: {target} (系统: {system or 'unknown'}, 包管理器: {pm_cmd[:20]})\n# 部署路径/数据目录: {deploy_path or '(默认)'}\n{script}\n# 启动: systemctl start {name}"}
        if deploy_type == "helm":
            return {"ai_generated": False, "kind": "helm", "system": system,
                    "title": f"{disp} K8s/Helm 方案",
                    "plan": (f"helm repo add bitnami {comp.get('helm_repo') or 'https://charts.bitnami.com/bitnami'}\n"
                             f"helm install {release} {comp.get('helm_chart') or name} -n {ns} --create-namespace")}
        return {"ai_generated": False, "kind": "ha", "system": system,
                "title": f"{disp} 高可用方案", "plan": f"# 高可用部署由 K8s/helm 引擎编排\n# Chart: {comp.get('helm_chart')}"}

    if not provider:
        return _fallback()
    from app.services.agent_service import call_llm
    system_msg = ("你是资深 SRE。请为目标机指定发行版 + 指定组件并**结合用户填写的部署路径**生成一份**可直接在终端执行的部署方案**。"
                  "若部署路径非空, 命令中应包含在该路径下创建目录/落数据/写配置(mkdir -p <path>)。"
                  "只输出 JSON: {\"summary\":\"一句话部署说明\",\"steps\":[\"第1条命令\",\"第2条命令\",...]}")
    user = (f"组件: {name}({disp}); 部署方式: {deploy_type}; "
            f"目标机系统: {system or 'unknown'}(据此选 yum/dnf 或 apt-get/apk); 目标机: {target or '?'}; "
            f"镜像: {image or 'N/A'}; 组件默认端口: {port or ''}; "
            f"用户指定的部署路径: {deploy_path or '(未指定, 用默认)'};\n"
            f"请给出与该系统类型匹配的、可直接执行的完整命令序列(含安装/启动/服务检查)。")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system_msg}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content, {})
        steps = parsed.get("steps") or []
        if not steps:
            return _fallback()
        has_pm = any((("yum" in s) or ("apt-get" in s) or ("apk" in s) or ("dnf" in s)) for s in steps)
        if not has_pm:
            # 若系统已知但 AI 没给安装命令, 荣誉补第一步安装
            steps = [f"{pm_cmd} {name}"] + steps
        header = f"# {disp} {deploy_type} 部署方案"
        header += f" (目标机: {target or '?'} / 系统: {system or 'unknown'})"
        plan = header + "\n" + "\n".join(steps)
        return {"ai_generated": True, "kind": deploy_type, "system": system,
                "title": parsed.get("summary") or f"{disp} {deploy_type} 部署方案",
                "plan": plan}
    except Exception:
        return _fallback()


def _get_deploy_provider(db):
    from app.models import AIProvider
    return db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712


def safe_json_parse(content: str, fallback=None):
    """统一的 LLM 返回 JSON 解析: 剥 markdown 代码围栏 + 容错 json.loads。
    三处旧代码手写剥壳, 收敛到此处复用(见 CONTRACT 规范评论)。"""
    if fallback is None:
        fallback = {}
    if not content:
        return fallback
    text = (content or "").strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        # 尝试截取第一个 { 到最后一个 } 的裸 JSON
        try:
            s, e = text.find("{"), text.rfind("}")
            if s >= 0 and e > s:
                return json.loads(text[s:e + 1])
        except Exception:
            pass
    return fallback


def _ai_autonomous_decision(db, comp_name, asset_name, deploy_type, system, question,
                            output="", history=None, risk_level="medium", deploy_path="", port=0) -> dict:
    """AI 自主处置决策(对标 AI 自动部署闭环): 步骤失败时在 fix/retry/skip/rollback 中自选并给修复命令。

    返回: {decision, reason, fix_commands, needs_confirm}
    - needs_confirm=True 当: decision==rollback 或 risk_level==high(需人工兜底确认, 高危操作铁律)
    - 无 provider / AI 异常: 回退 needs_confirm=True 走人工确认。
    """
    history = history or []
    provider = _get_deploy_provider(db)
    fallback = {"decision": "", "reason": "AI 不可用, 需人工确认", "fix_commands": [], "needs_confirm": True}
    if not provider:
        return fallback
    from app.services.agent_service import call_llm
    htxt = "; ".join([f"第{h.get('attempt', 1)}次: {h.get('decision', '')}({h.get('result', '')})" for h in history[-3:]]) or "无"
    sys = ("你是资深 SRE 运维专家, 负责组件部署失败后的自主处置。基于失败输出, 在 fix/retry/skip/rollback 中选择一个并给出修复命令。\n"
           "只输出 JSON: {\"decision\":\"fix|retry|skip|rollback\",\"reason\":\"一句话理由(中文)\",\"fix_commands\":[\"命令1\",\"命令2\"]}\n"
           "- fix: 有明确修复手段且修复成功率高(>70%)时选\n- retry: 偶发/瞬时问题(端口占用、资源竞态)时选\n"
           "- skip: 该异常不影响整体可用时选\n- rollback: 无法修复、风险高或反复失败时选\n"
           "fix_commands 最多 3 条, 必须是可执行 shell 命令, 且必须基于真实部署路径, 禁止臆造路径/包名/密码。")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type}; 系统: {system or 'unknown'}; "
            f"部署路径: {deploy_path or '(默认)'}; 端口: {port or '(默认)'};\n"
            f"需决策问题: {question}\n风险等级(前端标注): {risk_level}\n"
            f"历史处置: {htxt}\n失败输出:\n{(output or '')[-1800:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": sys}, {"role": "user", "content": user}], timeout_override=60)
        if resp.get("error"):
            return fallback
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content)
        decision = str(parsed.get("decision", "")).strip().lower()
        if decision not in ("fix", "retry", "skip", "rollback"):
            return fallback
        fm = parsed.get("fix_commands") or []
        fm = [str(x) for x in (fm if isinstance(fm, list) else [])][:3]
        needs_confirm = (decision == "rollback") or (risk_level == "high")
        return {
            "decision": decision, "reason": str(parsed.get("reason", "")).strip(),
            "fix_commands": fm, "needs_confirm": needs_confirm,
        }
    except Exception:
        return fallback


def _rule_deploy_tip(stage: str, comp_name: str) -> str:
    rules = {
        "preflight": f"{comp_name} 部署前预检完成。建议确认目标机内存/磁盘充足且已具备 Docker 环境。",
        "proxy": "已注入 docker 代理。建议确认代理可达, 否则镜像拉取会超时。",
        "pull": f"正在拉取 {comp_name} 镜像。若失败请检查网络、代理及镜像 tag 是否存在。",
        "deploy": f"{comp_name} 容器启动中。建议观察容器状态是否为 Up。",
        "verify": f"{comp_name} 部署完成校验中。建议执行健康探测确认服务可用。",
        "done": f"{comp_name} 部署成功。建议接着做四合一体检(高可用/配置/漏洞/AI 分析)。",
        "fail": f"{comp_name} 部署失败。建议查看上方错误日志, 定位问题后重试。",
        "helm": f"{comp_name} 采用 K8s/Helm 方式。当前为记录+配方, 需通过 K8s/Helm 引擎执行。",
    }
    return rules.get(stage, f"{comp_name} 部署阶段 {stage} 处理中。")


def _ai_deploy_tip(db, stage: str, comp_name: str, asset_name: str, context: str) -> dict:
    """在部署某阶段后调用 AI 生成实时建议; 无 provider / 解析失败时降级规则提示。"""
    rule = _rule_deploy_tip(stage, comp_name)
    provider = _get_deploy_provider(db)
    if not provider:
        return {"ai_generated": False, "stage": stage, "summary": rule}
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。根据组件部署过程中某个阶段的实时日志/上下文, 输出简洁专业的部署建议。"
              "只输出 JSON: {\"summary\":\"一句话结论(≤30字)\",\"advice\":\"可操作的下一步建议,1-3条用;分隔\",\"risk\":\"low|medium|high\"}")
    user = f"组件: {comp_name}; 目标机: {asset_name}; 阶段: {stage};\n上下文日志:\n{(context or '')[:1500]}"
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["stage"] = stage
        return parsed
    except Exception:
        return {"ai_generated": False, "stage": stage, "summary": rule}


def _ai_deploy_diagnosis(db, comp_name, asset_name, deploy_type, full_log, error_hint="") -> dict:
    """部署失败时用 AI 深度诊断根因 + 给修复步骤(自我察觉)。
    返回: {ai_generated, stage='diagnosis', summary, root_cause, steps[], risk}"""
    provider = _get_deploy_provider(db)
    default = {
        "ai_generated": False, "stage": "diagnosis", "root_cause": "",
        "steps": [], "risk": "medium", "summary": "部署失败, 请检查上方日志",
    }
    if not provider:
        return default
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。一次组件部署失败了, 请根据完整部署日志自我察觉并定位根因。"
              "只输出 JSON: {\"root_cause\":\"一句话根因(≤40字)\",\"steps\":[\"修复步骤1\",\"修复步骤2\",...],\"summary\":\"结论(≤30字)\",\"risk\":\"low|medium|high\"}")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type};\n"
            f"错误线索: {error_hint[:300]}\n完整部署日志:\n{(full_log or '')[-2500:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed.setdefault("stage", "diagnosis")
        parsed["ai_generated"] = True
        if not isinstance(parsed.get("steps"), list):
            parsed["steps"] = []
        return parsed
    except Exception:
        return default


def _ai_final_report(db, comp, asset, install_id, deploy_type, status, log_summary, health=None) -> dict:
    """生成可直接交付的 AI 部署报告(结论/根因/已执行/影响/下一步/风险)。
    返回 report 事件 payload: {ai_generated, title, conclusion, root_cause, executed, impact, next_steps, risks, overview}"""
    provider = _get_deploy_provider(db)
    base = {
        "ai_generated": False, "title": f"{comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}报告",
        "conclusion": f"组件 {comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}",
        "root_cause": "", "executed": "", "impact": "", "next_steps": [], "risks": [],
        "overview": status,
    }
    if not provider:
        return base
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。请基于以下组件部署信息生成一份**可直接交付给客户/团队的正式部署报告**, "
              "语言专业、结论清晰、可行动。只输出 JSON, 字段: "
              "{\"conclusion\":\"总体结论\",\"root_cause\":\"成功则留空, 失败则根因\","
              "\"executed\":\"已执行的部署动作摘要\",\"impact\":\"对业务/系统的影响\","
              "\"next_steps\":[\"后续动作\"],\"risks\":[\"风险项\"]}")
    user = (f"组件: {comp['name']}({comp.get('display_name','')}); 目标机: {asset.name if asset else ''}; "
            f"部署方式: {deploy_type}; 结果: {status}; 安装ID: {install_id};\n"
            f"部署要点摘录:\n{(log_summary or '')[-2000:]}\n"
            f"体检状态: {((health or {}).get('overall_status')) if isinstance(health, dict) else 'N/A'}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["title"] = f"{comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}报告"
        parsed["overview"] = status
        parsed.setdefault("next_steps", [])
        parsed.setdefault("risks", [])
        parsed.setdefault("root_cause", "")
        parsed.setdefault("executed", "")
        parsed.setdefault("impact", "")
        return parsed
    except Exception:
        return base


def generate_install_report(db: Session, install_id: int) -> dict:
    """为组件商店安装记录生成**可直接交付**的完整 AI 部署报告(对标 AI 自动部署页的可交付版报告)。

    读取安装记录 + 组件 catalog + 部署事件日志, 让 AI 产出:
    executive_summary / 架构 / 启停命令 / 部署路径 / 端口 / 访问方式 / 登录信息 /
    环境 / 时间线 / 验证 / 风险 / 建议 / 问题 等字段; AI 不可用时给结构化兜底。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    item = _install_to_dict(r, db)
    comp = get_component(db, r.component_id) or {
        "name": r.component_name, "display_name": r.component_name,
        "default_port": r.port or 0, "docker_image": "", "category": "",
    }
    events = get_install_events(db, install_id) or []
    # 从事件日志抽取: 预检/阶段/日志/决策/验证/报告
    log_lines = []
    preflight_passed = None
    verification_passed = None
    ai_decisions = 0
    health_overall = None
    for ev in events:
        t = ev.get("type")
        if t == "log" or t == "output":
            log_lines.append(ev.get("message") or "")
        elif t == "precheck":
            if preflight_passed is None:
                preflight_passed = True
            if not ev.get("ok"):
                preflight_passed = False
        elif t == "decision" or t == "decide":
            ai_decisions += 1
        elif t == "verify" or (t == "status" and "验证" in str(ev.get("message", ""))):
            _m = str(ev.get("message", ""))
            if "通过" in _m or "UP" in _m or "LISTEN" in _m:
                verification_passed = True
        elif t == "report":
            if ev.get("overall_status"):
                health_overall = ev.get("overall_status")
    if r.health_status:
        health_overall = health_overall or r.health_status

    def count_status(s):
        return sum(1 for ev in events if ev.get("type") == "complete" and ev.get("status") == s)

    succeeded = 1 if r.status == "succeeded" else 0
    failed = 1 if r.status in ("failed", "stopped") else 0

    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    deploy_info = {
        "组件": comp.get("display_name") or comp.get("name"),
        "目标机": (asset.name if asset else item["asset_name"]),
        "IP": (asset.ip if asset else ""),
        "部署方式": r.deploy_type,
        "部署路径": r.deploy_path or "(默认)",
        "端口": r.port or comp.get("default_port") or 0,
        "命名空间": r.name_space or "-",
        "Release": r.release_name or "-",
        "结果": r.status,
    }
    attached = []
    # 从日志推断访问方式 / 启停命令 / 服务端口
    access = []
    start_stop = []
    ports = []
    if asset and getattr(asset, "ip", None):
        _ip = str(asset.ip)
        if r.port:
            access.append(f"{comp.get('name')}: {_ip}:{r.port}")
            ports.append(f"{r.port} (应用端口)")
    if r.deploy_type == "docker":
        start_stop = ["docker compose up -d (启动)", "docker compose down (停止)"]
    elif r.deploy_type == "native":
        start_stop = [f"启动: nohup {r.deploy_path or '/opt'}/bin/kafka-server-start.sh config/kraft/server.properties",
                      "停止: 结束 kafka.Kafka 进程 (pkill -f kafka.Kafka)"]
    elif r.deploy_type == "helm":
        start_stop = [f"helm upgrade --install {r.release_name or comp.get('name')} {comp.get('helm_chart')} -n {r.name_space or 'default'}",
                      "helm uninstall {0} -n {1}".format(r.release_name or comp.get('name'), r.name_space or 'default')]
    deploy_paths = [r.deploy_path or comp.get("name")] if r.deploy_path else [f"/opt/{comp.get('name')}"]
    login_info = [{"user": "root", "via": f"ssh root@{asset.ip if asset and asset.ip else ''}"}] if asset and asset.ip else []

    def _join_logs(limit=2000):
        return "\n".join(log_lines)[-limit:]

    provider = _get_deploy_provider(db)
    title = f"{comp.get('display_name') or comp.get('name')} 部署报告"
    base = {
        "title": title, "status": r.status, "deployed_at": (r.created_at.isoformat() if r.created_at else ""),
        "deploy_count": 1, "deploy_type": r.deploy_type,
        "executive_summary": f"{comp.get('display_name') or comp.get('name')} 于目标机完成部署, 状态: {r.status}。",
        "kpi": {
            "total_steps": 5, "succeeded_steps": succeeded, "failed_steps": failed, "skipped_steps": 0,
            "total_assets": 1, "preflight_passed": preflight_passed, "verification_passed": verification_passed,
            "ai_decisions": ai_decisions,
        },
        "deployment_architecture": "", "start_stop_commands": start_stop,
        "deploy_paths": deploy_paths, "service_ports": ports, "access_methods": access,
        "login_info": login_info, "environment": deploy_info, "timeline": "",
        "verification": "", "risk_assessment": "", "recommendations": [], "issues": [],
        "raw_log": _join_logs(4000),
    }

    def _persist(report: dict) -> dict:
        """把报告写入 DB(report_json 列)持久化, 供下次打开直接读取, 不重复调 AI。"""
        try:
            row = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
            if row:
                row.report_json = json.dumps(report, ensure_ascii=False, default=str)
                row.updated_at = datetime.now()
                db.commit()
        except Exception:
            pass
        return report

    if not provider:
        return _persist(base)
    from app.services.agent_service import call_llm
    system = (
        "你是资深 SRE 部署专家。基于以下**单个组件**的已部署记录, 生成一份**可直接交付给客户/团队**的正式部署报告。"
        "语言专业、结论清晰、可行动。严格输出 JSON, 字段如下(所有字段都必须提供, 数组缺省给空数组, 字符串缺省给空串):\n"
        "{\"executive_summary\":\"执行摘要(2-4句, 含结论)\","
        "\"deployment_architecture\":\"部署架构说明\","
        "\"start_stop_commands\":[\"启停命令\"],"
        "\"deploy_paths\":[\"部署/数据目录\"],"
        "\"service_ports\":[\"服务端口\"],"
        "\"access_methods\":[\"访问方式\"],"
        "\"login_info\":[{\"user\":\"账号\",\"via\":\"登录方式\"}],"
        "\"environment\":{\"键\":\"值\"},"
        "\"timeline\":\"部署时间线概述\","
        "\"verification\":\"验证结论(端口/进程探测)\","
        "\"risk_assessment\":\"风险评估\","
        "\"recommendations\":[\"改进建议\"],"
        "\"issues\":[{\"severity\":\"low|medium|high\",\"description\":\"问题\",\"resolution\":\"处理\",\"status\":\"resolved|pending\"}]}"
    )
    user = (
        f"部署信息: {json.dumps(deploy_info, ensure_ascii=False)}\n"
        f"体检状态: {health_overall or 'N/A'}; 预检通过: {preflight_passed}; 验证通过: {verification_passed}; "
        f"AI决策次数: {ai_decisions};\n"
        f"部署日志摘录:\n{_join_logs(2000)}"
    )
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        merged = dict(base)
        merged.update(parsed)
        merged["kpi"].update({k: base["kpi"].get(k) for k in
                              ("total_steps", "succeeded_steps", "failed_steps", "skipped_steps",
                               "total_assets", "preflight_passed", "verification_passed", "ai_decisions")})
        merged.setdefault("start_stop_commands", start_stop)
        merged.setdefault("deploy_paths", deploy_paths)
        merged.setdefault("service_ports", ports)
        merged.setdefault("access_methods", access)
        merged.setdefault("login_info", login_info)
        merged.setdefault("environment", deploy_info)
        merged.setdefault("recommendations", [])
        merged.setdefault("issues", [])
        merged["title"] = title
        merged["status"] = r.status
        merged["deployed_at"] = base["deployed_at"]
        return _persist(merged)
    except Exception:
        return _persist(base)


def deploy_stream(db, asset, comp: dict, port: int, deploy_path: str,
                  deploy_type: str = "docker", http_proxy: str = "", https_proxy: str = "",
                  no_proxy: str = "", compose: str = "", namespace: str = "default",
                  release: str = "", install_id: int = 0, params: dict = None,
                  use_offline: bool = False):
    """生成器式实时组件部署(对标 K8s 集群部署 WS, 逐步 yield 事件)。

    yield 事件: {type: status/phase/log/ai/complete/error}
    - docker/native: 真实执行, 分阶段逐步推送日志 + 阶段后 AI 建议
    - helm/ha: 虚拟阶段占位 + AI 建议(依赖 K8s/helm 引擎)
    params: 组件级定制参数 {key:value}, 会真实注入 compose/脚本。
    use_offline: 可选用离线私有仓库(有默认 registry 时 docker 镜像改走私有仓库)。
    """
    params = params or {}
    name = comp["name"]
    image = comp.get("docker_image") or ""
    asset_name = asset.name if asset else f"资产#{getattr(asset, 'id', '?')}"
    connbuf = []

    def cancelled():
        ev = _DEployStop.get(install_id)
        return bool(ev and ev.is_set())

    def log(msg, t="log"):
        connbuf.append(msg)
        return {"type": t, "node": asset_name, "message": msg}

    def ai(stage):
        tip = _ai_deploy_tip(db, stage, name, asset_name, "\n".join(connbuf[-8:]))
        return {"type": "ai", **tip}

    def diag(error_hint="", phase=""):
        """失败时用 AI 深度诊断根因 + 修复步骤(自我察觉)。返回 ai 事件。"""
        diag_data = _ai_deploy_diagnosis(db, name, asset_name, deploy_type,
                                         "\n".join(connbuf[-40:]), error_hint=error_hint)
        diag_data["stage"] = "diagnosis"
        if phase:
            diag_data["phase"] = phase
        return {"type": "ai", **diag_data}

    def final_report(status, log_summary, health=None):
        """生成可直接交付的 AI 部署报告(report 事件)。"""
        rep = _ai_final_report(db, comp, asset, install_id, deploy_type, status, log_summary, health)
        return {"type": "report", **rep}

    def ask_decision(question, context=""):
        """AI 决策门控: 生成 2 个 AI 方案 + 用户自定义, yield decide 事件后阻塞等前端选择。
        返回用户选择内容(字符串); 取消/停止时返回空串。
        用法: choice = yield from ask_decision(...)"""
        import uuid
        _dtype = deploy_type
        _dsys = (pc or {}).get("system") or ""
        options = _ai_decision_options(db, name, asset_name, context, question,
                                       deploy_type=_dtype, system=_dsys,
                                       deploy_path=deploy_path, port=port)
        decision_id = str(uuid.uuid4())
        entry = register_decision(install_id, decision_id)
        yield {"type": "decide", "id": decision_id, "install_id": install_id,
               "question": question, "options": options, "free": True,
               "node": asset_name, "stage": "decision"}
        while not entry["event"].is_set():
            if cancelled():
                return ""
            entry["event"].wait(0.5)
        return entry.get("result") or ""

    def exec_choice(choice):
        """执行用户在决策中选择的方案/自定义意图:
        - AI 现成命令直接执行;
        - 用户自定义中文意图 → 先让 AI 转成命令再执行。
        返回 (ok, out)。"""
        raw = (choice or "").strip()
        if not raw:
            return (True, "")
        cmd = _ai_intent_to_command(db, name, raw, "\n".join(connbuf[-12:]))
        yield log(f"按所选方案执行: {cmd[:200]}")
        return _exec_ssh(asset, f"OUT=$({cmd} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC", timeout=300)

    def ai_handle_failure(question, out, retry_cmd=None, risk_level="medium", max_auto=2):
        """AI 自主处置闭环: 步骤失败时让 AI 自选 fix/retry/skip/rollback。
        - 非高危: AI 自动执行(fix 跑修复命令 / retry 重跑 / skip 跳过), 仅回退到 ask_decision 当 AI 不可用
        - 高危(rollback 或 risk_level=high): 暂停走 ask_decision 人工确认(高危操作铁律)
        返回: {decision, out}  (out 为处置后的输出/日志); decision 为 fix/retry/skip/rollback/''(用户中断)
        """
        history = []
        last_out = out
        for attempt in range(1, max_auto + 1):
            _dsys = (pc or {}).get("system") or ""
            dec = _ai_autonomous_decision(
                db, name, asset_name, deploy_type, _dsys, question,
                output=last_out, history=history, risk_level=risk_level,
                deploy_path=deploy_path, port=port)
            if dec.get("needs_confirm") or not dec.get("decision"):
                # 高危/不明确 → 人工确认兜底
                choice = yield from ask_decision(question + ("\n⚠ 高危操作已暂停等待确认" if dec.get("needs_confirm") else ""), last_out)
                if not choice:
                    return {"decision": "", "out": last_out}
                yield log(f"人工确认方案: {choice[:120]}")
                _ok, _o = yield from exec_choice(choice)
                last_out = _o or last_out
                history.append({"attempt": attempt, "decision": "human", "result": "ok" if _ok else "fail"})
                return {"decision": "" if not _ok else "fix", "out": last_out}
            decision = dec["decision"]
            reason = dec.get("reason", "")
            yield {"type": "ai", "ai_generated": True, "stage": "decision",
                   "summary": f"AI 自主处置: {decision}({reason})", "decision": decision, "install_id": install_id}
            yield log(f"🤖 AI 自主决策: {decision} — {reason}")
            if decision == "skip":
                return {"decision": "skip", "out": last_out}
            if decision == "retry" and retry_cmd:
                yield log(f"🤖 AI 选择重试(第{attempt}次)...")
                ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                yield log(out3)
                last_out = out3
                history.append({"attempt": attempt, "decision": "retry", "result": "ok" if ok3 else "fail"})
                if ok3:
                    return {"decision": "retry", "out": out3}
                continue
            if decision == "fix":
                fcs = dec.get("fix_commands") or []
                if fcs:
                    fix_ok = True
                    for fc in fcs:
                        yield log(f"🤖 AI 执行修复: {fc[:160]}")
                        fok, fout = _exec_ssh(asset, f"OUT=$({fc} 2>&1); RC=$?; echo \"$OUT\" | tail -20; echo __RC__=$RC", timeout=300)
                        yield log(fout)
                        if not fok:
                            fix_ok = False
                    last_out = fout if 'fout' in dir() else last_out
                    history.append({"attempt": attempt, "decision": "fix", "result": "ok" if fix_ok else "fail"})
                    if fix_ok and retry_cmd:
                        ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                        yield log(out3)
                        last_out = out3
                        if ok3:
                            return {"decision": "fix", "out": out3}
                    if fix_ok:
                        return {"decision": "fix", "out": last_out}
                    continue
                # 无修复命令 → 落到 retry
                if retry_cmd:
                    yield log("🤖 AI 无具体修复命令, 改为重试")
                    ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                    yield log(out3)
                    last_out = out3
                    history.append({"attempt": attempt, "decision": "retry", "result": "ok" if ok3 else "fail"})
                    if ok3:
                        return {"decision": "retry", "out": out3}
                    continue
            # rollback 或其它 → 人工确认
            choice = yield from ask_decision(question + "\n⚠ 需回滚/无法自动处理, 请选择方案或输入自定义命令", last_out)
            if not choice:
                return {"decision": "", "out": last_out}
            yield log(f"人工确认方案: {choice[:120]}")
            _ok, _o = yield from exec_choice(choice)
            last_out = _o or last_out
            history.append({"attempt": attempt, "decision": "human", "result": "ok" if _ok else "fail"})
            return {"decision": "fix" if _ok else "", "out": last_out}
        # 多次自动仍失败 → 人工确认兜底
        choice = yield from ask_decision(question + "\n⚠ AI 多次自动处置仍未成功, 请人工选择", last_out)
        if not choice:
            return {"decision": "", "out": last_out}
        yield log(f"人工确认方案: {choice[:120]}")
        _ok, _o = yield from exec_choice(choice)
        return {"decision": "fix" if _ok else "", "out": _o or last_out}

    yield {"type": "status", "status": "running", "message": f"开始部署 {comp['display_name']} ({deploy_type})"}

    # ── 预检 ──
    yield {"type": "phase", "step": 0, "title": "阶段0/5 预检环境"}
    yield log(f"目标机: {asset_name} | 组件: {name} | 方式: {deploy_type}")
    if cancelled():
        yield {"type": "ai", **{"ai_generated": False, "stage": "stop", "summary": "部署已取消"}}
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return

    # 逻辑预检(对标 K8s precheck), 逐项推 check 事件给前端预检面板
    pc = precheck_deploy(db, asset, comp, deploy_type=deploy_type, port=port,
                         http_proxy=http_proxy, https_proxy=https_proxy, no_proxy=no_proxy,
                         deploy_path=deploy_path)
    for _c in pc.get("checks", []):
        yield {"type": "precheck", "name": _c.get("name"), "ok": _c.get("ok"), "message": _c.get("message")}
    yield log(f"预检: {'通过' if pc.get('ok') else '存在 ' + str(len(pc.get('issues', []))) + ' 项问题'}")
    yield ai("preflight")
    if not pc.get("ok"):
        yield {"type": "error", "message": "预检未通过: " + "; ".join(pc.get("issues", []) or ["未知问题"])}
        yield {"type": "complete", "status": "failed", "message": f"预检失败: {comp['display_name']}"}
        return

    # ── 阶段1: 代理注入(docker) ──
    if deploy_type == "docker" and (http_proxy or https_proxy):
        if cancelled():
            yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
            return
        yield {"type": "phase", "step": 1, "title": "阶段1/5 注入 Docker 代理"}
        yield log(f"写入代理 {http_proxy or https_proxy} (no_proxy={no_proxy or '默认'})...")
        plog = _apply_docker_proxy(asset, http_proxy, https_proxy, no_proxy)
        if plog:
            yield log(plog)
        yield ai("proxy")
    else:
        yield {"type": "phase", "step": 1, "title": "阶段1/5 网络/代理(跳过或虚拟)"}
        yield log("未配置代理, 跳过 docker daemon 代理注入" if deploy_type == "docker" else f"{deploy_type} 方式忽略代理配置")

    # ── 阶段2: 生成部署方案(基于预检得到的系统类型, 优先 AI 生成) ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 2, "title": "阶段2/5 生成部署方案(AI)"}
    _sys = (pc or {}).get("system") or ""
    plan = _ai_generate_plan(db, comp, deploy_type, _sys, target=asset.ip or "", port=port, deploy_path=deploy_path)
    yield {"type": "plan", "ai_generated": plan.get("ai_generated"), "system": _sys,
           "title": plan.get("title", ""), "plan": plan.get("plan", "")}
    yield log(f"部署方案已生成({deploy_type} / 系统: {_sys or 'unknown'}):")
    for _ln in (plan.get("plan") or "").splitlines():
        yield log(_ln)
    # docker 仍然需要 compose 用于执行(有定制参数则按模板渲染, 否则用默认)
    offline_registry_url = ""
    offline_insecure = False
    if deploy_type == "docker":
        offline_image = ""
        if use_offline:
            from app.services.offline_repo_service import resolve_offline_image as _roi
            _ri = _roi(db, image, True) if image else {"image": "", "registry_url": "", "is_insecure": False}
            offline_image = _ri.get("image") or ""
            offline_registry_url = _ri.get("registry_url") or ""
            offline_insecure = bool(_ri.get("is_insecure"))
            if offline_image and offline_registry_url:
                yield log(f"🟢 使用离线私有仓库镜像: {offline_image}")
        if params:
            compose = render_compose(comp, params, port, offline_image=offline_image)
        else:
            compose = compose or (comp.get("compose_yaml") or build_default_compose(name, offline_image or image, port))

    # ── 阶段3: 执行部署 ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 3, "title": "阶段3/5 执行部署"}
    if deploy_type == "docker":
        yield log(f"docker compose up -d (路径: {deploy_path}) ...")
        prep = ""
        if offline_insecure and offline_registry_url:
            _dj_url = offline_registry_url.replace("/", "\\/").replace('"', '\\"')
            prep = (
                f"DK=/etc/docker/daemon.json; "
                f"if ! grep -q '{offline_registry_url}' \"$DK\" 2>/dev/null; then "
                f"  mkdir -p /etc/docker; "
                f"  if ! python3 -c \"import json;d=json.load(open('$DK'));d.setdefault('insecure-registries',[]).append('{offline_registry_url}');json.dump(d,open('$DK','w'),indent=2)\" 2>/dev/null; then "
                f"    echo '{{\"insecure-registries\":[\"{_dj_url}\"]}}' > \"$DK\"; "
                f"  fi; "
                f"  systemctl restart docker 2>/dev/null || service docker restart 2>/dev/null || true; "
                f"fi; "
            )
            yield log(f"🟢 已为目标机配置 insecure-registry: {offline_registry_url}")
        ok, out = _exec_ssh(asset, (
            f"{prep}"
            f"mkdir -p '{deploy_path}'; "
            f"cat > '{deploy_path}/docker-compose.yml' <<'AIOPS_COMPOSE'\n{compose}\nAIOPS_COMPOSE\n"
            f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; "
            f"OUT=$(docker compose up -d 2>&1); RC=$?; "
            f"echo \"$OUT\" | tail -30; echo __RC__=$RC"
        ), timeout=300)
        yield log(out)
        if not ok:
            yield diag("docker compose up 失败", phase="执行部署")
            # ▼ AI 自主决策闭环: AI 自选 fix/retry/skip/rollback, 高危才等人确认, 自动重试
            retry_up = f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; OUT=$(docker compose up -d 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC"
            _ad = yield from ai_handle_failure(
                f"{name} docker compose up 失败, AI 自主处置(自动执行修复/重试)",
                out, retry_cmd=retry_up, risk_level="medium", max_auto=2)
            if _ad.get("decision") == "":
                yield {"type": "error", "message": "docker compose up 失败"}
                yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                return
            if _ad.get("decision") == "skip":
                yield log("AI 判定跳过 compose 启动(继续后续流程)")
            else:
                # 处置后重新校验容器是否起来 (健康门禁)
                ok, out = _exec_ssh(asset, (
                    f"cd '{deploy_path}'; docker compose ps --format '{{{{.Name}}}} {{{{.Status}}}}' 2>/dev/null | head -10"
                ), timeout=120)
                yield log(out or "(无容器状态)")
                _o = out.lower()
                _up = ("up" in _o or "running" in _o or "healthy" in _o or "ok" in _o) and "exit" not in _o
                if not ok or not _up:
                    yield {"type": "error", "message": "docker compose 容器未成功启动"}
                    yield {"type": "complete", "status": "failed", "message": f"部署失败: 容器未启动 {(out or '')[:200]}"}
                    return
        yield ai("deploy")
    elif deploy_type == "native":
        # 优先使用组件显式配置的原生安装脚本(native_script, 如 Kafka 下载二进制/KRaft);
        # 仅当未配置 native_script 时才按系统类型回退到通用系统包管理器(yum/apt install -y {name})
        _sys_n = (pc or {}).get("system") or ""
        _native_script = comp.get("native_script") or ""
        install_cmd = ""
        if _native_script:
            install_cmd = _native_script
        elif _sys_n in ("debian", "ubuntu"):
            install_cmd = f"apt-get update && apt-get install -y {name}"
        elif _sys_n in ("rhel", "centos", "alma", "rocky"):
            install_cmd = f"(command -v dnf >/dev/null 2>&1 && dnf install -y {name}) || yum install -y {name}"
        if not install_cmd and not _native_script and not _sys_n:
            yield diag("组件未提供原生安装脚本, 无法执行 native 部署", phase="执行部署")
            yield {"type": "error", "message": "组件未提供原生安装脚本"}
            yield {"type": "complete", "status": "failed", "message": "部署失败: 无原生安装脚本"}
            return
        script = install_cmd or _native_script
        script = _inject_native_params(script, comp, params)
        # ▼ 离线二次强制校验: native 安装脚本禁止公网源
        _nb = _offline_native_block(script) if use_offline else ""
        if _nb:
            yield log(f"⛔ {_nb}")
            yield {"type": "error", "message": _nb}
            yield {"type": "complete", "status": "failed", "message": _nb}
            return
        yield log(f"按系统类型({_sys_n or 'unknown'})执行安装: {script[:120]}")
        ok, out = _exec_ssh(asset, f"OUT=$({script} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC", timeout=400)
        yield log(out)
        if not ok:
            yield diag("native 安装脚本执行返回非零, 部署失败", phase="执行部署")
            # ▼ AI 自主决策闭环: AI 自选处置并自动执行, 高危/回滚才等人确认
            _ad = yield from ai_handle_failure(
                f"{name} 原生安装脚本执行失败, AI 自主处置",
                out, retry_cmd=f"OUT=$({script} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC",
                risk_level="medium", max_auto=2)
            if _ad.get("decision") == "":
                yield {"type": "error", "message": "native 部署失败"}
                yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                return
            if _ad.get("decision") == "skip":
                yield log("AI 判定跳过 native 安装(继续后续验证)")
                choice = "skip"
            else:
                choice = _ad.get("decision")  # fix/retry/rollback/human 已处理
            # 返回后由下方验证逻辑兜底; 若 AI 未给出有效处置则失败
            if not choice:
                yield {"type": "error", "message": "native 部署失败"}
                yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                return
        # native 部署后验证: 检查进程/端口是否真正起来(避免装失败仍判 running)
        vdef = _NATIVE_VERIFY.get(name)
        if vdef:
            vcmd, okkeys = vdef
        else:
            vcmd = f"(pgrep -x {name} >/dev/null 2>&1 || pidof {name} >/dev/null 2>&1) && echo UP || echo DOWN"
            okkeys = ["UP"]
        vok, vout = _exec_ssh(asset, vcmd, timeout=60)
        # 关键: 只看明确的成功标记 UP 且无 DOWN(避免 'inactive' 含 'active' 子串误判)
        passed = ("UP" in vout) and ("DOWN" not in vout) if okkeys else bool(vout.strip())
        if not passed:
            yield log(f"⚠ 验证未通过: {vout[:150]}")
            yield diag(f"native 安装脚本执行了但服务未起来: {vout[:150]}", phase="验证")
            # ▼ AI 自主处置: AI 自选启动修复/重试, 回滚/高危才等人确认; 处置后重新验证
            _ad2 = yield from ai_handle_failure(
                f"{name} 服务未起来(验证未通过), AI 自主处置",
                out + "\n" + vout,
                retry_cmd=vcmd if not (okkeys and "UP" in okkeys) else f"systemctl restart {name} 2>/dev/null; sleep 3; {vcmd}",
                risk_level="medium", max_auto=2)
            if _ad2.get("decision") == "":
                yield {"type": "complete", "status": "failed", "message": f"部署脚本已执行但验证未通过: {vout[:150]}"}
                return
            if _ad2.get("decision") == "skip":
                yield log("AI 判定跳过验证(继续后续流程)")
                passed = True
            else:
                vk2, vout2 = _exec_ssh(asset, vcmd, timeout=60)
                passed = ("UP" in vout2) and ("DOWN" not in vout2) if okkeys else bool(vout2.strip())
                if passed:
                    yield log(f"重新验证通过: {vout2[:120]}")
                    yield ai("deploy")
                    native_ok = True
                else:
                    yield {"type": "complete", "status": "failed", "message": f"处置后服务仍未起来: {vout2[:120]}"}
                    return
        else:
            yield log(f"验证通过: {vout[:120]}")
            yield ai("deploy")
    else:
        # helm / ha: 虚拟执行(依赖 K8s/helm 引擎)
        yield log(f"{deploy_type} 部署记录已创建(依赖 K8s/helm 引擎执行)。配方见上方。")
        yield ai("helm")
        yield {"type": "complete", "status": "deployed", "message": f"{name} {deploy_type} 记录已建(待 K8s/helm 引擎执行)"}
        return

    # ── 阶段4: 验证 ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 4, "title": "阶段4/5 部署验证"}
    if deploy_type == "docker":
        cn = f"aiops-{name}"
        ok2, ps = _exec_ssh(asset, f"docker ps --filter name={cn} --format '{{{{.Names}}}} {{{{.Status}}}}' 2>&1 | head -5")
        running = "Up" in ps
        yield log(f"容器状态: {ps or '(未找到)'}")
        if not running:
            yield diag(f"docker 容器未进入 Up 状态: {ps or '(空)'}", phase="验证")
            yield {"type": "error", "message": "容器未进入 Up 状态"}
            yield {"type": "complete", "status": "failed", "message": f"容器未启动: {ps}"}
            return
        yield ai("verify")
    else:
        h, hout = _exec_ssh(asset, _HEALTH_CMDS.get(name, f"systemctl is-active {name} 2>/dev/null || echo DOWN"))
        yield log(f"健康探测: {hout[:200]}")
        yield ai("verify")

    yield {"type": "status", "status": "succeeded", "message": f"{name} 部署成功"}
    yield ai("done")

    # 部署成功后自动触发四合一体检(健康/配置/漏洞/AI 分析), 并产出可直接交付的 AI 部署报告
    health_data = None
    if install_id and deploy_type in ("docker", "native"):
        try:
            yield {"type": "phase", "step": 4, "title": "部署后·四合一体检"}
            yield log("部署成功, 自动执行健康/配置/漏洞/AI 四合一体检...")
            _report = full_health_check(db, install_id)
            health_data = _report
            yield {"type": "report", "report": _report,
                   "overall_status": _report.get("overall_status"),
                   "summary": ((_report.get("ai") or {}).get("summary") or "") or f"{name} 体检完成 overall={_report.get('overall_status')}"}
            yield log(f"四合一体检完成: overall={_report.get('overall_status')}")
        except Exception as _e:
            yield log(f"四合一体检跳过: {_e}")

    # 可直接交付的 AI 部署报告(结论/执行/影响/下一步/风险)
    deliv = final_report("succeeded", "\n".join(connbuf[-60:]), health_data)
    yield deliv

    yield {"type": "complete", "status": "succeeded", "message": f"{name} 部署成功"}


def precheck_deploy(db, asset, comp: dict, deploy_type: str = "docker",
                    port: Optional[int] = None, http_proxy: str = "",
                    https_proxy: str = "", no_proxy: str = "",
                    deploy_path: str = "") -> dict:
    """逻辑预检(对标 K8s 集群部署 precheck)。

    返回: {ok, issues, checks:[{name, ok, message}]}
    预检项: 目标机资产/SSH 连通/root 校验/端口占用/对应部署方式环境/代理可达/资源(含部署路径)。
    供前端「预检」按钮与部署流开头复用(不产生副作用)。
    """
    checks = []
    issues = []
    system = ""

    def _add(name, ok, msg=""):
        checks.append({"name": name, "ok": bool(ok), "message": msg or ("" if ok else "未通过")})
        if not ok:
            issues.append(f"{name}: {msg}" if msg else name)

    # 1. 目标机资产
    if not asset:
        _add("目标机资产", False, "资产不存在")
        return {"ok": False, "issues": issues, "checks": checks}
    _add("目标机资产", asset.connection_type == "ssh",
         f"{asset.name} ({asset.ip}) type={asset.connection_type or '?'}")

    if asset.connection_type != "ssh":
        return {"ok": False, "issues": issues, "checks": checks}

    # 2. SSH 连通 + root
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=12)
        ok = True
        try:
            _in, _out, _err = ssh.exec_command(
                "id -u; free -m | awk '/Mem:/{print $2}'; nproc; "
                "cat /etc/os-release 2>/dev/null | grep -iE '^(ID|VERSION_ID)=' | tr '\\n' ' '; "
                "which yum >/dev/null 2>&1 && echo pkgyum; which apt-get >/dev/null 2>&1 && echo pkgapt; which dnf >/dev/null 2>&1 && echo pkgdnf",
                timeout=25)
            out = _out.read().decode(errors="ignore").strip()
            ssh.close()
            lines = out.splitlines() or [""]
            uid = lines[0].strip()
            _add("SSH 连通", True, f"连接成功 uid={uid}")
            _add("root 权限", uid == "0", "非 root 用户" if uid != "0" else "")
            try:
                _mem = int(lines[1].strip()) if len(lines) > 1 and lines[1].strip().isdigit() else 0
                _add("目标机内存", _mem > 0, f"可用内存约 {_mem} MB" if _mem else "无法读取内存")
            except Exception:
                _add("目标机内存", False, "无法读取内存")
            # 探测目标机系统类型(pkg_manager + distro)
            _pm = ""
            for l in lines:
                if l.startswith("pkg"):
                    _pm = l[3:]
            _distro = ""
            for l in lines:
                if l.startswith("ID="):
                    _distro = l[len("ID="):].strip().strip('"')
                    break
            _did = (lines[1] if len(lines) > 1 else "")
            system = ("debian" if _pm == "apt" else
                      ("rhel" if _pm in ("yum", "dnf") else
                       ("alpine" if "alpine" in out else ("unknown" if not _distro else _distro))))
            _add("目标机系统", True, f"{_distro or 'unknown'} (包管理器: {_pm or 'unknown'})")
        except Exception as e:
            ssh.close()
            _add("SSH 命令执行", False, str(e)[:80])
    except Exception as e:
        _add("SSH 连通", False, str(e)[:80])

    # 3. 端口占用(docker/native 会占用 default_port)
    p = int(port or comp.get("default_port") or 0)
    if p and asset.connection_type == "ssh":
        try:
            from app.services.remediation_service import _ssh_connect as _sc2
            _ssh2 = _sc2(asset, timeout=12)
            _i, _o, _e = _ssh2.exec_command(f"ss -ltn 2>/dev/null | grep -q ':{p} ' && echo BUSY || echo FREE", timeout=25)
            rr = _o.read().decode(errors="ignore").strip()
            _ssh2.close()
            free = "FREE" in rr and "BUSY" not in rr
            _add(f"端口 {p} 占用", free, "端口已被占用" if not free else "端口可用")
        except Exception as e:
            _add(f"端口 {p} 检查", False, str(e)[:60])

    # 4. 各部署方式环境
    name = comp.get("name", "")
    if deploy_type == "docker":
        try:
            from app.services.remediation_service import _ssh_connect as _sc3
            _ssh3 = _sc3(asset, timeout=12)
            _i, _o, _e = _ssh3.exec_command("docker version --format '{{.Server.Version}}' 2>&1; echo '|'; docker compose version 2>&1 | head -1", timeout=25)
            rr = _o.read().decode(errors="ignore").strip()
            _ssh3.close()
            has_docker = "Docker version" in rr or any(ch.isdigit() for ch in rr.split("|")[0])
            _add("Docker 环境", "|" in rr and has_docker, rr.split("|")[0][:40] or "未安装 Docker")
            _add("Docker Compose", "Docker Compose" in rr or "v2" in rr.lower(), "Compose 未安装" if ("|" in rr and "Docker Compose" not in rr and "v2" not in rr.lower()) else "")
            if http_proxy or https_proxy:
                _add("HTTP 代理", True, f"将写入 docker daemon: {http_proxy or https_proxy}")
        except Exception as e:
            _add("Docker 环境", False, str(e)[:60])
    elif deploy_type == "native":
        _add("原生安装脚本", bool((comp.get("native_script") or "").strip()),
             "组件未提供原生安装脚本, 建议改用 docker" if not (comp.get("native_script") or "").strip() else "脚本就绪")
    elif deploy_type in ("helm", "ha"):
        _add("K8s/Helm 引擎", False, "helm/ha 部署需通过 K8s/helm 引擎执行(当前为记录+配方)")

    # 4.5 网络连通性(目标机能否解析域名/访问源/代理可达) —— 部署前尽早发现网络问题
    if asset.connection_type == "ssh":
        _net_tgt = "registry-1.docker.io" if deploy_type == "docker" else "mirrors.aliyun.com"
        try:
            from app.services.remediation_service import _ssh_connect as _scn
            _sshn = _scn(asset, timeout=12)
            _probe = (f"getent hosts {_net_tgt} >/dev/null 2>&1 && echo DNSOK || echo DNSFAIL; "
                      f"curl -s -o /dev/null -m 6 -I https://{_net_tgt} >/dev/null 2>&1 && echo NETOK || echo NETFAIL")
            _i3, _o3, _e3 = _sshn.exec_command(_probe, timeout=30)
            netout = _o3.read().decode(errors="ignore").strip()
            _sshn.close()
            dns_ok = "DNSOK" in netout
            net_ok = "NETOK" in netout
            # 有代理时额外测代理可达
            _proxy = http_proxy or https_proxy
            proxy_ok = False
            if _proxy:
                try:
                    from app.services.remediation_service import _ssh_connect as _scp
                    _sshp = _scp(asset, timeout=12)
                    _pi, _po, _pe = _sshp.exec_command(
                        f"curl -s -o /dev/null -m 6 -x '{_proxy}' https://{_net_tgt} >/dev/null 2>&1 && echo PROXYOK || echo PROXYFAIL", timeout=30)
                    proxyout = _po.read().decode(errors="ignore").strip()
                    _sshp.close()
                    proxy_ok = "PROXYOK" in proxyout
                    _add(f"代理可达({_net_tgt})", proxy_ok, "代理可连通" if proxy_ok else "代理不可达")
                    # 内网+代理环境: 本机无可用系统 DNS, 域名由代理解析, 代理可达即视为 DNS 通过
                    if proxy_ok:
                        dns_ok = True
                except Exception:
                    pass
            _add(f"DNS 解析({_net_tgt})", dns_ok, f"{_net_tgt} 可解析" if dns_ok else f"无法解析 {_net_tgt}(网络/DNS 问题)")
            _add(f"网络可达({_net_tgt})", net_ok, f"可访问 {_net_tgt}" if net_ok else f"无法访问 {_net_tgt}(源/代理问题)")
        except Exception as e:
            _add("网络连通性", False, str(e)[:60])

    # 5. 资源(基于实际部署路径所在文件系统)
    _target = (deploy_path or "").strip() or "/data"
    try:
        from app.services.remediation_service import _ssh_connect as _sc4
        _ssh4 = _sc4(asset, timeout=12)
        _i, _o, _e = _ssh4.exec_command(
            f"df -m \"$(dirname '{_target}' 2>/dev/null || echo /data)\" 2>/dev/null | awk 'NR==2{{print $4}}'",
            timeout=25)
        dfree = _o.read().decode(errors="ignore").strip()
        _ssh4.close()
        if dfree.isdigit():
            _add(f"磁盘空间({_target})", int(dfree) > 500,
                 f"剩余约 {int(dfree)} MB" if int(dfree) > 500 else "磁盘空间不足(<500MB)")
        # 目录可写性/父目录存在性校验(root 下 mkdir -p 即可创建)
        if deploy_type == "docker" and (deploy_path or "").strip():
            d = _target
            try:
                from app.services.remediation_service import _ssh_connect as _sc5
                _ssh5 = _sc5(asset, timeout=12)
                _i2, _o2, _e2 = _ssh5.exec_command(
                    f"mkdir -p '{d}' && [ -w '{d}' ] && echo WRITABLE || echo NOWRITE; "
                    f"touch '{d}/.aiops_probe' 2>/dev/null && rm -f '{d}/.aiops_probe' && echo OK || echo NOK",
                    timeout=25)
                probe = _o2.read().decode(errors="ignore").strip()
                _ssh5.close()
                wok = "WRITABLE" in probe and "OK" in probe
                _add(f"部署路径可写", wok, f"{d} 可读/可写" if wok else f"{d} 不可写(权限不足)")
            except Exception as _pe:
                _add(f"部署路径可写", False, str(_pe)[:60])
    except Exception:
        pass

    return {"ok": not issues, "issues": issues, "checks": checks, "system": system}
