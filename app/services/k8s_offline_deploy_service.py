"""K8S 离线集群部署服务 — 拆分后门面。

子模块:
  - k8s_offline_common.py     常量/状态/基础工具(共享)
  - k8s_offline_runtime.py    执行步骤 + docker 运行时
  - k8s_offline_generator.py  七阶段部署编排 + 报告/落库/AI预检
本文件保留 CRUD/编排/公共 API 并 re-export 全部符号, 保持对外接口不变。
"""
import json

import os
import time
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,
                        OfflineRepoBundle, OfflineRegistry, Asset)
from app.logger import logger
from app.services import offline_repo_service
from app.services.ssh_helper import connect_ssh
import threading as _threading


# ─── 从子模块 re-export(门面, 状态为共享同一对象) ───
from app.services.k8s_offline_common import (  # noqa: F401
    _PROJECT_ROOT, EXTRACT_ROOT, _DEFAULT_CNI_FILES, _CNI_POD_CIDR,
    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,
    _ACTIVE_CHANNELS_LOCK,
    _current_plan_id, _register_channel, _unregister_channel,
    _interrupt_plan_channels, _await_k8s_decision, _DeployStopped,
    _now, _human, _safe_json, _parse_cert_expiry, _k8s_ai_provider,
    _k8s_ai_call, _plan_to_dict, _node_to_dict, _append_log,
    _set_pending_decision, _get_assets, _resolve_node_conn,
    stop_execution, _release_exec, _check_stop,
)
from app.services.k8s_offline_runtime import (  # noqa: F401
    _get_bundle_context, _parse_ctl_rc, _run_remote, _iter_remote,
    _use_stop_guard, _check_stop_remote, _spawn_stop_guard,
    _sftp_put, _exec_ssh_db, _inject_etc_hosts, _disable_swap,
    _setup_kernel, _set_hostname, _node_hostname, _ensure_dns,
    _grant_admin_clusteradmin, _keepalive_check_stopped,
    _ensure_core_addons, _fix_cni_kubeconfig_localhost, _ensure_cni_plugins,
    _install_cilium, _normalize_k8s_version, _install_preflight_deps,
    _probe_node_environment, _install_k8s_binaries,
    _generate_kubeadm_config, _write_imagetar_jobs,
    _configure_insecure_registry, _apply_cert_expiry,
    _cert_days_remaining_check, _extract_yaml_images, _check_cni_pods,
)
from app.services.k8s_offline_docker import (  # noqa: F401
    _proxy_env_script, _remote_arch, _containerd_config_script,
    _configure_containerd_net, _docker_daemon_json, _install_docker,
    _configure_docker, _install_containerd, _containerd_version_for,
    _install_containerd_online, _start_containerd_service,
    _ensure_containerd_unit,
)
from app.services.k8s_offline_generator import (  # noqa: F401
    _run_deploy_generator, _ai_failure_diagnosis, _build_report,
    _ai_report_summary, _create_platform_datasource, _sync_k8s_deploy_plan,
    _k8s_preflight_ai, _k8s_preflight_rules, _k8s_failure_diagnosis,
    _k8s_decision_options,
)

# ─── 原 L293-340 ───
def create_plan(db: Session, payload: dict, user_id: int = 0) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("集群名称必填")
    nodes = payload.get("nodes") or payload.get("nodes_json") or []
    if isinstance(nodes, str):
        nodes = _safe_json(nodes, [])
    masters = [n for n in nodes if n.get("host_role") == "master"]
    if not masters:
        raise ValueError("至少需要一个 master 节点")
    plan = K8sClusterPlan(
        name=name,
        kubernetes_version=payload.get("kubernetes_version", "").strip(),
        runtime=payload.get("runtime", "containerd"),
        cni=payload.get("cni", "calico"),
        pod_cidr=payload.get("pod_cidr", "") or _CNI_POD_CIDR.get(payload.get("cni", "calico"), "10.244.0.0/16"),
        service_cidr=payload.get("service_cidr", "") or "10.96.0.0/12",
        image_repository=payload.get("image_repository", "").strip(),
        bundle_id=payload.get("bundle_id"),
        registry_id=payload.get("registry_id"),
        http_proxy=(payload.get("http_proxy") or "").strip(),
        https_proxy=(payload.get("https_proxy") or "").strip(),
        no_proxy=(payload.get("no_proxy") or "").strip() or "127.0.0.1,localhost,.local",
        cert_expiry_years=_parse_cert_expiry(payload.get("cert_expiry_years")),
        untaint_master=bool(payload.get("untaint_master", False)),
        nodes_json=json.dumps(nodes, ensure_ascii=False),
        status="draft",
        created_by=user_id,
    )
    db.add(plan)
    db.flush()
    for n in nodes:
        db.add(K8sClusterNode(
            plan_id=plan.id,
            asset_id=n.get("asset_id"),
            host_role=n.get("host_role", "worker"),
            ip=n.get("ip", "").strip(),
            hostname=n.get("hostname", "").strip(),
            username=n.get("username", "").strip(),
            password=n.get("password", "") or "",
            has_password=bool(n.get("password")),
            ssh_port=int(n.get("ssh_port", 22) or 22),
            status="pending",
            init_roles=n.get("init_roles", ""),
        ))
    db.commit()
    db.refresh(plan)
    return get_plan(db, plan.id)


