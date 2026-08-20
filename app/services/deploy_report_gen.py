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
    _ssh_connect,
)


# ─── 原 L3082-3156 ───
def post_deploy_verify(db: Session, plan_id: int) -> dict:
    """部署后验证：在目标机上运行健康检查，返回测试记录。"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    assets = _get_assets(db, plan)
    if not assets:
        return {"error": "计划未关联目标资产"}
    mapping = json.loads(plan.env_mapping or "{}")
    all_tests = []
    all_passed = True
    for asset in assets:
        try:
            client, host = _ssh_connect(asset)
        except Exception as e:
            all_tests.append({"asset": asset.name, "ip": asset.ip, "tests": [{"name": "SSH连接", "passed": False, "detail": str(e)}]})
            all_passed = False
            continue
        try:
            asset_tests = []
            def _verify(cmd, name, expect_ok=True):
                try:
                    _s, _o, _e = client.exec_command(cmd, timeout=15)
                    _rc = _o.channel.recv_exit_status()
                    _out = _o.read().decode(errors="replace").strip()
                    _err = _e.read().decode(errors="replace").strip()
                    _detail = _out or _err
                    _passed = (_rc == 0) if expect_ok else True
                    return {"name": name, "passed": _passed, "exit_code": _rc, "detail": _detail[:500], "command": cmd}
                except Exception as ex:
                    return {"name": name, "passed": False, "detail": str(ex)[:300], "command": cmd}
            # 1. Docker 守护进程
            asset_tests.append(_verify("docker info --format '{{.ServerVersion}}'", "Docker 守护进程"))
            # 2. 容器运行状态
            asset_tests.append(_verify("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'", "容器运行状态"))
            # 2b. 检查是否有容器在重启循环
            _restart_check = _verify("docker ps -a --filter status=restarting --format '{{.Names}}' | head -5 || echo 'NONE'", "容器重启检查", expect_ok=False)
            if _restart_check.get("detail", "") and "NONE" not in _restart_check.get("detail", ""):
                _restart_check["passed"] = False
                _restart_check["detail"] = f"容器在重启循环: {_restart_check['detail']}"
            else:
                _restart_check["passed"] = True
                _restart_check["detail"] = "无容器重启循环"
            asset_tests.append(_restart_check)
            # 3. Compose 服务状态（如果存在）
            app_dir = mapping.get("APP_DIR", "")
            if app_dir:
                _compose_cmd = f"cd {app_dir} && docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"
                asset_tests.append(_verify(_compose_cmd, "Compose 服务状态"))
            # 4. 端口监听
            _ports_to_check = []
            if mapping.get("TARGET_PORT"):
                _ports_to_check.append(mapping["TARGET_PORT"])
            _steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id, DeployStep.status == "succeeded").all()
            for _s in _steps:
                for _m in re.finditer(r'(\d{2,5})', _s.command or ""):
                    _p = int(_m.group(1))
                    if 80 <= _p <= 65535 and _p not in _ports_to_check:
                        _ports_to_check.append(str(_p))
            for _p in _ports_to_check[:5]:
                asset_tests.append(_verify(f"ss -tlnp | grep ':{_p} ' || echo 'NOT_LISTENING'", f"端口 {_p}", expect_ok=False))
            # 5. HTTP 健康检查
            if mapping.get("TARGET_PORT"):
                _hp = mapping["TARGET_PORT"]
                asset_tests.append(_verify(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{_hp} 2>/dev/null || echo 'FAIL'", f"HTTP GET :{_hp}"))
            all_tests.append({"asset": asset.name, "ip": asset.ip, "tests": asset_tests})
            for _t in asset_tests:
                if not _t["passed"]:
                    all_passed = False
        finally:
            client.close()
    result = {"tests": all_tests, "all_passed": all_passed}
    plan.test_results_json = json.dumps(result, ensure_ascii=False)
    db.commit()
    return {"ok": True, "result": result}


# ─── 原 L3159-3265 ───
def _extract_deploy_info(plan, assets, probe, mapping, sop, steps) -> dict:
    """从部署计划/环境探查/步骤中提取「交付级」运维信息：
    部署架构、启停服务命令、部署路径、服务端口、访问方式、登录信息。
    """
    info = {
        "architecture": "",
        "start_stop_commands": [],
        "deploy_paths": [],
        "service_ports": [],
        "access_methods": [],
        "login_info": [],
    }

    # ── 登录信息 ──
    for a in assets:
        try:
            conn = json.loads(a.connection_config or "{}")
        except Exception:
            conn = {}
        user = conn.get("ssh_user", "root")
        port = conn.get("ssh_port", 22)
        ip = a.ip or conn.get("ssh_host", "")
        info["login_info"].append({
            "asset": a.name, "ip": ip, "user": user, "port": port,
            "method": f"ssh {user}@{ip} -p {port}",
        })

    # ── 部署路径：从环境映射(APP_DIR 等) + 探查目录 ──
    if mapping:
        for k, v in mapping.items():
            if not v or not isinstance(v, str):
                continue
            if any(t in k.upper() for t in ("APP_DIR", "PATH", "DIR", "CONFIG", "LOG_DIR", "DATA_DIR")):
                info["deploy_paths"].append(f"{k} = {v}")
    if isinstance(probe, dict):
        for d in probe.get("dirs", {}):
            if not d.startswith("[probe_error]"):
                info["deploy_paths"].append(str(d))
        for _k in ("APP_DIR",):
            if mapping and mapping.get(_k):
                info["deploy_paths"].append(f"{_k} = {mapping.get(_k)}")

    # ── 服务端口：探查端口扫描 + 环境映射 TARGET_PORT + 步骤中的端口 ──
    if isinstance(probe, dict) and probe.get("port_scan"):
        for p, st in probe["port_scan"].items():
            if st == "IN_USE":
                info["service_ports"].append(f"{p} (占用)")
    if mapping and mapping.get("TARGET_PORT"):
        info["service_ports"].append(f"{mapping['TARGET_PORT']} (应用端口)")
    for s in steps:
        for _m in re.finditer(r'(?:EXPOSE|docker\s+-p|\-p\s+)(\d{2,5})', s.command or ""):
            _p = _m.group(1)
            if _p not in [x.split(" ")[0] for x in info["service_ports"]]:
                info["service_ports"].append(f"{_p}")

    # ── 启停服务命令：从步骤命令自动识别 ──
    all_cmds = "\n".join([(s.command or "") + "\n" + (s.rollback_command or "") for s in steps]) + "\n" + str(sop.get("steps", ""))
    _app_dir = (mapping or {}).get("APP_DIR", "")
    _compose_base = f"cd {_app_dir} && " if _app_dir else ""
    if "docker compose" in all_cmds or "docker-compose" in all_cmds:
        info["start_stop_commands"] = [
            f"启动: {_compose_base}docker compose up -d",
            f"停止: {_compose_base}docker compose down",
            f"重启: {_compose_base}docker compose restart",
            f"日志: {_compose_base}docker compose logs -f",
        ]
    if "systemctl" in all_cmds:
        _svc = re.search(r'systemctl\s+(?:start|stop|restart|enable)\s+([\w.-]+)', all_cmds)
        if _svc:
            info["start_stop_commands"].append(f"systemctl 服务: {_svc.group(1)}")
    if "docker run" in all_cmds:
        info["start_stop_commands"].append("容器运行: docker run (见步骤命令)")
    # 从步骤中抓取 docker compose 具体服务名
    _compose_services = set(re.findall(r'docker\s+compose\s+[a-z-]+\s+([\w-]+)', all_cmds))
    if _compose_services:
        info["start_stop_commands"].append(f"Compose 服务: {', '.join(sorted(_compose_services))}")
    if not info["start_stop_commands"]:
        info["start_stop_commands"] = ["见执行步骤命令"]

    # ── 访问方式 ──
    _ip = assets[0].ip if assets else ""
    _port = (mapping or {}).get("TARGET_PORT", "")
    if _ip:
        if _port:
            info["access_methods"].append(f"HTTP: http://{_ip}:{_port}")
        else:
            info["access_methods"].append(f"SSH: ssh root@{_ip}")
    # 从步骤 verify 中抓取 URL
    for s in steps:
        for _m in re.finditer(r'(?:curl|wget)\s+(-s\s+)?["\']?http://([^\s"\']+)', s.command or ""):
            info["access_methods"].append(f"{_m.group(2)}")

    # ── 部署架构：基于容器拓扑 + compose 服务 + 步骤描述 ──
    arch_parts = []
    if isinstance(probe, dict) and probe.get("containers"):
        arch_parts.append(f"当前容器: {probe.get('containers', '')[:200]}")
    for s in steps:
        if s.description and ("服务" in s.description or "启动" in s.description or "部署" in s.description or "compose" in (s.command or "").lower()):
            arch_parts.append(f"步骤{s.step_order}: {s.description} ({s.command[:80]})")
    info["architecture"] = "\n".join(arch_parts) if arch_parts else "无容器拓扑信息"

    # 去重
    info["deploy_paths"] = list(dict.fromkeys(info["deploy_paths"]))[:10]
    info["service_ports"] = list(dict.fromkeys(info["service_ports"]))[:10]
    info["start_stop_commands"] = list(dict.fromkeys(info["start_stop_commands"]))[:8]
    info["access_methods"] = list(dict.fromkeys(info["access_methods"]))[:5]
    return info


# ─── 原 L3268-3487 ───
def generate_deploy_report(db: Session, plan_id: int, template_id: int = 0) -> dict:
    """AI 生成专业部署报告：可直接交付客户的版本。

    产出包含：执行摘要、环境信息、部署时间线、步骤日志、预检结果、验证结果、
    AI 决策日志、风险评估、改进建议、总体评估。
    template_id: 知识库文档 ID, 可选。若指定则以其内容作为报告风格/结构参考。
    """
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    assets = _get_assets(db, plan)
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan_id).order_by(DeployStep.step_order).all()
    preflight = _safe_json(plan.preflight_json)
    test_results = _safe_json(plan.test_results_json)
    env_analysis = _safe_json(plan.env_analysis_json)
    probe = _safe_json(plan.environment_probe_json)
    mapping = _safe_json(plan.env_mapping)
    sop = _safe_json(plan.sop_json)
    history = _safe_json(plan.execution_history_json)
    dag = _safe_json(plan.dag_json)
    decision_log = _safe_json(plan.ai_decision_log_json)
    if not isinstance(history, list):
        history = []
    if not isinstance(decision_log, list):
        decision_log = []
    provider = _get_provider(db)

    _asset_info = [{"name": a.name, "ip": a.ip, "ci_type": a.ci_type} for a in assets] if assets else []
    deploy_info = _extract_deploy_info(plan, assets, probe, mapping, sop, steps)
    step_summary = []
    for s in steps:
        started = s.started_at.isoformat() if s.started_at else ""
        finished = s.finished_at.isoformat() if s.finished_at else ""
        duration = ""
        if s.started_at and s.finished_at:
            _secs = int((s.finished_at - s.started_at).total_seconds())
            if _secs >= 3600:
                duration = f"{_secs // 3600}h{(_secs % 3600) // 60}m{_secs % 60}s"
            elif _secs >= 60:
                duration = f"{_secs // 60}m{_secs % 60}s"
            else:
                duration = f"{_secs}s"
        step_summary.append({
            "order": s.step_order, "description": s.description,
            "command": s.command or "", "verify_command": s.verify_command or "",
            "rollback_command": s.rollback_command or "",
            "risk_level": s.risk_level, "status": s.status,
            "output": (s.output or "")[:2000],
            "diagnosis": s.diagnosis or "",
            "fix_command": s.fix_command or "",
            "retry_count": s.retry_count or 0,
            "precheck_result": s.precheck_result or "",
            "started_at": started, "finished_at": finished, "duration": duration,
        })

    preflight_detail = []
    _preflight_all_passed = False
    if isinstance(preflight, dict):
        _preflight_all_passed = bool(preflight.get("all_passed")) if "all_passed" in preflight else None
        # 兼容两种结构：预检接口写 {results:[...], all_passed}，execute 资源检查写 {checks:[...], passed}
        _pf_items = preflight.get("results", []) or preflight.get("checks", []) or []
        if not _pf_items and "passed" in preflight:
            _pf_items = [{"check": "资源检查", "passed": bool(preflight.get("passed")),
                          "command": "", "expect": "", "output": preflight.get("summary", ""), "exit_code": 0}]
        for _r in _pf_items:
            preflight_detail.append({
                "asset": _r.get("asset", ""), "check": _r.get("check", "") or _r.get("name", ""),
                "command": _r.get("command", ""), "expect": _r.get("expect", ""),
                "output": (_r.get("output", "") or "")[:300],
                "exit_code": _r.get("exit_code", -1), "passed": _r.get("passed", False),
            })
        # 缺省 all_passed 时按全部结果项推断（无结果项且无 all_passed → False）
        if _preflight_all_passed is None:
            _preflight_all_passed = bool(preflight_detail) and all(r["passed"] for r in preflight_detail)

    test_detail = []
    _test_all_passed = False
    if isinstance(test_results, dict):
        _test_all_passed = bool(test_results.get("all_passed")) if "all_passed" in test_results else None
        for _t_asset in test_results.get("tests", []):
            _a_name = _t_asset.get("asset", "")
            _a_ip = _t_asset.get("ip", "")
            for _t in _t_asset.get("tests", []):
                test_detail.append({
                    "asset": _a_name, "ip": _a_ip,
                    "name": _t.get("name", ""), "passed": _t.get("passed", False),
                    "detail": (_t.get("detail", "") or "")[:300],
                    "exit_code": _t.get("exit_code", -1),
                })
        if _test_all_passed is None:
            _test_all_passed = bool(test_detail) and all(t["passed"] for t in test_detail)

    if provider:
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

        sys_prompt = (
            "你是一名资深 SRE 运维专家，负责根据部署执行结果生成专业的、可直接交付客户的部署报告(Deployment Report)。\n"
            "报告必须专业、详尽、数据准确，包含具体指标和运维交付信息。\n"
            "请严格按以下 JSON Schema 输出，不要任何额外内容：\n"
            "{\n"
            '  "title": "部署报告标题",\n'
            '  "executive_summary": "执行摘要（中文，5-8句话，包含：部署目标、范围、结果、关键指标、风险评估）",\n'
            '  "deployment_architecture": "部署架构描述（中文，说明服务拓扑、组件依赖关系、部署模式(单机/集群/容器化)）",\n'
            '  "start_stop_commands": "启停服务命令（中文，提供完整的启动/停止/重启/查看日志命令，含路径前缀）",\n'
            '  "deploy_paths": "部署路径（中文，列出所有关键路径：应用目录、配置文件、日志目录、数据目录）",\n'
            '  "service_ports": "服务端口表（中文，说明每个端口的用途：如 8080(应用HTTP)、6379(Redis)等）",\n'
            '  "access_methods": "访问方式（中文，提供完整的访问URL、SSH命令、Web界面地址）",\n'
            '  "login_info": "登录信息（中文，说明如何登录目标服务器：SSH用户、IP、端口、密钥方式）",\n'
            '  "environment": {\n'
            '    "os": "操作系统版本",\n'
            '    "kernel": "内核版本",\n'
            '    "docker": "Docker 版本",\n'
            '    "disk": "磁盘使用情况",\n'
            '    "key_ports": "关键端口及状态",\n'
            '    "notes": "环境说明"\n'
            '  },\n'
            '  "timeline": "部署时间线概述（中文，描述整体执行耗时、每步耗时、是否有延迟）",\n'
            '  "steps_table": "步骤执行结果表格（markdown格式，包含序号、描述、耗时、状态、重试次数、诊断）",\n'
            '  "key_observations": ["关键观察1", "关键观察2"],\n'
            '  "verification": "部署验证结果（中文，详细描述每项检查的结果）",\n'
            '  "test_results": "测试记录摘要（中文，通过/失败项数、关键失败原因）",\n'
            '  "issues": [\n'
            '    {"severity": "high/medium/low", "description": "问题描述", "resolution": "如何处理", "status": "resolved/unresolved"}\n'
            '  ],\n'
            '  "risk_assessment": "风险评估（中文，分析当前部署的潜在风险）",\n'
            '  "recommendations": ["建议1", "建议2", "建议3"],\n'
            '  "overall_assessment": "总体评估（中文，succeeded/failed/partial，附一句话总结）"\n'
            "}\n"
            "关键要求：\n"
            "- 报告必须包含具体数据（IP、版本号、时长、端口号、路径、命令等），不能泛泛而谈\n"
            "- deployment_architecture 必须基于步骤描述和容器拓扑信息，描述服务部署模式\n"
            "- start_stop_commands 必须给出可直接复制的命令，包含 cd 路径前缀\n"
            "- login_info 必须给出具体的 SSH 登录命令和用户名\n"
            "- access_methods 必须给出完整的 URL 或 IP:端口\n"
            "- 如果存在失败步骤，必须在 issues 中详细分析根因和解决方案\n"
            "- 如果存在 AI 决策（skip/fix/rollback），必须在 issues 中记录\n"
            "- steps_table 必须包含所有步骤的执行状态、耗时、重试次数\n"
            "- 报告要专业、可读性强，能直接拿给客户或上级看"
        )
        if template_content:
            sys_prompt += (
                "\n\n## 部署报告风格模板(参考此模板的组织结构/章节顺序/措辞风格, 数据仍来自本次部署):\n"
                f"{template_content}"
            )
        user_prompt = (
            f"## 部署计划\n名称: {plan.name}\n描述: {plan.description or '无'}\n"
            f"状态: {plan.status}\n创建时间: {plan.created_at.isoformat() if plan.created_at else '未知'}\n"
            f"部署次数: {plan.deploy_count or 0}\n"
            f"最后部署: {plan.last_deployed_at.isoformat() if plan.last_deployed_at else '首次'}\n\n"
            f"## 目标资产\n{json.dumps(_asset_info, ensure_ascii=False, indent=1)}\n\n"
            f"## 环境探查结果\nOS: {probe.get('os', '')[:100] if isinstance(probe, dict) else '无'}\n"
            f"Kernel: {probe.get('kernel', '')[:100] if isinstance(probe, dict) else '无'}\n"
            f"Docker: {probe.get('docker', '')[:50] if isinstance(probe, dict) else '无'}\n"
            f"Disk: {probe.get('disk', '')[:80] if isinstance(probe, dict) else '无'}\n"
            f"Port scan: {json.dumps(probe.get('port_scan', {}), ensure_ascii=False)[:200] if isinstance(probe, dict) else '无'}\n\n"
            f"## 环境映射\n{json.dumps(mapping, ensure_ascii=False, indent=1) if mapping else '无'}\n\n"
            f"## 提取的运维信息（供参考）\n"
            f"部署路径: {json.dumps(deploy_info['deploy_paths'], ensure_ascii=False)}\n"
            f"服务端口: {json.dumps(deploy_info['service_ports'], ensure_ascii=False)}\n"
            f"启停命令: {json.dumps(deploy_info['start_stop_commands'], ensure_ascii=False)}\n"
            f"访问方式: {json.dumps(deploy_info['access_methods'], ensure_ascii=False)}\n"
            f"登录信息: {json.dumps(deploy_info['login_info'], ensure_ascii=False)}\n"
            f"容器拓扑: {(probe.get('containers', '')[:200] if isinstance(probe, dict) else '无')}\n\n"
            f"## 执行步骤（{len(step_summary)} 步）\n{json.dumps(step_summary, ensure_ascii=False, indent=1)}\n\n"
            f"## 预检结果\nall_passed: {_preflight_all_passed}\n"
            f"预检项: {json.dumps(preflight_detail, ensure_ascii=False, indent=1)[:2000]}\n\n"
            f"## 部署后验证\nall_passed: {_test_all_passed}\n"
            f"验证项: {json.dumps(test_detail, ensure_ascii=False, indent=1)[:2000]}\n\n"
            f"## AI 自适应建议\n{json.dumps(env_analysis.get('adaptations', []), ensure_ascii=False, indent=1) if isinstance(env_analysis, dict) else '[]'}\n\n"
            f"## AI 决策日志\n{json.dumps(decision_log, ensure_ascii=False, indent=1)}\n\n"
            f"## DAG 执行计划\n{json.dumps(dag, ensure_ascii=False, indent=1)}\n\n"
            f"请生成专业、详尽、可直接交付的部署报告。"
        )
        try:
            resp = call_llm(provider, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ], timeout_override=120)
            if not resp.get("error"):
                try:
                    content = resp["choices"][0]["message"]["content"]
                    report = _extract_json(content) or {}
                except Exception:
                    report = {}
            else:
                report = {}
        except Exception:
            report = {}
    else:
        report = {}

    if not report.get("executive_summary"):
        report = _generate_fallback_report(plan, step_summary, _asset_info, preflight_detail, test_detail, deploy_info)

    report["plan_name"] = plan.name
    report["status"] = plan.status
    report["deployed_at"] = datetime.now().isoformat()
    report["plan_id"] = plan.id
    report["deploy_count"] = plan.deploy_count or 0
    report["total_steps"] = len(step_summary)
    report["succeeded_steps"] = sum(1 for s in step_summary if s["status"] == "succeeded")
    report["failed_steps"] = sum(1 for s in step_summary if s["status"] == "failed")
    report["skipped_steps"] = sum(1 for s in step_summary if s["status"] == "skipped")
    report["total_assets"] = len(_asset_info)
    report["preflight_passed"] = _preflight_all_passed
    report["verification_passed"] = _test_all_passed
    report["ai_decisions"] = len(decision_log)

    plan.deploy_report_json = json.dumps(report, ensure_ascii=False)
    db.commit()
    return {"ok": True, "report": report}


# ─── 原 L3490-3510 ───
def download_report(db: Session, plan_id: int, fmt: str = "docx") -> dict:
    """下载部署报告：docx(Word) / html 两种格式。
    返回 {"ok": True, "content": bytes, "filename": "...", "mime": "..."}。
    """
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"error": "计划不存在"}
    report = _safe_json(plan.deploy_report_json)
    if not report or not isinstance(report, dict) or not report.get("executive_summary"):
        return {"error": "报告尚未生成，请先执行「生成报告」"}

    fmt = fmt.lower()

    if fmt == "html":
        content = _report_to_html(report).encode("utf-8")
        return {"ok": True, "content": content, "filename": f"deploy_report_{plan_id}.html", "mime": "text/html; charset=utf-8"}
    elif fmt == "docx":
        content = _report_to_docx(report)
        return {"ok": True, "content": content, "filename": f"deploy_report_{plan_id}.docx", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    else:
        return {"error": f"不支持的格式: {fmt}，支持 docx/html"}


# ─── 原 L3513-3533 ───
def _record_execution_history(db: Session, plan: DeployPlan, status: str, summary: dict) -> None:
    """记录执行历史到 plan.execution_history_json。"""
    try:
        history = json.loads(plan.execution_history_json) if isinstance(plan.execution_history_json, str) and plan.execution_history_json not in ("[]", "") else []
    except Exception:
        history = []
    if not isinstance(history, list):
        history = []
    history.append({
        "executed_at": datetime.now().isoformat(),
        "status": status,
        "total_assets": summary.get("total_assets", 0),
        "succeeded_assets": summary.get("succeeded_assets", 0),
        "step_count": len(db.query(DeployStep).filter(DeployStep.plan_id == plan.id).all()),
    })
    if len(history) > 50:
        history = history[-50:]
    plan.execution_history_json = json.dumps(history, ensure_ascii=False)
    plan.last_deployed_at = datetime.now()
    plan.deploy_count = (plan.deploy_count or 0) + 1
    db.commit()


# ─── 原 L3536-3551 ───
def _record_cleanup_history(db: Session, plan: DeployPlan, records: list, app_dir: str = "") -> None:
    """记录回滚清理历史到 plan.cleanup_history_json，便于事后查看每次清理的日志。"""
    try:
        history = json.loads(plan.cleanup_history_json) if isinstance(plan.cleanup_history_json, str) and plan.cleanup_history_json not in ("[]", "") else []
    except Exception:
        history = []
    if not isinstance(history, list):
        history = []
    history.append({
        "cleaned_at": datetime.now().isoformat(),
        "assets": records,
        "app_dir": app_dir,
    })
    if len(history) > 20:
        history = history[-20:]
    plan.cleanup_history_json = json.dumps(history, ensure_ascii=False)


