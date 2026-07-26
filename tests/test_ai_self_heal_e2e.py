"""
AI 自愈功能端到端多轮场景测试

测试链路: 告警触发 → AI 自动定位根因 → 生成修复命令 → 人工审批 → 执行 → 日志落库
覆盖 6 轮场景:
  1. 完整成功链路 (mock LLM + mock SSH 成功)
  2. 取消链路
  3. 危险命令拦截 (rm -rf /)
  4. SSH 失败 fail-soft (真实不可达资产)
  5. 边界测试 (不存在告警/动作、重复确认、已取消再确认)
  6. HTTP 接口层测试 (triggered-alerts/ai-pending/ai-analyze/confirm/cancel)

通过 monkeypatch mock call_llm / _remote_exec，不依赖真实 LLM API 和 SSH 可达性。
"""
import os
import sys
import json
import time
import importlib
from datetime import datetime
from unittest.mock import patch

# 路径基于 __file__ 动态计算
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from app.database import get_session_for, set_db_mode
from app.models import Alert, Asset, AIProvider, PendingAction, RemediationLog
from app.services import remediation_service

# 强制使用 demo 库
set_db_mode("demo")
DB_FACTORY = get_session_for("demo")

# ── 测试结果统计 ──
_results = []  # [(round_name, case_name, passed, detail)]


def record(round_name, case_name, passed, detail=""):
    _results.append((round_name, case_name, "PASS" if passed else "FAIL", detail))
    status = "✅" if passed else "❌"
    print(f"  {status} [{round_name}] {case_name}" + (f" — {detail}" if detail else ""))


def _make_alert(db, asset_id, metric, severity, message, actual=95.0, threshold=80.0):
    """构造一条 triggered 状态告警，返回 Alert 对象."""
    a = Alert(
        rule_id=None,
        asset_id=asset_id,
        metric_name=metric,
        severity=severity,
        message=message,
        actual_value=actual,
        threshold=threshold,
        status="triggered",
        created_at=datetime.now(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _make_mock_llm_response(content_json: dict):
    """构造一个假的 OpenAI chat completion 响应."""
    return {
        "choices": [
            {
                "message": {
                    "content": "```json\n" + json.dumps(content_json, ensure_ascii=False) + "\n```"
                }
            }
        ]
    }


def _cleanup_alert(db, alert_id):
    """清理测试告警及相关 PendingAction 和 RemediationLog."""
    for pa in db.query(PendingAction).filter(PendingAction.alert_id == alert_id).all():
        db.delete(pa)
    db.query(RemediationLog).filter(RemediationLog.alert_id == alert_id).delete()
    db.query(Alert).filter(Alert.id == alert_id).delete()
    db.commit()


# ════════════════════════════════════════════════════════════════════
# 第 1 轮: 完整成功链路
# ════════════════════════════════════════════════════════════════════
def round1_success_full_chain():
    print("\n" + "=" * 70)
    print("第 1 轮: 完整成功链路 (告警 → AI分析 → 审批 → 执行 → 日志落库)")
    print("=" * 70)
    db = DB_FACTORY()
    alert = None
    try:
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "cpu_usage", "critical",
                            "CPU 使用率 95% 超过阈值 80%", actual=95.0, threshold=80.0)
        record("R1", "构造告警", alert.id is not None, f"alert_id={alert.id} asset={asset.name}")

        mock_resp = _make_mock_llm_response({
            "root_cause": "nginx 进程内存泄漏导致 CPU 飙升",
            "impact": "web 服务响应变慢，影响线上用户",
            "risk_level": "low",
            "action_type": "restart",
            "command": "systemctl restart nginx",
            "command_description": "重启 nginx 服务",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp) as m_llm:
            with patch.object(remediation_service, "_remote_exec",
                              return_value=(True, "nginx 服务已重启成功")) as m_ssh:
                result = remediation_service.ai_self_heal_analyze(db, alert.id)

        record("R1", "AI 分析返回 ok", result.get("ok") is True, str(result.get("error", "")))
        record("R1", "AI 分析根因正确",
               "nginx" in result.get("analysis", {}).get("root_cause", ""),
               result.get("analysis", {}).get("root_cause", ""))
        pa_id = result.get("pending_action_id")
        record("R1", "生成 PendingAction", pa_id is not None, f"pa_id={pa_id}")

        pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
        record("R1", "动作状态=pending", pa.status == "pending", pa.status)
        record("R1", "动作 alert_id 关联", pa.alert_id == alert.id, f"alert_id={pa.alert_id}")
        record("R1", "动作 action_type=restart", pa.action_type == "restart", pa.action_type)
        record("R1", "动作 risk_level=low", pa.risk_level == "low", pa.risk_level)
        payload = json.loads(pa.action_payload)
        record("R1", "payload.command 正确",
               "systemctl restart nginx" in payload.get("command", ""),
               payload.get("command", ""))

        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "nginx 服务已重启成功")):
            exec_result = remediation_service.confirm_ai_action(db, pa_id, username="test_admin")
        record("R1", "confirm 返回 ok", exec_result.get("ok") is True)
        record("R1", "confirm 执行成功", exec_result.get("success") is True,
               str(exec_result.get("output", ""))[:80])

        db.refresh(pa)
        record("R1", "动作状态变为 executed", pa.status == "executed", pa.status)
        record("R1", "confirmed_by=test_admin", pa.confirmed_by == "test_admin", pa.confirmed_by)

        log = db.query(RemediationLog).filter(
            RemediationLog.alert_id == alert.id,
            RemediationLog.action_type == "restart",
        ).order_by(RemediationLog.id.desc()).first()
        record("R1", "RemediationLog 落库", log is not None, f"log_id={log.id if log else None}")
        record("R1", "日志记录成功", log and log.is_success is True, str(log.output)[:60] if log else "")
        record("R1", "日志 action_type=restart", log and log.action_type == "restart")

        db.refresh(alert)
        record("R1", "告警状态变 acknowledged", alert.status == "acknowledged", alert.status)
        record("R1", "告警 message 追加标记", "[AI 自愈执行" in (alert.message or ""),
               (alert.message or "")[-60:])
    finally:
        if alert:
            _cleanup_alert(db, alert.id)
        db.close()


