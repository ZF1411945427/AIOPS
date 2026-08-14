"""架构图自动生成服务: 按业务域生成 draw.io 架构图 (.drawio XML)。

数据来源:
- Asset(资产, 含 name/ci_type/ip/status/health/parent_id/ci_attributes)
- AssetRelation(资产间依赖/路由关系)
- parent_id 父子层级(集群->node/namespace->deployment->pod)

输出:
- build_drawio_xml(): 生成 draw.io 可编辑的 mxGraph XML 字符串
- export_via_drawio(): 用本地 draw.io 桌面命令行走无头导出 PNG/SVG/PDF/JPG
"""

from __future__ import annotations

import os
import subprocess
import time
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.models import Asset, AssetRelation
from app.services.health_engine import _extract_domains

# ── 导出目录约定: 项目根 / generated / architecture ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_ROOT = os.environ.get(
    "AIOPS_ARCH_DIR", str(PROJECT_ROOT / "generated" / "architecture")
)

# ── 分层配置 (对齐 health_engine LAYER_MAP 语义) ──
LAYER_ORDER_DISPLAY = ["1", "2", "3-mq", "3-db", "4", "k8s"]
LAYER_LABELS = {
    "1": "接入层 / Access",
    "2": "应用层 / Application",
    "3-mq": "中间件 / Middleware",
    "3-db": "存储层 / Storage",
    "4": "基础设施 / Infrastructure",
    "k8s": "容器编排 / Kubernetes",
}

# ci_type -> 显示层 (根据 get_layer 的 LAYER_MAP 归并)
CI_LAYER = {
    "api_gateway": "1",
    "loadbalancer": "1",
    "gateway": "1",
    "api": "2",
    "microservice": "2",
    "service": "2",
    "redis": "3-mq",
    "kafka": "3-mq",
    "mq": "3-mq",
    "rabbitmq": "3-mq",
    "zookeeper": "3-mq",
    "mysql": "3-db",
    "postgres": "3-db",
    "database": "3-db",
    "oracle": "3-db",
    "mongo": "3-db",
    "elasticsearch": "3-db",
    "server": "4",
    "node": "4",
    "vm": "4",
    "virtual_machine": "4",
    "host": "4",
    "kubernetes_cluster": "k8s",
    "namespace": "k8s",
    "deployment": "k8s",
    "pod": "k8s",
}

# ci_type -> 节点样式(颜色)
NODE_COLORS = {
    "1": "#fde68a",       # 接入层 黄
    "2": "#93c5fd",       # 应用层 蓝
    "3-mq": "#a5b4fc",    # 中间件 紫
    "3-db": "#fca5a5",    # 存储层 红
    "4": "#cbd5e1",       # 基础设施 灰
    "k8s": "#6ee7b7",     # K8s 绿
}

# 关系类型 -> 连线样式/标签/颜色
RELATION_STYLE = {
    "routes_to": ("#2563eb", "routes"),
    "depends_on": ("#dc2626", "depends"),
    "member_of": ("#059669", "member"),
    "connected_to": ("#7c3aed", "connected"),
}


def _ci_layer(ci_type: str) -> str:
    ct = (ci_type or "").strip().lower()
    if ct in CI_LAYER:
        return CI_LAYER[ct]
    # 回退: 用 health_engine 的 get_layer 语义
    api_layers = {"api_gateway", "loadbalancer", "gateway"}
    app_layers = {"api", "microservice", "service", "application", "app"}
    mq_layers = {"redis", "kafka", "mq", "rabbitmq", "zookeeper", "elasticsearch", "database", "mysql", "postgres", "oracle", "mongo"}
    base_layers = {"server", "node", "vm", "virtual_machine", "host", "kubernetes_cluster", "namespace", "deployment", "pod"}
    if ct in api_layers:
        return "1"
    if ct in app_layers:
        return "2"
    if ct in mq_layers:
        return "3-mq" if ct in {"redis", "kafka", "mq", "rabbitmq", "zookeeper"} else "3-db"
    if ct in base_layers:
        return "4" if ct in {"server", "node", "vm", "virtual_machine", "host"} else "k8s"
    return "4"


def _asset_name(asset: Asset) -> str:
    return asset.name or f"asset-{asset.id}"


def _asset_health_color(health: str) -> str:
    h = (health or "").lower()
    if h in ("red", "critical"):
        return "#ef4444"
    if h in ("warning", "warn"):
        return "#f59e0b"
    if h in ("gray", "offline", "down"):
        return "#9ca3af"
    return "#22c55e"


