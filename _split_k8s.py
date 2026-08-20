# -*- coding: utf-8 -*-
"""k8s_offline_deploy_service.py 绞杀者拆分.
DAG: common <- runtime <- generator <- 门面(CRUD+公共API+编排)
依赖方向单向, 状态/常量在 common 共享, 门面 re-export 同一引用。
"""
import os
import re
import shutil

SRC = "app/services/k8s_offline_deploy_service.py"
BACKUP = "logs/k8s_offline_deploy_service_backup_20260820.py"
os.makedirs("logs", exist_ok=True)
if not os.path.exists(BACKUP):
    shutil.copy2(SRC, BACKUP)
    print("备份:", BACKUP)
else:
    print("备份已存在, 跳过")

lines = open(BACKUP, encoding="utf-8").readlines()  # 从备份读原始行!
total = len(lines)
print("原文件行数(备份):", total)

tops = []
for i, ln in enumerate(lines):
    m = re.match(r"^(def|class) (\w+)", ln)
    if m:
        tops.append((i + 1, m.group(1), m.group(2)))

def _next_top_after(line_1based):
    for ln, kind, name in tops:
        if ln > line_1based:
            return ln
    return len(lines) + 1

def block_range(start_1based):
    end = _next_top_after(start_1based) - 1
    while end > start_1based and not lines[end - 1].strip():
        end -= 1
    return (start_1based, end)