# ════════════════════════════════════════════════════════════════════
# 第 2 轮: 取消链路
# ════════════════════════════════════════════════════════════════════
def round2_cancel():
    print("\n" + "=" * 70)
    print("第 2 轮: 取消链路 (AI 分析 → 人工取消 → 状态 canceled)")
    print("=" * 70)
    db = DB_FACTORY()
    alert = None
    try:
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "disk_usage", "warning",
                            "磁盘使用率 88%", actual=88.0, threshold=80.0)

        mock_resp = _make_mock_llm_response({
            "root_cause": "/tmp 临时文件堆积",
            "impact": "磁盘空间不足",
            "risk_level": "low",
            "action_type": "clean",
            "command": "find /tmp -type f -mtime +7 -delete",
            "command_description": "清理 7 天前临时文件",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp):
            result = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id = result.get("pending_action_id")
        record("R2", "AI 分析生成动作", result.get("ok") is True and pa_id is not None)

        cancel_result = remediation_service.cancel_ai_action(db, pa_id)
        record("R2", "cancel 返回 ok", cancel_result.get("ok") is True)

        pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
        record("R2", "动作状态=canceled", pa.status == "canceled", pa.status)

        # 已取消的动作不能再确认
        exec_result = remediation_service.confirm_ai_action(db, pa_id, username="test_admin")
        record("R2", "已取消动作拒绝确认", exec_result.get("ok") is False,
               exec_result.get("error", ""))
        record("R2", "拒绝原因含状态提示", "待确认" in (exec_result.get("error", "")),
               exec_result.get("error", ""))

        # 取消后不应有 RemediationLog
        log = db.query(RemediationLog).filter(RemediationLog.alert_id == alert.id).first()
        record("R2", "取消不产生执行日志", log is None)

        # 取消后告警状态应保持 triggered（未执行不应改 acknowledged）
        db.refresh(alert)
        record("R2", "告警状态保持 triggered", alert.status == "triggered", alert.status)
    finally:
        if alert:
            _cleanup_alert(db, alert.id)
        db.close()


# ════════════════════════════════════════════════════════════════════
# 第 3 轮: 危险命令拦截
# ════════════════════════════════════════════════════════════════════
def round3_dangerous_command():
    print("\n" + "=" * 70)
    print("第 3 轮: 危险命令拦截 (rm -rf /、mkfs、shutdown、dd 等)")
    print("=" * 70)
    db = DB_FACTORY()
    alert = None
    try:
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "disk_full", "critical",
                            "磁盘 100% 满", actual=100.0, threshold=90.0)

        # 场景 3a: rm -rf /
        mock_resp = _make_mock_llm_response({
            "root_cause": "磁盘满",
            "impact": "服务不可用",
            "risk_level": "high",
            "action_type": "run_command",
            "command": "rm -rf /",
            "command_description": "删除根目录",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp):
            result = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id = result.get("pending_action_id")
        record("R3", "rm -rf / 仍生成 PendingAction", result.get("ok") is True,
               "（拦截在执行层，不在生成层）")

        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "should_not_reach")) as m_ssh:
            exec_result = remediation_service.confirm_ai_action(db, pa_id, username="test_admin")
        record("R3", "rm -rf / 执行被拦截", exec_result.get("success") is False)
        record("R3", "拦截原因含黑名单", "黑名单" in (exec_result.get("output", "")),
               exec_result.get("output", "")[:80])
        record("R3", "SSH 未被调用", not m_ssh.called, "SSH 应被黑名单拦截在调用前")

        pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
        record("R3", "rm -rf / 动作状态=failed", pa.status == "failed", pa.status)

        # 场景 3b: mkfs.ext4 /dev/sda
        mock_resp2 = _make_mock_llm_response({
            "root_cause": "磁盘满",
            "impact": "服务不可用",
            "risk_level": "critical",
            "action_type": "run_command",
            "command": "mkfs.ext4 /dev/sda",
            "command_description": "格式化磁盘",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp2):
            result2 = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id2 = result2.get("pending_action_id")
        exec_result2 = remediation_service.confirm_ai_action(db, pa_id2, username="test_admin")
        record("R3", "mkfs 被拦截", exec_result2.get("success") is False)
        record("R3", "mkfs 拦截原因含黑名单", "黑名单" in (exec_result2.get("output", "")))

        # 场景 3c: shutdown
        mock_resp3 = _make_mock_llm_response({
            "root_cause": "磁盘满",
            "impact": "服务不可用",
            "risk_level": "critical",
            "action_type": "run_command",
            "command": "shutdown -h now",
            "command_description": "关机",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp3):
            result3 = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id3 = result3.get("pending_action_id")
        exec_result3 = remediation_service.confirm_ai_action(db, pa_id3, username="test_admin")
        record("R3", "shutdown 被拦截", exec_result3.get("success") is False)

        # 场景 3d: 安全命令（df -h）应通过
        mock_resp4 = _make_mock_llm_response({
            "root_cause": "磁盘满",
            "impact": "服务不可用",
            "risk_level": "low",
            "action_type": "run_command",
            "command": "df -h",
            "command_description": "查看磁盘",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp4):
            result4 = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id4 = result4.get("pending_action_id")
        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       50G   45G  5G  90% /")):
            exec_result4 = remediation_service.confirm_ai_action(db, pa_id4, username="test_admin")
        record("R3", "df -h 安全命令通过", exec_result4.get("success") is True)
    finally:
        if alert:
            _cleanup_alert(db, alert.id)
        db.close()


# ════════════════════════════════════════════════════════════════════
# 第 4 轮: SSH 失败 fail-soft
# ════════════════════════════════════════════════════════════════════
def round4_ssh_fail_soft():
    print("\n" + "=" * 70)
    print("第 4 轮: SSH 失败 fail-soft (资产不可达，验证优雅降级)")
    print("=" * 70)
    db = DB_FACTORY()
    alert = None
    try:
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "memory_usage", "high",
                            "内存使用率 92%", actual=92.0, threshold=80.0)

        mock_resp = _make_mock_llm_response({
            "root_cause": "内存泄漏",
            "impact": "OOM 风险",
            "risk_level": "low",
            "action_type": "run_command",
            "command": "free -m",
            "command_description": "查看内存",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp):
            result = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id = result.get("pending_action_id")

        # mock SSH 连接失败
        with patch.object(remediation_service, "_remote_exec",
                          return_value=(False, "SSH 连接失败: timed out")):
            exec_result = remediation_service.confirm_ai_action(db, pa_id, username="test_admin")
        record("R4", "SSH 失败返回 ok=True（流程正常）", exec_result.get("ok") is True)
        record("R4", "SSH 失败 success=False", exec_result.get("success") is False)
        record("R4", "失败信息含 SSH", "SSH" in (exec_result.get("output", "")),
               exec_result.get("output", "")[:80])

        pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
        record("R4", "动作状态=failed", pa.status == "failed", pa.status)
        record("R4", "result_payload 记录输出", "timed out" in (pa.result_payload or ""),
               (pa.result_payload or "")[:80])

        log = db.query(RemediationLog).filter(
            RemediationLog.alert_id == alert.id
        ).order_by(RemediationLog.id.desc()).first()
        record("R4", "失败也写 RemediationLog", log is not None)
        record("R4", "日志 is_success=False", log and log.is_success is False)
    finally:
        if alert:
            _cleanup_alert(db, alert.id)
        db.close()


# ════════════════════════════════════════════════════════════════════
# 第 5 轮: 边界测试
# ════════════════════════════════════════════════════════════════════
def round5_boundary():
    print("\n" + "=" * 70)
    print("第 5 轮: 边界测试 (不存在告警/动作、重复确认、已执行再确认)")
    print("=" * 70)
    db = DB_FACTORY()
    try:
        # 5a: 不存在的告警
        r = remediation_service.ai_self_heal_analyze(db, 999999)
        record("R5", "不存在告警 AI 分析返回 ok=False", r.get("ok") is False)
        record("R5", "错误信息含'告警不存在'", "告警不存在" in (r.get("error", "")),
               r.get("error", ""))

        # 5b: 不存在的动作 confirm
        r = remediation_service.confirm_ai_action(db, 999999)
        record("R5", "不存在动作 confirm 返回 ok=False", r.get("ok") is False)
        record("R5", "错误信息含'动作不存在'", "动作不存在" in (r.get("error", "")))

        # 5c: 不存在的动作 cancel
        r = remediation_service.cancel_ai_action(db, 999999)
        record("R5", "不存在动作 cancel 返回 ok=False", r.get("ok") is False)

        # 5d: 重复确认同一动作
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "load_avg", "warning", "负载高", actual=5.0, threshold=3.0)
        mock_resp = _make_mock_llm_response({
            "root_cause": "负载高",
            "impact": "响应慢",
            "risk_level": "low",
            "action_type": "run_command",
            "command": "uptime",
            "command_description": "查看负载",
        })
        with patch("app.services.agent_service.call_llm", return_value=mock_resp):
            result = remediation_service.ai_self_heal_analyze(db, alert.id)
        pa_id = result.get("pending_action_id")
        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "load average: 5.0")):
            remediation_service.confirm_ai_action(db, pa_id, username="t1")
        # 重复确认
        r = remediation_service.confirm_ai_action(db, pa_id, username="t2")
        record("R5", "已执行动作重复确认被拒", r.get("ok") is False, r.get("error", ""))
        record("R5", "拒绝原因含状态提示", "待确认" in (r.get("error", "")), r.get("error", ""))
        _cleanup_alert(db, alert.id)

        # 5e: get_triggered_alerts 返回结构
        alerts = remediation_service.get_triggered_alerts(db, limit=5)
        record("R5", "get_triggered_alerts 返回 list", isinstance(alerts, list))
        if alerts:
            a0 = alerts[0]
            for key in ("id", "asset_id", "asset_name", "metric_name", "severity", "message", "status", "created_at"):
                record("R5", f"triggered_alert 含字段 {key}", key in a0, str(a0.keys())[:60])

        # 5f: get_ai_pending_actions 状态过滤
        all_items = remediation_service.get_ai_pending_actions(db, status="all")
        pending_items = remediation_service.get_ai_pending_actions(db, status="pending")
        record("R5", "ai-pending status=all 返回 list", isinstance(all_items, list))
        record("R5", "ai-pending status=pending 返回 list", isinstance(pending_items, list))
        if all_items:
            for key in ("id", "alert_id", "title", "action_type", "risk_level", "status", "command", "created_at"):
                record("R5", f"ai-pending 含字段 {key}", key in all_items[0])
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════
# 第 6 轮: HTTP 接口层测试
# ════════════════════════════════════════════════════════════════════
def round6_http_api():
    print("\n" + "=" * 70)
    print("第 6 轮: HTTP 接口层测试 (通过后端 REST API + Bearer token 鉴权)")
    print("=" * 70)
    import urllib.request
    import urllib.error

    BASE = "http://127.0.0.1:8000"

    # ── 先登录获取 Bearer token ──
    token = None
    try:
        login_body = json.dumps({"username": "admin", "password": "admin123"}).encode()
        login_req = urllib.request.Request(BASE + "/login", data=login_body,
                                           headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(login_req, timeout=15) as r:
            login_resp = json.loads(r.read().decode())
        token = login_resp.get("token")
        record("R6", "登录获取 token", token is not None,
               f"ok={login_resp.get('ok')} must_change={login_resp.get('must_change_password')}")
    except Exception as e:
        record("R6", "登录获取 token", False, f"{type(e).__name__}: {e}")
        return

    AUTH_HDR = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                "Content-Type": "application/json"}

    def _get(path, params=None):
        url = BASE + path
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        try:
            req = urllib.request.Request(url, headers=AUTH_HDR)
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode()
                return r.status, json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                return e.code, json.loads(body) if body.strip() else {}
            except Exception:
                return e.code, {"_raw": body[:200]}
        except Exception as e:
            return 0, {"error": str(e)}

    def _post(path, data=None):
        url = BASE + path
        body = json.dumps(data or {}).encode()
        try:
            req = urllib.request.Request(url, data=body, headers=AUTH_HDR)
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode()
                return r.status, json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw) if raw.strip() else {}
            except Exception:
                return e.code, {"_raw": raw[:200]}
        except Exception as e:
            return 0, {"error": str(e)}

    # 6a: GET /remediation/api/triggered-alerts
    status, data = _get("/remediation/api/triggered-alerts", {"limit": 5})
    record("R6", "GET triggered-alerts 200", status == 200, f"status={status}")
    record("R6", "triggered-alerts 含 alerts 字段", "alerts" in data, str(data.keys())[:60])
    record("R6", "alerts 是 list", isinstance(data.get("alerts"), list))

    # 6b: GET /remediation/api/ai-pending
    status, data = _get("/remediation/api/ai-pending", {"status": "all"})
    record("R6", "GET ai-pending 200", status == 200, f"status={status}")
    record("R6", "ai-pending 含 items 字段", "items" in data)
    record("R6", "ai-pending 含 total 字段", "total" in data)

    # 6c: GET /remediation/api/list
    status, data = _get("/remediation/api/list")
    record("R6", "GET list 200", status == 200)
    record("R6", "list 含 remediations", "remediations" in data)
    record("R6", "list 含 actions", "actions" in data)
    record("R6", "actions 含中文 label", any(
        v in ("重启服务", "清理磁盘", "扩缩容", "执行脚本", "执行命令", "发送通知")
        for v in data.get("actions", {}).values()))

    # 6d: GET /remediation/api/logs
    status, data = _get("/remediation/api/logs", {"page": 1, "per_page": 5})
    record("R6", "GET logs 200", status == 200)
    record("R6", "logs 含 items/total/total_pages",
           all(k in data for k in ("items", "total", "total_pages")),
           str(data.keys())[:60])

    # 6e: AI 分析接口（需先造告警；HTTP 层会调真实 LLM，可能失败，
    #     这里验证接口可达性 + 鉴权通过，不验证业务成功）
    db = DB_FACTORY()
    alert = None
    try:
        asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
        alert = _make_alert(db, asset.id, "net_latency", "warning",
                            "网络延迟高", actual=200.0, threshold=100.0)
        status, data = _post(f"/remediation/api/ai-analyze/{alert.id}")
        record("R6", "POST ai-analyze 鉴权通过且可达", status in (200, 500), f"status={status}")
        if status == 200:
            record("R6", "ai-analyze 返回 ok 字段", "ok" in data)
            if data.get("ok"):
                pa_id = data.get("pending_action_id")
                record("R6", "ai-analyze 返回 pending_action_id", pa_id is not None)
                if pa_id:
                    s2, d2 = _post(f"/remediation/api/ai-pending/{pa_id}/cancel")
                    record("R6", "POST cancel 200", s2 == 200, f"status={s2}")
            else:
                record("R6", "ai-analyze 失败（预期，无真实 LLM api_key）",
                       "error" in data, data.get("error", "")[:80])
        elif status == 500:
            record("R6", "ai-analyze 500（LLM 调用失败，接口本身可达）",
                   True, str(data)[:80])
    finally:
        if alert:
            _cleanup_alert(db, alert.id)
        db.close()

    # 6f: 不存在的告警 AI 分析（验证 404/错误处理）
    status, data = _post("/remediation/api/ai-analyze/999999")
    record("R6", "不存在告警 ai-analyze 返回 ok=False", status == 200 and data.get("ok") is False,
           f"status={status} ok={data.get('ok')}")

    # 6g: 不存在的动作 confirm
    status, data = _post("/remediation/api/ai-pending/999999/confirm")
    record("R6", "不存在动作 confirm 返回 ok=False", status == 200 and data.get("ok") is False,
           f"status={status}")

    # 6h: 不存在的动作 cancel
    status, data = _post("/remediation/api/ai-pending/999999/cancel")
    record("R6", "不存在动作 cancel 返回 ok=False", status == 200 and data.get("ok") is False,
           f"status={status}")


