import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, text, distinct
from app.template_utils import get_templates

from app.database import get_db
from app.models import MetricRecord, MetricDashboardCard, AlertRule
from app.services import metric_service, asset_service
from app.services import metric_v2_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/metrics", tags=["metrics"])
templates = get_templates()

CATEGORIES = [
    {"key": "cpu", "label": "CPU / 负载", "icon": "⚡", "pattern": r"cpu|loadavg|uptime"},
    {"key": "memory", "label": "内存", "icon": "🧠", "pattern": r"memory|swap"},
    {"key": "disk", "label": "磁盘", "icon": "💿", "pattern": r"^disk"},
    {"key": "network", "label": "网络", "icon": "📥", "pattern": r"net_|network|tcp_"},
    {"key": "system", "label": "系统", "icon": "⚙️", "pattern": r"process_|zombie|open_files|uptime"},
    {"key": "connection", "label": "应用连接", "icon": "🔌", "pattern": r"ssh_conn|http_conn|mysql_conn|_connections"},
    {"key": "docker", "label": "Docker", "icon": "🐳", "pattern": r"docker"},
    {"key": "k8s", "label": "Kubernetes", "icon": "☸️", "pattern": r"deployment|node_|pod_"},
]


def _categorize(metric_names, latest_values=None):
    """Group metric names into categories, with 'other' catch-all. Sorts data-first."""
    if latest_values is None:
        latest_values = {}
    cat_map = {}
    other = []
    for m in metric_names:
        matched = False
        for cat in CATEGORIES:
            if re.search(cat["pattern"], m, re.I):
                cat_map.setdefault(cat["key"], []).append(m)
                matched = True
                break
        if not matched:
            other.append(m)
    for key in cat_map:
        cat_map[key].sort(key=lambda n: (0 if n in latest_values else 1, n))
    if other:
        other.sort(key=lambda n: (0 if n in latest_values else 1, n))
        cat_map["other"] = other
    return cat_map


