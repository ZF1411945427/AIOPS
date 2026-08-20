"""应用部署编排服务 (DeployPlan/DeployStep) — 拆分后门面。

子模块:
  - deploy_state.py      共享模块级状态
  - deploy_common.py     基础工具/序列化/常量
  - deploy_ai_engine.py  AI 决策簇
  - deploy_executor.py   执行链(execute_plan/_ai_stream_execute/回滚)
  - deploy_report_gen.py 报告域
本文件保留公共 API 并 re-export 全部符号, 保持对外接口不变。
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import DeployPlan, DeployStep, Asset, AIProvider, AgentConfig
from app.services.agent_service import call_llm  # noqa: F401
from app.services.ssh_helper import connect_ssh
from app.logger import logger
from app.services.deploy_report import (_generate_fallback_report, _report_to_markdown,
                                        _report_to_html, _report_to_docx)  # noqa: F401


# ─── deploy_state 状态(共享同一对象) ───
from app.services.deploy_state import (_EXEC_LOCK, _RUNNING_CLIENTS, _STOPPED,
                                       _DECISIONS, _STEP_TIMEOUT)  # noqa: F401

# ─── deploy_common: 基础工具+序列化+常量 ───
from app.services.deploy_common import (  # noqa: F401
    _release_exec, _now, _get_provider, _build_offline_hint, _get_asset_ids,
    _get_assets, _extract_json, _sanitize_dirname, resolve_download_path,
    detect_artifact_source, _run_ssh, _fetch_offline_bundle_path,
    auto_download_artifact, _git_zip_url, _set_compose_perms, _resolve_command,
    _check_unresolved, _is_valid_shell_command, _offline_blocked_reason,
    _assert_online_allowed, _proxy_env_prefix, _sync_env_mapping_from_sop,
    _ssh_connect, _collect_env_probes, _plan_to_dict, _step_to_dict, _safe_json,
    _GIT_HOST_HINTS, _OFFLINE_PUBLIC_IMAGES, _PUBLIC_REPO_HINTS,
)

# ─── deploy_ai_engine: AI 决策簇 ───
from app.services.deploy_ai_engine import (  # noqa: F401
    _ai_diagnose_failure, _ai_auto_resolve_env, _ai_auto_resolve_unresolved,
    _ai_build_execution_dag, _ai_pre_execution_risk, _ai_autonomous_decision,
    _ai_adaptive_rollback, _ai_decision_log, _ai_select_deployment_strategy,
    _ai_risk_scoring, _record_deployment_feature, _ai_pattern_matching,
    _ai_assess_state, _ai_health_gate, _ai_dynamic_scheduling,
    _ai_plan_step_autonomous, _ai_resource_check,
)

# ─── deploy_executor: 执行链 ───
from app.services.deploy_executor import (  # noqa: F401
    execute_plan, stream_execute, _wait_for_risk_confirm,
    _set_pending_decision_plan, submit_decision, _ai_stream_execute,
    _ai_stream_rollback, stream_rollback_cleanup, _ai_step_failure,
    _run_fix_commands, _do_rollback, _stream_rollback,
)

# ─── deploy_report_gen: 报告域 ───
from app.services.deploy_report_gen import (  # noqa: F401
    post_deploy_verify, _extract_deploy_info, generate_deploy_report,
    download_report, _record_execution_history, _record_cleanup_history,
)

# ─── 公共释放锁 API(原 L30-33) ───
def release_exec_lock(plan_id: int):
    """供 router 在 WS 断开时强制释放执行锁（不等后台线程自然结束）。"""
    _EXEC_LOCK.pop(plan_id, None)



# ─── 原 L35-58 ───
def probe_environment(db: Session, plan_id: int) -> dict:
    """SSH 探查目标机真实环境，返回探查结果 JSON。探查前自动下载源码(在线/离线)。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    # 探查前自动下载源码（在线 git/HTTP + 离线），幂等
    download = auto_download_artifact(db, plan_id)
    if not download.get("ok"):
        return {"error": f"源码准备失败: {download.get('error', '未知错误')}", "download": download}
    assets = _get_assets(db, plan)
    if not assets:
        return {"error": "计划未关联目标资产"}
    asset = assets[0]
    try:
        client, host = _ssh_connect(asset)
    except Exception as e:
        return {"error": f"SSH 连接失败: {e}"}
    try:
        probes = _collect_env_probes(client, plan)
        plan.environment_probe_json = json.dumps(probes, ensure_ascii=False)
        db.commit()
        return {"ok": True, "probe": probes}
    finally:
        client.close()


