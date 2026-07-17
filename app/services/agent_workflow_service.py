"""智能体编排工作流执行引擎（Coze 风格）

8 种节点执行器：start / end / llm / knowledge / tool / condition / code / http
变量传递：Jinja2 渲染 + runtime_context.nodes[node_id].output 引用
条件分支：求值表达式路由到匹配分支
"""
import json
import re
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from jinja2 import Environment, BaseLoader, TemplateSyntaxError
from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import (
    AgentWorkflow, AgentWorkflowRun, AgentWorkflowNodeRun,
    AIProvider, ChatSession, PendingAction, WorkflowAuditLog,
)
from app.services.mcp_registry import call_mcp_tool, get_internal_tools
from app.services.mcp_tools import _get_db  # 复用 db helper

_jinja_env = Environment(loader=BaseLoader(), autoescape=False)


def _now():
    return datetime.now()


def _audit(db: Session, run_id: Optional[int] = None, node_run_id: Optional[int] = None,
           workflow_id: Optional[int] = None, action: str = "", operator: str = "",
           tool_name: str = "", execution_mode: str = "", risk_level: str = "",
           detail: Optional[Dict] = None):
    """写入工作流操作审计日志（不可抵赖）。"""
    try:
        log = WorkflowAuditLog(
            run_id=run_id, node_run_id=node_run_id, workflow_id=workflow_id,
            action=action, operator=operator or "",
            tool_name=tool_name or "", execution_mode=execution_mode or "",
            risk_level=risk_level or "",
            detail=json.dumps(detail or {}, ensure_ascii=False),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        from app.logger import logger
        logger.warning(f"审计日志写入失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# ─── 序列化 ───
def _serialize_workflow(wf: AgentWorkflow) -> Dict:
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description or "",
        "category": wf.category or "generic",
        "nodes": wf.get_nodes(),
        "edges": wf.get_edges(),
        "inputs_schema": wf.get_inputs_schema(),
        "outputs_schema": wf.get_outputs_schema(),
        "enabled": bool(wf.enabled),
        "published": bool(wf.published),
        "trigger_type": wf.trigger_type or "manual",
        "created_at": str(wf.created_at) if wf.created_at else None,
        "updated_at": str(wf.updated_at) if wf.updated_at else None,
    }


def _serialize_run(run: AgentWorkflowRun, node_runs: Optional[List[AgentWorkflowNodeRun]] = None) -> Dict:
    data = {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "session_id": run.session_id,
        "status": run.status,
        "inputs": run.get_inputs(),
        "runtime_context": run.get_runtime_context(),
        "outputs": run.get_outputs(),
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by or "",
        "error": run.error or "",
        "started_at": str(run.started_at) if run.started_at else None,
        "completed_at": str(run.completed_at) if run.completed_at else None,
        "created_at": str(run.created_at) if run.created_at else None,
    }
    if node_runs is not None:
        data["node_runs"] = [_serialize_node_run(nr) for nr in node_runs]
    return data


def _serialize_node_run(nr: AgentWorkflowNodeRun) -> Dict:
    return {
        "id": nr.id,
        "run_id": nr.run_id,
        "node_id": nr.node_id,
        "node_type": nr.node_type,
        "node_name": nr.node_name,
        "config": nr.get_config(),
        "status": nr.status,
        "output": nr.get_output(),
        "error": nr.error or "",
        "requires_confirm": nr.requires_confirm,
        "pending_action_id": nr.pending_action_id,
        "started_at": str(nr.started_at) if nr.started_at else None,
        "completed_at": str(nr.completed_at) if nr.completed_at else None,
    }


# ─── 拓扑排序 + 依赖 ───
def topological_sort(nodes: List[Dict], edges: List[Dict]) -> List[str]:
    from collections import deque, defaultdict
    node_ids = [n.get("id") for n in nodes if n.get("id")]
    indeg = {nid: 0 for nid in node_ids}
    adj = defaultdict(list)
    for e in edges:
        s = e.get("source") or e.get("from")
        t = e.get("target") or e.get("to")
        if s in indeg and t in indeg:
            adj[s].append(t)
            indeg[t] += 1
    queue = deque([nid for nid in node_ids if indeg[nid] == 0])
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    for nid in node_ids:
        if nid not in order:
            order.append(nid)
    return order


def _node_dependencies(node_id: str, edges: List[Dict]) -> set:
    deps = set()
    for e in edges:
        s = e.get("source") or e.get("from")
        t = e.get("target") or e.get("to")
        if t == node_id and s:
            deps.add(s)
    return deps


# ─── Jinja2 渲染 ───
def _render_value(value: Any, runtime_context: Dict) -> Any:
    """递归渲染 Jinja2 模板。字符串含 {{ }} 则渲染，dict/list 递归。"""
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            try:
                return _jinja_env.from_string(value).render(**runtime_context)
            except (TemplateSyntaxError, Exception):
                return value
        return value
    if isinstance(value, dict):
        return {k: _render_value(v, runtime_context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(v, runtime_context) for v in value]
    return value


# ─── 条件表达式求值 ───
def _eval_condition(expr: str, runtime_context: Dict) -> bool:
    """简化条件表达式求值。支持: contains / eq / ne / gt / lt / in / startswith / default"""
    expr = expr.strip()
    if expr == "default" or expr == "true" or expr == "True":
        return True
    # 提取 {{ }} 内的表达式
    m = re.match(r"^\{\{(.+)\}\}$", expr.strip())
    if m:
        expr = m.group(1).strip()
    # contains: A contains B
    m = re.match(r"(.+?)\s+contains\s+(.+)", expr)
    if m:
        left = _eval_operand(m.group(1).strip(), runtime_context)
        right = _eval_operand(m.group(2).strip(), runtime_context)
        try:
            return str(right) in str(left)
        except Exception:
            return False
    # eq / ne / gt / lt
    for op, pyop in [(" eq ", " == "), (" ne ", " != "), (" gt ", " > "), (" lt ", " < "),
                     ("==", "=="), ("!=", "!="), (">", ">"), ("<", "<")]:
        if op in expr:
            parts = expr.split(op)
            if len(parts) == 2:
                left = _eval_operand(parts[0].strip(), runtime_context)
                right = _eval_operand(parts[1].strip(), runtime_context)
                try:
                    if pyop == "==": return str(left) == str(right)
                    if pyop == "!=": return str(left) != str(right)
                    if pyop == ">": return float(left) > float(right)
                    if pyop == "<": return float(left) < float(right)
                except Exception:
                    return False
    # startswith
    m = re.match(r"(.+?)\s+startswith\s+(.+)", expr)
    if m:
        left = _eval_operand(m.group(1).strip(), runtime_context)
        right = _eval_operand(m.group(2).strip(), runtime_context)
        try:
            return str(left).startswith(str(right))
        except Exception:
            return False
    # 纯布尔/Python 表达式
    try:
        return bool(_jinja_env.from_string("{{ " + expr + " }}").render(**runtime_context))
    except Exception:
        return False


def _eval_operand(operand: str, runtime_context: Dict) -> Any:
    operand = operand.strip()
    # 引号字符串
    if (operand.startswith("'") and operand.endswith("'")) or (operand.startswith('"') and operand.endswith('"')):
        return operand[1:-1]
    # 数字
    try:
        if "." in operand:
            return float(operand)
        return int(operand)
    except ValueError:
        pass
    # 变量路径 nodes.xxx.output.yyy
    try:
        val = _jinja_env.from_string("{{ " + operand + " }}").render(**runtime_context)
        if val == "" and not operand.startswith("'"):
            return operand
        return val
    except Exception:
        return operand


# ─── 节点执行器 ───
def _exec_start(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    inputs = runtime_context.get("inputs", {})
    return {"output": inputs, "status": "completed"}


def _exec_end(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    outputs = {}
    for out in node_data.get("outputs", []):
        key = out.get("key", "result")
        value_template = out.get("value", "")
        outputs[key] = _render_value(value_template, runtime_context)
    return {"output": outputs, "status": "completed"}


def _exec_llm(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    provider_id = node_data.get("provider_id")
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first() if provider_id else None
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"output": {}, "status": "failed", "error": "无可用 AI Provider"}

    system_prompt = _render_value(node_data.get("system_prompt", ""), runtime_context)
    user_prompt = _render_value(node_data.get("user_prompt", ""), runtime_context)
    model = node_data.get("model") or provider.default_model or "gpt-4o"
    temperature = float(node_data.get("temperature", 0.3))
    max_tokens = int(node_data.get("max_tokens", 2000))

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    from app.services.agent_service import call_llm
    result = call_llm(provider, messages, timeout_override=120)
    if "error" in result:
        return {"output": {}, "status": "failed", "error": result["error"]}

    text = ""
    if result.get("choices"):
        choices = result["choices"]
        if choices and "message" in choices[0]:
            text = choices[0]["message"].get("content", "") or ""
        elif "text" in choices[0]:
            text = choices[0].get("text", "") or ""
    if isinstance(text, list):
        text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
    usage = result.get("usage", {})

    return {
        "output": {"text": text, "usage": usage, "model": model},
        "status": "completed",
    }


def _exec_knowledge(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    query = _render_value(node_data.get("query", ""), runtime_context)
    kb_id = node_data.get("kb_id")
    top_k = int(node_data.get("top_k", 5))
    score_threshold = float(node_data.get("score_threshold", 0.5))

    try:
        result = call_mcp_tool("query_knowledge_rag", {
            "query": query,
            "kb_id": kb_id,
            "top_k": top_k,
            "score_threshold": score_threshold,
        }, db=db, allow_internal=True)
        status = result.get("status", "success")
        rdata = result.get("result", result)
        if status == "error":
            return {"output": {}, "status": "failed", "error": result.get("message", "")}
        return {"output": rdata if isinstance(rdata, dict) else {"data": rdata}, "status": "completed"}
    except Exception as e:
        return {"output": {}, "status": "failed", "error": f"知识库检索异常: {e}"}


def _exec_tool(node_data: Dict, runtime_context: Dict, db: Session, node_run: Optional[AgentWorkflowNodeRun] = None) -> Dict:
    tool_name = node_data.get("tool_name", "")
    parameters = _render_value(node_data.get("parameters", {}), runtime_context)
    if not tool_name:
        return {"output": {}, "status": "failed", "error": "未指定 tool_name"}

    # 读取工具真实风险等级
    from app.services.mcp_registry import get_mcp_tool
    tool_info = get_mcp_tool(tool_name)
    tool_risk = tool_info.risk_level if tool_info else "read_only"
    title = tool_info.description if tool_info else tool_name

    execution_mode = node_data.get("execution_mode", "confirm")
    forced_confirm = False
    # 危险操作拦截：high/critical 工具强制回到 confirm 模式，禁止 auto
    if tool_risk in ("high", "critical") and execution_mode == "auto":
        execution_mode = "confirm"
        forced_confirm = True

    # 等待确认模式：创建 PendingAction 暂停工作流
    if execution_mode == "confirm" and node_run:
        reason = f"工作流节点需确认后执行（风险等级: {tool_risk}）"
        if forced_confirm:
            reason += "；该工具为高危操作，已自动从「自动执行」降级为「等待确认」"
        pa = PendingAction(
            session_id=None,
            run_id=node_run.run_id,
            node_run_id=node_run.id,
            action_type=tool_name,
            title=f"[工作流] {title}",
            risk_level=tool_risk,
            reason=reason,
            action_payload=json.dumps(parameters, ensure_ascii=False),
            status=PendingAction.STATUS_PENDING,
        )
        db.add(pa)
        db.flush()

        node_run.pending_action_id = pa.id
        node_run.requires_confirm = True
        node_run.status = AgentWorkflowNodeRun.STATUS_AWAITING_CONFIRM
        db.commit()

        # 审计：高危强制降级确认
        if forced_confirm:
            _audit(db, run_id=node_run.run_id, node_run_id=node_run.id,
                   action=WorkflowAuditLog.ACTION_NODE_FORCE_CONFIRM,
                   tool_name=tool_name, execution_mode="auto", risk_level=tool_risk,
                   detail={"reason": "high/critical 工具自动模式已降级为确认", "parameters": parameters})

        return {
            "output": {"_pending_action": {"id": pa.id, "title": title}, "_forced_confirm": forced_confirm},
            "status": "awaiting_confirm",
            "pending_action_id": pa.id,
        }

    try:
        result = call_mcp_tool(tool_name, parameters, db=db, allow_internal=True)
        status = result.get("status", "success")
        rdata = result.get("result", result)
        # 审计：自动执行记录（不可抵赖）
        if execution_mode == "auto" and node_run:
            _audit(db, run_id=node_run.run_id, node_run_id=node_run.id,
                   action=WorkflowAuditLog.ACTION_NODE_AUTO_EXEC,
                   tool_name=tool_name, execution_mode="auto", risk_level=tool_risk,
                   detail={"parameters": parameters, "status": status,
                           "result_summary": str(rdata)[:500] if rdata else ""})
        if status == "error":
            return {"output": {}, "status": "failed", "error": result.get("message", "")}
        return {"output": rdata if isinstance(rdata, dict) else {"data": rdata}, "status": "completed"}
    except Exception as e:
        if execution_mode == "auto" and node_run:
            _audit(db, run_id=node_run.run_id, node_run_id=node_run.id,
                   action=WorkflowAuditLog.ACTION_NODE_AUTO_EXEC,
                   tool_name=tool_name, execution_mode="auto", risk_level=tool_risk,
                   detail={"parameters": parameters, "status": "error", "error": str(e)})
        return {"output": {}, "status": "failed", "error": f"工具调用异常: {e}"}


def _exec_condition(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    branches = node_data.get("branches", [])
    for branch in branches:
        cond = branch.get("condition", "default")
        target = branch.get("target", "")
        if _eval_condition(cond, runtime_context):
            return {"output": {"matched_branch": target, "condition": cond}, "status": "completed"}
    return {"output": {"matched_branch": None, "condition": "default"}, "status": "completed"}


_SAFE_BUILTINS = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "range": range, "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "sorted": sorted, "reversed": reversed, "any": any, "all": all,
    "isinstance": isinstance, "type": type,
    "True": True, "False": False, "None": None,
}


def _exec_code(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    code = node_data.get("code", "")
    inputs_mapping = node_data.get("inputs_mapping", {})
    inputs = {}
    for k, v in inputs_mapping.items():
        inputs[k] = _render_value(v, runtime_context)

    safe_globals = {"__builtins__": _SAFE_BUILTINS, "inputs": inputs, "result": None}
    safe_locals = {}
    # 禁止危险关键字
    for kw in ["import", "exec", "eval", "open", "__", "os.", "subprocess", "socket", "system"]:
        if kw in code:
            return {"output": {}, "status": "failed", "error": f"代码包含禁止关键字: {kw}"}

    try:
        exec(code, safe_globals, safe_locals)
        result = safe_globals.get("result", safe_locals.get("result"))
        return {"output": {"result": result}, "status": "completed"}
    except Exception as e:
        return {"output": {}, "status": "failed", "error": f"代码执行失败: {e}"}


def _exec_http(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    method = _render_value(node_data.get("method", "GET"), runtime_context)
    url = _render_value(node_data.get("url", ""), runtime_context)
    headers = _render_value(node_data.get("headers", {}), runtime_context)
    body = _render_value(node_data.get("body", {}), runtime_context)
    timeout = int(node_data.get("timeout", 10))

    if not url:
        return {"output": {}, "status": "failed", "error": "未指定 url"}

    try:
        resp = requests.request(
            method=method, url=url,
            headers=headers if isinstance(headers, dict) else {},
            json=body if isinstance(body, dict) else (body if body else None),
            timeout=timeout,
        )
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text
        return {
            "output": {"status_code": resp.status_code, "body": resp_body, "headers": dict(resp.headers)},
            "status": "completed" if resp.status_code < 400 else "failed",
            "error": "" if resp.status_code < 400 else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        return {"output": {}, "status": "failed", "error": f"HTTP 请求异常: {e}"}


NODE_EXECUTORS = {
    "start": _exec_start,
    "end": _exec_end,
    "llm": _exec_llm,
    "knowledge": _exec_knowledge,
    "tool": _exec_tool,
    "condition": _exec_condition,
    "code": _exec_code,
    "http": _exec_http,
}


# ─── 工作流 CRUD ───
def list_workflows(db: Session, category: Optional[str] = None, only_enabled: bool = False) -> List[Dict]:
    q = db.query(AgentWorkflow)
    if category:
        q = q.filter(AgentWorkflow.category == category)
    if only_enabled:
        q = q.filter(AgentWorkflow.enabled == True)
    return [_serialize_workflow(w) for w in q.order_by(AgentWorkflow.id.desc()).all()]


def get_workflow(db: Session, workflow_id: int) -> Optional[Dict]:
    w = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
    return _serialize_workflow(w) if w else None


def create_workflow(db: Session, data: Dict) -> Dict:
    w = AgentWorkflow(
        name=data.get("name", ""),
        description=data.get("description", ""),
        category=data.get("category", "generic"),
        nodes=json.dumps(data.get("nodes", []), ensure_ascii=False),
        edges=json.dumps(data.get("edges", []), ensure_ascii=False),
        inputs_schema=json.dumps(data.get("inputs_schema", []), ensure_ascii=False),
        outputs_schema=json.dumps(data.get("outputs_schema", []), ensure_ascii=False),
        enabled=bool(data.get("enabled", True)),
        published=bool(data.get("published", False)),
        trigger_type=data.get("trigger_type", "manual"),
        trigger_condition=json.dumps(data.get("trigger_condition", {}), ensure_ascii=False),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return _serialize_workflow(w)


def update_workflow(db: Session, workflow_id: int, data: Dict) -> Optional[Dict]:
    w = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
    if not w:
        return None
    for field in ["name", "description", "category", "trigger_type"]:
        if field in data:
            setattr(w, field, data[field])
    if "enabled" in data:
        w.enabled = bool(data["enabled"])
    if "published" in data:
        w.published = bool(data["published"])
    if "nodes" in data:
        w.nodes = json.dumps(data["nodes"], ensure_ascii=False)
    if "edges" in data:
        w.edges = json.dumps(data["edges"], ensure_ascii=False)
    if "inputs_schema" in data:
        w.inputs_schema = json.dumps(data["inputs_schema"], ensure_ascii=False)
    if "outputs_schema" in data:
        w.outputs_schema = json.dumps(data["outputs_schema"], ensure_ascii=False)
    if "trigger_condition" in data:
        w.trigger_condition = json.dumps(data["trigger_condition"], ensure_ascii=False)
    db.commit()
    db.refresh(w)
    return _serialize_workflow(w)


def delete_workflow(db: Session, workflow_id: int) -> bool:
    w = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
    if not w:
        return False
    db.delete(w)
    db.commit()
    return True


# ─── 执行 ───
def start_workflow_run(
    db: Session,
    workflow_id: Optional[int],
    inputs: Dict,
    trigger_source: str = "api",
    session_id: Optional[int] = None,
    custom_nodes: Optional[List[Dict]] = None,
    custom_edges: Optional[List[Dict]] = None,
    triggered_by: str = "",
) -> Tuple[Optional[AgentWorkflowRun], str]:
    """创建 Run + 全部 NodeRun，立即执行。返回 (run, error_msg)。"""
    nodes = []
    edges = []
    snapshot = {}
    if workflow_id:
        wf = db.query(AgentWorkflow).filter(AgentWorkflow.id == workflow_id).first()
        if not wf:
            return None, f"工作流 {workflow_id} 不存在"
        nodes = wf.get_nodes()
        edges = wf.get_edges()
        snapshot = _serialize_workflow(wf)
    else:
        nodes = custom_nodes or []
        edges = custom_edges or []

    if not nodes:
        return None, "工作流没有节点"

    # 校验节点类型
    for n in nodes:
        nt = n.get("type", "")
        if nt not in NODE_EXECUTORS:
            return None, f"节点 {n.get('id')} 类型 '{nt}' 不合法，可用: {', '.join(NODE_EXECUTORS.keys())}"

    run = AgentWorkflowRun(
        workflow_id=workflow_id,
        workflow_snapshot=json.dumps(snapshot, ensure_ascii=False),
        session_id=session_id,
        status=AgentWorkflowRun.STATUS_RUNNING,
        inputs=json.dumps(inputs or {}, ensure_ascii=False),
        runtime_context=json.dumps({"inputs": inputs or {}, "nodes": {}}, ensure_ascii=False),
        trigger_source=trigger_source,
        triggered_by=triggered_by,
        started_at=_now(),
    )
    db.add(run)
    db.flush()

    for n in nodes:
        nr = AgentWorkflowNodeRun(
            run_id=run.id,
            node_id=n.get("id", ""),
            node_type=n.get("type", ""),
            node_name=n.get("name", n.get("data", {}).get("label", "")),
            config=json.dumps(n.get("data", {}), ensure_ascii=False),
            status=AgentWorkflowNodeRun.STATUS_PENDING,
        )
        db.add(nr)
    db.commit()

    # 审计：工作流启动（记录触发人，不可抵赖）
    auto_nodes = [n.get("data", {}).get("tool_name", "") for n in nodes
                  if n.get("type") == "tool" and n.get("data", {}).get("execution_mode") == "auto"]
    _audit(db, run_id=run.id, workflow_id=workflow_id,
           action=WorkflowAuditLog.ACTION_RUN_START, operator=triggered_by,
           detail={"trigger_source": trigger_source, "inputs": inputs,
                   "auto_tool_nodes": auto_nodes})

    # 异步执行：后台线程用独立 db session 跑节点，API 立即返回 run_id
    _run_id = run.id
    _db_mode = get_db_mode()

    def _bg_advance():
        bg_db = get_session_for(_db_mode)()
        try:
            _advance_run(bg_db, _run_id)
        except Exception as e:
            try:
                _finalize_run(bg_db, _run_id, AgentWorkflowRun.STATUS_FAILED, f"后台执行异常: {e}")
            except Exception:
                pass
            from app.logger import logger
            logger.error(f"run#{_run_id} 后台执行异常: {e}")
        finally:
            bg_db.close()

    t = threading.Thread(target=_bg_advance, daemon=True)
    t.start()

    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run.id).first()
    return run, ""


def _advance_run(db: Session, run_id: int):
    """调度执行节点。"""
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run or run.status not in (AgentWorkflowRun.STATUS_RUNNING, AgentWorkflowRun.STATUS_AWAITING_CONFIRM):
        return
    # 从等待确认恢复：继续推进后续节点
    if run.status == AgentWorkflowRun.STATUS_AWAITING_CONFIRM:
        run.status = AgentWorkflowRun.STATUS_RUNNING
        db.commit()

    node_runs = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.run_id == run_id).all()
    if not node_runs:
        _finalize_run(db, run_id, AgentWorkflowRun.STATUS_COMPLETED, "")
        return

    nr_map = {nr.node_id: nr for nr in node_runs}
    runtime_context = run.get_runtime_context()

    # 从 snapshot 或 node_runs 重建 nodes/edges
    snapshot = run.get_workflow_snapshot()
    nodes = snapshot.get("nodes", []) if snapshot else []
    edges = snapshot.get("edges", []) if snapshot else []
    if not nodes:
        # 无 snapshot（自定义工作流），从 node_runs 重建
        nodes = [{"id": nr.node_id, "type": nr.node_type, "data": nr.get_config()} for nr in node_runs]
        # edges 无法重建，存入 runtime_context（start_workflow_run 已存入 snapshot 为空）
        edges = runtime_context.get("_edges", [])

    order = topological_sort(nodes, edges)
    node_data_map = {n.get("id"): n for n in nodes}

    progressed = False
    for nid in order:
        nr = nr_map.get(nid)
        # 跳过非 pending 节点（含 awaiting_confirm——已暂停的节点等确认/取消）
        if not nr or nr.status != AgentWorkflowNodeRun.STATUS_PENDING:
            continue
        deps = _node_dependencies(nid, edges)
        completed_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_COMPLETED}
        failed_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_FAILED}
        skipped_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_SKIPPED}

        # 上游有失败 → 跳过当前节点
        if failed_deps:
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue
        # 多分支汇聚：部分依赖被 condition 路由 skip，但至少一个 completed → 继续执行
        if skipped_deps and not completed_deps:
            # 所有依赖都被 skip → 跳过
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue
        if skipped_deps and completed_deps:
            # 部分 skip 部分 completed → 多分支汇聚，继续执行
            pass
        elif not deps.issubset(completed_deps):
            # 还有 pending 依赖未完成 → 等待
            continue

        # 条件分支路由检查：如果上游是 condition 节点，检查是否路由到当前节点
        condition_branch_match = True
        for d in deps:
            d_nr = nr_map.get(d)
            if d_nr and d_nr.node_type == "condition":
                d_output = d_nr.get_output()
                matched = d_output.get("matched_branch")
                if matched and matched != nid:
                    condition_branch_match = False
                    break
        if not condition_branch_match:
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue

        # 执行节点
        node = node_data_map.get(nid, {})
        node_data = node.get("data", nr.get_config())
        nr.status = AgentWorkflowNodeRun.STATUS_RUNNING
        nr.started_at = _now()
        db.commit()

        executor = NODE_EXECUTORS.get(nr.node_type)
        if not executor:
            nr.status = AgentWorkflowNodeRun.STATUS_FAILED
            nr.error = f"未知节点类型: {nr.node_type}"
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue

        try:
            if nr.node_type == "tool":
                result = executor(node_data, runtime_context, db, node_run=nr)
            else:
                result = executor(node_data, runtime_context, db)
            result_status = result.get("status", "completed")
            if result_status == "awaiting_confirm":
                nr.status = AgentWorkflowNodeRun.STATUS_AWAITING_CONFIRM
                nr.output = json.dumps(result.get("output", {}), ensure_ascii=False)
                nr.completed_at = None
                db.commit()
                # 暂停工作流，等用户确认
                run.status = AgentWorkflowRun.STATUS_AWAITING_CONFIRM
                db.commit()
                return  # 停止推进
            nr.output = json.dumps(result.get("output", {}), ensure_ascii=False)
            nr.status = result_status
            nr.error = result.get("error", "")
            nr.completed_at = _now()
        except Exception as e:
            nr.status = AgentWorkflowNodeRun.STATUS_FAILED
            nr.error = f"执行异常: {e}\n{traceback.format_exc()[-500:]}"
            nr.completed_at = _now()
        db.commit()
        progressed = True

        # 更新 runtime_context
        runtime_context.setdefault("nodes", {})[nid] = {"output": nr.get_output()}
        run.runtime_context = json.dumps(runtime_context, ensure_ascii=False)
        db.commit()

    # 检查是否全部完成
    all_done = all(nr.status in (
        AgentWorkflowNodeRun.STATUS_COMPLETED, AgentWorkflowNodeRun.STATUS_FAILED, AgentWorkflowNodeRun.STATUS_SKIPPED
    ) for nr in node_runs)

    if all_done:
        any_failed = any(nr.status == AgentWorkflowNodeRun.STATUS_FAILED for nr in node_runs)
        # 提取 end 节点输出作为 run outputs
        outputs = {}
        for nr in node_runs:
            if nr.node_type == "end" and nr.status == AgentWorkflowNodeRun.STATUS_COMPLETED:
                outputs = nr.get_output()
                break
        run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
        run.outputs = json.dumps(outputs, ensure_ascii=False)
        _finalize_run(db, run_id,
                      AgentWorkflowRun.STATUS_FAILED if any_failed else AgentWorkflowRun.STATUS_COMPLETED,
                      "" if not any_failed else "部分节点失败")


def _finalize_run(db: Session, run_id: int, status: str, message: str):
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run:
        return
    run.status = status
    run.completed_at = _now()
    if message:
        run.error = message
    db.commit()


def abort_run(db: Session, run_id: int, reason: str = "", operator: str = "") -> Dict:
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}
    if run.status in (AgentWorkflowRun.STATUS_COMPLETED, AgentWorkflowRun.STATUS_FAILED, AgentWorkflowRun.STATUS_ABORTED):
        return {"is_success": False, "message": f"工作流已处于终态 {run.status}"}
    node_runs = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.run_id == run_id).all()
    for nr in node_runs:
        if nr.status in (AgentWorkflowRun.STATUS_PENDING, AgentWorkflowRun.STATUS_RUNNING):
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
    db.commit()
    _finalize_run(db, run_id, AgentWorkflowRun.STATUS_ABORTED, reason or "用户手动中止")
    _audit(db, run_id=run_id, action=WorkflowAuditLog.ACTION_RUN_ABORT, operator=operator,
           detail={"reason": reason or "用户手动中止"})
    return {"is_success": True, "message": "工作流已中止"}


def retry_node(db: Session, node_run_id: int, operator: str = "") -> Dict:
    nr = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != AgentWorkflowNodeRun.STATUS_FAILED:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，仅失败节点可重试"}
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == nr.run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}
    nr.status = AgentWorkflowNodeRun.STATUS_PENDING
    nr.output = "{}"
    nr.error = ""
    nr.started_at = None
    nr.completed_at = None
    db.commit()
    if run.status in (AgentWorkflowRun.STATUS_FAILED, AgentWorkflowRun.STATUS_COMPLETED, AgentWorkflowRun.STATUS_ABORTED):
        run.status = AgentWorkflowRun.STATUS_RUNNING
        db.commit()
    _audit(db, run_id=run.id, node_run_id=nr.id,
           action=WorkflowAuditLog.ACTION_NODE_RETRY, operator=operator,
           detail={"node_name": nr.node_name})
    _advance_run(db, run.id)
    return {"is_success": True, "message": "节点已重试"}


def confirm_workflow_node(db: Session, node_run_id: int, user_name: str) -> Dict:
    """确认执行工作流中的待确认节点。"""
    nr = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != AgentWorkflowNodeRun.STATUS_AWAITING_CONFIRM:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，无法确认"}
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == nr.run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}

    pending_action = None
    if nr.pending_action_id:
        pending_action = db.query(PendingAction).filter(PendingAction.id == nr.pending_action_id).first()
        if pending_action and pending_action.status == PendingAction.STATUS_PENDING:
            pending_action.status = PendingAction.STATUS_CONFIRMED
            pending_action.confirmed_by = user_name
            pending_action.confirmed_at = datetime.now()
            db.commit()

    # 执行工具
    node_data = nr.get_config()
    runtime_context = run.get_runtime_context()
    tool_name = node_data.get("tool_name", "")
    parameters = _render_value(node_data.get("parameters", {}), runtime_context)

    try:
        result = call_mcp_tool(tool_name, parameters, db=db, allow_internal=True)
        rstatus = result.get("status", "success")
        rdata = result.get("result", result)
        if rstatus == "error":
            nr.status = AgentWorkflowNodeRun.STATUS_FAILED
            nr.error = result.get("message", "")
            nr.completed_at = _now()
            nr.output = "{}"
            db.commit()
            if pending_action:
                pending_action.status = PendingAction.STATUS_FAILED
                pending_action.result_payload = json.dumps({"error": result.get("message", "")}, ensure_ascii=False)
                db.commit()
            _audit(db, run_id=run.id, node_run_id=nr.id,
                   action=WorkflowAuditLog.ACTION_NODE_CONFIRM, operator=user_name,
                   tool_name=tool_name, execution_mode="confirm",
                   risk_level=pending_action.risk_level if pending_action else "",
                   detail={"parameters": parameters, "status": "failed", "error": result.get("message", "")})
            _advance_run(db, run.id)
            return {"is_success": False, "message": result.get("message", "")}

        output = rdata if isinstance(rdata, dict) else {"data": rdata}
        nr.status = AgentWorkflowNodeRun.STATUS_COMPLETED
        nr.output = json.dumps(output, ensure_ascii=False)
        nr.completed_at = _now()
        db.commit()

        if pending_action:
            pending_action.status = PendingAction.STATUS_EXECUTED
            pending_action.result_payload = json.dumps(output, ensure_ascii=False)
            db.commit()

        # 更新 runtime_context 并继续推进
        runtime_context.setdefault("nodes", {})[nr.node_id] = {"output": output}
        run.runtime_context = json.dumps(runtime_context, ensure_ascii=False)
        db.commit()
        _audit(db, run_id=run.id, node_run_id=nr.id,
               action=WorkflowAuditLog.ACTION_NODE_CONFIRM, operator=user_name,
               tool_name=tool_name, execution_mode="confirm",
               risk_level=pending_action.risk_level if pending_action else "",
               detail={"parameters": parameters, "status": "completed", "result_summary": str(output)[:500]})
        _advance_run(db, run.id)
        return {"is_success": True, "message": "执行完成"}
    except Exception as e:
        nr.status = AgentWorkflowNodeRun.STATUS_FAILED
        nr.error = f"执行异常: {e}"
        nr.completed_at = _now()
        nr.output = "{}"
        db.commit()
        if pending_action:
            pending_action.status = PendingAction.STATUS_FAILED
            pending_action.result_payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
        _audit(db, run_id=run.id, node_run_id=nr.id,
               action=WorkflowAuditLog.ACTION_NODE_CONFIRM, operator=user_name,
               tool_name=tool_name, execution_mode="confirm",
               risk_level=pending_action.risk_level if pending_action else "",
               detail={"parameters": parameters, "status": "error", "error": str(e)})
        _advance_run(db, run.id)
        return {"is_success": False, "message": f"执行异常: {e}"}


