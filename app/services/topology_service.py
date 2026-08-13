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


def build_service_call_topo(db: Session, hours: int = 168, min_calls: int = 1):
    """从 Span 表聚合服务调用链拓扑（服务 A → 服务 B 有向边）。

    通过 trace_id + parent_span_id 还原调用关系，筛选跨服务调用后聚合：
    - 节点: 每个 service_name 为一个服务节点，附带该服务的调用量/错误数/平均耗时/健康状态
    - 边:  caller → callee, 附带调用量/错误数/平均耗时/错误率
    hours=0 表示不限时间范围。
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from collections import defaultdict
    from app.models import Span

    q = db.query(Span)
    if hours and hours > 0:
        since = datetime.now() - timedelta(hours=hours)
        q = q.filter(Span.started_at >= since)
    spans = q.all()
    if not spans:
        return _empty_service_call_result()

    span_map = {}
    for s in spans:
        if s.trace_id is None:
            continue
        span_map.setdefault(s.trace_id, []).append(s)

    caller_map = defaultdict(lambda: {"count": 0, "error_count": 0, "total_duration": 0.0})
    svc_stats = defaultdict(lambda: {"call_count": 0, "error_count": 0, "total_duration": 0.0, "span_count": 0})

    for tid, trace_spans in span_map.items():
        ss_map = {s.span_id: s for s in trace_spans if s.span_id}
        for s in trace_spans:
            svc = s.service_name or "unknown"
            svc_stats[svc]["span_count"] += 1
            if s.duration_ms:
                svc_stats[svc]["total_duration"] += s.duration_ms
            if s.status and s.status != "OK":
                svc_stats[svc]["error_count"] += 1
            if not s.parent_span_id:
                continue
            parent = ss_map.get(s.parent_span_id)
            if parent and parent.service_name and parent.service_name != s.service_name:
                caller = parent.service_name
                callee = s.service_name
                key = (caller, callee)
                caller_map[key]["count"] += 1
                caller_map[key]["error_count"] += 1 if s.status and s.status != "OK" else 0
                if s.duration_ms:
                    caller_map[key]["total_duration"] += s.duration_ms
                svc_stats[caller]["call_count"] += 1
                if s.status and s.status != "OK":
                    svc_stats[caller]["error_count"] += 1

    nodes = []
    edge_ids = set()
    edges = []
    for svc, stat in svc_stats.items():
        avg_dur = round(stat["total_duration"] / max(stat["span_count"], 1), 1)
        error_rate = round(stat["error_count"] / max(stat["span_count"], 1) * 100, 1)
        health = "critical" if error_rate >= 30 else ("warning" if error_rate >= 5 else "healthy")
        nodes.append({
            "id": svc,
            "name": svc,
            "type": "service",
            "call_count": stat["call_count"],
            "span_count": stat["span_count"],
            "error_count": stat["error_count"],
            "avg_duration_ms": avg_dur,
            "error_rate": error_rate,
            "health": health,
        })

    for (caller, callee), stat in caller_map.items():
        if stat["count"] < min_calls:
            continue
        avg_dur = round(stat["total_duration"] / max(stat["count"], 1), 1)
        error_rate = round(stat["error_count"] / max(stat["count"], 1) * 100, 1)
        eid = f"{caller}→{callee}"
        if eid in edge_ids:
            continue
        edge_ids.add(eid)
        edges.append({
            "id": eid,
            "source": caller,
            "target": callee,
            "type": "service_call",
            "call_count": stat["count"],
            "error_count": stat["error_count"],
            "avg_duration_ms": avg_dur,
            "error_rate": error_rate,
        })

    stats = {
        "total_services": len(nodes),
        "total_edges": len(edges),
        "total_calls": sum(e["call_count"] for e in edges),
        "total_spans": sum(s["span_count"] for s in nodes),
        "hours": hours,
    }
    return {"nodes": nodes, "edges": edges, "stats": stats}


def _empty_service_call_result():
    return {"nodes": [], "edges": [], "stats": {
        "total_services": 0, "total_edges": 0, "total_calls": 0, "total_spans": 0, "hours": 0
    }}


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


# ============================================================
# 拓扑视图大改（2026-07-25）
# Tab1: 全资产拓扑（K8s 仅保留 cluster + node 维度，过滤其余 K8s 子资源）
# Tab2: 网络拓扑（双模式：网络设备关系 / IP 网段聚类）
# ============================================================

# K8s 子资源过滤清单：Tab1 中不显示这些 ci_type（资源纳管粒度收敛到 Node 维度）
K8S_CHILD_FILTER = {
    "namespace", "deployment", "statefulset", "daemonset",
    "service", "ingress", "pvc", "pv", "configmap", "secret",
    "pod", "replicaset", "container", "job", "cronjob", "hpa",
}

# 网络类设备 ci_type（Tab2 网络设备关系模式）
NETWORK_DEVICE_TYPES = {
    "network", "network_device", "switch", "router", "firewall",
    "loadbalancer", "load_balancer", "storage", "storage_device",
}


def build_asset_topo_by_node(db: Session):
    """Tab1: 全资产拓扑，K8s 仅保留 cluster + node 维度。

    资源纳管粒度收敛（CI Roll-up）：将细粒度 K8s CI（Pod/Deployment/Service/...）
    过滤，拓扑呈现层只保留 kubernetes_cluster 与 node 两个层级，降低拓扑噪声。
    非 K8s 资产（server/vm/database/middleware/网络设备等）全部正常显示。
    """
    assets = db.query(Asset).order_by(Asset.ci_type, Asset.name).all()
    # 过滤 K8s 子资源（保留 kubernetes_cluster / node）
    assets = [a for a in assets if a.ci_type not in K8S_CHILD_FILTER]
    keep_ids = set(a.id for a in assets)

    relations = db.query(AssetRelation).all()
    # 仅保留两端均在过滤后集合中的关系
    relations = [r for r in relations if r.parent_id in keep_ids and r.child_id in keep_ids]

    nodes = [{
        "id": a.id,
        "name": a.name,
        "type": a.ci_type,
        "ci_type": a.ci_type,
        "status": a.status,
        "parent_id": getattr(a, "parent_id", None),
        "ip": a.ip or "",
        "k8s_cluster": getattr(a, "k8s_cluster", None) or "",
    } for a in assets]
    edges = [{
        "id": r.id,
        "source_id": r.parent_id,
        "target_id": r.child_id,
        "relation_type": r.relation_type,
    } for r in relations]

    from collections import Counter
    type_counter = Counter(a.ci_type for a in assets)
    stats = {
        "total": len(nodes),
        "by_type": dict(type_counter),
        "edge_count": len(edges),
        "k8s_hidden": sum(1 for a in db.query(Asset).all() if a.ci_type in K8S_CHILD_FILTER),
    }
    return {"nodes": nodes, "edges": edges, "relations": edges, "stats": stats}


def _subnet_of(ip: str) -> str:
    """解析 IPv4 的 /24 网段（前三段 + .0/24）。非法 IP 返回空串。"""
    if not ip:
        return ""
    s = ip.strip().split("/")
    head = s[0]
    parts = head.split(".")
    if len(parts) < 3:
        return ""
    try:
        int(parts[0]); int(parts[1]); int(parts[2])
    except ValueError:
        return ""
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def build_network_topo(db: Session, mode: str = "devices"):
    """Tab2: 网络拓扑图。

    mode="devices": 网络设备关系拓扑——仅展示网络类设备及其 AssetRelation 连接。
    mode="subnets": IP 网段拓扑——解析所有有 IP 资产的 /24 网段，网段为父节点，
                    资产为叶子，呈现网段→资产的隶属关系。
    """
    if mode == "subnets":
        assets = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").all()
        subnet_nodes = {}  # subnet -> {"id": "subnet:xxx", "name": xxx, "items": [...]}
        node_id_seq = 0
        graph_nodes = []
        graph_edges = []
        for a in assets:
            subnet = _subnet_of(a.ip or "")
            if not subnet:
                continue
            if subnet not in subnet_nodes:
                node_id_seq -= 1
                subnet_nodes[subnet] = {
                    "id": f"subnet:{subnet}",
                    "_id": node_id_seq,
                    "name": subnet,
                    "ci_type": "subnet",
                    "count": 0,
                }
                graph_nodes.append({
                    "id": str(node_id_seq),
                    "name": subnet,
                    "ci_type": "subnet",
                    "status": "",
                    "ip": "",
                    "is_subnet": True,
                    "item_count": 0,
                })
            sn = subnet_nodes[subnet]
            sn["count"] += 1
            # 资产节点
            graph_nodes.append({
                "id": str(a.id),
                "name": a.name,
                "ci_type": a.ci_type,
                "status": a.status,
                "ip": a.ip or "",
                "is_subnet": False,
                "subnet": subnet,
            })
            # 网段 -> 资产
            graph_edges.append({
                "source_id": sn["_id"],
                "target_id": a.id,
                "relation_type": "belongs_to_subnet",
            })
        # 回填网段节点的 item_count
        for n in graph_nodes:
            if n.get("is_subnet"):
                n["item_count"] = subnet_nodes[n["name"]]["count"]
        from collections import Counter
        type_counter = Counter(a.ci_type for a in assets)
        stats = {
            "total": len(graph_nodes),
            "subnet_count": len(subnet_nodes),
            "asset_count": len(assets),
            "by_type": dict(type_counter),
            "edge_count": len(graph_edges),
        }
        return {"nodes": graph_nodes, "edges": graph_edges, "relations": graph_edges, "stats": stats, "mode": "subnets"}

    # 默认：网络设备关系
    assets = db.query(Asset).filter(Asset.ci_type.in_(NETWORK_DEVICE_TYPES)).order_by(Asset.ci_type, Asset.name).all()
    keep_ids = set(a.id for a in assets)
    relations = db.query(AssetRelation).all()
    relations = [r for r in relations if r.parent_id in keep_ids and r.child_id in keep_ids]

    nodes = [{
        "id": a.id,
        "name": a.name,
        "type": a.ci_type,
        "ci_type": a.ci_type,
        "status": a.status,
        "ip": a.ip or "",
        "parent_id": getattr(a, "parent_id", None),
    } for a in assets]
    edges = [{
        "id": r.id,
        "source_id": r.parent_id,
        "target_id": r.child_id,
        "relation_type": r.relation_type,
    } for r in relations]

    from collections import Counter
    type_counter = Counter(a.ci_type for a in assets)
    stats = {
        "total": len(nodes),
        "by_type": dict(type_counter),
        "edge_count": len(edges),
        "abnormal_count": sum(1 for a in assets if (a.status or "").lower() in ("offline", "error", "critical", "down")),
    }
    return {"nodes": nodes, "edges": edges, "relations": edges, "stats": stats, "mode": "devices"}

