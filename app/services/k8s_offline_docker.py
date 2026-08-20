"""子模块: k8s_offline docker/containerd 运行时(拆分生成)"""

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

from app.services.k8s_offline_common import (  # noqa: F401
    _now, _safe_json, _append_log, _parse_cert_expiry, _get_assets,
    _resolve_node_conn, _node_to_dict, _plan_to_dict, _k8s_ai_provider,
    _k8s_ai_call, _set_pending_decision, _current_plan_id,
    _register_channel, _unregister_channel, _interrupt_plan_channels,
    _await_k8s_decision, _DeployStopped,
    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,
    _ACTIVE_CHANNELS_LOCK,
)
from app.services.k8s_offline_runtime import (  # noqa: F401
    _run_remote, _iter_remote, _sftp_put, _exec_ssh_db,
    _use_stop_guard, _check_stop_remote, _spawn_stop_guard,
)

# ─── 原 L895-910 ───
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


# ─── 原 L913-926 ───
def _remote_arch(client) -> str:
    """探测目标机 CPU 架构，返回 amd64 或 arm64（K8s 官方二进制/静态包的接口命名）。"""
    r = _run_remote(client, 'uname -m', timeout=30)
    m = (r["stdout"] or "").strip().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    return "amd64"


# cilium 专用：用官方 cilium-cli(内置 helm chart) 安装，而非 apply 单个 yaml
_CILIUM_CLI_VERSION = "v0.16.19"
_CILIUM_AGENT_VERSION = "v1.16.5"


# ─── 原 L1068-1097 ───
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


# ─── 原 L1100-1198 ───
def _configure_containerd_net(client, label, p, db, yield_event=None) -> None:
    """配置 containerd 联网能力：
    1) 若 plan 有 http_proxy, 把代理写入 containerd systemd override(拉 registry.k8s.io 等外网镜像需要);
    2) 为 docker.io 配置 registry mirror(走代理拉 docker 大镜像易 EOF, mirror 更稳)。
    """
    import base64 as _b64
    http_p = (p.http_proxy or "").strip()
    # 1) 代理 override
    if http_p:
        no_proxy = (p.no_proxy or "127.0.0.1,localhost,.local")
        # 自动追加集群内网网段到 NO_PROXY：calico 等 CNI 需要在 Pod-sandbox 时访问
        # 内网 API(kube service/pod/节点网段)，若被 HTTP 代理劫持会 EOF 导致 Pod 无法创建。
        # 追加 plan 的 service/pod CIDR 与常见私有段。
        extra = [x for x in [
            (p.service_cidr or "").strip(),
            (p.pod_cidr or "").strip(),
            "10.96.0.0/12", "10.244.0.0/16", "10.0.0.0/8",
            "172.16.0.0/12", "192.168.0.0/16",
        ] if x and x not in no_proxy]
        no_proxy_full = ",".join([no_proxy] + extra)
        override = (
            f"[Service]\n"
            f"Environment=\"HTTP_PROXY={http_p}\"\n"
            f"Environment=\"HTTPS_PROXY={http_p}\"\n"
            f"Environment=\"NO_PROXY={no_proxy_full}\"\n"
        )
        b64 = _b64.b64encode(override.encode()).decode()
        _run_remote(client,
                    f"mkdir -p /etc/systemd/system/containerd.service.d; "
                    f"echo {b64} | base64 -d > /etc/systemd/system/containerd.service.d/http-proxy.conf; "
                    f"systemctl daemon-reload; ", timeout=60)
    # 2) docker.io mirror
    hosts = (
        'server = "https://registry-1.docker.io"\n\n'
        '[host."https://docker.m.daocloud.io"]\n  capabilities = ["pull", "resolve"]\n\n'
        '[host."https://dockerproxy.net"]\n  capabilities = ["pull", "resolve"]\n'
    )
    hb64 = _b64.b64encode(hosts.encode()).decode()
    _run_remote(client,
                f"mkdir -p /etc/containerd/certs.d/docker.io; "
                f"echo {hb64} | base64 -d > /etc/containerd/certs.d/docker.io/hosts.toml; "
                f"systemctl restart containerd >/dev/null 2>&1; sleep 3; ", timeout=120)
    _append_log(p, {"type": "info", "node": label,
                    "message": "containerd 联网配置已应用(代理" + ("有" if http_p else "无") + ", docker.io mirror 已配)"}, db)
    if yield_event: yield_event({"type": "log", "node": label,
                                 "message": "containerd 代理/mirror 已配置"})


