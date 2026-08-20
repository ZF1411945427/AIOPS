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

# ─── Action Proposal Tools (建议工具, 暴露给 LLM 触发 PendingAction) ───
# list_executable_actions / propose_action 是 LLM 触发待确认动作的唯一入口:
#   - list_executable_actions: 枚举 execute_* 内部工具清单 (action_type/参数 schema/风险等级)
#   - propose_action: 提议运维动作, 返回 _pending_action 字段;
#     process_chat_message 检测该字段后创建 PendingAction, 形成人工确认闭环.
# execute_* 工具本身 expose_to_llm=False, LLM 无法直调, 必须经 propose_action 走确认.


def _action_type_from_tool_name(name: str) -> str:
    """execute_restart_service -> restart_service; 非 execute_ 前缀原样返回."""
    return name[8:] if name.startswith("execute_") else name


# 风险等级序数: 用于"只允许升级不允许降级"校验, 防止 LLM 把高危操作标为低危绕过"知情同意"
_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
# ─── 诊断命令白名单: 用于 propose_action 强制 auto_confirm (方案B) ───
# 只读诊断命令的首词集合, 这些命令不改写磁盘/不修改系统状态/不影响业务.
# yum/apt/systemctl/docker/kubectl 等命令读写混杂 (yum install 写, yum list 读),
# 不纳入白名单, 由 LLM 自评 risk_level + auto_confirm.
# bash/sh 不纳入 (bash -c 'rm -rf /' 可执行任意命令, 风险不可控).
_READ_ONLY_COMMAND_PREFIXES = {
    "ps", "df", "free", "top", "grep", "egrep", "fgrep", "which", "whereis",
    "echo", "date", "ls", "ll", "cat", "head", "tail", "wc", "uname", "whoami",
    "id", "env", "printenv", "hostname", "ip", "ifconfig", "uptime", "who",
    "last", "find", "ss", "netstat", "lsof", "stat", "file", "du", "lsblk",
    "journalctl", "dmesg", "rpm", "nginx", "httpd", "test", "pwd", "basename",
    "dirname", "realpath", "readlink", "md5sum", "sha256sum", "cksum", "cut",
    "tr", "sort", "uniq", "awk", "sed",  # 注意: sed -i 是写操作, 由危险命令黑名单兜底
}


def _is_read_only_diagnostic_command(command: str) -> bool:
    """判断命令是否为只读诊断命令 (所有子命令首词都在白名单).

    用于 propose_action 强制 auto_confirm=true, 跳过用户确认.
    判定规则: 用管道/分号/逻辑与或分割成多个子命令, 每个子命令去掉 sudo 前缀后
    取首词, 全部在白名单才返回 True. 任一子命令首词不在白名单则返回 False.
    这样 `echo x | sudo rm` 会被拒绝 (rm 不在白名单), `ps aux | grep nginx` 会通过.
    """
    if not command or not isinstance(command, str):
        return False
    # 按 || && ; | 分割 (注意双字符操作符先匹配)
    parts = re.split(r'\|\||&&|;|\|', command)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        # 去掉 sudo 前缀
        if tokens[0] == "sudo" and len(tokens) > 1:
            tokens = tokens[1:]
        first = tokens[0]
        if first not in _READ_ONLY_COMMAND_PREFIXES:
            return False
    return True


