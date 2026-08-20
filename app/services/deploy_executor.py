"""子模块(由 deploy_service 拆分生成, 勿手改函数体)"""

from app.services.deploy_state import *  # noqa: F401,F403


class _DeferredCallLLM:
    """延迟取门面 call_llm, 确保测试 monkeypatch deploy_service.call_llm 生效。"""
    __slots__ = ()
    def __call__(self, *args, **kwargs):
        from app.services import deploy_service as _ds
        return _ds.call_llm(*args, **kwargs)

call_llm = _DeferredCallLLM()


import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import DeployPlan, DeployStep, Asset, AIProvider, AgentConfig
from app.services.ssh_helper import connect_ssh
from app.logger import logger
from app.services.deploy_report import (_generate_fallback_report, _report_to_markdown,
                                        _report_to_html, _report_to_docx)

from app.services.deploy_common import (  # noqa: F401
    _now, _get_provider, _get_assets, _get_asset_ids, _extract_json, _safe_json,
    _resolve_command, _check_unresolved, _ssh_connect, _offline_blocked_reason,
    _proxy_env_prefix, _sync_env_mapping_from_sop, resolve_download_path,
    _is_valid_shell_command, _plan_to_dict, _step_to_dict, auto_download_artifact,
    _run_ssh, detect_artifact_source, _sanitize_dirname,
)
from app.services.deploy_ai_engine import (  # noqa: F401
    _ai_diagnose_failure, _ai_auto_resolve_env, _ai_auto_resolve_unresolved,
    _ai_build_execution_dag, _ai_pre_execution_risk, _ai_autonomous_decision,
    _ai_adaptive_rollback, _ai_decision_log, _ai_select_deployment_strategy,
    _ai_risk_scoring, _record_deployment_feature, _ai_pattern_matching,
    _ai_assess_state, _ai_health_gate, _ai_dynamic_scheduling,
    _ai_plan_step_autonomous, _ai_resource_check,
)


