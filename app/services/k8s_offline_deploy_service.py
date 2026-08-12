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
import re
import time
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    "calico": "https://raw.githubusercontent.com/projectcalico/calico/master/manifests/calico.yaml",
    "flannel": "https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml",
    "cilium": "https://raw.githubusercontent.com/cilium/cilium/main/install/kubernetes/quick-install.yaml",
}

_CNI_POD_CIDR = {
    "calico": "10.244.0.0/16",
    "flannel": "10.244.0.0/16",
    "cilium": "10.0.0.0/8",
}

_EXEC_LOCK: Dict[int, bool] = {}
_STOPPED: Dict[int, bool] = {}

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
    _release_exec(plan_id)
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if p and p.status == "running":
        p.status = "failed"
        _append_log(p, {"type": "info", "message": "部署已被用户停止"}, db)
        db.commit()
    return {"ok": True}


def _release_exec(plan_id: int):
    _EXEC_LOCK.pop(plan_id, None)
    _STOPPED.pop(plan_id, None)


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


def _install_containerd(client, ctx, label, p, db) -> None:
    """安装 containerd：优先离线包 binaries/containerd，否则走包源。"""
    script = "which containerd && containerd --version 2>/dev/null || echo MISSING"
    r = _run_remote(client, script, timeout=60)
    if r["ok"] and "MISSING" not in r["stdout"]:
        _append_log(p, {"type": "info", "node": label, "message": "containerd 已安装，跳过"}, db)
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
    if not installed:
        # 走包源安装（deb/rpm）
        _run_remote(client, "apt-get install -y containerd >/dev/null 2>&1 || yum install -y containerd.io >/dev/null 2>&1; echo rc=$?", timeout=600)
    # 生成 containerd 配置
    cfg = (
        "mkdir -p /etc/containerd; containerd config default > /etc/containerd/config.toml 2>/dev/null || true; "
        "sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml "
        "|| sed -i 's/SystemdCgroup=false/SystemdCgroup=true/g' /etc/containerd/config.toml; "
        "systemctl enable containerd >/dev/null 2>&1; "
        "(systemctl restart containerd || pkill containerd; sleep 2); echo ok"
    )
    _run_remote(client, cfg, timeout=180)
    r = _run_remote(client, "containerd --version 2>/dev/null || echo FAIL", timeout=60)
    if "FAIL" in r["stdout"]:
        _append_log(p, {"type": "error", "node": label, "message": "containerd 安装/启动失败"}, db)
    else:
        _append_log(p, {"type": "info", "node": label, "message": "containerd 就绪: " + r["stdout"].strip()[:80]}, db)


def _install_k8s_binaries(client, ctx, label, p, db) -> None:
    """安装 kubeadm/kubelet/kubectl：优先离线包 binaries/，否则包源。"""
    need = []
    for b in ("kubeadm", "kubelet", "kubectl"):
        r = _run_remote(client, f"which {b} 2>/dev/null || echo MISSING", timeout=60)
        if "MISSING" in r["stdout"] or not r["ok"]:
            need.append(b)
    if not need:
        _append_log(p, {"type": "info", "node": label, "message": "k8s 二进制已存在，跳过"}, db)
        return
    xdir = ctx.get("extract_dir")
    missing = []
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
                    except Exception as e:
                        _append_log(p, {"type": "warn", "node": label, "message": f"上传 {b} 失败: {e}"}, db)
                        missing.append(b)
                else:
                    missing.append(b)
    if missing:
        # 退化：包源安装 kubeadm 全家桶
        _run_remote(client,
                    "apt-get install -y kubeadm kubelet kubectl >/dev/null 2>&1 || "
                    "yum install -y kubeadm kubelet kubectl >/dev/null 2>&1; echo rc=$?", timeout=900)
    # 启用 kubelet
    _run_remote(client,
                "systemctl enable kubelet >/dev/null 2>&1; "
                "mkdir -p /etc/systemd/system/kubelet.service.d; echo ok", timeout=120)


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
        _run_remote(client, f"mkdir -p /tmp/k8s-images && echo ok", timeout=60)
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


