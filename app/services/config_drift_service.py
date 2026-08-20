"""配置漂移检测与 AI 配置推荐服务 (对标天穹「AI 智能化配置」)

能力:
  - 内置配置采集模板(按资产 ci_type 匹配默认需采集的配置文件/配置项)
  - capture_baseline   : 建立配置基线(SSH 读取内容 + 哈希 + 版本)
  - refresh_baseline   : 手动刷新某资产基线(接受新基线, 视为正常变更, version+1)
  - detect_drift       : 检测漂移(重新采集, 与基线对比, 记录 diff + AI 评估)
  - ai_assess          : LLM 评估漂移(根因 / 影响 / 推荐修正方案 / 变更风险评估)
  - resolve_drift      : 标记已确认 / 已解决 / 忽略
适用于: 服务器系统配置、Nginx/Redis/MySQL 等中间件配置、K8s 配置。
"""
import hashlib
import json
import re
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models import Asset, ConfigBaseline, ConfigDriftRecord
from app.routers.agent_sse import _clean_key_point

# 内置采集模板: 按资产 ci_type 匹配要采集的配置项
import logging
logger = logging.getLogger(__name__)

_BUILTIN_TEMPLATES = [
    {
        "ci_type": "server",
        "name": "操作系统关键配置",
        "key": "sysctl.conf",
        "category": "system",
        "command": "cat /etc/sysctl.conf 2>/dev/null || echo NO_FILE",
    },
    {
        "ci_type": "server",
        "name": "SSH 服务配置",
        "key": "sshd_config",
        "category": "system",
        "command": "grep -vE '^\\s*(#|$)' /etc/ssh/sshd_config 2>/dev/null | grep -vE '^#' || echo NO_FILE",
    },
    {
        "ci_type": "server",
        "name": "资源限制配置",
        "key": "limits.conf",
        "category": "system",
        "command": "cat /etc/security/limits.conf 2>/dev/null | grep -vE '^\\s*(#|$)' || echo NO_FILE",
    },
    {
        "ci_type": "nginx",
        "name": "Nginx 主配置",
        "key": "nginx.conf",
        "category": "nginx",
        "command": "cat /etc/nginx/nginx.conf 2>/dev/null || cat /usr/local/nginx/conf/nginx.conf 2>/dev/null || echo NO_FILE",
    },
    {
        "ci_type": "redis",
        "name": "Redis 配置",
        "key": "redis.conf",
        "category": "redis",
        "command": "cat /etc/redis/redis.conf 2>/dev/null || cat /usr/local/etc/redis.conf 2>/dev/null || echo NO_FILE",
    },
    {
        "ci_type": "mysql",
        "name": "MySQL 配置",
        "key": "my.cnf",
        "category": "mysql",
        "command": "cat /etc/my.cnf 2>/dev/null || cat /etc/mysql/my.cnf 2>/dev/null || echo NO_FILE",
    },
    {
        "ci_type": "k8s",
        "name": "Kubelet 配置",
        "key": "kubelet.conf",
        "category": "k8s",
        "command": "cat /var/lib/kubelet/config.yaml 2>/dev/null || echo NO_FILE",
    },
]

_CI_ALIASES = {"virtual_machine": "server", "vm": "server", "host": "server", "physical_machine": "server"}


def _normalize_ci(ci_type):
    return _CI_ALIASES.get(ci_type, ci_type) if ci_type else "server"


def _exec_ssh(asset: Asset, command: str) -> tuple:
    """通过 SSH 远程执行命令, 返回 (成功?, 内容)"""
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=15)
    except Exception as e:
        return (False, f"SSH 连接失败: {e}")
    try:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=20)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        ssh.close()
        if out == "NO_FILE":
            return (True, "NO_FILE")  # 文件不存在是正常状态
        return (True, out)
    except Exception as e:
        try:
            ssh.close()
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
        return (False, f"命令执行失败: {e}")


def get_builtin_templates(ci_type: str) -> List[dict]:
    """按资产 ci_type 返回适用的内置采集模板(含 all 通配)"""
    ci = _normalize_ci(ci_type)
    templates = [t for t in _BUILTIN_TEMPLATES if t["ci_type"] in (ci, "all")]
    # server 通配: server 模板对 server/nginx/redis/mysql/k8s 等均可用作系统级检查
    if ci != "server":
        templates.extend([t for t in _BUILTIN_TEMPLATES if t["ci_type"] == "server"])
    seen = set()
    result = []
    for t in templates:
        if t["key"] not in seen:
            seen.add(t["key"])
            result.append(t)
    return result


