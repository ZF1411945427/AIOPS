"""子模块: k8s_offline 常量/状态/基础工具(拆分生成, 勿手改函数体)"""

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
import threading as _threading

# ─── 原 L27-58 ───
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACT_ROOT = Path(os.environ.get(
    "AIOPS_K8S_DEPLOY_DIR",
    str(_PROJECT_ROOT / "storage" / "k8s_deploy")))

# 控制面内置镜像（若离线包未提供可退化的最小集；实际以离线包 images/ 为准）
_DEFAULT_CNI_FILES = {
    "calico": "https://raw.githubusercontent.com/projectcalico/calico/v3.29.0/manifests/calico.yaml",
    "flannel": "https://raw.githubusercontent.com/flannel-io/flannel/v0.25.4/Documentation/kube-flannel.yml",
    "cilium": "https://raw.githubusercontent.com/cilium/cilium/v1.16.5/install/kubernetes/quick-install.yaml",
}

_CNI_POD_CIDR = {
    "calico": "10.244.0.0/16",
    "flannel": "10.244.0.0/16",
    "cilium": "10.0.0.0/8",
}

_EXEC_LOCK: Dict[int, bool] = {}
_STOPPED: Dict[int, bool] = {}
# 用户决策队列注册表: plan_id -> queue.Queue(供 AI 诊断失败时向前端提交方案选择)。
# 由 WS/SSE 路由创建并转发用户 decision, 与 deploy_service._DECISIONS 机制对齐。
K8S_DECISIONS: Dict[int, Any] = {}

# ── 停止即强中断(根治"停止后无法重新部署") ──
# plan_id -> set(活跃 SSH channel)。停止时将 channel.close() 强制中断阻塞的 stdout.read()，
# 使 _run_remote 快速返回失败 → 生成器走到 _check_stop → 抛 _DeployStopped → finally 释放锁。
# 线程本地保存当前部署线程的 plan_id，避免给 82 处 _run_remote 逐一加参。
import threading as _threading
_TLOCAL = _threading.local()
_ACTIVE_CHANNELS: Dict[int, set] = {}
_ACTIVE_CHANNELS_LOCK = _threading.Lock()


# ─── 原 L61-62 ───
def _current_plan_id() -> Optional[int]:
    return getattr(_TLOCAL, "plan_id", None)


# ─── 原 L65-70 ───
def _register_channel(chan) -> None:
    pid = _current_plan_id()
    if pid is None or chan is None:
        return
    with _ACTIVE_CHANNELS_LOCK:
        _ACTIVE_CHANNELS.setdefault(pid, set()).add(chan)


# ─── 原 L73-82 ───
def _unregister_channel(chan) -> None:
    pid = _current_plan_id()
    if pid is None or chan is None:
        return
    with _ACTIVE_CHANNELS_LOCK:
        s = _ACTIVE_CHANNELS.get(pid)
        if s:
            s.discard(chan)
            if not s:
                _ACTIVE_CHANNELS.pop(pid, None)


# ─── 原 L85-94 ───
def _interrupt_plan_channels(plan_id: int) -> None:
    """强制关闭该 plan 所有活跃 SSH channel，中断阻塞中的 stdout.read()。"""
    with _ACTIVE_CHANNELS_LOCK:
        chans = _ACTIVE_CHANNELS.pop(plan_id, None)
        chans = set(chans) if chans else set()
    for ch in chans:
        try:
            ch.close()
        except Exception:
            pass


# ─── 原 L97-111 ───
def _await_k8s_decision(plan_id: int, decision_queue, default: str = "rollback") -> str:
    """AI 诊断失败/关键节点后等待用户决策。decision_queue 缺失或超时按 default 兜底。"""
    import queue as _q
    if decision_queue is None:
        return default
    while True:
        try:
            decision = decision_queue.get(timeout=5)
            return decision
        except _q.Empty:
            if _STOPPED.get(plan_id):
                return default
            continue
        except Exception:
            return default


