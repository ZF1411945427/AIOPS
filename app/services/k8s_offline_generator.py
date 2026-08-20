"""子模块: k8s_offline 七阶段部署编排 + 报告/落库/AI预检(拆分生成)"""

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
    _await_k8s_decision, _DeployStopped, _EXEC_LOCK, _STOPPED,
    K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS, _ACTIVE_CHANNELS_LOCK,
)
from app.services.k8s_offline_runtime import (  # noqa: F401
    _run_remote, _iter_remote, _sftp_put, _exec_ssh_db, _inject_etc_hosts,
    _disable_swap, _setup_kernel, _set_hostname, _ensure_dns,
    _grant_admin_clusteradmin, _ensure_core_addons, _fix_cni_kubeconfig_localhost,
    _ensure_cni_plugins, _install_cilium, _install_preflight_deps,
    _probe_node_environment, _install_k8s_binaries, _generate_kubeadm_config,
    _write_imagetar_jobs, _configure_insecure_registry, _apply_cert_expiry,
    _extract_yaml_images, _check_cni_pods,
)
from app.services.k8s_offline_docker import (  # noqa: F401
    _proxy_env_script, _remote_arch, _containerd_config_script,
    _configure_containerd_net, _docker_daemon_json, _install_docker,
    _configure_docker, _install_containerd, _containerd_version_for,
    _install_containerd_online, _start_containerd_service,
    _ensure_containerd_unit,
)

