"""K8S 离线集群部署服务 - 对标 Pixiu 一键建集群（离线环境）。

核心能力:
1. 集群部署计划 CRUD：定义 master/worker 节点、K8S 版本、运行时、CNI、CIDR
2. 复用「离线仓库」(offline_repo_service) 的私有 Registry + 包源 + 离线包(binaries/images)
3. kubeadm 7 阶段编排，通过 SSH 在目标主机执行，产出 kubeconfig
4. 部署成功后自动创建 DataSource(type=kubernetes)，集群立即接入平台 K8S 监控

契约见 CONTRACT.md 第十三章。存储一律基于 __file__ 动态计算，禁止硬编码绝对路径。
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


class _DeployStopped(Exception):
    """用户点击停止时抛出，用于优雅中断部署并标记 stopped 状态。"""

# kubeadm join token 有效期（超过需 regenerate）
_JOIN_TTL = "2h"

_CNI_TEMPLATE_FALLBACK = ""  # 预留：离线包未含 CNI 清单时拉取模板


# ─────────────────────────────── 基础工具 ───────────────────────────────

def _now() -> datetime:
    return datetime.now()


def _human(n: int) -> str:
    return str(n)


def _safe_json(val: str, default=None):
    try:
        return json.loads(val or "")
    except Exception:
        return default if default is not None else {}


def _k8s_ai_provider(db: Session):
    """取启用的 AIProvider(与组件商店/部署页一致)。无则返回 None 走规则兜底。"""
    try:
        from app.models import AIProvider
        return db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    except Exception:
        return None


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
        "untaint_master": bool(p.untaint_master),
        "status": p.status or "draft",
        "current_step": p.current_step or 0,
        "kubeconfig": p.kubeconfig or "" if include_kubeconfig else "",
        "report": _safe_json(p.report_json),
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else None,
        "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M:%S") if p.updated_at else None,
    }
    return d


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


def _append_log(p: K8sClusterPlan, entry: dict, db: Session):
    logs = _safe_json(p.logs_json, [])
    if not isinstance(logs, list):
        logs = []
    entry.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    logs.append(entry)
    p.logs_json = json.dumps(logs[-2000:], ensure_ascii=False)
    db.commit()


def _get_assets(db: Session, node: K8sClusterNode) -> Optional[Asset]:
    if not node.asset_id:
        return None
    return db.query(Asset).filter(Asset.id == node.asset_id).first()


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


def stop_execution(db: Session, plan_id: int) -> dict:
    _STOPPED[plan_id] = True
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if p and p.status == "running":
        p.status = "stopped"
        _append_log(p, {"type": "info", "message": f"部署已停止(断点: 阶段{p.current_step})，可点击「继续部署」续传"}, db)
        db.commit()
    return {"ok": True}


def _release_exec(plan_id: int):
    _EXEC_LOCK.pop(plan_id, None)


def _check_stop(plan_id: int) -> bool:
    return _STOPPED.get(plan_id, False)


# ─────────────────────────────── 部署编排 ───────────────────────────────

def _get_bundle_context(db: Session, p: K8sClusterPlan) -> dict:
    """从离线仓库解析部署上下文：registry 地址 / 包源 / 离线包解压根目录。"""
    ctx = {"registry_url": "", "registry_secure": False,
           "registry_username": "", "registry_password": "",
           "package_sources": [], "bundle": None, "extract_dir": None}
    if p.registry_id:
        reg = db.query(OfflineRegistry).filter(OfflineRegistry.id == p.registry_id).first()
        if reg:
            ctx["registry_url"] = reg.registry_url
            ctx["registry_secure"] = bool(reg.is_secure)
            ctx["registry_username"] = reg.username or ""
            ctx["registry_password"] = reg.password or ""
    if not ctx["registry_url"]:
        reg = db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True).first()  # noqa: E712
        if reg:
            ctx["registry_url"] = reg.registry_url
            ctx["registry_secure"] = bool(reg.is_secure)
    if p.bundle_id:
        b = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.id == p.bundle_id).first()
        ctx["bundle"] = b
        if b and b.file_path and os.path.exists(b.file_path):
            xdir = EXTRACT_ROOT / f"bundle_{b.id}"
            xdir.mkdir(parents=True, exist_ok=True)
            if not any(xdir.iterdir()):
                try:
                    with tarfile.open(b.file_path, "r:gz") as tf:
                        tf.extractall(xdir)
                except Exception as e:
                    logger.warning(f"离线包解压失败: {e}")
            ctx["extract_dir"] = xdir
    ctx["package_sources"] = offline_repo_service.list_sources(db).get("items", [])
    # 控制面镜像仓库：优先 plan.image_repository，其次 <registry>/kubernetes
    if p.image_repository:
        ctx["image_repository"] = p.image_repository
    elif ctx["registry_url"]:
        ctx["image_repository"] = f"{ctx['registry_url']}/kubernetes"
    else:
        ctx["image_repository"] = ""
    return ctx


def _parse_ctl_rc(stdout: str, marker: str = "RC") -> int:
    """从命令输出中解析 `MARKER=<数字>` 的真实返回码。
    用于规避 `cmd; echo RC=$?` 末尾 echo 恒定返回 0 的误报。"""
    import re as _re
    m = None
    for pat in (fr"{marker}=(\d+)", fr"__{marker}__=(\d+)"):
        hits = _re.findall(pat, stdout, _re.M)
        if hits:
            m = hits[-1]
            break
    try:
        return int(m) if m is not None else -1
    except Exception:
        return -1


def _run_remote(client, command: str, timeout: int = 300) -> dict:
    """在已连接 SSH client 上执行命令，返回 {ok, stdout, stderr, exit_code}。"""
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        return {"ok": rc == 0, "stdout": out, "stderr": err, "exit_code": rc}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def _iter_remote(client, command: str, timeout: int = 300):
    """逐行执行远程命令，yield (line, is_stderr)。"""
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        import select
        chan = stdout.channel
        chan.settimeout(0.2)
        err_chan = stderr.channel
        while True:
            if chan.exit_status_ready() and chan.recv_ready() == 0 and err_chan.recv_ready() == 0:
                break
            rfds, _, _ = select.select([chan, err_chan], [], [], 0.2)
            for ch in rfds:
                if ch is err_chan:
                    while err_chan.recv_ready():
                        yield (err_chan.recv(4096).decode("utf-8", "replace"), True)
                else:
                    while chan.recv_ready():
                        yield (chan.recv(4096).decode("utf-8", "replace"), False)
            if chan.exit_status_ready() and chan.recv_ready() == 0 and err_chan.recv_ready() == 0:
                break
        rc = chan.recv_exit_status()
        yield (f"__EXIT__{rc}", False)
    except Exception as e:
        yield (f"__ERR__{e}", True)


def _sftp_put(client, local: Path, remote: str, mode: int = 0o755):
    """通过 SFTP 上传单文件到远程并设置权限。"""
    sftp = client.open_sftp()
    try:
        sftp.put(str(local), remote)
        sftp.chmod(remote, mode)
    finally:
        sftp.close()


def _exec_ssh_db(db: Session, p: K8sClusterPlan, node: K8sClusterNode, label: str):
    """建立节点 SSH 连接(带 TOFU)。返回 (client, conn)。连接异常时写日志并抛出。"""
    conn = _resolve_node_conn(db, node)
    _append_log(p, {"type": "ssh", "node": label, "message": f"连接 {conn['ip']}:{conn['port']}"}, db)
    client = connect_ssh(conn["ip"], port=conn["port"], username=conn["username"],
                         password=conn["password"], timeout=15)
    return client, conn


def _inject_etc_hosts(db, p, nodes, client, label) -> None:
    """在节点写入 /etc/hosts 的集群节点映射。"""
    lines = []
    for n in nodes:
        hn = n.get("hostname") or n.get("ip")
        lines.append(f"{n['ip']} {hn}")
    block = "\n".join(lines)
    script = (
        "grep -q 'AIOPS_K8S_DEPLOY' /etc/hosts || "
        f"""{{ echo '# AIOPS_K8S_DEPLOY'; echo -e '{block}'; }} >> /etc/hosts; """
        "echo done"
    )
    r = _run_remote(client, script, timeout=60)
    if not r["ok"]:
        _append_log(p, {"type": "warn", "node": label, "message": f"写入 hosts 失败: {r['stderr'][:200]}"}, db)


def _disable_swap(client, label, p, db) -> None:
    r = _run_remote(client,
                    "swapoff -a; sed -i '/ swap /s/^/#/' /etc/fstab; echo ok", timeout=120)
    if not r["ok"]:
        _append_log(p, {"type": "warn", "node": label, "message": "关闭 swap 失败: " + r["stderr"][:200]}, db)


def _setup_kernel(client, label, p, db) -> None:
    r = _run_remote(client, r'''
modprobe overlay; modprobe br_netfilter;
cat > /etc/modules-load.d/k8s.conf <<'EOF'
overlay
br_netfilter
EOF
cat > /etc/sysctl.d/k8s.conf <<'EOF'
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
vm.swappiness                       = 0
EOF
sysctl --system >/dev/null 2>&1
echo ok''', timeout=120)
    if not r["ok"]:
        _append_log(p, {"type": "warn", "node": label,
                        "message": f"内核模块/sysctl 配置警告: {r['stderr'][:200]}"}, db)


def _set_hostname(client, node, label, p, db) -> str:
    hn = node.get("hostname") or label
    _run_remote(client, f"hostnamectl set-hostname {hn}", timeout=60)
    return hn


def _proxy_env_script(p: K8sClusterPlan) -> str:
    """生成 export http_proxy/https_proxy/no_proxy 的 shell 片段。
    任何需要 curl/wget/apt/yum 联网的命令前都应注入。空=无代理。"""
    http_p = (p.http_proxy or "").strip()
    https_p = (p.https_proxy or http_p or "").strip()
    no_proxy_p = (p.no_proxy or "127.0.0.1,localhost,.local").strip()
    if not http_p:
        return ""
    return (
        f"export http_proxy='{http_p}'; "
        f"export https_proxy='{https_p}'; "
        f"export HTTP_PROXY='{http_p}'; "
        f"export HTTPS_PROXY='{https_p}'; "
        f"export no_proxy='{no_proxy_p}'; "
        f"export NO_PROXY='{no_proxy_p}'; "
    )


def _install_preflight_deps(client, label, p, db, yield_event=None) -> None:
    """安装 kubeadm preflight 依赖：conntrack/ethtool/socat/crictl(cri-tools 可选)。"""
    # 预配 apt 代理(plan.http_proxy)以提升在线源可用性
    http_p = p.http_proxy or ""
    https_p = p.https_proxy or http_p or ""
    proxy_conf = ""
    if http_p:
        # 写入 /etc/apt/apt.conf.d/95proxies (幂等：已存在则跳过)
        proxy_conf = (
            "cat /etc/apt/apt.conf.d/95proxies 2>/dev/null | grep -q 'Acquire::http::Proxy' || "
            f"printf 'Acquire::http::Proxy \"{http_p}\";\\nAcquire::https::Proxy \"{https_p or http_p}\";\\n' "
            "> /etc/apt/apt.conf.d/95proxies; "
        )
    script = (
        proxy_conf +
        "which conntrack ethtool socat >/dev/null 2>&1 && echo HAVE || "
        "(apt-get install -y conntrack ethtool socat >/dev/null 2>&1 || "
        "yum install -y conntrack-tools ethtool socat >/dev/null 2>&1); "
        "echo rc=$?"
    )
    r = _run_remote(client, script, timeout=300)
    if "HAVE" in r["stdout"] or "rc=0" in r["stdout"]:
        msg = "preflight 依赖(conntrack/ethtool/socat)就绪"
    else:
        msg = "preflight 依赖安装失败: " + r["stdout"][-150:]
    _append_log(p, {"type": "ok" if "就绪" in msg else "warn", "node": label, "message": msg}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": msg})


def _containerd_config_script(p: K8sClusterPlan, ctx: dict = None) -> str:
    """生成 containerd 配置脚本：SystemdCgroup + 与 k8s 版本匹配的 pause sandbox_image。
    返回一段可在目标机执行的 shell 脚本。"""
    try:
        ver_parts = (p.kubernetes_version or "v1.31").lstrip("v").split(".")
        k8s_minor = int(ver_parts[1]) if len(ver_parts) > 1 else 31
    except Exception:
        k8s_minor = 31
    pause_tag = "3.10" if k8s_minor >= 28 else "3.9"
    # 私有 registry 存在时 sandbox 镜像指向私有仓库，否则用官方
    sandbox_base = "registry.k8s.io"
    if ctx and ctx.get("registry_url"):
        sandbox_base = ctx["registry_url"].split("/")[0] + "/kubernetes"
    sandbox_img = f"{sandbox_base}/pause:{pause_tag}"
    cfg = (
        "mkdir -p /etc/containerd; containerd config default > /etc/containerd/config.toml 2>/dev/null || true; "
        "sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml "
        "|| sed -i 's/SystemdCgroup=false/SystemdCgroup=true/g' /etc/containerd/config.toml; "
        # containerd config default 可能自带 sandbox_image(pause)，必须强制替换为与 k8s 匹配的版本
        f"sed -i 's#sandbox_image = .*#sandbox_image = \"{sandbox_img}\"#' /etc/containerd/config.toml; "
        "grep -q sandbox_image /etc/containerd/config.toml || "
        f"echo 'sandbox_image = \"{sandbox_img}\"' >> /etc/containerd/config.toml; "
        # 开启 hosts.toml 支持(用于 HTTP registry)
        "sed -i 's|config_path = \"\"|config_path = \"/etc/containerd/certs.d\"|' /etc/containerd/config.toml; "
        "grep -q config_path /etc/containerd/config.toml || "
        "echo '      config_path = \"/etc/containerd/certs.d\"' >> /etc/containerd/config.toml; "
        "systemctl enable containerd >/dev/null 2>&1; "
        "(systemctl restart containerd || pkill containerd; sleep 2); echo ok"
    )
    return cfg


def _install_containerd(client, ctx, label, p, db, yield_event=None) -> None:
    """安装 containerd：优先离线包 binaries/，否则走包源。已安装时也强制刷新配置(sandbox)。"""
    script = "which containerd && containerd --version 2>/dev/null || echo MISSING"
    r = _run_remote(client, script, timeout=60)
    if r["ok"] and "MISSING" not in r["stdout"]:
        # 已安装：不重新安装二进制，但仍需确保配置文件包含匹配的 sandbox_image
        _run_remote(client, _containerd_config_script(p, ctx), timeout=180)
        _append_log(p, {"type": "info", "node": label, "message": "containerd 已安装，刷新 CRI 配置(sandbox)"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "containerd 已安装，刷新 CRI 配置(sandbox)"})
        return
    installed = False
    xdir = ctx.get("extract_dir")
    if xdir:
        bin_dir = xdir / "binaries"
        if bin_dir.exists():
            for name in ("containerd", "ctr", "containerd-shim", "containerd-shim-runc-v2"):
                src = bin_dir / name
                if src.exists():
                    remote = f"/usr/local/bin/{name}"
                    try:
                        _sftp_put(client, src, remote, 0o755)
                        _append_log(p, {"type": "info", "node": label,
                                        "message": f"SFTP 上传 {name} → {remote}"}, db)
                    except Exception as e:
                        _append_log(p, {"type": "warn", "node": label,
                                        "message": f"上传 {name} 失败: {e}"}, db)
            installed = True
    if yield_event: yield_event({"type": "log", "node": label, "message": "containerd 离线安装中..."})
    if not installed:
        # 走包源安装（deb/rpm）；如 plan 配置代理则注入环境变量
        _run_remote(client, _proxy_env_script(p) + "apt-get install -y containerd >/dev/null 2>&1 || yum install -y containerd.io >/dev/null 2>&1; echo rc=$?", timeout=600)
    # 生成 containerd 配置
    _run_remote(client, _containerd_config_script(p, ctx), timeout=180)
    r = _run_remote(client, "containerd --version 2>/dev/null || echo FAIL", timeout=60)
    if "FAIL" in r["stdout"]:
        _append_log(p, {"type": "error", "node": label, "message": "containerd 安装/启动失败"}, db)
    else:
        msg = "containerd 就绪: " + r["stdout"].strip()[:80]
        _append_log(p, {"type": "info", "node": label, "message": msg}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": msg})


def _install_k8s_binaries(client, ctx, label, p, db, yield_event=None) -> None:
    """安装 kubeadm/kubelet/kubectl：优先离线包 binaries/，否则包源。"""
    need = []
    for b in ("kubeadm", "kubelet", "kubectl"):
        r = _run_remote(client, f"which {b} 2>/dev/null || echo MISSING", timeout=60)
        if "MISSING" in r["stdout"] or not r["ok"]:
            need.append(b)
    if not need:
        msg = "k8s 二进制已存在，跳过"
        _append_log(p, {"type": "info", "node": label, "message": msg}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": msg})
    xdir = ctx.get("extract_dir")
    missing = list(need)
    if xdir:
        bin_dir = xdir / "binaries"
        if bin_dir.exists():
            for b in list(need):
                src = bin_dir / b
                if src.exists():
                    remote = f"/usr/local/bin/{b}"
                    try:
                        _sftp_put(client, src, remote, 0o755)
                        _append_log(p, {"type": "info", "node": label, "message": f"SFTP 上传 {b}"}, db)
                        if b in missing:
                            missing.remove(b)
                    except Exception as e:
                        _append_log(p, {"type": "warn", "node": label, "message": f"上传 {b} 失败: {e}"}, db)
    if missing:
        # 1) 在线兜底：dl.k8s.io 下载对应版本二进制(架构 amd64，可在代理下)
        if yield_event: yield_event({"type": "log", "node": label, "message": f"缺失 {missing}，尝试在线下载 dl.k8s.io"})
        _append_log(p, {"type": "info", "node": label, "message": f"缺失 {missing}，尝试在线下载 dl.k8s.io"}, db)
        kv = p.kubernetes_version or "v1.31"
        if not kv.startswith("v"):
            kv = "v" + kv
        for b in list(missing):
            url = f"https://dl.k8s.io/{kv}/bin/linux/amd64/{b}"
            r = _run_remote(client,
                            _proxy_env_script(p) +
                            f"curl -fsSL -A 'curl/8.4' '{url}' -o /usr/local/bin/{b} && chmod +x /usr/local/bin/{b} && echo OK || echo FAIL",
                            timeout=900)
            if "OK" in r["stdout"]:
                _append_log(p, {"type": "info", "node": label, "message": f"在线下载 {b} 成功"}, db)
                if yield_event: yield_event({"type": "log", "node": label, "message": f"在线下载 {b} 成功"})
                missing.remove(b)
            else:
                _append_log(p, {"type": "warn", "node": label, "message": f"在线下载 {b} 失败，尝试包源"}, db)
        # 2) 退化：包源安装 kubeadm 全家桶（注入代理）
        if missing:
            _run_remote(client,
                        _proxy_env_script(p) +
                        "apt-get install -y kubeadm kubelet kubectl >/dev/null 2>&1 || "
                        "yum install -y kubeadm kubelet kubectl >/dev/null 2>&1; echo rc=$?", timeout=900)
    # 启用 kubelet(确保 systemd unit 存在，二进制安装时不会自动生成)
    _run_remote(client,
                """if [ ! -f /etc/systemd/system/kubelet.service ]; then
