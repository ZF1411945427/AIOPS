"""
AI 洞察路由 — 统一指标/日志/链路三页的 AI 能力增强

功能:
- POST /ai-insight/analyze  — 统一分析入口(增强后,自动记录历史)
- GET  /ai-insight/history   — 查询历史分析记录
- GET  /ai-insight/history/{id} — 历史详情
- DELETE /ai-insight/history/{id} — 删除历史
- POST /ai-insight/rca       — 跨域根因分析
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Span
from app.services import metric_v2_service
from app.services.agent_service import call_llm
from app.services.ai_insight_service import (
    _get_provider, analyze_trend, TREND_CN, cluster_logs,
    aggregate_traces, cross_domain_rca,
    record_analysis, list_analysis, get_analysis_detail, delete_analysis,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-insight", tags=["ai_insight"])


@router.post("/analyze")
async def ai_insight_analyze(request: Request, db: Session = Depends(get_db)):
    """统一 AI 分析入口(增强版),返回增强结果 + 自动沉淀历史.

    body: {
      source_type: "metrics"|"logs"|"traces",
      question: "",
      ... 各类型专属字段
    }
    返回: {ok, analysis, provider, meta, record_id, ...增强数据}
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体格式错误"}, status_code=400)

    source_type = body.get("source_type", "")
    question = (body.get("question") or "").strip()

    provider = _get_provider(db)
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置可用的 AI 模型提供商"})

    analysis = ""
    meta = {"provider": provider.default_model, "source_type": source_type}
    enhanced_data = {}

    if source_type == "metrics":
        metrics = body.get("metrics") or []
        if not metrics:
            return JSONResponse({"error": "请先加载指标数据"}, status_code=400)
        if len(metrics) > 200:
            metrics = metrics[:200]
        hours = int(body.get("hours", 24))
        trend_map = {}
        for m in metrics:
            name = m.get("name", "")
            aid = m.get("asset_id", 0)
            agg = m.get("aggregate") or ""
            if name:
                if aid == 0 and agg:
                    r = metric_v2_service.query_range_aggregated(name, aggregate=agg, hours=hours)
                    vals = [pt.get("value") for pt in r.get("avg", []) if pt.get("value") is not None]
                else:
                    raw = metric_v2_service.query_range_data(asset_id=aid, name=name, hours=hours)
                    vals = [d.get("value") for d in raw if d.get("value") is not None]
                if len(vals) >= 3:
                    trend_map[name] = analyze_trend(vals)
        meta["trend_count"] = len(trend_map)
        meta["metric_count"] = len(metrics)
        enhanced_data["trends"] = trend_map
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
            tr = trend_map.get(name)
            if tr:
                parts.append(f" [趋势: {TREND_CN.get(tr['trend'], '?')} rel_change={tr['rel_change_pct']}%]")
            lines.append("".join(parts))
        sys_prompt = (
            "你是一名资深 SRE 运维专家，精通主机/应用/容器/K8s 资源指标解读与容量评估。"
            f"用户从指标监控页提交了 {len(metrics)} 项指标的最新值并附带了趋势分析(趋势/相对变化率/波动率/突刺检测)请求体检。"
            "请输出结构化分析：\n"
            "1. **健康总评**：整体资源健康度一句话结论（正常/需关注/高危）\n"
            "2. **异常指标**：列出明显异常或超阈值的指标（CPU>85%、内存>90%、磁盘>80%等），结合趋势判断风险\n"
            "3. **恶化趋势**：结合趋势数据指出哪些指标持续上涨/突刺/波动，判断是否会持续恶化\n"
            "4. **处置建议**：按 P0/P1/P2 优先级给出可执行命令或操作\n"
            "如果指标均正常，请如实说明并给出例行巡检建议。"
        )
        user_prompt = "以下是指标监控的最新值（附趋势分析）：\n\n" + "\n".join(lines)
        if question:
            user_prompt += f"\n\n用户附加诉求：{question}"
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=120)
        if resp.get("error"):
            return JSONResponse({"ok": False, "error": f"AI 分析失败: {resp['error']}"})
        try:
            analysis = resp["choices"][0]["message"]["content"]
        except Exception:
            return JSONResponse({"ok": False, "error": "AI 返回格式异常"})
        score = 0
        if "高危" in analysis or "严重" in analysis:
            score = 30
        elif "需关注" in analysis or "异常" in analysis:
            score = 60
        else:
            score = 90

    elif source_type == "logs":
        logs = body.get("logs") or []
        if not logs:
            return JSONResponse({"error": "请先勾选至少一条日志"}, status_code=400)
        if len(logs) > 100:
            logs = logs[:100]
        clustered = cluster_logs(logs)
        meta["log_count"] = len(logs)
        meta["cluster_count"] = clustered["cluster_count"]
        meta["error_pct"] = clustered["error_pct"]
        enhanced_data["clusters"] = clustered["clusters"]
        # 检测 trace_id 关联
        trace_ids = set()
        for lg in logs:
            msg = lg.get("message", "") or ""
            m = __import__("re").search(r'trace(?:_id|Id|ID)[=:\s]+([a-zA-Z0-9\-]+)', msg)
            if m:
                trace_ids.add(m.group(1))
        if trace_ids:
            related_spans = db.query(Span).filter(Span.trace_id.in_(list(trace_ids)[:5])).limit(30).all()
            if related_spans:
                meta["trace_related"] = len(set(s.trace_id for s in related_spans))
            enhanced_data["trace_ids"] = list(trace_ids)[:5]
        lines = []
        for c in clustered["clusters"][:20]:
            lines.append(f"  [{c['level']}] svc={c['service']} host={c['host']} type={c['error_type']} count={c['count']}")
        cluster_summary = "\n".join(lines)
        sys_prompt = (
            "你是一名资深 SRE 运维专家，精通日志分析与故障根因定位。"
            f"用户从日志中心勾选了 {len(logs)} 条日志，已自动聚类为 {clustered['cluster_count']} 组(错误占 {clustered['error_pct']}%)。"
            "请基于聚类摘要和原始日志做结构化分析：\n"
            "1. **异常模式**：结合聚类结果，识别错误规律和异常模式\n"
            "2. **根因推断**：最可能的故障根因，按可能性排序并说明依据\n"
            "3. **影响评估**：受影响的服务/主机范围与严重程度\n"
            "4. **处置建议**：P0/P1/P2 优先级给出可执行的具体命令或操作步骤\n"
            "如果日志无明显异常，请如实说明。"
        )
        raw_lines = []
        for i, lg in enumerate(logs[:100], 1):
            ts = (lg.get("timestamp") or "").replace("T", " ")[:19]
            lvl = lg.get("level") or "info"
            host = lg.get("host") or "-"
            svc = lg.get("service") or "-"
            msg = (lg.get("message") or "").strip()
            raw_lines.append(f"{i}. [{ts}] [{lvl}] host={host} service={svc} | {msg}")
        user_prompt = (
            f"日志聚类摘要（共 {clustered['cluster_count']} 组）:\n{cluster_summary}\n\n"
            f"原始日志:\n" + "\n".join(raw_lines)
        )
        if question:
            user_prompt += f"\n\n用户附加诉求：{question}"
        if trace_ids:
            user_prompt += f"\n\n关联 trace_id: {', '.join(list(trace_ids)[:5])}"
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=120)
        if resp.get("error"):
            return JSONResponse({"ok": False, "error": f"AI 分析失败: {resp['error']}"})
        try:
            analysis = resp["choices"][0]["message"]["content"]
        except Exception:
            return JSONResponse({"ok": False, "error": "AI 返回格式异常"})
        err_count = clustered["error_count"]
        score = 30 if err_count > 10 else 60 if err_count > 0 else 90

    elif source_type == "traces":
        traces = body.get("traces") or []
        if not traces:
            return JSONResponse({"error": "请先选择要分析的调用链"}, status_code=400)
        if len(traces) > 20:
            traces = traces[:20]
        aggregated = aggregate_traces(traces)
        meta["trace_count"] = len(traces)
        meta["service_count"] = len(aggregated["services"])
        enhanced_data["aggregation"] = aggregated
        blocks = []
        total_spans = 0
        for i, tr in enumerate(traces[:20], 1):
            spans = tr.get("spans") or []
            total_spans += len(spans)
            if len(spans) > 30:
                spans = spans[:30]
            head = (
                f"{i}. 调用链 {tr.get('trace_id', '?')[:20]} "
                f"根服务={tr.get('root_service') or '-'} 操作={tr.get('root_operation') or '-'} "
                f"总耗时={tr.get('total_duration_ms')}ms 状态={tr.get('worst_status') or 'OK'} "
                f"路径数={len(tr.get('spans') or [])}"
            )
            span_lines = []
            for j, s in enumerate(spans, 1):
                span_lines.append(
                    f"    {j}. [{s.get('service_name') or '-'}] {s.get('operation_name') or '-'} "
                    f"耗时={s.get('duration_ms')}ms 状态={s.get('status') or 'OK'}"
                )
            blocks.append(head + ("\n" + "\n".join(span_lines) if span_lines else " (无明细)"))
        top = aggregated.get("top_bottleneck")
        agg_line = ""
        if top:
            agg_line = f"\n\n跨链路聚合瓶颈分析: TOP1 {top['service']} P90={top['p90_duration_ms']}ms 错误率={top['error_rate']}%"
        sys_prompt = (
            "你是一名资深 SRE 工程师，精通分布式系统调用链分析（APM / 全链路追踪）。"
            f"用户提交了 {len(traces)} 条调用链({total_spans} 个 span, {len(aggregated['services'])} 个服务)请求分析。"
            f"已自动做跨链路聚合，按服务瓶颈评分排序。{agg_line}"
            "请输出结构化分析：\n"
            "1. **瓶颈定位**：哪个服务、哪个操作耗时占比最高(列出 top 瓶颈服务)\n"
            "2. **异常链路**：状态为 ERROR 的调用链及其错误服务/操作，推断可能原因\n"
            "3. **依赖关系**：识别上下游依赖，指出单点或雪崩风险\n"
            "4. **处置建议**：P0/P1/P2 给出可执行建议(扩容/限流/降级/慢 SQL 优化等)"
        )
        user_prompt = "以下是调用链及跨链路聚合数据：\n\n" + "\n".join(blocks)
        if question:
            user_prompt += f"\n\n用户附加诉求：{question}"
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=120)
        if resp.get("error"):
            return JSONResponse({"ok": False, "error": f"AI 分析失败: {resp['error']}"})
        try:
            analysis = resp["choices"][0]["message"]["content"]
        except Exception:
            return JSONResponse({"ok": False, "error": "AI 返回格式异常"})
        error_traces = sum(1 for tr in traces if tr.get("worst_status") == "ERROR")
        score = 30 if error_traces > 3 else 60 if error_traces > 0 else 90
    else:
        return JSONResponse({"error": "source_type 必须是 metrics/logs/traces"}, status_code=400)

    title = body.get("title") or f"{source_type} 分析 #{datetime.now().strftime('%H%M%S')}"
    rec = record_analysis(db, user_id, source_type, title, analysis,
                          provider=provider.default_model, meta_json=meta,
                          question=question, score=score)
    return JSONResponse({
        "ok": True,
        "analysis": analysis,
        "provider": provider.default_model,
        "record_id": rec.id,
        "meta": meta,
        "score": score,
        "enhanced": enhanced_data,
    })


