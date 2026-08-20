# -*- coding: utf-8 -*-
"""mcp_tools.py 绞杀者拆分: 字节级搬运函数块到 6 个子模块, 原文件变门面 re-export。
不改任何函数体, 只移动行 + 构造头部/尾部。拆分前自动备份。
"""
import os
import re
import shutil

SRC = "app/services/mcp_tools.py"
BACKUP = "logs/mcp_tools_backup_20260820.py"

# 域块起始行(1-based), 顺序排列; 最后一个块的 end = 3192(尾部注册语句起点)
starts = [21, 51, 152, 212, 483, 529, 583, 713, 766, 831, 934, 1114,
          1797, 1814, 2067, 2195, 2309, 2443, 2552, 2666, 2750, 2881,
          2967, 3038, 3141]
TAIL_START = 3192  # L3192-3196 尾部注册语句保留在门面

os.makedirs("logs", exist_ok=True)
# 备份
shutil.copy2(SRC, BACKUP)
print("已备份到:", BACKUP)

lines = open(SRC, encoding="utf-8").readlines()
total = len(lines)

# 头部模板: L1-15 (imports) + L17-18 (_get_db), L16 空行
header_lines = lines[0:15] + ["\n"] + lines[16:18]

# 域注释行验证
for st in starts:
    assert re.match(r"^# ───", lines[st - 1]), f"L{st} 不是域注释: {lines[st - 1]!r}"

# 分配: 每块 (title, [lines])
def block_lines(idx):
    start = starts[idx] - 1
    end = starts[idx + 1] - 1 if idx + 1 < len(starts) else TAIL_START - 1
    blk = lines[start:end]
    # 去掉块尾部多余空行
    while blk and not blk[-1].strip():
        blk.pop()
    return blk

def title_of(idx):
    m = re.match(r"^# ───\s*(.*?)\s*─*$", lines[starts[idx] - 1].rstrip())
    return m.group(1).strip()

# 分组映射: 块索引 -> 目标文件
GROUPS = {
    "mcp_tools_monitor.py": [1, 2, 3, 4, 5, 9],      # Alert/Asset/Metric/Incident/Change/K8s
    "mcp_tools_knowledge.py": [0, 6, 7, 8],          # 代码库/Knowledge/RAG/Runbook
    "mcp_tools_analysis.py": [10],                    # Analysis
    "mcp_tools_execute.py": [11],                     # Execute 15个
    "mcp_tools_action.py": [12, 13, 14, 15, 16],      # Action/SOP/编排/后台任务
    "mcp_tools_observability.py": [17, 18, 19, 20, 21, 22, 23, 24],  # 日志/链路/MySQL/Redis/Kafka/网络
}

# 门面 re-export 公共符号(非 _ 前缀)
PUBLIC_SYMBOLS = [
    "search_code", "query_alerts", "get_alert_detail", "query_assets",
    "query_metrics", "query_incidents", "query_change_records",
    "generate_knowledge_from_incident", "generate_knowledge_from_alert",
    "query_knowledge", "query_knowledge_rag", "query_runbook",
    "list_k8s_pods", "query_k8s_events",
    "analyze_incident_rca", "query_correlation_analysis", "run_preset_diagnosis",
    "execute_restart_service", "execute_clean_disk", "execute_run_script",
    "execute_run_command", "execute_acknowledge_alert", "execute_resolve_alert",
    "execute_resolve_incident", "execute_silence_alert",
    "execute_create_alert_rule", "execute_update_alert_rule",
    "execute_delete_alert_rule", "execute_create_asset", "execute_update_asset",
    "execute_delete_asset", "execute_probe_assets",
    "list_executable_actions", "switch_sub_agent", "propose_action",
    "list_workflow_templates", "propose_workflow",
    "list_agent_workflows", "run_agent_workflow",
    "get_task_status", "list_recent_tasks", "execute_install_package",
    "query_logs", "query_log_sources", "query_traces",
    "query_mysql", "check_mysql_permissions", "execute_mysql",
    "redis_monitor", "kafka_monitor", "net_device_query",
]