cat > /etc/systemd/system/kubelet.service <<'SVC'
[Unit]
Description=kubelet: The Kubernetes Node Agent
Documentation=https://kubernetes.io/docs/home/
Wants=network-online.target
After=network-online.target

[Service]
EnvironmentFile=-/etc/default/kubelet
ExecStart=/usr/local/bin/kubelet
Restart=always
StartLimitInterval=0
RestartSec=10

[Install]
WantedBy=multi-user.target
SVC
mkdir -p /etc/systemd/system/kubelet.service.d
cat > /etc/systemd/system/kubelet.service.d/10-kubeadm.conf <<'DRP'
[Service]
Environment="KUBELET_KUBECONFIG_ARGS=--bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf"
Environment="KUBELET_CONFIG_ARGS=--config=/var/lib/kubelet/config.yaml"
EnvironmentFile=-/etc/default/kubelet
ExecStart=
ExecStart=/usr/local/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS $KUBELET_EXTRA_ARGS
DRP
fi
systemctl daemon-reload
systemctl enable kubelet >/dev/null 2>&1
mkdir -p /etc/systemd/system/kubelet.service.d
echo ok""", timeout=120)


def _generate_kubeadm_config(p, first_master_ip: str, ctx: dict) -> str:
    """在首 master 生成 kubeadm-config.yaml。"""
    cri = "unix:///run/containerd/containerd.sock" if p.runtime == "containerd" else "unix:///var/run/dockershim.sock"
    kv = p.kubernetes_version
    if kv and not kv.startswith("v"):
        kv = "v" + kv
    repo = ctx.get("image_repository") or "registry.k8s.io"
    cfg = f"""apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: {first_master_ip}
