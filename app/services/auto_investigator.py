"""C1-C3: 告警/故障自动调查闭环（auto-investigator worker）。

C1 - worker:  新 incident（high/critical）创建后异步 spawn 调查 worker
C2 - 报告:    跑 RCA 算法收集证据 → 二次 LLM 提取结构化报告（根因/证据/建议/风险）落 InvestigationReport 表
C3 - 回写:    报告回写聊天会话 + 启用双向的 IM 渠道（飞书/钉钉/企微）

触发策略（防重复 + 控制成本）：
- 仅新 incident（ai_rca_at 为空）触发
- 仅 severity in (critical, high) 触发
- 每 incident 只调查一次（InvestigationReport 按 incident_id 去重）
"""
import json
import threading
from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from app.logger import logger


# ─── C2: 结构化 LLM 报告抽取 ──────────────────────────────────────

_LLM_REPORT_PROMPT = """你是一位资深 SRE 根因分析专家。以下是针对一次故障自动收集的结构化证据包，请生成一份精炼的调查报告。

必须严格输出 JSON，字段如下：
{
  "summary": "2-3句中文总结：故障现象、最可能根因、影响范围",
  "root_cause": {"rank": 1, "asset": "最可能根因资产", "confidence": "high|medium|low", "reason": "依据"},
  "root_causes": [{"rank": 1, "asset": "...", "confidence": "...", "reason": "..."}],
  "evidence": ["证据1", "证据2", "..."],
  "timeline": "故障时间线概述",
  "recommendations": [{"action": "建议动作", "priority": "high|medium|low"}],
  "risks": ["风险1", "风险2"],
  "action_needed": true
}
只输出 JSON。"""


def _call_llm_extract(db: Session, evidence_package: Dict) -> Dict:
    """二次 LLM 抽取结构化报告。无 LLM/失败 → 返回基于证据包的降级结构。"""
    from app.models import AIProvider
    from app.services.agent_service import call_llm

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return _fallback_report(evidence_package, "no_provider")

    try:
        messages = [
            {"role": "system", "content": _LLM_REPORT_PROMPT},
            {"role": "user", "content": "证据包:\n" + json.dumps(evidence_package, ensure_ascii=False, default=str)[:12000]},
        ]
        resp = call_llm(provider, messages, timeout_override=45, max_tokens_override=1200)
        if "error" in resp:
            return _fallback_report(evidence_package, str(resp["error"]))

        text = ""
        choices = resp.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "") or ""
        if isinstance(text, list):
            text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return _fallback_report(evidence_package, "llm_output_not_json")
        data = json.loads(text[start:end + 1])
        return {
            "summary": data.get("summary", ""),
            "root_cause": data.get("root_cause", {}),
            "root_causes": data.get("root_causes", []),
            "evidence": data.get("evidence", []),
            "timeline": data.get("timeline", ""),
            "recommendations": data.get("recommendations", []),
            "risks": data.get("risks", []),
            "action_needed": data.get("action_needed", True),
        }
    except Exception as e:
        return _fallback_report(evidence_package, str(e))


def _fallback_report(evidence_package: Dict, reason: str) -> Dict:
    """LLM 不可用时的降级结构化报告（基于 RCA 算法包，非空壳）。"""
    causes = evidence_package.get("candidate_causes", [])
    return {
        "summary": (evidence_package.get("summary", "") or
                    f"故障涉及 {evidence_package.get('affected_asset_count', 0)} 个资产、"
                    f"{evidence_package.get('total_alert_count', 0)} 条告警" +
                    (f"；候选根因 {causes[0]['asset_name']}" if causes else "")),
        "root_cause": causes[0] if causes else {},
        "root_causes": causes,
        "evidence": evidence_package.get("evidence_texts", []) or [],
        "timeline": str(evidence_package.get("timeline", "")),
        "recommendations": evidence_package.get("next_steps", []),
        "risks": evidence_package.get("exclusions", [])[:3],
        "action_needed": bool(causes),
        "_fallback": reason,
    }


