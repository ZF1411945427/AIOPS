# -*- coding: utf-8 -*-
"""验证 mcp_tools 拆分后注册完整性。"""
import app.services.mcp_tools
from app.services.mcp_registry import get_mcp_tool, get_mcp_manifest

key_tools = [
    'query_alerts', 'query_assets', 'query_metrics', 'propose_action',
    'redis_monitor', 'kafka_monitor', 'net_device_query',
    'execute_restart_service', 'execute_run_script',
    'query_logs', 'query_traces', 'query_mysql',
    'list_agent_workflows', 'search_code', 'query_knowledge_rag',
    'query_runbook', 'list_k8s_pods', 'analyze_incident_rca',
    'list_executable_actions', 'get_task_status',
    'query_incidents', 'query_change_records',
]

print("=== 逐个工具检索 ===")
for t in key_tools:
    found = get_mcp_tool(t)
    print(f"  {t}: {'OK' if found else 'MISSING'}")

manifest = get_mcp_manifest()
print(f"\n=== MCP manifest 工具总数: {len(manifest)} ===")
names = [m['name'] for m in manifest]
missing = [t for t in key_tools if t not in names]
print(f"manifest 缺失: {missing if missing else '无, 全部OK'}")

# 也检查内部工具(execute_*)
from app.services.mcp_registry import get_internal_tools
internals = [t.name for t in get_internal_tools()]
print(f"\n内部工具(execute_*): {len(internals)} 个")
print(f"  含 execute_restart_service: {'execute_restart_service' in internals}")