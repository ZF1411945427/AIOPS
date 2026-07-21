import json
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation, DataSource


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


def _get_online_cluster_names(db: Session) -> set:
    """查询 DataSource 表，返回状态为 online 的 k8s 集群名称集合"""
    online_ds = db.query(DataSource).filter(
        DataSource.type == "kubernetes",
        DataSource.last_status == "online"
    ).all()
    return set(ds.name for ds in online_ds)


def _empty_result():
    return {"nodes": [], "links": [], "clusters": [], "stats": {
        "total": 0, "by_type": {}, "abnormal_count": 0, "link_count": 0, "cluster_count": 0
    }, "trees": []}


def build_k8s_topo_graph(db: Session, cluster_name: str = "", namespace: str = ""):
    """构建 K8s 多维关系图：ownership 层级 + 弱引用关系 + 孤岛标记 + Pod 实时视图聚合。

    三层纳管模型（参考 ServiceNow Dynamic CI / OpenTelemetry 资源稳定性分层）:
      - 持久化 CI: cluster/node/namespace/deploy/sts/ds/service/ingress/pv/pvc
      - 弱纳管 CI: configmap/secret（带 referenced_by / orphan 标记）
      - 实时视图: pod/replicaset 不入库，Pod 概要聚合到工作负载 attrs.pod_summary

    关系类型:
      - owns:        父子归属（cluster→namespace→deployment）
      - references:  弱引用（deployment→configmap/secret/pvc，基于 attrs.referenced_by 反查）
      - selects:     Service selector → Deployment（基于 selector 匹配 deployment 标签）
    孤岛标记: configmap/secret/pvc 的 attrs.orphan=true 时节点标记 abnormal

    参数:
      cluster_name: 可选，按集群名筛选（精确匹配）
      namespace:    可选，按命名空间筛选（模糊匹配）
    """
    # 仅显示已在线集群的资源
    online_clusters = _get_online_cluster_names(db)
    if not online_clusters:
        return _empty_result()

    # 排除 deprecated（旧 pod/replicaset 记录已降级）
    container_types = ["kubernetes_cluster", "namespace", "node",
                       "deployment", "statefulset", "daemonset",
                       "service", "ingress", "pvc", "pv",
                       "configmap", "secret"]
    all_assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).all()
    all_assets = [a for a in all_assets if a.status != "deprecated"]

    # 只保留在线集群的资产（k8s_cluster 字段匹配 online_clusters 中的名称）
    all_assets = [a for a in all_assets if a.k8s_cluster in online_clusters]

    # 按集群名筛选
    if cluster_name:
        all_assets = [a for a in all_assets if a.k8s_cluster == cluster_name]

    # 只保留：1）kubernetes_cluster/cluster 根节点 2）有 parent_id 且父级在集合中的后代
    all_clusters = [a for a in all_assets if a.ci_type == "kubernetes_cluster"]
    # 按集群名去重：同名 cluster 只保留子资产最多的那个（防止重复纳管导致统计翻倍）
    _root_by_name = {}
    for c in all_clusters:
        key = c.name
        cnt = sum(1 for a in all_assets if a.parent_id == c.id)
        if key not in _root_by_name or cnt > sum(1 for a in all_assets if a.parent_id == _root_by_name[key].id):
            _root_by_name[key] = c
    cluster_ids = set(c.id for c in _root_by_name.values())
    valid_ids = set(cluster_ids)
    changed = True
    while changed:
        changed = False
        for a in all_assets:
            if a.id not in valid_ids and a.parent_id and a.parent_id in valid_ids:
                valid_ids.add(a.id)
                changed = True
    assets = [a for a in all_assets if a.id in valid_ids]

    # 按命名空间筛选（解析 ci_attributes 中 namespace 字段）
    # 保留集群/命名空间层级节点，只过滤叶子资源
    if namespace:
        _hierarchy_types = {"kubernetes_cluster", "namespace"}
        _matched_ids = set()
        for a in assets:
            if a.ci_type in _hierarchy_types:
                continue
            attrs = _parse_attrs(a)
            ns = attrs.get("namespace", "") or ""
            if namespace.lower() in ns.lower():
                _matched_ids.add(a.id)
        if not _matched_ids:
            return _empty_result()
        # 反向传播：从匹配的叶子往根走，保留父级路径
        _keep_ids = set(_matched_ids)
        _changed = True
        while _changed:
            _changed = False
            for a in assets:
                if a.id in _keep_ids and a.parent_id and a.parent_id not in _keep_ids:
                    _keep_ids.add(a.parent_id)
                    _changed = True
        assets = [a for a in assets if a.id in _keep_ids]

    asset_map = {}
    nodes = []
    # name → id 索引（用于弱引用反查：referenced_by 中的 deployment name → asset id）
    full_name_to_id = {}
    for a in assets:
        attrs = _parse_attrs(a)
        asset_map[a.id] = {"asset": a, "attrs": attrs}
        full_name_to_id[a.name] = a.id
        ci_type = a.ci_type
        # 异常标记：orphan 资源 / 工作负载 pod 概要异常 / status offline
        is_abnormal = False
        if attrs.get("orphan"):
            is_abnormal = True
        if ci_type in ("deployment", "statefulset", "daemonset"):
            ps = attrs.get("pod_summary") or {}
            if ps.get("failed", 0) > 0 or (ps.get("total", 0) > 0 and ps.get("running", 0) == 0):
                is_abnormal = True
        elif a.status == "offline":
            is_abnormal = True
        nodes.append({
            "id": a.id,
            "name": a.name.split("/")[-1] if "/" in a.name else a.name,
            "full_name": a.name,
            "ci_type": ci_type,
            "status": a.status,
            "cluster": a.k8s_cluster or attrs.get("k8s_cluster", ""),
            "attrs": attrs,
            "abnormal": is_abnormal,
            "orphan": bool(attrs.get("orphan")),
            "parent_id": a.parent_id,
        })

    links = []
    seen_edges = set()

    def _add_edge(source_id, target_id, rel_type):
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

    # 2. 弱引用关系：configmap/secret/pvc 的 attrs.referenced_by → deployment
    #    referenced_by 存的是 deployment 简短 name，构造完整 name 匹配 asset
    for a in assets:
        if a.ci_type not in ("configmap", "secret", "pvc"):
            continue
        attrs = asset_map[a.id]["attrs"]
        ns = attrs.get("namespace", "")
        refs = attrs.get("referenced_by", [])
        cluster_name = attrs.get("k8s_cluster", "") or a.k8s_cluster or ""
        for ref_name in refs:
            if not ref_name or ref_name == "?":
                continue
            # 构造 deployment 的完整 name: {cluster}/{ns}/{deploy_name}
            candidate = f"{cluster_name}/{ns}/{ref_name}"
            dep_id = full_name_to_id.get(candidate)
            if dep_id:
                # 边方向：deployment → configmap（deployment 引用了 configmap）
                _add_edge(dep_id, a.id, "references")

    # 3. service → deployment selector 关联
    #    service attrs.selector 匹配 deployment 名称（简化：deployment 名包含 selector value）
    dep_by_ns = {}
    for a in assets:
        if a.ci_type in ("deployment", "statefulset", "daemonset"):
            ns = asset_map[a.id]["attrs"].get("namespace", "")
            dep_by_ns.setdefault(ns, []).append(a)
    for a in assets:
        if a.ci_type != "service":
            continue
        svc_attrs = asset_map[a.id]["attrs"]
        selector = svc_attrs.get("selector", {})
        svc_ns = svc_attrs.get("namespace", "")
        if not selector:
            continue
        for dep in dep_by_ns.get(svc_ns, []):
            # 退化策略：selector app=xxx → deployment 名含 xxx
            selector_vals = [str(v) for v in selector.values()]
            dep_short = dep.name.split("/")[-1] if "/" in dep.name else dep.name
            if any(v and v in dep_short for v in selector_vals):
                _add_edge(a.id, dep.id, "selects")

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
    roots = [n for n in nodes if n["ci_type"] == "kubernetes_cluster"]

    # 构建 parent_id 索引
    by_parent = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid:
            by_parent.setdefault(pid, []).append(n)

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

    # 按语义分层构建树（三层纳管：cluster→namespace→[workload|service|弱引用CI]）
    def _node_obj(n):
        return {
            "id": n["id"], "name": n["name"],
            "full_name": n.get("full_name", ""),
            "ci_type": n["ci_type"],
            "status": n["status"],
            "cluster": n.get("cluster", ""),
            "attrs": n.get("attrs", {}),
            "abnormal": n.get("abnormal", False),
            "orphan": n.get("orphan", False),
            "children": [],
        }

    def build_semantic_tree():
        tree_roots = []
        for root in roots:
            cluster_id = root["id"]
            ns_nodes = [n for n in nodes if n["ci_type"] == "namespace" and n.get("parent_id") == cluster_id]
            ns_list = []
            for ns in ns_nodes:
                ns_id = ns["id"]
                # 工作负载（Pod 概要在 attrs.pod_summary，不再有 pod 子节点）
                deps = [n for n in nodes if n["ci_type"] in ("deployment", "statefulset", "daemonset")
                        and (n.get("parent_id") == ns_id or find_ns_for(n) == ns_id)]
                # Service / Ingress
                svcs = [n for n in nodes if n["ci_type"] in ("service", "ingress")
                        and (n.get("parent_id") == ns_id or find_ns_for(n) == ns_id)]
                # 弱纳管 CI（configmap/secret/pvc），含孤岛标记
                weak = [n for n in nodes if n["ci_type"] in ("configmap", "secret", "pvc")
                        and (n.get("parent_id") == ns_id or find_ns_for(n) == ns_id)]
                children = [_node_obj(n) for n in deps + svcs + weak]
                ns_list.append(_node_obj(ns) | {"children": children})
            tree_roots.append(_node_obj(root) | {"children": ns_list})
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
    assets = db.query(Asset).order_by(Asset.ci_type, Asset.name).all()
    relations = db.query(AssetRelation).all()
    asset_map = {a.id: {"id": a.id, "name": a.name, "type": a.ci_type, "ci_type": a.ci_type, "status": a.status} for a in assets}
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
    return trees


def build_container_topo(db: Session):
    container_types = ["kubernetes_cluster", "namespace", "node", "deployment", "statefulset", "daemonset",
                       "service", "ingress", "pvc", "pv", "configmap", "secret", "container"]
    assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).order_by(Asset.ci_type, Asset.name).all()
    assets = [a for a in assets if a.status != "deprecated"]
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