def write_submodule(fname, idxs):
    body_lines = []
    for idx in idxs:
        body_lines += block_lines(idx) + ["", ""]
    content = "".join(header_lines) + "\n" + "".join(body_lines).rstrip() + "\n"
    with open(os.path.join("app/services", fname), "w", encoding="utf-8") as f:
        f.write(content)
    print("生成 %s (%d 行)" % (fname, content.count("\n")))

for fname, idxs in GROUPS.items():
    write_submodule(fname, idxs)

# 门面文件
facade_parts = []
facade_parts.append("".join(header_lines))
facade_parts.append("\n# ─── 拆分后门面: 子模块在 import 时经装饰器副作用完成工具注册 ───\n")
for fname in GROUPS:
    facade_parts.append(f"from app.services.{fname[:-3]} import *  # noqa: F401,F403 — 触发注册\n")
facade_parts.append("\n# ─── 保留外部可导入符号 (公共 API 稳定) ───\n")
for sym in PUBLIC_SYMBOLS:
    facade_parts.append(f"from app.services.{' import '.join(['', sym])}\n".replace(" import ", " import ", 1))
# 修正: 上面的生成方式不对, 重写为逐个模块显式 import
facade_parts = []
facade_parts.append("".join(header_lines))
facade_parts.append("\n# ─── 拆分后门面: import 子模块触发装饰器工具注册 ───\n")
for fname in GROUPS:
    facade_parts.append(f"from app.services.{fname[:-3]} import *  # noqa: F401,F403 — 触发注册\n")
facade_parts.append("\n# ─── 显式 re-export 公共符号(保持 mcp_tools.<fn> 可用) ───\n")
imports_per_mod = {fname: [] for fname in GROUPS}
MOD_SYMS = {
    "mcp_tools_monitor": ["search_code"],
    "mcp_tools_action": []}
MOD_SYMS = {
    "mcp_tools_monitor": ["query_alerts", "get_alert_detail", "query_assets",
                         "query_metrics", "query_incidents", "query_change_records",
                         "list_k8s_pods", "query_k8s_events"],
    "mcp_tools_knowledge": ["search_code", "generate_knowledge_from_incident",
                            "generate_knowledge_from_alert", "query_knowledge",
                            "query_knowledge_rag", "query_runbook"],
    "mcp_tools_analysis": ["analyze_incident_rca", "query_correlation_analysis",
                           "run_preset_diagnosis"],
    "mcp_tools_execute": ["execute_restart_service", "execute_clean_disk",
                          "execute_run_script", "execute_run_command",
                          "execute_acknowledge_alert", "execute_resolve_alert",
                          "execute_resolve_incident", "execute_silence_alert",
                          "execute_create_alert_rule", "execute_update_alert_rule",
                          "execute_delete_alert_rule", "execute_create_asset",
                          "execute_update_asset", "execute_delete_asset",
                          "execute_probe_assets"],
    "mcp_tools_action": ["list_executable_actions", "switch_sub_agent",
                         "propose_action", "list_workflow_templates",
                         "propose_workflow", "list_agent_workflows",
                         "run_agent_workflow", "get_task_status",
                         "list_recent_tasks", "execute_install_package"],
    "mcp_tools_observability": ["query_logs", "query_log_sources", "query_traces",
                                "query_mysql", "check_mysql_permissions",
                                "execute_mysql", "redis_monitor", "kafka_monitor",
                                "net_device_query"],
}
for mod, syms in MOD_SYMS.items():
    if syms:
        facade_parts.append(f"from app.services.{mod} import {', '.join(syms)}  # noqa: F401\n")
facade_parts.append("\n__all__ = [\n")
for sym in PUBLIC_SYMBOLS:
    facade_parts.append(f"    {sym!r},\n")
facade_parts.append("]\n")
# 尾部注册语句(原 L3192-3196) 保留
facade_parts.append("\n# 技能/工具包/组件工具注册(原文件尾部)\n")
facade_parts.append("from app.services import skill_mcp_tools  # noqa: E402,F401\n")
facade_parts.append("from app.services import toolbag_mcp_tools  # noqa: E402,F401\n")
facade_parts.append("from app.services import component_mcp_tools  # noqa: E402,F401\n")

with open(SRC, "w", encoding="utf-8") as f:
    f.write("".join(facade_parts))
print("\n门面已写入 %s (%d 行)" % (SRC, "".join(facade_parts).count("\n")))
print("完成")