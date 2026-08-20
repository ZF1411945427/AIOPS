# -*- coding: utf-8 -*-
"""component_catalog_service.py 拆分 v2:
- component_catalog_data.py   (纯数据常量, 已生成)
- component_catalog_render.py (配方渲染, 已生成)
- component_catalog_ai.py     (纯 AI 辅助, 已生成)
- component_catalog_ops.py    (CRUD/安装/部署/SSH/健康检查/报告)
- 主文件门面: 保留 deploy_stream/precheck_deploy/决策注册/install_report,
  显式 re-export 全部子模块符号(含下划线, 因 deploy_stream 引用它们)。
"""
import os
import re
import shutil

SRC = "app/services/component_catalog_service.py"
BACKUP = "logs/component_catalog_service_backup_20260820.py"
os.makedirs("logs", exist_ok=True)
if not os.path.exists(BACKUP):
    shutil.copy2(SRC, BACKUP)
    print("备份:", BACKUP)
else:
    print("备份已存在, 跳过")

lines = open(SRC, encoding="utf-8").readlines()
total = len(lines)

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

# ── OPS 分组 (CRUD/安装/真实部署/SSH/健康检查): 1274-2359 区间的函数 ──
OPS_BLOCKS = [
    (1274, "def"),  # list_components
    (1284, "def"),  # get_component
    (1289, "def"),  # _comp_to_dict
    (1318, "def"),  # get_deploy_render
    (1371, "def"),  # list_installs
    (1379, "def"),  # _resolve_pending_decision
    (1390, "def"),  # get_install
    (1395, "def"),  # _install_to_dict
    (1431, "def"),  # record_install
    (1446, "def"),  # update_install_status
    (1457, "def"),  # _append_install_event
    (1472, "def"),  # _set_pending_decision_install
    (1485, "def"),  # get_install_events
    (1496, "def"),  # delete_install
    (1507, "def"),  # _apply_docker_proxy
    (1534, "def"),  # _apply_native_proxy
    (1559, "def"),  # _native_proxy_prefix
    (1574, "def"),  # deploy_docker
    (1608, "def"),  # component_to_asset
    (1678, "def"),  # _asset_brief
    (1685, "def"),  # _exec_ssh
    (1768, "def"),  # check_vuln
    (1817, "def"),  # _trivy_scan
    (1871, "def"),  # _probe_version
    (1887, "def"),  # ai_analyze
    (1956, "def"),  # _build_component_key_points
    (1971, "def"),  # get_stats
    (2019, "def"),  # check_config
    (2071, "def"),  # check_health
    (2140, "def"),  # full_health_check
    (2190, "def"),  # batch_full_check
    (2224, "def"),  # _build_full_health_key_points
    (2240, "def"),  # generate_ai_health_report
    (2344, "def"),  # _build_component_report_key_points
]

