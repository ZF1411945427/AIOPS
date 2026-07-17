import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Asset, MetricTemplate, AssetMetricRecommendation, MetricRecord, AIProvider, KnowledgeBase, AlertKbLink

_CI_ALIASES = {"virtual_machine": "server", "vm": "server", "host": "server", "physical_machine": "server"}


def get_metric_gaps(asset: Asset, db: Session) -> list:
    """规则匹配：按资产 ci_type 查模板，对比已采指标，返回观测缺口"""
    ci_type = _CI_ALIASES.get(asset.ci_type, asset.ci_type) if asset.ci_type else "server"
    templates = (
        db.query(MetricTemplate)
        .filter(MetricTemplate.ci_type.in_([ci_type, "all"]), MetricTemplate.enabled == True)
        .order_by(MetricTemplate.sort_order)
        .all()
    )
    collected = _get_collected_metric_keys(asset.id, db)
    recs = _get_existing_recommendations(asset.id, db)

    results = []
    for tpl in templates:
        already = tpl.metric_key in collected
        rec_status = recs.get(tpl.metric_key, "")
        results.append({
            "metric_key": tpl.metric_key,
            "metric_name": tpl.metric_name,
            "category": tpl.category,
            "unit": tpl.unit,
            "description": tpl.description,
            "collect_method": tpl.collect_method,
            "default_threshold_warn": tpl.default_threshold_warn,
            "default_threshold_critical": tpl.default_threshold_critical,
            "monitored": already,
            "recommendation_status": rec_status,
            "source": "template",
            "reason": f"{ci_type} 标准观测指标",
        })
    return results


def ai_recommend(asset: Asset, db: Session) -> dict:
    """AI 增强：调用 LLM 对资产做个性化指标推荐"""
    gaps = get_metric_gaps(asset, db)
    collected = _get_collected_metric_keys(asset.id, db)

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ai_enabled": False, "recommendations": [], "message": "未配置启用的 AI Provider"}

    ci_attrs = {}
    try:
        ci_attrs = json.loads(asset.ci_attributes) if asset.ci_attributes else {}
    except (json.JSONDecodeError, TypeError):
        pass

    system_prompt = """你是 AIOps 智能指标推荐专家。根据资产的 CI 类型和属性，推荐最值得监控的指标。
输出 JSON 格式：{"recommendations": [{"metric_key": "...", "metric_name": "...", "category": "...", "reason": "..."}]}
推荐 3-5 个最关键但当前缺失的指标。"""

    user_prompt = f"""资产名称: {asset.name}
CI 类型: {asset.ci_type}
IP: {asset.ip}
属性: {json.dumps(ci_attrs, ensure_ascii=False)}
状态: {asset.status}

已有指标: {json.dumps(list(collected), ensure_ascii=False)}
可选模板指标: {json.dumps([g for g in gaps if not g['monitored']], ensure_ascii=False, default=str)}

请根据此资产的负载特征，推荐最需要补充的观测指标，输出 JSON。"""

    try:
        from app.services.agent_service import call_llm
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {"ai_enabled": True, "recommendations": [], "message": "AI 返回为空"}
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        recs = parsed.get("recommendations", [])
        return {"ai_enabled": True, "recommendations": recs, "message": ""}
    except Exception as e:
        return {"ai_enabled": True, "recommendations": [], "message": f"AI 推荐失败: {e}"}


def apply_recommendation(asset_id: int, metric_key: str, metric_name: str, category: str, unit: str, source: str, reason: str, db: Session) -> dict:
    """应用推荐：保存到 asset_metric_recommendations 表"""
    existing = (
        db.query(AssetMetricRecommendation)
        .filter(
            AssetMetricRecommendation.asset_id == asset_id,
            AssetMetricRecommendation.metric_key == metric_key,
        )
        .first()
    )
    if existing:
        existing.status = "added"
        existing.reason = reason
        db.commit()
        return {"ok": True, "id": existing.id, "action": "updated"}
    rec = AssetMetricRecommendation(
        asset_id=asset_id,
        metric_key=metric_key,
        metric_name=metric_name,
        category=category,
        unit=unit,
        source=source,
        status="added",
        reason=reason,
    )
    db.add(rec)
    db.commit()
    return {"ok": True, "id": rec.id, "action": "created"}


def dismiss_recommendation(asset_id: int, metric_key: str, db: Session) -> dict:
    existing = (
        db.query(AssetMetricRecommendation)
        .filter(
            AssetMetricRecommendation.asset_id == asset_id,
            AssetMetricRecommendation.metric_key == metric_key,
        )
        .first()
    )
    if existing:
        existing.status = "dismissed"
        db.commit()
        return {"ok": True}
    return {"ok": False, "error": "未找到推荐记录"}


def ai_analyze_alert(alert, db: Session) -> dict:
    """AI 分析告警：调用 LLM 对告警做根因分析、影响评估、修复建议"""
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ai_enabled": False, "analysis": None, "message": "未配置启用的 AI Provider"}

    system_prompt = """你是 AIOps 告警分析专家。根据告警信息和相关上下文，给出专业的根因分析、影响评估和修复建议。
输出 JSON 格式：
{
  "root_cause": "根因分析（150字内）",
  "impact": "影响评估（100字内）",
  "recommendation": "修复建议（150字内）",
  "severity_assessment": "严重程度重新评估（critical/high/warning/info）",
  "suggested_runbooks": ["建议参考的 Runbook 标题（可选，最多3条）"]
}"""

    related_kbs = db.query(KnowledgeBase).join(
        AlertKbLink, AlertKbLink.kb_id == KnowledgeBase.id
    ).filter(AlertKbLink.alert_id == alert.id).all()
    kb_summary = ""
    if related_kbs:
        kb_summary = "相关知识库条目:\n" + "\n".join(
            f"- {kb.title}: {kb.symptom or ''} → {kb.solution or ''}" for kb in related_kbs[:3]
        )

    asset_info = ""
    if alert.asset_id:
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
        if asset:
            asset_info = f"关联资产: {asset.name} (ci_type={asset.ci_type}, ip={asset.ip})"

    user_prompt = f"""告警信息:
- ID: {alert.id}
- 指标: {alert.metric_name or '-'}
- 级别: {alert.severity or '-'}
- 状态: {alert.status or '-'}
- 消息: {alert.message or '-'}
- 时间: {alert.created_at or '-'}

{asset_info}
{kb_summary}

请分析此告警，输出 JSON。"""

    try:
        from app.services.agent_service import call_llm
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {"ai_enabled": True, "analysis": None, "message": "AI 返回为空"}
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        return {"ai_enabled": True, "analysis": parsed, "message": ""}
    except Exception as e:
        return {"ai_enabled": True, "analysis": None, "message": f"AI 分析失败: {e}"}


def _get_collected_metric_keys(asset_id: int, db: Session) -> set:
    last_24h = datetime.now() - timedelta(hours=24)
    rows = (
        db.query(MetricRecord.name)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.timestamp >= last_24h)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _get_existing_recommendations(asset_id: int, db: Session) -> dict:
    rows = (
        db.query(AssetMetricRecommendation)
        .filter(AssetMetricRecommendation.asset_id == asset_id)
        .all()
    )
    return {r.metric_key: r.status for r in rows}
