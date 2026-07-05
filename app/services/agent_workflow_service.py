"""智能体编排工作流执行引擎（Coze 风格）

8 种节点执行器：start / end / llm / knowledge / tool / condition / code / http
变量传递：Jinja2 渲染 + runtime_context.nodes[node_id].output 引用
条件分支：求值表达式路由到匹配分支
"""
import json
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from jinja2 import Environment, BaseLoader, TemplateSyntaxError
from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import (
    AgentWorkflow, AgentWorkflowRun, AgentWorkflowNodeRun,
    AIProvider, ChatSession,
)
from app.services.mcp_registry import call_mcp_tool, get_internal_tools
from app.services.mcp_tools import _get_db  # 复用 db helper

_jinja_env = Environment(loader=BaseLoader(), autoescape=False)


def _now():
    return datetime.now()


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
    result = call_llm(provider, messages, timeout_override=60)
    if "error" in result:
        return {"output": {}, "status": "failed", "error": result["error"]}

    text = result.get("content", "") or result.get("message", "")
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


def _exec_tool(node_data: Dict, runtime_context: Dict, db: Session) -> Dict:
    tool_name = node_data.get("tool_name", "")
    parameters = _render_value(node_data.get("parameters", {}), runtime_context)
    if not tool_name:
        return {"output": {}, "status": "failed", "error": "未指定 tool_name"}

    try:
        result = call_mcp_tool(tool_name, parameters, db=db, allow_internal=True)
        status = result.get("status", "success")
        rdata = result.get("result", result)
        if status == "error":
            return {"output": {}, "status": "failed", "error": result.get("message", "")}
        return {"output": rdata if isinstance(rdata, dict) else {"data": rdata}, "status": "completed"}
    except Exception as e:
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

    _advance_run(db, run.id)
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run.id).first()
    return run, ""


def _advance_run(db: Session, run_id: int):
    """调度执行节点。"""
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run or run.status != AgentWorkflowRun.STATUS_RUNNING:
        return

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
        if not nr or nr.status != AgentWorkflowNodeRun.STATUS_PENDING:
            continue
        deps = _node_dependencies(nid, edges)
        completed_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_COMPLETED}
        failed_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_FAILED}
        skipped_deps = {d for d in deps if nr_map.get(d) and nr_map[d].status == AgentWorkflowNodeRun.STATUS_SKIPPED}

        if failed_deps or skipped_deps:
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue
        if not deps.issubset(completed_deps):
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
            result = executor(node_data, runtime_context, db)
            nr.output = json.dumps(result.get("output", {}), ensure_ascii=False)
            nr.status = result.get("status", "completed")
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


def abort_run(db: Session, run_id: int, reason: str = "") -> Dict:
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == run_id).first()
    if not run:
        return {"success": False, "message": "工作流实例不存在"}
    if run.status in (AgentWorkflowRun.STATUS_COMPLETED, AgentWorkflowRun.STATUS_FAILED, AgentWorkflowRun.STATUS_ABORTED):
        return {"success": False, "message": f"工作流已处于终态 {run.status}"}
    node_runs = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.run_id == run_id).all()
    for nr in node_runs:
        if nr.status in (AgentWorkflowRun.STATUS_PENDING, AgentWorkflowRun.STATUS_RUNNING):
            nr.status = AgentWorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
    db.commit()
    _finalize_run(db, run_id, AgentWorkflowRun.STATUS_ABORTED, reason or "用户手动中止")
    return {"success": True, "message": "工作流已中止"}


def retry_node(db: Session, node_run_id: int) -> Dict:
    nr = db.query(AgentWorkflowNodeRun).filter(AgentWorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"success": False, "message": "节点不存在"}
    if nr.status != AgentWorkflowNodeRun.STATUS_FAILED:
        return {"success": False, "message": f"节点状态为 {nr.status}，仅失败节点可重试"}
    run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == nr.run_id).first()
    if not run:
        return {"success": False, "message": "工作流实例不存在"}
    nr.status = AgentWorkflowNodeRun.STATUS_PENDING
    nr.output = "{}"
    nr.error = ""
    nr.started_at = None
    nr.completed_at = None
    db.commit()
    if run.status in (AgentWorkflowRun.STATUS_FAILED, AgentWorkflowRun.STATUS_COMPLETED, AgentWorkflowRun.STATUS_ABORTED):
        run.status = AgentWorkflowRun.STATUS_RUNNING
        db.commit()
    _advance_run(db, run.id)
    return {"success": True, "message": "节点已重试"}


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
                {"id": "tool1", "type": "tool", "name": "查询告警", "data": {"tool_name": "query_alerts", "parameters": {"alert_id": "{{ inputs.alert_id }}", "limit": 1}}},
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
                {"id": "tool1", "type": "tool", "name": "查询告警", "data": {"tool_name": "query_alerts", "parameters": {"alert_id": "{{ inputs.alert_id }}", "limit": 1}}},
                {"id": "llm1", "type": "llm", "name": "决策分析", "data": {"system_prompt": "你是 AIOps 决策引擎，根据告警判断处置方式。只输出一个词：自愈、升级、通知。", "user_prompt": "告警: {{ nodes.tool1.output | tojson }}", "temperature": 0.1, "max_tokens": 50}},
                {"id": "cond1", "type": "condition", "name": "决策分支", "data": {"branches": [{"condition": "{{ nodes.llm1.output.text contains '自愈' }}", "target": "heal"}, {"condition": "{{ nodes.llm1.output.text contains '升级' }}", "target": "escalate"}, {"condition": "default", "target": "notify"}]}},
                {"id": "heal", "type": "tool", "name": "执行自愈", "data": {"tool_name": "query_alerts", "parameters": {"limit": 1}}},
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
                {"id": "tool1", "type": "tool", "name": "查询指标", "data": {"tool_name": "query_metrics", "parameters": {"asset_id": "{{ inputs.asset_id }}", "metric_name": "cpu_usage", "limit": 24}}},
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
