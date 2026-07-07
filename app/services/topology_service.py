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
    container_types = ["cluster", "kubernetes_cluster", "namespace", "node", "deployment", "statefulset",
                       "daemonset", "pod", "service", "ingress", "pvc"]
    all_assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).all()

    # 只保留：1）kubernetes_cluster/cluster 根节点 2）有 parent_id 且父级在集合中的后代
    # 过滤掉旧 seed 数据中无 parent_id 的零散 k8s 资产
    cluster_ids = set(a.id for a in all_assets if a.ci_type in ("kubernetes_cluster", "cluster"))
    valid_ids = set(cluster_ids)
    changed = True
    while changed:
        changed = False
        for a in all_assets:
            if a.id not in valid_ids and a.parent_id and a.parent_id in valid_ids:
                valid_ids.add(a.id)
                changed = True
    assets = [a for a in all_assets if a.id in valid_ids]

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

    # 构建树形结构（按 ci_type 语义分层，不依赖 owns 边）
    node_dict = {n["id"]: n for n in nodes}
    roots = [n for n in nodes if n["ci_type"] in ("kubernetes_cluster", "cluster")]

    # 构建 parent_id 索引
    by_parent = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid:
            if pid not in by_parent:
                by_parent[pid] = []
            by_parent[pid].append(n)

    # 同时构建 name 索引用于 ns→deploy 的关联（deployment/pod 的 name 含 namespace 前缀）
    name_to_node = {n["name"]: n for n in nodes}
    # namespace 名称到 id 的映射（用于 deployment/pod/service 通过名称前缀找到所属 namespace）
    ns_name_map = {}
    for n in nodes:
        if n["ci_type"] == "namespace":
            full = n.get("full_name", n["name"])
            # 取 name 的最后一段
            key = n["name"]
            ns_name_map[key] = n["id"]

    def find_ns_for(child):
        """通过名称前缀查找所属 namespace id"""
        full = child.get("full_name", child["name"])
        parts = full.split("/")
        if len(parts) >= 3:
            ns_name = parts[1]
            for nk, nid in ns_name_map.items():
                if nk == ns_name:
                    return nid
        return child.get("parent_id")

    def find_parent_dep(child, dep_list):
        """通过名称前缀查找所属 deployment id"""
        full = child.get("full_name", child["name"])
        parts = full.split("/")
        child_name = parts[-1] if len(parts) > 1 else child["name"]
        for dep in dep_list:
            dep_full = dep.get("full_name", dep["name"])
            dep_parts = dep_full.split("/")
            dep_name = dep_parts[-1]
            if child_name.startswith(dep_name + "-") or child_name == dep_name:
                return dep["id"]
            # daemonset 的 pod 名可能包含 daemonset 名
            if dep_name in child_name:
                return dep["id"]
        return None

    # 按语义分层构建树
    def build_semantic_tree():
        tree_roots = []
        for root in roots:
            cluster_id = root["id"]
            # 找出所有 namespace 子节点
            ns_nodes = [n for n in nodes if n["ci_type"] == "namespace" and n.get("parent_id") == cluster_id]
            ns_list = []
            for ns in ns_nodes:
                ns_id = ns["id"]
                # 找这个 namespace 下的 deployment
                deps = [n for n in nodes if n["ci_type"] in ("deployment", "statefulset", "daemonset") and (n.get("parent_id") == ns_id or find_ns_for(n) == ns_id)]
                dep_list = []
                for dep in deps:
                    dep_id = dep["id"]
                    dep_pods = [n for n in nodes if n["ci_type"] == "pod" and (n.get("parent_id") == dep_id or find_parent_dep(n, [dep]) == dep_id)]
                    dep_list.append({
                        "id": dep["id"], "name": dep["name"],
                        "full_name": dep.get("full_name", ""),
                        "ci_type": dep["ci_type"],
                        "status": dep["status"],
                        "cluster": dep.get("cluster", ""),
                        "attrs": dep.get("attrs", {}),
                        "abnormal": dep.get("abnormal", False),
                        "children": dep_pods,
                    })
                svcs = [n for n in nodes if n["ci_type"] == "service" and (n.get("parent_id") == ns_id or find_ns_for(n) == ns_id)]
                dep_list.extend({
                    "id": s["id"], "name": s["name"],
                    "full_name": s.get("full_name", ""),
                    "ci_type": s["ci_type"],
                    "status": s["status"],
                    "cluster": s.get("cluster", ""),
                    "attrs": s.get("attrs", {}),
                    "abnormal": s.get("abnormal", False),
                    "children": [],
                } for s in svcs)
                ns_list.append({
                    "id": ns["id"], "name": ns["name"],
                    "full_name": ns.get("full_name", ""),
                    "ci_type": ns["ci_type"],
                    "status": ns["status"],
                    "cluster": ns.get("cluster", ""),
                    "attrs": ns.get("attrs", {}),
                    "abnormal": ns.get("abnormal", False),
                    "children": dep_list,
                })
            tree_roots.append({
                "id": root["id"], "name": root["name"],
                "full_name": root.get("full_name", ""),
                "ci_type": root["ci_type"],
                "status": root["status"],
                "cluster": root.get("cluster", ""),
                "attrs": root.get("attrs", {}),
                "abnormal": root.get("abnormal", False),
                "children": ns_list,
            })
        return tree_roots

    trees = build_semantic_tree()

    return {"nodes": nodes, "links": links, "clusters": clusters, "stats": stats, "trees": trees}


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