# ─── 原 L114-133 ───
class _DeployStopped(Exception):
    """用户点击停止时抛出，用于优雅中断部署并标记 stopped 状态。"""

# kubeadm join token 有效期（超过需 regenerate）
_JOIN_TTL = "2h"

# 在线兜底安装 containerd 用：静态二进制版本（对应 K8s 1.27~1.31 均适用 1.7.x）。
# 优先级：K8s 版本映射表 → 默认 _CONTAINERD_DEFAULT_VERSION。
_CONTAINERD_DEFAULT_VERSION = "1.7.24"
_CONTAINERD_VERSION_MAP = {
    "1.31": "1.7.24",
    "1.30": "1.7.24",
    "1.29": "1.7.24",
    "1.28": "1.7.24",
    "1.27": "1.7.24",
}

_CNI_TEMPLATE_FALLBACK = ""  # 预留：离线包未含 CNI 清单时拉取模板




# ─── 原 L136-137 ───
def _now() -> datetime:
    return datetime.now()


# ─── 原 L140-141 ───
def _human(n: int) -> str:
    return str(n)


# ─── 原 L144-148 ───
def _safe_json(val: str, default=None):
    try:
        return json.loads(val or "")
    except Exception:
        return default if default is not None else {}


# ─── 原 L151-160 ───
def _parse_cert_expiry(val) -> Optional[int]:
    """解析证书统一有效期(年)。合法值为 >=1 的整数；空/None/0 视为 None(平台默认)。
    设定后要求所有证书(CA + 各服务证书)时长一致等于该年限。"""
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


# ─── 原 L163-169 ───
def _k8s_ai_provider(db: Session):
    """取启用的 AIProvider(与组件商店/部署页一致)。无则返回 None 走规则兜底。"""
    try:
        from app.models import AIProvider
        return db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    except Exception:
        return None


# ─── 原 L172-193 ───
def _k8s_ai_call(db: Session, system: str, user: str, fallback: dict, timeout=60) -> dict:
    """轻量 AI 调用(供预检建议/失败诊断/报告总结用)。AI 不可用或异常时返回 fallback。
    只做建议/分析, 绝不自动执行命令(K8s 集群属最高危, 全程人工确认)。"""
    provider = _k8s_ai_provider(db)
    if not provider:
        return fallback
    try:
        from app.services.agent_service import call_llm
        resp = call_llm(provider, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], timeout_override=timeout)
        if resp.get("error"):
            return fallback
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return fallback
        from app.services.component_catalog_service import safe_json_parse
        parsed = safe_json_parse(content, {})
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback


# ─── 原 L196-221 ───
def _plan_to_dict(p: K8sClusterPlan, include_kubeconfig: bool = False) -> dict:
    d = {
        "id": p.id,
        "name": p.name,
        "kubernetes_version": p.kubernetes_version or "",
        "runtime": p.runtime or "containerd",
        "cni": p.cni or "calico",
        "pod_cidr": p.pod_cidr or "",
        "service_cidr": p.service_cidr or "",
        "image_repository": p.image_repository or "",
        "bundle_id": p.bundle_id,
        "registry_id": p.registry_id,
        "http_proxy": p.http_proxy or "",
        "https_proxy": p.https_proxy or "",
        "no_proxy": p.no_proxy or "",
        "cert_expiry_years": p.cert_expiry_years,
        "untaint_master": bool(p.untaint_master),
        "status": p.status or "draft",
        "current_step": p.current_step or 0,
        "kubeconfig": p.kubeconfig or "" if include_kubeconfig else "",
        "report": _safe_json(p.report_json),
        "pending_decision": _safe_json(p.pending_decision_json, default=None),
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else None,
        "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M:%S") if p.updated_at else None,
    }
    return d


