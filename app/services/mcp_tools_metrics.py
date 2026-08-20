"""指标自定义卡片 MCP 工具（语音/对话建指标卡能力）。

对应 CONTRACT.md 指标卡契约(metric_dashboard_cards)：
- generate_promql      (LLM 可见, 只读): 自然语言 → PromQL + 标题, 复用 ai_insight 生成逻辑
- list_metric_cards    (LLM 可见, 只读): 列出当前用户的自定义指标卡, 防止重复创建
- execute_create_metric_card (内部, 确认闭环): propose_action 提案 → 人工确认 → 落库
- execute_delete_metric_card (内部, 确认闭环): 删除自定义指标卡(高危, 需确认)

坐标系: 与 app/routers/metrics.py 保持一致, card.user_id 默认 0(公共可见)。
"""

import json
import logging
import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import MetricDashboardCard
from app.services.mcp_registry import register_mcp_tool


logger = logging.getLogger(__name__)


def _get_db():
    return get_session_for(get_db_mode())()


# ────────────────────────── 只读工具 (LLM 可见) ──────────────────────────
@register_mcp_tool(
    name="generate_promql",
    description="根据自然语言需求生成 VikctoriaMetrics/Prometheus 可执行 PromQL 查询表达式和卡片标题。"
                "用于用户想新建指标监控自定义卡片前先产出表达式。也可用于仅供查看的表达式生成。"
                "输入用户描述(如'CPU使用率最高的前3台主机'), 返回 {promql, title}。",
    input_schema={
        "type": "object",
        "properties": {
            "request": {"type": "string", "description": "用户对指标/查询的自然语言描述, 如 '数据库 CPU 使用率趋势'、'内存占用最大的前5台主机'"},
            "hours": {"type": "integer", "description": "查询时间范围(小时), 默认 24"},
        },
        "required": ["request"],
    },
    risk_level="read_only",
    display_name="生成PromQL",
    expose_to_llm=True,
    location="cloud",
    category="metric",
    timeout_seconds=120,
)
def generate_promql(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        user_request = (kwargs.get("request") or "").strip()
        if not user_request:
            raise ValueError("缺少必填参数: request")
        hours = int(kwargs.get("hours", 24) or 24)

        from app.services import metric_v2_service
        from app.services.agent_service import call_llm
        from app.services.ai_insight_service import _get_provider

        provider = _get_provider(db)
        if not provider:
            return {"status": "error", "message": "未配置可用的 AI 模型提供商"}

        metric_names = metric_v2_service.query_metric_names()
        names_str = ", ".join(metric_names[:200]) if metric_names else "(无可用指标)"
        time_desc = f"最近 {hours} 小时"

        sys_prompt = (
            "你是一名资深 PromQL / Prometheus 专家。用户的系统会把指标写入 VictoriaMetrics，"
            "指标带 asset_id（资产 id）、unit（单位）、target 等标签。"
            f"系统当前可用的指标名有: {names_str}\n\n"
            "请根据用户的自然语言需求，生成一段可执行的自定义 PromQL。要求：\n"
            "1. 只能使用上面列出的指标名，不要臆造不存在的指标。\n"
            "2. 优先给出有意义的聚合，常见用法：avg/max/min/sum by 或 avg_over_time，"
            "需要排名的用 topk/bottomk，需要滚动的用 rate()。\n"
            "3. 若需要区分资产/单个主机，用 asset_id 标签过滤，如 {asset_id=\"1\"}。\n"
            "4. 注意：查询时间范围是用户卡片设置的时间范围，滚动函数窗口（如 rate()[5m]、avg_over_time()[1h]）"
            "要远小于该总时长，不要超过总时长，也不要恰好等于总时长。\n"
            "5. 只输出一行 PromQL 表达式，不要写解释、不要写 markdown 代码块、不要换行。\n"
            "同时给卡片起一个简短的标题（少于 20 字）。\n\n"
            "输出严格按如下 JSON 格式（不要输出其他内容）:\n"
            '{"promql": "<PromQL>", "title": "<卡片标题>"}'
        )
        user_prompt = f"查询时间范围: {time_desc}。\n用户需求: {user_request}"
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=120)
        if resp.get("error"):
            return {"error": f"AI 生成失败: {resp['error']}"}
        try:
            content = resp["choices"][0]["message"]["content"]
        except Exception:
            return {"error": "AI 返回格式异常"}

        promql, title = _parse_promql_reply(content, user_request)
        if not promql:
            return {"error": "AI 未能解析出有效的 PromQL"}
        return {
            "promql": promql.strip(),
            "title": title,
            "provider": provider.default_model,
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="list_metric_cards",
    description="列出当前用户已创建的自定义指标监控卡片（标题/PromQL/时间范围/宽高/分类）。"
                "新建卡片前应先查看，避免重复创建。",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="查看指标卡",
    expose_to_llm=True,
    location="cloud",
    category="metric",
)
def list_metric_cards(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        cards = db.query(MetricDashboardCard).filter(
            MetricDashboardCard.user_id == (user_id or 0)
        ).order_by(MetricDashboardCard.order.asc()).all()
        return {
            "cards": [
                {
                    "id": c.id,
                    "title": c.title,
                    "promql": c.promql,
                    "hours": c.hours,
                    "w": c.w,
                    "h": c.h,
                    "category": c.category or "",
                    "order": c.order,
                }
                for c in cards
            ],
            "count": len(cards),
        }
    finally:
        if close_db:
            db.close()


# ────────────────────────── 内部执行工具 (确认闭环) ──────────────────────────
# 设计约定与 mcp_tools_execute.py 一致:
#   业务成功 -> {"status":"success","message":...,"data":...}
#   业务失败 -> 抛异常 (ValueError/RuntimeError), 外层包装为 error.


@register_mcp_tool(
    name="execute_create_metric_card",
    description="创建自定义指标监控卡片（落库到 metric_dashboard_cards）。仅由 propose_action 确认后调用。",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "指标卡数据",
                "properties": {
                    "title": {"type": "string", "description": "卡片标题"},
                    "promql": {"type": "string", "description": "PromQL 查询表达式"},
                    "hours": {"type": "integer", "description": "时间范围(小时): 1/6/24/72/168, 默认 24"},
                    "w": {"type": "integer", "description": "宽度(1-4 列), 默认 2"},
                    "h": {"type": "integer", "description": "高度(1/2), 默认 1"},
                    "category": {"type": "string", "description": "分类, 默认空"},
                },
                "required": ["title", "promql"],
            },
        },
        "required": ["data"],
    },
    risk_level="medium",
    display_name="创建指标卡",
    expose_to_llm=False,
    location="cloud",
    category="metric",
)
def execute_create_metric_card(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        data = kwargs.get("data")
        if not data or not isinstance(data, dict):
            raise ValueError("缺少必填参数: data 对象")
        title = (data.get("title") or "").strip()
        promql = (data.get("promql") or "").strip()
        if not title:
            raise ValueError("缺少必填字段: title")
        if not promql:
            raise ValueError("缺少必填字段: promql")
        if len(title) > 128:
            raise ValueError("title 超过 128 字符")
        if len(promql) > 512:
            raise ValueError("promql 超过 512 字符")
        hours = int(data.get("hours", 24) or 24)
        hours = hours if hours in (1, 6, 24, 72, 168) else 24
        w = max(1, min(4, int(data.get("w", 2) or 2)))
        h = max(1, min(2, int(data.get("h", 1) or 1)))
        category = (data.get("category") or "").strip()[:32]

        max_order = db.query(MetricDashboardCard).filter(
            MetricDashboardCard.user_id == (user_id or 0)
        ).count()
        card = MetricDashboardCard(
            user_id=user_id or 0,
            title=title,
            promql=promql,
            hours=hours,
            w=w,
            h=h,
            category=category,
            order=max_order,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        return {
            "status": "success",
            "message": f"指标卡「{title}」已创建",
            "data": {"card_id": card.id, "title": card.title, "promql": card.promql},
        }
    finally:
        if close_db:
            db.close()


@register_mcp_tool(
    name="execute_delete_metric_card",
    description="删除自定义指标监控卡片（不可恢复, 需人工确认）。仅由 propose_action 确认后调用。",
    input_schema={
        "type": "object",
        "properties": {
            "card_id": {"type": "integer", "description": "指标卡 ID"},
        },
        "required": ["card_id"],
    },
    risk_level="high",
    review_gate=True,
    display_name="删除指标卡",
    expose_to_llm=False,
    location="cloud",
    category="metric",
)
def execute_delete_metric_card(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        card_id = kwargs.get("card_id")
        if card_id is None:
            raise ValueError("缺少必填参数: card_id")
        card = db.query(MetricDashboardCard).filter(
            MetricDashboardCard.id == int(card_id),
            MetricDashboardCard.user_id == (user_id or 0),
        ).first()
        if not card:
            raise ValueError(f"指标卡 {card_id} 未找到")
        title = card.title
        db.delete(card)
        db.commit()
        return {"status": "success", "message": f"指标卡「{title}」已删除", "data": {"card_id": int(card_id)}}
    finally:
        if close_db:
            db.close()


# ────────────────────────── 私有辅助 ──────────────────────────
def _parse_promql_reply(content: str, fallback_title: str) -> tuple:
    """从 LLM 输出解析 promql 与 title；剥离 markdown 代码块/JSON 包裹，取最像的表达式。
    与 app/routers/ai_insight.py::_parse_promql_response 行为一致。"""
    text = (content or "").strip()
    text = re.sub(r"^```(?:json|promql)?\s*", "", text).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    title = fallback_title[:20]
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("promql", ""), (data.get("title") or title)[:20]
    except Exception:
        pass
    m = re.search(r'"promql"\s*:\s*"([^"]*)"', text)
    if m:
        return m.group(1), title
    line = text.splitlines()[0].strip() if text else ""
    if line and (any(c in line for c in "({") or line[0].isalpha()):
        return line, title
    return "", title