"""LLM Reviewer 审查门（write gate，对齐 Ongrid tools/decorators/review_gate.go）。

高危写操作（execute_* 且 review_gate 标记）确认执行前，先经过 reviewer 子代理二签：
- reviewer 用 LLM 审查 payload + 上下文，判定 approve / reject
- reject 阻断执行，返回原因，PendingAction 标记 failed
- approve 才真正执行

设计：
- review_gate 工具元数据来自 tool_registry.tool_review_gate / register_mcp_tool(review_gate=True)
- 现有 propose_action 已标 review_gate=True（后续工具可自行扩展）
"""
import json
from typing import Dict, Optional

from sqlalchemy.orm import Session

REVIEW_SYSTEM_PROMPT = """你是 AIOps 平台的【安全审查员】。用户请求执行一个高风险运维写操作，你需要审查它是否安全、必要、合规。

审查维度：
1. 操作对象是否明确且存在于上下文（资产 ID、服务名不能缺失/含糊）
2. 命令/操作是否会破坏系统或数据（重启生产服务需谨慎；删除、清库、rm、drop 必须有充分理由）
3. 参数是否合理（阈值、目标是否异常）
4. 是否符合最小权限原则（能做只读就别做写操作）

输出要求：必须输出 JSON，格式：
{"verdict": "approve" 或 "reject", "confidence": 0-100, "reason": "简短中文理由", "suggestions": ["可选建议"]}
只输出 JSON，不要输出其他内容。"""


def should_review(tool_name: str) -> bool:
    """该工具是否需要 reviewer 审查门。命中任一条件即审查：
    - 工具显式标记 review_gate=True
    - 工具风险等级 high / critical（写操作一律审查）
    """
    try:
        from app.services.mcp_registry import get_mcp_tool
        tool = get_mcp_tool(tool_name)
        if not tool:
            return False
        if tool.review_gate:
            return True
        return tool.risk_level in ("high", "critical")
    except Exception:
        return False


def build_review_context(action_type: str, payload: Dict, title: str = "", session_id: Optional[int] = None) -> str:
    """构造 reviewer 可见的上下文（历史 + 操作内容）。"""
    lines = [
        f"操作类型: {action_type}",
        f"操作标题: {title or '(无)'}",
        f"操作参数: {json.dumps(payload, ensure_ascii=False)}",
    ]
    if session_id:
        lines.append(f"会话ID: {session_id}")
    return "\n".join(lines)


def review_action(
    db: Session,
    action_type: str,
    payload: Dict,
    title: str = "",
    session_id: Optional[int] = None,
    provider_id: Optional[int] = None,
) -> Dict:
    """调用 reviewer LLM 二签。返回 {verdict, confidence, reason, suggestions, error}。"""
    from app.models import AIProvider
    from app.services.agent_service import call_llm

    provider = None
    if provider_id:
        provider = db.query(AIProvider).filter(AIProvider.id == provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"verdict": "approve", "reason": "无可用 LLM，跳过审查（fail-open 保可用）", "error": "no_provider"}

    context = build_review_context(action_type, payload, title, session_id)
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": f"请审查以下运维操作是否安全：\n{context}"},
    ]

    try:
        resp = call_llm(provider, messages, timeout_override=30, max_tokens_override=200)
        if "error" in resp:
            return {"verdict": "approve", "reason": f"LLM 审查不可用({resp['error']})，fail-open 放行", "error": resp["error"]}
        text = ""
        choices = resp.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "") or ""
        if isinstance(text, list):
            text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
        text = text.strip()
        # 剥离 markdown code fence
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.replace("```", "").strip()
        # 提取 JSON 部分
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        verdict = data.get("verdict", "approve")
        if verdict not in ("approve", "reject"):
            verdict = "reject"  # 无明确 verdict 视为拒绝（保守）
        return {
            "verdict": verdict,
            "confidence": int(data.get("confidence", 0) or 0),
            "reason": data.get("reason", "LLM 未给出理由")[:500],
            "suggestions": data.get("suggestions", []),
        }
    except Exception as e:
        return {"verdict": "approve", "reason": f"reviewer 异常({e})，fail-open 放行", "error": str(e)}


def review_workflow_tool(db: Session, tool_name: str, parameters: Dict, title: str = "",
                         run_id: Optional[int] = None, session_id: Optional[int] = None) -> Dict:
    """工作流节点执行前的 review_gate 二签（同 review_action，但工具名查 review_gate）。"""
    if not should_review(tool_name):
        return {"verdict": "approve", "skipped": True}
    return review_action(db, tool_name or "workflow_tool", parameters, title, session_id)