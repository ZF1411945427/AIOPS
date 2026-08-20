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
    _now, _get_provider, _get_assets, _extract_json, _safe_json,
    _resolve_command, _ssh_connect, _offline_blocked_reason, _proxy_env_prefix,
    _sync_env_mapping_from_sop, resolve_download_path, _is_valid_shell_command,
    _check_unresolved, _get_asset_ids,
)


# ─── 原 L192-224 ───
def _ai_diagnose_failure(db: Session, provider, step: DeployStep, step_output: str, env_context: dict) -> dict:
    """步骤失败时, AI 诊断根因并给出修复建议(B 层核心)。"""
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责分析部署步骤失败原因并给出修复方案。\n"
        "输出严格 JSON：\n"
        "{\n"
        '  "root_cause": "根因分析（中文）",\n'
        '  "fix_commands": ["修复命令 1", "修复命令 2"],\n'
        '  "suggestion": "建议重试/跳过/回滚"\n'
        "}\n"
        "fix_commands 最多 3 条，每条应是可执行的 shell 命令。"
    )
    user_prompt = (
        f"## 失败步骤\n步骤 {step.step_order}: {step.description}\n"
        f"命令: {step.command}\n"
        f"校验命令: {step.verify_command or '无'}\n"
        f"## 输出\n{step_output[:2000]}\n"
        f"## 环境上下文\n{json.dumps(env_context, ensure_ascii=False)[:1500]}\n\n请诊断根因并给出修复方案。"
    )
    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=60)
    if resp.get("error"):
        return {"error": f"诊断失败: {resp['error']}"}
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return {"error": "AI 返回格式异常"}
    diag = _extract_json(content)
    if not diag:
        return {"ok": True, "root_cause": "AI 诊断失败", "fix_commands": [], "suggestion": "rollback"}
    return {"ok": True, "root_cause": diag.get("root_cause", ""), "fix_commands": diag.get("fix_commands", []), "suggestion": diag.get("suggestion", "rollback")}


