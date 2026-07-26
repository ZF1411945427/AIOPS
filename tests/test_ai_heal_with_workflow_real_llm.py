"""
AI 自愈 + 工作流协同改造 - 真实 LLM 多轮场景验证

用真实 zm 模型(glm-5.2)调用 ai_self_heal_analyze，验证：
  R1: CPU 高告警 → AI 推荐工作流 #1
  R2: 磁盘满告警 → AI 推荐工作流 #2
  R3: 网络延迟告警（不匹配工作流）→ AI 走单步动作
  R4: 工作流类型 PendingAction confirm（mock SSH）→ 多步骤执行
  R5: 单步动作 PendingAction confirm（mock SSH）→ 单步执行
"""
import os
import sys
import json
import time
from datetime import datetime
from unittest.mock import patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from app.database import get_session_for, set_db_mode
from app.models import Alert, Asset, PendingAction, RemediationLog, RemediationWorkflow
from app.services import remediation_service

set_db_mode("demo")
DB_FACTORY = get_session_for("demo")

_results = []


def record(round_name, case_name, passed, detail=""):
    _results.append((round_name, case_name, "PASS" if passed else "FAIL", detail))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] [{round_name}] {case_name}" + (f" -- {detail}" if detail else ""))


def _make_alert(db, asset_id, metric, severity, message, actual, threshold):
    a = Alert(rule_id=None, asset_id=asset_id, metric_name=metric, severity=severity,
              message=message, actual_value=actual, threshold=threshold,
              status="triggered", created_at=datetime.now())
    db.add(a); db.commit(); db.refresh(a)
    return a


def _cleanup(db, alert_id):
    for pa in db.query(PendingAction).filter(PendingAction.alert_id == alert_id).all():
        db.delete(pa)
    db.query(RemediationLog).filter(RemediationLog.alert_id == alert_id).delete()
    db.query(Alert).filter(Alert.id == alert_id).delete()
    db.commit()


def _real_analyze(db, alert):
    """调真实 LLM 分析（不 mock），返回 result dict."""
    t0 = time.time()
    result = remediation_service.ai_self_heal_analyze(db, alert.id)
    elapsed = time.time() - t0
    return result, elapsed


