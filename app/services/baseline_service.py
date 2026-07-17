import json
import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models import Asset, SecurityBaselineTemplate, AssetBaselineCheck

_CI_ALIASES = {"virtual_machine": "server", "vm": "server", "host": "server", "physical_machine": "server"}


def _normalize_ci(ci_type):
    return _CI_ALIASES.get(ci_type, ci_type) if ci_type else "server"


def get_baseline_templates(asset, db: Session) -> list:
    """按资产 ci_type 匹配基线模板，合并已有检测结果"""
    ci_type = _normalize_ci(asset.ci_type)
    templates = (
        db.query(SecurityBaselineTemplate)
        .filter(SecurityBaselineTemplate.ci_type.in_([ci_type, "all"]), SecurityBaselineTemplate.enabled == True)
        .order_by(SecurityBaselineTemplate.sort_order)
        .all()
    )
    existing = _get_existing_checks(asset.id, db)

    results = []
    for tpl in templates:
        check = existing.get(tpl.id)
        results.append({
            "template_id": tpl.id,
            "check_key": tpl.check_key,
            "check_name": tpl.check_name,
            "category": tpl.category,
            "severity": tpl.severity,
            "description": tpl.description,
            "check_method": tpl.check_method,
            "check_command": tpl.check_command,
            "expect_match": tpl.expect_match,
            "remediation": tpl.remediation,
            "status": check["status"] if check else "pending",
            "actual_value": check["actual_value"] if check else "",
            "checked_at": check["checked_at"] if check else None,
        })
    return results


def run_check(asset: Asset, template: SecurityBaselineTemplate, db: Session) -> dict:
    """对单个资产执行单条基线检查（自动检测或标注）"""
    if template.check_method == "manual":
        return {"status": "na", "actual_value": "", "reason": "需人工确认"}

    # 按检测方法分发
    method = template.check_method
    try:
        if method == "ssh":
            success, output = _exec_ssh(asset, template.check_command)
        elif method == "sql":
            success, output = _exec_sql(asset, template.check_command)
        elif method == "redis":
            success, output = _exec_redis(asset, template.check_command)
        else:
            return {"status": "na", "actual_value": "", "reason": f"不支持的检测方法: {method}"}

        if not success:
            return {"status": "na", "actual_value": output[:200], "reason": f"执行失败: {output[:200]}"}

        # 用 expect_match 正则判断 pass/fail
        status = _match_result(output, template.expect_match)
        return {"status": status, "actual_value": output[:200], "reason": ""}
    except Exception as e:
        return {"status": "na", "actual_value": "", "reason": f"异常: {e}"}


def save_check(asset_id: int, template_id: int, status: str, actual_value: str = "", reason: str = "", db: Optional[Session] = None):
    db_local = False
    if db is None:
        from app.database import get_session_for
        db = get_session_for("demo")()
        db_local = True
    try:
        existing = (
            db.query(AssetBaselineCheck)
            .filter(
                AssetBaselineCheck.asset_id == asset_id,
                AssetBaselineCheck.template_id == template_id,
            )
            .first()
        )
        if existing:
            existing.status = status
            existing.actual_value = actual_value
            existing.reason = reason
            existing.checked_at = datetime.now()
        else:
            check = AssetBaselineCheck(
                asset_id=asset_id,
                template_id=template_id,
                status=status,
                actual_value=actual_value,
                reason=reason,
                checked_at=datetime.now(),
            )
            db.add(check)
        db.commit()
    finally:
        if db_local:
            db.close()


def run_all_checks(asset: Asset, db: Session) -> dict:
    """对资产运行所有可自动检测的基线"""
    from app.models import SecurityBaselineTemplate
    templates = (
        db.query(SecurityBaselineTemplate)
        .filter(
            SecurityBaselineTemplate.ci_type.in_([_normalize_ci(asset.ci_type), "all"]),
            SecurityBaselineTemplate.enabled == True,
        )
        .all()
    )
    results = []
    for tpl in templates:
        result = run_check(asset, tpl, db)
        save_check(asset.id, tpl.id, result["status"], result.get("actual_value", ""), result.get("reason", ""), db)
        results.append({
            **result,
            "check_key": tpl.check_key,
            "check_name": tpl.check_name,
            "severity": tpl.severity,
            "category": tpl.category,
            "template_id": tpl.id,
        })
    return {"asset_id": asset.id, "total": len(results), "results": results}