def build_ops():
    out = ['"""子模块: 组件目录 CRUD/安装/部署/SSH/健康检查(由拆分生成)"""\n\n']
    out.append("import json\nimport re\nimport socket\nimport base64\nimport time\nimport threading\n")
    out.append("from datetime import datetime\nfrom typing import Optional, List\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import Asset, ComponentCatalog, ComponentInstall\n")
    out.append("from app.routers.agent_sse import _clean_key_point\n\n")
    out.append("import logging\nlogger = logging.getLogger(__name__)\n\n")
    out.append("from app.services.component_catalog_data import ("  # noqa
               "    _BUILTIN_COMPONENTS, _OFFLINE_PUBLIC_SOURCES, _MIN_CVE_RULES,\n"
               "    _HEALTH_CMDS, _CONFIG_FILES, _NATIVE_VERIFY,\n"
               ")\n")
    out.append("from app.services.component_catalog_render import ("
               "    build_default_compose, render_compose, _inject_native_params,\n"
               "    _offline_native_block, native_deploy, _shell_quote, _param_value,\n"
               ")\n")
    out.append("from app.services.component_catalog_ai import _plan_to_visual_steps  # noqa: F401\n\n")
    for start, kind in OPS_BLOCKS:
        s, e = block_range(start)
        out.append("# ─── 原 L%d-%d ───\n" % (s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")
    content = "".join(out)
    with open("app/services/component_catalog_ops.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("component_catalog_ops.py: %d 行" % content.count("\n"))

build_ops()
print("ops 子模块生成完成")

# ═══ 重写主文件为门面 ═══
# 主文件保留的 block(1-based 起始行): 决策注册/流式部署/报告/预检
MAIN_KEEP = [
    (2366, "register_deploy_stop"),
    (2371, "cancel_deploy"),
    (2384, "register_decision"),
    (2392, "resolve_decision"),
    (2402, "submit_install_decision"),
    (2964, "generate_install_report"),
    (3169, "deploy_stream"),
    (3792, "precheck_deploy"),
]
# 常量 _DECISION_REG (L2381)
MAIN_CONST_START = 2381

def build_facade():
    out = ['''"""组件应用商店服务 (Bitnami Catalog 风格) — 拆分后门面。

子模块:
  - component_catalog_data.py   纯数据常量
  - component_catalog_render.py 配方渲染/脚本生成
  - component_catalog_ai.py     纯 AI 辅助
  - component_catalog_ops.py    CRUD/安装/部署/SSH/健康检查
本文件保留流式部署编排(deploy_stream)等核心, 并 re-export 全部公共符号。
"""\n''']
    # 头部 imports(与原文件一致)
    out.append("import json\nimport re\nimport socket\nimport base64\nimport time\nimport threading\n")
    out.append("from datetime import datetime\nfrom typing import Optional, List\n\n")
    out.append("from sqlalchemy.orm import Session\n\n")
    out.append("from app.models import Asset, ComponentCatalog, ComponentInstall\n")
    out.append("from app.routers.agent_sse import _clean_key_point\n\n")
    out.append("import logging\nlogger = logging.getLogger(__name__)\n\n")

    # ── 从子模块 re-export(显式, 含下划线, 保证 deploy_stream 全可见) ──
    out.append("# ─── 从子模块 re-export(门面) ───\n")
    out.append("from app.services.component_catalog_data import (  # noqa: F401\n"
               "    _BUILTIN_COMPONENTS, _OFFLINE_PUBLIC_SOURCES, _MIN_CVE_RULES,\n"
               "    _HEALTH_CMDS, _CONFIG_FILES, _NATIVE_VERIFY, _SHELL_TRANSIENT_VARS,\n"
               ")\n")
    out.append("from app.services.component_catalog_render import (  # noqa: F401\n"
               "    build_default_compose, _param_value, render_compose, _offline_native_block,\n"
               "    _inject_native_params, _shell_quote, _stop_service, native_deploy,\n"
               "    seed_builtin_components,\n"
               ")\n")
    out.append("from app.services.component_catalog_ai import (  # noqa: F401\n"
               "    _ai_decision_options, _ai_intent_to_command, _contains_cn, _ai_generate_plan,\n"
               "    _plan_to_visual_steps, _plan_step_kind, _plan_to_steps, _apply_plan_params,\n"
               "    _get_deploy_provider, _extract_assignments, _native_step_wrapper, safe_json_parse,\n"
               "    _ai_autonomous_decision, _rule_deploy_tip, _ai_deploy_tip, _ai_deploy_diagnosis,\n"
               "    _ai_final_report, _build_install_report_key_points,\n"
               ")\n")
    out.append("from app.services.component_catalog_ops import (  # noqa: F401\n"
               "    list_components, get_component, _comp_to_dict, get_deploy_render,\n"
               "    list_installs, _resolve_pending_decision, get_install, _install_to_dict,\n"
               "    record_install, update_install_status, _append_install_event,\n"
               "    _set_pending_decision_install, get_install_events, delete_install,\n"
               "    _apply_docker_proxy, _apply_native_proxy, _native_proxy_prefix, deploy_docker,\n"
               "    component_to_asset, _asset_brief, _exec_ssh, check_vuln, _trivy_scan,\n"
               "    _probe_version, ai_analyze, _build_component_key_points, get_stats,\n"
               "    check_config, check_health, full_health_check, batch_full_check,\n"
               "    _build_full_health_key_points, generate_ai_health_report,\n"
               "    _build_component_report_key_points,\n"
               ")\n\n")

    # ── 保留: 决策注册 + 流式编排 block ──
    for start, name in MAIN_KEEP:
        s, e = block_range(start)
        out.append("# ─── %s (原 L%d-%d) ───\n" % (name, s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")

    content = "".join(out)
    with open(SRC, "w", encoding="utf-8") as f:
        f.write(content)
    print("\n门面 %s: %d 行" % (SRC, content.count("\n")))

build_facade()
print("完成")