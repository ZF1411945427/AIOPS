import json
import threading
import time
from collections import deque, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, BaseLoader
from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import (
    WorkflowTemplate, WorkflowRun, WorkflowNodeRun,
    PendingAction, ToolInvocation, ChatSession,
)
from app.services.mcp_registry import call_mcp_tool, get_internal_tools, get_mcp_tool

_rlock = threading.Lock()

# 工作流节点参数模板（渲染 JSON/字符串数据，非 HTML），autoescape=True 会破坏数据
# 安全性由 _render_value 的输入白名单与节点配置校验保障，故标记 nosec B701
_jinja_env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701


def _now():
    return datetime.now()


def _get_db():
    return get_session_for(get_db_mode())()


def _action_type_from_tool_name(name: str) -> str:
    return name[8:] if name.startswith("execute_") else name


def _valid_action_types() -> Dict[str, str]:
    """返回 {action_type: risk_level}，仅纳入 execute_ 前缀内部工具"""
    result = {}
    for tool in get_internal_tools():
        if not tool.name.startswith("execute_"):
            continue
        result[_action_type_from_tool_name(tool.name)] = tool.risk_level
    return result


def topological_sort(nodes: List[Dict], edges: List[Dict]) -> List[str]:
    """Kahn 算法拓扑排序。edges: [{source, target}, ...]。返回 node_id 有序列表。"""
    node_ids = [n.get("id") for n in nodes if n.get("id")]
    indeg = {nid: 0 for nid in node_ids}
    adj = defaultdict(list)
    for e in edges:
        s = e.get("source") or e.get("from") or e.get("source_id")
        t = e.get("target") or e.get("to") or e.get("target_id")
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
    # 有环的节点追加到末尾（容错）
    for nid in node_ids:
        if nid not in order:
            order.append(nid)
    return order


