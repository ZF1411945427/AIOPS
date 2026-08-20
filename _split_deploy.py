# -*- coding: utf-8 -*-
"""deploy_service.py 绞杀者拆分 v2.
子模块:
  deploy_state.py     — 模块级共享状态(_EXEC_LOCK/_RUNNING_CLIENTS/...)
  deploy_common.py    — 基础工具+序列化+常量
  deploy_ai_engine.py — _ai_* 决策簇(含 _DeferredCallLLM 代理)
  deploy_executor.py  — 执行链(execute_plan/_ai_stream_execute/回滚等)
  deploy_report_gen.py— 报告域(post_deploy_verify/generate_deploy_report/记录)
门面(原 deploy_service.py) 稍后重建 — 保留公共API + re-export 全部符号
"""
import os
import re
import shutil

SRC = "app/services/deploy_service.py"
BACKUP = "logs/deploy_service_backup_20260820.py"
os.makedirs("logs", exist_ok=True)
if not os.path.exists(BACKUP):
    shutil.copy2(SRC, BACKUP)
    print("备份:", BACKUP)
else:
    print("备份已存在, 跳过")

lines = open(SRC, encoding="utf-8").readlines()
total = len(lines)
print("原文件行数:", total)

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

HEADER = (
    "import json\nimport re\nfrom datetime import datetime\n"
    "from typing import Any, Dict, List, Optional\n\n"
    "from sqlalchemy.orm import Session\n\n"
    "from app.models import DeployPlan, DeployStep, Asset, AIProvider, AgentConfig\n"
    "from app.services.ssh_helper import connect_ssh\n"
    "from app.logger import logger\n"
    "from app.services.deploy_report import (_generate_fallback_report, _report_to_markdown,\n"
    "                                        _report_to_html, _report_to_docx)\n\n"
)

LAZY_CALL_LLM = '''
class _DeferredCallLLM:
    """延迟取门面 call_llm, 确保测试 monkeypatch deploy_service.call_llm 生效。"""
    __slots__ = ()
    def __call__(self, *args, **kwargs):
        from app.services import deploy_service as _ds
        return _ds.call_llm(*args, **kwargs)

call_llm = _DeferredCallLLM()
'''

# 共享状态模块
state_content = '''"""deploy_service 拆分后共享模块级状态(所有子模块 import 同一对象)。"""
from typing import Any, Dict

# 进程内执行互斥：同一计划同一时刻只允许一个执行流(HTTP 或 WS)。僵尸 running 状态可重跑。
_EXEC_LOCK: Dict[int, bool] = {}
# 活跃 SSH 客户端注册表（供停止接口关闭连接中断执行）
_RUNNING_CLIENTS: Dict[int, Any] = {}
# 停止请求标志：producer 检测到后立即终止且不覆盖状态
_STOPPED: Dict[int, bool] = {}
# 用户决策队列：plan_id -> queue.Queue（WS 路由转发用户"修复/重试/回滚/跳过"决策）
_DECISIONS: Dict[int, Any] = {}
# 单步骤 SSH 命令最大执行时长（docker build 等长任务，超时终止）
_STEP_TIMEOUT = 600
'''
with open("app/services/deploy_state.py", "w", encoding="utf-8") as f:
    f.write(state_content)
print("deploy_state.py: %d 行" % state_content.count("\n"))

# ── COMMON 块 ──
COMMON_BLOCKS = [
    26, 61, 325, 329, 343, 359, 367, 765, 820, 826, 834, 858, 876, 890,
    1002, 1018, 1024, 1038, 1046, 1066, 1096, 1103, 1117, 1148,
    3556, 3596, 3617,
    817,  # 常量 _GIT_HOST_HINTS
    1062, # 常量 _OFFLINE_PUBLIC_IMAGES + _PUBLIC_REPO_HINTS
]

AI_BLOCKS = [192, 506, 560, 1478, 1541, 1585, 1623, 1665, 1686,
             1726, 1764, 1793, 1835, 1884, 1919, 1958, 2028]

