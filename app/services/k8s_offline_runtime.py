"""子模块: k8s_offline 执行步骤 + 编排执行辅助(拆分生成)"""

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

from app.services.k8s_offline_common import (  # noqa: F401
    _now, _safe_json, _append_log, _parse_cert_expiry, _get_assets,
    _resolve_node_conn, _node_to_dict, _plan_to_dict, _k8s_ai_provider,
    _k8s_ai_call, _set_pending_decision, _current_plan_id,
    _register_channel, _unregister_channel, _interrupt_plan_channels,
    _await_k8s_decision, _DeployStopped,
    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,
    _ACTIVE_CHANNELS_LOCK,
)

# ─── 原 L467-505 ───
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


# ─── 原 L508-521 ───
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


# ─── 原 L524-549 ───
def _run_remote(client, command: str, timeout: int = 300) -> dict:
    """在已连接 SSH client 上执行命令，返回 {ok, stdout, stderr, exit_code}。

    停止感知：注册当前 channel，若用户点了「停止」，watchdog 会 close 该 channel，
    使阻塞的 stdout.read() 立即抛错返回失败，从而中断长耗时 SSH 命令。
    """
    guard = _threading.Event() if _use_stop_guard() else None
    started = _threading.Event()
    chan = None
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        chan = stdout.channel
        _register_channel(chan)
        if guard is not None:
            _spawn_stop_guard(guard, started, chan)
            started.set()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        return {"ok": rc == 0, "stdout": out, "stderr": err, "exit_code": rc}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "exit_code": -1}
    finally:
        if guard is not None:
            guard.set()
        _unregister_channel(chan)


# ─── 原 L552-585 ───
def _iter_remote(client, command: str, timeout: int = 300):
    """逐行执行远程命令，yield (line, is_stderr)。停止时提前结束。"""
    chan = None
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        import select
        chan = stdout.channel
        chan.settimeout(0.2)
        err_chan = stderr.channel
        _register_channel(chan)
        while True:
            if _check_stop_remote():
                break
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
    finally:
        _unregister_channel(chan)


# ── 停止感知辅助 ──


# ─── 原 L587-589 ───
def _use_stop_guard() -> bool:
    """仅当前线程属于某个部署计划时才启用停止中断 watchdog。"""
    return _current_plan_id() is not None


# ─── 原 L592-594 ───
def _check_stop_remote() -> bool:
    pid = _current_plan_id()
    return bool(pid and _STOPPED.get(pid, False))


# ─── 原 L597-615 ───
def _spawn_stop_guard(guard: _threading.Event, started: _threading.Event, chan) -> None:
    """后台 watchdog：检测到 _STOPPED[plan_id] 置位后 close channel 以中断阻塞读。
    guard: 命令结束时置位，令 watchdog 退出。started: 主线程已进入阻塞读的信号。"""

    def _watch():
        try:
            started.wait(timeout=2)
            while not guard.is_set():
                if _check_stop_remote():
                    try:
                        chan.close()
                    except Exception:
                        pass
                    return
                guard.wait(timeout=0.3)
        except Exception:
            pass

    _threading.Thread(target=_watch, daemon=True).start()


# ─── 原 L618-625 ───
def _sftp_put(client, local: Path, remote: str, mode: int = 0o755):
    """通过 SFTP 上传单文件到远程并设置权限。"""
    sftp = client.open_sftp()
    try:
        sftp.put(str(local), remote)
        sftp.chmod(remote, mode)
    finally:
        sftp.close()


