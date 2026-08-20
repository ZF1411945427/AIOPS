import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, Asset, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service
from app.services.promql_parser import parse_promql, promql_to_dict


import logging
logger = logging.getLogger(__name__)

def _get_db():
    return get_session_for(get_db_mode())()

# ─── 拆分后门面: import 子模块触发装饰器工具注册 ───
from app.services.mcp_tools_monitor import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_knowledge import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_analysis import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_execute import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_action import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_observability import *  # noqa: F401,F403 — 触发注册
from app.services.mcp_tools_metrics import *  # noqa: F401,F403 — 触发注册

# ─── 显式 re-export 公共符号(保持 mcp_tools.<fn> 可用) ───
from app.services.mcp_tools_monitor import query_alerts, get_alert_detail, query_assets, query_metrics, query_incidents, query_change_records, list_k8s_pods, query_k8s_events  # noqa: F401
from app.services.mcp_tools_knowledge import search_code, generate_knowledge_from_incident, generate_knowledge_from_alert, query_knowledge, query_knowledge_rag, query_runbook  # noqa: F401
from app.services.mcp_tools_analysis import analyze_incident_rca, query_correlation_analysis, run_preset_diagnosis  # noqa: F401
from app.services.mcp_tools_execute import execute_restart_service, execute_clean_disk, execute_run_script, execute_run_command, execute_acknowledge_alert, execute_resolve_alert, execute_resolve_incident, execute_silence_alert, execute_create_alert_rule, execute_update_alert_rule, execute_delete_alert_rule, execute_create_asset, execute_update_asset, execute_delete_asset, execute_probe_assets  # noqa: F401
from app.services.mcp_tools_action import list_executable_actions, switch_sub_agent, propose_action, list_workflow_templates, propose_workflow, list_agent_workflows, run_agent_workflow, get_task_status, list_recent_tasks, execute_install_package  # noqa: F401
from app.services.mcp_tools_observability import query_logs, query_log_sources, query_traces, query_mysql, check_mysql_permissions, execute_mysql, redis_monitor, kafka_monitor, net_device_query  # noqa: F401
from app.services.mcp_tools_metrics import generate_promql, list_metric_cards, execute_create_metric_card, execute_delete_metric_card  # noqa: F401

__all__ = [
    'search_code',
    'query_alerts',
    'get_alert_detail',
    'query_assets',
    'query_metrics',
    'query_incidents',
    'query_change_records',
    'generate_knowledge_from_incident',
    'generate_knowledge_from_alert',
    'query_knowledge',
    'query_knowledge_rag',
    'query_runbook',
    'list_k8s_pods',
    'query_k8s_events',
    'analyze_incident_rca',
    'query_correlation_analysis',
    'run_preset_diagnosis',
    'execute_restart_service',
    'execute_clean_disk',
    'execute_run_script',
    'execute_run_command',
    'execute_acknowledge_alert',
    'execute_resolve_alert',
    'execute_resolve_incident',
    'execute_silence_alert',
    'execute_create_alert_rule',
    'execute_update_alert_rule',
    'execute_delete_alert_rule',
    'execute_create_asset',
    'execute_update_asset',
    'execute_delete_asset',
    'execute_probe_assets',
    'list_executable_actions',
    'switch_sub_agent',
    'propose_action',
    'list_workflow_templates',
    'propose_workflow',
    'list_agent_workflows',
    'run_agent_workflow',
    'get_task_status',
    'list_recent_tasks',
    'execute_install_package',
    'query_logs',
    'query_log_sources',
    'query_traces',
    'query_mysql',
    'check_mysql_permissions',
    'execute_mysql',
    'redis_monitor',
    'kafka_monitor',
    'net_device_query',
    'generate_promql',
    'list_metric_cards',
    'execute_create_metric_card',
    'execute_delete_metric_card',
]

# 技能/工具包/组件工具注册(原文件尾部)
from app.services import skill_mcp_tools  # noqa: E402,F401
from app.services import toolbag_mcp_tools  # noqa: E402,F401
from app.services import component_mcp_tools  # noqa: E402,F401