@router.get("/history")
def insight_history(request: Request, source_type: str = Query(""),
                    limit: int = Query(50), db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    return JSONResponse(list_analysis(db, user_id, source_type=source_type, limit=limit))


@router.get("/history/{record_id}")
def insight_history_detail(record_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    detail = get_analysis_detail(db, record_id, user_id)
    if not detail:
        return JSONResponse({"error": "记录不存在"}, status_code=404)
    return JSONResponse(detail)


@router.delete("/history/{record_id}")
def insight_history_delete(record_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if delete_analysis(db, record_id, user_id):
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "记录不存在或无权删除"}, status_code=404)


@router.post("/rca")
async def insight_rca(request: Request, db: Session = Depends(get_db)):
    """跨域根因分析: 指标异常 → 自动关联告警+日志+链路

    body: {
      metric_name: "cpu_usage",
      asset_id: 1,
      hours: 6,
      question: "可选"
    }
    返回: {ok, analysis, trend, alert_count, trace_count, ...}
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体格式错误"}, status_code=400)
    metric_name = body.get("metric_name", "")
    asset_id = int(body.get("asset_id", 0) or 0)
    hours = int(body.get("hours", 6) or 6)
    question = (body.get("question") or "").strip()
    if not metric_name or not asset_id:
        return JSONResponse({"error": "metric_name 和 asset_id 必填"}, status_code=400)
    provider = _get_provider(db)
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置可用的 AI 模型提供商"})
    result = cross_domain_rca(db, provider, metric_name, asset_id, hours, question)
    if result.get("ok"):
        rec = record_analysis(db, user_id, "rca",
                              f"RCA: {metric_name} @ asset#{asset_id}",
                              result.get("analysis", ""),
                              provider=provider.default_model,
                              meta_json={"metric_name": metric_name, "asset_id": asset_id,
                                         "trend": result.get("trend"),
                                         "alert_count": result.get("alert_count", 0),
                                         "trace_count": result.get("trace_count", 0)})
        result["record_id"] = rec.id
    return JSONResponse(result)