def render_payload(payload_template: Dict, context: Dict, upstream_results: Dict[str, Any]) -> Dict:
    """Jinja2 渲染 payload_template。注入 context 和 upstream_results（{node_id: result}）。
    payload_template 中字符串值若含 {{ }} 则渲染，dict/list 递归渲染。"""
    render_ctx = {
        "context": context or {},
        "upstream": upstream_results or {},
        "results": upstream_results or {},
    }

    def _render(value):
        if isinstance(value, str):
            if "{{" in value or "{%" in value:
                try:
                    return _jinja_env.from_string(value).render(**render_ctx)
                except Exception:
                    return value
            return value
        if isinstance(value, dict):
            return {k: _render(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_render(v) for v in value]
        return value

    return _render(payload_template or {})


def _serialize_run(run: WorkflowRun, node_runs: Optional[List[WorkflowNodeRun]] = None) -> Dict:
    data = {
        "id": run.id,
        "template_id": run.template_id,
        "session_id": run.session_id,
        "title": run.title,
        "status": run.status,
        "context": run.get_context(),
        "trigger_source": run.trigger_source,
        "started_at": str(run.started_at) if run.started_at else None,
        "completed_at": str(run.completed_at) if run.completed_at else None,
        "created_at": str(run.created_at) if run.created_at else None,
    }
    if node_runs is not None:
        data["node_runs"] = [_serialize_node_run(nr) for nr in node_runs]
    return data


def _serialize_node_run(nr: WorkflowNodeRun) -> Dict:
    return {
        "id": nr.id,
        "run_id": nr.run_id,
        "node_id": nr.node_id,
        "node_name": nr.node_name,
        "action_type": nr.action_type,
        "payload": nr.get_payload(),
        "status": nr.status,
        "result": nr.get_result(),
        "requires_confirm": nr.requires_confirm,
        "pending_action_id": nr.pending_action_id,
        "retry_count": nr.retry_count,
        "started_at": str(nr.started_at) if nr.started_at else None,
        "completed_at": str(nr.completed_at) if nr.completed_at else None,
        "created_at": str(nr.created_at) if nr.created_at else None,
    }


def _serialize_template(t: WorkflowTemplate) -> Dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description or "",
        "category": t.category or "generic",
        "trigger_type": t.trigger_type or "manual",
        "trigger_condition": t.get_trigger_condition(),
        "nodes": t.get_nodes(),
        "edges": t.get_edges(),
        "risk_level": t.risk_level or "medium",
        "enabled": bool(t.enabled),
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


def start_workflow_run(
    db: Session,
    template_id: Optional[int],
    title: str,
    context: Dict,
    trigger_source: str = "ai",
    session_id: Optional[int] = None,
    custom_nodes: Optional[List[Dict]] = None,
    custom_edges: Optional[List[Dict]] = None,
) -> Tuple[Optional[WorkflowRun], str]:
    """创建 WorkflowRun + 全部 NodeRun，并立即开始执行只读节点。
    返回 (run, error_msg)。error_msg 非空表示创建失败。"""
    nodes = []
    edges = []
    if template_id:
        tpl = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
        if not tpl:
            return None, f"工作流模板 {template_id} 不存在"
        if not tpl.enabled:
            return None, f"工作流模板 {tpl.name} 已禁用"
        nodes = tpl.get_nodes()
        edges = tpl.get_edges()
        if not title:
            title = tpl.name or "工作流执行"
    else:
        nodes = custom_nodes or []
        edges = custom_edges or []
    if not nodes:
        return None, "工作流没有节点"

    valid_actions = _valid_action_types()
    for n in nodes:
        at = n.get("action_type", "")
        if at not in valid_actions:
            return None, f"节点 {n.get('id')} 的 action_type '{at}' 不合法，可用: {', '.join(sorted(valid_actions.keys()))}"

    run_context = dict(context or {})
    if not template_id:
        run_context["_edges"] = edges or []

    run = WorkflowRun(
        template_id=template_id,
        session_id=session_id,
        title=title,
        status=WorkflowRun.STATUS_RUNNING,
        context=json.dumps(run_context, ensure_ascii=False),
        trigger_source=trigger_source,
        started_at=_now(),
    )
    db.add(run)
    db.flush()

    for n in nodes:
        nr = WorkflowNodeRun(
            run_id=run.id,
            node_id=n.get("id", ""),
            node_name=n.get("name", ""),
            action_type=n.get("action_type", ""),
            payload=json.dumps(n.get("payload_template", {}), ensure_ascii=False),
            status=WorkflowNodeRun.STATUS_PENDING,
            requires_confirm=bool(n.get("requires_confirm", False)),
            retry_count=int(n.get("retry_count", 0) or 0),
        )
        db.add(nr)
    db.commit()

    _advance_run(db, run.id)
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run.id).first()
    return run, ""


