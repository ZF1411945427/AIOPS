import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Alert, Asset, KnowledgeBase, KnowledgeDraft, AlertKbLink, AIProvider


def generate_draft(alert_id: int, db: Session) -> dict:
    """当告警解决后，调用 LLM 自动生成知识草稿"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return {"ok": False, "error": "告警不存在"}

    if alert.status != "resolved":
        return {"ok": False, "error": "仅已解决的告警可生成知识草稿"}

    existing = db.query(KnowledgeDraft).filter(
        KnowledgeDraft.alert_id == alert_id,
        KnowledgeDraft.status == "pending"
    ).first()
    if existing:
        return {"ok": False, "error": "该告警已有待处理草稿", "draft_id": existing.id}

    asset = None
    if alert.asset_id:
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()

    related_kbs = (
        db.query(KnowledgeBase)
        .join(AlertKbLink, AlertKbLink.kb_id == KnowledgeBase.id)
        .filter(AlertKbLink.alert_id == alert_id)
        .all()
    )

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ok": False, "error": "未配置启用的 AI Provider"}

    kb_context = ""
    if related_kbs:
        kb_context = "相关历史知识:\n" + "\n".join(
            f"- {kb.title}: {kb.symptom or ''} → {kb.solution or ''}"
            for kb in related_kbs[:3]
        )

    system_prompt = """你是 AIOps 知识工程师。当告警被解决后，从告警信息中提取关键要素，生成结构化知识条目。

输出 JSON 格式：
{
  "title": "知识标题（简洁，≤30字，含关键指标）",
  "symptom": "故障表现（100字内，描述异常现象）",
  "root_cause": "根因分析（100字内，说明故障根本原因）",
  "solution": "解决方案（150字内，说明修复步骤）",
  "tags": "标签列表（英文逗号分隔，如 cpu,nginx,超时）",
  "severity": "级别（critical/high/warning/info，根据告警级别判断）",
  "asset_type": "资产类型（从告警信息推断，如 nginx, mysql, kubernetes_cluster）"
}"""

    asset_info = f"资产: {asset.name} (ci_type={asset.ci_type}, ip={asset.ip})" if asset else "无关联资产"

    user_prompt = f"""告警已解决，以下是告警信息：

- 告警ID: {alert.id}
- 指标: {alert.metric_name or '-'}
- 级别: {alert.severity or '-'}
- 状态: {alert.status}
- 告警消息: {alert.message or '-'}
- 触发时间: {alert.created_at}
- 解决时间: {alert.resolved_at or '未知'}
- 关联资产: {asset_info}
{kb_context}

请根据以上信息生成结构化知识条目，输出 JSON。"""

    try:
        from app.services.agent_service import call_llm
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {"ok": False, "error": "AI 返回为空"}

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content)

        source_data = json.dumps({
            "alert_id": alert.id,
            "metric_name": alert.metric_name,
            "severity": alert.severity,
            "message": alert.message,
            "created_at": str(alert.created_at) if alert.created_at else None,
            "resolved_at": str(alert.resolved_at) if alert.resolved_at else None,
            "asset_id": alert.asset_id,
            "asset_name": asset.name if asset else None,
        }, ensure_ascii=False)

        draft = KnowledgeDraft(
            alert_id=alert_id,
            title=parsed.get("title", f"告警 {alert_id} 知识沉淀"),
            symptom=parsed.get("symptom", ""),
            root_cause=parsed.get("root_cause", ""),
            solution=parsed.get("solution", ""),
            tags=parsed.get("tags", ""),
            severity=parsed.get("severity", alert.severity or "warning"),
            asset_type=parsed.get("asset_type", asset.ci_type if asset else ""),
            source_data=source_data,
            status="pending",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return {"ok": True, "draft_id": draft.id, "title": draft.title}
    except Exception as e:
        return {"ok": False, "error": f"AI 生成失败: {e}"}


def approve_draft(draft_id: int, db: Session) -> dict:
    """审批通过：草稿写入知识库，标记来源为auto并关联告警"""
    draft = db.query(KnowledgeDraft).filter(KnowledgeDraft.id == draft_id).first()
    if not draft:
        return {"ok": False, "error": "草稿不存在"}

    kb = KnowledgeBase(
        title=draft.title,
        symptom=draft.symptom,
        root_cause=draft.root_cause,
        solution=draft.solution,
        tags=draft.tags,
        severity=draft.severity,
        asset_type=draft.asset_type,
        source_type="auto",
        sop_steps=draft.sop_steps or "[]",
    )
    db.add(kb)

    if draft.alert_id:
        link = AlertKbLink(alert_id=draft.alert_id, kb_id=kb.id)
        db.add(link)

    draft.status = "approved"
    db.commit()
    db.refresh(draft)
    return {"ok": True, "kb_id": kb.id}


def generate_sop_from_incident(incident_id: int, db: Session) -> dict:
    """从故障单自动生成 SOP 步骤"""
    from app.services.incident_service import get_incident_detail
    from app.services.agent_service import call_llm

    detail = get_incident_detail(db, incident_id)
    if not detail:
        return {"ok": False, "error": "故障单不存在"}

    inc = detail["incident"]
    asset = detail.get("asset")
    alerts = detail.get("alerts", [])

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ok": False, "error": "未配置启用的 AI Provider"}

    asset_info = f"资产: {asset.name} (ip={asset.ip})" if asset else "无关联资产"
    alert_list = "\n".join(
        f"- #{a.id} [{a.severity}] {a.metric_name}: {a.message}"
        for a in alerts[:5]
    ) if alerts else "无关联告警"

    system_prompt = """你是运维 SRE 工程师。根据故障信息生成标准操作步骤（SOP）。

