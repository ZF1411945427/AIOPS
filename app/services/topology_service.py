import json
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation


def get_relations(db: Session):
    return db.query(AssetRelation).all()


def _parse_attrs(a):
    """安全解析 ci_attributes JSON，兼容 str/dict/None"""
    if not a.ci_attributes:
        return {}
    if isinstance(a.ci_attributes, dict):
        return a.ci_attributes
    try:
        return json.loads(a.ci_attributes)
    except Exception:
        return {}


def build_k8s_topo_graph(db: Session):
    """构建 K8s 多维关系图：ownership 层级 + pod-node 调度 + 异常标记。
    返回 {nodes, links, clusters, stats} 供 d3 力导向图渲染。
    """
    container_types = ["cluster", "namespace", "node", "deployment", "statefulset",
                       "daemonset", "pod", "service", "ingress", "pvc"]
    assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).all()

    # 节点按 id 索引，预解析 attrs
    asset_map = {}
    nodes = []
    for a in assets:
        attrs = _parse_attrs(a)
        asset_map[a.id] = {"asset": a, "attrs": attrs}
        # 异常标记：pod phase 非 Running/未知、status offline
        is_abnormal = False
        if a.ci_type == "pod":
            phase = attrs.get("phase", "")
            is_abnormal = phase not in ("Running", "")
        elif a.status == "offline":
            is_abnormal = True
        nodes.append({
            "id": a.id,
            "name": a.name.split("/")[-1] if "/" in a.name else a.name,
            "full_name": a.name,
            "ci_type": a.ci_type,
            "status": a.status,
            "cluster": a.k8s_cluster or attrs.get("k8s_cluster", ""),
            "attrs": attrs,
            "abnormal": is_abnormal,
            "parent_id": a.parent_id,
        })

    # 构建链接
    links = []
    seen_edges = set()

    def _add_edge(source_id, target_id, rel_type):
        """target 指向 source 的拥有关系：cluster owns namespace → edge cluster→namespace"""
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id, rel_type)
        if key in seen_edges:
            return
        seen_edges.add(key)
        links.append({"source": source_id, "target": target_id, "type": rel_type})

    # 1. ownership 层级（parent_id）
    for a in assets:
        if a.parent_id and a.parent_id in asset_map:
            _add_edge(a.parent_id, a.id, "owns")

    # 2. pod → node 调度关系（基于 attrs.node 名称匹配 node 资产）
    name_to_asset = {}
    for a in assets:
        if a.ci_type in ("node",):
            name_to_asset[a.name] = a.id
    for a in assets:
        if a.ci_type == "pod":
            attrs = asset_map[a.id]["attrs"]
            node_name = attrs.get("node", "")
            if node_name and node_name in name_to_asset:
                _add_edge(name_to_asset[node_name], a.id, "scheduled_on")

    # 3. service → pod selector 关联（基于 attrs.selector 匹配 pod attrs.labels，当前 demo 无 labels，跳过；
    #    退化策略：service.name 含 app 名 → 关联同 namespace 下 name 含同关键词的 pod）
    for a in assets:
        if a.ci_type != "service":
            continue
        svc_attrs = asset_map[a.id]["attrs"]
        selector = svc_attrs.get("selector", {})
        svc_ns = svc_attrs.get("namespace", "")
        if selector:
            # 精确 selector 匹配（pod attrs.labels 需存在，当前 demo 无，保留逻辑供真实数据）
            for a2 in assets:
                if a2.ci_type != "pod":
                    continue
                pod_attrs = asset_map[a2.id]["attrs"]
                if pod_attrs.get("namespace") != svc_ns:
                    continue
                pod_labels = pod_attrs.get("labels", {})
                if all(pod_labels.get(k) == v for k, v in selector.items()):
                    _add_edge(a.id, a2.id, "selects")

    # 集群分组
    clusters = sorted(set(n["cluster"] for n in nodes if n["cluster"]))

    # 统计
    from collections import Counter
    type_counter = Counter(n["ci_type"] for n in nodes)
    stats = {
        "total": len(nodes),
        "by_type": dict(type_counter),
        "abnormal_count": sum(1 for n in nodes if n["abnormal"]),
        "link_count": len(links),
        "cluster_count": len(clusters),
    }

    return {"nodes": nodes, "links": links, "clusters": clusters, "stats": stats}


def create_relation(db: Session, parent_id: int, child_id: int, relation_type: str = "depends_on"):
    if parent_id == child_id:
        return None
    exists = db.query(AssetRelation).filter(
        AssetRelation.parent_id == parent_id,
        AssetRelation.child_id == child_id,
    ).first()
    if exists:
        return exists
    r = AssetRelation(parent_id=parent_id, child_id=child_id, relation_type=relation_type)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def delete_relation(db: Session, relation_id: int):
    db.query(AssetRelation).filter(AssetRelation.id == relation_id).delete()
    db.commit()


def build_topo(db: Session):
    assets = db.query(Asset).order_by(Asset.type, Asset.name).all()
    relations = db.query(AssetRelation).all()
    asset_map = {a.id: {"id": a.id, "name": a.name, "type": a.type, "ci_type": a.ci_type, "status": a.status} for a in assets}
    children_map = {}
    for r in relations:
        children_map.setdefault(r.parent_id, []).append({
            "child_id": r.child_id, "type": r.relation_type,
        })
    trees = []
    linked = set()
    for r in relations:
        linked.add(r.child_id)
    roots = [a for a in assets if a.id not in linked]

    def build_node(aid):
        node = dict(asset_map.get(aid, {}))
        children = children_map.get(aid, [])
        if children:
            node["children"] = [build_node(c["child_id"]) for c in children]
        return node

    for root in roots:
        trees.append(build_node(root.id))
    orphans = [a for a in assets if a.id not in linked and a.id not in {r.parent_id for r in relations}]
    for o in orphans:
        if o.id not in linked:
            trees.append(build_node(o.id))
    return trees


def build_container_topo(db: Session):
    container_types = ["cluster", "namespace", "node", "deployment", "statefulset", "daemonset", "pod", "service", "ingress", "pvc", "container"]
    assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).order_by(Asset.ci_type, Asset.name).all()
    asset_map = {}
    for a in assets:
        try:
            attrs = json.loads(a.ci_attributes) if isinstance(a.ci_attributes, str) else a.ci_attributes or {}
        except Exception:
            attrs = {}
        asset_map[a.id] = {
            "id": a.id,
            "name": a.name.split("/")[-1],
            "full_name": a.name,
            "ci_type": a.ci_type,
            "status": a.status,
            "k8s_cluster": a.k8s_cluster,
            "attrs": attrs,
            "parent_id": a.parent_id,
        }

    children_map = {}
    for aid, a in asset_map.items():
        pid = a.get("parent_id")
        if pid and pid in asset_map:
            children_map.setdefault(pid, []).append(aid)

    roots = [aid for aid, a in asset_map.items() if a.get("parent_id") not in asset_map]

    def build_node(aid):
        a = asset_map.get(aid, {})
        node = {
            "id": a["id"],
            "name": a["name"],
            "full_name": a["full_name"],
            "ci_type": a["ci_type"],
            "status": a["status"],
            "k8s_cluster": a["k8s_cluster"],
            "attrs": a["attrs"],
        }
        kids = children_map.get(aid, [])
        if kids:
            node["children"] = [build_node(kid) for kid in kids]
        return node

    return [build_node(root) for root in roots if root in asset_map]

