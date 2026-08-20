# -*- coding: utf-8 -*-
"""重建 deploy_service.py 门面: 保留 GATEWAY_BLOCKS 公共 API + re-export 全部子模块符号。
用 _split_deploy.py 内部同源的行读取逻辑。
"""
import re

SRC = "app/services/deploy_service.py"
BACKUP = "logs/deploy_service_backup_20260820.py"
lines = open(BACKUP, encoding="utf-8").readlines()  # 从备份读原始行

tops = []
for i, ln in enumerate(lines):
    m = re.match(r"^def (\w+)", ln)
    if m:
        tops.append((i + 1, m.group(1)))

def _next_top_after(line_1based):
    for ln, name in tops:
        if ln > line_1based:
            return ln
    return len(lines) + 1

def block_range(start_1based):
    end = _next_top_after(start_1based) - 1
    while end > start_1based and not lines[end - 1].strip():
        end -= 1
    return (start_1based, end)

# 门面保留区(公共 API + 编排辅助)
GATEWAY_BLOCKS = [35, 104, 227, 266, 374, 388, 396, 426, 458, 484, 496,
                  627, 779, 1161]
# 常量 _STEP_TIMEOUT 等已入 deploy_state, 但 _GIT_HOST_HINTS 等已入 common。
# 门面还需模块级常量? _EXEC_LOCK 等状态外, 原 L15-23 定义全部移入 state。

def emit_blocks(blocks):
    out = []
    for start in blocks:
        s, e = block_range(start)
        out.append("# ─── 原 L%d-%d ───\n" % (s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")
    return out

# 门面 re-export 清单: 外部引用 22 + 测试直接访问 + 所有子模块符号
# 从子模块 import * (会自动带公共符号), 再显式补私有符号
RE_EXPORTS = (
    "\n# ─── deploy_state 状态(共享同一对象) ───\n"
    "from app.services.deploy_state import (_EXEC_LOCK, _RUNNING_CLIENTS, _STOPPED,\n"
    "                                       _DECISIONS, _STEP_TIMEOUT)  # noqa: F401\n\n"
    "# ─── deploy_common: 基础工具+序列化+常量 ───\n"
    "from app.services.deploy_common import (  # noqa: F401\n"
    "    _release_exec, _now, _get_provider, _build_offline_hint, _get_asset_ids,\n"
    "    _get_assets, _extract_json, _sanitize_dirname, resolve_download_path,\n"
    "    detect_artifact_source, _run_ssh, _fetch_offline_bundle_path,\n"
    "    auto_download_artifact, _git_zip_url, _set_compose_perms, _resolve_command,\n"
    "    _check_unresolved, _is_valid_shell_command, _offline_blocked_reason,\n"
    "    _assert_online_allowed, _proxy_env_prefix, _sync_env_mapping_from_sop,\n"
    "    _ssh_connect, _collect_env_probes, _plan_to_dict, _step_to_dict, _safe_json,\n"
    "    _GIT_HOST_HINTS, _OFFLINE_PUBLIC_IMAGES, _PUBLIC_REPO_HINTS,\n"
    ")\n\n"
    "# ─── deploy_ai_engine: AI 决策簇 ───\n"
    "from app.services.deploy_ai_engine import (  # noqa: F401\n"
    "    _ai_diagnose_failure, _ai_auto_resolve_env, _ai_auto_resolve_unresolved,\n"
    "    _ai_build_execution_dag, _ai_pre_execution_risk, _ai_autonomous_decision,\n"
    "    _ai_adaptive_rollback, _ai_decision_log, _ai_select_deployment_strategy,\n"
    "    _ai_risk_scoring, _record_deployment_feature, _ai_pattern_matching,\n"
    "    _ai_assess_state, _ai_health_gate, _ai_dynamic_scheduling,\n"
    "    _ai_plan_step_autonomous, _ai_resource_check,\n"
    ")\n\n"
    "# ─── deploy_executor: 执行链 ───\n"
    "from app.services.deploy_executor import (  # noqa: F401\n"
    "    execute_plan, stream_execute, _wait_for_risk_confirm,\n"
    "    _set_pending_decision_plan, submit_decision, _ai_stream_execute,\n"
    "    _ai_stream_rollback, stream_rollback_cleanup, _ai_step_failure,\n"
    "    _run_fix_commands, _do_rollback, _stream_rollback,\n"
    ")\n\n"
    "# ─── deploy_report_gen: 报告域 ───\n"
    "from app.services.deploy_report_gen import (  # noqa: F401\n"
    "    post_deploy_verify, _extract_deploy_info, generate_deploy_report,\n"
    "    download_report, _record_execution_history, _record_cleanup_history,\n"
    ")\n\n"
)

facade = []
facade.append('''"""应用部署编排服务 (DeployPlan/DeployStep) — 拆分后门面。

子模块:
  - deploy_state.py      共享模块级状态
  - deploy_common.py     基础工具/序列化/常量
  - deploy_ai_engine.py  AI 决策簇
  - deploy_executor.py   执行链(execute_plan/_ai_stream_execute/回滚)
  - deploy_report_gen.py 报告域
本文件保留公共 API 并 re-export 全部符号, 保持对外接口不变。
"""\n''')
facade.append("import json\nimport re\nfrom datetime import datetime\n")
facade.append("from typing import Any, Dict, List, Optional\n\n")
facade.append("from sqlalchemy.orm import Session\n\n")
facade.append("from app.models import DeployPlan, DeployStep, Asset, AIProvider, AgentConfig\n")
# call_llm 由门面持有, 供测试 monkeypatch deploy_service.call_llm
facade.append("from app.services.agent_service import call_llm  # noqa: F401\n")
facade.append("from app.services.ssh_helper import connect_ssh\n")
facade.append("from app.logger import logger\n")
facade.append("from app.services.deploy_report import (_generate_fallback_report, _report_to_markdown,\n"
              "                                        _report_to_html, _report_to_docx)  # noqa: F401\n\n")
facade.append(RE_EXPORTS)
facade.append("# ─── 公共释放锁 API(原 L30-33) ───\n")
facade.extend(lines[29:33])  # release_exec_lock 定义
facade.append("\n\n")
# 门面保留区
for start in GATEWAY_BLOCKS:
    # 跳过已经在 re-export 里、但仍需保留定义在门面的公共 API 块
    s, e = block_range(start)
    facade.append("# ─── 原 L%d-%d ───\n" % (s, e))
    facade.extend(lines[s - 1:e])
    facade.append("\n\n")

content = "".join(facade)
with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)
print("门面 %s: %d 行" % (SRC, content.count("\n")))
print("完成")