输出 JSON 格式：
{
  "title": "SOP 标题（简洁，≤30字）",
  "symptom": "故障表现（50字内）",
  "root_cause": "根因（30字内）",
  "solution": "解决方案（100字内）",
  "tags": "标签（英文逗号分隔）",
  "severity": "级别（critical/high/warning/info）",
  "asset_type": "资产类型",
  "sop_steps": [
    {"step": 1, "action": "检查步骤", "command": "命令或操作（无可填'无）", "expectation": "预期结果"},
    {"step": 2, "action": "处理步骤", "command": "...", "expectation": "..."},
    {"step": 3, "action": "验证步骤", "command": "...", "expectation": "..."}
  ]
}"""

    user_prompt = f"""故障单信息：
- ID: {inc.id}
- 标题: {inc.title}
- 级别: {inc.severity}
- 关联资产: {asset_info}
- 关联告警:
{alert_list}
- 创建时间: {inc.created_at}

请生成结构化 SOP 步骤，输出 JSON。"""

    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {"ok": False, "error": "AI 返回为空"}

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content)

        draft = KnowledgeDraft(
            title=parsed.get("title", f"故障单 {incident_id} SOP"),
            symptom=parsed.get("symptom", ""),
            root_cause=parsed.get("root_cause", ""),
            solution=parsed.get("solution", ""),
            tags=parsed.get("tags", ""),
            severity=parsed.get("severity", inc.severity or "warning"),
            asset_type=parsed.get("asset_type", asset.ci_type if asset else ""),
            source_data=json.dumps({
                "incident_id": inc.id,
                "incident_title": inc.title,
                "alerts": [{"id": a.id, "metric_name": a.metric_name, "severity": a.severity} for a in alerts[:5]],
            }, ensure_ascii=False),
            source_type="sop",
            sop_steps=json.dumps(parsed.get("sop_steps", []), ensure_ascii=False),
            status="pending",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return {"ok": True, "draft_id": draft.id, "title": draft.title}

    except Exception as e:
        return {"ok": False, "error": f"SOP 生成失败: {e}"}


def generate_from_incident(incident_id: int, db: Session) -> dict:
    """从故障单生成知识草稿（包含故障现象、根因、解决方案）"""
    from app.services.incident_service import get_incident_detail
    from app.services.agent_service import call_llm

    detail = get_incident_detail(db, incident_id)
    if not detail:
        return {"ok": False, "error": "故障单不存在"}

    inc = detail["incident"]
    asset = detail.get("asset")
    alerts = detail.get("alerts", [])

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ok": False, "error": "未配置启用的 AI Provider"}

    asset_info = f"资产: {asset.name} (ip={asset.ip})" if asset else "无关联资产"
    alert_list = "\n".join(
        f"- #{a.id} [{a.severity}] {a.metric_name}: {a.message}"
        for a in alerts[:5]
    ) if alerts else "无关联告警"

    system_prompt = """你是 AIOps 知识工程师。当故障解决后，从故障单信息中提取关键要素，生成结构化知识条目。

输出 JSON 格式：
{
  "title": "知识标题（简洁，≤30字，含关键指标）",
  "symptom": "故障表现（100字内，描述异常现象）",
  "root_cause": "根因分析（100字内，说明故障根本原因）",
  "solution": "解决方案（150字内，说明修复步骤）",
  "tags": "标签列表（英文逗号分隔，如 cpu,nginx,超时）",
  "severity": "级别（critical/high/warning/info，根据故障级别判断）",
  "asset_type": "资产类型（从故障信息推断，如 nginx, mysql, kubernetes_cluster）"
}"""

    user_prompt = f"""故障单信息：

- ID: {inc.id}
- 标题: {inc.title}
- 级别: {inc.severity}
- 描述: {inc.description or '无'}
- 关联资产: {asset_info}
- 关联告警:
{alert_list}
- 创建时间: {inc.created_at}
- 解决时间: {inc.resolved_at or '未知'}

请根据以上信息生成结构化知识条目，输出 JSON。"""

    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {"ok": False, "error": "AI 返回为空"}

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content)

        draft = KnowledgeDraft(
            title=parsed.get("title", f"故障 {incident_id} 知识沉淀"),
            symptom=parsed.get("symptom", ""),
            root_cause=parsed.get("root_cause", ""),
            solution=parsed.get("solution", ""),
            tags=parsed.get("tags", ""),
            severity=parsed.get("severity", inc.severity or "warning"),
            asset_type=parsed.get("asset_type", asset.ci_type if asset else ""),
            source_data=json.dumps({
                "incident_id": inc.id,
                "incident_title": inc.title,
                "incident_description": inc.description,
                "alerts": [{"id": a.id, "metric_name": a.metric_name, "severity": a.severity} for a in alerts[:5]],
            }, ensure_ascii=False),
            source_type="auto",
            status="pending",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return {"ok": True, "draft_id": draft.id, "title": draft.title}

    except Exception as e:
        return {"ok": False, "error": f"知识生成失败: {e}"}


def list_drafts(db: Session, status: str = "", page: int = 1, per_page: int = 20):
    """列出知识草稿"""
    q = db.query(KnowledgeDraft)
    if status:
        q = q.filter(KnowledgeDraft.status == status)
    q = q.order_by(KnowledgeDraft.created_at.desc())
    total = q.count()
    drafts = q.offset((page - 1) * per_page).limit(per_page).all()
    return drafts, total


def reject_draft(draft_id: int, db: Session, reason: str = "") -> dict:
    """审批拒绝：标记草稿为已拒绝"""
    draft = db.query(KnowledgeDraft).filter(KnowledgeDraft.id == draft_id).first()
    if not draft:
        return {"ok": False, "error": "草稿不存在"}
    draft.status = "rejected"
    draft.reject_reason = reason
    db.commit()
    return {"ok": True}