def ai_analyze(asset: Asset, checks: list, db: Session) -> dict:
    """AI 分析基线检查结果，输出安全报告"""
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    na_count = sum(1 for c in checks if c["status"] in ("na", "pending"))

    try:
        from app.services.agent_service import call_llm
        from app.models import AIProvider
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        if not provider:
            return _rule_report(fail_count, pass_count, na_count, checks)

        fails = [c for c in checks if c["status"] == "fail"]
        system_prompt = """你是 AIOps 安全基线分析专家。根据资产的基线检查结果，输出安全分析报告。
输出 JSON 格式：{"summary":"总体安全评估","risk_level":"critical|high|medium|low","score":0-100,"top_risks":[{"item":"...","risk":"...","suggestion":"..."}],"fix_priority":["修复建议1","修复建议2"]}"""

        user_prompt = f"""资产名称: {asset.name}
CI 类型: {asset.ci_type}
IP: {asset.ip}

检查结果: {json.dumps(checks, ensure_ascii=False, default=str)}
不合规项: {json.dumps(fails, ensure_ascii=False, default=str)}

请输出 JSON 安全分析报告。"""

        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return _rule_report(fail_count, pass_count, na_count, checks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        return {
            "ai_generated": True,
            "score": parsed.get("score", 100 - fail_count * 10),
            "risk_level": parsed.get("risk_level", "medium"),
            "summary": parsed.get("summary", ""),
            "top_risks": parsed.get("top_risks", []),
            "fix_priority": parsed.get("fix_priority", []),
            "fail_count": fail_count,
            "pass_count": pass_count,
            "na_count": na_count,
        }
    except Exception:
        return _rule_report(fail_count, pass_count, na_count, checks)


def _rule_report(fail_count, pass_count, na_count, checks):
    score = max(0, 100 - fail_count * 10)
    if fail_count == 0:
        risk = "low"
        summary = "未发现不合规项，安全状况良好"
    elif fail_count <= 2:
        risk = "medium"
        summary = f"发现 {fail_count} 项不合规，建议优先处理高风险项"
    elif fail_count <= 5:
        risk = "high"
        summary = f"发现 {fail_count} 项不合规，安全风险较高，建议立即处置"
    else:
        risk = "critical"
        summary = f"发现 {fail_count} 项不合规，安全状况严重，必须立即整改"

    fails = [c for c in checks if c["status"] == "fail"]
    top_risks = [{"item": c["check_name"], "risk": c.get("actual_value", ""), "suggestion": c.get("remediation", "")} for c in fails[:5]]

    return {
        "ai_generated": False,
        "score": score,
        "risk_level": risk,
        "summary": summary,
        "top_risks": top_risks,
        "fix_priority": [c.get("remediation", "") for c in fails[:3] if c.get("remediation")],
        "fail_count": fail_count,
        "pass_count": pass_count,
        "na_count": na_count,
    }


def _get_existing_checks(asset_id: int, db: Session) -> dict:
    rows = (
        db.query(AssetBaselineCheck)
        .filter(AssetBaselineCheck.asset_id == asset_id)
        .all()
    )
    result = {}
    for r in rows:
        result[r.template_id] = {
            "status": r.status,
            "actual_value": r.actual_value,
            "checked_at": r.checked_at.strftime("%Y-%m-%d %H:%M:%S") if r.checked_at else None,
        }
    return result


def _match_result(output: str, expect_pattern: str) -> str:
    if not expect_pattern:
        return "pass" if output else "fail"
    try:
        if re.search(expect_pattern, output, re.IGNORECASE):
            return "pass"
        else:
            return "fail"
    except re.error:
        return "pass" if expect_pattern in output else "fail"


def _exec_ssh(asset: Asset, command: str) -> tuple:
    """通过 SSH 远程执行命令"""
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=15)
    except Exception as e:
        return (False, f"SSH 连接失败: {e}")
    try:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        output = "\n".join(s for s in [out, err] if s)
        return (code == 0, output or f"exit_code={code}")
    except Exception as e:
        return (False, f"命令执行异常: {e}")
    finally:
        ssh.close()


def _exec_sql(asset: Asset, sql: str) -> tuple:
    """通过 pymysql 执行 SQL 检查"""
    import pymysql
    config = _get_connection_config(asset)
    try:
        conn = pymysql.connect(
            host=asset.ip,
            port=config.get("mysql_port", 3306),
            user=config.get("mysql_user", "root"),
            password=config.get("mysql_password", ""),
            connect_timeout=10,
            read_timeout=15,
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            output = "\n".join(str(r[0]) for r in rows) if rows else "(empty)"
        conn.close()
        return (True, output)
    except Exception as e:
        return (False, f"SQL 执行失败: {e}")


def _exec_redis(asset: Asset, command: str) -> tuple:
    """通过 redis-cli 执行命令"""
    config = _get_connection_config(asset)
    password = config.get("redis_password", "")
    try:
        import subprocess
        cmd_list = ["redis-cli", "-h", asset.ip, "-p", str(config.get("redis_port", 6379))]
        if password:
            cmd_list.extend(["-a", password])
        # Split the command into arguments
        parts = command.split()
        cmd_list.extend(parts)
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=15)
        out = result.stdout.strip()
        err = result.stderr.strip()
        output = "\n".join(s for s in [out, err] if s)
        return (result.returncode == 0, output or f"exit_code={result.returncode}")
    except Exception as e:
        return (False, f"Redis 执行失败: {e}")


def _get_connection_config(asset: Asset) -> dict:
    try:
        raw = getattr(asset, "connection_config", "{}") or "{}"
        if isinstance(raw, str):
            return json.loads(raw)
        elif isinstance(raw, dict):
            return raw
    except (json.JSONDecodeError, TypeError):
        pass
    return {}