def _configure_insecure_registry(client, ctx, label, p, db) -> None:
    """节点配置 containerd 信任私有 Registry(insecure)。"""
    ru = ctx.get("registry_url")
    if not ru:
        return
    host = ru.split("/")[0]
    r = _run_remote(client,
                    f"grep -q '{host}' /etc/containerd/config.toml && echo HAVE || echo NEED", timeout=60)
    if "HAVE" in r["stdout"]:
        return
    # 追加 containerd CRI 私有仓库 insecure 配置(若 config 无 configs 段则新增)
    reg_block = (
        '      [plugins."io.containerd.grpc.v1.cri".registry.configs."%s".tls]\n'
        '        insecure_skip_verify = true\n'
        '      [plugins."io.containerd.grpc.v1.cri".registry.configs."%s"]\n'
        '        [plugins."io.containerd.grpc.v1.cri".registry.configs."%s".auth]\n'
        '        username = ""\n        password = ""\n' % (host, host, host)
    )
    script = (
        "if ! grep -q 'registry.configs' /etc/containerd/config.toml; then "
        "sed -i '/\\[plugins\\.\"io\\.containerd\\.grpc\\.v1\\.cri\".registry\\]\\]/a\\      [plugins.\"io.containerd.grpc.v1.cri\".registry.configs]' /etc/containerd/config.toml; fi; "
        f"cat >> /etc/containerd/config.toml <<'EOF'\n{reg_block}EOF\n"
        "systemctl restart containerd >/dev/null 2>&1 || pkill containerd; sleep 2; echo ok"
    )
    _run_remote(client, script, timeout=120)
    _append_log(p, {"type": "info", "node": label, "message": f"containerd 已信任私有 Registry: {host}"}, db)