# ─── 原 L628-635 ───
def _exec_ssh_db(db: Session, p: K8sClusterPlan, node: K8sClusterNode, label: str, yield_event=None):
    """建立节点 SSH 连接(带 TOFU)。返回 (client, conn)。连接异常时写日志并抛出。"""
    conn = _resolve_node_conn(db, node)
    _append_log(p, {"type": "ssh", "node": label, "message": f"连接 {conn['ip']}:{conn['port']}"}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": f"连接 {conn['ip']}:{conn['port']}"})
    client = connect_ssh(conn["ip"], port=conn["port"], username=conn["username"],
                         password=conn["password"], timeout=15)
    return client, conn


# ─── 原 L638-652 ───
def _inject_etc_hosts(db, p, nodes, client, label) -> None:
    """在节点写入 /etc/hosts 的集群节点映射(主机名与 set-hostname 同源, 保证可解析)。"""
    lines = []
    for n in nodes:
        hn = _node_hostname(n, f"{n.get('host_role','node')}:{n.get('ip','')}")
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


# ─── 原 L655-659 ───
def _disable_swap(client, label, p, db) -> None:
    r = _run_remote(client,
                    "swapoff -a; sed -i '/ swap /s/^/#/' /etc/fstab; echo ok", timeout=120)
    if not r["ok"]:
        _append_log(p, {"type": "warn", "node": label, "message": "关闭 swap 失败: " + r["stderr"][:200]}, db)


# ─── 原 L662-683 ───
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
# SELinux 设为 permissive：cilium 等 CNI 需向宿主机 /hostbin 等 hostPath 写节点二进制，
# Enforcing 会拦截导致 Permission denied / Pod 无法就绪
[ -f /etc/selinux/config ] && sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
setenforce 0 2>/dev/null || true
echo ok''', timeout=120)
    if not r["ok"]:
        _append_log(p, {"type": "warn", "node": label,
                        "message": f"内核模块/sysctl 配置警告: {r['stderr'][:200]}"}, db)


# ─── 原 L686-689 ───
def _set_hostname(client, node, label, p, db) -> str:
    hn = _node_hostname(node, label)
    _run_remote(client, f"hostnamectl set-hostname {hn} 2>/dev/null; echo ok", timeout=60)
    return hn


# ─── 原 L692-708 ───
def _node_hostname(node, fallback_label: str) -> str:
    """解析节点的合法主机名。node 可含 hostname/ip/host_role。
    空 hostname 绝不 fallback 到 label(如 "master:")——那是非法/难解析主机名，
    而是生成合法名: hostname || k8s-<role>-<ip末段> || k8s-<role>-<fallback哈希>。
    """
    hn = (node.get("hostname") or "").strip()
    if hn:
        return hn
    ip = (node.get("ip") or "").strip()
    role = (node.get("host_role") or "node").strip()
    if ip:
        last = ip.rsplit(".", 1)[-1]
        return f"k8s-{role}-{last}" if last.isdigit() else f"k8s-{role}-{ip}"
    if fallback_label:
        tag = "".join(c for c in fallback_label if c.isalnum())
        return f"k8s-{role}-{tag or 'node'}"
    return f"k8s-{role}-node"


# ─── 原 L711-753 ───
def _ensure_dns(client, label, p, db, yield_event=None) -> None:
    """确保 /etc/resolv.conf 存在且可用。kubelet 创建 Pod sandbox 依赖 resolv.conf；
    若集群节点缺少 DNS 配置, 自动探测内网可达 DNS(优先同网段 .2/网关)并写入。"""
    script = (
        # 已有可信 resolv.conf 则不干预
        "if [ -f /etc/resolv.conf ] && grep -q nameserver /etc/resolv.conf; then echo DNS_OK; exit 0; fi; "
        # 收集候选 DNS: 网关主机位 .2, .1, 同网段常见地址
        "GW=$(ip route 2>/dev/null | awk '/default via/{print $3; exit}'); "
        "BASE=${GW%.*}; "
        "for d in \"${BASE}.2\" \"${BASE}.1\" \"$GW\" \"192.168.1.1\" \"192.168.100.1\" \"10.0.2.2\" \"114.114.114.114\" \"223.5.5.5\"; do "
        "[ -n \"$d\" ] || continue; "
        "if timeout 2 bash -c \"echo > /dev/tcp/$d/53\" 2>/dev/null; then "
        "echo \"nameserver $d\" > /etc/resolv.conf; "
        "sed -i 's/^nameserver/nameserver/' /etc/resolv.conf; "
        "chmod 644 /etc/resolv.conf; echo \"DNS_SET=$d\"; exit 0; "
        "fi; "
        "done; "
        # 全部探测失败也必须创建 resolv.conf(哪怕内容不可达)：
        # kubelet 创建 Pod sandbox 硬依赖 /etc/resolv.conf 存在(open 失败直接阻断 sandbox 创建)，
        # 缺文件会导致 apiserver/etcd 等静态 pod 永远起不来。兜底用网关或 127.0.0.1 占位。
        "if [ ! -f /etc/resolv.conf ]; then "
        "  echo \"nameserver ${GW:-127.0.0.1}\" > /etc/resolv.conf; "
        "  chmod 644 /etc/resolv.conf; echo DNS_FALLBACK; "
        "  exit 0; "
        "fi; "
        "echo DNS_NOT_FOUND"
    )
    r = _run_remote(client, script, timeout=60)
    out = r["stdout"].strip()
    if "DNS_SET=" in out:
        dns = out.split("DNS_SET=")[-1].strip()
        _append_log(p, {"type": "info", "node": label, "message": f"已配置 DNS({dns})"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": f"已配置 DNS({dns})"})
    elif "DNS_OK" in out:
        pass
    elif "DNS_FALLBACK" in out:
        _append_log(p, {"type": "warn", "node": label,
                        "message": "未探测到可用外部 DNS, 已创建占位 resolv.conf(网关/127.0.0.1), 保证 kubelet sandbox 可创建"}, db)
        if yield_event: yield_event({"type": "log", "node": label,
                                     "message": "未探测到可用外部 DNS, 已创建占位 resolv.conf"})
    else:
        _append_log(p, {"type": "warn", "node": label, "message": "未找到可用 DNS, kubelet sandbox 可能受影响"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "未找到可用 DNS, kubelet sandbox 可能受影响"})


# ─── 原 L756-784 ───
def _grant_admin_clusteradmin(client, label, p, db) -> None:
    """k8s>=1.28 kubeadm 的 admin.conf(kubernetes-admin)不再默认具备 cluster-admin,
    超管权限在 super-admin.conf(kubernetes-super-admin, 组 system:masters)。
    需幂等补绑: 用 super-admin.conf 把 kubernetes-admin 绑到 cluster-admin, 否则
    CNI/节点验证等基于 admin.conf 的 kubectl 操作会全部 Forbidden。
    """
    if _keepalive_check_stopped(p, db, label):
        return
    cmd = (
        'for KC in /etc/kubernetes/super-admin.conf /etc/kubernetes/admin.conf; do '
        '  [ -f "$KC" ] || continue; '
        '  export KUBECONFIG=$KC; '
        '  if kubectl get clusterrolebinding kubeadm-cluster-admins-grant >/dev/null 2>&1; then '
        '    echo GRANT_ALREADY; '
        '  else '
        '    kubectl create clusterrolebinding kubeadm-cluster-admins-grant '
        '      --clusterrole=cluster-admin --group=kubeadm:cluster-admins 2>/dev/null '
        '      && echo GRANT_OK && break; '
        '  fi; '
        'done; '
        'export KUBECONFIG=/etc/kubernetes/admin.conf; '
        "kubectl auth can-i '*' '*' --all-namespaces >/dev/null 2>&1 && echo ADMIN_FULL_OK || echo ADMIN_PARTIAL"
    )
    r = _run_remote(client, cmd, timeout=90)
    out = (r.get("stdout") or "") + " " + (r.get("stderr") or "")
    if "GRANT_OK" in out or "GRANT_ALREADY" in out or "ADMIN_FULL_OK" in out:
        _append_log(p, {"type": "ok", "node": label, "message": "已为 admin 授权 cluster-admin(适配 kubeadm>=1.28 RBAC)"}, db)
    else:
        _append_log(p, {"type": "warn", "node": label, "message": f"admin 授权 cluster-admin 未完全成功: {out[:200]}"}, db)


# ─── 原 L787-789 ───
def _keepalive_check_stopped(p, db, label) -> bool:
    """占位/幂等辅助: 若计划已标记停止则跳过(极少用)。"""
    return False


# ─── 原 L792-816 ───
def _ensure_core_addons(fclient, label, p, db) -> None:
    """确保核心 addon(kube-proxy / coredns)存在。
    触发背景: k8s>=1.28 断点续传/跳过 init 时 addon 可能未创建; 而 kube-proxy 缺失会
    导致 service ClusterIP 不可达, calico 等 CNI pod 的 init 无法经 service IP 访问
    API server 而 CrashLoop。这里幂等补全 kubeadm addon 阶段。
    """
    probe = (
        "export KUBECONFIG=/etc/kubernetes/admin.conf; "
        "kubectl get ds -n kube-system -l k8s-app=kube-proxy --no-headers 2>/dev/null | wc -l; "
        "kubectl get deploy -n kube-system coredns --no-headers 2>/dev/null | wc -l"
    )
    r = _run_remote(fclient, probe, timeout=60)
    lines = [ln.strip() for ln in (r.get("stdout") or "").splitlines() if ln.strip()]
    miss_proxy = not lines or lines[0] != "1"
    miss_coredns = len(lines) < 2 or lines[1] != "1"
    if not miss_proxy and not miss_coredns:
        return
    # 缺失则用 kubeadm addon phase 补全(API server 应已就绪)
    if miss_proxy:
        _append_log(p, {"type": "info", "node": label, "message": "核心组件 kube-proxy 缺失，自动补全(kubeadm addon)..."}, db)
        _run_remote(fclient, "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; kubeadm init phase addon kube-proxy --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; echo done", timeout=120)
    if miss_coredns:
        _append_log(p, {"type": "info", "node": label, "message": "核心组件 coredns 缺失，自动补全(kubeadm addon)..."}, db)
        _run_remote(fclient, "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; kubeadm init phase addon coredns --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; echo done", timeout=120)
    _append_log(p, {"type": "ok", "node": label, "message": "核心组件(kube-proxy/coredns)确保就绪"}, db)


# ─── 原 L819-860 ───
def _fix_cni_kubeconfig_localhost(client, label, p, db) -> None:
    """根治单节点 calico CNI 访问 API server 的 TCP/TLS 竞态:
    CNI 插件经 service IP(10.96.0.1)或 node IP(11.0.1.134)高频短连接时, 本机往返
    conntrack/DNAT 竞态导致间歇 EOF / TLS handshake timeout → 所有非 hostNetwork pod
    sandbox 创建失败(CrashLoopBackOff/ContainerCreating)。
    解法: 让 calico CNI 通过 127.0.0.1 回环访问 API server(绕开 DNAT 竞态路径),
    配 insecure-skip-tls-verify(apiserver 证书 SAN 无 127.0.0.1) + calico-cni-plugin 真实 token。
    """
    if p.cni not in ("calico",):
        return
    script = (
        "export KUBECONFIG=/etc/kubernetes/admin.conf; "
        "TOKEN=$(kubectl create token calico-cni-plugin -n kube-system --duration=87600h 2>/dev/null | tr -d '\\r'); "
        "if [ -z \"$TOKEN\" ]; then echo FIX_SKIP_NO_TOKEN; exit 0; fi; "
        "cat > /etc/cni/net.d/calico-kubeconfig <<'EOF2'\n"
        "apiVersion: v1\n"
        "kind: Config\n"
        "clusters:\n"
        "- name: local\n"
        "  cluster:\n"
        "    server: https://127.0.0.1:6443\n"
        "    insecure-skip-tls-verify: true\n"
        "contexts:\n"
        "- name: context\n"
        "  context:\n"
        "    cluster: local\n"
        "    user: calico\n"
        "current-context: context\n"
        "users:\n"
        "- name: calico\n"
        "  user:\n"
        "    token: $TOKEN\n"
        "EOF2\n"
        "echo CNI_KUBECONFIG_FIXED"
    )
    r = _run_remote(client, script, timeout=90)
    out = (r.get("stdout") or "") + (r.get("stderr") or "")
    if "CNI_KUBECONFIG_FIXED" in out:
        _append_log(p, {"type": "ok", "node": label,
                        "message": "CNI kubeconfig 已改为 127.0.0.1 回环 + calico token(根治单节点 CNI↔API TCP 竞态)"}, db)
    elif "NO_TOKEN" in out:
        _append_log(p, {"type": "warn", "node": label, "message": "无法获取 calico-cni-plugin token, 跳过 CNI kubeconfig 回环化"}, db)


# ─── 原 L863-892 ───
def _ensure_cni_plugins(client, label, p, db) -> None:
    """确保 /opt/cni/bin 存在 CNI 基础插件(loopback/bridge/portmap/host-local 等)。
    缺少时下载 containernetworking/plugins 静态包并解压。代理依赖 plan http_proxy。"""
    r = _run_remote(client, "ls /opt/cni/bin/loopback /opt/cni/bin/bridge /opt/cni/bin/portmap >/dev/null 2>&1 && echo HAVE || echo MISSING", timeout=30)
    if "HAVE" in r["stdout"]:
        return
    _append_log(p, {"type": "info", "node": label, "message": "缺少 CNI 基础插件(loopback/bridge等)，尝试下载..."}, db)
    proxy = _proxy_env_script(p)
    # 确保 tar 存在(干净 RHEL 可能缺 tar, 影响解压)
    _run_remote(client,
                proxy +
                "if ! command -v tar >/dev/null 2>&1; then "
                "if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then "
                "$(command -v dnf >/dev/null 2>&1 && echo dnf || echo yum) install -y tar >/dev/null 2>&1; "
                "elif command -v apt-get >/dev/null 2>&1; then apt-get install -y tar >/dev/null 2>&1; fi; fi",
                timeout=300)
    dl = (
        proxy +
        "mkdir -p /opt/cni/bin; "
        "curl -fsSL -A 'curl/8.4' -o /tmp/cni-plugins.tgz "
        "'https://github.com/containernetworking/plugins/releases/download/v1.5.1/cni-plugins-linux-amd64-v1.5.1.tgz' 2>&1 && "
        "tar -C /opt/cni/bin -xzf /tmp/cni-plugins.tgz 2>&1; "
        "rm -f /tmp/cni-plugins.tgz; "
        "ls /opt/cni/bin/loopback /opt/cni/bin/bridge >/dev/null 2>&1 && echo CNI_PLUGINS_OK || echo CNI_PLUGINS_FAIL"
    )
    r2 = _run_remote(client, dl, timeout=600)
    if "CNI_PLUGINS_OK" in r2["stdout"]:
        _append_log(p, {"type": "ok", "node": label, "message": "CNI 基础插件就绪(loopback/bridge/portmap等)"}, db)
    else:
        _append_log(p, {"type": "warn", "node": label, "message": "CNI 基础插件下载失败: " + (r2["stdout"] + r2["stderr"]).strip()[-200:]}, db)


# ─── 原 L929-994 ───
def _install_cilium(fclient, label, p, db, yield_event=None) -> bool:
    """通过 cilium-cli 安装 Cilium CNI。返回是否成功(agent ready)。
    下载 cilium-cli 静态二进制 → cilium install(指定 podCIDR 与其匹配) → cilium status。"""
    arch = _remote_arch(fclient)
    proxy = _proxy_env_script(p)
    cli_url = (f"https://github.com/cilium/cilium-cli/releases/download/{_CILIUM_CLI_VERSION}/"
               f"cilium-linux-{arch}.tar.gz")
    if yield_event: yield_event({"type": "log", "node": label, "message": "下载 cilium-cli..."})
    dl = (
        proxy +
        f"T=/tmp/cil-cli.tar.gz; curl -fsSL -A 'curl/8.4' '{cli_url}' -o $T && "
        f"tar -C /usr/local/bin -xzf $T cilium && chmod +x /usr/local/bin/cilium && rm -f $T; "
        f"which cilium && echo CLI_OK || echo CLI_FAIL"
    )
    rc = _run_remote(fclient, dl, timeout=600)
    if "CLI_OK" not in rc["stdout"]:
        _append_log(p, {"type": "warn", "node": label, "message": "cilium-cli 下载失败: " + (rc["stdout"] + rc["stderr"])[-200:]}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "cilium-cli 下载失败"})
        return False
    pod_cidr = (p.pod_cidr or "").strip() or "10.244.0.0/16"
    # cilium install 同时需要：访问外网 helm.cilium.io(走代理) + 连内网 API(不能走代理)。
    # 因此设代理并让 NO_PROXY 包含集群内网网段，而不是 unset 代理(否则拉 helm chart 失败)。
    proxy = _proxy_env_script(p)
    no_proxy_full = ("127.0.0.1,localhost,.local,10.96.0.0/12,10.244.0.0/16,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    proxy_env = proxy + f"export NO_PROXY='{no_proxy_full}'; "
    install = (
        proxy_env +
        "export KUBECONFIG=/etc/kubernetes/admin.conf; "
        f"/usr/local/bin/cilium install --version {_CILIUM_AGENT_VERSION} "
        f"--helm-set clusterPoolIPv4PodCIDR={pod_cidr} 2>&1; echo INSTALL_RC=$?"
    )
    if yield_event: yield_event({"type": "log", "node": label, "message": f"running cilium install (v{_CILIUM_AGENT_VERSION})..."})
    r = _run_remote(fclient, install, timeout=900)
    # 等待 agent 就绪(多次轮询)。若命中残留网卡冲突(cilium_vxlan address already in use)，
    # 自动清理残留虚拟网卡并强制重启 agent —— 这是 cilium 反复 CrashLoopBackOff 的已知根因。
    self_healed = False
    for i in range(6):
        time.sleep(20)
        st = _run_remote(fclient,
                         proxy_env +
                         "export KUBECONFIG=/etc/kubernetes/admin.conf; "
                         "/usr/local/bin/cilium status --wait 1>/tmp/cil-st.txt 2>&1; grep -iE 'Cilium is not ready|unhealthy|DaemonSet.*?not ready' /tmp/cil-st.txt >/dev/null 2>&1 && echo NOTREADY || (grep -qE 'Ready' /tmp/cil-st.txt && echo READY || echo PENDING)",
                         timeout=60)
        if "READY" in st["stdout"]:
            _append_log(p, {"type": "ok", "node": label, "message": "Cilium CNI 安装完成且 agent Ready"}, db)
            if yield_event: yield_event({"type": "log", "node": label, "message": "Cilium CNI Ready"})
            return True
        # 未就绪：检测 cilium agent 是否因残留网卡冲突而崩溃
        if not self_healed:
            crash = _run_remote(fclient,
                                "export KUBECONFIG=/etc/kubernetes/admin.conf; "
                                "POD=$(kubectl -n kube-system get pod -l app.kubernetes.io/name=cilium-agent "
                                "-o jsonpath='{.items[0].metadata.name}' 2>/dev/null); "
                                "kubectl -n kube-system logs \"$POD\" --tail=40 2>&1 | grep -i 'address already in use' >/dev/null 2>&1 && echo CONFLICT || echo CLEAN",
                                timeout=60)
            if "CONFLICT" in crash["stdout"]:
                if yield_event: yield_event({"type": "log", "node": label, "message": "检测到 cilium 残留网卡冲突,自动清理后重启 agent..."})
                cl = ("export KUBECONFIG=/etc/kubernetes/admin.conf; "
                      "kubectl -n kube-system delete pod -l app.kubernetes.io/name=cilium-agent --force --grace-period=0 >/dev/null 2>&1; "
                      "for d in cilium_vxlan cilium_net cilium_host tunl0 cni0 flannel.1; do ip link del $d >/dev/null 2>&1; done; "
                      "echo CLEANED")
                _run_remote(fclient, cl, timeout=120)
                self_healed = True
                continue
    _append_log(p, {"type": "warn", "node": label, "message": "Cilium 安装后状态未完全就绪: " + (r["stdout"] + r["stderr"])[-200:]}, db)
    return False


# ─── 原 L997-1012 ───
def _normalize_k8s_version(v: str) -> str:
    """规范化 K8s 版本字符串，保证可用于 dl.k8s.io 路径。
    处理用户手误与乱填：去空格、补 v 前缀、去多余点(如 v.1.31.6 -> v1.31.6)、
    不合法(缺主/次版本)时回退到稳定默认 v1.31。"""
    s = (v or "").strip().lstrip("v").lstrip(".")
    # 去多余点: 把 ".." 和 "a..b" 空段清理, 如 v.1.31.6 -> 1.31.6
    while ".." in s:
        s = s.replace("..", ".")
    # 若非标准 X.Y[.Z] 则回退
    parts = s.split(".")
    if not parts[0].isdigit() or len(parts) < 2 or not parts[1].isdigit():
        return "v1.31"
    major, minor = parts[0], parts[1]
    if len(parts) >= 3 and parts[2].isdigit():
        return f"v{major}.{minor}.{parts[2]}"
    return f"v{major}.{minor}"


# ─── 原 L1015-1065 ───
def _install_preflight_deps(client, label, p, db, yield_event=None) -> None:
    """安装 kubeadm preflight 依赖：conntrack/ethtool/socat，并确保 tar 存在。
    逐个依赖分步安装并实时推送进度，避免"长时间静默"让用户误以为卡死。"""
    http_p = p.http_proxy or ""
    https_p = p.https_proxy or http_p or ""
    proxy = _proxy_env_script(p)
    proxy_conf = ""
    if http_p:
        proxy_conf = (
            "cat /etc/apt/apt.conf.d/95proxies 2>/dev/null | grep -q 'Acquire::http::Proxy' || "
            f"printf 'Acquire::http::Proxy \"{http_p}\";\\nAcquire::https::Proxy \"{https_p or http_p}\";\\n' "
            "> /etc/apt/apt.conf.d/95proxies; "
        )
    pmgr_num = (
        "if command -v dnf >/dev/null 2>&1; then echo dnf; "
        "elif command -v yum >/dev/null 2>&1; then echo yum; "
        "elif command -v apt-get >/dev/null 2>&1; then echo apt; else echo none; fi"
    )
    pmgr_r = _run_remote(client, pmgr_num, timeout=30)
    pmgr = pmgr_r["stdout"].strip().splitlines()[-1] if pmgr_r["stdout"].strip() else "none"

    want = {"conntrack": "conntrack-tools", "ethtool": "ethtool", "socat": "socat", "tar": "tar"}
    want_cmd = {"conntrack": "conntrack", "ethtool": "ethtool", "socat": "socat", "tar": "tar"}
    needed = []
    for dep in want:
        # 检测当前是否已装
        chk = _run_remote(client, f"command -v {want_cmd[dep]} >/dev/null 2>&1 && echo YES || echo NO", timeout=30)
        if "YES" not in chk["stdout"]:
            needed.append(dep)
            if yield_event:
                yield_event({"type": "log", "node": label, "message": f"安装依赖 {want_cmd[dep]}..."})
    ok_all = True
    if needed:
        pkgs = " ".join(want[d] for d in needed)
        if pmgr in ("dnf", "yum"):
            cmd = f"{proxy}{pmgr} install -y {pkgs} >/dev/null 2>&1; echo rc=$?"
        elif pmgr == "apt":
            cmd = f"{proxy}{proxy_conf}apt-get update >/dev/null 2>&1; apt-get install -y {pkgs} >/dev/null 2>&1; echo rc=$?"
        else:
            cmd = "echo rc=1"
        r = _run_remote(client, cmd, timeout=600)
        ok_all = "rc=0" in r["stdout"]
    verify = _run_remote(client, "which conntrack ethtool socat tar >/dev/null 2>&1 && echo HAVE || echo MISSING", timeout=30)
    if "HAVE" in verify["stdout"]:
        msg = f"preflight 依赖就绪(conntrack/ethtool/socat/tar)"
        status = "ok"
    else:
        msg = "preflight 依赖安装失败: " + verify["stdout"][-120:]
        status = "warn"
    _append_log(p, {"type": status, "node": label, "message": msg}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": msg})


# ─── 原 L1583-1641 ───
def _probe_node_environment(client, p) -> dict:
    """SSH 只读采集节点环境信息, 供 AI 预检与自适应安装用。"""
    env = {
        "os_id": "", "os_version": "", "os_like": "",
        "pkg_mgr": "",            # apt / dnf / yum / unknown
        "has_tar": False, "has_curl": False,
        "has_containerd": False, "containerd_version": "",
        "has_docker": False, "docker_version": "", "has_cri_dockerd": False,
        "has_kubeadm": False, "has_kubelet": False, "has_kubectl": False,
        "epel_enabled": False, "offline_detected": False,
        "mem_mb": 0, "disk_avail_mb": 0,
    }
    script = (
        # 系统信息
        "OS=/etc/os-release; "
        "echo \"OS_ID=$(grep '^ID=' $OS 2>/dev/null | cut -d= -f2 | tr -d '\"\"')\"; "
        "echo \"OS_VER=$(grep '^VERSION_ID=' $OS 2>/dev/null | cut -d= -f2 | tr -d '\"\"')\"; "
        "echo \"OS_LIKE=$(grep '^ID_LIKE=' $OS 2>/dev/null | cut -d= -f2 | tr -d '\"\"')\"; "
        # 包管理器
        "command -v apt-get >/dev/null 2>&1 && echo PKGM=apt; "
        "command -v dnf >/dev/null 2>&1 && echo PKGM=dnf; "
        "command -v yum >/dev/null 2>&1 && echo PKGM=yum; "
        # 依赖
        "command -v tar >/dev/null 2>&1 && echo HAVE_TAR=1 || echo HAVE_TAR=0; "
        "command -v curl >/dev/null 2>&1 && echo HAVE_CURL=1 || echo HAVE_CURL=0; "
        # 含运行时 / 二进制现状
        "command -v containerd >/dev/null 2>&1 && echo CRT=1 && containerd --version 2>/dev/null | head -1 || echo CRT=0; "
        "command -v docker >/dev/null 2>&1 && echo DKR=1 && docker version --format '{{.Server.Version}}' 2>/dev/null | head -1 || echo DKR=0; "
        "test -x /usr/local/bin/cri-dockerd && echo CDD=1 || echo CDD=0; "
        "command -v kubeadm >/dev/null 2>&1 && echo KM=1 || echo KM=0; "
        "command -v kubelet >/dev/null 2>&1 && echo KL=1 || echo KL=0; "
        "command -v kubectl >/dev/null 2>&1 && echo KC=1 || echo KC=0; "
        # EPEL
        "[ -f /etc/yum.repos.d/epel.repo ] && echo EPEL=1 || echo EPEL=0; "
        # 资源
        "Mem=$(free -m 2>/dev/null | awk '/Mem:/{print $2}'); echo MEM=${Mem:-0}; "
        "Disk=$(df -m / 2>/dev/null | tail -1 | awk '{print $4}'); echo DISK=${Disk:-0}"
    )
    r = _run_remote(client, script, timeout=90)
    out = r["stdout"]
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("OS_ID="): env["os_id"] = line[6:].strip()
        elif line.startswith("OS_VER="): env["os_version"] = line[7:].strip()
        elif line.startswith("OS_LIKE="): env["os_like"] = line[8:].strip()
        elif line.startswith("PKGM="): env["pkg_mgr"] = line[5:].strip()
        elif line.startswith("HAVE_TAR="): env["has_tar"] = line[9:] == "1"
        elif line.startswith("HAVE_CURL="): env["has_curl"] = line[10:] == "1"
        elif line.startswith("CRT="): env["has_containerd"] = line[4:] == "1"
        elif line.startswith("containerd"): env["containerd_version"] = line
        elif line.startswith("DKR="): env["has_docker"] = line[4:] == "1"
        elif line.startswith("CDD="): env["has_cri_dockerd"] = line[4:] == "1"
        elif line.startswith("KM="): env["has_kubeadm"] = line[3:] == "1"
        elif line.startswith("KL="): env["has_kubelet"] = line[3:] == "1"
        elif line.startswith("KC="): env["has_kubectl"] = line[3:] == "1"
        elif line.startswith("EPEL="): env["epel_enabled"] = line[5:] == "1"
        elif line.startswith("MEM="): env["mem_mb"] = int(line[4:].strip() or "0")
        elif line.startswith("DISK="): env["disk_avail_mb"] = int(line[5:].strip() or "0")
    return env


# ─── 原 L1758-1847 ───
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
        # 规范化版本号，避免 v.1.31.6 等错误格式导致 dl.k8s.io 404
        kv = _normalize_k8s_version(kv)
        if p.kubernetes_version and kv != p.kubernetes_version:
            _append_log(p, {"type": "warn", "node": label,
                            "message": f"K8s 版本 [{p.kubernetes_version}] 不规范，已自动校正为 [{kv}]"}, db)
        arch = _remote_arch(client)
        for b in list(missing):
            url = f"https://dl.k8s.io/{kv}/bin/linux/{arch}/{b}"
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


# ─── 原 L1850-1896 ───
def _generate_kubeadm_config(p, first_master_ip: str, ctx: dict) -> str:
    """在首 master 生成 kubeadm-config.yaml。"""
    if p.runtime == "docker":
        cri = "unix:///var/run/cri-dockerd.sock"   # k8s>=1.24 dockershim 已移除，Docker 走 cri-dockerd
    else:
        cri = "unix:///run/containerd/containerd.sock"
    kv = p.kubernetes_version
    if kv and not kv.startswith("v"):
        kv = "v" + kv
    repo = ctx.get("image_repository") or "registry.k8s.io"
    # kubelet 必须显式拿到运行时 endpoint：systemd 10-kubeadm.conf 的 ExecStart 只带
    # --config=config.yaml(KUBELET_CONFIG_ARGS)，不含 kubeadm 写入 kubeadm-flags.env 的
    # KUBELET_KUBEADM_ARGS，故单靠 InitConfiguration.criSocket 不能保证 kubelet 用 cri-dockerd。
    # 因此直接在 KubeletConfiguration.containerRuntimeEndpoint 写死运行时 socket, 最可靠。
    cri_endpoint_line = f"containerRuntimeEndpoint: {cri}" if p.runtime == "docker" else ""
    klet_cfg = ("cgroupDriver: systemd\n"
                + (cri_endpoint_line + "\n" if cri_endpoint_line else ""))
    cfg = f"""apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: {first_master_ip}
nodeRegistration:
  criSocket: {cri}
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: {kv or "stable"}
imageRepository: {repo}
apiServer:
  extraArgs:
    - name: service-node-port-range
      value: "30000-32767"
networking:
  podSubnet: {p.pod_cidr}
  serviceSubnet: {p.service_cidr}
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
{klet_cfg}"""
    if p.runtime == "containerd":
        cfg += f"""---
apiVersion: kubeadm.k8s.io/v1beta4
kind: JoinConfiguration
nodeRegistration:
  criSocket: {cri}
"""
    return cfg


# ─── 原 L1899-1926 ───
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
    # 用 ctr 导入（containerd k8s.io namespace）; docker 运行时用 docker load
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
        load_cmd = ("ctr -n=k8s.io images import /tmp/k8s-images/{f} >/dev/null 2>&1 && echo OK || echo FAIL"
                    if p.runtime != "docker" else
                    "docker load < /tmp/k8s-images/{f} >/dev/null 2>&1 && echo OK || echo FAIL")
        r = _run_remote(client, load_cmd.format(f=f.name), timeout=600)
        if "OK" in r["stdout"]:
            cnt += 1
    _append_log(p, {"type": "info", "node": label, "message": f"离线镜像本地导入 {cnt} 个"}, db)


# ─── 原 L1929-2005 ───
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
    # 2. 私有仓库认证:写到 containerd config.toml 的 registry.configs.\"<host>\".auth(CRI 实际读取的凭据位置),
    #    而非 hosts.toml. 否则 kubeadm/CTR 拉带认证的仓库会报 \"no basic auth credentials\"。
    #    用 SFTP 读回 config.toml, 在宿主侧改写好支持认证的块再回写(幂等, 不破坏 mirrors/headers 等后续段)。
    reg_user = (ctx.get("registry_username") or "").strip()
    reg_pass = (ctx.get("registry_password") or "").strip()
    if reg_user:
        _cfg_path = "/etc/containerd/config.toml"
        _cfg = ""
        try:
            _sftp = client.open_sftp()
            with _sftp.open(_cfg_path, "r") as _f:
                _cfg = _f.read().decode("utf-8")
        except Exception:
            _cfg = ""
        if _cfg:
            _mk = '[plugins."io.containerd.grpc.v1.cri".registry.configs]'
            _auth_cfg = (
                '[plugins."io.containerd.grpc.v1.cri".registry.configs.%s]\n'
                '    [plugins."io.containerd.grpc.v1.cri".registry.configs.%s.auth]\n'
                '      username = "%s"\n'
                '      password = "%s"\n'
            ) % ('"%s"' % host, '"%s"' % host, reg_user, reg_pass)
            if ('registry.configs.%s' % ('"%s"' % host)) in _cfg:
                _append_log(p, {"type": "info", "node": label,
                                "message": f"私有 Registry 认证已存在: {host}"}, db)
            else:
                _cfg = _cfg.replace(_mk, _mk + "\n" + _auth_cfg, 1)
                try:
                    _sftp2 = client.open_sftp()
                    with _sftp2.open(_cfg_path, "w") as _f:
                        _f.write(_cfg)
                    _append_log(p, {"type": "info", "node": label,
                                    "message": f"containerd 已配置私有 Registry 认证: {host}"}, db)
                except Exception as _e:
                    _append_log(p, {"type": "warn", "node": label,
                                    "message": f"私有 Registry 认证写入失败: {_e}"}, db)
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


# ─── 原 L2008-2118 ───
def _apply_cert_expiry(fclient, label, p, db, yield_event=None) -> bool:
    """将节点 K8s 全部证书(三个 CA + 所有叶子证书)统一重签为 N 年, 保留各自 subject/SAN。
    - 三套 CA(ca / front-proxy-ca / etcd/ca): 用各自 key 自签 N 年(保留 CA 扩展)
    - 叶子证书: 按 issuer 路由到对应 CA key, 用 -copy_extensions 保留 SAN 重签 N 年
    - CA key 全程不变 → 旧叶子仍由同 key 校验, 集群不中断; 全部证书到期时间一致=N年
    返回是否成功(证书已是目标年限则幂等跳过)。"""
    years = (p.cert_expiry_years or 0)
    if not years or years < 1:
        return True  # 未配置 cert_expiry_years, 用平台默认, 无需重签
    days = str(int(years) * 365)
    pki = "/etc/kubernetes/pki"
    # 幂等: 全部证书已 >= 目标年限则跳过(用 notAfter 距今 > days 判断 apiserver 作为代表)
    probe = _run_remote(fclient,
                        f"openssl x509 -in {pki}/apiserver.crt -noout -enddate 2>/dev/null | cut -d= -f2",
                        timeout=30)
    if _cert_days_remaining_check(probe["stdout"], years):
        _append_log(p, {"type": "info", "node": label, "message": f"证书已为 {years} 年有效期，跳过重签(幂等)"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": f"证书已为 {years} 年有效期，跳过重签"})
        return True
    # 备份只有首次做
    _run_remote(fclient, f"[ -d {pki}.bk ] || cp -a {pki} {pki}.bk; echo bk_ok", timeout=60)
    script = (
        "set -e\n"
        f"PKI={pki}; D={days}\n"
        "cd \"$PKI\" || exit 1\n"
        "ok=1\n"
        "resign_leaf() { # cert key ca_crt ca_key\n"
        "  local c=$1 k=$2 cac=$3 cak=$4\n"
        "  [ -f \"$c\" ] || return 0\n"
        "  openssl x509 -x509toreq -in \"$c\" -signkey \"$k\" -out /tmp/_r.csr -copy_extensions copy 2>/dev/null || return 1\n"
        "  openssl x509 -req -in /tmp/_r.csr -CA \"$cac\" -CAkey \"$cak\" -CAcreateserial -out /tmp/_r.crt -days \"$D\" -sha256 -copy_extensions copy 2>/dev/null || return 1\n"
        "  cp /tmp/_r.crt \"$c\"; rm -f /tmp/_r.csr /tmp/_r.crt; return 0\n"
        "}\n"
        "resign_ca() { # ca_crt ca_key\n"
        "  local cac=$1 cak=$2\n"
        "  openssl x509 -x509toreq -in \"$cac\" -signkey \"$cak\" -out /tmp/_ca.csr -copy_extensions copy 2>/dev/null || return 1\n"
        "  openssl x509 -req -in /tmp/_ca.csr -signkey \"$cak\" -out /tmp/_ca.crt -days \"$D\" -sha256 -copy_extensions copy 2>/dev/null || return 1\n"
        "  cp /tmp/_ca.crt \"$cac\"; rm -f /tmp/_ca.csr /tmp/_ca.crt; return 0\n"
        "}\n"
        # 1) 三个 CA 用各自 key 自签
        "resign_ca ca.crt ca.key || ok=0\n"
        "resign_ca front-proxy-ca.crt front-proxy-ca.key || ok=0\n"
        "resign_ca etcd/ca.crt etcd/ca.key || ok=0\n"
        # 2) 叶子: apiserver 系列 + front-proxy-client 走对应 CA
        "resign_leaf apiserver.crt apiserver.key ca.crt ca.key || ok=0\n"
        "resign_leaf apiserver-kubelet-client.crt apiserver-kubelet-client.key ca.crt ca.key || ok=0\n"
        "resign_leaf apiserver-etcd-client.crt apiserver-etcd-client.key etcd/ca.crt etcd/ca.key || ok=0\n"
        "resign_leaf front-proxy-client.crt front-proxy-client.key front-proxy-ca.crt front-proxy-ca.key || ok=0\n"
        "resign_leaf etcd/server.crt etcd/server.key etcd/ca.crt etcd/ca.key || ok=0\n"
        "resign_leaf etcd/peer.crt etcd/peer.key etcd/ca.crt etcd/ca.key || ok=0\n"
        "resign_leaf etcd/healthcheck-client.crt etcd/healthcheck-client.key etcd/ca.crt etcd/ca.key || ok=0\n"
        # 3) kubeconfig 内嵌客户端证书(admin/controller-manager/scheduler/super-admin)统一重签为 N 年。
        #    用 kubernetes CA(ca.crt/ca.key)重签, 保留 subject + SAN, base64 写回原字段。
        #    (不含 kubelet.conf —— 其证书由 kubelet 自动轮换管理, 硬改会被覆盖, 保持 kubeadm 默认。)
        "resign_kubeconfig() { # cfg_path\n"
        "  local CFG=$1\n"
        "  [ -f \"$CFG\" ] || return 0\n"
        "  CERTB64=$(grep 'client-certificate-data:' \"$CFG\" | head -1 | awk '{print $2}')\n"
        "  KEYB64=$(grep 'client-key-data:' \"$CFG\" | head -1 | awk '{print $2}')\n"
        "  [ -z \"$CERTB64\" ] || [ -z \"$KEYB64\" ] && return 1\n"
        "  echo \"$CERTB64\" | base64 -d > /tmp/_kc.pem 2>/dev/null || return 1\n"
        "  echo \"$KEYB64\" | base64 -d > /tmp/_kk.pem 2>/dev/null || return 1\n"
        "  [ -s /tmp/_kc.pem ] || return 1\n"
        "  openssl x509 -x509toreq -in /tmp/_kc.pem -signkey /tmp/_kk.pem -out /tmp/_kc.csr -copy_extensions copy 2>/dev/null || return 1\n"
        "  openssl x509 -req -in /tmp/_kc.csr -CA \"$PKI\"/ca.crt -CAkey \"$PKI\"/ca.key -CAcreateserial -out /tmp/_kc.new -days \"$D\" -sha256 -copy_extensions copy 2>/dev/null || return 1\n"
        "  NEWB64=$(base64 -w0 /tmp/_kc.new 2>/dev/null || { base64 /tmp/_kc.new | tr -d '\\n'; })\n"
        "  [ -n \"$NEWB64\" ] || return 1\n"
        "  sed -i \"0,/client-certificate-data:.*/s//client-certificate-data: $NEWB64/\" \"$CFG\" || return 1\n"
        "  rm -f /tmp/_kc.pem /tmp/_kk.pem /tmp/_kc.csr /tmp/_kc.new\n"
        "  return 0\n"
        "}\n"
        "resign_kubeconfig \"$PKI/../admin.conf\" || ok=0\n"
        "resign_kubeconfig \"$PKI/../controller-manager.conf\" || ok=0\n"
        "resign_kubeconfig \"$PKI/../scheduler.conf\" || ok=0\n"
        "resign_kubeconfig \"$PKI/../super-admin.conf\" || ok=0\n"
        "if [ \"$ok\" != 1 ]; then echo CERT_RESIGN_PARTIAL; exit 0; fi\n"
        "echo CERT_RESIGN_OK\n"
    )
    r = _run_remote(fclient, script, timeout=300)
    out = r["stdout"] or ""
    if "CERT_RESIGN_OK" in out:
        # 校验各证书已是 N 年
        _check = _run_remote(fclient,
                             f"for f in {pki}/ca.crt {pki}/apiserver.crt {pki}/apiserver-etcd-client.crt "
                             f"{pki}/front-proxy-client.crt {pki}/etcd/server.crt {pki}/etcd/peer.crt; do "
                             f"openssl x509 -in $f -noout -enddate 2>/dev/null; done",
                             timeout=40)
        _append_log(p, {"type": "ok", "node": label,
                        "message": f"全部证书已统一重签为 {years} 年(CA+服务证书)"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": f"证书统一重签为 {years} 年完成，重启控制面加载..."})
        # 重启 kubelet + 各控制面静态 pod 以加载新证书(不删 manifest, kubelet 自动重建)
        _run_remote(fclient,
                    "rm -f /etc/kubernetes/manifests/kube-apiserver.yaml "
                    "/etc/kubernetes/manifests/kube-controller-manager.yaml "
                    "/etc/kubernetes/manifests/kube-scheduler.yaml; "
                    "systemctl restart kubelet >/dev/null 2>&1; "
                    "kubeadm init phase control-plane apiserver --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; "
                    "kubeadm init phase control-plane controller-manager --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; "
                    "kubeadm init phase control-plane scheduler --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1; "
                    "systemctl restart kubelet >/dev/null 2>&1; "
                    "(rm -f /etc/kubernetes/manifests/etcd.yaml; "
                    " kubeadm init phase etcd local --config /etc/kubernetes/kubeadm-config.yaml >/dev/null 2>&1;) "
                    "systemctl restart kubelet >/dev/null 2>&1; "
                    "for i in $(seq 1 30); do "
                    "  curl -sk -m 5 -o /dev/null -w '%{http_code}' https://127.0.0.1:6443/healthz 2>/dev/null | grep -q 200 && break; sleep 5; done; "
                    "echo or: $(curl -sk -m5 -o /dev/null -w '%{http_code}' https://127.0.0.1:6443/healthz 2>/dev/null)",
                    timeout=400)
        return True
    _append_log(p, {"type": "warn", "node": label,
                    "message": f"证书重签未完整成功: " + (out or r["stderr"] or "")[-200:] + "，已有备份可使用(" + pki + ".bk)"}, db)
    return False


# ─── 原 L2121-2131 ───
def _cert_days_remaining_check(enddate_line: str, years: int) -> bool:
    """根据 openssl enddate 输出判断证书剩余有效期是否 >= years 年。enddate 如 'notAfter=Jul 24 07:00:00 2126 GMT'"""
    if not enddate_line:
        return False
    val = enddate_line.split("=")[-1].strip()
    try:
        import datetime as _dt
        end = _dt.datetime.strptime(val, "%b %d %H:%M:%S %Y GMT")
        return (end - _dt.datetime.utcnow()).days >= years * 365
    except Exception:
        return False


# ─── 原 L2134-2141 ───
def _extract_yaml_images(fclient, yaml_path: str, label, p, db) -> list:
    """从下载的 CNI manifest 提取全部 image: 引用, 返回去重后的镜像列表(用于代理预拉)。"""
    r = _run_remote(fclient,
                    f"grep -oE 'image:\\s*\\S+' {yaml_path} 2>/dev/null | "
                    "sed 's/image:[[:space:]]*//' | sed 's/[\"\\'']//g' | sort -u",
                    timeout=60)
    imgs = [ln.strip() for ln in (r["stdout"] or "").splitlines() if ln.strip()]
    return imgs


# ─── 原 L2144-2162 ───
def _check_cni_pods(fclient, p: K8sClusterPlan, cni_names) -> bool:
    """确认目标 CNI/coredns pod 在 kube-system 命名空间均 Running(至少一个实例 Ready)。
    返回 True 表示全部就绪(含 coredns)。"""
    names_pat = "|".join(cni_names)
    cmd = (
        "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; "
        "export KUBECONFIG=/etc/kubernetes/admin.conf; "
        "kubectl get pods -n kube-system -o jsonpath='{range .items[*]}{.metadata.name}{\" \"}{.status.phase}{\" \"}{.status.conditions[?(@.type==\"Ready\")].status}{\"\\n\"}{end}' 2>/dev/null | "
        f"grep -E '({names_pat})' "
        # 统计每个目标 name 是否至少有一个 Ready=True 的运行项
        "> /tmp/cnicheck.txt 2>&1; "
        "ok=1; "
        f"for n in {' '.join(cni_names)}; do "
        "  if ! grep \"$n\" /tmp/cnicheck.txt | grep -q \"Running True\"; then ok=0; fi; "
        "done; "
        "echo CNI_OK=$ok"
    )
    r = _run_remote(fclient, cmd, timeout=60)
    return "CNI_OK=1" in (r["stdout"] or "")