# ─── 原 L104-189 ───
def ai_auto_env_mapping(db: Session, plan_id: int) -> dict:
    """基于环境探查结果，AI 自动生成环境映射 + SOP 适配建议（A + C 层核心）。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    if not plan.environment_probe_json or plan.environment_probe_json == "{}":
        return {"error": "请先执行环境探查(probe)"}
    probe = json.loads(plan.environment_probe_json)
    doc_raw = plan.doc_raw or ""
    sop = json.loads(plan.sop_json or "[]")
    assets = _get_assets(db, plan)
    asset_info = ""
    if assets:
        asset_info = json.dumps([{"name": a.name, "ip": a.ip, "type": a.ci_type} for a in assets], ensure_ascii=False)
    provider = _get_provider(db)
    if not provider:
        return {"error": "未配置 AI 提供商"}
    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责根据目标机真实环境探查结果和部署手册，完成以下任务：\n"
        "1. 自动生成环境映射(env_mapping)：根据探查结果确定 APP_DIR、TARGET_IP 等参数的真实值\n"
        "2. 服务拓扑分析：分析这个 compose/dockerfile 部署了哪些服务、依赖关系\n"
        "3. 自适应建议：基于当前环境推荐 SOP 调整（如：镜像已存在跳过 build、端口冲突换端口、目录已存在跳过创建）\n"
        "请严格按以下 JSON Schema 输出，不要额外内容：\n"
        "{\n"
        '  "env_mapping": {"APP_DIR": "<真实部署目录>", "TARGET_PORT": "80"},\n'
        '  "service_topology": "服务拓扑分析文本",\n'
        '  "adaptations": [\n'
        '    {"step": 2, "type": "skip_build", "reason": "镜像 nginx:latest 已存在，跳过 build", "action": "建议跳过 docker compose build"},'
        '    {"step": 3, "type": "port_check", "reason": "80 端口已被占用", "action": "建议改用 8080 端口"}\n'
        "  ],\n"
        '  "preflight_enhance": [\n'
        '    {"check": "端口冲突检查", "command": "ss -tlnp | grep 80", "expect": "端口未被占用"}\n'
        "  ]\n"
        "}\n"
        "规则：\n"
        "- env_mapping 的值必须来自探查结果，不能凭空编造\n"
        "- 如果探查结果中某个目录/端口不存在，不要强行映射\n"
        "- adaptations 是可选优化，不是必须的\n"
    )
    # 检测 OS 兼容性提示
    _os_text = probe.get("os", "")
    _os_hint = ""
    if "centos" in _os_text.lower() and "7" in _os_text:
        _os_hint = "注意：目标机为 CentOS 7，nginx 最新版可能存在 pwrite() 权限问题，建议添加 security_opt: [seccomp:unconfined] 到 docker-compose 服务中。"
    user_prompt = (
        f"## 部署手册\n{doc_raw}\n\n"
        f"## 目标资产信息\n{asset_info}\n\n"
        f"## 目标机环境探查结果\n{json.dumps(probe, ensure_ascii=False, indent=1)}\n\n"
        f"## AI 初版 SOP\n{json.dumps(sop, ensure_ascii=False, indent=1)}\n\n"
        f"{_os_hint}\n"
        "请分析真实环境，自动生成环境映射和自适应建议。"
    )
    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=max(provider.timeout_seconds, 120))
    if resp.get("error"):
        return {"error": f"AI 分析失败: {resp['error']}"}
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return {"error": "AI 返回格式异常"}
    analysis = _extract_json(content)
    if not analysis:
        return {"error": "AI 未能生成有效的环境分析"}
    mapping = analysis.get("env_mapping", {})
    if mapping:
        # 合并而非整体覆盖：已存在的非空值优先（用户手填 / resolve-env / 真实下载路径），
        # AI 只补充缺失的 key，避免 AI 凭空推断的 APP_DIR 等覆盖正确值。
        try:
            cur = json.loads(plan.env_mapping) if isinstance(plan.env_mapping, str) and plan.env_mapping not in ("{}", "[]") else {}
        except Exception:
            cur = {}
        merged = dict(cur)
        for k, v in (mapping or {}).items():
            if v in (None, ""):
                continue
            if merged.get(k) in (None, ""):
                merged[k] = v
        # APP_DIR 若缺失，用真实下载路径兜底
        if merged.get("APP_DIR") in (None, ""):
            merged["APP_DIR"] = resolve_download_path(plan)
        plan.env_mapping = json.dumps(merged, ensure_ascii=False)
    plan.env_analysis_json = json.dumps(analysis, ensure_ascii=False)
    db.commit()
    return {"ok": True, "analysis": analysis, "env_mapping": analysis.get("env_mapping", {})}


# ─── 原 L227-263 ───
def stop_execution(db: Session, plan_id: int, rollback: bool = True) -> dict:
    """停止正在执行的部署(强制)：关闭 SSH 连接 → 中断命令 → producer 异常退出 → 释放执行锁。
    默认 rollback=True：停止后自动执行一次回滚清理（停容器 + 清理产物 + 重置为 planned），
    避免卡死/中断后目标机残留容器或半成品。
    rollback=False 时仅断连重置状态（兼容旧行为）。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    client = _RUNNING_CLIENTS.pop(plan_id, None)
    if client:
        try:
            client.close()
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    _STOPPED[plan_id] = True
    # 如果有决策队列在等待，塞入停止信号立即解除阻塞
    _dq = _DECISIONS.get(plan_id)
    if _dq:
        try:
            _dq.put_nowait("rollback")
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    _release_exec(plan_id)
    _STOPPED.pop(plan_id, None)
    plan.status = "planned"
    _record_execution_history(db, plan, "stopped", {"stopped_by": "stop_execution", "rollback": rollback})
    db.commit()

    msg = "已停止执行"
    if rollback:
        try:
            rb = _force_rollback_cleanup_sync(db, plan_id)
            msg = "[已停止] " + (rb.get("message", "并已自动回滚清理"))
        except Exception as e:
            logger.warning(f"停止后自动回滚清理异常: plan_id={plan_id} {e}")
            msg = f"已停止执行(回滚清理异常: {e})"
    return {"ok": True, "message": msg}