# ─── 原 L343-354 ───
def get_plan(db: Session, plan_id: int, include_kubeconfig: bool = False) -> Optional[dict]:
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return None
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).order_by(
        K8sClusterNode.id,
    ).all()
    nodes = sorted(nodes, key=lambda n: 0 if n.host_role == "master" else 1)
    d = _plan_to_dict(p, include_kubeconfig=include_kubeconfig)
    d["nodes"] = [_node_to_dict(n, include_password=include_kubeconfig) for n in nodes]
    d["logs"] = _safe_json(p.logs_json, [])
    return d


# ─── 原 L357-369 ───
def list_plans(db: Session, status: str = "", page: int = 1, per_page: int = 20) -> dict:
    q = db.query(K8sClusterPlan)
    if status:
        q = q.filter(K8sClusterPlan.status == status)
    total = q.count()
    items = q.order_by(K8sClusterPlan.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    result = []
    for p in items:
        node_count = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == p.id).count()
        d = _plan_to_dict(p)
        d["node_count"] = node_count
        result.append(d)
    return {"items": result, "total": total, "page": page, "per_page": per_page}


# ─── 原 L372-425 ───
def update_plan(db: Session, plan_id: int, payload: dict) -> Optional[dict]:
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return None
    if p.status in ("running", "loading"):
        raise ValueError("集群部署进行中，不能修改")
    if "name" in payload and payload["name"].strip():
        p.name = payload["name"].strip()
    for f in ("kubernetes_version", "runtime", "cni", "image_repository"):
        if f in payload:
            setattr(p, f, str(payload[f] or ""))
    if "pod_cidr" in payload and payload["pod_cidr"]:
        p.pod_cidr = payload["pod_cidr"]
    if "service_cidr" in payload and payload["service_cidr"]:
        p.service_cidr = payload["service_cidr"]
    if "bundle_id" in payload:
        p.bundle_id = payload["bundle_id"] or None
    if "registry_id" in payload:
        p.registry_id = payload["registry_id"] or None
    if "http_proxy" in payload:
        p.http_proxy = (payload.get("http_proxy") or "").strip()
    if "https_proxy" in payload:
        p.https_proxy = (payload.get("https_proxy") or "").strip()
    if "no_proxy" in payload:
        p.no_proxy = (payload.get("no_proxy") or "").strip() or "127.0.0.1,localhost,.local"
    if "untaint_master" in payload:
        p.untaint_master = bool(payload["untaint_master"])
    if "cert_expiry_years" in payload:
        p.cert_expiry_years = _parse_cert_expiry(payload["cert_expiry_years"])
    # 节点更新：整体替换
    if payload.get("nodes"):
        db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).delete()
        nodes = payload["nodes"]
        if isinstance(nodes, str):
            nodes = _safe_json(nodes, [])
        masters = [n for n in nodes if n.get("host_role") == "master"]
        if not masters:
            raise ValueError("至少需要一个 master 节点")
        for n in nodes:
            db.add(K8sClusterNode(
                plan_id=plan_id,
                asset_id=n.get("asset_id"),
                host_role=n.get("host_role", "worker"),
                ip=n.get("ip", "").strip(),
                hostname=n.get("hostname", "").strip(),
                username=n.get("username", "").strip(),
                password=n.get("password", "") or "",
                has_password=bool(n.get("password")),
                ssh_port=int(n.get("ssh_port", 22) or 22),
                init_roles=n.get("init_roles", ""),
            ))
        p.nodes_json = json.dumps(nodes, ensure_ascii=False)
    db.commit()
    return get_plan(db, plan_id)


# ─── 原 L428-437 ───
def delete_plan(db: Session, plan_id: int) -> bool:
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return False
    if p.status == "running":
        raise ValueError("部署进行中，请先停止")
    db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).delete()
    db.delete(p)
    db.commit()
    return True


