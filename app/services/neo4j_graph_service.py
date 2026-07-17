"""
Neo4j 知识图谱服务层
支持真实图数据库连接，从 PostgreSQL 数据同步到 Neo4j
"""
import json
import os
from typing import Optional

_neo4j_driver = None


def get_neo4j_config() -> Optional[dict]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    enabled = uri and password and password != "password"
    return {"uri": uri, "user": user, "password": password, "enabled": enabled}


def _get_driver():
    global _neo4j_driver
    if _neo4j_driver is not None:
        return _neo4j_driver
    cfg = get_neo4j_config()
    if not cfg["enabled"]:
        return None
    try:
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(
            cfg["uri"],
            auth=(cfg["user"], cfg["password"]),
            max_connection_lifetime=300,
        )
        return _neo4j_driver
    except Exception:
        return None


def close_driver():
    global _neo4j_driver
    if _neo4j_driver:
        _neo4j_driver.close()
        _neo4j_driver = None


def sync_asset_graph(db_session):
    """从 PostgreSQL 同步资产关系到 Neo4j"""
    driver = _get_driver()
    if not driver:
        return 0

    from app.models import Asset, AssetRelation, Alert, Runbook
    from sqlalchemy.orm import Session

    assets = db_session.query(Asset).all()
    relations = db_session.query(AssetRelation).all()
    runbooks = db_session.query(Runbook).all()
    active_alerts = {}
    for row in db_session.query(Alert.asset_id).filter(
        Alert.status.in_(["triggered", "acknowledged"])
    ).all():
        active_alerts[row[0]] = active_alerts.get(row[0], 0) + 1

    cypher_nodes = """
    UNWIND $nodes AS node
    MERGE (a:Asset {asset_id: node.asset_id})
    SET a.name = node.name,
        a.ci_type = node.ci_type,
        a.status = node.status,
        a.ip = node.ip,
        a.alert_count = node.alert_count
    """

    cypher_rels = """
    UNWIND $rels AS rel
    MATCH (s:Asset {asset_id: rel.source_id}), (t:Asset {asset_id: rel.target_id})
    CALL apoc.merge.relationship(s, rel.rel_type, {}, {}, t, {}) YIELD rel2
    RETURN rel2
    """

    nodes = []
    for a in assets:
        nodes.append({
            "asset_id": f"asset_{a.id}",
            "name": a.name,
            "ci_type": a.ci_type or "unknown",
            "status": a.status or "unknown",
            "ip": a.ip or "",
            "alert_count": active_alerts.get(a.id, 0),
        })

    rels = []
    for rel in relations:
        rels.append({
            "source_id": f"asset_{rel.parent_id}",
            "target_id": f"asset_{rel.child_id}",
            "rel_type": rel.relation_type or "depends_on",
        })

    try:
        with driver.session() as session:
            session.run(cypher_nodes, nodes=nodes)
            session.run(cypher_rels, rels=rels)
        return len(assets)
    except Exception as e:
        return 0


def query_kg(query: str, limit: int = 50) -> list:
    """查询 Neo4j 图数据库"""
    driver = _get_driver()
    if not driver:
        return []
    try:
        cypher = """
        MATCH (a:Asset)
        WHERE a.name CONTAINS $q OR a.ci_type CONTAINS $q
        RETURN a.asset_id AS id, a.name AS name, a.ci_type AS type, a.status AS status, a.ip AS ip
        LIMIT $limit
        """
        with driver.session() as session:
            result = session.run(cypher, q=query, limit=limit)
            return [dict(record) for record in result]
    except Exception:
        return []


def get_subgraph(center_asset_id: str, depth: int = 2) -> dict:
    """获取指定资产为中心的子图"""
    driver = _get_driver()
    if not driver:
        return {"nodes": [], "edges": []}
    try:
        cypher = f"""
        MATCH path = (center:Asset {{asset_id: $center}})
           -[r*1..{depth}]-(connected:Asset)
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH collect(DISTINCT n) AS nodes, rs
        UNWIND rs AS r
        WITH nodes, collect(DISTINCT {{source: startNode(r).asset_id, target: endNode(r).asset_id, relation: type(r)}}) AS edges
        RETURN nodes, edges
        """
        with driver.session() as session:
            result = session.run(cypher, center=center_asset_id)
            record = result.single()
            if not record:
                return {"nodes": [], "edges": []}
            raw_nodes = record["nodes"]
            raw_edges = record["edges"]
            nodes = [{
                "id": n.get("asset_id", ""),
                "label": n.get("name", ""),
                "type": n.get("ci_type", ""),
                "status": n.get("status", ""),
                "ip": n.get("ip", ""),
                "alert_count": n.get("alert_count", 0),
            } for n in raw_nodes]
            edges = [{
                "source": e["source"],
                "target": e["target"],
                "relation": e["relation"],
            } for e in raw_edges]
            return {"nodes": nodes, "edges": edges}
    except Exception:
        return {"nodes": [], "edges": []}
