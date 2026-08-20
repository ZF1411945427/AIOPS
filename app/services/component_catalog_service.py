"""组件应用商店服务 (Bitnami Catalog 风格) — 拆分后门面。

子模块:
  - component_catalog_data.py   纯数据常量
  - component_catalog_render.py 配方渲染/脚本生成
  - component_catalog_ai.py     纯 AI 辅助
  - component_catalog_ops.py    CRUD/安装/部署/SSH/健康检查
本文件保留流式部署编排(deploy_stream)等核心, 并 re-export 全部公共符号。
"""
import json
import re
import socket
import base64
import time
import threading
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models import Asset, ComponentCatalog, ComponentInstall

import logging
logger = logging.getLogger(__name__)

# ─── 从子模块 re-export(门面) ───
from app.services.component_catalog_data import (  # noqa: F401
    _BUILTIN_COMPONENTS, _OFFLINE_PUBLIC_SOURCES, _MIN_CVE_RULES,
    _HEALTH_CMDS, _CONFIG_FILES, _NATIVE_VERIFY, _SHELL_TRANSIENT_VARS,
)
from app.services.component_catalog_render import (  # noqa: F401
    build_default_compose, _param_value, render_compose, _offline_native_block,
    _inject_native_params, _shell_quote, _stop_service, native_deploy,
    seed_builtin_components,
)
from app.services.component_catalog_ai import (  # noqa: F401
    _ai_decision_options, _ai_intent_to_command, _contains_cn, _ai_generate_plan,
    _plan_to_visual_steps, _plan_step_kind, _plan_to_steps, _apply_plan_params,
    _get_deploy_provider, _extract_assignments, _native_step_wrapper, safe_json_parse,
    _ai_autonomous_decision, _rule_deploy_tip, _ai_deploy_tip, _ai_deploy_diagnosis,
    _ai_final_report, _build_install_report_key_points,
)
from app.services.component_catalog_ops import (  # noqa: F401
    list_components, get_component, _comp_to_dict, get_deploy_render,
    list_installs, _resolve_pending_decision, get_install, _install_to_dict,
    record_install, update_install_status, _append_install_event,
    _set_pending_decision_install, get_install_events, delete_install,
    _apply_docker_proxy, _apply_native_proxy, _native_proxy_prefix, deploy_docker,
    component_to_asset, _asset_brief, _exec_ssh, check_vuln, _trivy_scan,
    _probe_version, ai_analyze, _build_component_key_points, get_stats,
    check_config, check_health, full_health_check, batch_full_check,
    _build_full_health_key_points, generate_ai_health_report,
    _build_component_report_key_points,
)

# 部署取消标记容器: {install_id: threading.Event} (流式部署状态, 留在门面)
_DEployStop = {}

# ─── register_deploy_stop (原 L2366-2368) ───
def register_deploy_stop(install_id: int):
    _DEployStop[install_id] = threading.Event()
    return _DEployStop[install_id]


# ─── cancel_deploy (原 L2371-2381) ───
def cancel_deploy(install_id: int) -> bool:
    """请求停止指定 install 的部署(幂等)。返回是否存在该部署流。"""
    ev = _DEployStop.get(install_id)
    if ev:
        ev.set()
        return True
    return False


# 部署决策门控注册表: {install_id: {"id": decision_id, "event": Event, "result": None}}
_DECISION_REG = {}


# ─── register_decision (原 L2384-2389) ───
def register_decision(install_id: int, decision_id: str) -> dict:
    entry = _DECISION_REG.setdefault(install_id, {"id": decision_id, "event": threading.Event(), "result": None})
    entry["id"] = decision_id
    entry["event"] = threading.Event()
    entry["result"] = None
    return entry


# ─── resolve_decision (原 L2392-2399) ───
def resolve_decision(install_id: int, decision_id: str, choice: str) -> bool:
    """前端回传决策选择: 写入结果并唤醒等待的部署流。返回是否命中。"""
    entry = _DECISION_REG.get(install_id)
    if not entry or entry.get("id") != decision_id:
        return False
    entry["result"] = choice
    entry["event"].set()
    return True


# ─── submit_install_decision (原 L2402-2409) ───
def submit_install_decision(db: Session, install_id: int, decision_id: str, choice: str) -> dict:
    """HTTP 决策提交(组件商店): 尝试唤醒内存注册表, 并清空 DB 持久化决策卡片。
    返回 {ok, message}。"""
    hit = resolve_decision(install_id, decision_id, choice)
    _set_pending_decision_install(db, install_id, None)
    if hit:
        return {"ok": True, "message": "决策已提交"}
    return {"ok": False, "message": "该安装记录当前无进行中的部署, 无需决策"}