# ─── 原 L1237-1454 ───
def execute_plan(db: Session, plan_id: int, user_id: int = 0) -> dict:
    """HTTP 同步执行部署计划（使用 AI 引擎：DAG编排 + 自主决策 + 自适应回滚）。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    if plan.status == "draft":
        return {"error": "计划尚未规划，无法执行"}

    assets = _get_assets(db, plan)
    if not assets:
        return {"error": "计划未关联目标资产"}

    mapping = json.loads(plan.env_mapping or "{}")
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()
    if not steps:
        return {"error": "无部署步骤"}

    _sync_env_mapping_from_sop(db, plan)
    mapping = json.loads(plan.env_mapping or "{}")
    probe = _safe_json(plan.environment_probe_json)

    _provider = _get_provider(db)

    # ── AI 自动解决未解析的环境变量 ──
    try:
        mapping = _ai_auto_resolve_unresolved(_provider, plan, db, steps, mapping)
        if mapping:
            plan.env_mapping = json.dumps(mapping, ensure_ascii=False)
            db.commit()
    except Exception as e:
        logger.warning(f"AI 自动解决环境变量异常: {e}")

    # ── 前置资源检查 ──
    try:
        probe = _safe_json(plan.environment_probe_json)
        rc = _ai_resource_check(_provider, plan, steps, assets, probe)
        plan.preflight_json = json.dumps(rc, ensure_ascii=False)
        db.commit()
        if rc["recommendation"] == "block":
            return {"error": f"资源检查未通过: {rc['summary']}", "resource_check": rc}
    except Exception as rce:
        logger.warning(f"资源检查异常: {rce}")

    # 构建 DAG
    dag = None
    if _provider:
        dag = _ai_build_execution_dag(db, _provider, plan, steps)
    if not dag:
        dag = {"groups": [{"group_order": i + 1, "step_orders": [s.step_order], "parallel": False, "reason": "线性回退"} for i, s in enumerate(steps)],
               "reasoning": "AI 不可用，回退为线性顺序执行"}
    plan.dag_json = json.dumps(dag, ensure_ascii=False)
    plan.status = "running"
    db.commit()

    total_assets = len(assets)
    succeeded_assets = 0
    step_map = {s.step_order: s for s in steps}

    for asset in assets:
        try:
            client, host = _ssh_connect(asset)
        except Exception as e:
            logger.error(f"部署 {asset.name}({asset.ip}) SSH 连接失败: {e}")
            continue

        asset_map = dict(mapping)
        asset_map["TARGET_IP"] = asset.ip or ""
        asset_map["TARGET_HOSTNAME"] = asset.name or ""

        has_failed = False
        asset_executed_ok = 0
        # 默认工作目录 = 源码下载路径(APP_DIR)，保证 docker compose 等依赖 cwd 的命令在正确目录执行
        try:
            _cwd = resolve_download_path(plan)
        except Exception:
            _cwd = ""
        try:
            for group in dag["groups"]:
                if has_failed:
                    break
                for so in group["step_orders"]:
                    if has_failed:
                        break
                    step = step_map[so]

                    cmd = _resolve_command(step.command, asset_map)
                    verify_cmd = _resolve_command(step.verify_command, asset_map) if step.verify_command else ""

                    # 维护工作目录，给依赖 cwd 的命令补 cd 前缀(SSH 命令间不共享 cwd)
                    _cd_m = re.match(r'^cd\s+([^\s;&|]+)', cmd.strip())
                    if _cd_m:
                        _cwd = _cd_m.group(1).strip('"\'')
                    elif _cwd:
                        cmd = f"cd {_cwd} && {cmd}"
                    if verify_cmd and _cwd and not re.match(r'^cd\s', verify_cmd.strip()):
                        verify_cmd = f"cd {_cwd} && {verify_cmd}"

                    step.status = "running"
                    step.started_at = _now()
                    db.commit()

                    try:
                        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
                        exit_code = stdout.channel.recv_exit_status()
                        output = stdout.read().decode("utf-8", errors="replace").strip()
                        error = stderr.read().decode("utf-8", errors="replace").strip()
                        if error:
                            output = f"{output}\n{error}" if output else error
                        step.output = (step.output or "") + f"\n[{asset.name}]\n{output[:2000]}"
                        step.finished_at = _now()

                        if exit_code != 0:
                            step.status = "failed"
                            db.commit()
                            has_failed = True
                            # AI 自主决策
                            if _provider:
                                diag = _ai_diagnose_failure(db, _provider, step, output, {})
                                if diag.get("ok"):
                                    decision = _ai_autonomous_decision(_provider, step, output, diag, [])
                                    _ai_decision_log(plan, {"step": step.step_order, "type": "http_failure",
                                        "decision": decision, "root_cause": diag.get("root_cause", ""),
                                        "fix_commands": diag.get("fix_commands", []), "asset": asset.name})
                                    if decision in ("fix", "retry"):
                                        if decision == "fix":
                                            fix_cmds = diag.get("fix_commands", [])
                                            if fix_cmds:
                                                try:
                                                    p_client, _ = _ssh_connect(asset)
                                                    _run_fix_commands(p_client, fix_cmds, "", asset_map)
                                                    p_client.close()
                                                except Exception as _exc6:
                                                    logger.warning("[except:pass] Exception: %s", _exc6, exc_info=True)
                                        step.retry_count += 1
                                        step.diagnosis = diag.get("root_cause", "")
                                        step.fix_command = json.dumps(diag.get("fix_commands", []), ensure_ascii=False)
                                        step.status = "running"
                                        db.commit()
                                        has_failed = False
                                        continue
                                    elif decision == "skip":
                                        step.status = "skipped"
                                        step.diagnosis = diag.get("root_cause", "")
                                        db.commit()
                                        has_failed = False
                                        continue
                            _do_rollback(client, steps, step, asset_map)
                            continue

                        if verify_cmd:
                            if not _is_valid_shell_command(verify_cmd):
                                verify_cmd = ""
                            if verify_cmd:
                                try:
                                    v_stdin, v_stdout, v_stderr = client.exec_command(verify_cmd, timeout=15)
                                    v_exit = v_stdout.channel.recv_exit_status()
                                    if v_exit != 0:
                                        v_out = v_stdout.read().decode("utf-8", errors="replace").strip()
                                        step.output = (step.output + f"\n[校验失败] {v_out[:500]}").strip()
                                        step.status = "failed"
                                        db.commit()
                                        has_failed = True
                                        if _provider:
                                            diag = _ai_diagnose_failure(db, _provider, step, f"校验失败: {v_out}", {})
                                            if diag.get("ok"):
                                                decision = _ai_autonomous_decision(_provider, step, f"校验失败: {v_out}", diag, [])
                                                _ai_decision_log(plan, {"step": step.step_order, "type": "http_verify_failure",
                                                    "decision": decision, "asset": asset.name})
                                                if decision in ("fix", "retry"):
                                                    if decision == "fix":
                                                        _run_fix_commands(client, diag.get("fix_commands", []), "", asset_map)
                                                    step.retry_count += 1
                                                    step.status = "running"
                                                    db.commit()
                                                    has_failed = False
                                                    continue
                                                elif decision == "skip":
                                                    step.status = "skipped"
                                                    db.commit()
                                                    has_failed = False
                                                    continue
                                        _do_rollback(client, steps, step, asset_map)
                                        continue
                                except Exception as ve:
                                    step.output = (step.output + f"\n[校验异常] {ve}").strip()
                                    step.status = "failed"
                                    db.commit()
                                    has_failed = True
                                    _do_rollback(client, steps, step, asset_map)
                                    continue

                        step.status = "succeeded"
                        asset_executed_ok += 1
                        db.commit()

                    except Exception as e:
                        step.output = (step.output or "") + f"\n[{asset.name}] {str(e)[:2000]}"
                        step.status = "failed"
                        step.finished_at = _now()
                        db.commit()
                        has_failed = True
                        _do_rollback(client, steps, step, asset_map)
        finally:
            client.close()

        if not has_failed:
            succeeded_assets += 1

    if succeeded_assets == total_assets:
        plan.status = "succeeded"
    elif succeeded_assets > 0:
        plan.status = "failed"
    else:
        plan.status = "rolled_back"
    db.commit()
    _record_execution_history(db, plan, plan.status, {"total_assets": total_assets, "succeeded_assets": succeeded_assets})

    return {"ok": True, "status": plan.status, "total_assets": total_assets, "succeeded_assets": succeeded_assets}


# ─── 原 L1457-1475 ───
def stream_execute(db: Session, plan_id: int, user_id: int = 0, decision_queue=None):
    """执行锁包装：同一计划同一时刻只允许一个执行流，僵尸 running 状态可重跑。
    任何退出路径（含生成器被外部 close）都会释放锁。
    decision_queue: 可选，用户决策队列（WS 路由转发修复/重试/回滚/跳过指令）。"""
    if _EXEC_LOCK.get(plan_id):
        yield {"type": "error", "message": "该计划正在执行中，请勿重复点击"}
        return
    _EXEC_LOCK[plan_id] = True
    if decision_queue is not None:
        _DECISIONS[plan_id] = decision_queue
    logger.info(f"部署执行开始: plan_id={plan_id}")
    try:
        yield from _ai_stream_execute(db, plan_id, user_id, decision_queue)
    finally:
        _set_pending_decision_plan(db, plan_id, None)
        _release_exec(plan_id)
        _STOPPED.pop(plan_id, None)
        _DECISIONS.pop(plan_id, None)
        logger.info(f"部署执行结束，释放锁: plan_id={plan_id}")


# ─── 原 L2160-2183 ───
def _wait_for_risk_confirm(decision_queue, plan_id, step_order, command, risk_level, reason) -> str:
    """等待用户确认高危操作。返回 'confirm' 或 'reject'。
    如果 WS 断开（_STOPPED 标志），短超时轮询避免线程永久阻塞。"""
    if decision_queue is None:
        return "confirm"  # 无决策队列时默认放行
    import queue as _qm
    try:
        _decision_queue = decision_queue
        while True:
            try:
                decision = _decision_queue.get(timeout=5)
                if decision in ("confirm", "reject"):
                    return decision
                # 兼容旧决策消息
                if decision in ("fix", "retry", "skip", "rollback"):
                    return "confirm"
            except _qm.Empty:
                if _STOPPED.get(plan_id):
                    return "reject"
                continue
            except Exception:
                return "reject"
    except Exception:
        return "confirm"


# ─── 原 L2186-2195 ───
def _set_pending_decision_plan(db: Session, plan_id: int, decision: Optional[dict] = None):
    """持久化/清空当前计划待决策卡片(按 plan_id 独立, 互不干扰)。"""
    try:
        p = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
        if not p:
            return
        p.pending_decision_json = "null" if decision is None else json.dumps(decision, ensure_ascii=False)
        db.commit()
    except Exception:
        pass


# ─── 原 L2198-2212 ───
def submit_decision(db: Session, plan_id: int, action: str = "") -> dict:
    """用户决策提交(HTTP 接口): 将 action 投递到该计划当前活跃的决策队列,
    并清空该计划持久化的决策卡片。若该计划无进行中的部署, 返回错误提示。"""
    action = (action or "").strip().lower()
    if not action:
        return {"ok": False, "message": "决策不能为空"}
    q = _DECISIONS.get(plan_id)
    if q is None:
        return {"ok": False, "message": "该计划当前无进行中的部署，无需决策"}
    try:
        q.put_nowait(action)
    except Exception as e:
        return {"ok": False, "message": f"提交决策失败: {e}"}
    _set_pending_decision_plan(db, plan_id, None)
    return {"ok": True, "message": "决策已提交"}


# ─── 原 L2215-2824 ───
def _ai_stream_execute(db: Session, plan_id: int, user_id: int = 0, decision_queue=None):
    """AI 驱动流式执行部署计划（10 分执行引擎）。

    能力① AI 动态编排(DAG) → 能力③ AI 执行前预判 → 按 DAG 执行 →
    失败时能力② AI 自主决策 → 能力⑤ AI 自适应回滚
    能力④ AI 并行调度：DAG parallel=true 组内步骤并行执行（多线程）

    产出事件 dict（兼容旧事件 + 新增）：
      {"type": "status", "status": "running"}
      {"type": "dag_plan", "groups": [...], "reasoning": "..."}   # 新增：DAG 执行计划
      {"type": "asset_start", "asset": 主机名, "ip": ...}
      {"type": "parallel_group", "group": N, "steps": [1,2], "parallel": bool}  # 新增
      {"type": "step_start", "step": 序号, "description": ..., "risk": ..., "ai_risk": "..."}  # 增强
      {"type": "ai_precheck", "step": 序号, "risk": ..., "reason": ..., "precheck": ...}  # 新增
      {"type": "cmd", "command": "..."}
      {"type": "output", "line": "..."}
      {"type": "step_end", "step": 序号, "status": 状态}
      {"type": "ai_decision", "step": 序号, "decision": "fix/retry/skip/rollback", "reason": "..."}  # 新增
      {"type": "asset_end", "asset": 主机名, "status": 状态}
      {"type": "complete", "status": 计划终态, "total_assets": N, "succeeded_assets": N}
    """
    import time as _time
    import concurrent.futures as _cf
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        yield {"type": "error", "message": "计划不存在"}
        return
    if plan.status == "draft":
        yield {"type": "error", "message": "计划尚未规划，无法执行"}
        return
    assets = _get_assets(db, plan)
    if not assets:
        yield {"type": "error", "message": "计划未关联目标资产"}
        return

    mapping = json.loads(plan.env_mapping or "{}")
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()
    if not steps:
        yield {"type": "error", "message": "无部署步骤"}
        return

    _provider = _get_provider(db)
    _health_gates = []

    _sync_env_mapping_from_sop(db, plan)
    mapping = json.loads(plan.env_mapping or "{}")
    probe = _safe_json(plan.environment_probe_json)

    # ── AI 自动解决未解析的环境变量 ──
    try:
        mapping = _ai_auto_resolve_unresolved(_provider, plan, db, steps, mapping)
        if mapping:
            plan.env_mapping = json.dumps(mapping, ensure_ascii=False)
            db.commit()
    except Exception as e:
        logger.warning(f"AI 自动解决环境变量异常: {e}")

    plan.status = "running"
    for _s in steps:
        _s.status = "pending"
        _s.output = ""
        _s.started_at = None
        _s.finished_at = None
    db.commit()
    yield {"type": "status", "status": "running"}

    # ── 前置资源检查 ──
    try:
        rc = _ai_resource_check(_provider, plan, steps, assets, probe)
        plan.preflight_json = json.dumps(rc, ensure_ascii=False)
        db.commit()
        yield {"type": "resource_check", "passed": rc["passed"], "checks": rc["checks"],
               "recommendation": rc["recommendation"], "summary": rc["summary"]}
        if rc["recommendation"] == "block":
            yield {"type": "error", "message": f"❌ 资源检查未通过，部署终止: {rc['summary']}"}
            plan.status = "planned"
            db.commit()
            return
        if rc["recommendation"] == "warn":
            yield {"type": "output", "line": f"\r\n\x1b[33m⚠️ 资源检查有风险，但 AI 建议继续: {rc['summary']}\x1b[0m"}
    except Exception as rce:
        logger.warning(f"资源检查异常: {rce}")

    # ── L4: AI 选择部署策略 ──
    strategy = "auto"
    try:
        history_now = _safe_json(plan.execution_history_json)
        if not isinstance(history_now, list):
            history_now = []
        if _provider:
            strategy = _ai_select_deployment_strategy(_provider, plan, steps, probe, assets)
            risk_score = _ai_risk_scoring(_provider, plan, steps, probe, assets, history_now)
            plan.strategy = strategy
            plan.risk_score = risk_score
            db.commit()
            yield {"type": "strategy_selected", "strategy": strategy, "risk_score": risk_score,
                   "reason": f"AI 评估风险 {risk_score}/100，选择 {strategy} 策略"}
            logger.info(f"部署策略选定 plan_id={plan_id} strategy={strategy} risk={risk_score}")
    except Exception as e:
        logger.warning(f"AI 策略选择异常: {e}")

    # ── L5: 历史模式匹配预警 ──
    try:
        if _provider and history_now:
            pending_features = _record_deployment_feature(plan, steps, assets, probe, "pending", [], 0)
            pattern = _ai_pattern_matching(_provider, pending_features, history_now)
            if pattern:
                yield {"type": "risk_warning", "pattern": pattern.get("pattern", ""),
                       "risk": pattern.get("risk", ""), "suggestion": pattern.get("suggestion", "")}
    except Exception as e:
        logger.warning(f"AI 模式匹配异常: {e}")

    # ── 能力①：AI 构建 DAG 执行计划 ──
    dag = None
    if _provider:
        dag = _ai_build_execution_dag(db, _provider, plan, steps)
    if not dag:
        dag = {"groups": [{"group_order": i + 1, "step_orders": [s.step_order], "parallel": False, "reason": "线性回退"} for i, s in enumerate(steps)],
               "reasoning": "AI 不可用，回退为线性顺序执行"}
    plan.dag_json = json.dumps(dag, ensure_ascii=False)
    db.commit()
    yield {"type": "dag_plan", "groups": dag["groups"], "reasoning": dag.get("reasoning", "")}

    total_assets = len(assets)
    succeeded_assets = 0
    step_map = {s.step_order: s for s in steps}

    for asset in assets:
        try:
            client, host = _ssh_connect(asset)
            _RUNNING_CLIENTS[plan_id] = client
        except Exception as e:
            yield {"type": "error", "line": f"❌ {asset.name}({asset.ip}) SSH 连接失败: {e}"}
            continue

        asset_map = dict(mapping)
        asset_map["TARGET_IP"] = asset.ip or ""
        asset_map["TARGET_HOSTNAME"] = asset.name or ""

        yield {"type": "asset_start", "asset": asset.name, "ip": asset.ip}
        asset_failed = False
        # 默认工作目录 = 源码下载路径(APP_DIR)，保证后续依赖 cwd 的命令(如 docker compose)即使 AI 命令不带 cd 也能在正确目录执行
        try:
            _cwd = resolve_download_path(plan)
        except Exception:
            _cwd = ""
        try:
            for group in dag["groups"]:
                if asset_failed:
                    break
                step_orders = group["step_orders"]
                parallel = group.get("parallel", False)
                yield {"type": "parallel_group", "group": group["group_order"], "steps": step_orders, "parallel": parallel, "reason": group.get("reason", "")}

                if parallel and len(step_orders) > 1:
                    # ── 能力④：AI 并行调度 ──
                    def _exec_parallel_step(so):
                        p_step = step_map[so]
                        p_cmd = _resolve_command(p_step.command, asset_map)
                        p_verify = _resolve_command(p_step.verify_command, asset_map) if p_step.verify_command else ""
                        p_cwd = _cwd
                        p_cd_m = re.match(r'^cd\s+([^\s;&|]+)', p_cmd.strip())
                        if p_cd_m:
                            p_cwd = p_cd_m.group(1).strip('"\'')
                        if not p_cd_m and p_cwd:
                            p_cmd = f"cd {p_cwd} && {p_cmd}"
                        _ppx = _proxy_env_prefix(plan)
                        if _ppx:
                            p_cmd = f"{_ppx} && {p_cmd}"
                        try:
                            p_client, _ = _ssh_connect(asset)
                            _, p_stdout, p_stderr = p_client.exec_command(p_cmd, timeout=600)
                            p_rc = p_stdout.channel.recv_exit_status()
                            p_out = p_stdout.read().decode("utf-8", errors="replace").strip()
                            p_err = p_stderr.read().decode("utf-8", errors="replace").strip()
                            p_client.close()
                            if p_err:
                                p_out = f"{p_out}\n{p_err}" if p_out else p_err
                            return {"step_order": so, "exit_code": p_rc, "output": p_out}
                        except Exception as pe:
                            return {"step_order": so, "exit_code": -1, "output": str(pe)}

                    with _cf.ThreadPoolExecutor(max_workers=len(step_orders)) as pool:
                        para_results = list(pool.map(_exec_parallel_step, step_orders))
                    for pr in para_results:
                        ps = step_map[pr["step_order"]]
                        ps.output = (ps.output or "") + f"\n[{asset.name}]\n{pr['output'][:2000]}"
                        ps.started_at = _now()
                        ps.finished_at = _now()
                        if pr["exit_code"] == 0:
                            ps.status = "succeeded"
                            yield {"type": "step_start", "step": ps.step_order, "description": ps.description, "risk": ps.risk_level}
                            yield {"type": "output", "line": f"并行步骤 {ps.step_order}: {ps.description} ✔"}
                            yield {"type": "step_end", "step": ps.step_order, "status": "succeeded"}
                        else:
                            ps.status = "failed"
                            asset_failed = True
                            yield {"type": "step_start", "step": ps.step_order, "description": ps.description, "risk": ps.risk_level}
                            yield {"type": "output", "line": f"并行步骤 {ps.step_order}: {ps.description} ✘ (exit={pr['exit_code']})"}
                            yield {"type": "step_end", "step": ps.step_order, "status": "failed", "exit_code": pr["exit_code"]}
                            if _provider:
                                diag = _ai_diagnose_failure(db, _provider, ps, pr["output"],
                                    {"os": "", "docker": "", "asset": asset.name, "ip": asset.ip})
                                if diag.get("ok"):
                                    decision = _ai_autonomous_decision(_provider, ps, pr["output"], diag, [])
                                    _ai_decision_log(plan, {"step": ps.step_order, "type": "parallel_failure", "decision": decision,
                                        "root_cause": diag.get("root_cause", ""), "asset": asset.name})
                                    if decision == "fix":
                                        fix_cmds = diag.get("fix_commands", [])
                                        if fix_cmds:
                                            try:
                                                p_client, _ = _ssh_connect(asset)
                                                _run_fix_commands(p_client, fix_cmds, _cwd, asset_map)
                                                p_client.close()
                                            except Exception as _exc16:
                                                logger.warning("[except:pass] Exception: %s", _exc16, exc_info=True)
                                    yield {"type": "ai_decision", "step": ps.step_order, "decision": decision,
                                        "reason": diag.get("root_cause", "")[:200]}
                    db.commit()
                    if asset_failed:
                        break
                else:
                    # ── 串行执行组内步骤 ──
                    prev_step_output = ""
                    prev_step_status = ""
                    for so in step_orders:
                        if asset_failed:
                            break
                        step = step_map[so]

                        # 记录上一步的输出给 AI 规划用
                        if so > 1 and (so - 1) in step_map and step_map[so - 1].output:
                            prev_step_output = step_map[so - 1].output[-300:]
                            prev_step_status = step_map[so - 1].status

                        cmd = _resolve_command(step.command, asset_map)
                        verify_cmd = _resolve_command(step.verify_command, asset_map) if step.verify_command else ""

                        _cd_m = re.match(r'^cd\s+([^\s;&|]+)', cmd.strip())
                        if _cd_m:
                            _cwd = _cd_m.group(1).strip('"\'')
                        if not _cd_m and _cwd:
                            cmd = f"cd {_cwd} && {cmd}"

                        # ── 能力③：AI 执行前预判 ──
                        ai_risk_info = ""
                        if _provider:
                            precheck = _ai_pre_execution_risk(_provider, step, plan)
                            if precheck:
                                precheck_text = json.dumps(precheck, ensure_ascii=False)
                                step.precheck_result = precheck_text
                                db.commit()
                                ai_risk_info = precheck.get("risk", "")
                                yield {"type": "ai_precheck", "step": step.step_order, "risk": precheck.get("risk", ""),
                                    "reason": precheck.get("reason", ""), "precheck": precheck.get("precheck", ""),
                                    "guard_note": precheck.get("guard_note", "")}
                                if precheck.get("suggest_modify"):
                                    yield {"type": "output", "line": f"🤖 AI 建议安全替换: {precheck['suggest_modify']}"}
                                if precheck.get("precheck") and precheck.get("precheck_expect"):
                                    try:
                                        p_stdin, p_stdout, p_stderr = client.exec_command(precheck["precheck"], timeout=10)
                                        p_exit = p_stdout.channel.recv_exit_status()
                                        p_out = p_stdout.read().decode("utf-8", errors="replace").strip()
                                        yield {"type": "output", "line": f"🔍 前置检查: {precheck['precheck']} → exit={p_exit} {p_out[:100]}"}
                                    except Exception as pce:
                                        yield {"type": "output", "line": f"⚠ 前置检查异常: {pce}"}

                        # ── AI 自主规划：理解意图 → 生成执行计划 ──
                        ai_intent = ""
                        ai_plan = None
                        if _provider:
                            env_ctx = {"prev_output": prev_step_output, "prev_status": prev_step_status, "cwd": _cwd}
                            ai_plan = _ai_plan_step_autonomous(_provider, step, plan, probe, env_ctx)
                            if ai_plan.get("commands"):
                                ai_cmds = ai_plan["commands"]
                                ai_intent = ai_plan.get("intent", "")
                                ai_verify = ai_plan.get("verify", "")
                                yield {"type": "ai_plan", "step": step.step_order, "intent": ai_intent,
                                    "commands": ai_cmds, "adjustments": ai_plan.get("adjustments", []),
                                    "risk": ai_plan.get("risk", step.risk_level)}
                                # 使用 AI 规划的命令（需再次解析 ${ENV_xxx} 占位符）
                                ai_cmds_resolved = [_resolve_command(c, asset_map) for c in ai_cmds]
                                cmd = ai_cmds_resolved[0] if len(ai_cmds_resolved) == 1 else " && ".join(ai_cmds_resolved)
                                if ai_verify:
                                    verify_cmd = _resolve_command(ai_verify, asset_map)
                                _cd_m = re.match(r'^cd\s+([^\s;&|]+)', cmd.strip())
                                if _cd_m:
                                    _cwd = _cd_m.group(1).strip('"\'')
                                if not _cd_m and _cwd:
                                    cmd = f"cd {_cwd} && {cmd}"

                        # ── 风险门控：高危操作需用户确认 ──
                        _risk_level = step.risk_level
                        if ai_plan and ai_plan.get("risk"):
                            _risk_level = ai_plan["risk"]
                        if _risk_level == "high" and decision_queue is not None:
                            _set_pending_decision_plan(db, plan_id, {
                                "step": step.step_order,
                                "description": step.description,
                                "command": cmd[:200],
                                "risk": "high",
                                "reason": "高危操作，请确认是否继续",
                            })
                            yield {"type": "risk_confirm", "step": step.step_order,
                                "command": cmd[:200], "description": step.description,
                                "risk": "high", "reason": "高危操作，请确认是否继续"}
                            decision = _wait_for_risk_confirm(decision_queue, plan_id,
                                step.step_order, cmd, "high", "高危操作")
                            _set_pending_decision_plan(db, plan_id, None)
                            yield {"type": "output", "line": f"\r\n\x1b[33m🔐 高危操作确认: {'✅ 已确认' if decision == 'confirm' else '⛔ 已拒绝'}\x1b[0m"}
                            if decision != "confirm":
                                step.status = "skipped"
                                db.commit()
                                yield {"type": "step_end", "step": step.step_order, "status": "skipped"}
                                continue

                        step.status = "running"
                        step.started_at = _now()
                        db.commit()

                        yield {"type": "step_start", "step": step.step_order, "description": step.description,
                            "risk": step.risk_level, "ai_risk": ai_risk_info, "ai_intent": ai_intent}
                        yield {"type": "cmd", "command": cmd}

                        # ▼ 离线二次强制校验: 勾选 use_offline 后拦截公网拉取/公网源命令
                        _offline_block = _offline_blocked_reason(plan, cmd)
                        if _offline_block:
                            step.status = "failed"
                            step.output = (step.output or "") + f"\n⛔ {_offline_block}"
                            db.commit()
                            yield {"type": "output", "line": f"\r\n\x1b[31m⛔ {_offline_block}\x1b[0m"}
                            yield {"type": "step_end", "step": step.step_order, "status": "failed", "note": _offline_block}
                            failed = True
                            continue

                        # ▼ 代理环境注入(可选): 在真实命令前导出 HTTP_PROXY/HTTPS_PROXY/NO_PROXY
                        _px = _proxy_env_prefix(plan)
                        _exec_cmd = (f"{_px} && {cmd}") if _px else cmd

                        try:
                            stdin, stdout, stderr = client.exec_command(_exec_cmd, timeout=60)
                            _ch = stdout.channel
                            _ch.settimeout(0.05)
                            collected = []
                            err_collected = []
                            _step_deadline = _time.time() + _STEP_TIMEOUT
                            while not _ch.exit_status_ready():
                                if _time.time() > _step_deadline:
                                    try:
                                        _ch.close()
                                    except Exception as _exc17:
                                        logger.warning("[except:pass] Exception: %s", _exc17, exc_info=True)
                                    raise TimeoutError(f"步骤超时({_STEP_TIMEOUT}s)，已终止该命令")
                                try:
                                    _line = stdout.readline()
                                    if _line:
                                        _line = _line.rstrip("\r\n")
                                        collected.append(_line)
                                        yield {"type": "output", "line": _line}
                                except Exception:
                                    _line = ""
                                try:
                                    _el = stderr.readline()
                                    if _el:
                                        _el = _el.rstrip("\r\n")
                                        if _el:
                                            err_collected.append(_el)
                                            yield {"type": "output", "line": _el}
                                except Exception:
                                    _el = ""
                                if not _line and not _el:
                                    _time.sleep(0.1)
                            _ch.settimeout(0.3)
                            try:
                                while True:
                                    _d = stdout.read(8192).decode("utf-8", errors="replace")
                                    if not _d:
                                        break
                                    for _l in _d.split("\n"):
                                        _l = _l.rstrip("\r")
                                        if _l:
                                            collected.append(_l)
                                            yield {"type": "output", "line": _l}
                            except Exception as _exc18:
                                logger.warning("[except:pass] Exception: %s", _exc18, exc_info=True)
                            try:
                                while True:
                                    _ed = stderr.read(8192).decode("utf-8", errors="replace")
                                    if not _ed:
                                        break
                                    for _el in _ed.split("\n"):
                                        _el = _el.rstrip("\r")
                                        if _el:
                                            err_collected.append(_el)
                                            yield {"type": "output", "line": _el}
                            except Exception as _exc19:
                                logger.warning("[except:pass] Exception: %s", _exc19, exc_info=True)
                            _rc = _ch.recv_exit_status()
                            _err = "\n".join(err_collected)
                            output = "\n".join(collected)
                            if _err:
                                output = f"{output}\n{_err}" if output else _err
                            step.output = (step.output or "") + f"\n[{asset.name}]\n{output[:2000]}"
                            step.finished_at = _now()

                            # ── 命令失败处理 → 能力②：AI 自主决策 ──
                            if _rc != 0:
                                step.status = "failed"
                                db.commit()
                                asset_failed = True
                                yield {"type": "step_end", "step": step.step_order, "status": "failed", "exit_code": _rc}
                                if _provider:
                                    diag = _ai_diagnose_failure(db, _provider, step, output, {"os": "", "docker": "",
                                        "asset": asset.name, "ip": asset.ip})
                                    if diag.get("ok"):
                                        decision = _ai_autonomous_decision(_provider, step, output, diag, [])
                                        _ai_decision_log(plan, {"step": step.step_order, "type": "command_failure",
                                            "decision": decision, "root_cause": diag.get("root_cause", ""),
                                            "fix_commands": diag.get("fix_commands", []), "asset": asset.name})
                                        yield {"type": "ai_decision", "step": step.step_order, "decision": decision,
                                            "reason": diag.get("root_cause", "")[:300],
                                            "fix_commands": diag.get("fix_commands", [])}
                                        if decision in ("fix", "retry"):
                                            if decision == "fix":
                                                _run_fix_commands(client, diag.get("fix_commands", []), _cwd, asset_map)
                                            step.retry_count += 1
                                            step.diagnosis = diag.get("root_cause", "")
                                            step.fix_command = json.dumps(diag.get("fix_commands", []), ensure_ascii=False)
                                            step.status = "running"
                                            db.commit()
                                            asset_failed = False
                                            continue
                                        elif decision == "skip":
                                            step.status = "skipped"
                                            step.diagnosis = diag.get("root_cause", "")
                                            db.commit()
                                            asset_failed = False
                                            continue
                                # fallback: rollback
                                yield {"type": "output", "line": f"⛔ 步骤 {step.step_order} 执行失败，AI 已决策回滚..."}
                                yield from _ai_stream_rollback(client, steps, step, asset_map, _cwd, _provider, plan)
                                continue

                            # ── 校验 ──
                            if verify_cmd:
                                if not _is_valid_shell_command(verify_cmd):
                                    yield {"type": "output", "line": f"ℹ 校验命令非 shell 命令，跳过: {verify_cmd[:60]}"}
                                    verify_cmd = ""
                                if verify_cmd and _cwd and not re.match(r'^cd\s', verify_cmd.strip()):
                                    verify_cmd = f"cd {_cwd} && {verify_cmd}"
                                yield {"type": "output", "line": f"✔ 校验: {verify_cmd}"}
                                try:
                                    v_stdin, v_stdout, v_stderr = client.exec_command(verify_cmd, timeout=15)
                                    v_exit = v_stdout.channel.recv_exit_status()
                                    if v_exit != 0:
                                        v_out = v_stdout.read().decode("utf-8", errors="replace").strip()
                                        step.output = (step.output + f"\n[校验失败] {v_out[:500]}").strip()
                                        step.status = "failed"
                                        db.commit()
                                        asset_failed = True
                                        yield {"type": "step_end", "step": step.step_order, "status": "failed", "exit_code": v_exit}
                                        if _provider:
                                            diag = _ai_diagnose_failure(db, _provider, step, f"校验失败: {v_out}", {})
                                            if diag.get("ok"):
                                                decision = _ai_autonomous_decision(_provider, step, f"校验失败: {v_out}", diag, [])
                                                _ai_decision_log(plan, {"step": step.step_order, "type": "verify_failure",
                                                    "decision": decision, "root_cause": diag.get("root_cause", ""),
                                                    "asset": asset.name})
                                                yield {"type": "ai_decision", "step": step.step_order, "decision": decision,
                                                    "reason": diag.get("root_cause", "")[:300]}
                                                if decision in ("fix", "retry"):
                                                    if decision == "fix":
                                                        _run_fix_commands(client, diag.get("fix_commands", []), _cwd, asset_map)
                                                    step.retry_count += 1
                                                    step.diagnosis = diag.get("root_cause", "")
                                                    step.status = "running"
                                                    db.commit()
                                                    asset_failed = False
                                                    continue
                                                elif decision == "skip":
                                                    step.status = "skipped"
                                                    db.commit()
                                                    asset_failed = False
                                                    continue
                                        yield {"type": "output", "line": "⛔ 校验失败，AI 已决策回滚..."}
                                        yield from _ai_stream_rollback(client, steps, step, asset_map, _cwd, _provider, plan)
                                        continue
                                except Exception as ve:
                                    step.output = (step.output + f"\n[校验异常] {ve}").strip()
                                    step.status = "failed"
                                    db.commit()
                                    asset_failed = True
                                    yield {"type": "step_end", "step": step.step_order, "status": "failed"}
                                    yield {"type": "output", "line": f"⛔ 校验异常: {ve}"}
                                    if _provider:
                                        diag = _ai_diagnose_failure(db, _provider, step, str(ve), {})
                                        if diag.get("ok"):
                                            decision = _ai_autonomous_decision(_provider, step, str(ve), diag, [])
                                            _ai_decision_log(plan, {"step": step.step_order, "type": "verify_exception",
                                                "decision": decision, "asset": asset.name})
                                            yield {"type": "ai_decision", "step": step.step_order, "decision": decision,
                                                "reason": diag.get("root_cause", "")[:200]}
                                            if decision in ("fix", "retry"):
                                                if decision == "fix":
                                                    _run_fix_commands(client, diag.get("fix_commands", []), _cwd, asset_map)
                                                step.retry_count += 1
                                                step.status = "running"
                                                db.commit()
                                                asset_failed = False
                                                continue
                                            elif decision == "skip":
                                                step.status = "skipped"
                                                db.commit()
                                                asset_failed = False
                                                continue
                                    yield from _ai_stream_rollback(client, steps, step, asset_map, _cwd, _provider, plan)
                                    continue

                            step.status = "succeeded"
                            db.commit()
                            yield {"type": "step_end", "step": step.step_order, "status": "succeeded"}

                            # ── L4: 健康门控 + 状态评估 ──
                            if _provider:
                                try:
                                    hg = _ai_health_gate(_provider, client, asset_map, step, strategy)
                                    _health_gates.append({"step": step.step_order, "checks": hg.get("checks", []),
                                        "passed": hg.get("passed", True), "ts": _now().isoformat()})
                                    yield {"type": "health_gate", "step": step.step_order,
                                        "passed": hg.get("passed", True), "checks": hg.get("checks", []),
                                        "recommendation": hg.get("recommendation", "continue")}
                                    if not hg.get("passed", True):
                                        if hg.get("recommendation") == "rollback":
                                            yield {"type": "output", "line": "\r\n\x1b[31m🔴 健康门控未通过，AI 决策回滚...\x1b[0m"}
                                            yield from _ai_stream_rollback(client, steps, step, asset_map, _cwd, _provider, plan)
                                            break
                                except Exception as hge:
                                    logger.warning(f"健康门控异常: {hge}")

                        except Exception as e:
                            step.output = (step.output or "") + f"\n[{asset.name}] {str(e)[:2000]}"
                            step.status = "failed"
                            step.finished_at = _now()
                            db.commit()
                            asset_failed = True
                            yield {"type": "step_end", "step": step.step_order, "status": "failed"}
                            yield {"type": "output", "line": f"⛔ 步骤异常: {e}"}
                            if _provider:
                                diag = _ai_diagnose_failure(db, _provider, step, str(e), {})
                                if diag.get("ok"):
                                    decision = _ai_autonomous_decision(_provider, step, str(e), diag, [])
                                    _ai_decision_log(plan, {"step": step.step_order, "type": "step_exception",
                                        "decision": decision, "asset": asset.name})
                                    yield {"type": "ai_decision", "step": step.step_order, "decision": decision,
                                        "reason": diag.get("root_cause", "")[:200]}
                                    if decision in ("fix", "retry"):
                                        if decision == "fix":
                                            _run_fix_commands(client, diag.get("fix_commands", []), _cwd, asset_map)
                                        step.retry_count += 1
                                        step.status = "running"
                                        db.commit()
                                        asset_failed = False
                                        continue
                                    elif decision == "skip":
                                        step.status = "skipped"
                                        db.commit()
                                        asset_failed = False
                                        continue
                            yield from _ai_stream_rollback(client, steps, step, asset_map, _cwd, _provider, plan)
        finally:
            _RUNNING_CLIENTS.pop(plan_id, None)
            client.close()

        # 兜底：即使 asset_failed 因 fix/retry 被重置，只要该计划存在最终态为 failed 的步骤，仍判为失败
        # （防止命令返回码为 0/被修复命令掩盖导致步骤 real 失败却误报 asset 成功）
        _asset_steps = [s for s in steps if s.plan_id == plan_id]
        _final_failed = any(s.status == "failed" for s in _asset_steps)
        if _final_failed:
            asset_failed = True

        if not asset_failed:
            succeeded_assets += 1
        yield {"type": "asset_end", "asset": asset.name, "status": "failed" if asset_failed else "succeeded"}

    if succeeded_assets == total_assets:
        plan.status = "succeeded"
    elif succeeded_assets > 0:
        plan.status = "failed"
    else:
        plan.status = "rolled_back"
    if _STOPPED.pop(plan_id, None):
        pass
    else:
        # ── L5: 记录部署特征(供学习) ──
        try:
            step_results = []
            for s in steps:
                step_results.append({"status": s.status, "retry_count": s.retry_count, "order": s.step_order})
            _total_dur = 0
            for s in steps:
                if s.started_at and s.finished_at:
                    _total_dur += (s.finished_at - s.started_at).total_seconds()
            features = _record_deployment_feature(plan, steps, assets, probe, plan.status, step_results, _total_dur)
            _ai_decision_log(plan, {"type": "deploy_complete", "status": plan.status, "features": features})
            plan.health_gate_json = json.dumps(_health_gates[-50:], ensure_ascii=False)
        except Exception as fe:
            logger.warning(f"部署特征记录异常: {fe}")
        db.commit()
        _record_execution_history(db, plan, plan.status, {"total_assets": total_assets, "succeeded_assets": succeeded_assets})
        yield {"type": "complete", "status": plan.status, "total_assets": total_assets, "succeeded_assets": succeeded_assets}


# ─── 原 L2827-2850 ───
def _ai_stream_rollback(client, steps: list, failed_step, mapping: dict, app_dir: str, provider, plan: DeployPlan):
    """能力⑤：AI 自适应回滚 — 只回滚有状态的步骤，跳过无状态步骤。"""
    step_map = {s.step_order: s for s in steps}
    if provider:
        rollback_orders = _ai_adaptive_rollback(provider, steps, plan)
        if rollback_orders:
            yield {"type": "output", "line": f"\r\n\x1b[33m🤖 AI 自适应回滚: 跳过 {len(steps) - len(rollback_orders)} 个无状态步骤\x1b[0m"}
            for ro in rollback_orders:
                s = step_map[ro]
                if s.status != "succeeded":
                    continue
                rc = _resolve_command(s.rollback_command, mapping) if s.rollback_command else ""
                if rc:
                    try:
                        _s, _o, _e = client.exec_command(rc, timeout=30)
                        _rc = _o.channel.recv_exit_status()
                        yield {"type": "output", "line": f"  ↩ 回滚步骤 {ro}: {s.description} (exit={_rc})"}
                    except Exception as ex:
                        yield {"type": "output", "line": f"  ⚠ 回滚步骤 {ro} 异常: {ex}"}
                s.status = "rolled_back"
            return
    # fallback: 全量逆序回滚
    yield {"type": "output", "line": "\r\n\x1b[33m⏪ 全量回滚...\x1b[0m"}
    yield from _stream_rollback(client, steps, failed_step, mapping, app_dir)


# ─── 原 L2853-2950 ───
def stream_rollback_cleanup(db: Session, plan_id: int):
    """手动一键清理回滚：部署完成后（succeeded/failed/rolled_back），
    逆序回滚所有已执行的步骤，并重置计划状态为 planned 以便重新部署。
    产出流式事件供 WS 实时显示。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        yield {"type": "error", "message": "计划不存在"}
        return
    if plan.status == "running":
        yield {"type": "error", "message": "部署执行中，无法清理"}
        return
    if plan.status == "draft":
        yield {"type": "error", "message": "计划尚未规划，无需清理"}
        return
    assets = _get_assets(db, plan)
    if not assets:
        yield {"type": "error", "message": "计划未关联目标资产"}
        return
    mapping = json.loads(plan.env_mapping or "{}")
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()

    yield {"type": "status", "status": "rolling_back", "message": "开始一键清理回滚..."}
    _log_lines = []  # 本资产生成的日志行（供历史记录）
    _cleanup_records = []
    for asset in assets:
        try:
            client, host = _ssh_connect(asset)
        except Exception as e:
            _msg = f"❌ {asset.name}({asset.ip}) SSH 连接失败: {e}"
            _log_lines.append(_msg)
            yield {"type": "error", "line": _msg}
            continue
        asset_map = dict(mapping)
        asset_map["TARGET_IP"] = asset.ip or ""
        asset_map["TARGET_HOSTNAME"] = asset.name or ""
        _asset_lines = []
        yield {"type": "asset_start", "asset": asset.name, "ip": asset.ip}
        try:
            # 模拟一个失败的「虚拟步骤」让其回滚所有已成功步骤
            _fake_failed = DeployStep(step_order=999)
            for _evt in _stream_rollback(client, steps, _fake_failed, asset_map, mapping.get("APP_DIR", "")):
                if _evt.get("type") == "output":
                    _asset_lines.append(_evt.get("line", ""))
                yield _evt
            # 额外执行 docker compose down（若存在）
            _app_dir = mapping.get("APP_DIR", "")
            if _app_dir:
                _down = f"cd {_app_dir} && docker compose down -v 2>/dev/null || true"
            else:
                _down = None
            if _down:
                try:
                    _s, _o, _e = client.exec_command(_down, timeout=30)
                    _rc = _o.channel.recv_exit_status()
                    _line = f"  🧹 清理容器: docker compose down -v (exit={_rc})"
                    _asset_lines.append(_line)
                    yield {"type": "output", "line": _line}
                except Exception as ex:
                    _line = f"  ⚠ 清理容器异常: {ex}"
                    _asset_lines.append(_line)
                    yield {"type": "output", "line": _line}
            # 清理运行产物（保留源码目录，便于再次部署）
            if _app_dir:
                _clean_run = (
                    f"cd {_app_dir} 2>/dev/null && "
                    f"rm -rf node_modules .venv venv __pycache__ dist build */__pycache__ 2>/dev/null; "
                    f"find . -name '*.pyc' -type f -delete 2>/dev/null; "
                    f"echo cleaned"
                )
                try:
                    _s, _o, _e = client.exec_command(_clean_run, timeout=30)
                    _rc = _o.channel.recv_exit_status()
                    _line = f"  🧹 清理运行产物(node_modules/venv/cache)，保留源码目录: {_app_dir}"
                    _asset_lines.append(_line)
                    yield {"type": "output", "line": _line}
                except Exception as ex:
                    _line = f"  ⚠ 清理运行产物异常: {ex}"
                    _asset_lines.append(_line)
                    yield {"type": "output", "line": _line}
        finally:
            client.close()
        _cleanup_records.append({"asset": asset.name, "ip": asset.ip, "lines": _asset_lines, "status": "cleaned"})
        _log_lines.extend(_asset_lines)
        yield {"type": "asset_end", "asset": asset.name, "status": "cleaned"}

    # 重置步骤与计划状态
    for s in steps:
        s.status = "pending"
        s.output = ""
        s.diagnosis = ""
        s.fix_command = ""
        s.retry_count = 0
        s.started_at = None
        s.finished_at = None
    _record_cleanup_history(db, plan, _cleanup_records, mapping.get("APP_DIR", ""))
    plan.status = "planned"
    db.commit()
    yield {"type": "complete", "status": "planned", "message": "清理完成，可重新部署"}


