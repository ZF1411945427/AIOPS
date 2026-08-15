"""组件智能运维 —— 组件 → 真实资产绑定与巡检目标解析

「组件方案」页每个组件卡片展示的是能力覆盖状态，但真正巡检必须有具体的目标资产。
本模块负责：
  1. 组件识别键(组件名) → 资产匹配规则(按 ci_type / connection_config.db_type / mw_subtype)
  2. 返回当前库中匹配的真实资产，供前端绑定 + 「问 AI」携带 asset_id 发起巡检
"""
import json
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models import Asset

# 组件 → 资产匹配规则。key 为前端组件名(与 ComponentOPSView comps[].name 对齐)
# rule: ci_type 必填; db_type/mw_subtype/name_kw 至少一个, 用于从 connection_config/名称进一步筛选
COMPONENT_ASSET_RULES: Dict[str, Dict] = {
    "MySQL":        {"ci_type": "database", "db_type": "mysql"},
    "PostgreSQL":   {"ci_type": "database", "db_type": "postgresql"},
    "Oracle":       {"ci_type": "database", "db_type": "oracle"},
    "SQL Server":   {"ci_type": "database", "db_type": "sqlserver"},
    "MongoDB":      {"ci_type": "database", "db_type": "mongodb"},
    "Elasticsearch":{"ci_type": "database", "db_type": "elasticsearch"},
    "OpenSearch":   {"ci_type": "database", "db_type": "opensearch"},
    "ClickHouse":   {"ci_type": "database", "db_type": "clickhouse"},
    "Redis":        {"ci_type": "database", "db_type": "redis"},
    "Kafka":        {"ci_type": "database", "db_type": "kafka"},
    "RabbitMQ":     {"ci_type": "middleware", "mw_subtype": "rabbitmq"},
    "RocketMQ":     {"ci_type": "middleware", "mw_subtype": "rocketmq"},
    "Nacos":        {"ci_type": "middleware", "mw_subtype": "nacos"},
    "ZooKeeper":    {"ci_type": "middleware", "mw_subtype": "zookeeper"},
    "etcd":         {"ci_type": "middleware", "mw_subtype": "etcd"},
    "Nginx":        {"ci_type": "middleware", "mw_subtype": "nginx"},
    "Kubernetes":   {"ci_type": "kubernetes_cluster"},
    "Linux 服务器":  {"ci_type": "virtual_machine"},
    "Windows 服务器": {"ci_type": "virtual_machine", "name_kw": "windows"},
}


def _asset_cfg(asset: Asset) -> dict:
    if not asset.connection_config:
        return {}
    if isinstance(asset.connection_config, dict):
        return asset.connection_config
    try:
        return json.loads(asset.connection_config) if asset.connection_config else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _match_rule(asset: Asset, rule: dict) -> bool:
    if asset.ci_type != rule.get("ci_type"):
        return False
    cfg = _asset_cfg(asset)
    db_type = rule.get("db_type")
    mw_subtype = rule.get("mw_subtype")
    name_kw = rule.get("name_kw")
    if db_type and cfg.get("db_type", "").lower() != db_type:
        return False
    if mw_subtype and cfg.get("mw_subtype", "").lower() != mw_subtype:
        return False
    if name_kw and name_kw not in (asset.name or "").lower():
        return False
    return True


def resolve_component_assets(db: Session, component_name: str) -> List[Dict]:
    """返回匹配组件名的真实资产列表(id/name/status/ip/type/cfg)。按状态在线优先。"""
    rule = COMPONENT_ASSET_RULES.get(component_name)
    if not rule:
        return []
    matched = [
        a for a in db.query(Asset).all() if _match_rule(a, rule)
    ]
    matched.sort(key=lambda a: (a.status != "online", a.id))
    return [{
        "id": a.id,
        "name": a.name,
        "status": a.status,
        "ip": a.ip or "",
        "type": a.ci_type,
        "cfg": _asset_cfg(a),
    } for a in matched]


def build_inspection_prompt(component_name: str, asset: Optional[Dict]) -> str:
    """构造「问 AI」的巡检提问: 携带目标资产, 让 AI 用 MCP 工具对真实实例巡检。"""
    base = f"请对「{component_name}」组件做一次智能运维巡检"
    if asset:
        base += (f"，目标资产为「{asset['name']}」(资产ID {asset['id']}, "
                 f"IP {asset.get('ip','') or '无'})，请用对应 MCP 诊断工具针对该资产实例巡检 "
                 f"(如 query_mysql / redis_monitor / kafka_monitor / es_diagnose 等，参数 asset_id 传 {asset['id']})，"
                 f"输出巡检结论、发现的问题与优化建议。")
    return base