def cancel_workflow_node(db: Session, node_run_id: int, operator: str = "") -> Dict:
    """取消执行工作流中的待确认节点，标记为已跳过。"""
    nr = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != AgentWorkflowNodeRun.STATUS_AWAITING_CONFIRM:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，无法取消"}

    if nr.pending_action_id:
        pa = db.query(PendingAction).filter(PendingAction.id == nr.pending_action_id).first()
        if pa and pa.status == PendingAction.STATUS_PENDING:
            pa.status = PendingAction.STATUS_CANCELED
            db.commit()

    nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
    nr.completed_at = _now()
    nr.error = "用户已取消"
    db.commit()

    # 审计：取消确认
    node_data = nr.get_config()
    _audit(db, run_id=nr.run_id, node_run_id=nr.id,
           action=WorkflowAuditLog.ACTION_NODE_CANCEL, operator=operator,
           tool_name=node_data.get("tool_name", ""),
           detail={"reason": "用户取消执行"})

    # 继续推进工作流
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == nr.run_id).first()
    if run:
        _advance_run(db, run.id)
    return {"is_success": True, "message": "已取消"}


def list_runs(db: Session, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    q = db.query(AgentWorkflowRun)
    if status:
        q = q.filter(AgentWorkflowRun.status == status)
    runs = q.order_by(AgentWorkflowRun.id.desc()).limit(limit).all()
    result = []
    for r in runs:
        node_runs = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.run_id == r.id).all()
        result.append(_serialize_run(r, node_runs))
    return result