nodeRegistration:
  criSocket: {cri}
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: {kv or "stable"}
imageRepository: {repo}
apiServer:
  extraArgs:
    service-node-port-range: "30000-32767"
networking:
  podSubnet: {p.pod_cidr}
  serviceSubnet: {p.service_cidr}
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
"""
    if p.runtime == "containerd":
        cfg += f"""---
apiVersion: kubeadm.k8s.io/v1beta3
kind: JoinConfiguration
nodeRegistration:
  criSocket: {cri}
"""
    return cfg


def _write_imagetar_jobs(client, ctx, label, p, db) -> None:
    """若离线包含 images/，在节点 docker load / ctr -n=k8s.io images import 预拉镜像。
    仅当目标节点 Docker/containerd 可访问镜像时使用；实际导入通常在加载离线包时已 push 到 Registry。
    """
    xdir = ctx.get("extract_dir")
    if not xdir:
        return
    img_dir = xdir / "images"
    if not img_dir.exists():
        return
    # 用 ctr 导入（containerd k8s.io namespace）
    cnt = 0
    for f in sorted(img_dir.iterdir()):
        if not f.is_file() or not f.name.endswith((".tar", ".tar.gz", ".tgz")):
            continue
        _run_remote(client, "mkdir -p /tmp/k8s-images && echo ok", timeout=60)
        try:
            _sftp_put(client, f, f"/tmp/k8s-images/{f.name}", 0o644)
        except Exception as e:
            _append_log(p, {"type": "warn", "node": label, "message": f"上传镜像 {f.name} 失败: {e}"}, db)
            continue
        r = _run_remote(client,
                        f"ctr -n=k8s.io images import /tmp/k8s-images/{f.name} >/dev/null 2>&1 && echo OK || echo FAIL",
                        timeout=600)
        if "OK" in r["stdout"]:
            cnt += 1
    _append_log(p, {"type": "info", "node": label, "message": f"离线镜像本地导入 {cnt} 个"}, db)


def _configure_insecure_registry(client, ctx, label, p, db, yield_event=None) -> None:
    """节点配置 containerd 信任私有 Registry(insecure+hosts.toml)。"""
    ru = ctx.get("registry_url")
    if not ru:
        return
    host = ru.split("/")[0]
    # 1. 写 hosts.toml 支持 HTTP registry（纯 HTTP：不配 TLS，避免 containerd 误判走 HTTPS）
    hosts_script = (
        "mkdir -p /etc/containerd/certs.d/%(host)s; "
        "cat > /etc/containerd/certs.d/%(host)s/hosts.toml <<'EOF'\n"
        'server = "http://%(host)s"\n\n'
        '[host."http://%(host)s"]\n'
        '  capabilities = ["pull", "resolve", "push"]\n'
        "EOF\n"
        "echo hosts_toml_ok"
    ) % {"host": host}
    _run_remote(client, hosts_script, timeout=60)
    # 2. 清掉 config.toml 中旧的 insecure_skip_verify 块（曾导致 containerd 判定为 HTTP+TLS → 优先尝试 HTTPS）
    _run_remote(client, "sed -i '/registry.configs/,\\$d' /etc/containerd/config.toml; echo cleaned", timeout=60)
    # 3. 若 plan 配置了代理，为 containerd 写入 systemd proxy（CNI/coredns 镜像来自 docker.io，不走 HTTP_PROXY 拉不到）
    http_p = (p.http_proxy or "").strip()
    https_p = (p.https_proxy or http_p or "").strip()
    no_proxy_p = (p.no_proxy or "127.0.0.1,localhost,.local").strip()
    if http_p:
        # 把私有 Registry 加入 NO_PROXY，避免 containerd 走代理拉内网镜像
        if host not in no_proxy_p:
            no_proxy_p = f"{no_proxy_p},{host}"
        proxy_unit = (
            "mkdir -p /etc/systemd/system/containerd.service.d; "
            f"cat > /etc/systemd/system/containerd.service.d/http-proxy.conf <<'PVC'\n"
            "[Service]\n"
            f"Environment=\"HTTP_PROXY={http_p}\"\n"
            f"Environment=\"HTTPS_PROXY={https_p}\"\n"
            f"Environment=\"NO_PROXY={no_proxy_p}\"\n"
            "PVC\n"
            "systemctl daemon-reload; echo proxy_ok"
        )
        _run_remote(client, proxy_unit, timeout=60)
        _append_log(p, {"type": "info", "node": label, "message": f"containerd 已配置代理 {http_p}"}, db)
    _run_remote(client, "systemctl restart containerd >/dev/null 2>&1 || pkill containerd; sleep 2; echo ok", timeout=120)
    msg = f"containerd 已信任私有 Registry: {host}"
    _append_log(p, {"type": "info", "node": label, "message": msg}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": msg})


def _run_deploy_generator(db, p: K8sClusterPlan, plan_id: int, resume_step: int = 0):
    """kubeadm 7 阶段编排生成器。yield 事件 dict(供 WS/SSE 推送)。
    resume_step>0 时为断点续传：已完成阶段直接幂等跳过。"""
    yield {"type": "status", "status": "running", "message": "开始离线集群部署"}
    p.status = "running"
    if resume_step == 0:
        p.current_step = 0
    db.commit()

    nodes_db = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).order_by(
        K8sClusterNode.id).all()
    if not nodes_db:
        p.status = "failed"
        _append_log(p, {"type": "error", "message": "没有节点"}, db)
        yield {"type": "complete", "status": "failed", "message": "没有节点"}
        return

    masters = [n for n in nodes_db if n.host_role == "master"]
    workers = [n for n in nodes_db if n.host_role != "master"]
    first_master = masters[0]
    first_ip = _resolve_node_conn(db, first_master)["ip"]

    ctx = _get_bundle_context(db, p)
    _append_log(p, {"type": "info", "message": f"控制面镜像仓库: {ctx.get('image_repository') or '(未配置)'}"}, db)

    clients: Dict[int, Any] = {}  # node.id -> ssh client
    labels: Dict[int, str] = {}
    try:
        # ── 阶段0 预检 ──
        p.current_step = 0
        yield {"type": "phase", "step": 0, "title": "阶段0/6 预检"}
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            label = f"{n.host_role}:{n.ip}"
            labels[n.id] = label
            n.status = "running"
            db.commit()
            try:
                client, conn = _exec_ssh_db(db, p, n, label)
                clients[n.id] = client
                r = _run_remote(client, "id -u; uname -r; which swapoff", timeout=60)
                msg = "SSH 连通，root=" + (r["stdout"].splitlines()[0] if r["stdout"] else "?")
                _append_log(p, {"type": "ok", "node": label, "message": msg}, db)
                yield {"type": "log", "node": label, "message": msg}
                n.status = "succeeded"
            except Exception as e:
                n.status = "failed"
                _append_log(p, {"type": "error", "node": label, "message": f"SSH 连接失败: {e}"}, db)
                yield {"type": "log", "node": label, "message": f"SSH 连接失败: {e}"}
        db.commit()
        if any(n.status == "failed" for n in nodes_db):
            raise RuntimeError("存在无法连接的节点，中止部署")

        # ── 阶段1 环境准备(所有节点，可并行) ──
        pending_yields = []
        def _emit(evt): pending_yields.append(evt)
        p.current_step = 1
        yield {"type": "phase", "step": 1, "title": "阶段1/6 环境准备(swap/内核/hosts)"}
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            label = labels[n.id]
            client = clients[n.id]
            hn = _set_hostname(client, {"hostname": n.hostname}, label, p, db)
            _disable_swap(client, label, p, db)
            _setup_kernel(client, label, p, db)
            _install_preflight_deps(client, label, p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
        # /etc/hosts 全部集群节点映射
        all_nodes = [{"ip": _resolve_node_conn(db, x)["ip"], "hostname": x.hostname}
                     for x in nodes_db]
        for n in nodes_db:
            _inject_etc_hosts(db, p, all_nodes, clients[n.id], labels[n.id])
        _append_log(p, {"type": "ok", "message": "环境准备完成"}, db)
        yield {"type": "log", "message": "环境准备完成"}

        # ── 阶段2 容器运行时 + k8s 二进制(所有节点) ──
        p.current_step = 2
        yield {"type": "phase", "step": 2, "title": "阶段2/6 运行时与二进制"}
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            label = labels[n.id]
            client = clients[n.id]
            yield {"type": "log", "node": label, "message": f"配置节点 {label}..."}
            _install_containerd(client, ctx, label, p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
            if ctx.get("registry_url"):
                _configure_insecure_registry(client, ctx, label, p, db, yield_event=_emit)
                for evt in pending_yields:
                    yield evt
                pending_yields.clear()
            _install_k8s_binaries(client, ctx, label, p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
            _write_imagetar_jobs(client, ctx, label, p, db)
            yield {"type": "log", "node": label, "message": f"节点 {label} 配置完成"}
        _append_log(p, {"type": "ok", "message": "运行时与二进制就绪"}, db)
        yield {"type": "log", "message": "运行时与二进制就绪"}

        # ── 阶段3 首 master 生成配置 + 预拉镜像 ──
        p.current_step = 3
        yield {"type": "phase", "step": 3, "title": "阶段3/6 生成 kubeadm 配置"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        fclient = clients[first_master.id]
        cfg = _generate_kubeadm_config(p, first_ip, ctx)
        _run_remote(fclient, "mkdir -p /etc/kubernetes && echo ok", timeout=60)
        sftp = fclient.open_sftp()
        try:
            with sftp.file("/etc/kubernetes/kubeadm-config.yaml", "w") as f:
                f.write(cfg)
        finally:
            sftp.close()
        _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": "kubeadm-config.yaml 已生成"}, db)
        yield {"type": "log", "node": labels[first_master.id], "message": "生成 kubeadm 配置"}
        # 预拉控制面镜像(可失败)
        yield {"type": "log", "node": labels[first_master.id], "message": "预拉控制面镜像中(可能需要几分钟)..."}
        _run_remote(fclient, "kubeadm config images pull --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; echo rc=$?", timeout=900)

        # ── 阶段4 kubeadm init ──
        p.current_step = 4
        yield {"type": "phase", "step": 4, "title": "阶段4/6 初始化控制平面"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        # 断点续传幂等：admin.conf 已存在且 API server 健康才跳过 init
        already_init = _run_remote(fclient, "test -f /etc/kubernetes/admin.conf && echo YES || echo NO", timeout=60)
        apiserver_ok = False
        if "YES" in already_init["stdout"]:
            # 健康检查 API server：只检查 admin.conf 存在不可靠，需确认 6443 可达
            health = _run_remote(fclient,
                                 "curl -sk -m 8 -o /dev/null -w '%{http_code}' https://127.0.0.1:6443/healthz 2>/dev/null || echo 000",
                                 timeout=30)
            apiserver_ok = "200" in health["stdout"]
            if apiserver_ok:
                _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": "控制平面已初始化且 API server 健康，跳过 init"}, db)
                yield {"type": "log", "node": labels[first_master.id], "message": "控制平面已初始化(API server 健康)，跳过 kubeadm init"}
            else:
                _append_log(p, {"type": "warn", "node": labels[first_master.id],
                                "message": f"admin.conf 存在但 API server 不可达(http={health['stdout'].strip()})，将重置后重新初始化"}, db)
                yield {"type": "log", "node": labels[first_master.id], "message": "检测到残留 admin.conf 但集群未运行，kubeadm reset 后重新初始化"}
                _run_remote(fclient, "kubeadm reset -f >/dev/null 2>&1; rm -rf /etc/kubernetes/*.conf /etc/kubernetes/pki /etc/kubernetes/manifests /var/lib/kubelet/* /etc/cni/net.d/*; echo reset_done", timeout=180)
                already_init = {"stdout": "NO"}
        if not apiserver_ok:
            init_cmd = ("kubeadm init --config /etc/kubernetes/kubeadm-config.yaml "
                        "--upload-certs "
                        "--ignore-preflight-errors=FileExisting-conntrack,FileExisting-ethtool")
            for line, is_err in _iter_remote(fclient, init_cmd + " 2>&1; echo __KUBEADM_RC__=$?"):
                if line.startswith("__KUBEADM_RC__="):
                    rc = line.split("=")[1].strip()
                    if rc != "0":
                        raise RuntimeError(f"kubeadm init 失败(rc={rc})")
                    break
                if line.strip():
                    yield {"type": "output", "node": labels[first_master.id], "line": line.rstrip()}
            _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": "kubeadm init 完成"}, db)

        # 配置 kubectl
        _run_remote(fclient,
                    "mkdir -p $HOME/.kube; cp /etc/kubernetes/admin.conf $HOME/.kube/config 2>/dev/null; chown $(id -u):$(id -g) $HOME/.kube/config; echo ok",
                    timeout=60)

        # ── 阶段5 CNI ──
        p.current_step = 5
        yield {"type": "phase", "step": 5, "title": "阶段5/6 安装 CNI"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        # 断点续传幂等：CNI daemonset 已存在则跳过
        cni_exist = _run_remote(fclient,
                                "export KUBECONFIG=/etc/kubernetes/admin.conf; kubectl get ds -A 2>/dev/null | grep -iE 'flannel|calico|cilium' | head -1 || true",
                                timeout=60)
        if cni_exist["stdout"].strip():
            _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": f"CNI 已安装({p.cni})，跳过"}, db)
            yield {"type": "log", "node": labels[first_master.id], "message": "CNI 已安装，跳过 apply"}
        else:
            xdir = ctx.get("extract_dir")
            cni_manifest = ""
            if xdir:
                cni_dir = xdir / "cni"
                if cni_dir.exists():
                    cand = [f for f in cni_dir.iterdir() if p.cni.lower() in f.name.lower() and f.is_file()]
                    if cand:
                        cni_manifest = str(cand[0])
            if cni_manifest:
                remote_yaml = "/root/k8s-cni.yaml"
                _sftp_put(fclient, Path(cni_manifest), remote_yaml, 0o644)
                r = _run_remote(fclient, f"kubectl apply --validate=false -f {remote_yaml} 2>&1; echo __CNI_RC__=$?", timeout=600)
                cni_rc = _parse_ctl_rc(r["stdout"], "CNI_RC")
                if cni_rc == 0:
                    _append_log(p, {"type": "ok", "node": labels[first_master.id],
                                    "message": "CNI 已应用(离线清单) rc=0"}, db)
                else:
                    raise RuntimeError(f"CNI(离线清单) 应用失败 rc={cni_rc}: " + r["stdout"][-300:])
            else:
                url = _DEFAULT_CNI_FILES.get(p.cni)
                if url:
                    # 先下载独立文件，下载失败立即报错(不落到旧残留文件)；成功后再 apply
                    r = _run_remote(fclient,
                                    _proxy_env_script(p) +
                                    f"rm -f /root/k8s-cni-download.yaml; "
                                    f"curl -fsSL '{url}' -o /root/k8s-cni-download.yaml 2>&1; echo CURL_RC=$?; "
                                    f"if [ -s /root/k8s-cni-download.yaml ]; then "
                                    f"kubectl apply --validate=false -f /root/k8s-cni-download.yaml 2>&1; echo APPLY_RC=$?; "
                                    f"else echo APPLY_RC=99; fi",
                                    timeout=600)
                    dl_rc = _parse_ctl_rc(r["stdout"], "CURL_RC")
                    apply_rc = _parse_ctl_rc(r["stdout"], "APPLY_RC")
                    if dl_rc == 0 and apply_rc == 0:
                        _append_log(p, {"type": "ok", "node": labels[first_master.id],
                                        "message": f"CNI 在线下载并应用成功 ({p.cni})"}, db)
                    else:
                        raise RuntimeError(f"CNI 安装失败: 下载rc={dl_rc}, applyrc={apply_rc}: " + r["stdout"][-300:])
        yield {"type": "log", "node": labels[first_master.id], "message": f"CNI 已安装: {p.cni}"}

        # ── 阶段6 生成 join 凭证 + worker(及额外 master)加入 ──
        p.current_step = 6
        yield {"type": "phase", "step": 6, "title": "阶段6/6 节点加入"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        # 获取 join token + discovery hash
        token_r = _run_remote(
            fclient,
            "kubeadm token create --ttl " + _JOIN_TTL + " 2>/dev/null | tail -1", timeout=120)
        token = token_r["stdout"].strip()
        ca_r = _run_remote(fclient,
                           "openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt | openssl rsa -pubin -outform der 2>/dev/null | openssl dgst -sha256 -hex | sed 's/^.* //'",
                           timeout=120)
        ca_hash = ca_r["stdout"].strip()
        if not token or not ca_hash:
            raise RuntimeError("无法生成 join token 或 CA hash")
        p.join_token = token
        db.commit()

        # control-plane 追加 master
        extra_masters = masters[1:]
        for n in extra_masters:
            label = labels[n.id]
            client = clients[n.id]
            cert_r = _run_remote(
                fclient, "kubeadm init phase upload-certs --upload-certs --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; echo done", timeout=300)
            join_cmd = (
                f"kubeadm join {first_ip}:6443 --token {token} "
                f"--discovery-token-ca-cert-hash sha256:{ca_hash} "
                f"--control-plane --certificate-key $(kubeadm init phase upload-certs --upload-certs --config /etc/kubernetes/kubeadm-config.yaml 2>/dev/null | tail -1)"
            )
            r = _run_remote(client, join_cmd + " 2>&1; echo __JOIN_RC__=$?", timeout=1200)
            if not r["ok"]:
                raise RuntimeError(f"master {label} join 失败: {r['stderr'][:300]}")
            n.status = "succeeded"
            db.commit()
            _append_log(p, {"type": "ok", "node": label, "message": "control-plane 加入成功"}, db)

        # worker 加入
        for n in workers:
            label = labels[n.id]
            client = clients[n.id]
            join_cmd = (
                f"kubeadm join {first_ip}:6443 --token {token} "
                f"--discovery-token-ca-cert-hash sha256:{ca_hash}"
            )
            for line, is_err in _iter_remote(client, join_cmd + " 2>&1; echo __JOIN_RC__=$;"):
                if line.startswith("__JOIN_RC__="):
                    rc = line.split("=")[1].strip()
                    if rc != "0":
                        raise RuntimeError(f"worker {label} join 失败(rc={rc})")
                    break
                if line.strip():
                    yield {"type": "output", "node": label, "line": line.rstrip()}
            n.status = "succeeded"
            n.joined_at = _now()
            db.commit()
            _append_log(p, {"type": "ok", "node": label, "message": "worker 加入成功"}, db)

        # 清理临时 join token
        p.join_token = ""

        # ── 阶段7 验证 + 接入平台 ──
        p.current_step = 7
        yield {"type": "phase", "step": 7, "title": "验证并接入平台"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        # 等待节点 Ready
        verify_cmd = (
            "for i in $(seq 1 30); do "
            " n=$(kubectl get nodes 2>/dev/null | grep -c Ready || true); "
            " if [ \"$n\" -ge %d ]; then echo READY:$n; exit 0; fi; sleep 5; done; "
            " echo TIMEOUT; kubectl get nodes 2>&1" % len(nodes_db)
        )
        vr = _run_remote(fclient, verify_cmd, timeout=400)
        _append_log(p, {"type": "ok", "node": labels[first_master.id],
                        "message": "节点就绪验证: " + vr["stdout"].strip()[:120]}, db)
        yield {"type": "log", "message": "节点就绪验证: " + vr["stdout"].strip()[:120]}

        # 采集 kubeconfig
        kc = _run_remote(fclient, "cat /etc/kubernetes/admin.conf", timeout=60)
        if kc["ok"] and kc["stdout"].strip():
            p.kubeconfig = kc["stdout"]
            _create_platform_datasource(db, p, first_ip)
            _append_log(p, {"type": "ok", "message": "已采集 kubeconfig 并接入平台监控"}, db)

        # 若勾选"去除主节点污点"，在 master 上移除 NoSchedule 污点，允许 Pod 调度到 master
        if p.untaint_master:
            taint_cmd = (
                "kubectl taint nodes --all node-role.kubernetes.io/control-plane-:NoSchedule- 2>/dev/null; "
                "kubectl taint nodes --all node-role.kubernetes.io/master-:NoSchedule- 2>/dev/null; "
                "echo taint_removed"
            )
            tr = _run_remote(fclient, taint_cmd, timeout=30)
            if "taint_removed" in tr["stdout"]:
                _append_log(p, {"type": "ok", "message": "已去除 master 节点污点，允许 Pod 调度到 master"}, db)
                yield {"type": "log", "message": "已去除 master 节点污点"}
            else:
                _append_log(p, {"type": "warn", "message": "去除 master 污点失败: " + tr["stdout"][:100]}, db)

        p.status = "succeeded"
        p.report_json = json.dumps(_build_report(db, p), ensure_ascii=False)
        db.commit()
        yield {"type": "complete", "status": "succeeded",
               "message": f"集群 {p.name} 部署成功，已接入监控"}
    except _DeployStopped:
        p.status = "stopped"
        _append_log(p, {"type": "info", "message": f"部署已停止(断点: 阶段{p.current_step})，可点击「继续部署」续传"}, db)
        db.commit()
        yield {"type": "complete", "status": "stopped", "message": "部署已停止"}
    except Exception as e:
        p.status = "failed"
        _append_log(p, {"type": "error", "message": f"部署失败: {e}"}, db)
        # ▼ AI 失败诊断(仅建议, K8s 集群高危不自动执行)
        try:
            _diag = _ai_failure_diagnosis(db, p, str(e))
            _append_log(p, {"type": "ai", "message": f"AI 诊断: {_diag.get('root_cause','')} → {_diag.get('suggestion','fix')}"}, db)
            yield {"type": "ai", "ai_generated": _diag.get("ai_generated", False), "stage": "failure",
                   "root_cause": _diag.get("root_cause", ""), "suggestion": _diag.get("suggestion", "fix"),
                   "advice": _diag.get("advice", "")}
        except Exception:
            pass
        db.commit()
        yield {"type": "error", "status": "failed", "message": str(e)}
        yield {"type": "complete", "status": "failed", "message": str(e)}
    finally:
        for client in clients.values():
            try:
                client.close()
            except Exception:
                pass
        _release_exec(plan_id)


def _ai_failure_diagnosis(db: Session, p: K8sClusterPlan, error: str) -> dict:
    """失败 AI 诊断: 汇总最近部署日志, 给出根因 + fix/retry/skip 建议(仅诊断, 不自动执行)。"""
    fallback = {
        "ai_generated": False, "root_cause": str(error)[:120],
        "suggestion": "fix", "advice": "检查上方部署日志, 修复后重新部署或续传",
    }
    logs = _safe_json(p.logs_json, []) if p else []
    recent = "\n".join(
        f"{l.get('type') or ''}[{l.get('node') or ''}]: {l.get('message') or ''}" for l in (logs or [])[-40:])
    system = ("你是资深 K8s 集群建设专家。kubeadm 离线建集群失败, 请根据最近日志给出一句话根因和处置建议。"
              "只输出 JSON: {\"root_cause\":\"一句话根因(≤60字,中文)\",\"suggestion\":\"fix|retry|skip\","
              "\"advice\":\"具体建议(含可执行修复要点, 但强调由人工确认后执行)\"}")
    user = (f"集群: {p.name}; 版本: {p.kubernetes_version}; 当前阶段: {p.current_step};\n"
            f"错误: {str(error)[:300]}\n最近部署日志:\n{recent[:2200]}")
    res = _k8s_ai_call(db, system, user, fallback)
    res.setdefault("ai_generated", True)
    if res.get("suggestion") not in ("fix", "retry", "skip"):
        res["suggestion"] = "fix"
    return res


def _build_report(db: Session, p: K8sClusterPlan) -> dict:
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == p.id).all()
    report = {
        "cluster_name": p.name,
        "kubernetes_version": p.kubernetes_version,
        "runtime": p.runtime,
        "cni": p.cni,
        "status": p.status,
        "node_matrix": [_node_to_dict(n) for n in nodes],
        "master_count": sum(1 for n in nodes if n.host_role == "master"),
        "worker_count": sum(1 for n in nodes if n.host_role != "master"),
    }
    report["ai_summary"] = _ai_report_summary(db, p, report)
    return report


def _ai_report_summary(db: Session, p: K8sClusterPlan, report: dict) -> dict:
    """部署完成报告 AI 总结: 集群构成 + 一句话结论 + 后续建议(仅总结, 不执行)。"""
    fallback = {"ai_generated": False,
                "summary": f"集群 {report.get('cluster_name')} 状态 {report.get('status')}: {report.get('master_count')} master / {report.get('worker_count')} worker",
                "recommendations": ["可用 kubectl get nodes 验证节点状态"]}
    system = ("你是资深 K8s 专家。根据集群部署结果给出一句话结论和后续建议(离线环境)。"
              "只输出 JSON: {\"summary\":\"一句话结论(≤50字,中文)\",\"recommendations\":[\"建议1\",\"建议2\"]}")
    user = (f"集群: {report.get('cluster_name')}; 版本: {report.get('kubernetes_version')}; "
            f"运行时: {report.get('runtime')}; CNI: {report.get('cni')}; 状态: {report.get('status')}; "
            f"节点: {report.get('master_count')} master / {report.get('worker_count')} worker")
    res = _k8s_ai_call(db, system, user, fallback, timeout=45)
    res.setdefault("ai_generated", True)
    if not isinstance(res.get("recommendations"), list):
        res["recommendations"] = []
    return res


def _create_platform_datasource(db: Session, p: K8sClusterPlan, api_ip: str) -> Optional[DataSource]:
    """部署成功后自动创建 DataSource(type=kubernetes)，集群接入监控。"""
    kc = p.kubeconfig or ""
    if not kc:
        return None
    ds_name = p.name
    existing = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == ds_name).first()
    auth_config = json.dumps({"kubeconfig": kc, "verify_ssl": False}, ensure_ascii=False)
    endpoint = f"https://{api_ip}:6443"
    if existing:
        existing.endpoint = endpoint
        existing.auth_config = auth_config
        existing.enabled = True
        existing.last_status = "unknown"
        existing.last_error = ""
        ds = existing
    else:
        ds = DataSource(
            name=ds_name, type="kubernetes", endpoint=endpoint,
            auth_type="kubeconfig", auth_config=auth_config,
            scrape_interval=60, enabled=True, last_status="unknown",
        )
        db.add(ds)
    db.commit()
    logger.info(f"K8S 集群 {ds_name} 已接入平台 DataSource(id={ds.id})")
    return ds


def run_deploy(db: Session, plan_id: int):
    """集群部署入口(生成器，供 WS/SSE 流式推送)。支持从 stopped 状态断点续传。"""
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
    try:
        if resume:
            _append_log(p, {"type": "info", "message": f"断点续传：从阶段{p.current_step}继续(已完成阶段幂等跳过)"}, db)
            yield {"type": "log", "message": f"断点续传：从阶段{p.current_step}继续"}
        yield from _run_deploy_generator(db, p, plan_id, resume_step=p.current_step if resume else 0)
    finally:
        _release_exec(plan_id)


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