def build_report_markdown(report_data: Dict, title: str = "") -> str:
    """把结构化报告渲染成 IM/会话可读的 Markdown。"""
    lines = [f"## 🔍 自动调查报告{'：' + title if title else ''}\n"]
    summary = report_data.get("summary", "")
    if summary:
        lines.append(f"### 结论\n{summary}\n")

    causes = report_data.get("root_causes") or []
    if causes:
        lines.append("### 候选根因")
        for c in causes:
            conf = c.get("confidence", "medium")
            icon = "🔴" if conf == "high" else "🟡" if conf == "medium" else "⚪"
            lines.append(f"- {icon} **{c.get('asset', c.get('asset_name', ''))}**（{conf}）：{c.get('reason', '')}")

    evidence = report_data.get("evidence") or []
    if evidence:
        lines.append("### 证据")
        for e in evidence[:8]:
            lines.append(f"- {e}")

    tl = report_data.get("timeline")
    if tl:
        lines.append(f"### 时间线\n{tl}")

    recs = report_data.get("recommendations") or []
    if recs:
        lines.append("### 建议操作")
        for r in recs[:6]:
            if isinstance(r, dict):
                pri = r.get("priority", "medium")
                icon = "🔴" if pri == "high" else "📋" if pri == "medium" else "🟢"
                lines.append(f"- {icon} {r.get('action', '')}")
            else:
                lines.append(f"- {r}")

    risks = report_data.get("risks") or []
    if risks:
        lines.append("### 风险提示")
        for r in risks[:4]:
            if isinstance(r, dict):
                lines.append(f"- ⚠️ {r.get('asset_name', r.get('reason', ''))}")
            else:
                lines.append(f"- ⚠️ {r}")

    if not summary and not causes and not evidence:
        lines.append("_未提取到有效调查内容（LLM 不可用或证据不足）。_")
    return "\n".join(lines)


# ─── C1: 调查 worker ─────────────────────────────────────────────