# ─── generate_install_report (原 L2964-3148) ───
def generate_install_report(db: Session, install_id: int, template_id: int = 0) -> dict:
    """为组件商店安装记录生成**可直接交付**的完整 AI 部署报告(对标 AI 自动部署页的可交付版报告)。

    读取安装记录 + 组件 catalog + 部署事件日志, 让 AI 产出:
    executive_summary / 架构 / 启停命令 / 部署路径 / 端口 / 访问方式 / 登录信息 /
    环境 / 时间线 / 验证 / 风险 / 建议 / 问题 等字段; AI 不可用时给结构化兜底。
    template_id: 知识库文档 ID, 可选。若指定则以其内容作为报告风格/结构参考。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    item = _install_to_dict(r, db)
    comp = get_component(db, r.component_id) or {
        "name": r.component_name, "display_name": r.component_name,
        "default_port": r.port or 0, "docker_image": "", "category": "",
    }
    events = get_install_events(db, install_id) or []
    # 从事件日志抽取: 预检/阶段/日志/决策/验证/报告
    log_lines = []
    preflight_passed = None
    verification_passed = None
    ai_decisions = 0
    health_overall = None
    for ev in events:
        t = ev.get("type")
        if t == "log" or t == "output":
            log_lines.append(ev.get("message") or "")
        elif t == "precheck":
            if preflight_passed is None:
                preflight_passed = True
            if not ev.get("ok"):
                preflight_passed = False
        elif t == "decision" or t == "decide":
            ai_decisions += 1
        elif t == "verify" or (t == "status" and "验证" in str(ev.get("message", ""))):
            _m = str(ev.get("message", ""))
            if "通过" in _m or "UP" in _m or "LISTEN" in _m:
                verification_passed = True
        elif t == "report":
            if ev.get("overall_status"):
                health_overall = ev.get("overall_status")
    if r.health_status:
        health_overall = health_overall or r.health_status

    def count_status(s):
        return sum(1 for ev in events if ev.get("type") == "complete" and ev.get("status") == s)

    succeeded = 1 if r.status == "succeeded" else 0
    failed = 1 if r.status in ("failed", "stopped") else 0

    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    deploy_info = {
        "组件": comp.get("display_name") or comp.get("name"),
        "目标机": (asset.name if asset else item["asset_name"]),
        "IP": (asset.ip if asset else ""),
        "部署方式": r.deploy_type,
        "部署路径": r.deploy_path or "(默认)",
        "端口": r.port or comp.get("default_port") or 0,
        "命名空间": r.name_space or "-",
        "Release": r.release_name or "-",
        "结果": r.status,
    }
    attached = []
    # 从日志推断访问方式 / 启停命令 / 服务端口
    access = []
    start_stop = []
    ports = []
    if asset and getattr(asset, "ip", None):
        _ip = str(asset.ip)
        if r.port:
            access.append(f"{comp.get('name')}: {_ip}:{r.port}")
            ports.append(f"{r.port} (应用端口)")
    if r.deploy_type == "docker":
        start_stop = ["docker compose up -d (启动)", "docker compose down (停止)"]
    elif r.deploy_type == "native":
        start_stop = [f"启动: nohup {r.deploy_path or '/opt'}/bin/kafka-server-start.sh config/kraft/server.properties",
                      "停止: 结束 kafka.Kafka 进程 (pkill -f kafka.Kafka)"]
    elif r.deploy_type == "helm":
        start_stop = [f"helm upgrade --install {r.release_name or comp.get('name')} {comp.get('helm_chart')} -n {r.name_space or 'default'}",
                      "helm uninstall {0} -n {1}".format(r.release_name or comp.get('name'), r.name_space or 'default')]
    deploy_paths = [r.deploy_path or comp.get("name")] if r.deploy_path else [f"/opt/{comp.get('name')}"]
    login_info = [{"user": "root", "via": f"ssh root@{asset.ip if asset and asset.ip else ''}"}] if asset and asset.ip else []

    def _join_logs(limit=2000):
        return "\n".join(log_lines)[-limit:]

    provider = _get_deploy_provider(db)
    title = f"{comp.get('display_name') or comp.get('name')} 部署报告"
    base = {
        "title": title, "status": r.status, "deployed_at": (r.created_at.isoformat() if r.created_at else ""),
        "deploy_count": 1, "deploy_type": r.deploy_type,
        "executive_summary": f"{comp.get('display_name') or comp.get('name')} 于目标机完成部署, 状态: {r.status}。",
        "kpi": {
            "total_steps": 5, "succeeded_steps": succeeded, "failed_steps": failed, "skipped_steps": 0,
            "total_assets": 1, "preflight_passed": preflight_passed, "verification_passed": verification_passed,
            "ai_decisions": ai_decisions,
        },
        "deployment_architecture": "", "start_stop_commands": start_stop,
        "deploy_paths": deploy_paths, "service_ports": ports, "access_methods": access,
        "login_info": login_info, "environment": deploy_info, "timeline": "",
        "verification": "", "risk_assessment": "", "recommendations": [], "issues": [],
        "raw_log": _join_logs(4000),
    }

    def _persist(report: dict) -> dict:
        """把报告写入 DB(report_json 列)持久化, 供下次打开直接读取, 不重复调 AI。"""
        report.setdefault("summary_block", _build_install_report_key_points(report))
        try:
            row = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
            if row:
                row.report_json = json.dumps(report, ensure_ascii=False, default=str)
                row.updated_at = datetime.now()
                db.commit()
        except Exception as _exc8:
            logger.warning("[except:pass] Exception: %s", _exc8, exc_info=True)
        return report

    if not provider:
        return _persist(base)
    from app.services.agent_service import call_llm
    # ▼ 加载部署报告模板(知识库文档, 可选)
    template_content = ""
    if template_id:
        try:
            from app.models import KbDocument
            tmpl = db.query(KbDocument).filter(KbDocument.id == template_id).first()
            if tmpl and tmpl.content:
                template_content = tmpl.content[:3000]
        except Exception:
            pass
    system = (
        "你是资深 SRE 部署专家。基于以下**单个组件**的已部署记录, 生成一份**可直接交付给客户/团队**的正式部署报告。"
        "语言专业、结论清晰、可行动。严格输出 JSON, 字段如下(所有字段都必须提供, 数组缺省给空数组, 字符串缺省给空串):\n"
        "{\"executive_summary\":\"执行摘要(2-4句, 含结论)\","
        "\"deployment_architecture\":\"部署架构说明\","
        "\"start_stop_commands\":[\"启停命令\"],"
        "\"deploy_paths\":[\"部署/数据目录\"],"
        "\"service_ports\":[\"服务端口\"],"
        "\"access_methods\":[\"访问方式\"],"
        "\"login_info\":[{\"user\":\"账号\",\"via\":\"登录方式\"}],"
        "\"environment\":{\"键\":\"值\"},"
        "\"timeline\":\"部署时间线概述\","
        "\"verification\":\"验证结论(端口/进程探测)\","
        "\"risk_assessment\":\"风险评估\","
        "\"recommendations\":[\"改进建议\"],"
        "\"issues\":[{\"severity\":\"low|medium|high\",\"description\":\"问题\",\"resolution\":\"处理\",\"status\":\"resolved|pending\"}]}"
    )
    if template_content:
        system += (
            "\n\n## 部署报告风格模板(参考此模板的组织结构/章节顺序/措辞风格, 数据仍来自本次部署):\n"
            f"{template_content}"
        )
    user = (
        f"部署信息: {json.dumps(deploy_info, ensure_ascii=False)}\n"
        f"体检状态: {health_overall or 'N/A'}; 预检通过: {preflight_passed}; 验证通过: {verification_passed}; "
        f"AI决策次数: {ai_decisions};\n"
        f"部署日志摘录:\n{_join_logs(2000)}"
    )
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        merged = dict(base)
        merged.update(parsed)
        merged["kpi"].update({k: base["kpi"].get(k) for k in
                              ("total_steps", "succeeded_steps", "failed_steps", "skipped_steps",
                               "total_assets", "preflight_passed", "verification_passed", "ai_decisions")})
        merged.setdefault("start_stop_commands", start_stop)
        merged.setdefault("deploy_paths", deploy_paths)
        merged.setdefault("service_ports", ports)
        merged.setdefault("access_methods", access)
        merged.setdefault("login_info", login_info)
        merged.setdefault("environment", deploy_info)
        merged.setdefault("recommendations", [])
        merged.setdefault("issues", [])
        merged["title"] = title
        merged["status"] = r.status
        merged["deployed_at"] = base["deployed_at"]
        return _persist(merged)
    except Exception:
        return _persist(base)


# ─── deploy_stream (原 L3169-3789) ───
def deploy_stream(db, asset, comp: dict, port: int, deploy_path: str,
                  deploy_type: str = "docker", http_proxy: str = "", https_proxy: str = "",
                  no_proxy: str = "", compose: str = "", namespace: str = "default",
                  release: str = "", install_id: int = 0, params: dict = None,
                  use_offline: bool = False, plan: str = ""):
    """生成器式实时组件部署(对标 K8s 集群部署 WS, 逐步 yield 事件)。

    yield 事件: {type: status/phase/log/ai/complete/error}
    - docker/native: 真实执行, 分阶段逐步推送日志 + 阶段后 AI 建议
    - helm/ha: 虚拟阶段占位 + AI 建议(依赖 K8s/helm 引擎)
    params: 组件级定制参数 {key:value}, 会真实注入 compose/脚本。
    use_offline: 可选用离线私有仓库(有默认 registry 时 docker 镜像改走私有仓库)。
    plan: 前端已确认并展示的部署方案文本(AI 生成方案后, 部署流复用它而不重新生成,
          native 时按方案步骤逐步执行, 保证「所见即所部署」)。
    """
    params = params or {}
    name = comp["name"]
    image = comp.get("docker_image") or ""
    asset_name = asset.name if asset else f"资产#{getattr(asset, 'id', '?')}"
    connbuf = []

    def cancelled():
        ev = _DEployStop.get(install_id)
        return bool(ev and ev.is_set())

    def log(msg, t="log"):
        connbuf.append(msg)
        return {"type": t, "node": asset_name, "message": msg}

    def ai(stage):
        tip = _ai_deploy_tip(db, stage, name, asset_name, "\n".join(connbuf[-8:]))
        return {"type": "ai", **tip}

    def diag(error_hint="", phase=""):
        """失败时用 AI 深度诊断根因 + 修复步骤(自我察觉)。返回 ai 事件。"""
        diag_data = _ai_deploy_diagnosis(db, name, asset_name, deploy_type,
                                         "\n".join(connbuf[-40:]), error_hint=error_hint)
        diag_data["stage"] = "diagnosis"
        if phase:
            diag_data["phase"] = phase
        return {"type": "ai", **diag_data}

    def final_report(status, log_summary, health=None):
        """生成可直接交付的 AI 部署报告(report 事件)。"""
        rep = _ai_final_report(db, comp, asset, install_id, deploy_type, status, log_summary, health)
        return {"type": "report", **rep}

    def ask_decision(question, context=""):
        """AI 决策门控: 生成 2 个 AI 方案 + 用户自定义, yield decide 事件后阻塞等前端选择。
        返回用户选择内容(字符串); 取消/停止时返回空串。
        用法: choice = yield from ask_decision(...)"""
        import uuid
        _dtype = deploy_type
        _dsys = (pc or {}).get("system") or ""
        options = _ai_decision_options(db, name, asset_name, context, question,
                                       deploy_type=_dtype, system=_dsys,
                                       deploy_path=deploy_path, port=port)
        decision_id = str(uuid.uuid4())
        entry = register_decision(install_id, decision_id)
        _decision_card = {
            "id": decision_id, "install_id": install_id,
            "question": question, "options": options, "free": True,
            "node": asset_name, "stage": "decision",
        }
        _set_pending_decision_install(db, install_id, _decision_card)
        yield {"type": "decide", "id": decision_id, "install_id": install_id,
               "question": question, "options": options, "free": True,
               "node": asset_name, "stage": "decision"}
        while not entry["event"].is_set():
            if cancelled():
                _set_pending_decision_install(db, install_id, None)
                return ""
            entry["event"].wait(0.5)
        _set_pending_decision_install(db, install_id, None)
        return entry.get("result") or ""

    def exec_choice(choice):
        """执行用户在决策中选择的方案/自定义意图:
        - AI 现成命令直接执行;
        - 用户自定义中文意图 → 先让 AI 转成命令再执行。
        返回 (ok, out)。"""
        raw = (choice or "").strip()
        if not raw:
            return (True, "")
        cmd = _ai_intent_to_command(db, name, raw, "\n".join(connbuf[-12:]))
        yield log(f"按所选方案执行: {cmd[:200]}")
        return _exec_ssh(asset, f"OUT=$({cmd} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC", timeout=300)

    def ai_handle_failure(question, out, retry_cmd=None, risk_level="medium", max_auto=2):
        """AI 自主处置闭环: 步骤失败时让 AI 自选 fix/retry/skip/rollback。
        - 非高危: AI 自动执行(fix 跑修复命令 / retry 重跑 / skip 跳过), 仅回退到 ask_decision 当 AI 不可用
        - 高危(rollback 或 risk_level=high): 暂停走 ask_decision 人工确认(高危操作铁律)
        返回: {decision, out}  (out 为处置后的输出/日志); decision 为 fix/retry/skip/rollback/''(用户中断)
        """
        history = []
        last_out = out
        for attempt in range(1, max_auto + 1):
            _dsys = (pc or {}).get("system") or ""
            dec = _ai_autonomous_decision(
                db, name, asset_name, deploy_type, _dsys, question,
                output=last_out, history=history, risk_level=risk_level,
                deploy_path=deploy_path, port=port)
            if dec.get("needs_confirm") or not dec.get("decision"):
                # 高危/不明确 → 人工确认兜底
                choice = yield from ask_decision(question + ("\n⚠ 高危操作已暂停等待确认" if dec.get("needs_confirm") else ""), last_out)
                if not choice:
                    return {"decision": "", "out": last_out}
                yield log(f"人工确认方案: {choice[:120]}")
                _ok, _o = yield from exec_choice(choice)
                last_out = _o or last_out
                history.append({"attempt": attempt, "decision": "human", "result": "ok" if _ok else "fail"})
                return {"decision": "" if not _ok else "fix", "out": last_out}
            decision = dec["decision"]
            reason = dec.get("reason", "")
            yield {"type": "ai", "ai_generated": True, "stage": "decision",
                   "message": f"🤖 AI 自主决策: {decision} — {reason}",
                   "summary": f"AI 自主处置: {decision}({reason})", "decision": decision, "install_id": install_id}
            if decision == "skip":
                return {"decision": "skip", "out": last_out}
            if decision == "retry" and retry_cmd:
                yield log(f"🤖 AI 选择重试(第{attempt}次)...")
                ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                yield log(out3)
                last_out = out3
                history.append({"attempt": attempt, "decision": "retry", "result": "ok" if ok3 else "fail"})
                if ok3:
                    return {"decision": "retry", "out": out3}
                continue
            if decision == "fix":
                fcs = dec.get("fix_commands") or []
                if fcs:
                    fix_ok = True
                    for fc in fcs:
                        # ▼ 高危修复命令黑名单: 遏制 AI 臆造/误用破坏性操作(项目高危铁律)
                        _blocked = re.search(r"\b(rm\s+-rf|mkfs|fdisk|dd\s+of=|wipefs|:\(\)\{)", fc)
                        if _blocked:
                            yield log(f"⛔ AI 修复命令含高危操作, 已拦截: {fc[:120]}")
                            fix_ok = False
                            continue
                        yield log(f"🤖 AI 执行修复: {fc[:160]}")
                        fok, fout = _exec_ssh(asset, f"OUT=$({fc} 2>&1); RC=$?; echo \"$OUT\" | tail -20; echo __RC__=$RC", timeout=300)
                        yield log(fout)
                        if not fok:
                            fix_ok = False
                    last_out = fout if 'fout' in dir() else last_out
                    history.append({"attempt": attempt, "decision": "fix", "result": "ok" if fix_ok else "fail"})
                    if fix_ok and retry_cmd:
                        ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                        yield log(out3)
                        last_out = out3
                        if ok3:
                            return {"decision": "fix", "out": out3}
                    if fix_ok:
                        return {"decision": "fix", "out": last_out}
                    # ▼ fix 失败(含被拦截) → 不空转, 直接用部署脚本重跑兜底
                    if retry_cmd:
                        yield log("🤖 AI 修复未生效, 重跑部署脚本兜底")
                        ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                        yield log(out3)
                        last_out = out3
                        if ok3:
                            return {"decision": "fix", "out": out3}
                    continue
                # 无修复命令 → 落到 retry
                if retry_cmd:
                    yield log("🤖 AI 无具体修复命令, 改为重试")
                    ok3, out3 = _exec_ssh(asset, retry_cmd, timeout=300)
                    yield log(out3)
                    last_out = out3
                    history.append({"attempt": attempt, "decision": "retry", "result": "ok" if ok3 else "fail"})
                    if ok3:
                        return {"decision": "retry", "out": out3}
                    continue
            # rollback 或其它 → 人工确认
            choice = yield from ask_decision(question + "\n⚠ 需回滚/无法自动处理, 请选择方案或输入自定义命令", last_out)
            if not choice:
                return {"decision": "", "out": last_out}
            yield log(f"人工确认方案: {choice[:120]}")
            _ok, _o = yield from exec_choice(choice)
            last_out = _o or last_out
            history.append({"attempt": attempt, "decision": "human", "result": "ok" if _ok else "fail"})
            return {"decision": "fix" if _ok else "", "out": last_out}
        # 多次自动仍失败 → 人工确认兜底
        choice = yield from ask_decision(question + "\n⚠ AI 多次自动处置仍未成功, 请人工选择", last_out)
        if not choice:
            return {"decision": "", "out": last_out}
        yield log(f"人工确认方案: {choice[:120]}")
        _ok, _o = yield from exec_choice(choice)
        return {"decision": "fix" if _ok else "", "out": _o or last_out}

    yield {"type": "status", "status": "running", "message": f"开始部署 {comp['display_name']} ({deploy_type})"}

    # ── 预检 ──
    yield {"type": "phase", "step": 0, "title": "阶段0/5 预检环境"}
    yield log(f"目标机: {asset_name} | 组件: {name} | 方式: {deploy_type}")
    if cancelled():
        yield {"type": "ai", **{"ai_generated": False, "stage": "stop", "summary": "部署已取消"}}
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return

    # 逻辑预检(对标 K8s precheck), 逐项推 check 事件给前端预检面板
    pc = precheck_deploy(db, asset, comp, deploy_type=deploy_type, port=port,
                         http_proxy=http_proxy, https_proxy=https_proxy, no_proxy=no_proxy,
                         deploy_path=deploy_path, params=params)
    for _c in pc.get("checks", []):
        yield {"type": "precheck", "name": _c.get("name"), "ok": _c.get("ok"), "message": _c.get("message")}
    yield log(f"预检: {'通过' if pc.get('ok') else '存在 ' + str(len(pc.get('issues', []))) + ' 项问题'}")
    yield ai("preflight")
    if not pc.get("ok"):
        yield {"type": "error", "message": "预检未通过: " + "; ".join(pc.get("issues", []) or ["未知问题"])}
        yield {"type": "complete", "status": "failed", "message": f"预检失败: {comp['display_name']}"}
        return

    # ── 阶段1: 代理注入(docker → docker daemon; native → dnf/yum) ──
    if deploy_type == "docker" and (http_proxy or https_proxy):
        if cancelled():
            yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
            return
        yield {"type": "phase", "step": 1, "title": "阶段1/5 注入 Docker 代理"}
        yield log(f"写入代理 {http_proxy or https_proxy} (no_proxy={no_proxy or '默认'})...")
        plog = _apply_docker_proxy(asset, http_proxy, https_proxy, no_proxy)
        if plog:
            yield log(plog)
        yield ai("proxy")
    elif deploy_type == "native" and (http_proxy or https_proxy):
        # ▼ 修复: native 部署也复用用户已配置的网络代理, 使 yum/dnf install 走代理
        if cancelled():
            yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
            return
        yield {"type": "phase", "step": 1, "title": "阶段1/5 注入 Native(yum/dnf) 代理"}
        yield log(f"写入 native 代理 {http_proxy or https_proxy} (no_proxy={no_proxy or '默认'})...")
        nlog = _apply_native_proxy(asset, http_proxy, https_proxy, no_proxy)
        if nlog:
            yield log(nlog)
        yield ai("proxy")
    else:
        yield {"type": "phase", "step": 1, "title": "阶段1/5 网络/代理(跳过或虚拟)"}
        yield log("未配置代理, 跳过 docker daemon 代理注入" if deploy_type == "docker" else f"{deploy_type} 方式忽略代理配置")

    # ── 阶段2: 生成部署方案(基于预检得到的系统类型, 优先 AI 生成) ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 2, "title": "阶段2/5 生成部署方案(AI)"}
    _sys = (pc or {}).get("system") or ""
    # 前端已确认展示过方案 → 直接复用, 不重新生成(保证所见即所部署);
    # 否则(直接点击部署未生成方案)在部署流内补生成
    if plan and plan.strip():
        plan_text = plan
        plan_data = {"ai_generated": True, "system": _sys,
                     "title": f"{comp['display_name']} 部署方案(已确认)",
                     "plan": plan_text}
    else:
        plan_data = _ai_generate_plan(db, comp, deploy_type, _sys, target=asset.ip or "", port=port, deploy_path=deploy_path, params=params)
        plan_text = plan_data.get("plan", "") or ""
    yield {"type": "plan", **plan_data}
    yield {"type": "ai", "message": f"🤖 AI 生成部署方案({deploy_type} / 系统: {_sys or 'unknown'})"}
    for _ln in (plan_text or "").splitlines():
        yield log(_ln)
    # docker 仍然需要 compose 用于执行(有定制参数则按模板渲染, 否则用默认)
    offline_registry_url = ""
    offline_insecure = False
    if deploy_type == "docker":
        offline_image = ""
        if use_offline:
            from app.services.offline_repo_service import resolve_offline_image as _roi
            _ri = _roi(db, image, True) if image else {"image": "", "registry_url": "", "is_insecure": False}
            offline_image = _ri.get("image") or ""
            offline_registry_url = _ri.get("registry_url") or ""
            offline_insecure = bool(_ri.get("is_insecure"))
            if offline_image and offline_registry_url:
                yield log(f"🟢 使用离线私有仓库镜像: {offline_image}")
        if params:
            compose = render_compose(comp, params, port, offline_image=offline_image)
        else:
            compose = compose or (comp.get("compose_yaml") or build_default_compose(name, offline_image or image, port))

    # ── 阶段3: 执行部署 ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 3, "title": "阶段3/5 执行部署"}
    if deploy_type == "docker":
        yield log(f"docker compose up -d (路径: {deploy_path}) ...")
        prep = ""
        if offline_insecure and offline_registry_url:
            _dj_url = offline_registry_url.replace("/", "\\/").replace('"', '\\"')
            prep = (
                f"DK=/etc/docker/daemon.json; "
                f"if ! grep -q '{offline_registry_url}' \"$DK\" 2>/dev/null; then "
                f"  mkdir -p /etc/docker; "
                f"  if ! python3 -c \"import json;d=json.load(open('$DK'));d.setdefault('insecure-registries',[]).append('{offline_registry_url}');json.dump(d,open('$DK','w'),indent=2)\" 2>/dev/null; then "
                f"    echo '{{\"insecure-registries\":[\"{_dj_url}\"]}}' > \"$DK\"; "
                f"  fi; "
                f"  systemctl restart docker 2>/dev/null || service docker restart 2>/dev/null || true; "
                f"fi; "
            )
            yield log(f"🟢 已为目标机配置 insecure-registry: {offline_registry_url}")
        ok, out = _exec_ssh(asset, (
            f"{prep}"
            f"mkdir -p '{deploy_path}'; "
            f"cat > '{deploy_path}/docker-compose.yml' <<'AIOPS_COMPOSE'\n{compose}\nAIOPS_COMPOSE\n"
            f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; "
            f"OUT=$(docker compose up -d 2>&1); RC=$?; "
            f"echo \"$OUT\" | tail -30; echo __RC__=$RC"
        ), timeout=300)
        yield log(out)
        if not ok:
            yield diag("docker compose up 失败", phase="执行部署")
            # ▼ AI 自主决策闭环: AI 自选 fix/retry/skip/rollback, 高危才等人确认, 自动重试
            retry_up = f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; OUT=$(docker compose up -d 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC"
            _ad = yield from ai_handle_failure(
                f"{name} docker compose up 失败, AI 自主处置(自动执行修复/重试)",
                out, retry_cmd=retry_up, risk_level="medium", max_auto=2)
            if _ad.get("decision") == "":
                yield {"type": "error", "message": "docker compose up 失败"}
                yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                return
            if _ad.get("decision") == "skip":
                yield log("AI 判定跳过 compose 启动(继续后续流程)")
            else:
                # 处置后重新校验容器是否起来 (健康门禁)
                ok, out = _exec_ssh(asset, (
                    f"cd '{deploy_path}'; docker compose ps --format '{{{{.Name}}}} {{{{.Status}}}}' 2>/dev/null | head -10"
                ), timeout=120)
                yield log(out or "(无容器状态)")
                _o = out.lower()
                _up = ("up" in _o or "running" in _o or "healthy" in _o or "ok" in _o) and "exit" not in _o
                if not ok or not _up:
                    yield {"type": "error", "message": "docker compose 容器未成功启动"}
                    yield {"type": "complete", "status": "failed", "message": f"部署失败: 容器未启动 {(out or '')[:200]}"}
                    return
        yield ai("deploy")
    elif deploy_type == "native":
        # ▼ 无论方案来自前端确认或部署流内生成, 一律按方案步骤执行(AI 方案驱动, 所见即所部署);
        #   失败时交给 AI 自主决策闭环(fix/retry/skip/rollback, 高危/回滚才等人确认)。
        _steps = _plan_to_steps(plan_text, deploy_type) if (plan_text or "").strip() else []
        if _steps:
            yield log(f"⚠ 按已确认部署方案执行, 共 {len(_steps)} 步; 逐步骤执行, 每步失败 AI 即时处置...")

            # ── 跨步骤 shell 变量持久化: 预抽取所有步骤的赋值行写入 vars 文件 ──
            #   (替代原先「整段合并为 set -e 大脚本」的方式, 逐步骤独立执行但变量上下文保持)
            _vars_file = f"/tmp/.aiops_vars_{install_id}"
            _assign_map = {}
            _xp = _native_proxy_prefix(http_proxy, https_proxy, no_proxy)
            if _xp:
                _assign_map["__native_proxy__"] = _xp      # 多变量 export 行, 原样保留
                yield log(f"▶ 注入 native 代理环境: {http_proxy or https_proxy}")
            for _cmd0 in _steps:
                _cmd = _apply_plan_params(_cmd0, params)
                for _al in _extract_assignments(_cmd):
                    _mm = re.match(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", _al)
                    if _mm:
                        _assign_map[_mm.group(1)] = _al
            _init_vars = "\n".join(_assign_map.values()) if _assign_map else ""
            if _init_vars.strip():
                _exec_ssh(asset, f"cat > {_vars_file} <<'AIOPS_VARS'\n{_init_vars}\nAIOPS_VARS", timeout=30)
            else:
                _exec_ssh(asset, f"rm -f {_vars_file}", timeout=30)

            # ── 预置步骤(目标机工具链补齐 / redis 配置路径兜底), 也逐步骤执行 ──
            _pre_steps = []
            if (http_proxy or https_proxy or "").strip():
                _pre_steps.append((
                    "检测并自动补齐缺失工具(curl/tar)",
                    "for _t in curl tar; do "
                    "command -v $_t >/dev/null 2>&1 || "
                    "(yum install -y $_t >/dev/null 2>&1 || dnf install -y $_t >/dev/null 2>&1 || true); "
                    "done",
                ))
            if name == "redis":
                _pre_steps.append((
                    "修正 redis 配置文件路径兜底(/etc/redis/redis.conf)",
                    "[ -f /etc/redis/redis.conf ] && { "
                    "[ -f /etc/redis.conf ] || cp /etc/redis/redis.conf /etc/redis.conf; "
                    "find / -name 'redis*.conf' -path '*/redis/*' 2>/dev/null | head -1; "
                    "} || true",
                ))
            for _pt, _pc in _pre_steps:
                if cancelled():
                    yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
                    return
                yield log(f"▶ {_pt}")
                _ok, _out = _exec_ssh(asset, _native_step_wrapper(_pc, install_id), timeout=300)
                yield log(_out)
                if not _ok:
                    yield log(f"⚠ 预置步骤未完全成功({_pt}), 继续后续(尽力而为)")

            # ── ★ 真正逐步骤执行: 每步独立 SSH 执行 → 检查返回码 → 失败立即 AI 决策修正 ──
            for _si, _cmd0 in enumerate(_steps):
                if cancelled():
                    yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
                    return
                _cmd = _apply_plan_params(_cmd0, params)
                # ▼ 离线二次强制校验: native 安装步骤禁止公网源
                if use_offline:
                    _nb = _offline_native_block(_cmd)
                    if _nb:
                        yield log(f"⛔ {_nb}")
                        yield {"type": "error", "message": _nb}
                        yield {"type": "complete", "status": "failed", "message": _nb}
                        return
                yield log(f"▶ 步骤 {_si + 1}/{len(_steps)}: {_cmd[:160]}")
                _step_wrap = _native_step_wrapper(_cmd, install_id)
                ok, out = _exec_ssh(asset, _step_wrap, timeout=600)
                yield log(out)
                if not ok:
                    # ▼ 该步骤失败 → 立即 AI 诊断 + 自主决策闭环(fix/retry/skip/rollback, 高危/回滚才人工确认)
                    #   与之前「整串脚本跑完才事后处理」不同: 每步失败即时处置, 修复后重跑该步。
                    yield diag(f"步骤 {_si + 1}/{len(_steps)} 执行失败({name}): {_cmd[:120]}", phase="执行部署")
                    _ad = yield from ai_handle_failure(
                        f"{name} 部署步骤 {_si + 1}/{len(_steps)} 执行失败: {_cmd[:120]}",
                        out, retry_cmd=_step_wrap, risk_level="medium", max_auto=2)
                    if not _ad.get("decision") or _ad.get("decision") == "":
                        yield {"type": "error", "message": f"native 执行失败(步骤 {_si + 1}): {_cmd[:120]}"}
                        yield {"type": "complete", "status": "failed", "message": f"部署失败(步骤 {_si + 1}): {(out or '')[:200]}"}
                        return
                    if _ad.get("decision") == "skip":
                        yield log(f"⚠ AI 判定跳过步骤 {_si + 1}(修复无需/无法, 继续后续)")
                        continue
                    yield log(f"✓ 步骤 {_si + 1} 已由 AI 处置完成({_ad.get('decision')})")
            # 临时文件清理(每步的 ._aiops_step_*.sh / ._aiops_out_* 由各 wrapper 内的 `bash > out_f` 自然覆盖,
            # vars 文件在本次部署完成后删除)
            _exec_ssh(asset, f"rm -f {_vars_file} 2>/dev/null || true", timeout=30)
            yield ai("deploy")
        else:
            # ▼ 方案无可用命令时回退到组件显式原生脚本/系统包管理器
            # 优先使用组件显式配置的原生安装脚本(native_script, 如 Kafka 下载二进制/KRaft);
            # 仅当未配置 native_script 时才按系统类型回退到通用系统包管理器(yum/apt install -y {name})
            _sys_n = (pc or {}).get("system") or ""
            _native_script = comp.get("native_script") or ""
            install_cmd = ""
            if _native_script:
                install_cmd = _native_script
            elif _sys_n in ("debian", "ubuntu"):
                install_cmd = f"apt-get update && apt-get install -y {name}"
            elif _sys_n in ("rhel", "centos", "alma", "rocky"):
                install_cmd = f"(command -v dnf >/dev/null 2>&1 && dnf install -y {name}) || yum install -y {name}"
            if not install_cmd and not _native_script and not _sys_n:
                yield diag("组件未提供原生安装脚本, 无法执行 native 部署", phase="执行部署")
                yield {"type": "error", "message": "组件未提供原生安装脚本"}
                yield {"type": "complete", "status": "failed", "message": "部署失败: 无原生安装脚本"}
                return
            script = install_cmd or _native_script
            script = _inject_native_params(script, comp, params, deploy_path=deploy_path)
            # ▼ else 分支补齐基础工具(curl/tar/wget, if 分支在 pre_steps 里做):
            #   缺 tar 会导致 Kafka 等下载 tgz 后无法解压; 缺 wget 也是下载兜底缺失。
            #   幂等: 已有则跳过; yum/dnf 失败不中断后续(尽力而为)。
            #   ⚡ 注意: 工具安装必须在 proxy 注入之后, 否则 yum 无代理连不上 mirrors.rockylinux.org
            _xp = _native_proxy_prefix(http_proxy, https_proxy, no_proxy)
            _tool_fix = (
                "for _t in curl tar wget; do command -v $_t >/dev/null 2>&1 || "
                "(yum install -y $_t >/dev/null 2>&1 || dnf install -y $_t >/dev/null 2>&1 || true); done; "
            )
            if _xp:
                # proxy 在前, 工具安装在中, 主脚本在后
                script = _xp + " && " + _tool_fix + script
            else:
                script = _tool_fix + script
            # ▼ 离线二次强制校验: native 安装脚本禁止公网源
            _nb = _offline_native_block(script) if use_offline else ""
            if _nb:
                yield log(f"⛔ {_nb}")
                yield {"type": "error", "message": _nb}
                yield {"type": "complete", "status": "failed", "message": _nb}
                return
            yield log(f"按系统类型({_sys_n or 'unknown'})执行安装: {script[:120]}")
            ok, out = _exec_ssh(asset, f"OUT=$({script} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC", timeout=400)
            yield log(out)
            if not ok:
                yield diag("native 安装脚本执行返回非零, 部署失败", phase="执行部署")
                # ▼ AI 自主决策闭环: AI 自选处置并自动执行, 高危/回滚才等人确认
                _ad = yield from ai_handle_failure(
                    f"{name} 原生安装脚本执行失败, AI 自主处置",
                    out, retry_cmd=f"OUT=$({script} 2>&1); RC=$?; echo \"$OUT\" | tail -30; echo __RC__=$RC",
                    risk_level="medium", max_auto=2)
                if _ad.get("decision") == "":
                    yield {"type": "error", "message": "native 部署失败"}
                    yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                    return
                if _ad.get("decision") == "skip":
                    yield log("AI 判定跳过 native 安装(继续后续验证)")
                    choice = "skip"
                else:
                    choice = _ad.get("decision")  # fix/retry/rollback/human 已处理
                # 返回后由下方验证逻辑兜底; 若 AI 未给出有效处置则失败
                if not choice:
                    yield {"type": "error", "message": "native 部署失败"}
                    yield {"type": "complete", "status": "failed", "message": f"部署失败: {out[:200]}"}
                    return
            # native 部署后验证: 检查进程/端口是否真正起来(避免装失败仍判 running)
            vdef = _NATIVE_VERIFY.get(name)
            if vdef:
                vcmd, okkeys = vdef
            else:
                vcmd = f"(pgrep -x {name} >/dev/null 2>&1 || pidof {name} >/dev/null 2>&1) && echo UP || echo DOWN"
                okkeys = ["UP"]
            vok, vout = _exec_ssh(asset, vcmd, timeout=60)
            # 关键: 只看明确的成功标记 UP 且无 DOWN(避免 'inactive' 含 'active' 子串误判)
            passed = ("UP" in vout) and ("DOWN" not in vout) if okkeys else bool(vout.strip())
            if not passed:
                yield log(f"⚠ 验证未通过: {vout[:150]}")
                yield diag(f"native 安装脚本执行了但服务未起来: {vout[:150]}", phase="验证")
                # ▼ AI 自主处置: AI 自选启动修复/重试, 回滚/高危才等人确认; 处置后重新验证
                _ad2 = yield from ai_handle_failure(
                    f"{name} 服务未起来(验证未通过), AI 自主处置",
                    out + "\n" + vout,
                    retry_cmd=vcmd if not (okkeys and "UP" in okkeys) else f"systemctl restart {name} 2>/dev/null; sleep 3; {vcmd}",
                    risk_level="medium", max_auto=2)
                if _ad2.get("decision") == "":
                    yield {"type": "complete", "status": "failed", "message": f"部署脚本已执行但验证未通过: {vout[:150]}"}
                    return
                if _ad2.get("decision") == "skip":
                    yield log("AI 判定跳过验证(继续后续流程)")
                    passed = True
                else:
                    vk2, vout2 = _exec_ssh(asset, vcmd, timeout=60)
                    passed = ("UP" in vout2) and ("DOWN" not in vout2) if okkeys else bool(vout2.strip())
                    if passed:
                        yield log(f"重新验证通过: {vout2[:120]}")
                        yield ai("deploy")
                        native_ok = True
                    else:
                        yield {"type": "complete", "status": "failed", "message": f"处置后服务仍未起来: {vout2[:120]}"}
                        return
            else:
                yield log(f"验证通过: {vout[:120]}")
                yield ai("deploy")
    else:
        # helm / ha: 虚拟执行(依赖 K8s/helm 引擎)
        yield log(f"{deploy_type} 部署记录已创建(依赖 K8s/helm 引擎执行)。配方见上方。")
        yield ai("helm")
        yield {"type": "complete", "status": "deployed", "message": f"{name} {deploy_type} 记录已建(待 K8s/helm 引擎执行)"}
        return

    # ── 阶段4: 验证 ──
    if cancelled():
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
        return
    yield {"type": "phase", "step": 4, "title": "阶段4/5 部署验证"}
    if deploy_type == "docker":
        cn = f"aiops-{name}"
        ok2, ps = _exec_ssh(asset, f"docker ps --filter name={cn} --format '{{{{.Names}}}} {{{{.Status}}}}' 2>&1 | head -5")
        running = "Up" in ps
        yield log(f"容器状态: {ps or '(未找到)'}")
        if not running:
            yield diag(f"docker 容器未进入 Up 状态: {ps or '(空)'}", phase="验证")
            yield {"type": "error", "message": "容器未进入 Up 状态"}
            yield {"type": "complete", "status": "failed", "message": f"容器未启动: {ps}"}
            return
        yield ai("verify")
    else:
        # ▼ native 真正验证服务是否起来: 用 _NATIVE_VERIFY 探测命令 + 输出含 UP 判定成功;
        #   修复此前"不检查探测结果、无条件标成功"导致的假成功(部署未起也报成功)。
        _vp = _NATIVE_VERIFY.get(name)
        if _vp:
            _vcmd, _upkeys = _vp
            # 针对 redis 等带端口/密码的组件, 把探测命令里的默认端口/密码替换为实际部署值
            _redis_pwd = str((params or {}).get("redis_password") or "")
            if name == "redis":
                # ▼ 探活命令带 timeout 防止 redis-cli 挂死; 密码优先用部署参数(deploy_params), 临时文件可能已被部署脚本清理
                _vcmd = (f"timeout 6 redis-cli -p {port or 6379} -a '{_redis_pwd}' ping 2>/dev/null | grep -q PONG && echo UP "
                         f"|| timeout 6 redis-cli -p {port or 6379} -a \"$(cat /tmp/.aiops_redis_pw 2>/dev/null)\" ping 2>/dev/null | grep -q PONG && echo UP "
                         f"|| timeout 6 redis-cli -p {port or 6379} ping 2>/dev/null | grep -q PONG && echo UP "
                         f"|| echo DOWN")
            h, hout = _exec_ssh(asset, _vcmd, timeout=30)
            yield log(f"健康探测: {hout[:200]}")
            _live = any(k in hout for k in _upkeys)
            if not _live:
                # ▼ 容忍服务重启抖动: 首次 DOWN 间隔重探一次, 仍 DOWN 才进入 AI 处置/失败
                yield log("健康探测未就绪, 3s 后重探...")
                time.sleep(3)
                hout = _exec_ssh(asset, _vcmd, timeout=30)[1]
                yield log(f"复探健康探测: {hout[:200]}")
                _live = any(k in hout for k in _upkeys)
            if not _live:
                # 探测未到 UP → 部署实际未成功, 交给 AI 自主处置闭环(而不是假成功)
                yield diag(f"{name} 服务未正常启动(健康探测=<DOWN>)", phase="验证")
                _ad = yield from ai_handle_failure(
                    f"{name} 部署已完成但服务未成功启动(健康探测 DOWN), AI 自主处置",
                    hout, retry_cmd=_vcmd, risk_level="medium", max_auto=2)
                if _ad.get("decision") == "":
                    yield {"type": "error", "message": "服务未启动"}
                    yield {"type": "complete", "status": "failed", "message": f"{name} 服务未启动: {hout[:200]}"}
                    return
                # ▼ 修复: AI 决策(retry/fix 等)执行后, 必须**再次真实探测**确认服务真正起来,
                #   否则 retry 失败(仍 DOWN)也会被放行到"部署成功"(假成功)。
                h2, hout2 = _exec_ssh(asset, _vcmd, timeout=30)
                yield log(f"复检健康探测: {hout2[:200]}")
                if not any(k in hout2 for k in _upkeys):
                    yield {"type": "error", "message": "复检仍 DOWN"}
                    yield {"type": "complete", "status": "failed", "message": f"{name} 服务仍未启动: {hout2[:200]}"}
                    return
        else:
            h, hout = _exec_ssh(asset, _HEALTH_CMDS.get(name, f"systemctl is-active {name} 2>/dev/null || echo DOWN"))
            yield log(f"健康探测: {hout[:200]}")
            yield ai("verify")

    yield {"type": "status", "status": "succeeded", "message": f"{name} 部署成功"}
    yield ai("done")

    # 部署成功后自动触发四合一体检(健康/配置/漏洞/AI 分析), 并产出可直接交付的 AI 部署报告
    health_data = None
    if install_id and deploy_type in ("docker", "native"):
        try:
            yield {"type": "phase", "step": 4, "title": "部署后·四合一体检"}
            yield log("部署成功, 自动执行健康/配置/漏洞/AI 四合一体检...")
            _report = full_health_check(db, install_id)
            health_data = _report
            yield {"type": "report", "report": _report,
                   "overall_status": _report.get("overall_status"),
                   "summary": ((_report.get("ai") or {}).get("summary") or "") or f"{name} 体检完成 overall={_report.get('overall_status')}"}
            yield log(f"四合一体检完成: overall={_report.get('overall_status')}")
        except Exception as _e:
            yield log(f"四合一体检跳过: {_e}")

    # 可直接交付的 AI 部署报告(结论/执行/影响/下一步/风险)
    deliv = final_report("succeeded", "\n".join(connbuf[-60:]), health_data)
    yield deliv

    yield {"type": "complete", "status": "succeeded", "message": f"{name} 部署成功"}


# ─── precheck_deploy (原 L3792-4066) ───
def precheck_deploy(db, asset, comp: dict, deploy_type: str = "docker",
                    port: Optional[int] = None, http_proxy: str = "",
                    https_proxy: str = "", no_proxy: str = "",
                    deploy_path: str = "", params: dict = None) -> dict:
    """逻辑预检(对标 K8s 集群部署 precheck)。

    返回: {ok, issues, checks:[{name, ok, message}]}
    预检项: 目标机资产/SSH 连通/root/内存/端口占用/残留进程/部署方式环境/网络/资源。
    端口与会话内残留进程优先使用用户填写的定制参数(params['db_port']), 否则回退 default_port。
    供前端「预检」按钮与部署流开头复用(不产生副作用)。
    """
    checks = []
    issues = []
    system = ""
    params = params or {}
    # 用户填写的端口优先(针对各组件 param_schema 的 db_port / amqp_port / mq_port)
    _pkey = "db_port"
    if comp.get("name") == "rabbitmq":
        _pkey = "amqp_port"
    elif comp.get("name") == "kafka":
        _pkey = "db_port"
    user_port = int(params.get(_pkey) or port or comp.get("default_port") or 0)
    name = comp.get("name", "")

    def _add(name, ok, msg="", level=None):
        checks.append({"name": name, "ok": bool(ok), "message": msg or ("" if ok else "未通过"), "level": level or ("error" if not ok else "info")})
        if not ok:
            issues.append(f"{name}: {msg}" if msg else name)

    # 1. 目标机资产
    if not asset:
        _add("目标机资产", False, "资产不存在")
        return {"ok": False, "issues": issues, "checks": checks}
    _add("目标机资产", asset.connection_type == "ssh",
         f"{asset.name} ({asset.ip}) type={asset.connection_type or '?'}")

    if asset.connection_type != "ssh":
        return {"ok": False, "issues": issues, "checks": checks}

    # 2. SSH 连通 + root
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=12)
        ok = True
        try:
            _in, _out, _err = ssh.exec_command(
                "id -u; free -m | awk '/Mem:/{print $2}'; nproc; "
                "cat /etc/os-release 2>/dev/null | grep -iE '^(ID|VERSION_ID)=' | tr '\\n' ' '; "
                "which yum >/dev/null 2>&1 && echo pkgyum; which apt-get >/dev/null 2>&1 && echo pkgapt; which dnf >/dev/null 2>&1 && echo pkgdnf",
                timeout=25)
            out = _out.read().decode(errors="ignore").strip()
            ssh.close()
            lines = out.splitlines() or [""]
            uid = lines[0].strip()
            _add("SSH 连通", True, f"连接成功 uid={uid}")
            _add("root 权限", uid == "0", "非 root 用户" if uid != "0" else "")
            try:
                _mem = int(lines[1].strip()) if len(lines) > 1 and lines[1].strip().isdigit() else 0
                _add("目标机内存", _mem > 0, f"可用内存约 {_mem} MB" if _mem else "无法读取内存")
            except Exception:
                _add("目标机内存", False, "无法读取内存")
            # 探测目标机系统类型(pkg_manager + distro)
            _pm = ""
            for l in lines:
                if l.startswith("pkg"):
                    _pm = l[3:]
            _distro = ""
            for l in lines:
                if l.startswith("ID="):
                    _distro = l[len("ID="):].strip().strip('"')
                    break
            _did = (lines[1] if len(lines) > 1 else "")
            system = ("debian" if _pm == "apt" else
                      ("rhel" if _pm in ("yum", "dnf") else
                       ("alpine" if "alpine" in out else ("unknown" if not _distro else _distro))))
            _add("目标机系统", True, f"{_distro or 'unknown'} (包管理器: {_pm or 'unknown'})")
        except Exception as e:
            ssh.close()
            _add("SSH 命令执行", False, str(e)[:80])
    except Exception as e:
        _add("SSH 连通", False, str(e)[:80])

    # 3. 端口占用(docker/native 会占用用户填写的端口; native 时残留进程将由部署自动清理)
    p = user_port
    if p and asset.connection_type == "ssh":
        try:
            from app.services.remediation_service import _ssh_connect as _sc2
            _ssh2 = _sc2(asset, timeout=12)
            _i, _o, _e = _ssh2.exec_command(f"ss -ltn -p 2>/dev/null | grep -q ':{p} ' && echo BUSY || echo FREE", timeout=25)
            rr = _o.read().decode(errors="ignore").strip()
            _ssh2.close()
            free = "FREE" in rr and "BUSY" not in rr
            if free:
                _add(f"端口 {p}", True, "端口可用")
            elif deploy_type == "native":
                # native 部署会先停旧服务/杀残留进程, 端口占用不作为阻断, 但显著提示
                _add(f"端口 {p}", True, f"端口已被占用(旧实例残留, 部署将自动停止并清理后重启)", level="warning")
            else:
                _add(f"端口 {p}", False, f"端口已被占用, 请先停止占用 {p} 端口的进程")
        except Exception as e:
            _add(f"端口 {p} 检查", False, str(e)[:60])

    # 3.5 残留进程/旧实例检测(native): 提前发现可能占用端口/数据的旧服务进程
    if deploy_type == "native" and asset.connection_type == "ssh":
        try:
            from app.services.remediation_service import _ssh_connect as _sc_p
            _sshp = _sc_p(asset, timeout=12)
            _pi, _po, _pe = _sshp.exec_command(
                f"pgrep -f '{name}' >/dev/null 2>&1 && echo PROC_ALIVE || echo PROC_CLEAN", timeout=25)
            rr = _po.read().decode(errors="ignore").strip()
            _sshp.close()
            alive = "PROC_ALIVE" in rr and "PROC_CLEAN" not in rr
            # native 部署会先停旧服务/杀残留进程, 不作为阻断, 但显著提示
            _add(f"残留进程({name})", True if not alive else True,
                 "存在运行中的旧进程, 部署将自动停止并清理" if alive else "无残留进程",
                 level="warning" if alive else "info")
        except Exception as _pex:
            _add(f"残留进程检测", False, str(_pex)[:60])

    # 4. 各部署方式环境
    if deploy_type == "docker":
        try:
            from app.services.remediation_service import _ssh_connect as _sc3
            _ssh3 = _sc3(asset, timeout=12)
            _i, _o, _e = _ssh3.exec_command("docker version --format '{{.Server.Version}}' 2>&1; echo '|'; docker compose version 2>&1 | head -1", timeout=25)
            rr = _o.read().decode(errors="ignore").strip()
            _ssh3.close()
            has_docker = "Docker version" in rr or any(ch.isdigit() for ch in rr.split("|")[0])
            _add("Docker 环境", "|" in rr and has_docker, rr.split("|")[0][:40] or "未安装 Docker")
            _add("Docker Compose", "Docker Compose" in rr or "v2" in rr.lower(), "Compose 未安装" if ("|" in rr and "Docker Compose" not in rr and "v2" not in rr.lower()) else "")
            if http_proxy or https_proxy:
                _add("HTTP 代理", True, f"将写入 docker daemon: {http_proxy or https_proxy}")
        except Exception as e:
            _add("Docker 环境", False, str(e)[:60])
    elif deploy_type == "native":
        _add("原生安装脚本", bool((comp.get("native_script") or "").strip()),
             "组件未提供原生安装脚本, 建议改用 docker" if not (comp.get("native_script") or "").strip() else "脚本就绪")
    elif deploy_type in ("helm", "ha"):
        _add("K8s/Helm 引擎", False, "helm/ha 部署需通过 K8s/helm 引擎执行(当前为记录+配方)")

    # 4.4 工具链 + 系统包源(native 部署前必查, 避免 wget 缺失/yum 源不可达等隐性失败)
    if deploy_type == "native" and asset.connection_type == "ssh":
        try:
            from app.services.remediation_service import _ssh_connect as _sct
            _ssht = _sct(asset, timeout=12)
            # 一次性探测: 工具链 + yum/apt 源状态(用 timeout 卡死, grep 在远端执行, 避免回传大段日志)
            _ti, _to, _te = _ssht.exec_command(
                "for c in curl wget tar make gcc; do command -v $c >/dev/null 2>&1 && echo HAS_$c || echo MISS_$c; done; "
                "echo '|YUM|'; (timeout 12 yum repolist 2>&1 | grep -iE '(repo id|repolist:|error|could not|timeout|failed)' | head -5); "
                "echo '|APT|'; (timeout 12 apt-get update 2>&1 | grep -iE '(hit|err|ign|get|failed)' | head -3)",
                timeout=40)
            tout = _to.read().decode(errors="ignore").strip()
            _ssht.close()
            # 工具链
            # 用户是否配置了网络代理(有代理则缺失工具可在部署时自动安装, 不阻断预检)
            _has_proxy = bool((http_proxy or https_proxy or "").strip())
            has_curl = has_wget = has_tar = False
            for line in tout.splitlines():
                if line.startswith("HAS_"):
                    t = line[4:]
                    if t == "curl": has_curl = True
                    if t == "wget": has_wget = True
                    if t == "tar":  has_tar = True
                    _add(f"工具 {t}", True, "已安装", level="info")
                elif line.startswith("MISS_"):
                    t = line[5:]
                    if t in ("curl", "tar"):
                        # ▼ 修复: 已配置网络代理时, 缺失工具不再硬阻断预检(部署阶段将自动通过代理安装)
                        if _has_proxy:
                            _add(f"工具 {t}", True,
                                 f"目标机缺少 {t}, 已配置网络代理, 部署时将自动安装(yum install -y {t})",
                                 level="warning")
                        else:
                            _add(f"工具 {t}", False, f"目标机缺少 {t}, 部署前请安装: yum install -y {t}")
                    else:
                        _add(f"工具 {t}", True, f"目标机缺少 {t}(非必需, 仅源码编译组件需要)", level="warning")
            # 系统包源(yum/dnf 同协议, 兼容识别)
            yum_part = ""
            try:
                yum_part = tout.split("|YUM|")[1].split("|APT|")[0]
            except Exception:
                yum_part = ""
            if yum_part:
                yp = yum_part.lower()
                # 优先级 1: 源报错关键词
                if ("could not" in yp or "timeout" in yp or "failed" in yp
                        or "error: error downloading" in yp
                        or "failed to connect" in yp):
                    _add("系统包源(yum)", True,
                         "yum/dnf 源响应异常, 建议检查网络/切国内源(阿里云/清华)",
                         level="warning")
                # 优先级 2: 列出 repo → yum 源 OK
                elif ("repolist:" in yum_part or "repo id" in yum_part):
                    _add("系统包源(yum)", True, "yum/dnf 源可解析(已列出仓库)", level="info")
                # 优先级 3: 无输出(可能 dnf 在后台刷新缓存中或输出被 grep 吃掉)
                elif not yum_part.strip():
                    _add("系统包源(yum)", True, "yum/dnf 源响应为空(可能源不可达或被超时截断, 建议先手测)", level="warning")
                else:
                    _add("系统包源", True, "目标机未识别为 yum/dnf/apt 系(跳过)", level="info")
            # 工具链兜底: 如果 curl 和 wget 都缺, 阻断
            if not has_curl and not has_wget:
                _add("下载工具", False, "目标机同时缺少 curl 和 wget, 无法下载任何外部资源")
        except Exception as _tec:
            logger.warning("[precheck tool chain probe failed] %s", _tec, exc_info=True)

    # 4.5 网络连通性(目标机能否解析域名/访问源/代理可达) —— 部署前尽早发现网络问题
    if asset.connection_type == "ssh":
        _net_tgt = "registry-1.docker.io" if deploy_type == "docker" else "mirrors.aliyun.com"
        try:
            from app.services.remediation_service import _ssh_connect as _scn
            _sshn = _scn(asset, timeout=12)
            _probe = (f"getent hosts {_net_tgt} >/dev/null 2>&1 && echo DNSOK || echo DNSFAIL; "
                      f"curl -s -o /dev/null -m 6 -I https://{_net_tgt} >/dev/null 2>&1 && echo NETOK || echo NETFAIL")
            _i3, _o3, _e3 = _sshn.exec_command(_probe, timeout=30)
            netout = _o3.read().decode(errors="ignore").strip()
            _sshn.close()
            dns_ok = "DNSOK" in netout
            net_ok = "NETOK" in netout
            # 有代理时额外测代理可达
            _proxy = http_proxy or https_proxy
            proxy_ok = False
            if _proxy:
                try:
                    from app.services.remediation_service import _ssh_connect as _scp
                    _sshp = _scp(asset, timeout=12)
                    _pi, _po, _pe = _sshp.exec_command(
                        f"curl -s -o /dev/null -m 6 -x '{_proxy}' https://{_net_tgt} >/dev/null 2>&1 && echo PROXYOK || echo PROXYFAIL", timeout=30)
                    proxyout = _po.read().decode(errors="ignore").strip()
                    _sshp.close()
                    proxy_ok = "PROXYOK" in proxyout
                    _add(f"代理可达({_net_tgt})", proxy_ok, "代理可连通" if proxy_ok else "代理不可达")
                    # 内网+代理环境: 本机无可用系统 DNS, 域名由代理解析, 代理可达即视为 DNS/网络均通过
                    if proxy_ok:
                        dns_ok = True
                        net_ok = True
                except Exception as _exc9:
                    logger.warning("[except:pass] Exception: %s", _exc9, exc_info=True)
            _add(f"DNS 解析({_net_tgt})", dns_ok, f"{_net_tgt} 可解析" if dns_ok else f"无法解析 {_net_tgt}(网络/DNS 问题)")
            _add(f"网络可达({_net_tgt})", net_ok, f"可访问 {_net_tgt}" if net_ok else f"无法访问 {_net_tgt}(源/代理问题)")
        except Exception as e:
            _add("网络连通性", False, str(e)[:60])

    # 5. 资源(基于实际部署路径所在文件系统)
    _target = (deploy_path or "").strip() or "/data"
    try:
        from app.services.remediation_service import _ssh_connect as _sc4
        _ssh4 = _sc4(asset, timeout=12)
        _i, _o, _e = _ssh4.exec_command(
            f"df -m \"$(dirname '{_target}' 2>/dev/null || echo /data)\" 2>/dev/null | awk 'NR==2{{print $4}}'",
            timeout=25)
        dfree = _o.read().decode(errors="ignore").strip()
        _ssh4.close()
        if dfree.isdigit():
            _add(f"磁盘空间({_target})", int(dfree) > 500,
                 f"剩余约 {int(dfree)} MB" if int(dfree) > 500 else "磁盘空间不足(<500MB)")
        # 目录可写性/父目录存在性校验(root 下 mkdir -p 即可创建)
        if deploy_type == "docker" and (deploy_path or "").strip():
            d = _target
            try:
                from app.services.remediation_service import _ssh_connect as _sc5
                _ssh5 = _sc5(asset, timeout=12)
                _i2, _o2, _e2 = _ssh5.exec_command(
                    f"mkdir -p '{d}' && [ -w '{d}' ] && echo WRITABLE || echo NOWRITE; "
                    f"touch '{d}/.aiops_probe' 2>/dev/null && rm -f '{d}/.aiops_probe' && echo OK || echo NOK",
                    timeout=25)
                probe = _o2.read().decode(errors="ignore").strip()
                _ssh5.close()
                wok = "WRITABLE" in probe and "OK" in probe
                _add(f"部署路径可写", wok, f"{d} 可读/可写" if wok else f"{d} 不可写(权限不足)")
            except Exception as _pe:
                _add(f"部署路径可写", False, str(_pe)[:60])
    except Exception as _exc10:
        logger.warning("[except:pass] Exception: %s", _exc10, exc_info=True)

    return {"ok": not issues, "issues": issues, "checks": checks, "system": system}


