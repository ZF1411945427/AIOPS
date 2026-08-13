"""技能 MCP 工具(F1: Agent 可调用技能清单 + 可审计执行)。

依赖 skill_registry: list_skills 返回可用技能, use_skill 返回 SKILL.md 指令
供 LLM 按步骤执行, 并写 skill_executions 审计。契约见 CONTRACT.md 第十九章。
"""
import time

from app.services.mcp_registry import register_mcp_tool
from app.services.mcp_tools import _get_db
from app.services import skill_registry


@register_mcp_tool(
    name="list_skills",
    description="列出当前启用的技能库(SKILL.md)技能, 含名称/描述/分类/依赖工具, 供选择调用 use_skill",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="技能清单",
    location="cloud",
    category="skill",
)
def list_skills(db=None, user_id=None, **kwargs):
    session = _get_db()
    try:
        skills = [s for s in skill_registry.list_skills(session) if s["enabled"]]
        return {
            "total": len(skills),
            "skills": [{
                "name": s["name"],
                "description": s["description"],
                "category": s["category"],
                "risk_level": s["risk_level"],
                "tools_required": s["tools_required"],
            } for s in skills],
        }
    finally:
        session.close()


@register_mcp_tool(
    name="use_skill",
    description="调用一个已安装技能: 返回该技能的 SKILL.md 指令正文, 请严格按指令步骤执行(必要时调用 tools_required 里的工具)",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名(list_skills 返回的 name)"},
            "input": {"type": "string", "description": "技能输入参数/目标说明"},
        },
        "required": ["name"],
    },
    risk_level="read_only",
    display_name="调用技能",
    location="cloud",
    category="skill",
)
def use_skill(db=None, user_id=None, **kwargs):
    name = str(kwargs.get("name") or "").strip()
    user_input = str(kwargs.get("input") or "")
    if not name:
        raise ValueError("缺少技能名 name")
    session = _get_db()
    try:
        skill = skill_registry.get_skill_by_name(session, name)
        if not skill:
            raise ValueError(f"技能 {name} 不存在, 可先调用 list_skills 查看可用技能")
        if not skill.enabled:
            raise ValueError(f"技能 {name} 已禁用")
        start = time.time()
        record = skill_registry.record_execution(
            session, skill.id, skill.name, "use_skill", "success",
            input_summary=user_input,
            output_summary=f"技能指令已加载({len(skill.content)} 字符)",
            duration_ms=int((time.time() - start) * 1000),
            executed_by=user_id,
        )
        return {
            "skill": skill.name,
            "version": skill.version,
            "description": skill.description,
            "risk_level": skill.risk_level,
            "tools_required": skill_registry._load_json(skill.tools_required),
            "instructions": skill.content,
            "audit_id": record.id,
            "usage_count": (skill.usage_count or 0) + 1,
        }
    finally:
        session.close()