def collect_domain_assets(db, domain: str) -> List[Asset]:
    """返回指定业务域下的全部资产(与 health_engine.fetch_domains 一致的过滤口径)。"""
    assets = db.query(Asset).all()
    result = []
    for a in assets:
        domains = _extract_domains(a)
        if domain in domains:
            result.append(a)
    return result


def _topo_layers(assets: List[Asset]) -> Dict[str, List[Asset]]:
    """将资产按显示层分组。"""
    layers: Dict[str, List[Asset]] = {k: [] for k in LAYER_ORDER_DISPLAY}
    for a in assets:
        layers[_ci_layer(a.ci_type)].append(a)
    return layers


def _topo_sort_layer(assets: List[Asset], rels: List[Tuple[str, str, str]],
                     layer_key: str, layer_assets: List[Asset],
                     ai_scores: Optional[Dict[str, float]] = None) -> List[Asset]:
    """按拓扑序排列同层节点: 上游多(入口)靠左, 下游多(出口)靠右, 减少连线交叉。

    ai_scores: {asset_id: score}, 若提供则作为主要排序依据(越大越靠左)。
    """
    if len(layer_assets) <= 1:
        return layer_assets
    ids = {str(a.id) for a in layer_assets}
    # 统计上下游
    up = {}  # aid -> set of upstream assets (target = this)
    down = {}  # aid -> set of downstream assets (source = this)
    for a in layer_assets:
        aid = str(a.id)
        up[aid] = set()
        down[aid] = set()
    for ps, cs, _ in rels:
        if ps in ids and cs in ids:
            down[ps].add(cs)
            up[cs].add(ps)
    # 评分: 上游多=偏左(数据源), 下游多=偏右(消费者)
    has_ai = bool(ai_scores) and any(str(a.id) in ai_scores for a in layer_assets)
    scored = []
    for a in layer_assets:
        aid = str(a.id)
        if has_ai:
            score = float(ai_scores.get(aid, 0))
        else:
            # 加权: 上游数正分(偏左), 下游数负分(偏右)
            score = len(up[aid]) * 100 - len(down[aid]) * 100
        scored.append((score, _asset_name(a), a))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in scored]


