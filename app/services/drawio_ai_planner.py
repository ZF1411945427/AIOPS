"""AI 架构图布局规划器: 调用 LLM 分析资产关系, 输出布局优化建议。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.models import AIProvider, Asset, AssetRelation
from app.services.agent_service import call_llm


def _pick_provider(db) -> Optional[AIProvider]:
    """取第一个启用的 AI provider（is_enabled=True）。"""
    providers = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()  # noqa: E712
    if not providers:
        return None
    return providers[0]


def _build_prompt(domain: str, assets: List[Asset], relations: List[AssetRelation]) -> str:
    """构建给 LLM 的 prompt, 让 AI 分析资产关系并输出布局建议。"""
    lines = [f"你是一个系统架构图布局专家。分析业务域「{domain}」的资产和关系，给出布局优化建议。\n"]
    lines.append("## 资产列表")
    for a in assets:
        pid = a.parent_id or "-"
        lines.append(f"  id={a.id} name={a.name} type={a.ci_type} layer={a.ci_type} parent_id={pid}")
    lines.append("")
    lines.append("## 关系列表")
    for r in relations:
        lines.append(f"  {r.parent_id} -> {r.child_id}  relation={r.relation_type}")
    lines.append("")
    lines.append("## 要求")
    lines.append("请按以下 JSON 格式输出（不要输出其他内容，只输出 JSON）：")
    lines.append("""
{
  "analysis": "简要分析该系统的架构特点（中文，50字以内）",
  "node_order": {
    "asset_id: score",
    ...
  },
  "suggestions": "布局优化建议文字（中文，30字以内）"
}

其中 node_order 是一个 JSON 对象, key 为资产 id, value 为排序分数（整数, 越大越靠左）。同一层的节点会根据分数排序。分数参考: 上游服务(如网关)应靠左, 下游服务(如数据库)应靠右。
""")
    return "\n".join(lines)


def ai_layout_plan(domain: str, assets: List[Asset], relations: List[AssetRelation],
                   provider: Optional[AIProvider] = None) -> Dict[str, Any]:
    """调用 LLM 分析资产关系, 返回布局建议。

    返回:
    {
        "ok": True/False,
        "analysis": "AI 分析说明",
        "node_order": {asset_id_str: score_int, ...},
        "suggestions": "布局建议",
        "fallback": True/False (是否使用了兜底策略)
    }
    """
    if provider is None:
        from app.database import get_session_for, get_db_mode
        db = get_session_for(get_db_mode())()
        try:
            provider = _pick_provider(db)
        finally:
            db.close()

    if provider is None:
        return {"ok": False, "error": "没有可用的 AI provider", "fallback": True}

    prompt = _build_prompt(domain, assets, relations)
    messages = [
        {"role": "system", "content": "你是一个系统架构图布局专家。请严格按照 JSON 格式输出，不要包含其他内容。"},
        {"role": "user", "content": prompt},
    ]

    resp = call_llm(provider, messages, timeout_override=30, max_tokens_override=2048)
    if not resp or (isinstance(resp, dict) and resp.get("error")):
        err = resp.get("error") if isinstance(resp, dict) else str(resp)
        return {"ok": False, "error": f"AI 调用失败: {err}", "fallback": True}

    try:
        content = resp["choices"][0]["message"]["content"]
        # 解析 JSON (可能被 ```json ... ``` 包裹)
        content = content.strip()
        if content.startswith("```"):
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            if m:
                content = m.group(1).strip()
        plan = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        return {"ok": False, "error": f"AI 返回解析失败: {e}", "fallback": True}

    node_order = plan.get("node_order", {})
    # 确保分数是整数
    if isinstance(node_order, dict):
        try:
            node_order = {str(k): int(v) for k, v in node_order.items()}
        except (ValueError, TypeError):
            node_order = {}

    return {
        "ok": True,
        "analysis": plan.get("analysis", ""),
        "node_order": node_order,
        "suggestions": plan.get("suggestions", ""),
        "fallback": False,
    }


def apply_ai_scores(assets: List[Asset], node_order: Dict[str, int]) -> Dict[str, int]:
    """将 AI 的排序分数应用到资产列表。返回 {asset_id_str: score} 的完整映射。"""
    scores = {}
    for a in assets:
        aid = str(a.id)
        scores[aid] = node_order.get(aid, 0)
    return scores