def run_investigation(db: Session, incident_id: int) -> Dict:
    """同步执行一次自动调查，返回报告 dict。"""
    from app.models import Incident
    from app.services import rca_service

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return {"ok": False, "error": "故障单不存在"}

    # 防重复：该 incident 已跑过则不重复
    from app.models import InvestigationReport
    existing = db.query(InvestigationReport).filter(
        InvestigationReport.incident_id == incident_id
    ).first()
    if existing:
        return {"ok": False, "error": "该故障单已调查过", "report_id": existing.id}

    report = InvestigationReport(
        incident_id=incident_id,
        title=incident.title or f"故障 #{incident.id}",
        investigation_type="root_cause",
        status=InvestigationReport.STATUS_RUNNING,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        pkg = rca_service.analyze_incident(db, incident_id)
        if "error" in pkg:
            report.status = InvestigationReport.STATUS_FAILED
            report.error_message = pkg["error"]
            db.commit()
            return {"ok": False, "error": pkg["error"], "report_id": report.id}

        # 证据包（给 LLM 抽取用）
        evidence_package = {
            "summary": pkg.get("report_md", "")[:500],
            "candidate_causes": pkg.get("candidate_causes", []),
            "affected_asset_count": pkg.get("facts", {}).get("affected_asset_count", 0),
            "total_alert_count": pkg.get("facts", {}).get("total_alert_count", 0),
            "timeline": pkg.get("timeline", {}),
            "next_steps": pkg.get("next_steps", []),
            "exclusions": pkg.get("exclusions", []),
            "evidence_texts": [
                f"{f['metric']} 资产#{f['asset_id']} 严重度{f['severity_cn']} {f['message']}"
                for f in pkg.get("facts", {}).get("anomalies", [])[:10]
            ],
        }

        # C2: 二次 LLM 抽取结构化报告
        report_data = _call_llm_extract(db, evidence_package)
        report.report_data = json.dumps(report_data, ensure_ascii=False, default=str)
        report.report_md = build_report_markdown(report_data, incident.title)
        report.evidence_summary = json.dumps(evidence_package.get("evidence_texts", [])[:5], ensure_ascii=False)
        report.status = InvestigationReport.STATUS_COMPLETED
        report.completed_at = datetime.now()
        db.commit()

        # C3: 回写聊天会话 + IM
        _writeback(db, report, report_data, incident)

        return {"ok": True, "report_id": report.id, "status": report.status}
    except Exception as e:
        logger.error(f"[auto-investigate] incident#{incident_id} 调查异常: {e}")
        report.status = InvestigationReport.STATUS_FAILED
        report.error_message = str(e)[:500]
        report.completed_at = datetime.now()
        db.commit()
        return {"ok": False, "error": str(e), "report_id": report.id}


def _writeback(db: Session, report, report_data: Dict, incident) -> None:
    """C3: 报告回写——聊天会话 + 双向 IM 渠道。失败不影响主流程。"""
    md = report.report_md or build_report_markdown(report_data, incident.title)
    try:
        # 1) 聊天会话：创建/复用 incident 专用会话并写入 assistant 消息
        from app.models import ChatSession, ChatMessage, User
        admin = db.query(User).filter(User.role == "admin").first()
        user_id = admin.id if admin else 1
        session = db.query(ChatSession).filter(
            ChatSession.title == f"[自动调查] {incident.title}",
        ).first()
        if not session:
            session = ChatSession(
                user_id=user_id, title=f"[自动调查] {incident.title}",
                mode=ChatSession.MODE_AGENT, sub_agent="general",
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        db.add(ChatMessage(
            session_id=session.id, role=ChatMessage.ROLE_ASSISTANT,
            message_type="analysis",
            message_content=f"**自动调查报告（故障 #{incident.id}）**\n\n{md}",
            sub_agent="general",
        ))
        db.commit()
    except Exception as e:
        logger.warning(f"[auto-investigate] 会话回写失败: {e}")

    try:
        # 2) IM 渠道：启用双向的渠道推送（不打扰单向 webhook）
        from app.models import NotificationChannel
        from app.services.im_chatops_service import reply_to_im
        channels = db.query(NotificationChannel).filter(
            NotificationChannel.bidirectional == True,
            NotificationChannel.enabled == True,
        ).all()
        for ch in channels:
            chat_id = ""
            if ch.channel_config:
                try:
                    chat_id = json.loads(ch.channel_config).get("chat_id", "")
                except Exception:
                    chat_id = ""
            if not chat_id:
                continue
            ok, resp = reply_to_im(ch, chat_id, md[:3900])
            if not ok:
                logger.warning(f"[auto-investigate] IM 回写 {ch.name} 失败: {resp}")
    except Exception as e:
        logger.warning(f"[auto-investigate] IM 回写异常: {e}")


def auto_investigate_new_incidents(db: Session, lookback_minutes: int = 30, max_incidents: int = 5) -> int:
    """C1: 后台轮询——扫描新产生的未调查 high/critical incident，异步 spawn 调查 worker。

    由 main.py background_loop 周期调用。每 incident 只调查一次（ai_rca_at / InvestigationReport 去重）。
    """
    from app.models import Incident
    from datetime import timedelta
    recent = db.query(Incident).filter(
        Incident.status == "open",
        Incident.created_at >= (datetime.now() - timedelta(minutes=lookback_minutes)),
        Incident.severity.in_(["critical", "high"]),
    ).order_by(Incident.id.desc()).limit(max_incidents * 3).all()

    # 记录当前会话对应的库模式，worker 沿用同一库
    mode = _session_mode(db)
    spawned = 0
    for inc in recent:
        # 防重复：已调查（ai_rca_at 或已有 report）跳过
        if inc.ai_rca_at:
            continue
        from app.models import InvestigationReport
        has_report = db.query(InvestigationReport).filter(
            InvestigationReport.incident_id == inc.id,
            InvestigationReport.status == InvestigationReport.STATUS_COMPLETED,
        ).first()
        if has_report:
            inc.ai_rca_at = datetime.now()
            db.commit()
            continue

        # 标记正在调查（并发防重）
        inc.ai_rca_at = datetime.now()
        db.commit()

        # 异步 spawn worker（独立 session，与当前库一致）
        _spawn_worker(inc.id, mode)
        spawned += 1
        logger.info(f"[auto-investigate] 已 spawn incident#{inc.id} 调查 worker")
        if spawned >= max_incidents:
            break
    return spawned


def _session_mode(db: Session) -> str:
    """推断 session 对应的库模式：优先用其 bind 匹配，fallback 全局模式。"""
    try:
        from app.database import get_all_engines, get_db_mode
        bind = db.get_bind()
        for mode, eng in get_all_engines().items():
            if bind is eng:
                return mode
    except Exception:
        pass
    from app.database import get_db_mode
    return get_db_mode()


def _spawn_worker(incident_id: int, mode: str = None):
    """后台线程跑调查（独立 DB session，避免与请求 session 冲突）。"""
    if not mode:
        from app.database import get_db_mode
        mode = get_db_mode()
    def _run():
        from app.database import get_session_for
        db = get_session_for(mode)()
        try:
            run_investigation(db, incident_id)
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True).start()


def run_investigation_async(incident_id: int, db: Session = None):
    """供 API 手动触发：异步启动一次调查。db 传参会复用其库模式。"""
    mode = _session_mode(db) if db is not None else None
    _spawn_worker(incident_id, mode)
