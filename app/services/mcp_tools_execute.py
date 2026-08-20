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

# ─── Execute Tools (待确认动作执行链路, expose_to_llm=False) ───
# 以下 execute_* 工具供 confirm_pending_action 通过 call_mcp_tool 调用,
# 不暴露给 LLM (expose_to_llm=False), 防止绕过人工确认直接执行高危操作.
#
# 设计约定 (与 call_mcp_tool 包装语义对齐):
#   - 业务成功 -> 返回 {"status":"success","message":"...","data":...}
#     call_mcp_tool 会包成 {"status":"success","result":{...}}, confirm 判定成功.
#   - 业务失败/异常 -> 抛异常 (ValueError/RuntimeError),
#     call_mcp_tool 捕获后返回 {"status":"error","message":...}, confirm 判定失败.
#   - 切勿在 handler 内返回 {"status":"error",...} dict, 否则会被外层误包为 success.


@register_mcp_tool(
    name="execute_restart_service",
    description="通过 SSH 远程重启指定资产主机上的服务 (高危, 需人工确认). 必须指定 asset_id 指向 CMDB 中的资产记录",
    input_schema={
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "服务名称, 如 nginx、mysql"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录), 系统将通过该资产的 SSH 连接配置远程执行"},
        },
        "required": ["service", "asset_id"],
    },
    risk_level="high",
    review_gate=True,  # 高危写操作, 需审批
    display_name="重启服务",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_restart_service(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        service = kwargs.get("service")
        asset_id = kwargs.get("asset_id")
        pending_action_id = kwargs.get("_pending_action_id")
        if not service:
            raise ValueError("缺少必填参数: service")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        # 异步路径：有 pending_action_id（来自 propose → confirm 链路）则走 BackgroundJob
        if pending_action_id:
            from app.services.background_task import submit_restart_job
            job_id = submit_restart_job(service=service, asset_id=int(asset_id),
                                      pending_action_id=pending_action_id)
            return {
                "status": "executing",
                "message": f"重启任务已提交，job_id={job_id}",
                "data": {"job_id": job_id, "service": service, "asset_id": asset_id, "ip": asset.ip},
            }
        # 同步路径：复用自愈 CI-Type-Aware 执行通道（SSH/K8s/Docker 自动分派）
        success, message = remediation_service.execute_action("restart", {"service": service}, asset, db=db)
        if not success:
            raise RuntimeError(message)
        return {"status": "success", "message": message, "data": {"service": service, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_clean_disk",
    description="通过 SSH 远程清理指定资产主机上某路径的磁盘空间 (高危, 需人工确认). 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "待清理路径, 如 /tmp、/var/log"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["path", "asset_id"],
    },
    risk_level="high",
    review_gate=True,  # 高危写操作, 需审批
    display_name="清理磁盘",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_clean_disk(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        path = kwargs.get("path")
        asset_id = kwargs.get("asset_id")
        if not path:
            raise ValueError("缺少必填参数: path")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        success, message = remediation_service.execute_action("clean", {"path": path}, asset, db=db)
        if not success:
            raise RuntimeError(message)
        return {"status": "success", "message": message, "data": {"path": path, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_run_script",
    description="通过 SSH 在指定资产主机上执行脚本 (极危, 需人工确认). 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "脚本在远程主机上的绝对路径, 如 /opt/scripts/fix.sh"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["script", "asset_id"],
    },
    risk_level="critical",
    display_name="执行脚本",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_run_script(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        script = kwargs.get("script")
        asset_id = kwargs.get("asset_id")
        pending_action_id = kwargs.get("_pending_action_id")
        if not script:
            raise ValueError("缺少必填参数: script")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")
        # cmdpolicy 沙箱: 沙盒启用时按策略校验
        try:
            from app.services import sandbox_service
            sb = sandbox_service.evaluate_request(
                "mcp_tool", "execute_run_script", asset.id, script,
                "high", session_id=0, user_id=user_id or 0, role_id=0, db=db)
            if sb.get("decision") == "rejected":
                raise ValueError(f"沙盒策略拦截: {sb.get('reason')}")
        except ValueError:
            raise
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
        # 异步路径
        if pending_action_id:
            from app.services.background_task import submit_script_job
            job_id = submit_script_job(script=script, asset_id=int(asset_id),
                                   pending_action_id=pending_action_id)
            return {
                "status": "executing",
                "message": f"脚本执行任务已提交，job_id={job_id}",
                "data": {"job_id": job_id, "script": script, "asset_id": asset_id, "ip": asset.ip},
            }
        # 同步路径：复用自愈 CI-Type-Aware 执行通道
        success, output = remediation_service.execute_action("script", {"script": script}, asset, db=db)
        if not success:
            raise RuntimeError(output)
        return {"status": "success", "message": output, "data": {"script": script, "asset_id": asset.id, "ip": asset.ip}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_run_command",
    description="通过 SSH 在指定资产主机上执行任意命令 (极危, 需人工确认). 适用于诊断命令如 ps/df/free/top/grep/cat 等. 危险命令(rm -rf /、mkfs、dd、shutdown、reboot 等)会被黑名单拦截. 必须指定 asset_id",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令, 如 'ps aux | grep nginx'、'df -h'、'free -m'"},
            "asset_id": {"type": "integer", "description": "目标资产 ID (CMDB 资产记录)"},
        },
        "required": ["command", "asset_id"],
    },
    risk_level="critical",
    display_name="执行命令",
    expose_to_llm=False,
    location="edge",
    category="execute_host",
)
def execute_run_command(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        command = kwargs.get("command")
        asset_id = kwargs.get("asset_id")
        if not command:
            raise ValueError("缺少必填参数: command")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可远程执行")

        # cmdpolicy 沙箱: 沙盒启用时按策略校验(黑/白名单/风险/执行窗口)
        try:
            from app.services import sandbox_service
            sb = sandbox_service.evaluate_request(
                "mcp_tool", "execute_run_command", asset.id, command,
                "critical", session_id=0, user_id=user_id or 0, role_id=0, db=db)
            if sb.get("decision") == "rejected":
                raise ValueError(f"沙盒策略拦截: {sb.get('reason')}")
        except ValueError:
            raise
        except Exception as _exc2:
            logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)

        # 统一命令路由：优先走 edge agent 隧道，无在线 agent 时回退 SSH
        from app.routers.agent_deploy import route_exec
        result = route_exec(
            asset.id, command,
            user_id=user_id or 0,
            username=kwargs.get("username", ""),
            timeout=int(kwargs.get("timeout", 30)),
        )
        if result.get("exit_code", -1) != 0:
            raise RuntimeError(result.get("stderr") or result.get("stdout") or "命令执行失败")
        return {
            "status": "success",
            "message": result.get("stdout", ""),
            "data": {
                "command": command,
                "asset_id": asset.id,
                "ip": asset.ip,
                "channel": result.get("channel", "ssh"),
            },
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_acknowledge_alert",
    description="确认告警 (标记为已处理)，支持单个或批量",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "单个告警 ID（与 alert_ids 二选一）"},
            "alert_ids": {"type": "array", "items": {"type": "integer"}, "description": "批量告警 ID 列表（与 alert_id 二选一）"},
        },
        "required": [],
    },
    risk_level="low",
    display_name="确认告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_acknowledge_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert_id = kwargs.get("alert_id")
        alert_ids = kwargs.get("alert_ids")
        if alert_id is None and not alert_ids:
            raise ValueError("缺少必填参数: alert_id 或 alert_ids")
        if alert_id is not None:
            alert_ids = [alert_id]
        confirmed = []
        for aid in alert_ids:
            alert = alert_service.acknowledge_alert(db, int(aid))
            if not alert:
                raise ValueError(f"告警 {aid} 未找到")
            confirmed.append(alert.id)
        if len(confirmed) == 1:
            return {"status": "success", "message": f"告警 {confirmed[0]} 已确认", "data": {"alert_ids": confirmed, "status": "acknowledged"}}
        return {"status": "success", "message": f"已批量确认 {len(confirmed)} 条告警", "data": {"alert_ids": confirmed, "status": "acknowledged"}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_resolve_alert",
    description="解决告警 (标记为已解决)",
    input_schema={
        "type": "object",
        "properties": {
            "alert_id": {"type": "integer", "description": "告警 ID"},
        },
        "required": ["alert_id"],
    },
    risk_level="low",
    display_name="解决告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_resolve_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        alert_id = kwargs.get("alert_id")
        if alert_id is None:
            raise ValueError("缺少必填参数: alert_id")
        alert = alert_service.resolve_alert(db, int(alert_id))
        if not alert:
            raise ValueError(f"告警 {alert_id} 未找到")
        return {"status": "success", "message": f"告警 {alert_id} 已解决", "data": {"alert_id": alert.id, "status": alert.status}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_resolve_incident",
    description="解决故障单 (标记为已解决)",
    input_schema={
        "type": "object",
        "properties": {
            "incident_id": {"type": "integer", "description": "故障单 ID"},
        },
        "required": ["incident_id"],
    },
    risk_level="low",
    display_name="解决故障单",
    expose_to_llm=False,
    location="cloud",
    category="incident",
)
def execute_resolve_incident(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        incident_id = kwargs.get("incident_id")
        if incident_id is None:
            raise ValueError("缺少必填参数: incident_id")
        incident = incident_service.resolve_incident(db, int(incident_id))
        if not incident:
            raise ValueError(f"故障单 {incident_id} 未找到")
        return {"status": "success", "message": f"故障单 {incident_id} 已解决", "data": {"incident_id": incident.id, "status": incident.status}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_silence_alert",
    description="静默告警规则指定时长 (抑制告警通知)",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
            "minutes": {"type": "integer", "description": "静默时长 (分钟)"},
            "reason": {"type": "string", "description": "静默原因"},
        },
        "required": ["rule_id", "minutes"],
    },
    risk_level="medium",
    display_name="静默告警",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_silence_alert(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        minutes = kwargs.get("minutes")
        reason = kwargs.get("reason", "")
        if rule_id is None or minutes is None:
            raise ValueError("缺少必填参数: rule_id, minutes")
        silence = alert_service.create_silence(db, int(rule_id), int(minutes), reason)
        return {"status": "success", "message": f"规则 {rule_id} 已静默 {minutes} 分钟", "data": {"silence_id": silence.id, "rule_id": silence.rule_id, "expires_at": str(silence.expires_at)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_create_alert_rule",
    description="创建告警规则",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "告警规则数据",
                "properties": {
                    "name": {"type": "string", "description": "规则名称"},
                    "metric_name": {"type": "string", "description": "指标名称, 如 cpu_usage"},
                    "condition": {"type": "string", "description": "比较条件: gt (大于) / lt (小于)"},
                    "threshold": {"type": "number", "description": "阈值"},
                    "severity": {"type": "string", "description": "严重级别: warning / critical"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                },
                "required": ["name", "metric_name", "condition", "threshold"],
            },
        },
        "required": ["data"],
    },
    risk_level="medium",
    display_name="创建告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_create_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        data = kwargs.get("data")
        if not data:
            raise ValueError("缺少必填参数: data")
        rule = alert_service.create_rule(db, data)
        return {"status": "success", "message": f"告警规则 {rule.name} 已创建", "data": {"rule_id": rule.id, "name": rule.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_update_alert_rule",
    description="更新告警规则",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
            "data": {
                "type": "object",
                "description": "待更新的规则字段",
                "properties": {
                    "name": {"type": "string", "description": "规则名称"},
                    "metric_name": {"type": "string", "description": "指标名称"},
                    "condition": {"type": "string", "description": "比较条件: gt / lt"},
                    "threshold": {"type": "number", "description": "阈值"},
                    "severity": {"type": "string", "description": "严重级别"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                },
            },
        },
        "required": ["rule_id", "data"],
    },
    risk_level="medium",
    display_name="更新告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_update_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        data = kwargs.get("data")
        if rule_id is None or not data:
            raise ValueError("缺少必填参数: rule_id, data")
        rule = alert_service.update_rule(db, int(rule_id), data)
        if not rule:
            raise ValueError(f"告警规则 {rule_id} 未找到")
        return {"status": "success", "message": f"告警规则 {rule_id} 已更新", "data": {"rule_id": rule.id, "name": rule.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_delete_alert_rule",
    description="删除告警规则 (高危, 不可恢复)",
    input_schema={
        "type": "object",
        "properties": {
            "rule_id": {"type": "integer", "description": "告警规则 ID"},
        },
        "required": ["rule_id"],
    },
    risk_level="high",
    review_gate=True,  # 高危写操作, 需审批
    display_name="删除告警规则",
    expose_to_llm=False,
    location="cloud",
    category="alert",
)
def execute_delete_alert_rule(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        rule_id = kwargs.get("rule_id")
        if rule_id is None:
            raise ValueError("缺少必填参数: rule_id")
        deleted = alert_service.delete_rule(db, int(rule_id))
        if not deleted:
            raise ValueError(f"告警规则 {rule_id} 未找到")
        return {"status": "success", "message": f"告警规则 {rule_id} 已删除", "data": {"rule_id": int(rule_id)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_create_asset",
    description="创建资产 (CMDB 资产录入)",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "资产数据",
                "properties": {
                    "name": {"type": "string", "description": "资产名称"},
                    "type": {"type": "string", "description": "资产类型"},
                    "ci_type": {"type": "string", "description": "CI 类型: server / pod / deployment / service / node / cluster"},
                    "ip": {"type": "string", "description": "IP 地址"},
                    "status": {"type": "string", "description": "状态: online / offline / warning"},
                    "tags": {"type": "string", "description": "标签 (逗号分隔)"},
                    "k8s_cluster": {"type": "string", "description": "K8s 集群名称"},
                    "connection_type": {"type": "string", "description": "连接类型: ssh"},
                    "connection_config": {"type": "string", "description": "连接配置 (JSON 字符串)"},
                },
                "required": ["name", "type"],
            },
        },
        "required": ["data"],
    },
    risk_level="medium",
    display_name="创建资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_create_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        data = kwargs.get("data")
        if not data:
            raise ValueError("缺少必填参数: data")
        asset = asset_service.create_asset(db, data)
        return {"status": "success", "message": f"资产 {asset.name} 已创建", "data": {"asset_id": asset.id, "name": asset.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_update_asset",
    description="更新资产信息",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID"},
            "data": {
                "type": "object",
                "description": "待更新的资产字段",
                "properties": {
                    "name": {"type": "string", "description": "资产名称"},
                    "type": {"type": "string", "description": "资产类型"},
                    "ci_type": {"type": "string", "description": "CI 类型"},
                    "ip": {"type": "string", "description": "IP 地址"},
                    "status": {"type": "string", "description": "状态"},
                    "tags": {"type": "string", "description": "标签"},
                    "k8s_cluster": {"type": "string", "description": "K8s 集群名称"},
                    "connection_type": {"type": "string", "description": "连接类型"},
                    "connection_config": {"type": "string", "description": "连接配置"},
                },
            },
        },
        "required": ["asset_id", "data"],
    },
    risk_level="medium",
    display_name="更新资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_update_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset_id = kwargs.get("asset_id")
        data = kwargs.get("data")
        if asset_id is None or not data:
            raise ValueError("缺少必填参数: asset_id, data")
        asset = asset_service.update_asset(db, int(asset_id), data)
        if not asset:
            raise ValueError(f"资产 {asset_id} 未找到")
        return {"status": "success", "message": f"资产 {asset_id} 已更新", "data": {"asset_id": asset.id, "name": asset.name}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_delete_asset",
    description="删除资产 (高危, 不可恢复)",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID"},
        },
        "required": ["asset_id"],
    },
    risk_level="high",
    review_gate=True,  # 高危写操作, 需审批
    display_name="删除资产",
    expose_to_llm=False,
    location="cloud",
    category="asset",
)
def execute_delete_asset(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset_id = kwargs.get("asset_id")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")
        deleted = asset_service.delete_asset(db, int(asset_id))
        if not deleted:
            raise ValueError(f"资产 {asset_id} 未找到")
        return {"status": "success", "message": f"资产 {asset_id} 已删除", "data": {"asset_id": int(asset_id)}}
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_probe_assets",
    description="批量探测所有资产的连接状态并更新",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="low",
    display_name="探测资产",
    expose_to_llm=False,
    location="edge",
    category="asset",
)
def execute_probe_assets(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        changed = asset_service.probe_assets(db)
        return {"status": "success", "message": f"资产探测完成, {len(changed)} 个状态变更", "data": {"changed_count": len(changed), "changed": changed}}
    finally:
        if close_db:
            db.close()