def list_builtin_templates(db: Session) -> List[dict]:
    """内置采集模板清单(供前端展示可选的配置项)"""
    result = []
    for t in _BUILTIN_TEMPLATES:
        result.append({
            "key": t["key"],
            "name": t["name"],
            "category": t["category"],
            "ci_type": t["ci_type"],
            "command": t["command"],
        })
    return result


# ───────────── 配置基线 ─────────────

def list_baselines(db: Session, asset_id: Optional[int] = None) -> List[dict]:
    q = db.query(ConfigBaseline)
    if asset_id:
        q = q.filter(ConfigBaseline.asset_id == asset_id)
    rows = q.order_by(ConfigBaseline.asset_id, ConfigBaseline.id).all()
    result = []
    for b in rows:
        result.append(_baseline_to_dict(b))
    return result


def _baseline_to_dict(b: ConfigBaseline) -> dict:
    return {
        "id": b.id,
        "asset_id": b.asset_id,
        "config_key": b.config_key,
        "config_name": b.config_name,
        "category": b.category,
        "source_command": b.source_command,
        "content": b.content,
        "content_hash": b.content_hash,
        "version": b.version,
        "baseline_at": b.baseline_at.isoformat() if b.baseline_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def capture_baseline(db: Session, asset_id: int, config_key: str,
                     config_name: str = "", category: str = "custom",
                     source_command: str = "") -> dict:
    """对指定资产建立/更新配置基线。已存在同 key 基线则更新内容并 version+1。"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise ValueError("资产不存在")

    if not source_command:
        tpl = next((t for t in _BUILTIN_TEMPLATES if t["key"] == config_key), None)
        if tpl:
            source_command = tpl["command"]
            config_name = config_name or tpl["name"]
            category = category or tpl["category"]
    if not source_command:
        raise ValueError("未提供采集命令(source_command), 无法采集配置")

    success, content = _exec_ssh(asset, source_command)
    if not success:
        raise ValueError(f"采集失败: {content}")

    existing = db.query(ConfigBaseline).filter(
        ConfigBaseline.asset_id == asset_id,
        ConfigBaseline.config_key == config_key,
    ).first()

    content_hash = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()

    if existing:
        existing.content = content
        existing.content_hash = content_hash
        existing.source_command = source_command
        existing.config_name = config_name or existing.config_name
        existing.category = category or existing.category
        existing.version = (existing.version or 1) + 1
        existing.updated_at = datetime.now()
        db.commit()
        return _baseline_to_dict(existing)

    baseline = ConfigBaseline(
        asset_id=asset_id,
        config_key=config_key,
        config_name=config_name,
        category=category,
        source_command=source_command,
        content=content,
        content_hash=content_hash,
        version=1,
        baseline_at=datetime.now(),
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return _baseline_to_dict(baseline)


def delete_baseline(db: Session, baseline_id: int) -> bool:
    b = db.query(ConfigBaseline).filter(ConfigBaseline.id == baseline_id).first()
    if not b:
        return False
    db.delete(b)
    db.commit()
    return True


# ───────────── 漂移检测 ─────────────

def _diff_text(old: str, new: str) -> str:
    """简单逐行 diff, 输出 +新增 / -减少 / ~修改 行"""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    old_set = {ln.strip() for ln in old_lines if ln.strip()}
    new_set = {ln.strip() for ln in new_lines if ln.strip()}
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    lines = []
    for ln in removed:
        lines.append(f"- {ln}")
    for ln in added:
        lines.append(f"+ {ln}")
    return "\n".join(lines)


def detect_drift(db: Session, asset_id: int, config_key: str,
                 config_name: str = "", category: str = "custom",
                 source_command: str = "") -> dict:
    """检测指定资产配置项是否漂移。
    与基线对比, 一致则返回 clean; 不一致则创建/更新 ConfigDriftRecord 并触发 AI 评估。
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise ValueError("资产不存在")

    baseline = db.query(ConfigBaseline).filter(
        ConfigBaseline.asset_id == asset_id,
        ConfigBaseline.config_key == config_key,
    ).first()
    if not baseline:
        return {"exist": False, "message": f"资产 {asset.name} 暂无配置基线 [{config_key}], 请先建立基线", "drifted": False}

    if not source_command:
        source_command = baseline.source_command
    success, content = _exec_ssh(asset, source_command)
    if not success:
        raise ValueError(f"采集当前配置失败: {content}")

    if baseline.content_hash and baseline.content_hash == hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest():
        return {"exist": True, "drifted": False, "message": "配置与基线一致, 无漂移"}

    # 有漂移
    drift_type = "content"
    if not content.strip() or content.strip() == "NO_FILE":
        drift_type = "removed"
    elif not baseline.content.strip() or baseline.content.strip() == "NO_FILE":
        drift_type = "added"
    diff = _diff_text(baseline.content, content)
    drift_count = len([ln for ln in diff.splitlines() if ln]) if diff else 1

    record = db.query(ConfigDriftRecord).filter(
        ConfigDriftRecord.asset_id == asset_id,
        ConfigDriftRecord.config_key == config_key,
        ConfigDriftRecord.status.in_(["open", "acknowledged"]),
    ).order_by(ConfigDriftRecord.detected_at.desc()).first()

    if record:
        # 更新已有 open 记录
        record.current_content = content
        record.diff_text = diff
        record.drift_count = drift_count
        record.drift_type = drift_type
        record.detected_at = datetime.now()
        db.commit()
        return {"exist": True, "drifted": True, "record_id": record.id,
                "diff_text": diff, "drift_count": drift_count, "status": record.status}

    record = ConfigDriftRecord(
        asset_id=asset_id,
        baseline_id=baseline.id,
        config_key=config_key,
        config_name=config_name or baseline.config_name,
        category=category or baseline.category,
        baseline_content=baseline.content,
        current_content=content,
        drift_type=drift_type,
        diff_text=diff,
        drift_count=drift_count,
        severity="medium",
        status="open",
        detected_at=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 尝试 AI 评估(失败不阻断)
    try:
        ai = ai_assess(db, record.id)
    except Exception:
        ai = None

    return {"exist": True, "drifted": True, "record_id": record.id,
            "diff_text": diff, "drift_count": drift_count, "status": "open",
            "ai_assessment": ai}


def list_drifts(db: Session, asset_id: Optional[int] = None,
                status: Optional[str] = None, limit: int = 100) -> List[dict]:
    q = db.query(ConfigDriftRecord)
    if asset_id:
        q = q.filter(ConfigDriftRecord.asset_id == asset_id)
    if status:
        q = q.filter(ConfigDriftRecord.status == status)
    rows = q.order_by(ConfigDriftRecord.detected_at.desc()).limit(limit).all()
    result = []
    for r in rows:
        d = _drift_to_dict(r)
        d["asset_name"] = db.query(Asset.name).filter(Asset.id == r.asset_id).scalar() or ""
        result.append(d)
    return result


def get_drift(db: Session, drift_id: int) -> Optional[dict]:
    r = db.query(ConfigDriftRecord).filter(ConfigDriftRecord.id == drift_id).first()
    if not r:
        return None
    d = _drift_to_dict(r)
    d["asset_name"] = db.query(Asset.name).filter(Asset.id == r.asset_id).scalar() or ""
    return d


def _drift_to_dict(r: ConfigDriftRecord) -> dict:
    return {
        "id": r.id,
        "asset_id": r.asset_id,
        "baseline_id": r.baseline_id,
        "config_key": r.config_key,
        "config_name": r.config_name,
        "category": r.category,
        "baseline_content": r.baseline_content,
        "current_content": r.current_content,
        "drift_type": r.drift_type,
        "diff_text": r.diff_text,
        "drift_count": r.drift_count,
        "severity": r.severity,
        "status": r.status,
        "ai_assessment": r.ai_assessment,
        "detected_at": r.detected_at.isoformat() if r.detected_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
    }


def set_drift_status(db: Session, drift_id: int, status: str) -> Optional[dict]:
    """更新漂移状态: open/acknowledged/resolved/ignored"""
    r = db.query(ConfigDriftRecord).filter(ConfigDriftRecord.id == drift_id).first()
    if not r:
        return None
    r.status = status
    if status == "resolved":
        r.resolved_at = datetime.now()
    db.commit()
    db.refresh(r)
    return _drift_to_dict(r)


def get_drift_stats(db: Session) -> dict:
    open_count = db.query(ConfigDriftRecord).filter(
        ConfigDriftRecord.status.in_(["open", "acknowledged"])).count()
    resolved_count = db.query(ConfigDriftRecord).filter(
        ConfigDriftRecord.status == "resolved").count()
    total_baseline = db.query(ConfigBaseline).count()
    drifted_assets = db.query(ConfigDriftRecord.asset_id).filter(
        ConfigDriftRecord.status.in_(["open", "acknowledged"])
    ).distinct().count()
    return {
        "open_count": open_count,
        "resolved_count": resolved_count,
        "total_baseline": total_baseline,
        "drifted_assets": drifted_assets,
    }


# ───────────── AI 评估 ─────────────

def ai_assess(db: Session, drift_id: int) -> dict:
    """LLM 评估漂移: 根因 / 影响 / 推荐修正方案 / 变更风险评估"""
    r = db.query(ConfigDriftRecord).filter(ConfigDriftRecord.id == drift_id).first()
    if not r:
        raise ValueError("漂移记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    asset_name = asset.name if asset else f"资产#{r.asset_id}"
    asset_ip = asset.ip if asset else ""

    from app.services.agent_service import call_llm
    from app.models import AIProvider
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    if not provider:
        return _rule_assessment(r)

    system_prompt = """你是企业 IT 配置漂移分析专家。根据资产配置基线与当前配置的差异, 输出配置漂移分析报告。
只输出 JSON, 格式:
{"summary":"一句话根因说明","root_cause":"可能的变更原因","impact":"配置漂移可能造成的影响",
 "severity":"low|medium|high|critical","recommendation":"推荐的修正配置方案(具体命令或配置片段)",
 "risk":"修正该配置的变更风险评估","change_action":"建议的处置动作 apply|review|ignore"}"""

    user_prompt = f"""资产: {asset_name} ({asset_ip})
配置项: {r.config_key} ({r.config_name}, 分类={r.category})
漂移类型: {r.drift_type}

--- 基线配置内容 ---
{r.baseline_content[:2000]}

--- 当前配置内容 ---
{r.current_content[:2000]}

--- 差异 ---
{r.diff_text[:2000]}

请分析该配置漂移的根因、影响, 并给出推荐修正方案与变更风险评估。"""

    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        assessment = {
            "ai_generated": True,
            "summary": parsed.get("summary", ""),
            "root_cause": parsed.get("root_cause", ""),
            "impact": parsed.get("impact", ""),
            "severity": parsed.get("severity", "medium"),
            "recommendation": parsed.get("recommendation", ""),
            "risk": parsed.get("risk", ""),
            "change_action": parsed.get("change_action", "review"),
            "assessed_at": datetime.now().isoformat(),
        }
    except Exception:
        assessment = _rule_assessment(r)

    assessment["summary_block"] = {
        "root_cause": _clean_key_point(assessment.get("root_cause") or assessment.get("summary", ""), 100),
        "solution": _clean_key_point(assessment.get("recommendation", ""), 160),
        "impact": _clean_key_point(assessment.get("impact", ""), 100),
    }

    # 同步严重级别
    r.severity = assessment.get("severity", r.severity)
    try:
        r.ai_assessment = json.dumps(assessment, ensure_ascii=False)
    except Exception:
        r.ai_assessment = ""
    db.commit()
    return assessment


def _rule_assessment(r: ConfigDriftRecord) -> dict:
    """无 AI provider 时的规则兜底评估"""
    if r.drift_type == "removed":
        sev = "high"
        summary = "配置文件被删除, 可能造成服务异常"
    elif r.drift_count >= 5:
        sev = "high"
        summary = f"检测到 {r.drift_count} 处配置漂移"
    elif r.drift_count >= 1:
        sev = "medium"
        summary = f"检测到 {r.drift_count} 处配置与基线不一致"
    else:
        sev = "low"
        summary = "配置存在轻微差异"
    return {
        "ai_generated": False,
        "summary": summary,
        "root_cause": "配置被外部修改",
        "impact": "可能影响服务稳定性",
        "severity": sev,
        "recommendation": "建议对比基线恢复配置, 并确认变更来源",
        "risk": "中等",
        "change_action": "review",
        "assessed_at": datetime.now().isoformat(),
    }


def seed_demo_if_empty(db: Session) -> None:
    """(可选) 若基线为空, 不自动造数, 保持干净"""
    return