# ─── 原 L266-322 ───
def _force_rollback_cleanup_sync(db: Session, plan_id: int) -> dict:
    """强制同步回滚清理（停止时调用）：对每个资产 SSH 停容器 + 清理运行产物，重置步骤与计划为 planned。
    可用于 running/卡死状态，不校验 status。返回 {"ok","message","assets"}。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"ok": False, "message": "计划不存在"}
    assets = _get_assets(db, plan)
    if not assets:
        return {"ok": False, "message": "计划未关联目标资产"}
    mapping = json.loads(plan.env_mapping or "{}")
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()
    app_dir = mapping.get("APP_DIR", "")
    records = []
    for asset in assets:
        _alines = []
        try:
            client, host = _ssh_connect(asset)
        except Exception as e:
            _alines.append(f"❌ {asset.name}({asset.ip}) SSH 连接失败: {e}")
            records.append({"asset": asset.name, "ip": asset.ip, "lines": _alines, "status": "ssh_failed"})
            continue
        try:
            if app_dir:
                _down = f"cd {app_dir} && docker compose down -v 2>/dev/null || true"
                try:
                    _, _o, _e = client.exec_command(_down, timeout=30)
                    _rc = _o.channel.recv_exit_status()
                    _alines.append(f"🧹 清理容器: docker compose down -v (exit={_rc})")
                except Exception as ex:
                    _alines.append(f"⚠ 清理容器异常: {ex}")
                try:
                    _clean = (f"cd {app_dir} 2>/dev/null && "
                              f"rm -rf node_modules .venv venv __pycache__ dist build */__pycache__ 2>/dev/null; "
                              f"find . -name '*.pyc' -type f -delete 2>/dev/null; echo cleaned")
                    _, _o, _e = client.exec_command(_clean, timeout=30)
                    _rc = _o.channel.recv_exit_status()
                    _alines.append(f"🧹 清理运行产物，保留源码目录: {app_dir}")
                except Exception as ex:
                    _alines.append(f"⚠ 清理运行产物异常: {ex}")
            records.append({"asset": asset.name, "ip": asset.ip, "lines": _alines, "status": "cleaned"})
        finally:
            try:
                client.close()
            except Exception as _exc2:
                logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)
    for s in steps:
        s.status = "pending"
        s.output = ""
        s.diagnosis = ""
        s.fix_command = ""
        s.retry_count = 0
        s.started_at = None
        s.finished_at = None
    _record_cleanup_history(db, plan, records, app_dir)
    plan.status = "planned"
    db.commit()
    return {"ok": True, "message": f"已回滚清理 {len(records)} 个资产，状态重置为 planned", "assets": len(records)}


# ─── 原 L374-385 ───
def list_plans(db: Session, status: Optional[str] = None, page: int = 1, per_page: int = 20):
    q = db.query(DeployPlan).order_by(DeployPlan.created_at.desc())
    if status:
        q = q.filter(DeployPlan.status == status)
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_plan_to_dict(p) for p in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ─── 原 L388-393 ───
def get_plan(db: Session, plan_id: int):
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return None
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()
    return {**_plan_to_dict(plan), "steps": [_step_to_dict(s) for s in steps]}


# ─── 原 L396-423 ───
def create_plan(db: Session, payload: dict, user_id: int) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("计划名称不能为空")
    plan = DeployPlan(
        name=name,
        description=(payload.get("description") or "").strip(),
        artifact_path=(payload.get("artifact_path") or "").strip(),
        artifact_download_path=(payload.get("artifact_download_path") or "").strip(),
        artifact_auto_download=bool(payload.get("artifact_auto_download", True)),
        doc_raw=(payload.get("doc_raw") or "").strip(),
        doc_file_name=(payload.get("doc_file_name") or "").strip(),
        asset_ids=json.dumps(payload.get("asset_ids", []) if isinstance(payload.get("asset_ids"), list) else []),
        use_offline=bool(payload.get("use_offline", False)),
        http_proxy=(payload.get("http_proxy") or "").strip(),
        https_proxy=(payload.get("https_proxy") or "").strip(),
        no_proxy=(payload.get("no_proxy") or "").strip(),
        created_by=user_id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    result = _plan_to_dict(plan)
    # 创建前校验本地路径是否已存在非空内容(防止误部署到已有项目目录)，已有则警告提示但允许继续
    warning = _check_artifact_path_warning(db, plan)
    if warning:
        result["path_warning"] = warning
    return result


# ─── 原 L426-455 ───
def _check_artifact_path_warning(db: Session, plan) -> Optional[str]:
    """创建计划时,SSH 到目标机校验本地源码/下载目标路径是否已存在非空内容。
    若路径非空(已有别的文件/项目),返回警告文案(不拦截创建)。SSH/不可达/远程地址则返回 None。"""
    checks = []
    ap = (plan.artifact_path or "").strip()
    dp = (plan.artifact_download_path or "").strip()
    # artifact_path: 仅当是本地路径(非 git/http/offline)时校验
    if ap:
        src = detect_artifact_source(ap)
        if src == "local":
            checks.append(("代码包路径", ap))
    # 下载目标路径: 永远本地,非空即校验
    if dp:
        checks.append(("源码下载目标路径", dp))
    if not checks:
        return None
    assets = _get_assets(db, plan)
    if not assets:
        return None
    asset = assets[0]
    for label, path in checks:
        try:
            code, out = _run_ssh(asset, f"if [ -d {path} ]; then ls -A {path} 2>/dev/null | head -1; fi", timeout=30)
        except Exception:
            continue
        if code == 0 and out.strip():
            return (f"⚠️ {label}「{path}」在目标机 {asset.ip} 上已存在非空内容"
                    f"（首个文件/目录: {out.strip().splitlines()[0]}），请确认路径是否正确，"
                    f"避免误部署到已有项目目录。")
    return None


# ─── 原 L458-481 ───
def update_plan(db: Session, plan_id: int, payload: dict) -> Optional[dict]:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return None
    for field in ("name", "description", "artifact_path", "doc_raw", "doc_file_name", "env_mapping", "sop_json"):
        if field in payload:
            val = payload[field]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            setattr(plan, field, val)
    if "artifact_download_path" in payload:
        plan.artifact_download_path = (payload.get("artifact_download_path") or "").strip()
    if "artifact_auto_download" in payload:
        plan.artifact_auto_download = bool(payload.get("artifact_auto_download"))
    if "use_offline" in payload:
        plan.use_offline = bool(payload.get("use_offline"))
    for f in ("http_proxy", "https_proxy", "no_proxy"):
        if f in payload:
            setattr(plan, f, (payload.get(f) or "").strip())
    if "asset_ids" in payload and isinstance(payload["asset_ids"], list):
        plan.asset_ids = json.dumps(payload["asset_ids"])
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


# ─── 原 L484-493 ───
def update_doc_raw(db: Session, plan_id: int, doc_raw: str, doc_file_name: str = "") -> Optional[dict]:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return None
    plan.doc_raw = doc_raw
    if doc_file_name:
        plan.doc_file_name = doc_file_name
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


# ─── 原 L496-503 ───
def delete_plan(db: Session, plan_id: int) -> bool:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return False
    db.query(DeployStep).filter(DeployStep.plan_id == plan_id).delete()
    db.delete(plan)
    db.commit()
    return True


# ─── 原 L627-762 ───
def ai_parse_manual(db: Session, plan_id: int) -> dict:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    doc_raw = plan.doc_raw.strip()
    if not doc_raw:
        return {"error": "部署手册内容为空，请先上传手册"}

    provider = _get_provider(db)
    if not provider:
        return {"error": "未配置可用的 AI 模型提供商"}

    assets = _get_assets(db, plan)
    asset_info = ""
    if assets:
        lines = [f"- 名称: {a.name}  IP: {a.ip}  CI: {a.ci_type}" for a in assets]
        asset_info = f"\n目标资产信息（共 {len(assets)} 台）：\n" + "\n".join(lines)

    sys_prompt = (
        "你是一名资深 SRE 运维专家，负责将部署手册解析为结构化部署 SOP。\n"
        "请严格按以下 JSON Schema 输出，不要输出任何额外内容：\n"
        "{\n"
        '  "plan_name": "部署计划名称",\n'
        '  "preflight": [{"check": "检查项名", "command": "只读检查命令", "expect": "预期结果"}],\n'
        '  "steps": [\n'
        "    {\n"
        '      "order": 1,\n'
        '      "description": "步骤说明",\n'
        '      "command": "shell 命令，环境敏感值用 ${ENV_xxx} 占位符",\n'
        '      "verify": "可执行的校验 shell 命令，必须返回 exit 0 才算通过；若无命令则留空字符串。严禁写自然语言描述",\n'
        '      "rollback": "可执行的回滚 shell 命令；若无则留空字符串。严禁写自然语言描述",\n'
        '      "risk": "low|medium|high"\n'
        "    }\n"
        "  ],\n"
        '  "env_vars": [\n'
        '    {"name": "TARGET_IP", "description": "目标 IP", "example": "192.168.1.100", "source": "资产"},\n'
        '    {"name": "APP_DIR", "description": "应用目录", "example": "/opt/myapp", "source": "用户输入"}\n'
        "  ]\n"
        "}\n"
        "规则：\n"
        "1. 从手册中提取所有步骤，按执行顺序排列\n"
        "2. **重要：手册中已有的 ${xxx} 占位符必须原样保留在命令中，不得删除或替换**\n"
        "3. 环境相关的值（IP、端口、目录、密码等）用 ${ENV_xxx} 占位符替代\n"
        "4. 识别手册中的环境参数，在 env_vars 中列出\n"
        "5. 每步标记风险等级（low/medium/high）\n"
        "6. 识别可验证的检查点和可回滚的命令\n"
    )
    user_prompt = f"以下是部署手册内容：\n\n{doc_raw}\n{asset_info}\n\n请解析为结构化 SOP JSON。"

    if plan.use_offline:
        offline_hint = _build_offline_hint(db)
        if offline_hint:
            user_prompt += (
                "\n\n【离线部署要求】本计划启用离线私有仓库，务必遵守：\n"
                "- 一切 docker pull / 镜像引用必须改用私有仓库地址（docker login 后拉取），禁止从公网 Docker Hub 拉取。\n"
                "- 系统包安装(yum/dnf/apt-get install)必须使用本地/内网包源，禁止使用公网软件源。\n"
                f"- 离线资源：\n{offline_hint}"
            )

    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=max(provider.timeout_seconds, 120))
    if resp.get("error"):
        return {"error": f"AI 解析失败: {resp['error']}"}
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return {"error": "AI 返回格式异常"}

    sop = _extract_json(content)
    if not sop:
        return {"error": "AI 未能生成有效的结构化 SOP"}

    steps = sop.get("steps", [])
    env_vars = sop.get("env_vars", [])
    if not steps:
        return {"error": "AI 未能从手册中提取出部署步骤"}

    plan.sop_json = json.dumps(sop, ensure_ascii=False)
    plan.status = "planned"

    db.query(DeployStep).filter(DeployStep.plan_id == plan_id).delete()
    for s in steps:
        step = DeployStep(
            plan_id=plan_id,
            step_order=s.get("order", 0),
            description=(s.get("description") or "").strip(),
            command=(s.get("command") or "").strip(),
            verify_command=(s.get("verify") or "").strip(),
            rollback_command=(s.get("rollback") or "").strip(),
            risk_level=s.get("risk", "medium"),
        )
        db.add(step)
    db.commit()

    # 从所有命令中扫描 ${ENV_xxx} 占位符，没在 env_mapping 里的自动种子（空值，用户编辑）
    try:
        current_mapping = json.loads(plan.env_mapping) if isinstance(plan.env_mapping, str) and plan.env_mapping not in ("{}", "[]") else {}
    except Exception:
        current_mapping = {}
    # 从已保存的步骤命令中额外提取占位符（AI 可能漏报）
    _all_steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).all()
    for _s in _all_steps:
        for _field in (_s.command, _s.verify_command, _s.rollback_command):
            if _field:
                for _m in re.finditer(r'\$\{(\w+)\}', _field):
                    _k = _m.group(1)
                    if _k not in current_mapping:
                        current_mapping[_k] = ""
    # 从原始手册中额外提取占位符（双重兜底：即使 AI 删了命令里的占位符，也能找到）
    for _m in re.finditer(r'\$\{(\w+)\}', doc_raw):
        _k = _m.group(1)
        if _k not in current_mapping:
            current_mapping[_k] = ""
    plan.env_mapping = json.dumps(current_mapping, ensure_ascii=False)
    db.commit()

    # ── AI 自动推断环境变量值（从手册上下文）──
    try:
        provider = _get_provider(db)
        if provider and env_vars:
            inferred = _ai_auto_resolve_env(provider, plan, doc_raw, steps, env_vars)
            if inferred:
                current_mapping.update(inferred)
                for k, v in inferred.items():
                    if k.startswith("ENV_") and (not current_mapping.get(k[4:]) or not current_mapping.get(k)):
                        current_mapping[k[4:]] = v
                    elif not k.startswith("ENV_") and (not current_mapping.get(f"ENV_{k}") or not current_mapping.get(k)):
                        current_mapping[f"ENV_{k}"] = v
                plan.env_mapping = json.dumps(current_mapping, ensure_ascii=False)
                db.commit()
    except Exception as e:
        logger.warning(f"AI 自动推断环境变量异常: {e}")

    return {"ok": True, "sop": sop, "env_vars": env_vars, "step_count": len(steps)}


# ─── 原 L779-817 ───
def resolve_env_mapping(db: Session, plan_id: int, user_mapping: dict) -> dict:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}

    mapping = dict(user_mapping)
    assets = _get_assets(db, plan)
    for i, asset in enumerate(assets):
        suffix = f"_{i + 1}" if len(assets) > 1 else ""
        mapping.setdefault(f"TARGET_IP{suffix}", asset.ip or "")
        mapping.setdefault(f"TARGET_HOSTNAME{suffix}", asset.name or "")
        if i == 0:
            mapping.setdefault("TARGET_IP", asset.ip or "")
            mapping.setdefault("TARGET_HOSTNAME", asset.name or "")

    mapping.setdefault("ARTIFACT_URL", plan.artifact_path or "")
    mapping.setdefault("ARTIFACT_DOWNLOAD_PATH", resolve_download_path(plan))

    # 兼容 ${ENV_xxx} 占位符：若命令里用了 ENV_ 前缀但用户只填了裸 key，则同步一份
    try:
        current_mapping = json.loads(plan.env_mapping) if isinstance(plan.env_mapping, str) and plan.env_mapping not in ("{}", "[]") else {}
    except Exception:
        current_mapping = {}
    for _k, _v in list(mapping.items()):
        if _k.startswith("ENV_"):
            mapping.setdefault(_k[4:], _v)
        else:
            mapping.setdefault(f"ENV_{_k}", _v)
    for _k in list(current_mapping.keys()):
        if _k.startswith("ENV_") and _k not in mapping:
            mapping.setdefault(_k, current_mapping.get(_k, ""))

    plan.env_mapping = json.dumps(mapping, ensure_ascii=False)
    plan.status = "planned"
    db.commit()
    return {"ok": True, "env_mapping": mapping}


_GIT_HOST_HINTS = ("github.com", "gitee.com", "gitlab.com", "gitcode.com", "jihulab.com", ".git")


# ─── 原 L1161-1234 ───
def run_preflight(db: Session, plan_id: int) -> dict:
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}

    assets = _get_assets(db, plan)
    if not assets:
        return {"error": "计划未关联目标资产"}

    sop = json.loads(plan.sop_json or "{}")
    if isinstance(sop, list):
        sop = {"preflight": [], "steps": []}
    mapping = json.loads(plan.env_mapping or "{}")
    preflight_checks = sop.get("preflight", [])
    if not preflight_checks:
        plan.preflight_json = json.dumps({"skipped": True, "message": "无预检项"})
        db.commit()
        return {"ok": True, "results": [], "skipped": True}

    _sync_env_mapping_from_sop(db, plan)
    mapping = json.loads(plan.env_mapping or "{}")

    all_results = []
    all_ok = True
    unresolved = set()
    for check in preflight_checks:
        cmd = _resolve_command(check.get("command", ""), mapping)
        missing = _check_unresolved(cmd)
        if missing:
            unresolved.add(missing)
    if unresolved:
        return {"error": f"环境参数未设置，请先在环境映射 Tab 中填写: {', '.join(sorted(unresolved))}"}
    for asset in assets:
        try:
            client, host = _ssh_connect(asset)
        except Exception as e:
            all_results.append({"asset": asset.name, "asset_ip": asset.ip, "error": str(e)})
            all_ok = False
            continue

        try:
            for check in preflight_checks:
                cmd = _resolve_command(check.get("command", ""), mapping)
                expect = check.get("expect", "")
                try:
                    stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
                    exit_code = stdout.channel.recv_exit_status()
                    output = stdout.read().decode("utf-8", errors="replace").strip()
                    error = stderr.read().decode("utf-8", errors="replace").strip()
                    if error:
                        output = f"{output}\n{error}" if output else error
                    passed = exit_code == 0
                    all_results.append({
                        "asset": asset.name, "asset_ip": asset.ip,
                        "check": check.get("check", ""), "command": cmd,
                        "expect": expect, "output": output[:500],
                        "exit_code": exit_code, "passed": passed,
                    })
                    if not passed:
                        all_ok = False
                except Exception as e:
                    all_results.append({
                        "asset": asset.name, "asset_ip": asset.ip,
                        "check": check.get("check", ""), "command": cmd,
                        "expect": expect, "output": str(e), "exit_code": -1, "passed": False,
                    })
                    all_ok = False
        finally:
            client.close()

    preflight_result = {"results": all_results, "all_passed": all_ok}
    plan.preflight_json = json.dumps(preflight_result, ensure_ascii=False)
    db.commit()
    return {"ok": True, "results": all_results, "all_passed": all_ok}