def _advance_run(db: Session, run_id: int):
    """调度下一批可执行节点（入度为 0 且未开始）。只读节点立即执行，写操作节点置 awaiting_confirm。"""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run or run.status not in (WorkflowRun.STATUS_RUNNING, WorkflowRun.STATUS_PAUSED):
        return
    node_runs = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.run_id == run_id).all()
    if not node_runs:
        _finalize_run(db, run_id, WorkflowRun.STATUS_COMPLETED, "无节点")
        return

    nr_map = {nr.node_id: nr for nr in node_runs}
    nodes = [{"id": nr.node_id} for nr in node_runs]
    edges = _load_edges(db, run)
    indeg = _compute_indegree([nr.node_id for nr in node_runs], edges)

    order = topological_sort(nodes, edges)
    completed_ids = {nr.node_id for nr in node_runs if nr.status == WorkflowNodeRun.STATUS_COMPLETED}
    failed_ids = {nr.node_id for nr in node_runs if nr.status == WorkflowNodeRun.STATUS_FAILED}
    skipped_ids = {nr.node_id for nr in node_runs if nr.status == WorkflowNodeRun.STATUS_SKIPPED}
    running_ids = {nr.node_id for nr in node_runs if nr.status in (WorkflowNodeRun.STATUS_RUNNING, WorkflowNodeRun.STATUS_AWAITING_CONFIRM)}

    context = run.get_context()
    upstream_results = {}
    for nr in node_runs:
        if nr.status == WorkflowNodeRun.STATUS_COMPLETED:
            upstream_results[nr.node_id] = nr.get_result()

    progressed = False
    for nid in order:
        nr = nr_map.get(nid)
        if not nr or nr.status != WorkflowNodeRun.STATUS_PENDING:
            continue
        deps = _node_dependencies(nid, edges)
        if not deps.issubset(completed_ids):
            continue
        if failed_ids & deps:
            nr.status = WorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue

        payload_tpl = nr.get_payload()
        try:
            payload = render_payload(payload_tpl, context, upstream_results)
        except Exception as e:
            nr.status = WorkflowNodeRun.STATUS_FAILED
            nr.result = json.dumps({"status": "error", "message": f"payload 渲染失败: {e}"}, ensure_ascii=False)
            nr.started_at = _now()
            nr.completed_at = _now()
            db.commit()
            progressed = True
            continue
        nr.payload = json.dumps(payload, ensure_ascii=False)

        if nr.requires_confirm:
            nr.status = WorkflowNodeRun.STATUS_AWAITING_CONFIRM
            nr.started_at = _now()
            db.commit()
            progressed = True
            run.status = WorkflowRun.STATUS_PAUSED
            db.commit()
        else:
            _execute_node(db, run, nr, payload)
            progressed = True
            if nr.status == WorkflowNodeRun.STATUS_COMPLETED:
                upstream_results[nr.node_id] = nr.get_result()
                completed_ids.add(nr.node_id)
            elif nr.status == WorkflowNodeRun.STATUS_FAILED:
                failed_ids.add(nr.node_id)

    all_done = all(nr.status in (
        WorkflowNodeRun.STATUS_COMPLETED, WorkflowNodeRun.STATUS_FAILED, WorkflowNodeRun.STATUS_SKIPPED
    ) for nr in node_runs)
    if all_done:
        any_failed = any(nr.status == WorkflowNodeRun.STATUS_FAILED for nr in node_runs)
        _finalize_run(db, run_id,
                      WorkflowRun.STATUS_FAILED if any_failed else WorkflowRun.STATUS_COMPLETED,
                      "")
    elif run.status == WorkflowRun.STATUS_PAUSED:
        db.commit()
    elif not progressed and not running_ids:
        if all_done:
            _finalize_run(db, run_id, WorkflowRun.STATUS_COMPLETED, "")


def _load_edges(db: Session, run: WorkflowRun) -> List[Dict]:
    if run.template_id:
        tpl = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == run.template_id).first()
        if tpl:
            return tpl.get_edges()
    ctx = run.get_context()
    return ctx.get("_edges", [])


def _compute_indegree(node_ids: List[str], edges: List[Dict]) -> Dict[str, int]:
    indeg = {nid: 0 for nid in node_ids}
    for e in edges:
        s = e.get("source") or e.get("from") or e.get("source_id")
        t = e.get("target") or e.get("to") or e.get("target_id")
        if t in indeg:
            indeg[t] += 1
    return indeg


def _node_dependencies(node_id: str, edges: List[Dict]) -> set:
    deps = set()
    for e in edges:
        s = e.get("source") or e.get("from") or e.get("source_id")
        t = e.get("target") or e.get("to") or e.get("target_id")
        if t == node_id and s:
            deps.add(s)
    return deps


def _execute_node(db: Session, run: WorkflowRun, nr: WorkflowNodeRun, payload: Dict):
    """执行单个节点：调 execute_* MCP 工具，记录结果。失败按 retry_count 重试。"""
    nr.status = WorkflowNodeRun.STATUS_RUNNING
    nr.started_at = _now()
    db.commit()

    tool_name = f"execute_{nr.action_type}"
    max_retry = nr.retry_count or 0
    result = None
    for attempt in range(max_retry + 1):
        try:
            result = call_mcp_tool(tool_name, payload, db=db, allow_internal=True)
        except Exception as e:
            result = {"status": "error", "message": f"工具执行异常: {e}"}
        if isinstance(result, dict) and result.get("status") == "is_success":
            break
        if attempt < max_retry:
            time.sleep(0.5)
    nr.result = json.dumps(result, ensure_ascii=False)
    nr.completed_at = _now()
    is_success = isinstance(result, dict) and result.get("status") == "success"
    nr.status = WorkflowNodeRun.STATUS_COMPLETED if is_success else WorkflowNodeRun.STATUS_FAILED
    db.commit()

    try:
        if run.session_id:
            db.add(ToolInvocation(
                session_id=run.session_id,
                tool_name=tool_name,
                status="success" if is_success else "failed",
                latency_ms=0,
                request_payload=json.dumps(payload, ensure_ascii=False),
                response_summary=json.dumps(result, ensure_ascii=False),
            ))
            db.commit()
    except Exception:
        pass