def emit_blocks(blocks):
    out = []
    for b in blocks:
        if isinstance(b, tuple):
            s, e = b  # 显式区间
        else:
            s, e = block_range(b)
        out.append("# ─── 原 L%d-%d ───\n" % (s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")
    return out

# ───────────────── 归属: common ─────────────────
COMMON_BLOCKS = [
    (27, 58),   # 常量 _PROJECT_ROOT/EXTRACT_ROOT/_DEFAULT_CNI_FILES/_CNI_POD_CIDR + 状态 _EXEC_LOCK..._ACTIVE_CHANNELS_LOCK
    61, 65, 73, 85, 97,          # channel/决策基础
    (114, 133), # class _DeployStopped
    136, 140, 144, 151, 163, 172,  # 基础工具
    196, 224, 245, 255, 263, 269,  # 序列化/资产/连接
    440,        # stop_execution (公共, 依赖 channel - 放 common? 是公共API, 门面 re-export)
    457, 461,   # _release_exec/_check_stop
]

# ───────────────── 归属: runtime (执行步骤 + 编排执行辅助) ─────────────────
RUNTIME_BLOCKS = [
    467, 508,                     # _get_bundle_context/_parse_ctl_rc
    524, 552,                     # _run_remote/_iter_remote
    587, 592, 597,                # _use_stop_guard/_check_stop_remote/_spawn_stop_guard
    618, 628,          # _sftp_put/_exec_ssh_db
    638, 655, 662, 686, 692, 711,  # 环境准备执行步骤
    756, 787, 792, 819, 863,       # 集群管理执行
    929, 997, 1015,          # _install_cilium/_normalize/_install_preflight_deps
    1583,             # _probe_node_environment
    1758, 1850, 1899, 1929, 2008, 2121, 2134, 2144,  # 安装二进制/生成配置/证书/镜像
]

# ───────────────── 归属: docker (docker/containerd 运行时) ─────────────────
DOCKER_BLOCKS = [
    895, 913,          # _proxy_env_script/_remote_arch
    1068, 1100,        # _containerd_config_script/_configure_containerd_net
    1201, 1220, 1323, 1372, 1423, 1432, 1505, 1550,  # docker/containerd
]

# ───────────────── 归属: generator (七阶段编排 + 报告 + 落库 + AI预检) ─────────────────
GENERATOR_BLOCKS = [
    2165,             # _run_deploy_generator
    2773, 2794, 2810, 2827, 2871,  # 报告/落库/AI诊断/数据源
    1644, 1686, 1715, 1746,        # AI 预检
]

# ───────────────── 门面保留: header(1-26注释+imports) + CRUD(293-464中的create/get/list/update/delete) + orchestration + public API ─────────────────
GATEWAY_BLOCKS = [
    293, 343, 357, 372, 428,  # CRUD create_plan/get_plan/list_plans/update_plan/delete_plan
    467, 508, 524, 552,        # _get_bundle_context/_parse_ctl_rc/_run_remote/_iter_remote
    587, 592, 597,             # stop_guard 执行内联
    2911, 2956, 2976, 3011, 3062,  # run_deploy/submit_decision/validate_plan/precheck_plan/_ai_precheck_advice
]

HEADER = lines[:26]  # 原始注释+imports (L1-26)

def build_common():
    out = ['"""子模块: k8s_offline 常量/状态/基础工具(拆分生成, 勿手改函数体)"""\n\n']
    out.append("import json\nimport os\nimport time\nimport tarfile\n")
    out.append("from datetime import datetime\nfrom pathlib import Path\n")
    out.append("from typing import Any, Dict, Optional\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,\n")
    out.append("                        OfflineRepoBundle, OfflineRegistry, Asset)\n")
    out.append("from app.logger import logger\n")
    out.append("from app.services import offline_repo_service\n")
    out.append("import threading as _threading\n\n")
    out.extend(emit_blocks(COMMON_BLOCKS))
    return "".join(out)

def build_runtime():
    out = ['"""子模块: k8s_offline 执行步骤 + 编排执行辅助(拆分生成)"""\n\n']
    out.append("import os\nimport time\nimport tarfile\n")
    out.append("from datetime import datetime\nfrom pathlib import Path\n")
    out.append("from typing import Any, Dict, Optional\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,\n"
               "                        OfflineRepoBundle, OfflineRegistry, Asset)\n")
    out.append("from app.logger import logger\n")
    out.append("from app.services import offline_repo_service\n")
    out.append("import threading as _threading\n\n")
    out.append("from app.services.k8s_offline_common import (  # noqa: F401\n"
               "    _now, _safe_json, _append_log, _parse_cert_expiry, _get_assets,\n"
               "    _resolve_node_conn, _node_to_dict, _plan_to_dict, _k8s_ai_provider,\n"
               "    _k8s_ai_call, _set_pending_decision, _current_plan_id,\n"
               "    _register_channel, _unregister_channel, _interrupt_plan_channels,\n"
               "    _await_k8s_decision, _DeployStopped,\n"
               "    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,\n"
               "    _ACTIVE_CHANNELS_LOCK,\n"
               ")\n\n")
    out.extend(emit_blocks(RUNTIME_BLOCKS))
    return "".join(out)

def build_docker():
    out = ['"""子模块: k8s_offline docker/containerd 运行时(拆分生成)"""\n\n']
    out.append("import os\nimport time\nimport tarfile\n")
    out.append("from datetime import datetime\nfrom pathlib import Path\n")
    out.append("from typing import Any, Dict, Optional\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,\n"
               "                        OfflineRepoBundle, OfflineRegistry, Asset)\n")
    out.append("from app.logger import logger\n")
    out.append("from app.services import offline_repo_service\n\n")
    out.append("from app.services.k8s_offline_common import (  # noqa: F401\n"
               "    _now, _safe_json, _append_log, _parse_cert_expiry, _get_assets,\n"
               "    _resolve_node_conn, _node_to_dict, _plan_to_dict, _k8s_ai_provider,\n"
               "    _k8s_ai_call, _set_pending_decision, _current_plan_id,\n"
               "    _register_channel, _unregister_channel, _interrupt_plan_channels,\n"
               "    _await_k8s_decision, _DeployStopped,\n"
               "    _EXEC_LOCK, _STOPPED, K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS,\n"
               "    _ACTIVE_CHANNELS_LOCK,\n"
               ")\n")
    out.append("from app.services.k8s_offline_runtime import (  # noqa: F401\n"
               "    _run_remote, _iter_remote, _sftp_put, _exec_ssh_db,\n"
               "    _use_stop_guard, _check_stop_remote, _spawn_stop_guard,\n"
               ")\n\n")
    out.extend(emit_blocks(DOCKER_BLOCKS))
    return "".join(out)

def build_generator():
    out = ['"""子模块: k8s_offline 七阶段部署编排 + 报告/落库/AI预检(拆分生成)"""\n\n']
    out.append("import os\nimport time\nimport tarfile\n")
    out.append("from datetime import datetime\nfrom pathlib import Path\n")
    out.append("from typing import Any, Dict, Optional\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import (K8sClusterPlan, K8sClusterNode, DataSource,\n"
               "                        OfflineRepoBundle, OfflineRegistry, Asset)\n")
    out.append("from app.logger import logger\n")
    out.append("from app.services import offline_repo_service\n\n")
    out.append("from app.services.k8s_offline_common import (  # noqa: F401\n"
               "    _now, _safe_json, _append_log, _parse_cert_expiry, _get_assets,\n"
               "    _resolve_node_conn, _node_to_dict, _plan_to_dict, _k8s_ai_provider,\n"
               "    _k8s_ai_call, _set_pending_decision, _current_plan_id,\n"
               "    _register_channel, _unregister_channel, _interrupt_plan_channels,\n"
               "    _await_k8s_decision, _DeployStopped, _EXEC_LOCK, _STOPPED,\n"
               "    K8S_DECISIONS, _TLOCAL, _ACTIVE_CHANNELS, _ACTIVE_CHANNELS_LOCK,\n"
               ")\n")
    out.append("from app.services.k8s_offline_runtime import (  # noqa: F401\n"
               "    _run_remote, _iter_remote, _sftp_put, _exec_ssh_db, _inject_etc_hosts,\n"
               "    _disable_swap, _setup_kernel, _set_hostname, _ensure_dns,\n"
               "    _grant_admin_clusteradmin, _ensure_core_addons, _fix_cni_kubeconfig_localhost,\n"
               "    _ensure_cni_plugins, _install_cilium, _install_preflight_deps,\n"
               "    _probe_node_environment, _install_k8s_binaries, _generate_kubeadm_config,\n"
               "    _write_imagetar_jobs, _configure_insecure_registry, _apply_cert_expiry,\n"
               "    _extract_yaml_images, _check_cni_pods,\n"
               ")\n")
    out.append("from app.services.k8s_offline_docker import (  # noqa: F401\n"
               "    _proxy_env_script, _remote_arch, _containerd_config_script,\n"
               "    _configure_containerd_net, _docker_daemon_json, _install_docker,\n"
               "    _configure_docker, _install_containerd, _containerd_version_for,\n"
               "    _install_containerd_online, _start_containerd_service,\n"
               "    _ensure_containerd_unit,\n"
               ")\n\n")
    out.extend(emit_blocks(GENERATOR_BLOCKS))
    return "".join(out)

for name, fn in [("k8s_offline_common.py", build_common),
                 ("k8s_offline_runtime.py", build_runtime),
                 ("k8s_offline_docker.py", build_docker),
                 ("k8s_offline_generator.py", build_generator)]:
    content = fn()
    with open(os.path.join("app/services", name), "w", encoding="utf-8") as f:
        f.write(content)
    print("%s: %d 行" % (name, content.count("\n")))

print("四个子模块生成完成")