# ─── 原 L2953-2985 ───
def _ai_step_failure(db, provider, decision_queue, step: DeployStep, output: str, plan_id: int = 0) -> tuple:
    """步骤失败时调用：AI 诊断 → 存库 → yield 事件 → 等用户决策。
    返回 (decision, fix_commands)。decision ∈ {fix, retry, skip, rollback}。
    如果 WS 断开（_STOPPED 标志），短超时轮询避免线程永久阻塞。"""
    diag = {"root_cause": "（AI 诊断不可用，请看上方输出）", "fix_commands": [], "suggestion": "rollback"}
    if provider:
        d = _ai_diagnose_failure(db, provider, step, output, {})
        if d.get("ok"):
            diag = d
    step.diagnosis = diag.get("root_cause", "")
    step.fix_command = json.dumps(diag.get("fix_commands", []), ensure_ascii=False)
    db.commit()
    yield {"type": "step_diagnosis", "step": step.step_order,
           "root_cause": diag.get("root_cause", ""),
           "fix_commands": diag.get("fix_commands", []),
           "suggestion": diag.get("suggestion", "rollback")}
    yield {"type": "need_decision", "step": step.step_order}
    decision = diag.get("suggestion", "rollback")
    if decision_queue is not None:
        import queue as _queue_module
        while True:
            try:
                decision = decision_queue.get(timeout=5)
                break
            except _queue_module.Empty:
                if _STOPPED.get(plan_id):
                    decision = "rollback"
                    break
                continue
            except Exception:
                decision = diag.get("suggestion", "rollback")
                break
    return decision, diag.get("fix_commands", [])