# ─────────────────────────────── Docker 运行时(CRI) ───────────────────────────────
# k8s>=1.24 dockershim 已移除，用 Docker 作为 CRI 必须额外装 cri-dockerd(shim)，
# kubeadm/kubelet 通过 unix:///var/run/cri-dockerd.sock 与 Docker 通信。
_CRI_DOCKERD_VERSION = "0.3.16"          # 兼容 k8s 1.28~1.31
_DOCKER_CE_REPO_VER = "9"                # Rocky/RHEL 9 系列
_CRI_DOCKERD_SERVICE_TEMPLATE = (
    "if [ ! -f /etc/systemd/system/cri-docker.service ]; then "
    "cat > /etc/systemd/system/cri-docker.service <<'SVC'\n"
    "[Unit]\n"
    "Description=CRI Interface for Docker Application Container Engine\n"
    "Documentation=https://docs.mirantis.com\n"
    "After=network-online.target firewalld.service docker.service\n"
    "Wants=network-online.target\n"
    "Requires=cri-docker.socket\n"
    "\n"
    "[Service]\n"
    "Type=notify\n"
    "ExecStart=/usr/local/bin/cri-dockerd --container-runtime-endpoint fd://\n"
    "ExecReload=/bin/kill -s HUP $MAINPID\n"
    "TimeoutSec=0\n"
    "RestartSec=2\n"
    "Restart=always\n"
    "StartLimitBurst=3\n"
    "StartLimitInterval=60s\n"
    "LimitNOFILE=infinity\n"
    "LimitNPROC=infinity\n"
    "LimitCORE=infinity\n"
    "TasksMax=infinity\n"
    "Delegate=yes\n"
    "KillMode=process\n"
    "\n"
    "[Install]\n"
    "WantedBy=multi-user.target\n"
    "SVC\n"
    "cat > /etc/systemd/system/cri-docker.socket <<'SVC2'\n"
    "[Unit]\n"
    "Description=CRI Docker Socket for the API\n"
    "PartOf=cri-docker.service\n"
    "\n"
    "[Socket]\n"
    "ListenStream=/var/run/cri-dockerd.sock\n"
    "SocketMode=0660\n"
    "SocketUser=root\n"
    "SocketGroup=docker\n"
    "\n"
    "[Install]\n"
    "WantedBy=sockets.target\n"
    "SVC2\n"
    "systemctl daemon-reload; "
    "fi; echo cri_unit_ok"
)


# ─── 原 L1201-1217 ───
def _docker_daemon_json(p: K8sClusterPlan, ctx: dict = None) -> str:
    """生成 Docker daemon.json 内容：cgroupdriver=systemd + 私有 registry insecure。"""
    conf = {
        "exec-opts": ["native.cgroupdriver=systemd"],
        "log-driver": "json-file",
        "log-opts": {"max-size": "100m", "max-file": "3"},
        "iptables": True,
        "ip6tables": False,
        "storage-driver": "overlay2",
    }
    routers = []
    if ctx and ctx.get("registry_url"):
        host = ctx["registry_url"].split("/")[0]
        routers.append(host)
    if routers:
        conf["insecure-registries"] = routers
    return json.dumps(conf, ensure_ascii=False)