@register_mcp_tool(
    name="list_executable_actions",
    description="列出所有可提议执行的运维动作清单 (action_type、风险等级、参数 schema)。AI 助手在提议运维操作前应先调用此工具了解可用动作及其参数要求。",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="可执行动作清单",
    expose_to_llm=True,
    location="cloud",
    category="propose",
)
def list_executable_actions(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    actions = [
        {
            "action_type": _action_type_from_tool_name(tool.name),
            "tool_name": tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "input_schema": tool.input_schema,
        }
        for tool in get_internal_tools()
        if tool.name.startswith("execute_")
    ]
    return {"actions": actions}


@register_mcp_tool(
    name="switch_sub_agent",
    description="切换子智能体（协调器用）。当前会话切换到指定子专家后，对话上下文将独立保持。可用子专家见 list_sub_agents。",
    input_schema={
        "type": "object",
        "properties": {
            "sub_agent_name": {
                "type": "string",
                "description": "子专家名称: sre_expert / network_expert / database_expert / middleware_expert / k8s_expert / general",
            },
            "reason": {"type": "string", "description": "切换原因，供用户理解"},
        },
        "required": ["sub_agent_name"],
    },
    risk_level="low",
    display_name="切换子智能体",
    location="cloud",
    category="general",
    timeout_seconds=5,
)
def switch_sub_agent(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    """切换当前会话的子智能体。协调器（general）检测到用户问题需特定子专家时调用此工具。"""
    sub_agent_name = kwargs.get("sub_agent_name", "").strip()
    if not sub_agent_name:
        return {"status": "error", "message": "缺少 sub_agent_name"}
    from app.services.sub_agent_service import list_sub_agents
    valid = [sa.name for sa in list_sub_agents(db, enabled_only=True)] if db else []
    if sub_agent_name not in valid:
        return {"status": "error", "message": f"无效子智能体 '{sub_agent_name}'，可用: {', '.join(valid)}"}
    return {
        "status": "success",
        "result": {
            "_switch_sub_agent": sub_agent_name,
            "message": f"已切换到子智能体「{sub_agent_name}」，后续对话将使用该子专家的上下文和工具集。",
            "sub_agent_name": sub_agent_name,
            "reason": kwargs.get("reason", ""),
        },
    }


@register_mcp_tool(
    name="propose_action",
    description="提议一个运维操作, 生成待确认动作供用户确认后执行。不直接执行任何操作, 仅创建待确认记录。AI 助手想执行运维操作时必须用此工具提议, 不能直接调用 execute_* 工具。",
    input_schema={
        "type": "object",
        "properties": {
            "action_type": {"type": "string", "description": "动作类型, 对应 execute_* 的后缀 (如 restart_service、acknowledge_alert), 必须是 list_executable_actions 返回的合法值"},
            "title": {"type": "string", "description": "动作标题, 展示给用户"},
            "payload": {"type": "object", "description": "执行参数, 将原样传给对应的 execute_* 工具"},
            "risk_level": {"type": "string", "description": "风险等级: low / medium / high / critical, 默认由 action_type 推断", "enum": ["low", "medium", "high", "critical"]},
            "reason": {"type": "string", "description": "提议原因"},
            "auto_confirm": {"type": "boolean", "description": "设为 true 时跳过用户确认直接执行（仅限低风险只读诊断命令如 ps/df/which/grep），写操作必须为 false 等待用户确认", "default": False},
        },
        "required": ["action_type", "title", "payload"],
    },
    risk_level="advisory",
    display_name="提议运维动作",
    expose_to_llm=True,
    location="cloud",
    category="propose",
    timeout_seconds=10,
    audit_enabled=True,
    review_gate=True,
)
def propose_action(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    action_type = kwargs.get("action_type")
    title = kwargs.get("title")
    payload = kwargs.get("payload")
    reason = kwargs.get("reason", "")
    user_risk = kwargs.get("risk_level")
    auto_confirm = kwargs.get("auto_confirm", False)

    # Fail Fast: 必填参数缺失立即抛错 (call_mcp_tool 捕获后包装为 error)
    if not action_type:
        raise ValueError("缺少必填参数: action_type")
    if not title:
        raise ValueError("缺少必填参数: title")
    if payload is None:
        raise ValueError("缺少必填参数: payload")
    # Fail Fast: payload 必须是 dict（_parse_text_tool_calls 中 json.loads 失败会回退原字符串，
    # 导致此处收到 str；对字符串做 `in` 会按子串匹配，行为异常，故入口立即拦截非 dict 类型）
    if not isinstance(payload, dict):
        raise ValueError(f"payload 必须是对象(dict), 收到 {type(payload).__name__}")

    # 自动剥离 execute_ 前缀: LLM 常把 "execute_run_command" 当作 action_type 传入
    if action_type.startswith("execute_"):
        action_type = action_type[len("execute_"):]

    # 校验 action_type 合法性 + 收集登记风险等级
    # 只纳入 execute_ 前缀工具, 防 confirm 拼接 execute_{action_type} 时工具名错配导致静默失败
    valid_actions: Dict[str, str] = {}  # action_type -> execute_* risk_level
    for tool in get_internal_tools():
        if not tool.name.startswith("execute_"):
            continue
        valid_actions[_action_type_from_tool_name(tool.name)] = tool.risk_level

    if action_type not in valid_actions:
        _valid_list = sorted(valid_actions.keys())
        raise ValueError(
            f"非法 action_type: '{action_type}'。合法值: {', '.join(_valid_list)}。"
            f"注意 action_type 不要加 execute_ 前缀（如用 run_command 而非 execute_run_command）"
        )

    # 风险等级: 只允许升级不允许降级 — 取 LLM 指定值与登记值中更高者
    # 防止 LLM 把高危操作 (如 execute_restart_service 登记为 high) 标为 low,
    # 让确认 UI 显示低危徽章诱导用户草率确认, 破坏"知情同意"安全控制
    if user_risk and user_risk not in _RISK_ORDER:
        raise ValueError(f"非法 risk_level: {user_risk}, 合法值: low/medium/high/critical")
    registered_risk = valid_actions[action_type]
    if user_risk and _RISK_ORDER[user_risk] > _RISK_ORDER[registered_risk]:
        risk_level = user_risk  # LLM 想升级, 允许 (升级无害, 用户会更谨慎)
    else:
        risk_level = registered_risk  # 用登记值 (防止降级)

    # ── 确定性风险分类器覆盖（复用自愈 _classify_command_risk，不依赖 LLM 自评）──
    # 对 run_command 类型，用自愈的确定性分类器按命令语义硬判定风险等级，
    # 取分类器结果与当前 risk_level 中更高者，确保变更命令不会被标为低危
    if action_type == "run_command":
        _cmd = payload.get("command", "")
        try:
            _cls_risk, _cls_auto = remediation_service._classify_command_risk("run_command", _cmd)
            _RISK_MAP = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            if _RISK_MAP.get(_cls_risk, 2) > _RISK_MAP.get(risk_level, 2):
                risk_level = _cls_risk
        except Exception as _exc3:
            logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)

    # 字段别名兼容: LLM 常把 "service" 误写成 "service_name" 等
    _FIELD_ALIASES = {
        "service": ["service_name"],
        "command": ["command_line", "cmd"],
    }
    for standard_field, aliases in _FIELD_ALIASES.items():
        if standard_field not in payload:
            for alias in aliases:
                if alias in payload:
                    payload[standard_field] = payload.pop(alias)
                    break

    # 方案B: 诊断命令白名单强制 auto_confirm=true
    # LLM 经常忘记设 auto_confirm 或对命令风险误判, 导致只读诊断命令 (ps/df/grep/find 等)
    # 仍卡在确认环节. 代码层判定: action_type=run_command 且命令在只读白名单时, 强制免确认.
    # 写操作 (install/restart/rm 等) 不受影响, 仍走用户确认流程.
    if action_type == "run_command":
        _cmd = payload.get("command", "")
        if _is_read_only_diagnostic_command(_cmd):
            auto_confirm = True

    # ── 生产只读铁闸 ──
    # 目标资产 effective=read-only(生产未豁免)时, 拒绝创建任何待确认写动作。
    # 无论 action_type 是否高危, 一律不放行(查询模式铁闸, 不走人工确认兜底)。
    from app.services.asset_service import assert_ai_writable
    _ro_deny = assert_ai_writable(db, payload)
    if _ro_deny:
        return {"status": "error", "message": _ro_deny, "_read_only_denied": True}

    # payload 必填字段校验: 文档承诺 payload 须符合对应 execute_* 工具参数 schema, 提前拦截畸形 payload
    # confirm 阶段仍会二次校验 (agent_service._validate_payload_schema), 此处为入口防御 + 文档与实现一致性
    exec_tool = get_mcp_tool(f"execute_{action_type}")
    if exec_tool and exec_tool.input_schema:
        required_fields = exec_tool.input_schema.get("required", []) or []
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise ValueError(f"payload 缺少必填字段: {', '.join(missing)}")

    # 返回 _pending_action: 字段与 process_chat_message 检测逻辑对齐
    # call_mcp_tool 包装后: tool_result["result"]["_pending_action"] 即此处的 _pending_action,
    # process_chat_message 据此创建 PendingAction (action_type/title/risk_level/payload).
    return {
        "status": "proposed",
        "_pending_action": {
            "action_type": action_type,
            "title": title,
            "payload": payload,
            "risk_level": risk_level,
            "reason": reason,
            "auto_confirm": auto_confirm,
        },
    }
# ─── SOP 工作流引擎 Tools (AI 触发多步运维剧本) ───
# list_workflow_templates: 枚举可用 SOP 模板 (read_only)
# propose_workflow: 创建 WorkflowRun + NodeRun 并立即执行只读节点, 写操作节点置 awaiting_confirm (advisory)
# 与 propose_action 的区别: propose_action 单步动作, propose_workflow 多步 DAG 编排
# 复用 execute_* 内部工具作为节点动作, 复用 PendingAction 确认理念 (节点 awaiting_confirm 状态)


@register_mcp_tool(
    name="list_workflow_templates",
    description="列出可用的 SOP 工作流模板。AI 助手处理多步骤运维任务时应先调用此工具了解可用剧本，再用 propose_workflow 触发。",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "按分类筛选: disk / service / scaling / healing / custom"},
            "only_enabled": {"type": "boolean", "description": "仅返回已启用模板", "default": True},
        },
    },
    risk_level="read_only",
    display_name="工作流模板",
    location="cloud",
    category="workflow",
)
def list_workflow_templates(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import workflow_service
        category = kwargs.get("category") or None
        only_enabled = bool(kwargs.get("only_enabled", True))
        result = workflow_service.list_templates(db, category=category, only_enabled=only_enabled)
        templates = result.get("items", []) if isinstance(result, dict) else (result or [])
        return {
            "count": len(templates),
            "templates": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t["description"],
                    "category": t["category"],
                    "trigger_type": t["trigger_type"],
                    "risk_level": t["risk_level"],
                    "nodes_count": len(t.get("nodes", [])),
                    "enabled": t["enabled"],
                }
                for t in templates
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="propose_workflow",
    description="提议执行一个 SOP 工作流。会立即创建工作流实例并自动执行只读步骤，写操作步骤会暂停等待用户在前端确认。AI 助手处理多步骤运维任务时应优先用此工具，而非逐步 propose_action。",
    input_schema={
        "type": "object",
        "properties": {
            "template_id": {"type": "integer", "description": "SOP 模板 ID（可选，无则需提供 nodes/edges）"},
            "title": {"type": "string", "description": "工作流标题"},
            "context": {"type": "object", "description": "运行时上下文（asset_id、告警信息等），用于渲染节点 payload 模板"},
            "nodes": {"type": "array", "description": "自定义节点（无 template_id 时必填），每项含 id/name/action_type/payload_template/requires_confirm/retry_count"},
            "edges": {"type": "array", "description": "自定义边（无 template_id 时必填），每项含 source/target"},
        },
        "required": ["title"],
    },
    risk_level="advisory",
    display_name="提议工作流",
    location="cloud",
    category="workflow",
)
def propose_workflow(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import workflow_service
        template_id = kwargs.get("template_id")
        title = kwargs.get("title")
        context = kwargs.get("context") or {}
        custom_nodes = kwargs.get("nodes")
        custom_edges = kwargs.get("edges")

        if not title:
            raise ValueError("缺少必填参数: title")
        if not template_id and not custom_nodes:
            raise ValueError("必须提供 template_id 或自定义 nodes")

        run, err = workflow_service.start_workflow_run(
            db,
            template_id=template_id,
            title=title,
            context=context,
            trigger_source="ai",
            session_id=None,
            custom_nodes=custom_nodes,
            custom_edges=custom_edges,
        )
        if err:
            return {"status": "error", "message": err}

        run_data = workflow_service.get_run(db, run.id)
        node_summary = []
        awaiting = []
        for nr in run_data.get("node_runs", []):
            node_summary.append({"node_id": nr["node_id"], "name": nr["node_name"], "status": nr["status"], "requires_confirm": nr["requires_confirm"]})
            if nr["status"] == "awaiting_confirm":
                awaiting.append({"node_run_id": nr["id"], "node_id": nr["node_id"], "name": nr["node_name"]})

        return {
            "status": "created",
            "run_id": run.id,
            "title": run.title,
            "workflow_status": run.status,
            "node_count": len(node_summary),
            "awaiting_confirm_count": len(awaiting),
            "awaiting_confirm_nodes": awaiting,
            "message": f"工作流 #{run.id} 已创建，只读步骤自动执行中，{len(awaiting)} 个写操作步骤待确认",
            "_pending_workflow": {"run_id": run.id, "title": run.title},
        }
    finally:
        if close_db:
            db.close()
# ─── 智能体编排工作流 MCP 工具 (Coze 风格) ───
# list_agent_workflows: 枚举已发布的智能体工作流 (read_only)
# run_agent_workflow: 执行智能体工作流，AI 在画布编排的 LLM/知识库/工具/条件分支节点链 (advisory)


@register_mcp_tool(
    name="list_agent_workflows",
    description="列出可用的智能体编排工作流（Coze 风格可视化编排）。AI 助手处理复杂多步骤任务时可调用此工具了解可用智能体，再用 run_agent_workflow 触发。",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "按分类筛选: analysis / chatbot / healing / report / generic"},
            "only_enabled": {"type": "boolean", "description": "仅返回已启用工作流", "default": True},
        },
    },
    risk_level="read_only",
    display_name="Agent 工作流列表",
    location="cloud",
    category="workflow",
)
def list_agent_workflows(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import agent_workflow_service
        category = kwargs.get("category") or None
        only_enabled = bool(kwargs.get("only_enabled", True))
        workflows = agent_workflow_service.list_workflows(db, category=category, only_enabled=only_enabled)
        return {
            "count": len(workflows),
            "workflows": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "description": w["description"],
                    "category": w["category"],
                    "trigger_type": w["trigger_type"],
                    "nodes_count": len(w.get("nodes", [])),
                    "inputs_schema": w.get("inputs_schema", []),
                }
                for w in workflows
            ],
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="run_agent_workflow",
    description="执行一个智能体编排工作流。工作流会按画布编排的节点顺序执行（LLM 推理/知识库检索/工具调用/条件分支等），返回最终输出。AI 助手处理复杂多步骤推理任务时应优先用此工具。",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "integer", "description": "智能体工作流 ID"},
            "inputs": {"type": "object", "description": "工作流输入参数，对应 start 节点定义的 inputs schema"},
        },
        "required": ["workflow_id", "inputs"],
    },
    risk_level="advisory",
    display_name="运行 Agent 工作流",
    location="cloud",
    category="workflow",
)
def run_agent_workflow(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        from app.services import agent_workflow_service
        workflow_id = kwargs.get("workflow_id")
        inputs = kwargs.get("inputs") or {}

        if not workflow_id:
            raise ValueError("缺少必填参数: workflow_id")

        run, err = agent_workflow_service.start_workflow_run(
            db,
            workflow_id=workflow_id,
            inputs=inputs,
            trigger_source="ai",
            session_id=None,
        )
        if err:
            return {"status": "error", "message": err}

        run_data = agent_workflow_service.get_run(db, run.id)
        node_summary = []
        for nr in run_data.get("node_runs", []):
            node_summary.append({
                "node_id": nr["node_id"],
                "name": nr["node_name"],
                "type": nr["node_type"],
                "status": nr["status"],
            })

        return {
            "status": "completed" if run.status == "completed" else run.status,
            "run_id": run.id,
            "workflow_status": run.status,
            "outputs": run_data.get("outputs", {}),
            "node_count": len(node_summary),
            "nodes": node_summary,
            "error": run_data.get("error", ""),
            "message": f"智能体工作流 #{run.id} 执行完成，状态: {run.status}",
        }
    finally:
        if close_db:
            db.close()
# ─── 后台任务 Tools ──────────────────────────────────────────────

@register_mcp_tool(
    name="get_task_status",
    description="查询后台异步任务的最新状态（进度/结果/错误），LLM 应定期轮询此工具获取长耗时任务（如安装、部署）的执行进度",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "后台任务 ID（由 propose_action 返回的 job_id）"},
        },
        "required": ["job_id"],
    },
    risk_level="read_only",
    display_name="任务状态",
    expose_to_llm=True,
    location="cloud",
    category="task",
)
def get_task_status(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.background_task import get_background_job
    job_id = kwargs.get("job_id")
    if not job_id:
        raise ValueError("缺少必填参数: job_id")
    result = get_background_job(job_id)
    if not result:
        return {"error": f"任务 {job_id} 未找到"}
    return result


@register_mcp_tool(
    name="list_recent_tasks",
    description="列出最近执行的后台任务（当前会话），用于查看有哪些任务在后台运行或刚结束",
    input_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "integer", "description": "会话 ID，不传则查所有"},
            "limit": {"type": "integer", "description": "返回数量上限", "default": 20},
        },
    },
    risk_level="read_only",
    display_name="最近任务",
    expose_to_llm=True,
    location="cloud",
    category="task",
)
def list_recent_tasks(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.background_task import list_running_jobs
    session_id = kwargs.get("session_id")
    limit = kwargs.get("limit", 20)
    jobs = list_running_jobs(session_id=session_id, limit=limit)
    return {"tasks": jobs, "count": len(jobs)}


@register_mcp_tool(
    name="execute_install_package",
    description="在远程资产上异步安装软件包（支持 Elasticsearch/Nginx/MySQL 等），任务在后台执行不受 LLM 超时限制，通过 get_task_status 轮询进度。安装完成后自动返回最终结果",
    input_schema={
        "type": "object",
        "properties": {
            "package_name": {"type": "string", "description": "软件包名，如 elasticsearch、nginx、mysql"},
            "asset_id": {"type": "integer", "description": "目标资产 ID（CMDB 资产记录，必须为 online 状态且连接类型为 ssh）"},
            "version": {"type": "string", "description": "版本号，如 8.19.0（不传则默认安装可用版本）"},
            "install_type": {"type": "string", "description": "安装方式: package（系统包）/ binary（二进制tar.gz）/ docker，默认 binary"},
            "options": {
                "type": "object",
                "description": "高级选项",
                "properties": {
                    "os_type": {"type": "string", "description": "操作系统类型: auto / debian / rhel / alpine，默认 auto（自动检测）"},
                    "extra_packages": {"type": "array", "items": {"type": "string"}, "description": "额外需要安装的依赖包"},
                    "start_service": {"type": "boolean", "description": "安装后是否启动服务，默认 true"},
                    "open_ports": {"type": "array", "items": {"type": "integer"}, "description": "需要开放的端口"},
                },
            },
        },
        "required": ["package_name", "asset_id"],
    },
    risk_level="critical",
    display_name="安装软件包",
    expose_to_llm=False,  # 不直调，必须经 propose_action,
    location="edge",
    category="execute_host",
)
def execute_install_package(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        package_name = kwargs.get("package_name")
        asset_id = kwargs.get("asset_id")
        version = kwargs.get("version", "latest")
        install_type = kwargs.get("install_type", "binary")
        options = kwargs.get("options", {})

        if not package_name:
            raise ValueError("缺少必填参数: package_name")
        if asset_id is None:
            raise ValueError("缺少必填参数: asset_id")

        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            raise ValueError(f"资产 id={asset_id} 不存在")
        if asset.status != "online":
            raise ValueError(f"资产 {asset.name} 当前状态为 {asset.status}，仅 online 资产可操作")
        if asset.connection_type != "ssh":
            raise ValueError(f"资产 {asset.name} 连接类型为 {asset.connection_type}，仅 ssh 类型支持。对于数据库(database)类型资产，请使用 mysql action_type 通过 SQL 操作。")

        # 提交后台任务
        from app.services.background_task import submit_install_job
        job_id = submit_install_job(
            package_name=package_name,
            asset_id=int(asset_id),
            version=version,
            options={**options, "install_type": install_type},
            session_id=None,
            pending_action_id=None,
        )
        return {
            "status": "success",
            "message": f"安装任务已提交，job_id={job_id}",
            "data": {
                "job_id": job_id,
                "package": package_name,
                "asset_id": asset_id,
                "ip": asset.ip,
                "status": "pending",
                "hint": "使用 get_task_status(job_id=...) 轮询任务进度",
            },
        }
    finally:
        if close_db:
            db.close()