# ─── 原 L2911-2953 ───
def run_deploy(db: Session, plan_id: int, decision_queue=None):
    """集群部署入口(生成器，供 WS/SSE 流式推送)。支持从 stopped 状态断点续传。
    decision_queue: 可选，AI 诊断失败时接收用户决策(fix/retry/skip/rollback)的队列。"""
    if _EXEC_LOCK.get(plan_id):
        yield {"type": "error", "message": "该集群正在部署中，请勿重复触发"}
        return
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        yield {"type": "error", "message": "集群计划不存在"}
        return
    if p.status == "running":
        yield {"type": "error", "message": "该集群正在部署中"}
        return
    resume = (p.status == "stopped" and p.current_step > 0)
    _EXEC_LOCK[plan_id] = True
    _STOPPED.pop(plan_id, None)
    # 新部署开始时清理残留决策卡片(该计划专属, 各行其是)
    _set_pending_decision(p, db, None)
    # 标记当前线程所属 plan，使 _run_remote 的停止 watchdog 能感知本计划停止
    _TLOCAL.plan_id = plan_id
    if decision_queue is not None:
        K8S_DECISIONS[plan_id] = decision_queue
    try:
        if resume:
            _append_log(p, {"type": "info", "message": f"断点续传：从阶段{p.current_step}继续(已完成阶段幂等跳过)"}, db)
            yield {"type": "log", "message": f"断点续传：从阶段{p.current_step}继续"}
        # 落库追溯: 创建/复用 DeployPlan + DeployStep 阶段记录
        try:
            _dp_id = _sync_k8s_deploy_plan(db, p)
            logger.info(f"K8S 计划 #{plan_id} 已同步 DeployPlan #{_dp_id} 用于追溯")
        except Exception as _e:
            logger.warning(f"K8S DeployPlan 同步失败(不影响部署): {_e}")
        yield from _run_deploy_generator(db, p, plan_id, resume_step=p.current_step if resume else 0,
                                         decision_queue=decision_queue)
    finally:
        _release_exec(plan_id)
        _interrupt_plan_channels(plan_id)
        _STOPPED.pop(plan_id, None)
        K8S_DECISIONS.pop(plan_id, None)
        try:
            _TLOCAL.plan_id = None
        except Exception:
            pass


# ─── 原 L2956-2973 ───
def submit_decision(db: Session, plan_id: int, choice: str = "") -> dict:
    """用户决策提交力(HTTP 接口)：将 choice 投递到该计划当前活跃的决策队列，
    并清空该计划持久化的决策卡片。若该计划无进行中的部署，返回错误提示。"""
    choice = (choice or "").strip().lower()
    if not choice:
        return {"ok": False, "message": "决策不能为空"}
    q = K8S_DECISIONS.get(plan_id)
    if q is None:
        return {"ok": False, "message": "该计划当前无进行中的部署，无需决策（可点「继续部署」续传）"}
    try:
        q.put(choice)
    except Exception as e:
        return {"ok": False, "message": f"提交决策失败: {e}"}
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if p:
        _append_log(p, {"type": "ai", "message": f"用户通过详情页提交决策: {choice}"}, db)
        _set_pending_decision(p, db, None)
    return {"ok": True, "message": "决策已提交"}


# ─── 原 L2976-3010 ───
def validate_plan(db: Session, plan_id: int, test_ssh: bool = True) -> dict:
    """部署前校验：节点完整性 + 可选 SSH 连通性测试。"""
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return {"ok": False, "message": "计划不存在"}
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).all()
    masters = [n for n in nodes if n.host_role == "master"]
    issues = []
    if not masters:
        issues.append("缺少 master 节点")
    if not p.kubernetes_version:
        issues.append("未设置 K8S 版本")
    for n in nodes:
        conn = _resolve_node_conn(db, n)
        if not conn.get("ip") or not conn.get("username"):
            issues.append(f"节点 {n.ip or n.id} 缺少 IP/用户名")
    if test_ssh:
        ssh_results = []
        for n in nodes:
            label = f"{n.host_role}:{n.ip}"
            try:
                conn = _resolve_node_conn(db, n)
                client = connect_ssh(conn["ip"], port=conn["port"], username=conn["username"],
                                     password=conn["password"], timeout=10)
                r = _run_remote(client, "id -u", timeout=30)
                client.close()
                ssh_results.append({"node": label, "ok": True, "message": f"SSH ok, uid={r['stdout'].strip()}"})
            except Exception as e:
                ssh_results.append({"node": label, "ok": False, "message": str(e)})
        return {"ok": all(s["ok"] for s in ssh_results) and not issues,
                "issues": issues, "ssh": ssh_results}
    return {"ok": not issues, "issues": issues}


# 供逻辑预检(可带 SSH)使用