# ─── 原 L2165-2770 ───
def _run_deploy_generator(db, p: K8sClusterPlan, plan_id: int, resume_step: int = 0, decision_queue=None):
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
    yield {"type": "log", "message": f"控制面镜像仓库: {ctx.get('image_repository') or '(未配置)'}"}

    clients: Dict[int, Any] = {}  # node.id -> ssh client
    labels: Dict[int, str] = {}
    try:
        # ── 阶段0 预检 ──
        p.current_step = 0
        yield {"type": "phase", "step": 0, "title": "阶段0/6 预检"}
        pending_yields = []
        def _emit(evt): pending_yields.append(evt)
        nodes_env = []
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            label = f"{n.host_role}:{n.ip}"
            labels[n.id] = label
            n.status = "running"
            db.commit()
            try:
                client, conn = _exec_ssh_db(db, p, n, label, yield_event=_emit)
                for evt in pending_yields:
                    yield evt
                pending_yields.clear()
                clients[n.id] = client
                r = _run_remote(client, "id -u; uname -r; which swapoff", timeout=60)
                msg = "SSH 连通，root=" + (r["stdout"].splitlines()[0] if r["stdout"] else "?")
                _append_log(p, {"type": "ok", "node": label, "message": msg}, db)
                yield {"type": "log", "node": label, "message": msg}
                # AI 预检: 采集节点系统/包源/运行时/依赖信息
                env = _probe_node_environment(client, p)
                env["node"] = label
                nodes_env.append(env)
                yield {"type": "log", "node": label,
                       "message": f"预检: {env.get('os_id')} {env.get('os_version')} | 包源: {env.get('pkg_mgr') or 'unknown'} | containerd: {'有' if env.get('has_containerd') else '无'} | docker: {'有' if env.get('has_docker') else '无'}{(' v' + env.get('docker_version')) if env.get('docker_version') else ''} | tar: {'有' if env.get('has_tar') else '缺失'} | 内存: {env.get('mem_mb')}MB | 磁盘: {env.get('disk_avail_mb')}MB"}
                n.status = "succeeded"
            except Exception as e:
                n.status = "failed"
                _append_log(p, {"type": "error", "node": label, "message": f"SSH 连接失败: {e}"}, db)
                yield {"type": "log", "node": label, "message": f"SSH 连接失败: {e}"}
        db.commit()
        if any(n.status == "failed" for n in nodes_db):
            raise RuntimeError("存在无法连接的节点，中止部署")

        # AI 预检: 生成部署方案(含 containerd 安装方式/风险项), 不阻断仅提示
        if nodes_env:
            preflight = _k8s_preflight_ai(db, p, nodes_env)
            _append_log(p, {"type": "ai",
                            "message": f"AI 预检: containerd安装={preflight.get('containerd_install')} 策略={preflight.get('strategy')}"
                                       f"{(' 风险: ' + '; '.join(preflight.get('risks', []))) if preflight.get('risks') else ''}"}, db)
            yield {"type": "preflight", "plan": p.id, "strategy": preflight.get("strategy"),
                   "containerd_install": preflight.get("containerd_install"),
                   "risks": preflight.get("risks", []),
                   "preflight_notes": preflight.get("preflight_notes", []),
                   "recommendation": preflight.get("recommendation")}

        # ── 阶段1 环境准备(所有节点，可并行) ──
        pending_yields = []
        p.current_step = 1
        yield {"type": "phase", "step": 1, "title": "阶段1/6 环境准备(swap/内核/hosts)"}
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            label = labels[n.id]
            client = clients[n.id]
            hn = _set_hostname(client, {"hostname": n.hostname,
                                        "ip": _resolve_node_conn(db, n)["ip"],
                                        "host_role": n.host_role or "node"}, label, p, db)
            _disable_swap(client, label, p, db)
            _setup_kernel(client, label, p, db)
            _ensure_dns(client, label, p, db, yield_event=_emit)
            _install_preflight_deps(client, label, p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
        # /etc/hosts 全部集群节点映射(与 set-hostname 同源生成合法主机名, 保证本机可解析)
        all_nodes = [{"ip": _resolve_node_conn(db, x)["ip"], "hostname": x.hostname,
                      "host_role": x.host_role} for x in nodes_db]
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
            yield {"type": "log", "node": label, "message": f"配置节点 {label} (运行时 {p.runtime})..."}
            if p.runtime == "docker":
                _runtime_name, _cri_bin = "docker+cri-dockerd", "cri-dockerd"
                _install_ok = _install_docker(client, ctx, label, p, db, yield_event=_emit)
                _probe_cmd = "which docker >/dev/null 2>&1 && docker version --format 'v{{.Server.Version}}' 2>/dev/null && test -S /var/run/cri-dockerd.sock && echo CRI_OK || echo FAIL"
            else:
                _runtime_name, _cri_bin = "containerd", "containerd"
                _install_containerd(client, ctx, label, p, db, yield_event=_emit)
                _probe_cmd = "which containerd >/dev/null 2>&1 && containerd --version 2>/dev/null || echo FAIL"
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
            # AI 盯梢: 运行时仍未就绪时, 诊断并向前端提交方案选择
            _cr = _run_remote(client, _probe_cmd, timeout=60)
            if not _cr["ok"] or "FAIL" in _cr["stdout"]:
                _diag = _k8s_failure_diagnosis(db, _cri_bin, f"安装 {_runtime_name} 容器运行时", _cr["stdout"], {"os": "probe"})
                _opts = _k8s_decision_options(_diag)
                _append_log(p, {"type": "ai",
                                "message": f"AI 诊断[{_cri_bin}]: {_diag.get('root_cause')} → 等待你的选择"}, db)
                _decision_card = {
                    "id": f"plan{plan_id}-node{n.id}-{_cri_bin}",
                    "question": f"节点 {label} 的 {_runtime_name} 安装失败。{_diag.get('root_cause')}",
                    "options": _opts,
                    "root_cause": _diag.get('root_cause', ''),
                }
                _set_pending_decision(p, db, _decision_card)
                yield {"type": "decide", "id": f"plan{plan_id}-node{n.id}-{_cri_bin}",
                       "question": f"节点 {label} 的 {_runtime_name} 安装失败。{_diag.get('root_cause')}",
                       "options": _opts, "free": False}
                _choice = _await_k8s_decision(plan_id, decision_queue, default="stop")
                _set_pending_decision(p, db, None)
                _choice = (_choice or "").lower()
                _append_log(p, {"type": "ai", "node": label,
                                "message": f"你的选择: {_choice}"}, db)
                yield {"type": "log", "node": label, "message": f"AI 决策: {_choice}"}
                if _choice in ("fix", "retry"):
                    # 一次兜底重试
                    if p.runtime == "docker":
                        _install_docker(client, ctx, label, p, db, yield_event=_emit)
                    else:
                        _install_containerd_online(client, label, p, db, yield_event=_emit)
                    for evt in pending_yields:
                        yield evt
                    pending_yields.clear()
                    _cr2 = _run_remote(client, _probe_cmd, timeout=60)
                    if _cr2["ok"] and "FAIL" not in _cr2["stdout"]:
                        _append_log(p, {"type": "info", "node": label, "message": f"{_runtime_name} 重试安装成功"}, db)
                    else:
                        _append_log(p, {"type": "error", "node": label, "message": f"{_runtime_name} 仍无法安装，继续后续可能失败"}, db)
                elif _choice == "stop":
                    raise _DeployStopped()
                elif _choice != "skip":
                    # 非 skip/stop, 视为 retry
                    if p.runtime == "docker":
                        _install_docker(client, ctx, label, p, db, yield_event=_emit)
                    else:
                        _install_containerd_online(client, label, p, db, yield_event=_emit)
                    for evt in pending_yields:
                        yield evt
                    pending_yields.clear()
            # 私有 Registry 信任: docker 走 daemon.json(insecure), containerd 走 hosts.toml
            if ctx.get("registry_url"):
                if p.runtime == "docker":
                    _configure_docker(client, ctx, label, p, db, yield_event=_emit)
                else:
                    _configure_insecure_registry(client, ctx, label, p, db, yield_event=_emit)
                for evt in pending_yields:
                    yield evt
                pending_yields.clear()
            _install_k8s_binaries(client, ctx, label, p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()
            # 确保 CNI 基础插件在 kubelet 启动前就绪(控制面 static pod sandbox 依赖 loopback 等)
            _ensure_cni_plugins(client, label, p, db)
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
            init_lines = []
            init_rc = 0
            for line, is_err in _iter_remote(fclient, init_cmd + " 2>&1; echo __KUBEADM_RC__=$?"):
                if line.startswith("__KUBEADM_RC__="):
                    init_rc = int(line.split("=")[1].strip())
                    break
                if line.strip():
                    init_lines.append(line.rstrip())
                    yield {"type": "output", "node": labels[first_master.id], "line": line.rstrip()}
            if init_rc != 0:
                # AI 盯梢: kubeadm init 失败诊断 + 提交方案
                _kout = "\n".join(init_lines[-40:])
                _diag = _k8s_failure_diagnosis(db, "kubeadm_init", "kubeadm init 初始化控制平面", _kout)
                _opts = _k8s_decision_options(_diag, [
                    {"key": "retry_after_fix", "title": "修复依赖后重试", "desc": "安装/启动 containerd 等运行时后重跑 init"},
                ])
                _append_log(p, {"type": "ai", "node": labels[first_master.id],
                                "message": f"AI 诊断[kubeadm init]: {_diag.get('root_cause')} → 等待你的选择"}, db)
                _decision_card = {
                    "id": f"plan{plan_id}-kubeadm-init",
                    "question": f"kubeadm init 失败(rc={init_rc})。{_diag.get('root_cause')}",
                    "options": _opts,
                    "root_cause": _diag.get('root_cause', ''),
                }
                _set_pending_decision(p, db, _decision_card)
                yield {"type": "decide", "id": f"plan{plan_id}-kubeadm-init",
                       "question": f"kubeadm init 失败(rc={init_rc})。{_diag.get('root_cause')}",
                       "options": _opts, "free": False}
                _choice = _await_k8s_decision(plan_id, decision_queue, default="stop")
                _set_pending_decision(p, db, None)
                _choice = (_choice or "").lower()
                _append_log(p, {"type": "ai", "node": labels[first_master.id], "message": f"你的选择: {_choice}"}, db)
                yield {"type": "log", "node": labels[first_master.id], "message": f"AI 决策: {_choice}"}
                if _choice == "stop":
                    raise _DeployStopped()
                if _choice in ("fix", "retry", "retry_after_fix"):
                    # 重跑一次 init（可能用户已手工修复, 或依赖已就绪）
                    yield {"type": "log", "node": labels[first_master.id], "message": "重试 kubeadm init..."}
                    for line, is_err in _iter_remote(fclient, init_cmd + " 2>&1; echo __KUBEADM_RC__=$?"):
                        if line.startswith("__KUBEADM_RC__="):
                            init_rc = int(line.split("=")[1].strip())
                            break
                        if line.strip():
                            yield {"type": "output", "node": labels[first_master.id], "line": line.rstrip()}
                    if init_rc != 0:
                        raise RuntimeError(f"kubeadm init 重试仍失败(rc={init_rc})")
            _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": "kubeadm init 完成"}, db)

        # k8s>=1.28 kubeadm 把超管权限移到 super-admin.conf, admin.conf 的 kubernetes-admin
        # 默认不再具备 cluster-admin(CNI/验证等 kubectl 操作会 Forbidden)。
        # 幂等补绑: 用 super-admin.conf 把 kubernetes-admin 绑到 cluster-admin, 保证 admin.conf 可用。
        _grant_admin_clusteradmin(fclient, labels[first_master.id], p, db)

        # 配置 kubectl
        _run_remote(fclient,
                    "mkdir -p $HOME/.kube; cp /etc/kubernetes/admin.conf $HOME/.kube/config 2>/dev/null; chown $(id -u):$(id -g) $HOME/.kube/config; echo ok",
                    timeout=60)

        # 证书统一有效期(可选): 配置了 cert_expiry_years 则把 CA+全部服务证书重签为该年限(全一致)
        if p.cert_expiry_years:
            _apply_cert_expiry(fclient, labels[first_master.id], p, db, yield_event=_emit)
            for evt in pending_yields:
                yield evt
            pending_yields.clear()

        # ── 阶段5 CNI ──
        p.current_step = 5
        yield {"type": "phase", "step": 5, "title": "阶段5/6 安装 CNI"}
        if _check_stop(plan_id):
            raise _DeployStopped()
        # 确保所有节点具备 CNI 基础插件(loopback/bridge 等)，否则 Pod sandbox 创建失败
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            _ensure_cni_plugins(clients[n.id], labels[n.id], p, db)
        # 断点续传幂等：CNI daemonset 已存在则跳过
        cni_exist = _run_remote(fclient,
                                "export KUBECONFIG=/etc/kubernetes/admin.conf; kubectl get ds -A 2>/dev/null | grep -iE 'flannel|calico|cilium' | head -1 || true",
                                timeout=60)
        if cni_exist["stdout"].strip():
            _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": f"CNI 已安装({p.cni})，跳过"}, db)
            yield {"type": "log", "node": labels[first_master.id], "message": "CNI 已安装，跳过 apply"}
        else:
            # cilium：用官方 cilium-cli 安装(内置 helm chart)，不走单个 yaml apply
            if p.cni == "cilium":
                _ok = _install_cilium(fclient, labels[first_master.id], p, db, yield_event=_emit)
                for evt in pending_yields:
                    yield evt
                pending_yields.clear()
                if _ok:
                    _append_log(p, {"type": "ok", "node": labels[first_master.id], "message": "CNI 已安装: cilium"}, db)
                    yield {"type": "log", "node": labels[first_master.id], "message": "CNI 已安装: cilium"}
                else:
                    raise RuntimeError("Cilium CNI 安装未就绪")
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
                    r = _run_remote(fclient,
                                    f"unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; "
                                    f"export KUBECONFIG=/etc/kubernetes/admin.conf; "
                                    f"kubectl apply --validate=false -f {remote_yaml} 2>&1; echo __CNI_RC__=$?", timeout=600)
                    cni_rc = _parse_ctl_rc(r["stdout"], "CNI_RC")
                    if cni_rc == 0:
                        _append_log(p, {"type": "ok", "node": labels[first_master.id],
                                        "message": "CNI 已应用(离线清单) rc=0"}, db)
                    else:
                        raise RuntimeError(f"CNI(离线清单) 应用失败 rc={cni_rc}: " + r["stdout"][-300:])
                else:
                    url = _DEFAULT_CNI_FILES.get(p.cni)
                    if url:
                        # 先下载独立文件，下载失败立即报错(不落到旧残留文件)；成功后再 apply。
                        # 下载走代理(curl 需外网), 但 kubectl apply 连内网 API server 必须去掉代理, 否则 TLS 握手超时。
                        # 对 flannel 等，把固定的默认网段替换为 plan.pod_cidr，避免 PodCIDR 与 CNI 网段不一致导致 flannel crash。
                        pod_cidr = (p.pod_cidr or "").strip()
                        # CNI 完全离线化(私有仓库): 把 manifest 里的 CNI 镜像(docker.io/quay.io 前缀)改写为
                        # 私有仓库 <reg>/kubernetes/<cni>/<img>, 让 kubelet 从私有仓库拉 CNI 镜像而非 docker.io mirror。
                        cni_mirror_sed = ""
                        if ctx and ctx.get("registry_url"):
                            _reg_host = ctx["registry_url"].split("/")[0]
                            if p.cni == "flannel":
                                cni_mirror_sed = (f"sed -i 's#docker.io/flannel/#{_reg_host}/kubernetes/flannel/#g' "
                                                  "/root/k8s-cni-download.yaml; ")
                            elif p.cni == "calico":
                                cni_mirror_sed = (f"sed -i 's#docker.io/calico/#{_reg_host}/kubernetes/calico/#g; "
                                                  f"s#quay.io/calico/#{_reg_host}/kubernetes/calico/#g' "
                                                  "/root/k8s-cni-download.yaml; ")
                        r = _run_remote(fclient,
                                        _proxy_env_script(p) +
                                        f"rm -f /root/k8s-cni-download.yaml; "
                                        f"curl -fsSL '{url}' -o /root/k8s-cni-download.yaml 2>&1; echo CURL_RC=$?; "
                                        f"if [ -s /root/k8s-cni-download.yaml ]; then "
                                        + (f"sed -i 's#10.244.0.0/16#{pod_cidr}#g; s#10.244.0.0\\/16#{pod_cidr}#g' /root/k8s-cni-download.yaml; "
                                           if pod_cidr and p.cni == "flannel" else "") +
                                        cni_mirror_sed +
                                        f"unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; "
                                        f"export KUBECONFIG=/etc/kubernetes/admin.conf; "
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
                # CNI 镜像全自动预拉(平台自动化, 非手动): kubectl apply 只创建资源, 镜像由 kubelet 拉取;
                # 离线/代理环境下 kubelet 拉 docker.io 大镜像易失败(ImagePullBackOff), 导致 CNI/coredns 起不来。
                # 这里从已 apply 的 manifest 提取镜像并用代理显式 docker pull 预拉, 保证 pod 能起来。
                if p.runtime == "docker":
                    yaml_path = "/root/k8s-cni-download.yaml"
                    if not _run_remote(fclient, f"test -s {yaml_path} && echo EXISTS || echo MISSING", timeout=30)["stdout"].count("EXISTS"):
                        yaml_path = "/root/k8s-cni.yaml"
                    imgs = _extract_yaml_images(fclient, yaml_path, label, p, db)
                    if imgs:
                        _append_log(p, {"type": "info", "node": labels[first_master.id],
                                        "message": f"CNI 镜像自动预拉({len(imgs)}个): " + ", ".join(imgs)}, db)
                        yield {"type": "log", "node": labels[first_master.id],
                               "message": f"CNI 镜像自动预拉({len(imgs)}个): " + ", ".join(imgs)}
                        for img in imgs:
                            if _check_stop(plan_id):
                                raise _DeployStopped()
                            rp = _run_remote(fclient,
                                             f"docker pull {img} >/tmp/cni_pull.log 2>&1 && echo PULL_OK || echo PULL_FAIL; tail -1 /tmp/cni_pull.log",
                                             timeout=600)
                            if "PULL_OK" in (rp["stdout"] or ""):
                                _append_log(p, {"type": "ok", "node": labels[first_master.id],
                                                "message": f"镜像已预拉: {img}"}, db)
                            else:
                                _append_log(p, {"type": "warn", "node": labels[first_master.id],
                                                "message": f"镜像预拉失败(将由 kubelet 重试): {img} " + (rp["stdout"] or rp["stderr"] or "")[-150:]}, db)
                            for evt in pending_yields:
                                yield evt
                            pending_yields.clear()
        yield {"type": "log", "node": labels[first_master.id], "message": f"CNI 已安装: {p.cni}"}

        # 确保核心 addon(kube-proxy/coredns)存在: 跳过 init/断点续传时它们可能缺失,
        # 而 kube-proxy 缺失会导致 service ClusterIP 不可达, calico 等 CNI init 崩溃。
        _ensure_core_addons(fclient, labels[first_master.id], p, db)
        for evt in pending_yields:
            yield evt
        pending_yields.clear()

        # 根治单节点 CNI↔API server 经 service/node IP 的 TCP/TLS 竞态: 把所有节点
        # 的 calico CNI kubeconfig 改写为 127.0.0.1 回环 + insecure + calico token,
        # 否则非 hostNetwork pod(如 coredns/calico-kube-controllers)sandbox 创建失败。
        for n in nodes_db:
            if _check_stop(plan_id):
                raise _DeployStopped()
            _fix_cni_kubeconfig_localhost(clients[n.id], labels[n.id], p, db)
        for evt in pending_yields:
            yield evt
        pending_yields.clear()

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

        # CNI/核心组件就绪验证：节点 Ready 不代表 CNI/coredns 真正 Running。
        # 必须等待关键 pod Running，否则集群实际不可用(CNI 拉镜像失败/调度问题)却仍标成功。
        cni_names = {
            "calico": ["calico-node", "calico-kube-controllers"],
            "cilium": ["cilium-agent"],
            "flannel": ["kube-flannel"],
        }.get(p.cni, ["coredns"])
        cni_names.append("coredns")
        cni_ok = False
        for _attempt in range(40):
            if _check_stop(plan_id):
                raise _DeployStopped()
            if _check_cni_pods(fclient, p, cni_names):
                cni_ok = True
                break
            time.sleep(6)
        if cni_ok:
            _append_log(p, {"type": "ok", "message": "CNI/核心组件就绪校验通过(calico/coredns Running)"}, db)
            yield {"type": "log", "message": "CNI/核心组件就绪校验通过"}
        else:
            # 不静默判成功：CNI 未就绪视为异常, 报告到日志(不直接失败, 交由前端/AI 判断, 但标注非健康)
            _append_log(p, {"type": "warn",
                            "message": "CNI/核心组件未完全 Running(集群可能不可用), 请检查镜像拉取/网络插件"}, db)
            yield {"type": "log", "message": "警告: CNI/核心组件未完全 Running(集群可能不可用)"}

        # 采集 kubeconfig
        kc = _run_remote(fclient, "cat /etc/kubernetes/admin.conf", timeout=60)
        if kc["ok"] and kc["stdout"].strip():
            p.kubeconfig = kc["stdout"]
            _create_platform_datasource(db, p, first_ip)
            _append_log(p, {"type": "ok", "message": "已采集 kubeconfig 并接入平台监控"}, db)

        # 若勾选"去除主节点污点"，在 master 上移除 NoSchedule 污点，允许 Pod 调度到 master
        if p.untaint_master:
            taint_cmd = (
                "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; "
                "export KUBECONFIG=/etc/kubernetes/admin.conf; "
                "kubectl taint nodes --all node-role.kubernetes.io/control-plane- 2>&1; "
                "kubectl taint nodes --all node-role.kubernetes.io/master- 2>&1; "
                "untainted=$(kubectl get nodes -o jsonpath='{.items[*].spec.taints}' 2>/dev/null); "
                "echo UNTAINT_CHECK=[$untainted]"
            )
            tr = _run_remote(fclient, taint_cmd, timeout=30)
            if "NoSchedule" not in tr["stdout"]:
                _append_log(p, {"type": "ok", "message": "已去除 master 节点污点，允许 Pod 调度到 master"}, db)
                yield {"type": "log", "message": "已去除 master 节点污点"}
            else:
                _append_log(p, {"type": "warn", "message": "去除 master 污点可能未完全生效: " + tr["stdout"][-150:]}, db)
                yield {"type": "log", "message": "去除 master 污点可能未完全生效"}

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
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
        db.commit()
        yield {"type": "error", "status": "failed", "message": str(e)}
        yield {"type": "complete", "status": "failed", "message": str(e)}
    finally:
        for client in clients.values():
            try:
                client.close()
            except Exception as _exc1:
                logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
        _release_exec(plan_id)
        _set_pending_decision(p, db, None)


# ─── 原 L2773-2791 ───
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


# ─── 原 L2794-2807 ───
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


# ─── 原 L2810-2824 ───
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


# ─── 原 L2827-2868 ───
def _create_platform_datasource(db: Session, p: K8sClusterPlan, api_ip: str, ds_name: str = None) -> Optional[DataSource]:
    """部署成功后自动创建 DataSource(type=kubernetes)，集群接入监控。
    ds_name 可选：自定义资产/数据源名，默认用计划名 p.name。"""
    kc = p.kubeconfig or ""
    if not kc:
        return None
    ds_name = (ds_name or "").strip() or p.name
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


# ─────────────────────── 落库追溯: 同步 DeployPlan / DeployStep ───────────────────────
# K8s 部署保留自己的编排, 但把"阶段计划 + 阶段状态"同步落库到通用 deploy_plans/deploy_steps,
# 供追溯/报告/审计与中间件部署对齐, 复用 deploy 的表模型, 不侵入其执行引擎。

_K8S_STAGE_NAMES = [
    ("阶段0 预检（SSH 连通 + AI 预检）", "medium"),
    ("阶段1 环境准备（swap/内核/hosts/依赖）", "medium"),
    ("阶段2 运行时与二进制（containerd/docker + kubeadm/kubelet/kubectl）", "high"),
    ("阶段3 生成 kubeadm 配置", "medium"),
    ("阶段4 初始化控制平面（kubeadm init）", "high"),
    ("阶段5 安装 CNI 网络插件", "medium"),
    ("阶段6 节点加入（join）", "high"),
]


# ─── 原 L2871-2908 ───
def _sync_k8s_deploy_plan(db: Session, p: K8sClusterPlan) -> int:
    """为 K8s 计划创建/复用一条 DeployPlan, 并把 7 个阶段写成 DeployStep 行。
    返回 DeployPlan.id。幂等: 同一 K8s plan 复用同一条 DeployPlan。"""
    from app.models import DeployPlan, DeployStep
    name = f"[K8s] {p.name}"
    dp = db.query(DeployPlan).filter(
        DeployPlan.name == name).order_by(DeployPlan.id.desc()).first()
    if not dp:
        node_assets = [n.asset_id for n in db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == p.id).all()]
        dp = DeployPlan(
            name=name,
            description=f"K8S 集群离线部署 计划#{p.id} (v{p.kubernetes_version}, {p.runtime}, {p.cni})",
            asset_ids=json.dumps(node_assets),
            http_proxy=p.http_proxy or "", https_proxy=p.https_proxy or "",
            no_proxy=p.no_proxy or "", status=p.status or "draft",
            created_by=p.created_by,
        )
        db.add(dp)
        db.flush()
        for idx, (desc, risk) in enumerate(_K8S_STAGE_NAMES):
            db.add(DeployStep(plan_id=dp.id, step_order=idx, description=desc,
                              risk_level=risk, status="pending"))
    else:
        dp.status = p.status or "draft"
        dp.updated_at = _now()
        # 用断点续传映射 K8s current_step -> DeployStep 状态
        _steps = db.query(DeployStep).filter(DeployStep.plan_id == dp.id) \
            .order_by(DeployStep.step_order).all()
        _cur = p.current_step or 0
        for _s in _steps:
            if _s.step_order < _cur:
                _s.status = "succeeded"
            elif _s.step_order == _cur:
                _s.status = "running"
            else:
                _s.status = "pending"
    db.commit()
    return dp.id


# ─── 原 L1644-1683 ───
def _k8s_preflight_ai(db: Session, p: K8sClusterPlan, nodes_env: list) -> dict:
    """AI 预检: 根据每节点探测结果, 生成整体部署方案与风险项。
    返回 {"plan"|"strategy"|"containerd_install"|"preflight_notes"|"risks"|"recommendation"}。
    AI 不可用则回退规则生成。"""
    fallback = _k8s_preflight_rules(db, p, nodes_env)
    provider = _k8s_ai_provider(db)
    if not provider:
        return fallback
    probe_summary = [{
        "node": e.get("node", ""), "os": f"{e.get('os_id')} {e.get('os_version')}",
        "pkg_mgr": e.get("pkg_mgr"), "has_tar": e.get("has_tar"),
        "containerd": e.get("has_containerd"), "epel": e.get("epel_enabled"),
    } for e in nodes_env]
    system = (
        "你是资深 Kubernetes 集群部署架构师。根据节点预检结果，为离线集群部署制定方案。\n"
        "只输出 JSON，不要额外内容：\n"
        "{\n"
        '  "strategy": "在线/离线/混合",\n'
        '  "containerd_install": "离线包/静态二进制在线下载/EPEL包源/apt包源",\n'
        '  "risks": ["风险1", "风险2"],\n'
        '  "preflight_notes": ["部署要点1", "部署要点2"]\n'
        "}\n"
        "判断要点：\n"
        "- 有离线包(bundle)且节点缺 containerd → containerd_install=离线包；否则按系统类型选 EPEL(RHEL系)/apt(Debian系)/静态二进制在线下载\n"
        "- 无 tar 的 RHEL 系统，静态二进制解压会失败 → 优先 EPEL 包源；若 EPEL 未启用需先启 EPEL\n"
        "- K8s 版本对应 containerd 1.7.x 为宜"
    )
    user = (
        f"## 集群\n名称: {p.name}; K8s版本: {p.kubernetes_version}; 运行时: {p.runtime}; CNI: {p.cni}\n"
        f"离线包: {'有(bundle_id=' + str(p.bundle_id) + ')' if p.bundle_id else '无'}\n"
        f"代理: {p.http_proxy or '无'}\n"
        f"## 节点预检\n{json.dumps(probe_summary, ensure_ascii=False, indent=1)}"
    )
    res = _k8s_ai_call(db, system, user, fallback, timeout=60)
    res.setdefault("preflight_notes", fallback.get("preflight_notes", []))
    res.setdefault("risks", fallback.get("risks", []))
    res.setdefault("strategy", fallback.get("strategy", "在线"))
    res.setdefault("containerd_install", fallback.get("containerd_install", "EPEL包源"))
    res["recommendation"] = fallback["recommendation"]
    return res


# ─── 原 L1686-1712 ───
def _k8s_preflight_rules(db: Session, p: K8sClusterPlan, nodes_env: list) -> dict:
    """AI 不可用时的规则兜底预检。"""
    notes, risks = [], []
    containerd_install, strategy, recommendation = "EPEL包源", "在线", "proceed"
    for e in nodes_env:
        if e.get("has_containerd"):
            continue
        if e.get("pkg_mgr") in ("dnf", "yum"):
            if not e.get("has_tar"):
                notes.append(f"{e.get('node')}: RHEL系无tar，containerd 用 EPEL 包源安装")
                containerd_install = "EPEL包源"
            else:
                containerd_install = "静态二进制在线下载"
        elif e.get("pkg_mgr") == "apt":
            containerd_install = "apt包源"
        if not e.get("has_tar"):
            risks.append(f"{e.get('node')}: 缺少 tar(会影响静态包解压)")
    if any(e.get("os_id", "").lower().find("rocky") >= 0 or e.get("os_id", "").lower().find("rhel") >= 0 for e in nodes_env):
        notes.append("Rocky/RHEL 默认源无 containerd 包，需 EPEL 或静态二进制")
    if not all(e.get("disk_avail_mb", 0) >= 2048 for e in nodes_env):
        risks.append("存在节点磁盘可用空间 <2GB")
    if not all(e.get("mem_mb", 0) >= 2048 for e in nodes_env):
        risks.append("存在节点内存 <2GB")
    return {
        "strategy": strategy, "containerd_install": containerd_install,
        "risks": risks, "preflight_notes": notes, "recommendation": recommendation,
    }


# ─── 原 L1715-1743 ───
def _k8s_failure_diagnosis(db: Session, phase: str, description: str, output: str, env_context: dict = None) -> dict:
    """阶段失败时 AI 诊断根因并给出修复建议与方案选项(供前端提交选择)。
    复用 deploy_service._ai_diagnose_failure(DeployStep 适配)。AI 不可用则规则兜底。"""
    options = [
        {"key": "fix", "title": "修复并重试", "desc": "应用 AI 建议的修复命令后重试该阶段"},
        {"key": "retry", "title": "仅重试", "desc": "不修复，重新执行该阶段"},
        {"key": "skip", "title": "跳过该阶段", "desc": "标记跳过，继续后续阶段（可能导致集群不完整）"},
        {"key": "rollback", "title": "停止部署", "desc": "中止并清理，稍后调整方案再部署"},
    ]
    fallback = {
        "ok": True, "root_cause": f"{description} 失败: {output[-300:]}",
        "fix_commands": [], "suggestion": "rollback", "options": options,
    }
    provider = _k8s_ai_provider(db)
    if not provider:
        return fallback
    try:
        from app.models import DeployStep
        from app.services.deploy_service import _ai_diagnose_failure, _extract_json
        step = DeployStep(step_order=0, description=description, command="", verify_command="")
        diag = _ai_diagnose_failure(db, provider, step, output or "", env_context or {})
        if diag.get("ok"):
            fallback["root_cause"] = diag.get("root_cause", "") or fallback["root_cause"]
            fallback["fix_commands"] = diag.get("fix_commands", []) or []
            fallback["suggestion"] = diag.get("suggestion", "rollback")
        return fallback
    except Exception as e:
        logger.warning(f"AI 阶段诊断异常({phase}): {e}")
        return fallback


# ─── 原 L1746-1755 ───
def _k8s_decision_options(diag: dict, extra_options: list = None) -> list:
    """根据 AI 诊断结果生成可提交的方案选项(前端决策卡用)。"""
    opts = list(diag.get("options") or [])
    for ex in (extra_options or []):
        opts.append(ex)
    # 有 fix 命令时, fix 排在首位
    if diag.get("fix_commands"):
        opts = [{"key": "fix", "title": "修复并重试", "desc": ", ".join(diag["fix_commands"][:2])}
                ] + [o for o in opts if o["key"] != "fix"]
    return opts