# ─── 原 L2988-3002 ───
def _run_fix_commands(client, fix_commands: list, _cwd: str, asset_map: dict) -> None:
    """执行 AI 建议的修复命令（带 cwd 前缀）。"""
    for fc in fix_commands or []:
        fc = _resolve_command(fc, asset_map)
        if _cwd and not re.match(r'^cd\s', fc.strip()):
            fc = f"cd {_cwd} && {fc}"
        try:
            _, fo, fe = client.exec_command(fc, timeout=60)
            _rc = fo.channel.recv_exit_status()
            while fo.readline():
                pass
            e = fe.read().decode("utf-8", errors="replace").strip()
            logger.info(f"修复命令执行 {fc} -> exit={_rc} {e[:200]}")
        except Exception as e:
            logger.warning(f"修复命令执行异常: {fc} {e}")


# ─── 原 L3005-3019 ───
def _do_rollback(client, steps: List[DeployStep], failed_step: DeployStep, mapping: dict):
    """静默回滚（HTTP 路径用）。"""
    for r in range(len(steps) - 1, -1, -1):
        s = steps[r]
        if s.step_order > failed_step.step_order:
            if s.status == "skipped":
                continue
        if s.step_order < failed_step.step_order and s.status == "succeeded":
            rc = _resolve_command(s.rollback_command, mapping) if s.rollback_command else ""
            if rc:
                try:
                    client.exec_command(rc, timeout=30)
                except Exception as _exc20:
                    logger.warning("[except:pass] Exception: %s", _exc20, exc_info=True)
            s.status = "rolled_back"