# ─── 原 L224-242 ───
def _node_to_dict(n: K8sClusterNode, include_password: bool = False) -> dict:
    d = {
        "id": n.id,
        "plan_id": n.plan_id,
        "asset_id": n.asset_id,
        "host_role": n.host_role or "worker",
        "ip": n.ip or "",
        "hostname": n.hostname or "",
        "username": n.username or "",
        "has_password": bool(n.has_password),
        "ssh_port": n.ssh_port or 22,
        "status": n.status or "pending",
        "init_roles": (n.init_roles or "").split(",") if n.init_roles else [],
        "joined_at": n.joined_at.strftime("%Y-%m-%d %H:%M:%S") if n.joined_at else None,
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else None,
    }
    if include_password:
        d["password"] = "***"
    return d


# ─── 原 L245-252 ───
def _append_log(p: K8sClusterPlan, entry: dict, db: Session):
    logs = _safe_json(p.logs_json, [])
    if not isinstance(logs, list):
        logs = []
    entry.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    logs.append(entry)
    p.logs_json = json.dumps(logs[-2000:], ensure_ascii=False)
    db.commit()


# ─── 原 L255-260 ───
def _set_pending_decision(p: K8sClusterPlan, db: Session, decision: Optional[dict] = None):
    persist_val = "null"
    if decision is not None:
        persist_val = json.dumps(decision, ensure_ascii=False)
    p.pending_decision_json = persist_val
    db.commit()


# ─── 原 L263-266 ───
def _get_assets(db: Session, node: K8sClusterNode) -> Optional[Asset]:
    if not node.asset_id:
        return None
    return db.query(Asset).filter(Asset.id == node.asset_id).first()


# ─── 原 L269-291 ───
def _resolve_node_conn(db: Session, node: K8sClusterNode) -> dict:
    """解析节点连接配置。优先用节点自带凭据；否则从关联资产 connection_config 读取。"""
    port = node.ssh_port or 22
    username = node.username or "root"
    password = node.password or ""
    ip = node.ip or ""
    if node.asset_id:
        asset = _get_assets(db, node)
        if asset:
            cc = _safe_json(asset.connection_config)
            ip = ip or asset.ip or cc.get("ssh_host", "")
            if not username or username == "root":
                username = cc.get("ssh_user", "") or username
            if not password:
                password = cc.get("ssh_password", "")
            if not port or port == 22:
                port = int(cc.get("ssh_port", 22) or 22)
    if not ip:
        raise ValueError(f"节点缺少 IP 地址(节点 id={node.id})")
    return {"ip": ip, "port": int(port), "username": username or "root", "password": password or ""}


# ─────────────────────────────── 计划 CRUD ───────────────────────────────


# ─── 原 L440-454 ───
def stop_execution(db: Session, plan_id: int) -> dict:
    """停止部署：置停止标记 + 强中断该 plan 活跃 SSH channel(中断阻塞 read)
    + 立即释放执行锁，确保"停止后可立即重新部署/续传"，根治锁占用卡死。"""
    _STOPPED[plan_id] = True
    # 强中断阻塞中的 SSH read，让部署线程尽快走到 _check_stop 退出并释放锁
    _interrupt_plan_channels(plan_id)
    # 立即释放执行锁(幂等)，避免"停止后仍提示正在部署中"
    _release_exec(plan_id)
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if p and p.status == "running":
        p.status = "stopped"
        _set_pending_decision(p, db, None)
        _append_log(p, {"type": "info", "message": f"部署已停止(断点: 阶段{p.current_step})，可点击「继续部署」续传"}, db)
        db.commit()
    return {"ok": True}


# ─── 原 L457-458 ───
def _release_exec(plan_id: int):
    _EXEC_LOCK.pop(plan_id, None)


# ─── 原 L461-465 ───
def _check_stop(plan_id: int) -> bool:
    return _STOPPED.get(plan_id, False)


# ─────────────────────────────── 部署编排 ───────────────────────────────


