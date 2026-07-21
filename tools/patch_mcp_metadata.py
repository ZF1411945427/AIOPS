"""批量给 mcp_tools.py 的 45 个 @register_mcp_tool 补 location + category 元数据。
跑一次后即可删除。幂等：已带 location 的工具会跳过。"""
import re
from pathlib import Path

TOOL_META = {
    # Alert
    "query_alerts": ("cloud", "alert"),
    "get_alert_detail": ("cloud", "alert"),
    "execute_acknowledge_alert": ("cloud", "alert"),
    "execute_resolve_alert": ("cloud", "alert"),
    "execute_silence_alert": ("cloud", "alert"),
    "execute_create_alert_rule": ("cloud", "alert"),
    "execute_update_alert_rule": ("cloud", "alert"),
    "execute_delete_alert_rule": ("cloud", "alert"),
    # Asset
    "query_assets": ("cloud", "asset"),
    "execute_create_asset": ("cloud", "asset"),
    "execute_update_asset": ("cloud", "asset"),
    "execute_delete_asset": ("cloud", "asset"),
    "execute_probe_assets": ("edge", "asset"),
    # Metric
    "query_metrics": ("cloud", "metric"),
    # Incident
    "query_incidents": ("cloud", "incident"),
    "execute_resolve_incident": ("cloud", "incident"),
    # Change
    "query_change_records": ("cloud", "change"),
    # Knowledge
    "generate_knowledge_from_incident": ("cloud", "knowledge"),
    "generate_knowledge_from_alert": ("cloud", "knowledge"),
    "query_knowledge": ("cloud", "knowledge"),
    "query_knowledge_rag": ("cloud", "knowledge"),
    "query_runbook": ("cloud", "knowledge"),
    # K8s
    "list_k8s_pods": ("cloud", "k8s"),
    "query_k8s_events": ("cloud", "k8s"),
    # RCA
    "analyze_incident_rca": ("cloud", "rca"),
    "query_correlation_analysis": ("cloud", "rca"),
    # Execute Host
    "execute_restart_service": ("edge", "execute_host"),
    "execute_clean_disk": ("edge", "execute_host"),
    "execute_run_script": ("edge", "execute_host"),
    "execute_run_command": ("edge", "execute_host"),
    "execute_install_package": ("edge", "execute_host"),
    # Workflow
    "list_workflow_templates": ("cloud", "workflow"),
    "propose_workflow": ("cloud", "workflow"),
    "list_agent_workflows": ("cloud", "workflow"),
    "run_agent_workflow": ("cloud", "workflow"),
    # Task
    "get_task_status": ("cloud", "task"),
    "list_recent_tasks": ("cloud", "task"),
    # Propose
    "list_executable_actions": ("cloud", "propose"),
    "propose_action": ("cloud", "propose"),
    # Log
    "query_logs": ("cloud", "log"),
    "query_log_sources": ("cloud", "log"),
    # Trace
    "query_traces": ("cloud", "trace"),
    # MySQL
    "query_mysql": ("cloud", "mysql"),
    "check_mysql_permissions": ("cloud", "mysql"),
    "execute_mysql": ("cloud", "mysql"),
}

path = Path(__file__).resolve().parent.parent / "app" / "services" / "mcp_tools.py"
src = path.read_text(encoding="utf-8")

# 匹配 @register_mcp_tool( ... ) 块，捕获 name 值
pattern = re.compile(
    r'@register_mcp_tool\(\s*\n(.*?)\n\s*\)',
    re.DOTALL,
)

changed = 0
skipped = 0


def add_meta(match):
    global changed, skipped
    block = match.group(1)
    # 提取 name
    name_m = re.search(r'name="([^"]+)"', block)
    if not name_m:
        return match.group(0)
    tool_name = name_m.group(1)
    if tool_name not in TOOL_META:
        return match.group(0)
    # 已有 location 则跳过
    if re.search(r'location\s*=', block):
        skipped += 1
        return match.group(0)
    loc, cat = TOOL_META[tool_name]
    # 在最后一个参数后追加 location 和 category
    # 找到块末尾最后一个逗号或参数，确保格式正确
    new_block = block.rstrip()
    if not new_block.endswith(','):
        new_block += ','
    new_block += f'\n    location="{loc}",\n    category="{cat}",'
    changed += 1
    return f'@register_mcp_tool(\n{new_block}\n)'


new_src = pattern.sub(add_meta, src)

if changed == 0 and skipped > 0:
    print(f"全部 {skipped} 个工具已带 location，无需修改")
else:
    path.write_text(new_src, encoding="utf-8")
    print(f"已修改 {changed} 个工具，跳过 {skipped} 个已带 location 的工具")
print(f"工具映射表共 {len(TOOL_META)} 个")