@router.get("/data")
def metrics_data(asset_id: int = 0, name: str = "", hours: float = 1, db: Session = Depends(get_db)):
    """Return recent metric records (limited, fast)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    MR = MetricRecord
    q = db.query(MR.name, MR.asset_id, MR.value, MR.unit, MR.timestamp).filter(MR.timestamp >= since)
    if asset_id:
        q = q.filter(MR.asset_id == asset_id)
    if name:
        q = q.filter(MR.name == name)
    rows = q.order_by(MR.timestamp.desc()).limit(50000).all()
    return JSONResponse([
        {"time": r.timestamp.isoformat(), "value": r.value, "name": r.name, "asset_id": r.asset_id, "unit": r.unit}
        for r in rows
    ])


@router.get("/latest")
def metrics_latest(asset_id: int = 0, db: Session = Depends(get_db)):
    """Return latest value per metric name (optimized)."""
    since = datetime.utcnow() - timedelta(hours=24)
    MR = MetricRecord
    # Subquery to get max timestamp per metric name
    sub = db.query(
        MR.name,
        func.max(MR.timestamp).label("max_ts")
    ).filter(MR.timestamp >= since)
    if asset_id:
        sub = sub.filter(MR.asset_id == asset_id)
    sub = sub.group_by(MR.name).subquery()

    # Join to get full record for each latest timestamp
    q = db.query(MR).join(sub, (MR.name == sub.c.name) & (MR.timestamp == sub.c.max_ts))
    if asset_id:
        q = q.filter(MR.asset_id == asset_id)
    rows = q.all()
    latest = {}
    for r in rows:
        latest[r.name] = {"value": r.value, "unit": r.unit, "asset_id": r.asset_id, "timestamp": r.timestamp.isoformat() if r.timestamp else ""}
    return JSONResponse(latest)


@router.get("/names")
def metrics_names(db: Session = Depends(get_db)):
    """Return distinct metric names."""
    rows = db.query(MetricRecord.name).distinct().all()
    return JSONResponse(sorted([r[0] for r in rows]))


# === VictoriaMetrics v2 查询接口 ===

@router.get("/api/v2/query")
def metrics_v2_query(q: str = "", asset_id: int = 0):
    """执行 PromQL 查询，返回 VM 查询结果."""
    if not q:
        return JSONResponse({"error": "q 参数必填"}, status_code=400)
    if asset_id > 0:
        q = f'{q}{{asset_id="{asset_id}"}}'
    result = metric_v2_service.query_promql(q)
    return JSONResponse(result)


@router.get("/api/v2/latest")
def metrics_v2_latest(asset_id: int = 0, aggregate: str = ""):
    """查询最新指标值（走 VM）。

    - asset_id=0 + aggregate=avg|sum|max|min: 跨资产聚合值
    - asset_id>0: 返回该资产的最新值
    - asset_id=0 且无 aggregate: 兼容旧行为(返回最后一条)
    """
    if asset_id == 0 and aggregate:
        latest = metric_v2_service.query_latest_aggregated(aggregate=aggregate)
    else:
        latest = metric_v2_service.query_latest_values(asset_id=asset_id if asset_id else None)
    return JSONResponse(latest)


@router.get("/api/v2/range")
def metrics_v2_range(asset_id: int = 0, name: str = "", hours: int = 24, aggregate: str = ""):
    """查询指标历史范围数据（走 VM）。

    - asset_id=0 + aggregate=avg|sum|max|min: 返回 {avg, series} 聚合+明细叠加
    - asset_id>0: 返回该资产的时间序列
    - asset_id=0 且无 aggregate: 返回所有资产数据
    """
    if asset_id == 0 and aggregate:
        if name:
            return JSONResponse(metric_v2_service.query_range_aggregated(name, aggregate=aggregate, hours=hours))
        names = metric_v2_service.query_metric_names()
        merged = {"avg": [], "series": []}
        seen_avg = set()
        seen_series = {}
        for n in names:
            r = metric_v2_service.query_range_aggregated(n, aggregate=aggregate, hours=hours)
            for pt in r.get("avg", []):
                k = pt["time"]
                if k not in seen_avg:
                    merged["avg"].append(pt)
                    seen_avg.add(k)
            for s in r.get("series", []):
                sk = s["asset_id"]
                if sk not in seen_series:
                    seen_series[sk] = s
                    merged["series"].append(s)
        merged["avg"].sort(key=lambda x: x["time"])
        return JSONResponse(merged)
    if name:
        data = metric_v2_service.query_range_data(asset_id=asset_id, name=name, hours=hours)
        return JSONResponse(data)
    names = metric_v2_service.query_metric_names()
    all_data = []
    for n in names:
        all_data.extend(metric_v2_service.query_range_data(asset_id=asset_id, name=n, hours=hours))
    return JSONResponse(all_data)


@router.get("/api/v2/range-all")
def metrics_v2_range_all(hours: int = 24, aggregate: str = "avg"):
    """跨资产聚合最近 hours 内所有指标的范围数据，返回 {name: {avg, series}}（前端聚合卡片用）"""
    names = metric_v2_service.query_metric_names()
    result = {}
    for n in names:
        r = metric_v2_service.query_range_aggregated(n, aggregate=aggregate, hours=hours)
        result[n] = r
    return JSONResponse(result)


@router.post("/api/v2/custom-query")
def metrics_v2_custom_query(body: dict):
    """执行自定义 PromQL 查询.

    body: {"promql": "...", "hours": 24}
    """
    promql = body.get("promql", "").strip()
    if not promql:
        return JSONResponse({"error": "promql 必填", "series": []}, status_code=400)
    hours = int(body.get("hours", 24))
    result = metric_v2_service.query_custom_promql(promql, hours=hours)
    return JSONResponse(result)


@router.get("/api/v2/names")
def metrics_v2_names():
    """查询 VM 中所有指标名."""
    names = metric_v2_service.query_metric_names()
    return JSONResponse(sorted(names))


@router.get("/api/v2/status")
def metrics_v2_status():
    """查询 VM 健康状态."""
    available = metric_v2_service.is_vm_available()
    return JSONResponse({"available": available, "url": metric_v2_service.VM_URL})


# === 自定义仪表盘卡片持久化 ===
@router.get("/api/cards")
def list_cards(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 0)
    cards = db.query(MetricDashboardCard).filter(
        MetricDashboardCard.user_id == user_id
    ).order_by(MetricDashboardCard.order.asc()).all()
    return JSONResponse([{
        "id": c.id, "title": c.title, "promql": c.promql,
        "hours": c.hours, "w": c.w, "h": c.h, "order": c.order,
    } for c in cards])


@router.post("/api/cards")
def create_card(request: Request, body: dict, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 0)
    card = MetricDashboardCard(
        user_id=user_id,
        title=body.get("title", ""),
        promql=body.get("promql", ""),
        hours=body.get("hours", 24),
        w=body.get("w", 2),
        h=body.get("h", 1),
        order=body.get("order", 0),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return JSONResponse({"ok": True, "id": card.id})


@router.put("/api/cards/{card_id}")
def update_card(card_id: int, request: Request, body: dict, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 0)
    card = db.query(MetricDashboardCard).filter(
        MetricDashboardCard.id == card_id,
        MetricDashboardCard.user_id == user_id
    ).first()
    if not card:
        return JSONResponse({"error": "卡片不存在"}, status_code=404)
    for k in ("title", "promql", "hours", "w", "h", "order"):
        if k in body:
            setattr(card, k, body[k])
    db.commit()
    return JSONResponse({"ok": True})


@router.delete("/api/cards/{card_id}")
def delete_card(card_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 0)
    card = db.query(MetricDashboardCard).filter(
        MetricDashboardCard.id == card_id,
        MetricDashboardCard.user_id == user_id
    ).first()
    if not card:
        return JSONResponse({"error": "卡片不存在"}, status_code=404)
    db.delete(card)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/quick-create-rule")
def quick_create_rule(body: dict, db: Session = Depends(get_db)):
    """从指标卡片快捷创建告警规则"""
    rule = AlertRule(
        name=body.get("name", ""),
        metric_name=body.get("metric_name", ""),
        condition=body.get("condition", ">"),
        threshold=body.get("threshold", 80),
        severity=body.get("severity", "warning"),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return JSONResponse({"ok": True, "rule_id": rule.id})


@router.get("/api/export-csv")
def export_metrics_csv(asset_id: int = 0, hours: int = 24, db: Session = Depends(get_db)):
    """导出指标数据为 CSV"""
    import csv, io
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=hours)
    MR = MetricRecord
    q = db.query(MR).filter(MR.timestamp >= since)
    if asset_id:
        q = q.filter(MR.asset_id == asset_id)
    rows = q.order_by(MR.timestamp.desc()).limit(50000).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "asset_id", "value", "unit", "timestamp"])
    for r in rows:
        writer.writerow([r.name, r.asset_id, r.value, r.unit, r.timestamp.isoformat() if r.timestamp else ""])
    return JSONResponse({"ok": True, "csv": output.getvalue()})


@router.post("/api/analyze")
async def metrics_ai_analyze(request: Request, db: Session = Depends(get_db)):
    """AI 指标健康体检：把全量指标最新值交给 LLM 分析超阈值/恶化趋势。

    body: {
      "metrics": [{"name": "cpu_usage", "value": 85.3, "unit": "%", "asset_id": 1, "aggregate": "avg"}],
      "question": "可选，自定义分析诉求"
    }
    返回: {ok, analysis, provider, metric_count}
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体格式错误"}, status_code=400)

    metrics = body.get("metrics") or []
    question = (body.get("question") or "").strip()
    if not metrics:
        return JSONResponse({"error": "请先加载指标数据"}, status_code=400)
    if len(metrics) > 200:
        return JSONResponse({"error": "单次最多分析 200 项指标"}, status_code=400)

    # 取默认 AI Provider
    from app.models import AgentConfig, AIProvider
    from app.services.agent_service import call_llm
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).order_by(AgentConfig.id.asc()).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        from app.services.ai_provider_health import select_healthy_provider
        _all = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
        _sel, _cand, _skip = select_healthy_provider(_all)
        provider = _sel or (_all[0] if _all else None)
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置可用的 AI 模型提供商，请在 AI 设置中配置并启用一个"})

    # 组装指标文本
    lines = []
    for i, m in enumerate(metrics[:200], 1):
        name = m.get("name") or "?"
        value = m.get("value")
        unit = m.get("unit") or ""
        aid = m.get("asset_id")
        agg = m.get("aggregate") or ""
        try:
            value_s = f"{float(value):.2f}" if value is not None else "-"
        except (TypeError, ValueError):
            value_s = str(value) if value is not None else "-"
        parts = [f"{i}. {name} = {value_s} {unit}".rstrip()]
        if aid:
            parts.append(f" (asset_id={aid})")
        if agg:
            parts.append(f" [跨资产{agg}]")
        lines.append("".join(parts))

    sys_prompt = (
        "你是一名资深 SRE 运维专家，精通主机/应用/容器/K8s 资源指标解读与容量评估。"
        f"用户从指标监控页提交了 {len(lines)} 项指标的最新值（可能含跨资产聚合值）请求体检。"
        "请输出结构化分析：\n"
        "1. **健康总评**：整体资源健康度一句话结论（正常/需关注/高危）\n"
        "2. **异常指标**：列出明显异常或超阈值的指标（CPU>85%、内存>90%、磁盘>80%、网络丢包/连接数激增等），说明风险\n"
        "3. **恶化趋势**：结合常识判断哪些指标可能持续上涨（如内存缓增、连接数爬升）\n"
        "4. **处置建议**：按 P0/P1/P2 优先级给出可执行的排查/治理命令或操作\n"
        "如果指标均正常，请如实说明并给出例行巡检建议。注意区分单位（% / MB / 个 / ms）。"
    )
    user_prompt = "以下是指标监控的最新值（时间为最近采集）：\n\n" + "\n".join(lines)
    if question:
        user_prompt += f"\n\n用户附加诉求：{question}"

    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=max(provider.timeout_seconds, 90))
    if resp.get("error"):
        return JSONResponse({"ok": False, "error": f"AI 分析失败: {resp['error']}"})
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return JSONResponse({"ok": False, "error": "AI 返回格式异常"})

    return JSONResponse({"ok": True, "analysis": content or "", "provider": provider.default_model, "metric_count": len(metrics)})