def get_run(db: Session, run_id: int) -> Optional[Dict]:
    r = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not r:
        return None
    node_runs = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.run_id == run_id).all()
    return _serialize_run(r, node_runs)


def export_run_pdf(db: Session, run_id: int) -> Optional[bytes]:
    """生成工作流执行报告 PDF，支持 Markdown 格式渲染，确保不溢出纸张。"""
    from fpdf import FPDF

    def _safe_text(s: str, max_chunk: int = 40) -> str:
        """超长无空格字符串按固定长度插入空格，避免 multi_cell 宽度不足报错。"""
        if len(s) <= max_chunk:
            return s
        return " ".join(s[i:i + max_chunk] for i in range(0, len(s), max_chunk))

    def _wrap_cjk(text: str, max_width: float) -> str:
        """逐字符测量宽度并手动换行，解决 fpdf2 multi_cell 对 CJK 宽度计算不精确导致溢出。"""
        if not text:
            return text
        lines_out = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines_out.append("")
                continue
            current = ""
            for char in paragraph:
                trial = current + char
                if pdf.get_string_width(trial) > max_width and current:
                    lines_out.append(current)
                    current = char
                else:
                    current = trial
            if current:
                lines_out.append(current)
        return "\n".join(lines_out)

    import re as _re

    def _strip_emoji(s: str) -> str:
        """移除 emoji 字符（msyh 字体不含 emoji 字形，会导致子集化警告）。"""
        return _re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF]", "", s)

    def _strip_md_inline(s: str) -> str:
        """移除行内 Markdown 标记（**bold**、`code`），保留纯文本内容。"""
        s = _re.sub(r"\*\*(.+?)\*\*", r"\1", s)   # **bold** → bold
        s = _re.sub(r"`(.+?)`", r"\1", s)          # `code` → code
        s = _re.sub(r"\*(.+?)\*", r"\1", s)         # *italic* → italic
        return s

    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run:
        return None

    outputs = run.get_outputs()
    report_text = ""
    if outputs:
        for k, v in outputs.items():
            v_str = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            if k == "report" or not report_text:
                report_text = v_str

    # A4 纵向，统一边距
    pdf = FPDF(format="A4")
    import os as _os
    _proj = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    _fonts_dir = _os.path.join(_proj, "fonts")
    _regular = _os.path.join(_fonts_dir, "msyh.ttc")
    _bold = _os.path.join(_fonts_dir, "msyhbd.ttc")
    pdf.add_font("YaHei", "", _regular)
    pdf.add_font("YaHei", "B", _bold)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    _page_w = pdf.w - pdf.l_margin - pdf.r_margin  # 可用宽度

    pdf.add_page()
    pdf.set_font("YaHei", "B", 16)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 12, f"\u5de1\u68c0\u62a5\u544a #{run.id}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    if report_text:
        for line in report_text.split("\n"):
            line = line.rstrip()
            if not line:
                pdf.ln(4)
                continue
            # Markdown 标题
            if line.startswith("### "):
                pdf.set_font("YaHei", "B", 11)
                pdf.set_text_color(99, 102, 241)
                for wl in _wrap_cjk(_strip_emoji(line[4:]), _page_w).split("\n"):
                    pdf.cell(0, 6, wl, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("YaHei", "", 10)
                pdf.set_text_color(30, 41, 59)
            elif line.startswith("#### "):
                pdf.set_font("YaHei", "B", 10)
                pdf.set_text_color(99, 102, 241)
                for wl in _wrap_cjk(_strip_emoji(line[5:]), _page_w).split("\n"):
                    pdf.cell(0, 5.5, wl, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("YaHei", "", 10)
                pdf.set_text_color(30, 41, 59)
            elif line.startswith("## "):
                pdf.set_font("YaHei", "B", 12)
                pdf.set_text_color(99, 102, 241)
                for wl in _wrap_cjk(_strip_emoji(line[3:]), _page_w).split("\n"):
                    pdf.cell(0, 7, wl, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("YaHei", "", 10)
                pdf.set_text_color(30, 41, 59)
            elif line.startswith("# "):
                pdf.set_font("YaHei", "B", 14)
                pdf.set_text_color(99, 102, 241)
                for wl in _wrap_cjk(_strip_emoji(line[2:]), _page_w).split("\n"):
                    pdf.cell(0, 7, wl, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("YaHei", "", 10)
                pdf.set_text_color(30, 41, 59)
            elif line.startswith("---"):
                pdf.set_draw_color(200, 210, 220)
                y = pdf.get_y()
                pdf.line(pdf.l_margin, y, pdf.l_margin + _page_w, y)
                pdf.ln(3)
            elif line.startswith("**") and line.endswith("**") and len(line) > 4:
                # 粗体整行
                pdf.set_font("YaHei", "B", 10)
                for wl in _wrap_cjk(_strip_emoji(line.strip("*")), _page_w).split("\n"):
                    pdf.cell(0, 5.5, wl, new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("YaHei", "", 10)
            else:
                # 普通正文：清理行内 Markdown 标记和 emoji，保证宽度安全
                pdf.set_font("YaHei", "", 10)
                pdf.set_text_color(30, 41, 59)
                clean = _strip_md_inline(_strip_emoji(line))
                for wl in _wrap_cjk(clean, _page_w).split("\n"):
                    pdf.cell(0, 5.5, wl, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font("YaHei", "", 10)
        pdf.set_text_color(100, 116, 139)
        for wl in _wrap_cjk("\u672c\u6b21\u6267\u884c\u672a\u4ea7\u51fa\u62a5\u544a\u5185\u5bb9", _page_w).split("\n"):
            pdf.cell(0, 6, wl, new_x="LMARGIN", new_y="NEXT")

    from datetime import datetime as _dt
    pdf.ln(6)
    pdf.set_font("YaHei", "", 7)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5, f"AIOps  \u5bfc\u51fa\u65f6\u95f4: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")

    return pdf.output()


def seed_agent_workflows(db: Session):
    """幂等播种 5 个预置智能体工作流模板。按 name 去重。"""
    existing_names = {w.name for w in db.query(AgentWorkflow).all()}
    presets = _preset_workflows()
    added = 0
    for p in presets:
        if p["name"] in existing_names:
            continue
        w = AgentWorkflow(
            name=p["name"],
            description=p.get("description", ""),
            category=p.get("category", "generic"),
            nodes=json.dumps(p.get("nodes", []), ensure_ascii=False),
            edges=json.dumps(p.get("edges", []), ensure_ascii=False),
            inputs_schema=json.dumps(p.get("inputs_schema", []), ensure_ascii=False),
            outputs_schema=json.dumps(p.get("outputs_schema", []), ensure_ascii=False),
            enabled=bool(p.get("enabled", True)),
            published=bool(p.get("published", True)),
            trigger_type=p.get("trigger_type", "manual"),
        )
        db.add(w)
        added += 1
    if added:
        db.commit()
    return added


def _preset_workflows() -> List[Dict]:
    return [
        {
            "name": "智能告警根因分析",
            "description": "查询告警 → RAG 检索知识库 → LLM 分析根因 → 输出结论",
            "category": "analysis",
            "trigger_type": "alert_auto",
            "enabled": True,
            "published": True,
            "inputs_schema": [{"key": "alert_id", "type": "integer", "required": True, "desc": "告警 ID"}],
            "outputs_schema": [{"key": "analysis", "value": "{{ nodes.llm1.output.text }}"}],
            "nodes": [
                {"id": "start", "type": "start", "name": "开始", "data": {"inputs": [{"key": "alert_id", "type": "integer", "required": True}]}},
                {"id": "tool1", "type": "tool", "name": "查询告警", "data": {"tool_name": "query_alerts", "execution_mode": "auto", "parameters": {"alert_id": "{{ inputs.alert_id }}", "limit": 1}}},
                {"id": "kb1", "type": "knowledge", "name": "检索知识库", "data": {"query": "{{ nodes.tool1.output.alerts[0].name if nodes.tool1.output.alerts else '告警' }}", "top_k": 5, "score_threshold": 0.5}},
                {"id": "llm1", "type": "llm", "name": "根因分析", "data": {"system_prompt": "你是 AIOps 运维专家，根据告警信息和知识库文档分析根因，给出处置建议。", "user_prompt": "告警信息: {{ nodes.tool1.output | tojson }}\n\n知识库文档: {{ nodes.kb1.output | tojson }}\n\n请分析根因并给出处置建议。", "temperature": 0.3, "max_tokens": 2000}},
                {"id": "end", "type": "end", "name": "结束", "data": {"outputs": [{"key": "analysis", "value": "{{ nodes.llm1.output.text }}"}]}},
            ],
            "edges": [
                {"source": "start", "target": "tool1"},
                {"source": "tool1", "target": "kb1"},
                {"source": "kb1", "target": "llm1"},
                {"source": "llm1", "target": "end"},
            ],
        },
        {
            "name": "智能运维问答",
            "description": "用户提问 → RAG 检索知识库 → LLM 生成回答",
            "category": "chatbot",
            "trigger_type": "chat",
            "enabled": True,
            "published": True,
            "inputs_schema": [{"key": "question", "type": "string", "required": True, "desc": "用户问题"}],
            "outputs_schema": [{"key": "answer", "value": "{{ nodes.llm1.output.text }}"}],
            "nodes": [
                {"id": "start", "type": "start", "name": "开始", "data": {"inputs": [{"key": "question", "type": "string", "required": True}]}},
                {"id": "kb1", "type": "knowledge", "name": "检索知识库", "data": {"query": "{{ inputs.question }}", "top_k": 5, "score_threshold": 0.5}},
                {"id": "llm1", "type": "llm", "name": "生成回答", "data": {"system_prompt": "你是 AIOps 运维助手，根据知识库文档回答用户问题。若知识库无相关信息，请说明。", "user_prompt": "用户问题: {{ inputs.question }}\n\n知识库文档: {{ nodes.kb1.output | tojson }}", "temperature": 0.3, "max_tokens": 1500}},
                {"id": "end", "type": "end", "name": "结束", "data": {"outputs": [{"key": "answer", "value": "{{ nodes.llm1.output.text }}"}]}},
            ],
            "edges": [
                {"source": "start", "target": "kb1"},
                {"source": "kb1", "target": "llm1"},
                {"source": "llm1", "target": "end"},
            ],
        },
        {
            "name": "故障自愈决策",
            "description": "查询告警 → LLM 决策处置方式 → 条件分支 → 自愈/升级/通知",
            "category": "healing",
            "trigger_type": "alert_auto",
            "enabled": True,
            "published": True,
            "inputs_schema": [{"key": "alert_id", "type": "integer", "required": True, "desc": "告警 ID"}],
            "outputs_schema": [{"key": "decision", "value": "{{ nodes.cond1.output.matched_branch }}"}, {"key": "reason", "value": "{{ nodes.llm1.output.text }}"}],
            "nodes": [
                {"id": "start", "type": "start", "name": "开始", "data": {"inputs": [{"key": "alert_id", "type": "integer", "required": True}]}},
                {"id": "tool1", "type": "tool", "name": "查询告警", "data": {"tool_name": "query_alerts", "execution_mode": "auto", "parameters": {"alert_id": "{{ inputs.alert_id }}", "limit": 1}}},
                {"id": "llm1", "type": "llm", "name": "决策分析", "data": {"system_prompt": "你是 AIOps 决策引擎，根据告警判断处置方式。只输出一个词：自愈、升级、通知。", "user_prompt": "告警: {{ nodes.tool1.output | tojson }}", "temperature": 0.1, "max_tokens": 50}},
                {"id": "cond1", "type": "condition", "name": "决策分支", "data": {"branches": [{"condition": "{{ nodes.llm1.output.text contains '自愈' }}", "target": "heal"}, {"condition": "{{ nodes.llm1.output.text contains '升级' }}", "target": "escalate"}, {"condition": "default", "target": "notify"}]}},
                {"id": "heal", "type": "tool", "name": "执行自愈", "data": {"tool_name": "query_alerts", "execution_mode": "auto", "parameters": {"limit": 1}}},
                {"id": "escalate", "type": "llm", "name": "生成升级报告", "data": {"system_prompt": "生成升级报告", "user_prompt": "告警需升级: {{ nodes.tool1.output | tojson }}", "temperature": 0.3, "max_tokens": 500}},
                {"id": "notify", "type": "code", "name": "生成通知", "data": {"code": "result = {'message': '已通知值班人员', 'alert': inputs.get('alert_info', {})}", "inputs_mapping": {"alert_info": "{{ nodes.tool1.output | tojson }}"}}},
                {"id": "end", "type": "end", "name": "结束", "data": {"outputs": [{"key": "decision", "value": "{{ nodes.cond1.output.matched_branch }}"}, {"key": "reason", "value": "{{ nodes.llm1.output.text }}"}]}},
            ],
            "edges": [
                {"source": "start", "target": "tool1"},
                {"source": "tool1", "target": "llm1"},
                {"source": "llm1", "target": "cond1"},
                {"source": "cond1", "target": "heal"},
                {"source": "cond1", "target": "escalate"},
                {"source": "cond1", "target": "notify"},
                {"source": "heal", "target": "end"},
                {"source": "escalate", "target": "end"},
                {"source": "notify", "target": "end"},
            ],
        },
        {
            "name": "变更影响评估",
            "description": "查询变更 → RAG 检索 → LLM 评估影响",
            "category": "analysis",
            "trigger_type": "manual",
            "enabled": True,
            "published": True,
            "inputs_schema": [{"key": "change_id", "type": "integer", "required": True, "desc": "变更单 ID"}],
            "outputs_schema": [{"key": "assessment", "value": "{{ nodes.llm1.output.text }}"}],
            "nodes": [
                {"id": "start", "type": "start", "name": "开始", "data": {"inputs": [{"key": "change_id", "type": "integer", "required": True}]}},
                {"id": "kb1", "type": "knowledge", "name": "检索变更知识", "data": {"query": "变更影响评估 {{ inputs.change_id }}", "top_k": 5, "score_threshold": 0.4}},
                {"id": "llm1", "type": "llm", "name": "影响评估", "data": {"system_prompt": "你是变更管理专家，评估变更对系统的影响，给出风险等级和建议。", "user_prompt": "变更 ID: {{ inputs.change_id }}\n\n相关知识: {{ nodes.kb1.output | tojson }}", "temperature": 0.3, "max_tokens": 1000}},
                {"id": "end", "type": "end", "name": "结束", "data": {"outputs": [{"key": "assessment", "value": "{{ nodes.llm1.output.text }}"}]}},
            ],
            "edges": [
                {"source": "start", "target": "kb1"},
                {"source": "kb1", "target": "llm1"},
                {"source": "llm1", "target": "end"},
            ],
        },
        {
            "name": "巡检报告生成",
            "description": "查询指标 → LLM 生成巡检报告",
            "category": "report",
            "trigger_type": "scheduled",
            "enabled": True,
            "published": True,
            "inputs_schema": [{"key": "asset_id", "type": "integer", "required": False, "desc": "资产 ID"}],
            "outputs_schema": [{"key": "report", "value": "{{ nodes.llm1.output.text }}"}],
            "nodes": [
                {"id": "start", "type": "start", "name": "开始", "data": {"inputs": [{"key": "asset_id", "type": "integer", "required": False}]}},
                {"id": "tool1", "type": "tool", "name": "查询指标", "data": {"tool_name": "query_metrics", "execution_mode": "auto", "parameters": {"asset_id": "{{ inputs.asset_id }}", "metric_name": "cpu_usage", "limit": 24}}},
                {"id": "llm1", "type": "llm", "name": "生成报告", "data": {"system_prompt": "你是运维巡检专家，根据指标数据生成巡检报告，包含异常点、趋势分析、建议。", "user_prompt": "最近 24 小时指标: {{ nodes.tool1.output | tojson }}", "temperature": 0.3, "max_tokens": 1500}},
                {"id": "end", "type": "end", "name": "结束", "data": {"outputs": [{"key": "report", "value": "{{ nodes.llm1.output.text }}"}]}},
            ],
            "edges": [
                {"source": "start", "target": "tool1"},
                {"source": "tool1", "target": "llm1"},
                {"source": "llm1", "target": "end"},
            ],
        },
    ]