# ─── 原 L506-557 ───
def _ai_auto_resolve_env(provider, plan: DeployPlan, doc_raw: str, steps: list, env_vars: list) -> dict:
    """AI 基于手册上下文自动推断环境变量值，无需用户手动填写。

    输入: 解析后的 env_vars 列表 + 原始手册 + 步骤
    输出: {"APP_DIR": "/tmp/aiplan-test", "PORT": "8080", ...}
    """
    if not env_vars or not provider:
        return {}
    only_auto = all(e.get("source") == "auto" or e.get("source") == "资产" for e in env_vars)
    if only_auto:
        return {}
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责从部署手册中自动推断环境变量的值。\n"
        "严格按 JSON 输出，key=环境变量名, value=推断的值:\n"
        "{\n"
        '  "APP_DIR": "/tmp/aiplan-test",\n'
        '  "PORT": "8080"\n'
        "}\n"
        "规则：\n"
        "- 从手册的步骤命令中寻找原始值（手册中可能有 mkdir -p /tmp/xxx，从中提取 APP_DIR）\n"
        "- 从手册的端口映射、URL 中提取端口号\n"
        "- 从资产信息中提取 IP（TARGET_IP 用资产 IP）\n"
        "- 如果无法推断，留空字符串\n"
        "- 只输出 JSON，不要任何额外内容"
    )
    doc_raw_snippet = doc_raw[:3000] if doc_raw else ""
    step_cmds = "\n".join([(s.get("command", "") or "")[:200] for s in steps])
    env_names = [e.get("name", "") for e in env_vars]
    user_prompt = (
        f"## 部署手册(片段)\n{doc_raw_snippet}\n\n"
        f"## 步骤命令\n{step_cmds[:2000]}\n\n"
        f"## 需要推断的环境变量\n{json.dumps(env_names, ensure_ascii=False)}\n\n"
        f"请从手册和步骤命令中为每个环境变量推断实际值，只输出 JSON。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=60)
        if resp.get("error"):
            return {}
        content = resp["choices"][0]["message"]["content"]
        inferred = _extract_json(content) or {}
        if not isinstance(inferred, dict):
            return {}
        # 只保留在 env_vars 中声明过的 key
        valid_keys = set(e.get("name", "") for e in env_vars)
        valid_keys.update(k for k in inferred.keys() if k.startswith("ENV_"))
        return {k: v for k, v in inferred.items() if k in valid_keys and v}
    except Exception as e:
        logger.warning(f"AI 自动推断环境变量异常: {e}")
    return {}


# ─── 原 L560-624 ───
def _ai_auto_resolve_unresolved(provider, plan: DeployPlan, db: Session, steps: list, mapping: dict) -> dict:
    """执行前，如果还有未解析的环境变量，AI 自动解决而非阻塞返回。

    返回填充后的完整 mapping。
    """
    unresolved = set()
    for s in steps:
        for field in (s.command, s.verify_command, s.rollback_command):
            if field:
                missing = _check_unresolved(_resolve_command(field, mapping))
                if missing:
                    unresolved.add(missing)
    if not unresolved:
        return mapping

    if not provider:
        # 没有 AI 时还是要阻塞
        return mapping

    # 让 AI 推断未设置的值
    doc_raw = plan.doc_raw or ""
    cmds = "\n".join([(s.command or "")[:200] for s in steps])
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责为部署计划中的环境变量推断实际值。\n"
        "严格按 JSON 输出，key=变量名, value=推断值:\n{\n"
        '  "APP_DIR": "/tmp/myapp",\n'
        '  "PORT": "8080"\n'
        "}\n"
        "从手册命令中寻找原始值，如果无法推断就留空。"
    )
    user_prompt = (
        f"## 手册(片段)\n{(doc_raw or '')[:3000]}\n\n"
        f"## 步骤命令\n{cmds[:2000]}\n\n"
        f"## 未设置的变量\n{json.dumps(list(unresolved), ensure_ascii=False)}\n\n"
        f"请推断每个变量的值。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=60)
        if resp.get("error"):
            return mapping
        content = resp["choices"][0]["message"]["content"]
        inferred = _extract_json(content) or {}
        if not isinstance(inferred, dict):
            return mapping
        for k, v in inferred.items():
            if k in unresolved and v:
                mapping[k] = str(v)
                if not mapping.get(f"ENV_{k}"):
                    mapping[f"ENV_{k}"] = str(v)
        # 重新检查是否全部解决
        still_unresolved = set()
        for s in steps:
            for field in (s.command, s.verify_command, s.rollback_command):
                if field:
                    missing = _check_unresolved(_resolve_command(field, mapping))
                    if missing:
                        still_unresolved.add(missing)
        if still_unresolved:
            logger.warning(f"AI 无法推断的变量: {still_unresolved}")
    except Exception as e:
        logger.warning(f"AI 自动解决未解析变量异常: {e}")
    return mapping


# ─── 原 L1478-1538 ───
def _ai_build_execution_dag(db: Session, provider, plan: DeployPlan, steps: list) -> Optional[dict]:
    """AI 分析步骤依赖关系，生成 DAG 执行计划（能力①：动态编排）。

    返回 {"groups": [{"group_order", "step_orders", "parallel", "reason"}], "reasoning"}。
    AI 不可用/解析失败时回退为线性顺序（每步一组，串行）。
    """
    probe = {}
    if plan.environment_probe_json:
        probe = _safe_json(plan.environment_probe_json)
    step_descs = [{
        "order": s.step_order,
        "description": s.description,
        "command": (s.command or "")[:200],
        "risk": s.risk_level,
        "verify": (s.verify_command or "")[:100],
        "rollback": (s.rollback_command or "")[:100],
    } for s in steps]
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责分析部署步骤的依赖关系，生成最优执行计划(DAG)。\n"
        "请严格按以下 JSON Schema 输出，不要任何额外内容：\n"
        "{\n"
        '  "groups": [\n'
        "    {\n"
        '      "group_order": 1,\n'
        '      "step_orders": [1],\n'
        '      "parallel": false,\n'
        '      "reason": "前置准备步骤，无依赖"\n'
        "    }\n"
        "  ],\n"
        '  "reasoning": "简要分析说明"\n'
        "}\n"
        "规则：\n"
        "- 有依赖关系的步骤必须放在不同组（前组完成后才能执行后组）\n"
        "- 互不依赖的步骤可放入同一组并行执行（parallel: true）\n"
        "- 同一组内并行步骤必须互不依赖，且不能互相覆盖文件/端口/服务\n"
        "- 组按执行先后顺序排列 group_order，所有 step_orders 必须覆盖全部步骤，不得遗漏\n"
        "- 若无法判断依赖关系，保守起见每步单独成组（串行最安全）\n"
        "- 涉及 docker compose up / 启动服务 / 写配置的步骤通常串行，避免竞争"
    )
    user_prompt = (
        f"## 部署步骤\n{json.dumps(step_descs, ensure_ascii=False, indent=1)}\n\n"
        f"## 目标环境探查摘要\nOS: {str(probe.get('os', ''))[:100]}\n"
        f"Docker: {str(probe.get('docker', ''))[:50]}\n"
        f"端口: {json.dumps(probe.get('port_scan', {}), ensure_ascii=False)[:200]}\n\n"
        "请分析步骤依赖关系，生成最优执行计划。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=60)
        if resp.get("error"):
            logger.warning(f"DAG 分析失败: {resp['error']}")
            return None
        content = resp["choices"][0]["message"]["content"]
        dag = _extract_json(content)
        if dag and isinstance(dag.get("groups"), list) and dag["groups"]:
            return dag
    except Exception as e:
        logger.warning(f"DAG 分析异常: {e}")
    return None


# ─── 原 L1541-1582 ───
def _ai_pre_execution_risk(provider, step: DeployStep, plan: DeployPlan) -> dict:
    """AI 预判单步骤执行风险（能力③：执行前预判），返回风险建议 dict。"""
    probe = {}
    if plan.environment_probe_json:
        probe = _safe_json(plan.environment_probe_json)
    sys_prompt = (
        "你是资深 SRE 运维专家，负责分析部署步骤命令的执行风险并给出应对建议。\n"
        "严格按 JSON 输出，不要额外内容：\n"
        "{\n"
        '  "risk": "low|medium|high",\n'
        '  "reason": "风险分析（中文，一句话）",\n'
        '  "precheck": "可选的前置检查命令（空串表示无需额外检查）",\n'
        '  "precheck_expect": "前置检查预期结果",\n'
        '  "suggest_modify": "建议替换后的更安全命令（空串表示无需修改）",\n'
        '  "guard_note": "执行中的注意事项（中文，一句话）"\n'
        "}\n"
        "规则：\n"
        "- 涉及 rm -rf、docker compose down、重启服务、覆盖配置文件 → high\n"
        "- 涉及文件复制、mkdir、chmod、wget/curl 下载 → medium\n"
        "- 只读查询、echo、日志输出 → low\n"
        "- 若目标环境已存在端口占用/目录冲突，precheck 应给出检测命令"
    )
    user_prompt = (
        f"## 步骤\n序列: {step.step_order}\n描述: {step.description}\n"
        f"命令: {step.command}\n风险声明: {step.risk_level}\n"
        f"## 目标环境\n{json.dumps(probe, ensure_ascii=False)[:1200]}\n\n"
        "请分析该命令的执行风险。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return {}
        content = resp["choices"][0]["message"]["content"]
        r = _extract_json(content) or {}
        if r.get("risk"):
            return r
    except Exception as _exc7:
        logger.warning("[except:pass] Exception: %s", _exc7, exc_info=True)
    return {}


# ─── 原 L1585-1620 ───
def _ai_autonomous_decision(provider, step: DeployStep, output: str, diag: dict, history: list) -> str:
    """AI 自主决策（能力②：失败自主决策），返回 fix/retry/skip/rollback 之一。"""
    sys_prompt = (
        "你是资深 SRE 运维专家，部署步骤失败后由你自主决策下一步操作，无需人工确认。\n"
        "只输出一个单词：fix 或 retry 或 skip 或 rollback\n"
        "决策规则：\n"
        "- fix: 有明确修复命令且修复成功率高（>70%），选择 fix\n"
        "- retry: 疑似临时性问题（网络抖动、资源刚好被占用、重试能解决），选择 retry\n"
        "- skip: 该步骤非关键、失败不影响整体可用性、后续步骤可补偿，选择 skip\n"
        "- rollback: 严重错误、修复/重试风险高、继续执行会扩大损失，选择 rollback\n"
        "只输出一个单词，不要任何其他内容。"
    )
    history_txt = "无"
    if history:
        history_txt = "; ".join([f"第{h.get('attempt', 1)}次: {h.get('decision', '')}({h.get('result', '')})" for h in history[-3:]])
    user_prompt = (
        f"## 失败步骤\n步骤 {step.step_order}: {step.description}\n风险等级: {step.risk_level}\n"
        f"## 命令\n{(step.command or '')[:200]}\n"
        f"## 输出(截断)\n{(output or '')[:1500]}\n"
        f"## AI 诊断\n根因: {diag.get('root_cause', '')}\n建议: {diag.get('suggestion', '')}\n"
        f"修复命令: {json.dumps(diag.get('fix_commands', []), ensure_ascii=False)}\n"
        f"## 历史决策\n{history_txt}\n\n请自主决策下一步操作。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return diag.get("suggestion", "rollback") or "rollback"
        content = resp["choices"][0]["message"]["content"].strip().lower()
        if content in ("fix", "retry", "skip", "rollback"):
            return content
    except Exception as _exc8:
        logger.warning("[except:pass] Exception: %s", _exc8, exc_info=True)
    return diag.get("suggestion", "rollback") or "rollback"


# ─── 原 L1623-1662 ───
def _ai_adaptive_rollback(provider, steps: list, plan: DeployPlan) -> Optional[list]:
    """AI 自适应回滚分析（能力⑤）：返回需回滚的步骤逆序列表(step_order 列表)。
    跳过无状态步骤(echo/mkdir/校验等)。AI 不可用时回退全量逆序。
    """
    step_info = [{
        "order": s.step_order,
        "description": s.description,
        "command": (s.command or "")[:150],
        "rollback": (s.rollback_command or "")[:150],
        "status": s.status,
    } for s in steps]
    sys_prompt = (
        "你是资深 SRE 运维专家，分析部署失败后哪些步骤真正需要回滚。\n"
        "严格按 JSON 输出，不要额外内容：\n"
        "{\n"
        '  "rollback_steps": [3, 2],\n'
        '  "skip_steps": [1, 4],\n'
        '  "reasoning": "简要分析说明"\n'
        "}\n"
        "规则：\n"
        "- rollback_steps 按回滚执行顺序排列（先回滚后执行的步骤，即逆序）\n"
        "- 无状态步骤（echo、mkdir -p、ls、校验命令、只读检查）可跳过回滚\n"
        "- 有状态步骤（docker compose up、cp/覆盖文件、服务启动、配置写入）必须回滚\n"
        "- 必须覆盖所有已成功执行的步骤"
    )
    user_prompt = f"## 步骤列表(含状态)\n{json.dumps(step_info, ensure_ascii=False, indent=1)}\n\n请分析哪些步骤需要回滚。"
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return None
        content = resp["choices"][0]["message"]["content"]
        r = _extract_json(content) or {}
        if isinstance(r.get("rollback_steps"), list) and r["rollback_steps"]:
            return r["rollback_steps"]
    except Exception as _exc9:
        logger.warning("[except:pass] Exception: %s", _exc9, exc_info=True)
    return None


# ─── 原 L1665-1683 ───
def _ai_decision_log(plan: DeployPlan, entry: dict) -> None:
    """把 AI 自主决策/重排追加到 plan.ai_decision_log_json（最多 200 条）。"""
    try:
        log = json.loads(plan.ai_decision_log_json) if isinstance(plan.ai_decision_log_json, str) and plan.ai_decision_log_json not in ("[]", "") else []
    except Exception:
        log = []
    if not isinstance(log, list):
        log = []
    entry.setdefault("ts", datetime.now().isoformat())
    log.append(entry)
    if len(log) > 200:
        log = log[-200:]
    plan.ai_decision_log_json = json.dumps(log, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# L4 — AI 决策引擎（策略选择 + 实时决策 + 健康门控 + 动态调度）
# L5 — 历史学习引擎（特征记录 + 风险评分 + 模式匹配）
# ═══════════════════════════════════════════════════════════════


# ─── 原 L1686-1723 ───
def _ai_select_deployment_strategy(provider, plan: DeployPlan, steps: list, probe: dict, assets: list) -> str:
    """L4: AI 根据服务类型/风险/环境选择部署策略。
    返回: rolling / blue-green / canary / recreate / auto。
    """
    step_descs = [{"order": s.step_order, "desc": s.description, "cmd": (s.command or "")[:100], "risk": s.risk_level} for s in steps]
    asset_info = [{"name": a.name, "ip": a.ip, "ci_type": a.ci_type} for a in assets]
    has_compose = any("docker compose" in (s.command or "") or "docker-compose" in (s.command or "") for s in steps)
    has_service = any("up" in (s.command or "") or "restart" in (s.command or "") or "start" in (s.command or "") for s in steps)
    sys_prompt = (
        "你是一名资深 SRE 架构师，负责为部署计划选择最佳策略。\n"
        "只输出一个单词：rolling 或 blue-green 或 canary 或 recreate 或 auto\n"
        "规则：\n"
        "- recreate: 简单应用/测试/开发环境/无状态服务，风险低，直接重建\n"
        "- rolling: 生产环境多实例服务，需要逐步替换，保持可用性\n"
        "- blue-green: 关键业务服务，需要零停机切换，有完整回滚能力\n"
        "- canary: 高风险变更，需要灰度放量验证，逐步扩大范围\n"
        "- auto: 不确定时选 auto，由执行引擎自动判断\n"
        "只输出一个单词，不要任何其他内容。"
    )
    user_prompt = (
        f"## 服务类型\n涉及 docker-compose: {has_compose}\n涉及服务启停: {has_service}\n"
        f"资产数: {len(assets)}\n\n## 步骤\n{json.dumps(step_descs, ensure_ascii=False, indent=1)}\n\n"
        f"## 目标资产\n{json.dumps(asset_info, ensure_ascii=False)}\n\n"
        f"## 环境\nOS: {probe.get('os','')[:80]}\nDocker: {probe.get('docker','')[:30]}\n\n请选择最佳部署策略。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return "auto"
        decision = resp["choices"][0]["message"]["content"].strip().lower()
        if decision in ("rolling", "blue-green", "canary", "recreate", "auto"):
            return decision
    except Exception as _exc10:
        logger.warning("[except:pass] Exception: %s", _exc10, exc_info=True)
    return "auto"


# ─── 原 L1726-1761 ───
def _ai_risk_scoring(provider, plan: DeployPlan, steps: list, probe: dict, assets: list, history: list) -> int:
    """L5: AI 基于历史数据和当前环境，预判部署风险评分 0-100。
    0=无风险, 100=极高风险。
    """
    step_risks = [s.risk_level for s in steps]
    high_count = sum(1 for r in step_risks if r == "high")
    med_count = sum(1 for r in step_risks if r == "medium")
    prev_failures = sum(1 for h in history if h.get("status") in ("failed", "rolled_back")) if history else 0
    prev_total = len(history) if history else 0
    fail_rate = prev_failures / prev_total if prev_total > 0 else 0
    sys_prompt = (
        "你是一名资深 SRE 专家，负责评估部署风险。\n"
        "只输出一个 0-100 的整数，不要任何其他内容。\n"
        "评分规则：\n"
        "- 0-20: 低风险（简单脚本/只读操作/测试环境）\n"
        "- 21-50: 中等风险（常规部署/有回滚/已验证）\n"
        "- 51-80: 高风险（涉及服务重启/端口变更/生产环境）\n"
        "- 81-100: 极高风险（数据库变更/架构变更/历史失败率高）\n"
        "综合考虑：步骤风险等级、历史失败率、服务类型、资产数量。"
    )
    user_prompt = (
        f"## 步骤风险\nhigh={high_count} medium={med_count} low={len(steps)-high_count-med_count}\n"
        f"## 历史失败率\n失败 {prev_failures}/{prev_total} 次 ({fail_rate*100:.0f}%)\n"
        f"## 资产数\n{len(assets)} 台\n\n请评估部署风险评分(0-100)。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return min(100, high_count * 30 + med_count * 10)
        score = int("".join(c for c in resp["choices"][0]["message"]["content"] if c.isdigit()) or "50")
        return max(0, min(100, score))
    except Exception:
        return min(100, high_count * 30 + med_count * 10)


# ─── 原 L1764-1790 ───
def _record_deployment_feature(plan: DeployPlan, steps: list, assets: list, probe: dict,
                                status: str, step_results: list, total_duration: float) -> dict:
    """L5: 记录部署特征向量，供后续学习和风险预测使用。
    返回特征 dict 并存入 plan.deployment_feature_json。
    """
    step_risks = [s.risk_level for s in steps]
    features = {
        "step_count": len(steps),
        "asset_count": len(assets),
        "high_risk_steps": sum(1 for r in step_risks if r == "high"),
        "medium_risk_steps": sum(1 for r in step_risks if r == "medium"),
        "has_compose": any("docker compose" in (s.command or "") for s in steps),
        "has_docker_run": any("docker run" in (s.command or "") for s in steps),
        "has_systemctl": any("systemctl" in (s.command or "") for s in steps),
        "has_db_migration": any("migrate" in (s.command or "").lower() or "schema" in (s.command or "").lower() for s in steps),
        "total_duration_seconds": total_duration,
        "step_success_count": sum(1 for r in step_results if r.get("status") == "succeeded"),
        "step_fail_count": sum(1 for r in step_results if r.get("status") == "failed"),
        "step_skip_count": sum(1 for r in step_results if r.get("status") == "skipped"),
        "retry_count": sum(r.get("retry_count", 0) for r in step_results),
        "ai_decision_count": len(step_results) - sum(1 for r in step_results if r.get("status") == "succeeded"),
        "deploy_status": status,
        "os_type": "centos" if "centos" in (probe.get("os", "") or "").lower() else "ubuntu" if "ubuntu" in (probe.get("os", "") or "").lower() else "other",
        "docker_version": (probe.get("docker", "") or "")[:20],
    }
    plan.deployment_feature_json = json.dumps(features, ensure_ascii=False)
    return features


# ─── 原 L1793-1832 ───
def _ai_pattern_matching(provider, features: dict, history: list) -> Optional[dict]:
    """L5: AI 匹配历史部署中的失败模式，提前预警。
    返回 {"matched": True/False, "pattern": "...", "risk": "high/medium/low", "suggestion": "..."}。
    """
    if not history or len(history) < 2:
        return None
    # 提取历史特征
    hist_features = [h for h in history if isinstance(h, dict) and h.get("features")]
    if not hist_features:
        return None
    sys_prompt = (
        "你是一名资深 SRE 专家，分析部署历史数据，识别失败模式。\n"
        "严格按 JSON 输出，不要额外内容：\n"
        "{\n"
        '  "matched": true/false,\n'
        '  "pattern": "匹配到的失败模式描述",\n'
        '  "risk": "high/medium/low",\n'
        '  "suggestion": "建议的预防措施"\n'
        "}\n"
        "如果当前部署特征与历史上失败模式相似，matched=true 并给出建议。"
    )
    user_prompt = (
        f"## 当前部署特征\n{json.dumps(features, ensure_ascii=False, indent=1)}\n\n"
        f"## 历史部署({len(hist_features)} 次)\n{json.dumps(hist_features[-5:], ensure_ascii=False, indent=1)}\n\n"
        f"请分析是否存在失败模式匹配。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return None
        content = resp["choices"][0]["message"]["content"]
        pattern = _extract_json(content) or {}
        if pattern.get("matched"):
            return pattern
    except Exception as _exc11:
        logger.warning("[except:pass] Exception: %s", _exc11, exc_info=True)
    return None


# ─── 原 L1835-1881 ───
def _ai_assess_state(provider, plan: DeployPlan, step_results: list, current_step: int,
                      health_data: dict, strategy: str) -> dict:
    """L4: AI 实时评估部署状态，决定下一步动作。
    返回 {"action": "continue/adjust/rollback/complete", "reason": "...", "adjustments": {...}}。
    """
    succeed_count = sum(1 for r in step_results if r.get("status") == "succeeded")
    fail_count = sum(1 for r in step_results if r.get("status") == "failed")
    total = len(step_results)
    sys_prompt = (
        "你是一名资深 SRE 专家，负责在部署过程中实时评估状态并决策。\n"
        "严格按 JSON 输出，不要额外内容：\n"
        "{\n"
        '  "action": "continue/adjust/rollback/complete",\n'
        '  "reason": "决策理由（中文，一句话）",\n'
        '  "adjustments": {\n'
        '    "parallelism": "保持/增加/减少",\n'
        '    "pace": "正常/加快/放慢",\n'
        '    "next_steps": "继续执行/先验证/先修复"\n'
        '  }\n'
        "}\n"
        "规则：\n"
        "- continue: 一切正常，继续执行\n"
        "- adjust: 需要调整执行节奏或并行度\n"
        "- rollback: 出现严重问题，必须回滚\n"
        "- complete: 所有步骤已完成或无需继续\n"
        "如果失败率超过 30%，考虑 rollback。"
    )
    user_prompt = (
        f"## 当前策略\n{strategy}\n\n"
        f"## 执行进度\n总步骤: {total}\n成功: {succeed_count}\n失败: {fail_count}\n当前步骤: {current_step}\n\n"
        f"## 健康数据\n{json.dumps(health_data, ensure_ascii=False)[:500]}\n\n"
        f"请评估当前状态并决策。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return {"action": "continue", "reason": "AI 评估不可用", "adjustments": {}}
        content = resp["choices"][0]["message"]["content"]
        decision = _extract_json(content) or {}
        if decision.get("action") in ("continue", "adjust", "rollback", "complete"):
            return decision
    except Exception as _exc12:
        logger.warning("[except:pass] Exception: %s", _exc12, exc_info=True)
    return {"action": "continue", "reason": "AI 评估异常，默认继续", "adjustments": {}}


# ─── 原 L1884-1916 ───
def _ai_health_gate(provider, client, asset_map: dict, step: DeployStep, strategy: str) -> dict:
    """L4: 健康门控 — 每步执行后检查关键指标，决定是否放行下一步。
    返回 {"passed": True/False, "checks": [...], "recommendation": "continue/verify/rollback"}。
    """
    checks = []
    # 1. Docker 守护进程
    try:
        _, o, _ = client.exec_command("docker info --format '{{.ServerVersion}}' 2>/dev/null || echo 'FAIL'", timeout=10)
        rc = o.channel.recv_exit_status()
        ver = o.read().decode(errors="replace").strip()
        checks.append({"name": "Docker 守护进程", "passed": rc == 0, "detail": ver if rc == 0 else "不可用"})
    except Exception as e:
        checks.append({"name": "Docker 守护进程", "passed": False, "detail": str(e)})
    # 2. 磁盘空间
    try:
        _, o, _ = client.exec_command("df -h / 2>/dev/null | tail -1 | awk '{print $5}'", timeout=5)
        pct = o.read().decode(errors="replace").strip().rstrip("%")
        disk_ok = int(pct) < 85 if pct.isdigit() else True
        checks.append({"name": "磁盘使用率", "passed": disk_ok, "detail": f"{pct}%" if pct.isdigit() else "未知"})
    except Exception:
        checks.append({"name": "磁盘使用率", "passed": True, "detail": "检查失败"})
    # 3. 关键端口（如果已知）
    target_port = asset_map.get("TARGET_PORT", "")
    if target_port:
        try:
            _, o, _ = client.exec_command(f"ss -tlnp | grep ':{target_port} ' || echo 'FREE'", timeout=5)
            out = o.read().decode(errors="replace").strip()
            checks.append({"name": f"端口 {target_port}", "passed": True, "detail": "已监听" if "FREE" not in out else "未占用"})
        except Exception as _exc13:
            logger.warning("[except:pass] Exception: %s", _exc13, exc_info=True)
    all_passed = all(c.get("passed", True) for c in checks)
    recommendation = "continue" if all_passed else "rollback" if strategy == "blue-green" else "verify"
    return {"passed": all_passed, "checks": checks, "recommendation": recommendation}


# ─── 原 L1919-1955 ───
def _ai_dynamic_scheduling(provider, plan: DeployPlan, step_results: list, strategy: str) -> dict:
    """L4: AI 动态调度 — 根据执行进度和状态，调整后续步骤的并行度/顺序。
    返回 {"adjusted_dag": {...}, "reason": "..."}。
    """
    fail_count = sum(1 for r in step_results if r.get("status") == "failed")
    retry_count = sum(r.get("retry_count", 0) for r in step_results)
    sys_prompt = (
        "你是一名资深 SRE 专家，负责动态调整部署调度。\n"
        "严格按 JSON 输出，不要额外内容：\n"
        "{\n"
        '  "adjust": "none/slow_down/speed_up/reorder",\n'
        '  "reason": "调整理由（中文）",\n'
        '  "parallelism": "keep/reduce/increase"\n'
        "}\n"
        "规则：\n"
        "- 失败次数多 → slow_down + reduce 并行度\n"
        "- 一切顺利 → speed_up + increase 并行度\n"
        "- 重试过多 → reorder 提前执行关键步骤"
    )
    user_prompt = (
        f"## 策略\n{strategy}\n\n## 执行结果\n{json.dumps(step_results[-5:], ensure_ascii=False, indent=1)}\n\n"
        f"## 统计\n失败: {fail_count}\n重试: {retry_count}\n\n请决定是否调整调度。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=30)
        if resp.get("error"):
            return {"adjust": "none", "reason": "AI 不可用", "parallelism": "keep"}
        content = resp["choices"][0]["message"]["content"]
        decision = _extract_json(content) or {}
        if decision.get("adjust"):
            return decision
    except Exception as _exc14:
        logger.warning("[except:pass] Exception: %s", _exc14, exc_info=True)
    return {"adjust": "none", "reason": "默认继续", "parallelism": "keep"}


# ─── 原 L1958-2025 ───
def _ai_plan_step_autonomous(provider, step: DeployStep, plan: DeployPlan, probe: dict, env_context: dict) -> dict:
    """AI 理解步骤意图 + 结合环境 → 自主生成执行计划。

    替代机械执行 step.command，让 AI 理解步骤意图后，根据当前环境动态调整命令。
    返回 {"intent": "步骤意图", "commands": ["调整后的命令"], "verify": "验证命令",
          "expected": "期望结果", "adjustments": ["调整说明"], "risk": "low/medium/high"}。
    """
    step_desc = step.description or ""
    step_cmd = (step.command or "")[:500]
    step_verify = (step.verify_command or "")[:200]
    probe_os = (probe.get("os", "") if isinstance(probe, dict) else "")[:200]
    probe_docker = (probe.get("docker", "") if isinstance(probe, dict) else "")[:50]
    probe_ports = (probe.get("port_scan", {}) if isinstance(probe, dict) else {})
    probe_containers = (probe.get("containers", "") if isinstance(probe, dict) else "")[:200]
    prev_output = env_context.get("prev_output", "")[:500]
    prev_status = env_context.get("prev_status", "")
    cwd = env_context.get("cwd", "")
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责理解部署步骤的意图，并根据当前目标机环境自主生成最佳执行方案。\n"
        "严格按以下 JSON Schema 输出，不要任何额外内容：\n"
        "{\n"
        '  "intent": "步骤意图（中文，一句话说明这本书要做什么）",\n'
        '  "commands": ["最终要执行的 shell 命令（每行一条）"],\n'
        '  "verify": "执行后的验证命令（可选，空串表示无需验证）",\n'
        '  "expected": "期望结果描述",\n'
        '  "adjustments": ["针对当前环境的调整说明（如：端口冲突换端口、目录已存在跳过创建）"],\n'
        '  "risk": "low/medium/high"\n'
        "}\n"
        "关键规则：\n"
        "- 必须理解步骤意图，不能机械照搬手册命令\n"
        "- 结合当前环境（OS/Docker 版本/端口/容器/磁盘/内存）调整命令\n"
        "- 如果手册命令在当前环境有问题（端口冲突、镜像不存在、目录已存在），自动调整\n"
        "- 如果上一步失败或告警，自动添加前置检查\n"
        "- commands 中的命令必须是可直接执行的 shell 命令，且必须真实、可落地\n"
        "- 不要自行编造或添加 cd 前缀：工作目录由系统根据当前工作目录(cwd)自动处理；\n"
        "  只有当命令确实需要切换到其它目录时，才使用该命令自身的 cd，且 cd 后的路径必须是真实存在的绝对路径\n"
        "- 严禁使用占位示例路径（如 /path/to/project、/home/user/xxx 等）——不存在这样的目录，会导致命令失败\n"
        "- 如果无法确定正确的目录或路径，直接使用原始命令，不要编造\n"
        "- 确保命令安全：不要 rm -rf 无验证、不要遗漏依赖\n"
        "- 如果无法确定，保守执行原命令，不要编造"
    )
    user_prompt = (
        f"## 步骤信息\n序号: {step.step_order}\n"
        f"描述: {step_desc}\n原始命令: {step_cmd}\n原始验证: {step_verify}\n"
        f"风险等级: {step.risk_level}\n\n"
        f"## 目标机环境\nOS: {probe_os}\nDocker: {probe_docker}\n"
        f"端口状态: {json.dumps(probe_ports, ensure_ascii=False)[:200]}\n"
        f"当前容器: {probe_containers[:200]}\n\n"
        f"## 执行上下文\n上一步状态: {prev_status}\n上一步输出: {prev_output[:300]}\n"
        f"当前工作目录: {cwd}\n\n"
        f"请理解步骤意图，结合环境自主生成最佳执行方案。"
    )
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], timeout_override=60)
        if resp.get("error"):
            return {"intent": step_desc, "commands": [step_cmd], "verify": step_verify,
                    "expected": "", "adjustments": [], "risk": step.risk_level}
        content = resp["choices"][0]["message"]["content"]
        plan_data = _extract_json(content) or {}
        if plan_data.get("commands") and isinstance(plan_data["commands"], list):
            return plan_data
    except Exception as e:
        logger.warning(f"AI 自主规划异常: {e}")
    return {"intent": step_desc, "commands": [step_cmd], "verify": step_verify,
            "expected": "", "adjustments": [], "risk": step.risk_level}


# ─── 原 L2028-2157 ───
def _ai_resource_check(provider, plan: DeployPlan, steps: list, assets: list, probe: dict) -> dict:
    """前置资源检查：SSH 采集目标机真实资源，AI 分析是否足够部署。
    返回 {"passed": True/False, "checks": [...], "recommendation": "proceed/block/warn", "summary": "..."}。
    """
    if not assets:
        return {"passed": False, "checks": [{"name": "SSH连接", "passed": False, "detail": "无目标资产"}],
                "recommendation": "block", "summary": "无目标资产，无法部署"}

    asset = assets[0]
    try:
        client, host = _ssh_connect(asset)
    except Exception as e:
        return {"passed": False, "checks": [{"name": "SSH连接", "passed": False, "detail": str(e)[:100]}],
                "recommendation": "block", "summary": f"SSH 连接失败: {str(e)[:100]}"}

    checks = []
    try:
        # 1. 内存
        _, o, _ = client.exec_command("free -m | grep Mem:", timeout=10)
        mem_raw = o.read().decode(errors="replace").strip().split()
        mem_total = int(mem_raw[1]) if len(mem_raw) > 1 else 0
        mem_used = int(mem_raw[2]) if len(mem_raw) > 2 else 0
        mem_avail = int(mem_raw[6]) if len(mem_raw) > 6 else mem_total - mem_used  # available 列
        # 估算服务所需内存(mem_avail 已扣除系统占用，故基础值只算 Docker 容器开销)
        estimated_mb = 128  # Docker 容器 + 网络开销
        for s in steps:
            cmd = (s.command or "").lower()
            if "mysql" in cmd or "postgres" in cmd or "mariadb" in cmd:
                estimated_mb += 400
            elif "redis" in cmd:
                estimated_mb += 50
            elif "elastic" in cmd or "mongo" in cmd:
                estimated_mb += 512
            elif "java" in cmd or "spring" in cmd or "tomcat" in cmd or "jenkins" in cmd:
                estimated_mb += 512
            elif "nginx" in cmd:
                estimated_mb += 50
            elif "python" in cmd or "flask" in cmd or "django" in cmd or "node" in cmd or "php" in cmd:
                estimated_mb += 128
            elif "rabbitmq" in cmd or "kafka" in cmd:
                estimated_mb += 256
            elif "gitlab" in cmd:
                estimated_mb += 1024
            elif "memcached" in cmd:
                estimated_mb += 50
        mem_ok = mem_avail >= estimated_mb
        checks.append({"name": "内存", "passed": mem_ok, "detail": f"可用 {mem_avail}MB, 估算需 {estimated_mb}MB",
                        "value": mem_avail, "threshold": estimated_mb, "unit": "MB"})

        # 2. 磁盘
        _, o, _ = client.exec_command("df -m / | tail -1 | awk '{print $2,$3,$4}'", timeout=10)
        disk_raw = o.read().decode(errors="replace").strip().split()
        disk_total = int(disk_raw[0]) if len(disk_raw) > 0 else 0
        disk_avail = int(disk_raw[2]) if len(disk_raw) > 2 else 0
        disk_ok = disk_avail >= 2048  # 至少 2GB
        checks.append({"name": "磁盘", "passed": disk_ok, "detail": f"可用 {disk_avail}MB, 建议>=2048MB",
                        "value": disk_avail, "threshold": 2048, "unit": "MB"})

        # 3. Docker 可用
        _, o, _ = client.exec_command("docker info --format '{{.ServerVersion}}' 2>/dev/null || echo 'NODOCKER'", timeout=10)
        docker_ver = o.read().decode(errors="replace").strip()
        docker_ok = docker_ver != "NODOCKER" and docker_ver != ""
        checks.append({"name": "Docker", "passed": docker_ok, "detail": docker_ver if docker_ok else "Docker 不可用"})

        # 4. 端口冲突
        port_conflicts = []
        for s in steps:
            cmd = (s.command or "")
            for _m in re.finditer(r'(?:EXPOSE\s+|ports:\s*["\']?|:\s*)(\d{2,5})', cmd):
                _p = _m.group(1)
                _pi = int(_p)
                if 80 <= _pi <= 65535:
                    _, o, _ = client.exec_command(f"ss -tlnp | grep ':{_p} ' || echo 'FREE'", timeout=5)
                    p_status = o.read().decode(errors="replace").strip()
                    if "FREE" not in p_status:
                        port_conflicts.append(_p)
        port_ok = len(port_conflicts) == 0
        checks.append({"name": "端口", "passed": port_ok, "detail": f"冲突端口: {', '.join(port_conflicts)}" if port_conflicts else "无冲突",
                        "conflicts": port_conflicts})

        # 5. 容器名冲突
        container_conflicts = []
        for s in steps:
            cmd = (s.command or "")
            for _m in re.finditer(r'container_name:\s*(\S+)', cmd):
                cname = _m.group(1)
                _, o, _ = client.exec_command(f"docker ps -a --format '{{{{.Names}}}}' | grep -x '{cname}' || echo 'FREE'", timeout=5)
                if "FREE" not in o.read().decode(errors="replace").strip():
                    container_conflicts.append(cname)
        container_ok = len(container_conflicts) == 0
        checks.append({"name": "容器名", "passed": container_ok, "detail": f"冲突: {', '.join(container_conflicts)}" if container_conflicts else "无冲突"})

        # 6. 镜像可用性
        images_missing = []
        for s in steps:
            for _m in re.finditer(r'image:\s*(\S+)', s.command or ""):
                img = _m.group(1)
                _, o, _ = client.exec_command(f"docker images --format '{{{{.Repository}}}}.{{{{.Tag}}}}' | grep -q '{img.split(':')[0]}' && echo 'HAVE' || echo 'MISS'", timeout=5)
                if "HAVE" not in o.read().decode(errors="replace").strip():
                    images_missing.append(img)
        images_ok = len(images_missing) == 0
        checks.append({"name": "镜像", "passed": images_ok, "detail": f"缺失: {', '.join(images_missing)}" if images_missing else "全部存在"})

    finally:
        client.close()

    # 汇总
    all_passed = all(c["passed"] for c in checks)
    critical_fail = not mem_ok or not docker_ok or not disk_ok
    recommendation = "block" if critical_fail else "warn" if not all_passed else "proceed"

    # AI 分析
    summary = f"资源检查: {'通过' if all_passed else '有风险'}"
    if provider:
        sys_prompt = "你是一名 SRE 专家，分析部署前置检查结果。输出 JSON: {\"passed\": true/false, \"summary\": \"一句话总结\", \"suggestion\": \"建议\"}"
        user_prompt = f"检查项: {json.dumps(checks, ensure_ascii=False)}\nestimated_mb={estimated_mb} mem_avail={mem_avail}\n请分析是否可部署。"
        try:
            resp = call_llm(provider, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ], timeout_override=15)
            if not resp.get("error"):
                content = resp["choices"][0]["message"]["content"]
                ai = _extract_json(content) or {}
                if ai.get("summary"):
                    summary = ai["summary"]
        except Exception as _exc15:
            logger.warning("[except:pass] Exception: %s", _exc15, exc_info=True)

    return {"passed": all_passed, "checks": checks, "recommendation": recommendation, "summary": summary}