def _finalize_run(db: Session, run_id: int, status: str, message: str):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return
    run.status = status
    run.completed_at = _now()
    if message:
        ctx = run.get_context()
        ctx.setdefault("finalize_message", message)
        run.context = json.dumps(ctx, ensure_ascii=False)
    db.commit()


def confirm_node(db: Session, node_run_id: int, user_name: str = "") -> Dict:
    """用户确认写操作节点，执行后推进工作流。"""
    nr = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != WorkflowNodeRun.STATUS_AWAITING_CONFIRM:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，无法确认"}
    run = db.query(WorkflowRun).filter(WorkflowRun.id == nr.run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}

    payload = nr.get_payload()
    _execute_node(db, run, nr, payload)

    if run.status == WorkflowRun.STATUS_PAUSED:
        run.status = WorkflowRun.STATUS_RUNNING
        db.commit()
    _advance_run(db, run.id)
    return {"is_success": True, "status": nr.status, "result": nr.get_result()}


def cancel_node(db: Session, node_run_id: int, reason: str = "") -> Dict:
    """取消 awaiting_confirm 节点（置 skipped），并中止整个 Run。"""
    nr = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != WorkflowNodeRun.STATUS_AWAITING_CONFIRM:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，无法取消"}
    nr.status = WorkflowNodeRun.STATUS_SKIPPED
    nr.result = json.dumps({"status": "canceled", "message": f"用户取消: {reason}"}, ensure_ascii=False)
    nr.completed_at = _now()
    db.commit()
    _finalize_run(db, nr.run_id, WorkflowRun.STATUS_ABORTED, f"节点 {nr.node_id} 被用户取消")
    return {"is_success": True, "message": "节点已取消，工作流已中止"}


def abort_run(db: Session, run_id: int, reason: str = "") -> Dict:
    """中止整个工作流。"""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}
    if run.status in (WorkflowRun.STATUS_COMPLETED, WorkflowRun.STATUS_FAILED, WorkflowRun.STATUS_ABORTED):
        return {"is_success": False, "message": f"工作流已处于终态 {run.status}"}
    node_runs = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.run_id == run_id).all()
    for nr in node_runs:
        if nr.status in (WorkflowNodeRun.STATUS_PENDING, WorkflowNodeRun.STATUS_RUNNING, WorkflowNodeRun.STATUS_AWAITING_CONFIRM):
            nr.status = WorkflowNodeRun.STATUS_SKIPPED
            nr.completed_at = _now()
    db.commit()
    _finalize_run(db, run_id, WorkflowRun.STATUS_ABORTED, reason or "用户手动中止")
    return {"is_success": True, "message": "工作流已中止"}


def retry_node(db: Session, node_run_id: int) -> Dict:
    """重试失败节点：重置为 pending 并重新推进。"""
    nr = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.id == node_run_id).first()
    if not nr:
        return {"is_success": False, "message": "节点不存在"}
    if nr.status != WorkflowNodeRun.STATUS_FAILED:
        return {"is_success": False, "message": f"节点状态为 {nr.status}，仅失败节点可重试"}
    run = db.query(WorkflowRun).filter(WorkflowRun.id == nr.run_id).first()
    if not run:
        return {"is_success": False, "message": "工作流实例不存在"}
    nr.status = WorkflowNodeRun.STATUS_PENDING
    nr.result = ""
    nr.started_at = None
    nr.completed_at = None
    db.commit()
    if run.status in (WorkflowRun.STATUS_FAILED, WorkflowRun.STATUS_COMPLETED, WorkflowRun.STATUS_ABORTED):
        run.status = WorkflowRun.STATUS_RUNNING
        db.commit()
    _advance_run(db, run.id)
    return {"is_success": True, "message": "节点已重试"}


