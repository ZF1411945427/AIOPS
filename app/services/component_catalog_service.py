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
    },
    {
        "name": "kafka", "display_name": "Apache Kafka", "category": "message",
        "version": "3.6", "description": "分布式消息/流平台", "icon": "📨",
        "docker_image": "bitnami/kafka:3.6", "helm_chart": "bitnami/kafka", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 9092, "deploy_types": ["docker", "helm", "ha"],
        "native_script": "", "compose_yaml": "",
        "ha_config": json.dumps({"mode": "cluster", "brokers": 3}, ensure_ascii=False),
        "config_keys": "server.properties", "complexity": "complex", "sort_order": 3,
    },
    {
        "name": "rabbitmq", "display_name": "RabbitMQ", "category": "message",
        "version": "3-management", "description": "消息队列(AMQP)", "icon": "🐇",
        "docker_image": "rabbitmq:3-management", "helm_chart": "bitnami/rabbitmq", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 5672, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y rabbitmq-server || (apt-get update && apt-get install -y rabbitmq-server)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "rabbitmq.conf", "complexity": "medium", "sort_order": 4,
    },
    {
        "name": "nginx", "display_name": "Nginx", "category": "web",
        "version": "latest", "description": "高性能 Web/反向代理服务器", "icon": "🌐",
        "docker_image": "nginx:latest", "helm_chart": "bitnami/nginx", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 80, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y nginx || (apt-get update && apt-get install -y nginx)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "keepalived", "replicas": 2}, ensure_ascii=False),
        "config_keys": "nginx.conf", "complexity": "simple", "sort_order": 5,
    },
    {
        "name": "elasticsearch", "display_name": "Elasticsearch", "category": "database",
        "version": "8.12", "description": "分布式搜索与分析引擎", "icon": "🔎",
        "docker_image": "docker.elastic.co/elasticsearch/elasticsearch:8.12.2", "helm_chart": "elastic/elasticsearch", "helm_repo": "https://helm.elastic.co",
        "default_port": 9200, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y elasticsearch || echo '需官方 repo'",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "cluster", "nodes": 3}, ensure_ascii=False),
        "config_keys": "elasticsearch.yml", "complexity": "complex", "sort_order": 6,
    },
    {
        "name": "mongodb", "display_name": "MongoDB", "category": "database",
        "version": "7", "description": "文档型 NoSQL 数据库", "icon": "🍃",
        "docker_image": "mongo:7", "helm_chart": "bitnami/mongodb", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 27017, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y mongodb-org || (apt-get update && apt-get install -y mongodb)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "replicaset", "members": 3}, ensure_ascii=False),
        "config_keys": "mongod.conf", "complexity": "medium", "sort_order": 7,
    },
    {
        "name": "postgresql", "display_name": "PostgreSQL", "category": "database",
        "version": "16", "description": "开源关系型数据库(对象-关系)", "icon": "🐘",
        "docker_image": "postgres:16", "helm_chart": "bitnami/postgresql", "helm_repo": "https://charts.bitnami.com/bitnami",
        "default_port": 5432, "deploy_types": ["native", "docker", "helm", "ha"],
        "native_script": "yum install -y postgresql-server || (apt-get update && apt-get install -y postgresql)",
        "compose_yaml": "", "ha_config": json.dumps({"mode": "replication", "replicas": 1}, ensure_ascii=False),
        "config_keys": "postgresql.conf", "complexity": "medium", "sort_order": 8,
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
    install_count = 0
    return {
        "id": c.id, "name": c.name, "display_name": c.display_name,
        "category": c.category, "version": c.version, "description": c.description,
        "icon": c.icon, "docker_image": c.docker_image, "helm_chart": c.helm_chart,
        "helm_repo": c.helm_repo, "default_port": c.default_port,
        "deploy_types": deploy_types, "native_script": c.native_script,
        "compose_yaml": c.compose_yaml, "ha_config": ha_config,
        "config_keys": c.config_keys, "complexity": c.complexity,
        "sort_order": c.sort_order, "install_count": install_count,
    }


# ───────────── 部署 ─────────────

def get_deploy_render(comp: dict, deploy_type: str, params: dict) -> dict:
    """渲染部署配方内容(不执行): 返回 compose/native 脚本/helm 命令, 供前端确认。
    comp 为 get_component 的 dict。"""
    allowed = comp.get("deploy_types") or []
    if deploy_type not in allowed:
        return {"ok": False, "error": f"组件不支持部署方式 {deploy_type}(支持: {allowed})"}

    host = params.get("host") or ""
    ns = params.get("namespace") or "default"
    release = params.get("release") or f"{comp['name']}-{datetime.now().strftime('%m%d%H%M')}"
    port = comp.get("default_port") or 0
    image = comp.get("docker_image") or ""

    if deploy_type == "docker":
        compose = comp.get("compose_yaml") or build_default_compose(comp["name"], image, port)
        content = f"# {comp.get('display_name')} Docker 部署 (docker compose)\n# 目标机: {host}\n{compose}\n# 命令: docker compose up -d\n"
        meta = {"kind": "docker", "release": release}
    elif deploy_type == "native":
        script = comp.get("native_script") or f"echo '暂未提供 {comp['name']} 原生安装脚本'"
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
        "ai_analysis": r.ai_analysis, "deploy_log": (r.deploy_log or "")[-2000:],
        "deploy_plan_id": r.deploy_plan_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def record_install(db: Session, component_id: int, component_name: str, asset_id: int,
                   deploy_type: str, deploy_path: str = "", release_name: str = "",
                   name_space: str = "", port: int = 0) -> dict:
    inst = ComponentInstall(
        component_id=component_id, component_name=component_name, asset_id=asset_id,
        deploy_type=deploy_type, deploy_path=deploy_path, release_name=release_name,
        name_space=name_space, port=port, status="running",
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
    if deploy_path:
        logs.append(_apply_docker_proxy(asset, http_proxy, https_proxy, no_proxy))
    # 生成 compose(优先显式传入覆盖)
    compose = (compose or comp.get("compose_yaml") or build_default_compose(name, image, port))
    cn = f"aiops-{name}"
    # 组合远程执行命令
    remote = (
        f"set -e; mkdir -p '{deploy_path}'; "
        f"cat > '{deploy_path}/docker-compose.yml' <<'AIOPS_COMPOSE'\n{compose}\nAIOPS_COMPOSE\n"
        f"cd '{deploy_path}' && docker compose down >/dev/null 2>&1; "
        f"docker compose up -d 2>&1 | tail -20; echo __RC__=$?"
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
        return (out != "" or err == "", out or err)
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

    r.config_check_status = "pass" if all(c["status"] == "pass" for c in result["checks"]) and result["checks"] else "drift"
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
    config_ok = result["config"] and result["config"].get("config_check_status") in ("pass", None)
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
