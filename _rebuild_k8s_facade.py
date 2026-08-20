# -*- coding: utf-8 -*-
"""重建 k8s_offline_deploy_service.py 门面: header + CRUD + 编排 + 公共API + re-export。"""
import re

SRC = "app/services/k8s_offline_deploy_service.py"
BACKUP_lines = open("logs/k8s_offline_deploy_service_backup_20260820.py", encoding="utf-8").readlines()

tops = []
for i, ln in enumerate(BACKUP_lines):
    m = re.match(r"^(def|class) (\w+)", ln)
    if m:
        tops.append((i + 1, m.group(1), m.group(2)))

def _next_top_after(line_1based):
    for ln, kind, name in tops:
        if ln > line_1based:
            return ln
    return len(BACKUP_lines) + 1

def block_range(start_1based):
    end = _next_top_after(start_1based) - 1
    while end > start_1based and not BACKUP_lines[end - 1].strip():
        end -= 1
    return (start_1based, end)

GATEWAY_BLOCKS = [
    293, 343, 357, 372, 428,  # CRUD
    2911, 2956, 2976, 3011, 3062,  # 公共API
]

facade = []
facade.append('''"""K8S 离线集群部署服务 — 拆分后门面。

子模块:
  - k8s_offline_common.py     常量/状态/基础工具(共享)
  - k8s_offline_runtime.py    执行步骤 + docker 运行时
  - k8s_offline_generator.py  七阶段部署编排 + 报告/落库/AI预检
本文件保留 CRUD/编排/公共 API 并 re-export 全部符号, 保持对外接口不变。
"""\n''')
# header 原始 imports + 常量? 状态/常量已在 common, 但 _PROJECT_ROOT/EXTRACT_ROOT 等被子模块用(common 内)
facade.append(BACKUP_lines[10] + "\n")  # import json
facade.append("import os\nimport time\nimport tarfile\n")
facade.append("from datetime import datetime\nfrom pathlib import Path\n")
facade.append("from typing import Any, Dict, Optional\n\n")
facade.append("from sqlalchemy.orm import Session\n\n")
facade.append("from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,\n")
facade.append("                        OfflineRepoBundle, OfflineRegistry, Asset)\n")
facade.append("from app.logger import logger\n")
facade.append("from app.services import offline_repo_service\n")
facade.append("from app.services.ssh_helper import connect_ssh\n")
facade.append("import threading as _threading\n\n")

# re-export 所有子模块符号(含共享状态同一引用)
facade.append("\n# ─── 从子模块 re-export(门面, 状态为共享同一对象) ───\n")
facade.append("from app.services.k8s_offline_common import (  # noqa: F401\n"
              "    _PROJECT_ROOT, EXTRACT_ROOT, _DEFAULT_CNI_FILES, _CNI_POD_CIDR,\n"
              "    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,\n"
              "    _ACTIVE_CHANNELS_LOCK,\n"
              "    _current_plan_id, _register_channel, _unregister_channel,\n"
              "    _interrupt_plan_channels, _await_k8s_decision, _DeployStopped,\n"
              "    _now, _human, _safe_json, _parse_cert_expiry, _k8s_ai_provider,\n"
              "    _k8s_ai_call, _plan_to_dict, _node_to_dict, _append_log,\n"
              "    _set_pending_decision, _get_assets, _resolve_node_conn,\n"
              "    stop_execution, _release_exec, _check_stop,\n"
              ")\n")
facade.append("from app.services.k8s_offline_runtime import (  # noqa: F401\n"
              "    _get_bundle_context, _parse_ctl_rc, _run_remote, _iter_remote,\n"
              "    _use_stop_guard, _check_stop_remote, _spawn_stop_guard,\n"
              "    _sftp_put, _exec_ssh_db, _inject_etc_hosts, _disable_swap,\n"
              "    _setup_kernel, _set_hostname, _node_hostname, _ensure_dns,\n"
              "    _grant_admin_clusteradmin, _keepalive_check_stopped,\n"
              "    _ensure_core_addons, _fix_cni_kubeconfig_localhost, _ensure_cni_plugins,\n"
              "    _install_cilium, _normalize_k8s_version, _install_preflight_deps,\n"
              "    _probe_node_environment, _install_k8s_binaries,\n"
              "    _generate_kubeadm_config, _write_imagetar_jobs,\n"
              "    _configure_insecure_registry, _apply_cert_expiry,\n"
              "    _cert_days_remaining_check, _extract_yaml_images, _check_cni_pods,\n"
              ")\n")
facade.append("from app.services.k8s_offline_docker import (  # noqa: F401\n"
              "    _proxy_env_script, _remote_arch, _containerd_config_script,\n"
              "    _configure_containerd_net, _docker_daemon_json, _install_docker,\n"
              "    _configure_docker, _install_containerd, _containerd_version_for,\n"
              "    _install_containerd_online, _start_containerd_service,\n"
              "    _ensure_containerd_unit,\n"
              ")\n")
facade.append("from app.services.k8s_offline_generator import (  # noqa: F401\n"
              "    _run_deploy_generator, _ai_failure_diagnosis, _build_report,\n"
              "    _ai_report_summary, _create_platform_datasource, _sync_k8s_deploy_plan,\n"
              "    _k8s_preflight_ai, _k8s_preflight_rules, _k8s_failure_diagnosis,\n"
              "    _k8s_decision_options,\n"
              ")\n\n")

# 门面保留块
for start in GATEWAY_BLOCKS:
    s, e = block_range(start)
    facade.append("# ─── 原 L%d-%d ───\n" % (s, e))
    facade.extend(BACKUP_lines[s - 1:e])
    facade.append("\n\n")

content = "".join(facade)
with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)
print("门面 %s: %d 行" % (SRC, content.count("\n")))
print("完成")