# ════════════════════════════════════════════════════════════════════
# 主函数
# ════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "#" * 70)
    print("#  AI 自愈功能端到端多轮场景测试")
    print(f"#  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  数据库: demo ({_PROJECT_ROOT}/db/aiops.db)")
    print("#" * 70)

    t0 = time.time()
    try:
        round1_success_full_chain()
        round2_cancel()
        round3_dangerous_command()
        round4_ssh_fail_soft()
        round5_boundary()
        round6_http_api()
    except Exception as e:
        import traceback
        print(f"\n❌ 测试异常中断: {e}")
        traceback.print_exc()

    # ── 汇总报告 ──
    elapsed = time.time() - t0
    total = len(_results)
    passed = sum(1 for r in _results if r[2] == "PASS")
    failed = total - passed

    print("\n" + "=" * 70)
    print("  测试汇总报告")
    print("=" * 70)
    print(f"  总用例: {total}")
    print(f"  通过:   {passed}")
    print(f"  失败:   {failed}")
    print(f"  通过率: {passed/total*100:.1f}%" if total else "N/A")
    print(f"  耗时:   {elapsed:.1f}s")
    print("-" * 70)

    # 分轮统计
    rounds = {}
    for rn, cn, st, d in _results:
        rounds.setdefault(rn, [0, 0])
        if st == "PASS":
            rounds[rn][0] += 1
        else:
            rounds[rn][1] += 1
    round_names = {
        "R1": "完整成功链路", "R2": "取消链路", "R3": "危险命令拦截",
        "R4": "SSH 失败 fail-soft", "R5": "边界测试", "R6": "HTTP 接口层",
    }
    for rn in ["R1", "R2", "R3", "R4", "R5", "R6"]:
        p, f = rounds.get(rn, [0, 0])
        name = round_names.get(rn, rn)
        print(f"  {rn} {name}: {p} pass / {f} fail")

    # 失败明细
    fails = [(rn, cn, d) for rn, cn, st, d in _results if st == "FAIL"]
    if fails:
        print("-" * 70)
        print("  ❌ 失败明细:")
        for rn, cn, d in fails:
            print(f"    [{rn}] {cn} — {d}")

    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