def _route_waypoints(start, goal, obstacles, margin: float = 14.0):
    """在稀疏网格上求正交最短路, 生成避开矩形障碍物的连线路径点。

    - 网格坐标轴为所有障碍物的左/右/上/下边界 + 起终点坐标
         (经典正交连线布线法: 路径只会发生在这类"走廊"坐标上)
    - 返回中间路径点列表 [(x,y)...], 不含 start/goal 本身; 无法绕行时
         退化为直线 (无中间点)
    obstacles: [(x0,y0,x1,y1), ...] 矩形列表 (将被扩展 margin)
    """
    import heapq

    sx, sy = start
    gx, gy = goal

    obs = []
    for (x0, y0, x1, y1) in obstacles:
        obs.append((x0 - margin, y0 - margin, x1 + margin, y1 + margin))

    xs = sorted({x0 for (x0, _, _, _) in obs} | {x1 for (_, _, x1, _) in obs} | {sx, gx})
    ys = sorted({y0 for (_, y0, _, _) in obs} | {y1 for (_, _, _, y1) in obs} | {sy, gy})

    W = len(xs) - 1
    H = len(ys) - 1

    def cell_blocked(xa, xb, ya, yb):
        for (ox0, oy0, ox1, oy1) in obs:
            if xb > ox0 and ox1 > xa and yb > oy0 and oy1 > ya:
                return True
        return False

    def locate(px, py):
        xi = next((i for i in range(W) if xs[i] <= px <= xs[i + 1]), W - 1)
        yj = next((j for j in range(H) if ys[j] <= py <= ys[j + 1]), H - 1)
        return xi, yj

    si, sj = locate(sx, sy)
    gi, gj = locate(gx, gy)
    if (si, sj) == (gi, gj):
        return []

    dist = {(si, sj): 0.0}
    prev = {}
    heap = [(0.0, si, sj)]
    reached = None
    while heap:
        d, xi, yj = heapq.heappop(heap)
        if d > dist.get((xi, yj), float("inf")):
            continue
        if (xi, yj) == (gi, gj):
            reached = (xi, yj)
            break
        for ni, nj in ((xi + 1, yj), (xi - 1, yj), (xi, yj + 1), (xi, yj - 1)):
            if ni < 0 or nj < 0 or ni >= W or nj >= H:
                continue
            if cell_blocked(xs[ni], xs[ni + 1], ys[nj], ys[nj + 1]):
                continue
            cost = (xs[ni + 1] - xs[ni]) + (ys[nj + 1] - ys[nj])
            nd = d + cost
            if nd < dist.get((ni, nj), float("inf")):
                dist[(ni, nj)] = nd
                prev[(ni, nj)] = (xi, yj)
                heapq.heappush(heap, (nd, ni, nj))

    if reached is None:
        return []

    path_cells = []
    cur = reached
    while cur is not None:
        path_cells.append(cur)
        cur = prev.get(cur)
    path_cells.reverse()

    # 两相邻 cell 的公共边中心作为转向点
    raw = [(sx, sy)]
    for a, b in zip(path_cells, path_cells[1:]):
        ax, ay = a
        bx, by = b
        if ax != bx:
            # 横向移动: 公共边是竖线 x = xs[max(ax,bx)], 经过圆整的 y 走廊(用段内中心 y)
            ex = xs[max(ax, bx)]
            emid_y = ys[min(ay, by)] + (ys[min(ay, by) + 1] - ys[min(ay, by)]) / 2
            raw.append((ex, emid_y))
        else:
            # 纵向移动: 公共边是横线 y = ys[max(ay,by)]
            ey = ys[max(ay, by)]
            exmid = xs[min(ax, bx)] + (xs[min(ax, bx) + 1] - xs[min(ax, bx)]) / 2
            raw.append((exmid, ey))
    raw.append((gx, gy))

    def simplify(pts_):
        if len(pts_) <= 2:
            return pts_
        out = [pts_[0]]
        for p in pts_[1:-1]:
            if (out[-1][0] == p[0] and p[0] == pts_[0]) or (out[-1][1] == p[1] and p[1] == pts_[1]):
                pass
        out = [pts_[0]]
        for i in range(1, len(pts_) - 1):
            p0 = out[-1]
            p1 = pts_[i]
            p2 = pts_[i + 1]
            if (p0[0] == p1[0] and p1[0] == p2[0]) or (p0[1] == p1[1] and p1[1] == p2[1]):
                continue
            out.append(p1)
        out.append(pts_[-1])
        return out

    way = simplify(raw)
    return way[1:-1]


def _route_waypoints_robust(start, goal, obstacles, margin: float = 14.0):
    """带兜底的 _route_waypoints: 任何异常都返回空列表(直线连接)。"""
    try:
        return _route_waypoints(start, goal, obstacles, margin=margin)
    except Exception:
        return []


def _calc_edge_anchor(src_pos, tgt_pos, src_w, src_h, tgt_w, tgt_h,
                      src_idx: int, src_total: int):
    """计算边的 exit/entry 锚点, 避免平行边重叠和穿节点。

    返回 (exitX, exitY, entryX, entryY) 百分比坐标。
    - 平行边: 按 idx/total 分配不同的水平偏移(slot), 沿节点边均匀分布
    - 水平方向: 从左侧/右侧出, 不同垂直槽位
    - 垂直方向: 从底部/顶部出, 不同水平槽位
    """
    sx, sy = src_pos
    tx, ty = tgt_pos
    cx, cy = sx + src_w / 2, sy + src_h / 2
    tx_c, ty_c = tx + tgt_w / 2, ty + tgt_h / 2

    dx = tx_c - cx
    dy = ty_c - cy

    # 平行边槽位: 在 0.2~0.8 之间均匀分配
    if src_total > 1:
        slot = 0.2 + (src_idx / (src_total - 1)) * 0.6
    else:
        slot = 0.5

    # 判断主方向: 水平(H) vs 垂直(V)
    # 水平方向: dx 绝对值显著大于 dy
    if abs(dx) > abs(dy) * 1.2:
        if dx > 0:
            # 目标在右: 从右侧出, 左侧入
            return (1.0, slot, 0.0, slot)
        else:
            # 目标在左: 从左侧出, 右侧入
            return (0.0, slot, 1.0, slot)
    elif abs(dy) > abs(dx) * 1.2:
        # 垂直方向为主
        if dy > 0:
            # 目标在下: 从底部出, 顶部入
            return (slot, 1.0, slot, 0.0)
        else:
            return (slot, 0.0, slot, 1.0)
    else:
        # 混合方向: 用目标所在的象限决定主锚点, 但 slot 依然错开
        if dx >= 0 and dy >= 0:
            return (1.0, slot, 0.0, slot)
        elif dx < 0 and dy >= 0:
            return (0.0, slot, 1.0, slot)
        elif dx >= 0 and dy < 0:
            return (1.0, slot, 0.0, slot)
        else:
            return (0.0, slot, 1.0, slot)