def main():
    print("\n" + "#" * 70)
    print("#  AI 自愈 + 工作流协同 - 真实 LLM 多轮验证")
    print(f"#  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  LLM: zm (glm-5.2 @ http://39.106.16.32:9001/v1)")
    print("#" * 70)

    # 先看工作流清单
    db = DB_FACTORY()
    wfs = db.query(RemediationWorkflow).filter(RemediationWorkflow.enabled == True).all()
    print(f"\n已有工作流清单:")
    for w in wfs:
        try:
            steps = json.loads(w.steps) if isinstance(w.steps, str) else (w.steps or [])
            step_names = [s.get("action", str(s)) if isinstance(s, dict) else str(s) for s in steps]
        except Exception:
            step_names = []
        print(f"  #{w.id} {w.name} steps={step_names}")

    asset = db.query(Asset).filter(Asset.ip != None, Asset.ip != "").first()
    print(f"测试资产: {asset.name} ip={asset.ip}")
    db.close()

    # ════════════════════════════════════════════════════════════════════
    # R1: CPU 高告警 → 期望 AI 推荐工作流 #1（CPU 高自愈流程）
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("R1: CPU 高告警 → 期望 AI 推荐工作流 #1")
    print("=" * 70)
    db = DB_FACTORY()
    alert1 = None
    try:
        alert1 = _make_alert(db, asset.id, "cpu_usage", "critical",
                             "CPU 使用率 95% 超过阈值 80%", actual=95.0, threshold=80.0)
        result, elapsed = _real_analyze(db, alert1)
        record("R1", "真实 LLM 分析返回 ok", result.get("ok") is True,
               f"耗时 {elapsed:.1f}s err={result.get('error','')}")
        if result.get("ok"):
            analysis = result.get("analysis", {})
            record("R1", "AI 返回根因非空", bool(analysis.get("root_cause")),
                   analysis.get("root_cause", "")[:60])
            record("R1", "AI 返回 action_type", "action_type" in analysis,
                   analysis.get("action_type"))
            rec_wf_id = analysis.get("recommended_workflow_id")
            record("R1", "AI 推荐了 workflow_id", rec_wf_id is not None,
                   f"workflow_id={rec_wf_id}")
            record("R1", "AI 推荐 action_type=workflow",
                   analysis.get("action_type") == "workflow",
                   analysis.get("action_type"))
            if rec_wf_id:
                record("R1", f"推荐工作流 #{rec_wf_id} 名称非空",
                       bool(analysis.get("recommended_workflow_name")),
                       analysis.get("recommended_workflow_name", ""))
            pa_id = result.get("pending_action_id")
            pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
            record("R1", "PendingAction action_type=workflow",
                   pa.action_type == "workflow" if pa else False, pa.action_type if pa else "None")
            payload = json.loads(pa.action_payload) if pa else {}
            record("R1", "payload 含 workflow_id",
                   "workflow_id" in payload, str(payload))
    finally:
        if alert1:
            _cleanup(db, alert1.id)
        db.close()

    # ════════════════════════════════════════════════════════════════════
    # R2: 磁盘满告警 → 期望 AI 推荐工作流 #2（磁盘满自愈流程）
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("R2: 磁盘满告警 → 期望 AI 推荐工作流 #2")
    print("=" * 70)
    db = DB_FACTORY()
    alert2 = None
    try:
        alert2 = _make_alert(db, asset.id, "disk_usage", "critical",
                             "磁盘根分区使用率 96% 超过阈值 90%", actual=96.0, threshold=90.0)
        result, elapsed = _real_analyze(db, alert2)
        record("R2", "真实 LLM 分析返回 ok", result.get("ok") is True,
               f"耗时 {elapsed:.1f}s")
        if result.get("ok"):
            analysis = result.get("analysis", {})
            rec_wf_id = analysis.get("recommended_workflow_id")
            record("R2", "AI 推荐了 workflow_id", rec_wf_id is not None,
                   f"workflow_id={rec_wf_id}")
            record("R2", "AI 推荐 action_type=workflow",
                   analysis.get("action_type") == "workflow",
                   analysis.get("action_type"))
            pa_id = result.get("pending_action_id")
            pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
            record("R2", "PendingAction action_type=workflow",
                   pa.action_type == "workflow" if pa else False)
    finally:
        if alert2:
            _cleanup(db, alert2.id)
        db.close()

    # ════════════════════════════════════════════════════════════════════
    # R3: 网络延迟告警（不匹配工作流）→ 期望 AI 走单步动作
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("R3: 网络延迟告警（不匹配工作流）→ 期望 AI 走单步动作")
    print("=" * 70)
    db = DB_FACTORY()
    alert3 = None
    try:
        alert3 = _make_alert(db, asset.id, "network_latency", "warning",
                             "出口网络延迟 350ms 超过阈值 100ms", actual=350.0, threshold=100.0)
        result, elapsed = _real_analyze(db, alert3)
        record("R3", "真实 LLM 分析返回 ok", result.get("ok") is True,
               f"耗时 {elapsed:.1f}s")
        if result.get("ok"):
            analysis = result.get("analysis", {})
            rec_wf_id = analysis.get("recommended_workflow_id")
            record("R3", "AI 未推荐 workflow（或推荐 null）",
                   rec_wf_id is None, f"workflow_id={rec_wf_id}")
            record("R3", "AI action_type 非 workflow",
                   analysis.get("action_type") != "workflow",
                   analysis.get("action_type"))
            record("R3", "AI 给出单步命令", bool(analysis.get("command")),
                   (analysis.get("command", "") or "")[:60])
            pa_id = result.get("pending_action_id")
            pa = db.query(PendingAction).filter(PendingAction.id == pa_id).first()
            record("R3", "PendingAction action_type 非 workflow",
                   pa.action_type != "workflow" if pa else False, pa.action_type if pa else "")
    finally:
        if alert3:
            _cleanup(db, alert3.id)
        db.close()

    # ════════════════════════════════════════════════════════════════════
    # R4: 工作流类型 PendingAction confirm（mock SSH）→ 多步骤执行
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("R4: 工作流类型 confirm（mock SSH 多步骤执行）")
    print("=" * 70)
    db = DB_FACTORY()
    alert4 = None
    try:
        alert4 = _make_alert(db, asset.id, "cpu_usage", "high",
                             "CPU 持续 92%", actual=92.0, threshold=80.0)
        # 构造一个 workflow 类型的 PendingAction（手动构造，模拟 AI 推荐结果）
        wf = db.query(RemediationWorkflow).first()
        pa = PendingAction(
            alert_id=alert4.id,
            title=f"AI 自愈: 执行工作流 #{wf.id} {wf.name}"[:60],
            action_type="workflow",
            risk_level="low",
            reason="根因: CPU 高 | 影响: 服务变慢",
            status=PendingAction.STATUS_PENDING,
            action_payload=json.dumps({"workflow_id": wf.id}, ensure_ascii=False),
        )
        db.add(pa); db.commit(); db.refresh(pa)
        record("R4", "构造 workflow PendingAction", pa.action_type == "workflow")

        # mock SSH 每步成功
        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "step executed ok")):
            exec_result = remediation_service.confirm_ai_action(db, pa.id, username="test_admin")
        record("R4", "workflow confirm 返回 ok", exec_result.get("ok") is True)
        record("R4", "workflow confirm success", exec_result.get("success") is True,
               str(exec_result.get("output", ""))[:80])
        record("R4", "返回含 workflow_id", "workflow_id" in exec_result,
               f"wf_id={exec_result.get('workflow_id')}")

        db.refresh(pa)
        record("R4", "PendingAction 状态=executed", pa.status == "executed", pa.status)
        # 验证多步骤日志（steps 数量）
        steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
        logs = db.query(RemediationLog).filter(
            RemediationLog.alert_id == alert4.id,
            RemediationLog.remediation_id == wf.id,
        ).all()
        record("R4", f"多步骤日志数={len(steps)}（每步一条）",
               len(logs) == len(steps), f"实际日志数={len(logs)}")
        # 每步日志含 [Step N/M]
        for lg in logs:
            record("R4", f"日志#{lg.id} 含 [Step N/M] 标记",
                   "[Step" in (lg.output or ""), (lg.output or "")[:60])
    finally:
        if alert4:
            _cleanup(db, alert4.id)
        db.close()

    # ════════════════════════════════════════════════════════════════════
    # R5: 单步动作 confirm（mock SSH）→ 单步执行（回归测试）
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("R5: 单步动作 confirm（mock SSH，回归测试）")
    print("=" * 70)
    db = DB_FACTORY()
    alert5 = None
    try:
        alert5 = _make_alert(db, asset.id, "memory_usage", "warning",
                             "内存 88%", actual=88.0, threshold=80.0)
        pa = PendingAction(
            alert_id=alert5.id,
            title="AI 自愈: free -m",
            action_type="run_command",
            risk_level="low",
            reason="根因: 内存高 | 影响: OOM 风险",
            status=PendingAction.STATUS_PENDING,
            action_payload=json.dumps({"command": "free -m"}, ensure_ascii=False),
        )
        db.add(pa); db.commit(); db.refresh(pa)
        with patch.object(remediation_service, "_remote_exec",
                          return_value=(True, "              total   used   free\nMem:          16000   14000   2000")):
            exec_result = remediation_service.confirm_ai_action(db, pa.id, username="test_admin")
        record("R5", "单步 confirm 返回 ok", exec_result.get("ok") is True)
        record("R5", "单步 confirm success", exec_result.get("success") is True)
        db.refresh(pa)
        record("R5", "PendingAction 状态=executed", pa.status == "executed", pa.status)
        # 单步应只有 1 条日志
        logs = db.query(RemediationLog).filter(RemediationLog.alert_id == alert5.id).all()
        record("R5", "单步日志数=1", len(logs) == 1, f"实际={len(logs)}")
    finally:
        if alert5:
            _cleanup(db, alert5.id)
        db.close()

    # ════════════════════════════════════════════════════════════════════
    # 汇总
    # ════════════════════════════════════════════════════════════════════
    total = len(_results)
    passed = sum(1 for r in _results if r[2] == "PASS")
    failed = total - passed
    print("\n" + "=" * 70)
    print("  真实 LLM 验证汇总")
    print("=" * 70)
    print(f"  总用例: {total}  通过: {passed}  失败: {failed}  通过率: {passed/total*100:.1f}%")
    rounds = {}
    for rn, cn, st, d in _results:
        rounds.setdefault(rn, [0, 0])
        if st == "PASS": rounds[rn][0] += 1
        else: rounds[rn][1] += 1
    for rn in ["R1", "R2", "R3", "R4", "R5"]:
        p, f = rounds.get(rn, [0, 0])
        print(f"  {rn}: {p} pass / {f} fail")
    fails = [(rn, cn, d) for rn, cn, st, d in _results if st == "FAIL"]
    if fails:
        print("-" * 70)
        print("  FAIL 明细:")
        for rn, cn, d in fails:
            print(f"    [{rn}] {cn} -- {d}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