# ─── 原 L3011-3059 ───
def precheck_plan(db: Session, plan_id: int, test_ssh: bool = True) -> dict:
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return {"ok": False, "issues": ["计划不存在"], "checks": [{"name": "计划存在", "ok": False, "message": "计划不存在"}]}
    checks = []
    issues = []
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).all()

    def _add(name, ok, msg=""):
        checks.append({"name": name, "ok": ok, "message": msg})
        if not ok:
            issues.append(f"{name}: {msg}" if msg else name)

    _add("Master 节点", any(n.host_role == "master" for n in nodes), "至少需要一个 master 节点" if not any(n.host_role == "master" for n in nodes) else f"{sum(1 for n in nodes if n.host_role=='master')} 个 master, {sum(1 for n in nodes if n.host_role!='master')} 个 worker")
    _add("Pod CIDR", bool(p.pod_cidr), "未设置" if not p.pod_cidr else p.pod_cidr)
    _add("Service CIDR", bool(p.service_cidr), "未设置" if not p.service_cidr else p.service_cidr)
    _add("K8s 版本", bool(p.kubernetes_version), "未设置" if not p.kubernetes_version else p.kubernetes_version)
    for n in nodes:
        try:
            conn = _resolve_node_conn(db, n)
            if not conn.get("ip"):
                _add(f"节点(id={n.id}) IP", False, "缺少 IP")
            else:
                _add(f"节点 {n.host_role}:{conn.get('ip')} 配置", True, f"用户 {conn.get('username')} 端口 {conn.get('port')}")
        except ValueError as e:
            _add(f"节点(id={n.id}) 配置", False, str(e))
        except Exception:
            _add(f"节点(id={n.id}) 配置", False, "缺少 IP")
    if test_ssh:
        ssh_results = []
        for n in nodes:
            label = f"{n.host_role}:{n.ip}"
            try:
                conn = _resolve_node_conn(db, n)
                client = connect_ssh(conn["ip"], port=conn["port"], username=conn["username"],
                                     password=conn["password"], timeout=10)
                r = _run_remote(client, "id -u; which swapoff; uname -r", timeout=30)
                client.close()
                uid = (r["stdout"].splitlines() or [""])[0].strip()
                ok = uid == "0"
                _add(f"SSH 校验 {label}", ok, f"uid={uid}" if ok else f"非 root: {uid} | {r['stdout'][:80]}")
                ssh_results.append({"node": label, "ok": ok, "message": f"SSH ok, uid={uid}" if ok else str(r["stderr"][:120] or r["stdout"][:120])})
            except Exception as e:
                _add(f"SSH 校验 {label}", False, str(e))
                ssh_results.append({"node": label, "ok": False, "message": str(e)})
        return {"ok": not issues, "issues": issues, "checks": checks, "ssh": ssh_results,
                "ai_advice": _ai_precheck_advice(db, p, checks, issues)}
    return {"ok": not issues, "issues": issues, "checks": checks,
            "ai_advice": _ai_precheck_advice(db, p, checks, issues)}


# ─── 原 L3062-3081 ───
def _ai_precheck_advice(db: Session, p: K8sClusterPlan, checks: list, issues: list) -> dict:
    """预检阶段 AI 建议: 汇总检查项, 给出一句话结论 + 可操作建议(仅建议, 不执行)。"""
    fallback = {
        "ai_generated": False,
        "summary": f"预检完成: {len(checks)} 项检查" + (f", 发现 {len(issues)} 个问题" if issues else ", 通过"),
        "recommendations": issues or ["检查通过, 可直接开始部署"],
    }
    ok_count = sum(1 for c in checks if c.get("ok"))
    check_txt = "\n".join(
        f"[{'通过' if c.get('ok') else '未通过'}] {c.get('name') or ''}: {c.get('message') or ''}" for c in checks)
    provider_note = "AI 不可用, 以下为规则摘要" if not _k8s_ai_provider(db) else ""
    system = ("你是资深 K8s 集群建设专家。根据预检项给出一句话结论和可操作部署建议(离线环境)。"
              "只输出 JSON: {\"summary\":\"一句话结论(≤40字)\",\"recommendations\":[\"建议1\",\"建议2\"]}")
    user = (f"集群: {p.name}; K8s 版本: {p.kubernetes_version}; 运行时: {p.runtime}; CNI: {p.cni};\n"
            f"检查项({ok_count}/{len(checks)} 通过):\n{check_txt[:1800]}")
    res = _k8s_ai_call(db, system, user, fallback)
    res["ai_generated"] = res.get("ai_generated", True)
    if not isinstance(res.get("recommendations"), list):
        res["recommendations"] = issues or []
    return res