# ─── 原 L1220-1320 ───
def _install_docker(client, ctx, label, p, db, yield_event=None) -> bool:
    """安装 Docker CE + cri-dockerd(CRI shim)。Rocky/RHEL 系。
    Docker CE 走官方 repo(注入代理)；cri-dockerd 走 GitHub 静态二进制。
    配置 daemon.json(cgroupdriver=systemd + insecure-registries)，启用 docker + cri-dockerd。
    返回 docker 与 cri-dockerd 是否就绪。"""
    proxy = _proxy_env_script(p)
    arch = _remote_arch(client)

    def _docker_ready() -> bool:
        r = _run_remote(client,
                        "docker info >/dev/null 2>&1 && echo DV=$(docker version --format '{{.Server.Version}}') || echo NO_DOCKER; "
                        "test -S /var/run/cri-dockerd.sock && echo CRI_SOCK_OK || echo NO_CRI_SOCK",
                        timeout=60)
        out = r["stdout"] or ""
        return "NO_DOCKER" not in out and "NO_CRI_SOCK" not in out

    # 1) 已就绪：直接刷新 daemon.json 并重启 docker
    if _docker_ready():
        _append_log(p, {"type": "info", "node": label, "message": "docker + cri-dockerd 已存在，刷新配置"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "docker + cri-dockerd 已存在，刷新配置"})
        _configure_docker(client, ctx, label, p, db, yield_event=yield_event)
        return _docker_ready()

    # 2) 安装 Docker CE（Rocky/RHEL: 配置官方 repo）
    if yield_event: yield_event({"type": "log", "node": label, "message": "安装 Docker CE (含 containerd.io)...(可能需要几分钟)"})
    _append_log(p, {"type": "info", "node": label, "message": "安装 Docker CE(官方 repo, 走代理)..."}, db)
    install_docker = (
        proxy +
        # 配置 docker-ce repo（Rocky 9 用 centos/9 仓库）
        "if [ ! -f /etc/yum.repos.d/docker-ce.repo ]; then "
        "cat > /etc/yum.repos.d/docker-ce.repo <<'REPO'\n"
        f"[docker-ce-stable]\nname=Docker CE Stable - $basearch\n"
        "baseurl=https://download.docker.com/linux/centos/" + _DOCKER_CE_REPO_VER + "/$basearch/stable\n"
        "enabled=1\ngpgcheck=1\n"
        "gpgkey=https://download.docker.com/linux/centos/gpg\n"
        "REPO\n"
        "fi; "
        # 用 dnf 安装（--allowerasing 解决冲突）
        "(dnf install -y --allowerasing docker-ce docker-ce-cli containerd.io docker-compose-plugin "
        ">/tmp/dk-inst.log 2>&1 && echo DOCKER_INSTALL_OK) || echo DOCKER_INSTALL_FAIL; "
        "tail -3 /tmp/dk-inst.log | sed 's/^/  /'"
    )
    r = _run_remote(client, install_docker, timeout=1200)
    if "DOCKER_INSTALL_OK" not in (r["stdout"] or ""):
        # 兜底: 无代理直连 download.docker.com(可能内网可达) 或试 yum
        r2 = _run_remote(client,
                         "dnf install -y --allowerasing docker-ce docker-ce-cli containerd.io docker-compose-plugin >/tmp/dk2.log 2>&1 && echo DOCKER_INSTALL_OK || echo DOCKER_INSTALL_FAIL; tail -3 /tmp/dk2.log | sed 's/^/  /'",
                         timeout=1200)
        if "DOCKER_INSTALL_OK" not in (r2["stdout"] or ""):
            _append_log(p, {"type": "error", "node": label,
                            "message": "docker-ce 安装失败: " + ((r["stdout"] or "") + (r2["stdout"] or ""))[-300:]}, db)
            if yield_event: yield_event({"type": "log", "node": label, "message": "docker-ce 安装失败"})
            return False

    # 3) 安装 cri-dockerd 静态二进制
    if not _run_remote(client, "test -x /usr/local/bin/cri-dockerd && echo HAVE || echo MISSING", timeout=30)["stdout"].count("HAVE"):
        if yield_event: yield_event({"type": "log", "node": label, "message": f"下载 cri-dockerd v{_CRI_DOCKERD_VERSION}..."})
        _append_log(p, {"type": "info", "node": label, "message": f"下载 cri-dockerd v{_CRI_DOCKERD_VERSION}..."}, db)
        cri_url = (f"https://github.com/Mirantis/cri-dockerd/releases/download/v{_CRI_DOCKERD_VERSION}/"
                   f"cri-dockerd-{_CRI_DOCKERD_VERSION}.{arch}.tgz")
        cri_rc = _run_remote(client,
                             proxy +
                             f"CD=/tmp/cri-dockerd.tgz; rm -f $CD; "
                             f"curl -fsSL -A 'curl/8.4' '{cri_url}' -o $CD && "
                             f"mkdir -p /tmp/cri-x && tar -C /tmp/cri-x -xzf $CD && "
                             f"cp /tmp/cri-x/cri-dockerd/cri-dockerd /usr/local/bin/cri-dockerd && chmod +x /usr/local/bin/cri-dockerd && "
                             f"rm -rf $CD /tmp/cri-x; "
                             f"test -x /usr/local/bin/cri-dockerd && echo CRI_DOWNLOAD_OK || echo CRI_DOWNLOAD_FAIL",
                             timeout=600)
        if "CRI_DOWNLOAD_OK" not in (cri_rc["stdout"] or ""):
            # 兜底: 下载后用 tar 解压(兼容不同打包布局)
            cri_rc = _run_remote(client,
                                 proxy +
                                 f"curl -fsSL -A 'curl/8.4' 'https://github.com/Mirantis/cri-dockerd/releases/download/v{_CRI_DOCKERD_VERSION}/cri-dockerd-{_CRI_DOCKERD_VERSION}.{arch}.tgz' -o /tmp/cri-dockerd.tgz 2>/dev/null; "
                                 "rm -rf /tmp/cri-x && mkdir -p /tmp/cri-x && tar -C /tmp/cri-x -xzf /tmp/cri-dockerd.tgz 2>/dev/null; "
                                 "BIN=$(find /tmp/cri-x -type f -name cri-dockerd | head -1); "
                                 "if [ -n \"$BIN\" ]; then cp \"$BIN\" /usr/local/bin/cri-dockerd && chmod +x /usr/local/bin/cri-dockerd; fi; "
                                 "test -x /usr/local/bin/cri-dockerd && echo CRI_DOWNLOAD_OK || echo CRI_DOWNLOAD_FAIL",
                                 timeout=600)
        if "CRI_DOWNLOAD_OK" not in (cri_rc["stdout"] or ""):
            _append_log(p, {"type": "error", "node": label,
                            "message": "cri-dockerd 下载失败: " + (cri_rc["stdout"] or cri_rc["stderr"] or "")[-300:]}, db)
            if yield_event: yield_event({"type": "log", "node": label, "message": "cri-dockerd 下载失败"})
            return False

    # 4) 创建 cri-dockerd systemd unit + socket，并启用
    _run_remote(client, _CRI_DOCKERD_SERVICE_TEMPLATE + (
        "systemctl daemon-reload; systemctl enable cri-docker.socket cri-docker.service >/dev/null 2>&1; echo cri_unit_ok"),
        timeout=120)

    # 5) 配置 daemon.json 并启动 docker + cri-dockerd
    _configure_docker(client, ctx, label, p, db, yield_event=yield_event)
    ready = _docker_ready()
    if ready:
        ver = _run_remote(client, "docker version --format '{{.Server.Version}}'", timeout=30)["stdout"].strip()
        msg = f"Docker 运行时就绪: v{ver} + cri-dockerd v{_CRI_DOCKERD_VERSION}"
        _append_log(p, {"type": "info", "node": label, "message": msg}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": msg})
    else:
        _append_log(p, {"type": "error", "node": label, "message": "docker/cri-dockerd 未完全就绪"}, db)
    return ready


# ─── 原 L1323-1369 ───
def _configure_docker(client, ctx, label, p, db, yield_event=None) -> None:
    """配置 Docker：写 daemon.json(cgroupdriver=systemd + insecure-registries) +
    配置 Docker daemon 代理(与 containerd 同款, 拉 registry.k8s.io/docker.io 镜像需要) +
    启动 cri-dockerd。"""
    import base64 as _b64
    dj = _docker_daemon_json(p, ctx)
    db64 = _b64.b64encode(dj.encode()).decode()
    # Docker daemon 拉镜像走 HTTP 代理(134 等离线节点无直连, 必须配 proxy, 与 containerd 的 _configure_containerd_net 对齐)。
    # NO_PROXY 需含集群内网网段, 避免 docker 拉内网私有镜像/连内网被代理劫持。
    http_p = (p.http_proxy or "").strip()
    https_p = (p.https_proxy or http_p or "").strip()
    no_proxy = (p.no_proxy or "127.0.0.1,localhost,.local").strip()
    extra = [x for x in [
        (p.service_cidr or "").strip(),
        (p.pod_cidr or "").strip(),
        "10.96.0.0/12", "10.244.0.0/16", "10.0.0.0/8",
        "172.16.0.0/12", "192.168.0.0/16",
    ] if x and x not in no_proxy]
    no_proxy_full = ",".join([no_proxy] + extra)
    proxy_override = ""
    if http_p:
        proxy_override = (
            "mkdir -p /etc/systemd/system/docker.service.d; "
            "cat > /etc/systemd/system/docker.service.d/http-proxy.conf <<'DV'\n"
            "[Service]\n"
            f"Environment=\"HTTP_PROXY={http_p}\"\n"
            f"Environment=\"HTTPS_PROXY={https_p}\"\n"
            f"Environment=\"NO_PROXY={no_proxy_full}\"\n"
            "DV\n"
        )
    _run_remote(client,
                "mkdir -p /etc/docker; "
                f"{proxy_override}"
                f"echo {db64} | base64 -d > /etc/docker/daemon.json; "
                "systemctl daemon-reload; "
                "systemctl enable docker >/dev/null 2>&1; "
                "systemctl restart docker >/dev/null 2>&1; sleep 5; "
                "systemctl enable cri-docker.socket cri-docker.service >/dev/null 2>&1; "
                "systemctl restart cri-docker >/dev/null 2>&1; sleep 4; "
                "docker info >/dev/null 2>&1 && echo DOCKER_ACTIVE || echo DOCKER_INACTIVE; "
                "test -S /var/run/cri-dockerd.sock && echo CRI_SOCK_OK || echo NO_CRI_SOCK",
                timeout=180)
    ru = (ctx or {}).get("registry_url", "")
    msg = "docker daemon 已配置(cgroupdriver=systemd" + (f", insecure-registry={ru.split('/')[0]}" if ru else "") + \
          (", 代理已配" if http_p else ", 无代理") + ")"
    _append_log(p, {"type": "info", "node": label, "message": msg}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": msg})


# ─── 原 L1372-1420 ───
def _install_containerd(client, ctx, label, p, db, yield_event=None) -> None:
    """安装 containerd：优先离线包 binaries/，否则走包源。已安装时也强制刷新配置(sandbox)。"""
    script = "which containerd && containerd --version 2>/dev/null || echo MISSING"
    r = _run_remote(client, script, timeout=60)
    if r["ok"] and "MISSING" not in r["stdout"]:
        # 已安装：不重新安装二进制，但仍需确保配置文件包含匹配的 sandbox_image，
        # 并确保 containerd 服务启动(systemd unit ExecStart 与真实二进制路径一致)
        _run_remote(client, _containerd_config_script(p, ctx), timeout=180)
        _start_containerd_service(client, label, p, db, yield_event=yield_event)
        _configure_containerd_net(client, label, p, db, yield_event=yield_event)
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
    # 兜底安装链（均注入代理）：静态二进制(主) → 包源(RHEL 启 EPEL / Debian apt)
    if not installed:
        _install_containerd_online(client, label, p, db, yield_event=yield_event)
    installed = _run_remote(client, "which containerd >/dev/null 2>&1 && containerd --version 2>/dev/null || echo FAIL", timeout=60)
    if not installed or "FAIL" in installed["stdout"]:
        _append_log(p, {"type": "error", "node": label, "message": "containerd 安装/启动失败（离线包/静态二进制/包源均未成功）"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "containerd 安装/启动失败"})
        return
    # 生成 containerd 配置（SystemdCgroup + sandbox_image + certs.d）
    _run_remote(client, _containerd_config_script(p, ctx), timeout=180)
    # 配置 containerd 联网(代理 + docker.io mirror), 确保能拉 registry.k8s.io / docker.io 镜像
    _configure_containerd_net(client, label, p, db, yield_event=yield_event)
    r = _run_remote(client, "containerd --version 2>/dev/null || echo FAIL", timeout=60)
    if "FAIL" in r["stdout"]:
        _append_log(p, {"type": "error", "node": label, "message": "containerd 安装/启动失败"}, db)
    else:
        msg = "containerd 就绪: " + r["stdout"].strip()[:80]
        _append_log(p, {"type": "info", "node": label, "message": msg}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": msg})


# ─── 原 L1423-1429 ───
def _containerd_version_for(k8s_version: str) -> str:
    """根据 K8s 版本挑选配套的 containerd 版本；无法映射时回退默认。"""
    short = (k8s_version or "").strip().lstrip("v")
    # 取主.次（如 v1.31.6 -> 1.31）
    parts = short.split(".")
    key = ".".join(parts[:2]) if len(parts) >= 2 else short
    return _CONTAINERD_VERSION_MAP.get(key, _CONTAINERD_DEFAULT_VERSION)


# ─── 原 L1432-1502 ───
def _install_containerd_online(client, label, p, db, yield_event=None) -> None:
    """在线兜底安装 containerd：优先 GitHub 静态二进制(不依赖包源，最稳)，
    失败再退化 EPEL(RHEL 系) / apt(Debian 系) 包源。全程注入 plan 代理。"""
    proxy = _proxy_env_script(p)
    cv = _containerd_version_for(p.kubernetes_version)
    arch = _remote_arch(client)
    tar_url = f"https://github.com/containerd/containerd/releases/download/v{cv}/containerd-{cv}-linux-{arch}.tar.gz"
    runc_url = f"https://github.com/opencontainers/runc/releases/download/v1.1.14/runc.{arch}"

    if yield_event: yield_event({"type": "log", "node": label, "message": f"containerd 不在系统，尝试在线安装 (v{cv})..."})
    _append_log(p, {"type": "info", "node": label,
                    "message": f"containerd 缺失，尝试在线安装 (v{cv})：静态二进制优先，包源兜底"}, db)

    # 1) 静态二进制：下载含 containerd/ctr/shim 的 tar，以及独立 runc。
    #    先确保 tar 命令存在(干净 Rocky/RHEL 可能缺 tar)，否则无法解压。
    ensure_tar = (
        proxy +
        "if ! command -v tar >/dev/null 2>&1; then "
        "if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then "
        "$(command -v dnf >/dev/null 2>&1 && echo dnf || echo yum) install -y tar >/dev/null 2>&1; "
        "elif command -v apt-get >/dev/null 2>&1; then apt-get install -y tar >/dev/null 2>&1; fi; "
        "fi; command -v tar >/dev/null 2>&1 && echo TAR_OK || echo TAR_MISSING"
    )
    _run_remote(client, ensure_tar, timeout=300)
    dl = (
        proxy +
        f"set -e; T=/tmp/cr-{cv}.tar.gz; "
        f"curl -fsSL -A 'curl/8.4' '{tar_url}' -o $T && "
        f"tar -C /usr/local/bin -xzf $T --strip-components=1 bin/ && "
        f"curl -fsSL -A 'curl/8.4' '{runc_url}' -o /usr/local/bin/runc && chmod +x /usr/local/bin/runc && "
        f"rm -f $T; "
        f"which containerd && echo STATIC_OK || echo STATIC_FAIL"
    )
    r = _run_remote(client, dl, timeout=900)
    if "STATIC_OK" in r["stdout"]:
        _append_log(p, {"type": "info", "node": label, "message": f"containerd 静态二进制下载成功 (v{cv})"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "containerd 静态二进制下载成功"})
        # 创建 systemd unit（静态二进制不会自动生成），并启动服务
        _run_remote(client, _ensure_containerd_unit(), timeout=60)
        _start_containerd_service(client, label, p, db, yield_event=yield_event)
        return

    msgtail = (r["stdout"] + r["stderr"]).strip()[-200:]
    _append_log(p, {"type": "warn", "node": label, "message": f"静态二进制下载失败: {msgtail}"}, db)
    if yield_event: yield_event({"type": "log", "node": label, "message": "静态二进制下载失败，尝试包源..."})

    # 2) 包源兜底：RHEL 系先启 EPEL 再装 containerd；Debian 系直接 apt
    script = (
        proxy +
        # Debian/Ubuntu
        "if command -v apt-get >/dev/null 2>&1; then "
        "apt-get update >/dev/null 2>&1; apt-get install -y containerd >/dev/null 2>&1; "
        # RHEL/CentOS/Rocky：装 EPEL(按需) 后 dnf 安装 containerd(epel 提供该包)
        "elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then "
        "PkgMgr=$(command -v dnf >/dev/null 2>&1 && echo dnf || echo yum); "
        "if [ ! -f /etc/yum.repos.d/epel.repo ]; then "
        "curl -fsSL -o /tmp/epel-rel.rpm 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm' 2>/dev/null; "
        "$PkgMgr install -y /tmp/epel-rel.rpm >/dev/null 2>&1 || dnf install -y epel-release >/dev/null 2>&1 || yum install -y epel-release >/dev/null 2>&1; "
        "fi; "
        "$PkgMgr install -y containerd >/dev/null 2>&1; "
        "fi; "
        "which containerd >/dev/null 2>&1 && echo PKG_OK || echo PKG_FAIL"
    )
    r2 = _run_remote(client, script, timeout=900)
    if "PKG_OK" in r2["stdout"]:
        _append_log(p, {"type": "info", "node": label, "message": "containerd 包源安装成功"}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": "containerd 包源安装成功"})
        _run_remote(client, _ensure_containerd_unit(), timeout=60)
        _start_containerd_service(client, label, p, db, yield_event=yield_event)
    else:
        _append_log(p, {"type": "warn", "node": label, "message": "containerd 包源安装失败: " + (r2["stdout"] + r2["stderr"]).strip()[-200:]}, db)


# ─── 原 L1505-1547 ───
def _start_containerd_service(client, label, p, db, yield_event=None) -> bool:
    """确保 containerd systemd 服务启用并运行。
    先确保 runc(containerd 运行 OCI 容器的必要条件)存在——EPEL 装 containerd 常缺 runc，
    否则 etcd/apiserver 等控制面容器会报 exec: runc not found。
    通过 override 用真实二进制路径(/usr/bin 或 /usr/local/bin)校正 ExecStart,
    兼容 rpm 与静态二进制两种安装。返回 bool 是否 socket 就绪。"""
    proxy = _proxy_env_script(p)
    # 1) 确保 runc: 优先包管理器, 缺失则静态下载到 /usr/local/bin/runc
    _run_remote(client,
                proxy +
                "if ! command -v runc >/dev/null 2>&1 && [ ! -x /usr/local/bin/runc ]; then "
                "(dnf install -y runc >/dev/null 2>&1 || "
                "yum install -y runc >/dev/null 2>&1 || "
                "apt-get install -y runc >/dev/null 2>&1) ; "
                "if ! command -v runc >/dev/null 2>&1; then "
                "curl -fsSL -A 'curl/8.4' -o /usr/local/bin/runc "
                "'https://github.com/opencontainers/runc/releases/download/v1.1.14/runc.amd64' && chmod +x /usr/local/bin/runc; "
                "fi; fi; "
                "command -v runc >/dev/null 2>&1 || [ -x /usr/local/bin/runc ] && echo RUNC_OK || echo RUNC_MISSING",
                timeout=300)
    script = (
        "BIN=$(command -v containerd); "
        "if [ -z \"$BIN\" ]; then echo NO_BIN; exit 1; fi; "
        "mkdir -p /etc/systemd/system/containerd.service.d; "
        "printf '[Service]\\nExecStart=\\nExecStart=%s\\n' \"$BIN\" > /etc/systemd/system/containerd.service.d/override.conf; "
        "systemctl daemon-reload; "
        "systemctl enable containerd >/dev/null 2>&1; "
        "systemctl restart containerd >/dev/null 2>&1; sleep 3; "
        "systemctl is-active containerd; "
        "ls /run/containerd/containerd.sock >/dev/null 2>&1 && echo SOCK_OK || echo NO_SOCK"
    )
    r = _run_remote(client, script, timeout=120)
    out = r["stdout"].strip()
    active = "active" in out
    sock_ok = "SOCK_OK" in out
    if active and sock_ok:
        msg = "containerd 服务已启用并运行"
        _append_log(p, {"type": "info", "node": label, "message": msg}, db)
        if yield_event: yield_event({"type": "log", "node": label, "message": msg})
        return True
    _append_log(p, {"type": "warn", "node": label,
                    "message": f"containerd 服务未就绪(active={'active' if active else '否'}, sock={'OK' if sock_ok else '缺失'}): {out[-200:]}"}, db)
    return False


# ─── 原 L1550-1581 ───
def _ensure_containerd_unit() -> str:
    """静态/包源安装后确保 containerd systemd unit 存在（离线二进制默认无 unit）。"""
    return (
        "if [ ! -f /etc/systemd/system/containerd.service ]; then "
        "cat > /etc/systemd/system/containerd.service <<'SVC'\n"
        "[Unit]\n"
        "Description=containerd container runtime\n"
        "Documentation=https://containerd.io\n"
        "After=network.target local-fs.target\n"
        "\n"
        "[Service]\n"
        "ExecStartPre=-/sbin/modprobe overlay\n"
        "ExecStart=/usr/local/bin/containerd\n"
        "KillMode=process\n"
        "Delegate=yes\n"
        "LimitNOFILE=1048576\n"
        "TasksMax=infinity\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
        "SVC\n"
        "systemctl daemon-reload; "
        "fi; "
        "mkdir -p /etc/containerd; echo ok"
    )


# ─────────────────────────────── AI 预检(阶段0) ───────────────────────────────
# 在真正部署前 SSH 采集节点系统信息, 由 AI 生成部署方案(含 containerd 安装方式/包源/依赖),
# 避免在 Rocky 等系统上因写死的包源假设而盲栽跟头。预检失败不阻断, 仅降级为规则兜底。