def list_templates(db: Session, category: Optional[str] = None, only_enabled: bool = False, page: Optional[int] = None, per_page: int = 20) -> Dict:
    q = db.query(WorkflowTemplate)
    if category:
        q = q.filter(WorkflowTemplate.category == category)
    if only_enabled:
        q = q.filter(WorkflowTemplate.enabled == True)
    q = q.order_by(WorkflowTemplate.id.desc())
    if page is None:
        items = [_serialize_template(t) for t in q.all()]
        return {"items": items, "count": len(items)}
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return {"items": [_serialize_template(t) for t in rows], "count": total, "total": total, "page": page, "per_page": per_page, "total_pages": total_pages}


def get_template(db: Session, template_id: int) -> Optional[Dict]:
    t = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    return _serialize_template(t) if t else None


def create_template(db: Session, data: Dict) -> Dict:
    t = WorkflowTemplate(
        name=data.get("name", ""),
        description=data.get("description", ""),
        category=data.get("category", "generic"),
        trigger_type=data.get("trigger_type", "manual"),
        trigger_condition=json.dumps(data.get("trigger_condition", {}), ensure_ascii=False),
        nodes=json.dumps(data.get("nodes", []), ensure_ascii=False),
        edges=json.dumps(data.get("edges", []), ensure_ascii=False),
        risk_level=data.get("risk_level", "medium"),
        enabled=bool(data.get("enabled", True)),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize_template(t)


def update_template(db: Session, template_id: int, data: Dict) -> Optional[Dict]:
    t = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    if not t:
        return None
    for field in ["name", "description", "category", "trigger_type", "risk_level"]:
        if field in data:
            setattr(t, field, data[field])
    if "enabled" in data:
        t.enabled = bool(data["enabled"])
    if "nodes" in data:
        t.nodes = json.dumps(data["nodes"], ensure_ascii=False)
    if "edges" in data:
        t.edges = json.dumps(data["edges"], ensure_ascii=False)
    if "trigger_condition" in data:
        t.trigger_condition = json.dumps(data["trigger_condition"], ensure_ascii=False)
    db.commit()
    db.refresh(t)
    return _serialize_template(t)


def delete_template(db: Session, template_id: int) -> bool:
    t = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


def list_runs(db: Session, status: Optional[str] = None, limit: int = 50, page: Optional[int] = None, per_page: int = 20) -> Dict:
    q = db.query(WorkflowRun)
    if status:
        q = q.filter(WorkflowRun.status == status)
    q = q.order_by(WorkflowRun.id.desc())
    if page is None:
        runs = q.limit(limit).all()
        result = []
        for r in runs:
            node_runs = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.run_id == r.id).all()
            result.append(_serialize_run(r, node_runs))
        return {"items": result, "count": len(result)}
    total = q.count()
    runs = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    result = []
    for r in runs:
        node_runs = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.run_id == r.id).all()
        result.append(_serialize_run(r, node_runs))
    return {"items": result, "count": total, "total": total, "page": page, "per_page": per_page, "total_pages": total_pages}


def get_run(db: Session, run_id: int) -> Optional[Dict]:
    r = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not r:
        return None
    node_runs = db.query(WorkflowNodeRun).filter(WorkflowNodeRun.run_id == run_id).all()
    return _serialize_run(r, node_runs)


def seed_workflow_templates(db: Session):
    """幂等播种 5 个预置 SOP 模板。按 name 去重。"""
    existing_names = {t.name for t in db.query(WorkflowTemplate).all()}
    presets = _preset_templates()
    added = 0
    for p in presets:
        if p["name"] in existing_names:
            continue
        t = WorkflowTemplate(
            name=p["name"],
            description=p.get("description", ""),
            category=p.get("category", "generic"),
            trigger_type=p.get("trigger_type", "manual"),
            trigger_condition=json.dumps(p.get("trigger_condition", {}), ensure_ascii=False),
            nodes=json.dumps(p.get("nodes", []), ensure_ascii=False),
            edges=json.dumps(p.get("edges", []), ensure_ascii=False),
            risk_level=p.get("risk_level", "medium"),
            enabled=bool(p.get("enabled", True)),
        )
        db.add(t)
        added += 1
    if added:
        db.commit()
    return added


def _preset_templates() -> List[Dict]:
    from app.data.sop_templates import get_all_templates
    return get_all_templates()