# ─── 原 L3022-3079 ───
def _stream_rollback(client, steps: List[DeployStep], failed_step: DeployStep, mapping: dict, app_dir: str = ""):
    """流式回滚（WS 路径用），逐条产出事件供终端实时显示。"""
    yield {"type": "output", "line": "\r\n\x1b[33m⏪ 开始回滚...\x1b[0m"}
    for r in range(len(steps) - 1, -1, -1):
        s = steps[r]
        # 跳过失败步骤之后的步骤（它们未执行）
        if s.step_order > failed_step.step_order:
            if s.status == "skipped":
                continue
            s.status = "rolled_back"
            yield {"type": "output", "line": f"  ⏭ 步骤 {s.step_order} 未执行，标记回滚"}
            continue
        # 回滚已成功的步骤
        if s.step_order < failed_step.step_order and s.status == "succeeded":
            rc = _resolve_command(s.rollback_command, mapping) if s.rollback_command else ""
            if not rc:
                # 自动生成通用回滚命令
                if "docker compose" in s.command or "docker-compose" in s.command:
                    rc = f"cd {app_dir} && docker compose down -v 2>/dev/null" if app_dir else "docker compose down -v 2>/dev/null"
                elif "mkdir" in s.command:
                    _dir_match = re.search(r'mkdir\s+(?:-p\s+)?(\S+)', s.command)
                    if _dir_match:
                        rc = f"rm -rf {_dir_match.group(1)}"
                elif "cat >" in s.command or "echo " in s.command or "cp " in s.command or ">" in s.command:
                    _file_match = re.search(r'cat\s+>\s*(\S+)', s.command)
                    if _file_match:
                        rc = f"rm -f {_file_match.group(1)}"
                    _file_match = re.search(r'cp\s+(\S+)\s+(\S+)', s.command)
                    if _file_match:
                        rc = f"rm -f {_file_match.group(2)}"
                    _file_match = re.search(r'echo\s+.*?>\s*(\S+)', s.command)
                    if _file_match:
                        rc = f"rm -f {_file_match.group(1)}"
                    _file_match = re.search(r'>>\s*(\S+)', s.command)
                    if _file_match:
                        rc = f"rm -f {_file_match.group(1)}"
                elif "wget" in s.command or "curl -o" in s.command:
                    _file_match = re.search(r'(?:-o|>)\s+(\S+)', s.command)
                    if _file_match:
                        rc = f"rm -f {_file_match.group(1)}"
                elif "apt-get" in s.command or "yum" in s.command:
                    _pkg = re.search(r'(?:install|remove)\s+(\S+)', s.command)
                    if _pkg:
                        rc = f"apt-get remove -y {_pkg.group(1)} 2>/dev/null || yum remove -y {_pkg.group(1)} 2>/dev/null"
            if rc:
                try:
                    _s, _o, _e = client.exec_command(rc, timeout=30)
                    _rc_code = _o.channel.recv_exit_status() if hasattr(_o, 'channel') else 0
                    _out = _o.read().decode(errors="replace").strip()[:200]
                    _err = _e.read().decode(errors="replace").strip()[:200]
                    _detail = _out or _err
                    yield {"type": "output", "line": f"  ↩ 回滚步骤 {s.step_order}: {rc[:80]}... exit={_rc_code} {_detail[:60]}"}
                except Exception as ex:
                    yield {"type": "output", "line": f"  ⚠ 回滚步骤 {s.step_order} 异常: {ex}"}
            else:
                yield {"type": "output", "line": f"  → 步骤 {s.step_order} 无需回滚命令"}
            s.status = "rolled_back"
    yield {"type": "output", "line": "\x1b[32m✔ 回滚完成\x1b[0m\r\n"}