def _run_deploy_generator(db, p: K8sClusterPlan, plan_id: int):
    """kubeadm 7 阶段编排生成器。yield 事件 dict(供 WS/SSE 推送)。"""
    yield {"type": "status", "status": "running", "message": "开始离线集群部署"}
    p.status = "running"
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
            label = f"{n.host_role}:{n.ip}"
            labels[n.id] = label
            n.status = "running"
            db.commit()
            try:
                client, conn = _exec_ssh_db(db, p, n, label)
                clients[n.id] = client
                r = _run_remote(client, "id -u; uname -r; which swapoff", timeout=60)
                _append_log(p, {"type": "ok", "node": label, "message": "SSH 连通，root=" + (r["stdout"].splitlines()[0] if r["stdout"] else "?")}, db)
                n.status = "succeeded"
            except Exception as e:
                n.status = "failed"
                _append_log(p, {"type": "error", "node": label, "message": f"SSH 连接失败: {e}"}, db)
                yield {"type": "log", "node": label, "message": f"SSH 连接失败: {e}"}
        db.commit()
        if any(n.status == "failed" for n in nodes_db):
            raise RuntimeError("存在无法连接的节点，中止部署")

        # ── 阶段1 环境准备(所有节点，可并行) ──
        p.current_step = 1
        yield {"type": "phase", "step": 1, "title": "阶段1/6 环境准备(swap/内核/hosts)"}
        for n in nodes_db:
            label = labels[n.id]
            client = clients[n.id]
            hn = _set_hostname(client, {"hostname": n.hostname}, label, p, db)
            _disable_swap(client, label, p, db)
            _setup_kernel(client, label, p, db)
        # /etc/hosts 全部集群节点映射
        all_nodes = [{"ip": _resolve_node_conn(db, x)["ip"], "hostname": x.hostname}
                     for x in nodes_db]
        for n in nodes_db:
            _inject_etc_hosts(db, p, all_nodes, clients[n.id], labels[n.id])
        _append_log(p, {"type": "ok", "message": "环境准备完成"}, db)

        # ── 阶段2 容器运行时 + k8s 二进制(所有节点) ──
        p.current_step = 2
        yield {"type": "phase", "step": 2, "title": "阶段2/6 运行时与二进制"}
        for n in nodes_db:
            label = labels[n.id]
            client = clients[n.id]
            if ctx.get("registry_url"):
                _configure_insecure_registry(client, ctx, label, p, db)
            _install_containerd(client, ctx, label, p, db)
            _install_k8s_binaries(client, ctx, label, p, db)
            _write_imagetar_jobs(client, ctx, label, p, db)
        _append_log(p, {"type": "ok", "message": "运行时与二进制就绪"}, db)
        yield {"type": "log", "message": "运行时与二进制就绪"}

        # ── 阶段3 首 master 生成配置 + 预拉镜像 ──
        p.current_step = 3
        yield {"type": "phase", "step": 3, "title": "阶段3/6 生成 kubeadm 配置"}
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
        _run_remote(fclient, "kubeadm config images pull --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; echo rc=$?", timeout=900)

        # ── 阶段4 kubeadm init ──
        p.current_step = 4
        yield {"type": "phase", "step": 4, "title": "阶段4/6 初始化控制平面"}
        init_cmd = ("kubeadm init --config /etc/kubernetes/kubeadm-config.yaml "
                    "--upload-certs")
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
            r = _run_remote(fclient, f"kubectl apply -f {remote_yaml} 2>&1; echo __CNI_RC__=$?", timeout=600)
            _append_log(p, {"type": "ok", "node": labels[first_master.id],
                            "message": "CNI 已应用(离线清单)" if r["ok"] else "CNI 应用异常: " + r["stderr"][:150]}, db)
        else:
            url = _DEFAULT_CNI_FILES.get(p.cni)
            if url:
                r = _run_remote(fclient,
                                f"curl -fsSL {url} -o /root/k8s-cni.yaml && kubectl apply -f /root/k8s-cni.yaml 2>&1; echo __CNI_RC__=$?",
                                timeout=600)
                _append_log(p, {"type": "info", "node": labels[first_master.id],
                                "message": f"CNI 在线下载并应用 rc={r['exit_code']}"}, db)
        yield {"type": "log", "node": labels[first_master.id], "message": "CNI 安装指令已下发"}

        # ── 阶段6 生成 join 凭证 + worker(及额外 master)加入 ──
        p.current_step = 6
        yield {"type": "phase", "step": 6, "title": "阶段6/6 节点加入"}
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

        p.status = "succeeded"
        p.report_json = json.dumps(_build_report(db, p), ensure_ascii=False)
        db.commit()
        yield {"type": "complete", "status": "succeeded",
               "message": f"集群 {p.name} 部署成功，已接入监控"}
    except Exception as e:
        p.status = "failed"
        _append_log(p, {"type": "error", "message": f"部署失败: {e}"}, db)
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


def _build_report(db: Session, p: K8sClusterPlan) -> dict:
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == p.id).all()
    return {
        "cluster_name": p.name,
        "kubernetes_version": p.kubernetes_version,
        "runtime": p.runtime,
        "cni": p.cni,
        "status": p.status,
        "node_matrix": [_node_to_dict(n) for n in nodes],
        "master_count": sum(1 for n in nodes if n.host_role == "master"),
        "worker_count": sum(1 for n in nodes if n.host_role != "master"),
    }


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
    """集群部署入口(生成器，供 WS/SSE 流式推送)。"""
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
    _EXEC_LOCK[plan_id] = True
    _STOPPED.pop(plan_id, None)
    try:
        yield from _run_deploy_generator(db, p, plan_id)
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


# 供逻辑预检(不校验 SSH)使用
def precheck_plan(db: Session, plan_id: int) -> dict:
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return {"ok": False, "issues": ["计划不存在"]}
    issues = []
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).all()
    if not any(n.host_role == "master" for n in nodes):
        issues.append("缺少 master 节点")
    if not p.pod_cidr:
        issues.append("缺少 Pod CIDR")
    if not p.service_cidr:
        issues.append("缺少 Service CIDR")
    for n in nodes:
        if not n.ip:
            issues.append(f"节点(id={n.id})缺少 IP")
    return {"ok": not issues, "issues": issues}
