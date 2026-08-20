import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, Asset, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service
from app.services.promql_parser import parse_promql, promql_to_dict


import logging
logger = logging.getLogger(__name__)

def _get_db():
    return get_session_for(get_db_mode())()

# ─── Analysis Tools ────────────────────────────────────────────

@register_mcp_tool(
    name="analyze_incident_rca",
    description="分析故障单的根因",
    input_schema={
        "type": "object",
        "properties": {
            "incident_id": {"type": "integer", "description": "故障单 ID"},
        },
        "required": ["incident_id"],
    },
    risk_level="read_only",
    display_name="RCA 根因分析",
    location="cloud",
    category="rca",
)
def analyze_incident_rca(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.rca_service import analyze_incident
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        incident_id = kwargs.get("incident_id")
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return {"error": "故障单未找到"}
        result = analyze_incident(db, incident_id)
        return result
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="query_correlation_analysis",
    description="查询多维度可观测性关联分析结果。同时分析告警、指标异常(Z-Score)、日志异常(K8s Events)、链路追踪(慢调用+错误率)四个信号维度，按资产加权评分聚合。适用于：系统出现异常时快速了解全局状态、告警风暴时定位根因资产、故障复盘时查看多信号关联关系。返回关联分析概览+告警列表+指标异常+日志异常+链路追踪+资产评分+RCA预判建议。支持按时间范围、服务名、资产ID筛选。",
    input_schema={
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "分析时间范围（最近多少小时）", "default": 1},
            "service": {"type": "string", "description": "服务名过滤（可选，模糊匹配）"},
            "asset_id": {"type": "integer", "description": "资产 ID 过滤（可选）"},
        },
    },
    risk_level="read_only",
    display_name="关联分析",
    location="cloud",
    category="rca",
)
def query_correlation_analysis(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.routers.observability_correlation import run_correlation_analysis, format_correlation_for_llm
        hours = int(kwargs.get("hours", 1))
        service = kwargs.get("service", "")
        asset_id = int(kwargs.get("asset_id", 0))
        data = run_correlation_analysis(db, hours, service, asset_id)
        formatted = format_correlation_for_llm(data)
        return {
            "summary": data.get("summary", {}),
            "alert_count": len(data.get("alerts", [])),
            "metric_anomaly_count": len(data.get("metric_anomalies", [])),
            "log_anomaly_count": len(data.get("log_anomalies", [])),
            "trace_error_rate_pct": data.get("trace_anomalies", {}).get("error_rate_pct", 0),
            "correlated_asset_count": data.get("summary", {}).get("correlated_assets", 0),
            "change_record_count": len(data.get("change_records", [])),
            "rca_suggestions": data.get("rca_suggestions", []),
            "detail": formatted,
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="run_preset_diagnosis",
    description="按告警指标类型自动执行预置诊断命令包（只读、免审批）。根据 metric_name 匹配诊断包（cpu_usage→top/ps/vmstat，memory_usage→free/ps，disk_usage→df/du，k8s_pod_crash→kubectl describe/logs 等），自动在目标资产上执行并返回命令输出。比 AI 手动逐条选命令更完整、更快速。",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "告警 ID（优先使用，自动读取 metric_name 和 asset_id）"},
            "asset_id": {"type": "integer", "description": "目标资产 ID（alert_id 缺失时必填）"},
            "metric_name": {"type": "string", "description": "指标名（alert_id 缺失时用于匹配诊断包，如 cpu_usage、memory_usage、disk_usage）"},
        },
    },
    risk_level="read_only",
    display_name="预置诊断命令包",
    location="edge",
    category="rca",
)
def run_preset_diagnosis(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    """复用自愈 DIAGNOSIS_COMMAND_PACKS + run_diagnosis，按指标类型自动跑完整诊断命令包."""
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert_id = kwargs.get("alert_id")
        asset_id = kwargs.get("asset_id")
        metric_name = kwargs.get("metric_name", "")

        # 优先从告警读取 metric_name + asset_id
        if alert_id:
            alert = db.query(Alert).filter(Alert.id == int(alert_id)).first()
            if not alert:
                return {"error": f"告警 id={alert_id} 不存在"}
            metric_name = metric_name or alert.metric_name or ""
            asset_id = asset_id or alert.asset_id

        if not asset_id:
            return {"error": "缺少 asset_id（需提供 alert_id 或 asset_id）"}

        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 id={asset_id} 不存在"}

        # 有 alert_id：走 run_diagnosis（会存 DiagnosisReport，支持缓存）
        if alert_id:
            result = remediation_service.run_diagnosis(
                db,
                alert_id=int(alert_id),
                asset_id=int(asset_id),
                metric_name=metric_name,
            )
            if result.get("ok"):
                commands = result.get("commands", [])
                return {
                    "status": "success",
                    "cached": result.get("cached", False),
                    "report_id": result.get("report_id"),
                    "command_count": len(commands),
                    "commands": [
                        {"cmd": c.get("cmd", ""), "desc": c.get("desc", ""),
                         "exit_code": c.get("exit_code", -1),
                         "duration_ms": c.get("duration_ms", 0),
                         "output": c.get("output", "")}
                        for c in commands
                ],
                "summary": f"执行了 {len(commands)} 条诊断命令，"
                           + ("全部成功" if all(c.get("exit_code") == 0 for c in commands) else "部分失败"),
            }
            return {"error": result.get("error", "诊断执行失败")}

        # 无 alert_id：直接用 DIAGNOSIS_COMMAND_PACKS + _remote_exec 执行（不存报告）
        pack_key = remediation_service._match_diagnosis_pack(metric_name)
        pack = remediation_service.DIAGNOSIS_COMMAND_PACKS.get(pack_key,
                    remediation_service.DIAGNOSIS_COMMAND_PACKS["_default"])
        channel = remediation_service._ci_channel(asset)
        results = []
        for cmd_spec in pack:
            raw_cmd = cmd_spec["cmd"]
            cmd = remediation_service._fill_template(raw_cmd, asset, channel)
            desc = cmd_spec.get("desc", "")
            timeout = cmd_spec.get("timeout", 10)
            success, output = remediation_service._remote_exec(asset, cmd, timeout=timeout)
            results.append({
                "cmd": cmd, "desc": desc,
                "exit_code": 0 if success else 1,
                "duration_ms": 0,
                "output": output[:1000] if output else "",
            })
        return {
            "status": "success",
            "cached": False,
            "report_id": None,
            "command_count": len(results),
            "commands": results,
            "summary": f"执行了 {len(results)} 条诊断命令，"
                       + ("全部成功" if all(r["exit_code"] == 0 for r in results) else "部分失败"),
        }
    finally:
        if close_db:
            db.close()