def build_drawio_xml(domain: str, assets: List[Asset], relations: List[AssetRelation],
                     diagram_title: str = "", ai_scores: Optional[Dict[str, float]] = None) -> str:
    """根据资产与关系生成 draw.io 的 mxGraph XML。

    ai_scores: {asset_id: score} 可选。提供时, 同层节点按 AI 评分排序(越大越靠左),
    替代默认的拓扑序评分。适用于 AI 布局规划器 (drawio_ai_planner)。
    """
    # 资产 id -> 名称与信息
    asset_map = {}
    for a in assets:
        asset_map[str(a.id)] = a

    # 只保留两端都在该资产集合内的关系
    valid_ids = set(asset_map.keys())
    rels = []
    for r in relations:
        ps = str(r.parent_id)
        cs = str(r.child_id)
        if ps in valid_ids and cs in valid_ids:
            rels.append((ps, cs, r.relation_type or "depends_on"))

    # 分层
    layers = _topo_layers(assets)
    # 同层内排序(默认拓扑序, 有 AI 评分则用 AI 评分)
    for k in LAYER_ORDER_DISPLAY:
        if layers[k]:
            layers[k] = _topo_sort_layer(assets, rels, k, layers[k], ai_scores=ai_scores)

    # 计算布局: 每层一行, 节点水平等距
    CARD_W = 150
    CARD_H = 46
    GAP_X = 24
    LAYER_GAP = 70
    X0 = 60
    Y0 = 60
    cell_w = CARD_W + GAP_X

    layer_y = {}
    cursor_y = Y0
    for k in LAYER_ORDER_DISPLAY:
        items = layers[k]
        if not items:
            continue
        layer_y[k] = cursor_y
        cursor_y += CARD_H + LAYER_GAP

    # 计算每层最大行宽(用于整体居中)
    max_widths = {}
    for k in LAYER_ORDER_DISPLAY:
        if layers[k]:
            max_widths[k] = len(layers[k]) * cell_w - GAP_X
    if max_widths:
        total_max = max(max_widths.values())
    else:
        total_max = 0

    pos = {}  # asset_id -> (x, y)
    for k in LAYER_ORDER_DISPLAY:
        items = layers[k]
        if not items:
            continue
        n = len(items)
        row_w = n * cell_w - GAP_X
        start_x = X0 + (total_max - row_w) / 2
        for i, a in enumerate(items):
            pos[str(a.id)] = (start_x + i * cell_w, layer_y[k])

    # 预计算每个源节点的平行边分组(用于锚点分配)
    src_edge_count = {}
    for (ps, cs, _) in rels:
        if ps not in valid_ids or cs not in valid_ids:
            continue
        src_edge_count[ps] = src_edge_count.get(ps, 0) + 1
    src_edge_idx = {}
    for ps in src_edge_count:
        src_edge_idx[ps] = 0

    # 生成 XML
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    title = escape(diagram_title or f"{domain} - 系统架构图")
    parts.append('<mxfile host="app.diagrams.net" modified="%s" agent="aiops-arch" version="24.0.0">' % _now_xml())
    parts.append('<diagram id="arch-%s" name="%s">' % (escape(domain), title))
    parts.append('<mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
                 'arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="1200" math="0" shadow="0">')
    parts.append('<root>')
    parts.append('<mxCell id="0" />')
    parts.append('<mxCell id="1" parent="0" />')

    # 图层背景容器(用于标题)
    cell_id = 10
    for k in LAYER_ORDER_DISPLAY:
        items = layers[k]
        if not items:
            continue
        y = layer_y[k]
        w = (len(items) * cell_w - GAP_X)
        bg_id = cell_id
        cell_id += 1
        parts.append(
            '<mxCell id="bg-%s" value="%s" style="rounded=1;whiteSpace=wrap;html=1;fillColor=none;'
            'strokeColor=#e2e8f0;dashed=1;verticalAlign=top;fontStyle=1;fontSize=12;fontColor=#64748b;" '
            'vertex="1" parent="1">'
            '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
            '</mxCell>' % (bg_id, escape(LAYER_LABELS.get(k, k)),
                           int(X0 + (total_max - w) / 2), int(y - 30), int(w), int(CARD_H + 26)))

    # 节点
    node_id_map = {}  # asset_id -> cell id
    for aid, (x, y) in pos.items():
        a = asset_map[aid]
        layer = _ci_layer(a.ci_type)
        color = NODE_COLORS.get(layer, "#cbd5e1")
        health = _asset_health_color(a.health_status)
        label = _asset_name(a)
        info = []
        if a.ip:
            info.append(a.ip)
        if a.status:
            info.append(a.status)
        tooltip = escape(f"{a.ci_type} · {' · '.join(info)}" if info else (a.ci_type or "asset"))
        style = ("rounded=1;whiteSpace=wrap;html=1;fillColor={};strokeColor={};"
                 "fontColor=#1e293b;fontSize=11;".format(color, health))
        cid = cell_id
        cell_id += 1
        node_id_map[aid] = cid
        parts.append(
            '<mxCell id="n%s" value="%s" style="%s" vertex="1" parent="1">'
            '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
            '</mxCell>'
            % (cid, escape(label), style, int(x), int(y), int(CARD_W), int(CARD_H)))

    # 构建所有节点矩形(用于障碍物避开路由)
    node_rects = {}
    for aid, (x, y) in pos.items():
        node_rects[aid] = (x, y, x + CARD_W, y + CARD_H)

    # 关系连线(带锚点+障碍物规避路由)
    for (ps, cs, rtype) in rels:
        if ps not in node_id_map or cs not in node_id_map:
            continue
        color, lbl = RELATION_STYLE.get(rtype, ("#94a3b8", rtype))
        total = src_edge_count.get(ps, 1)
        idx = src_edge_idx.get(ps, 0)
        src_edge_idx[ps] = idx + 1
        exitX, exitY, entryX, entryY = _calc_edge_anchor(
            (pos[ps][0], pos[ps][1]), (pos[cs][0], pos[cs][1]),
            CARD_W, CARD_H, CARD_W, CARD_H, idx, total)
        # 起点/终点在节点边框上的具体坐标
        sx = pos[ps][0] + CARD_W * exitX
        sy = pos[ps][1] + CARD_H * exitY
        gx = pos[cs][0] + CARD_W * entryX
        gy = pos[cs][1] + CARD_H * entryY
        # 障碍物: 排除源和目标节点
        obstacles = [r for aid, r in node_rects.items() if aid != ps and aid != cs]
        wpts = _route_waypoints_robust((sx, sy), (gx, gy), obstacles)
        edge_id = cell_id
        cell_id += 1
        # 构建 geometry 部分(含可选路径点)
        if wpts:
            pts_xml = "".join('<mxPoint x="%s" y="%s"/>' % (int(p[0]), int(p[1])) for p in wpts)
            geom = '<mxGeometry relative="1" as="geometry"><Array as="points">%s</Array></mxGeometry>' % pts_xml
        else:
            geom = '<mxGeometry relative="1" as="geometry"/>'
        parts.append(
            '<mxCell id="e%s" value="%s" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
            'jettySize=auto;html=1;strokeColor=%s;strokeWidth=2;labelBackgroundColor=#ffffff;fontSize=9;'
            'fontColor=%s;exitX=%s;exitY=%s;entryX=%s;entryY=%s;" edge="1" parent="1" source="n%s" target="n%s">'
            '%s</mxCell>'
            % (edge_id, escape(lbl), color, color,
               str(exitX), str(exitY), str(entryX), str(entryY),
               node_id_map[ps], node_id_map[cs], geom))

    # 父子归属线(parent_id -> 父资产). 忽略 parent_id in (0, None) 或父不在集合内
    for aid, (x, y) in pos.items():
        a = asset_map[aid]
        pid = a.parent_id
        if pid is None or int(pid) == 0:
            continue
        pid_str = str(pid)
        if pid_str not in node_id_map:
            continue
        parent = asset_map.get(pid_str)
        if parent is None:
            continue
        parent_cid = node_id_map[pid_str]
        child_cid = node_id_map[aid]
        # 避免与关系线重复(同源同目标)
        if (pid_str, aid) in {(ps, cs) for (ps, cs, _) in rels}:
            continue
        edge_id = cell_id
        cell_id += 1
        label = "in"
        # 归属线: 从父底部出, 从子顶部入
        exitX, exitY, entryX, entryY = 0.5, 1.0, 0.5, 0.0
        sx = pos[pid_str][0] + CARD_W * exitX
        sy = pos[pid_str][1] + CARD_H * exitY
        gx = pos[aid][0] + CARD_W * entryX
        gy = pos[aid][1] + CARD_H * entryY
        obstacles = [r for aid2, r in node_rects.items() if aid2 != pid_str and aid2 != aid]
        wpts = _route_waypoints_robust((sx, sy), (gx, gy), obstacles)
        if wpts:
            pts_xml = "".join('<mxPoint x="%s" y="%s"/>' % (int(p[0]), int(p[1])) for p in wpts)
            geom = '<mxGeometry relative="1" as="geometry"><Array as="points">%s</Array></mxGeometry>' % pts_xml
        else:
            geom = '<mxGeometry relative="1" as="geometry"/>'
        parts.append(
            '<mxCell id="h%s" value="%s" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
            'jettySize=auto;html=1;strokeColor=#64748b;strokeWidth=1.5;dashed=1;labelBackgroundColor=#ffffff;'
            'fontSize=8;fontColor=#64748b;endArrow=open;exitX=%s;exitY=%s;entryX=%s;entryY=%s;" edge="1" '
            'parent="1" source="n%s" target="n%s">'
            '%s</mxCell>'
            % (edge_id, escape(label), str(exitX), str(exitY), str(entryX), str(entryY),
               parent_cid, child_cid, geom))

    parts.append('</root>')
    parts.append('</mxGraphModel>')
    parts.append('</diagram>')
    parts.append('</mxfile>')

    return "\n".join(parts)