EXEC_BLOCKS = [1237, 1457, 2160, 2186, 2198, 2215, 2827, 2853,
               2953, 2988, 3005, 3022]

REPORT_BLOCKS = [3082, 3159, 3268, 3490, 3513, 3536]

GATEWAY_BLOCKS = [35, 104, 227, 266, 374, 388, 396, 426, 458, 484, 496,
                  627, 779, 1161]

def emit_blocks(blocks):
    out = []
    for start in blocks:
        s, e = block_range(start)
        out.append("# ─── 原 L%d-%d ───\n" % (s, e))
        out.extend(lines[s - 1:e])
        out.append("\n\n")
    return out

def build(fname, blocks, extra_imports="", extra_top=""):
    out = ['"""子模块(由 deploy_service 拆分生成, 勿手改函数体)"""\n\n']
    out.append("from app.services.deploy_state import *  # noqa: F401,F403\n\n")
    if extra_top:
        out.append(extra_top + "\n\n")
    out.append(HEADER)
    if extra_imports:
        out.append(extra_imports + "\n\n")
    out.extend(emit_blocks(blocks))
    content = "".join(out)
    with open(os.path.join("app/services", fname), "w", encoding="utf-8") as f:
        f.write(content)
    print("%s: %d 行" % (fname, content.count("\n")))

# common: 无 call_llm 依赖
build("deploy_common.py", COMMON_BLOCKS)

# ai_engine: 依赖 common + call_llm 代理
AI_EXTRA = (
    "from app.services.deploy_common import (  # noqa: F401\n"
    "    _now, _get_provider, _get_assets, _extract_json, _safe_json,\n"
    "    _resolve_command, _ssh_connect, _offline_blocked_reason, _proxy_env_prefix,\n"
    "    _sync_env_mapping_from_sop, resolve_download_path, _is_valid_shell_command,\n"
    "    _check_unresolved, _get_asset_ids,\n"
    ")\n"
)
build("deploy_ai_engine.py", AI_BLOCKS, AI_EXTRA, LAZY_CALL_LLM)

# executor: 依赖 common + ai_engine + call_llm 代理
EXEC_EXTRA = (
    "from app.services.deploy_common import (  # noqa: F401\n"
    "    _now, _get_provider, _get_assets, _get_asset_ids, _extract_json, _safe_json,\n"
    "    _resolve_command, _check_unresolved, _ssh_connect, _offline_blocked_reason,\n"
    "    _proxy_env_prefix, _sync_env_mapping_from_sop, resolve_download_path,\n"
    "    _is_valid_shell_command, _plan_to_dict, _step_to_dict, auto_download_artifact,\n"
    "    _run_ssh, detect_artifact_source, _sanitize_dirname,\n"
    ")\n"
    "from app.services.deploy_ai_engine import (  # noqa: F401\n"
    "    _ai_diagnose_failure, _ai_auto_resolve_env, _ai_auto_resolve_unresolved,\n"
    "    _ai_build_execution_dag, _ai_pre_execution_risk, _ai_autonomous_decision,\n"
    "    _ai_adaptive_rollback, _ai_decision_log, _ai_select_deployment_strategy,\n"
    "    _ai_risk_scoring, _record_deployment_feature, _ai_pattern_matching,\n"
    "    _ai_assess_state, _ai_health_gate, _ai_dynamic_scheduling,\n"
    "    _ai_plan_step_autonomous, _ai_resource_check,\n"
    ")\n"
)
build("deploy_executor.py", EXEC_BLOCKS, EXEC_EXTRA, LAZY_CALL_LLM)

# report_gen: 依赖 common + call_llm 代理
REPORT_EXTRA = (
    "from app.services.deploy_common import (  # noqa: F401\n"
    "    _now, _get_provider, _get_assets, _extract_json, _safe_json,\n"
    "    _ssh_connect,\n"
    ")\n"
)
build("deploy_report_gen.py", REPORT_BLOCKS, REPORT_EXTRA, LAZY_CALL_LLM)

print("四个子模块生成完成")