def _now_xml() -> str:
    t = time.time()
    import datetime
    dt = datetime.datetime.fromtimestamp(t)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def render_meta(domain: str, assets: List[Asset], relations: List[AssetRelation]) -> dict:
    """返回生成图的元信息(供前端展示/调试)。"""
    layers = _topo_layers(assets)
    return {
        "domain": domain,
        "asset_count": len(assets),
        "relation_count": len([r for r in relations]),
        "layers": {k: [a.name or f"asset-{a.id}" for a in vs] for k, vs in layers.items() if vs},
        "ci_types": sorted({(a.ci_type or "") for a in assets}),
        "health": {a.name or f"asset-{a.id}": (a.health_status or "green") for a in assets},
    }


def ensure_export_dir() -> Path:
    d = Path(EXPORT_ROOT)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_drawio_file(xml: str, filename: str) -> Path:
    """将 XML 写入导出目录, 返回文件路径。"""
    d = ensure_export_dir()
    p = d / filename
    p.write_text(xml, encoding="utf-8")
    return p


def export_via_drawio(drawio_path: str, drawio_file: Path, fmt: str = "png",
                      out_dir: Optional[Path] = None, timeout: int = 120) -> Tuple[bool, str, Optional[Path]]:
    """调用本地 draw.io 桌面命令行走无头导出。

    返回 (success, message, output_path)。
    """
    fmt = (fmt or "png").lower().lstrip(".")
    if fmt not in ("png", "svg", "pdf", "jpg"):
        return False, f"不支持的导出格式: {fmt}", None
    if not drawio_path or not Path(drawio_path).exists():
        return False, f"draw.io 路径不存在: {drawio_path}", None
    if not drawio_file.exists():
        return False, f"待导出的 .drawio 文件不存在: {drawio_file}", None

    out = out_dir or ensure_export_dir()
    out_f = out / f"{drawio_file.stem}.{fmt}"

    cmd = [drawio_path, "--export", "--format", fmt, "--output", str(out_f), str(drawio_file)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        return False, f"无法执行 draw.io: {drawio_path}", None
    except subprocess.TimeoutExpired:
        return False, f"导出超时({timeout}s): {drawio_path}", None
    except Exception as ex:  # pragma: no cover
        return False, f"导出异常: {ex}", None

    if proc.returncode != 0:
        msg = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        return False, f"draw.io 导出失败(exit={proc.returncode}): {msg[:500]}", None
    if not out_f.exists():
        return False, f"导出完成但未找到输出文件: {out_f}", None
    return True, f"导出成功: {out_f.name}", out_f
