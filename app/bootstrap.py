"""应用启动装配(bootstrap/H4): 集中注册全部路由, 收敛 main.py。"""

def register_routers(app):
    """注册全部 API 路由(按业务域分组)。"""
    # 路由模块按需局部导入, 避免顶层循环依赖
    from app.routers.assets import router as assets_router
    from app.routers.asset_changes import router as asset_changes_router
    from app.routers.asset_discovery import router as asset_discovery_router
    from app.routers.lifecycle import router as lifecycle_router
    from app.routers.topology import router as topology_router
    from app.routers.topology_path import router as topology_path_router
    from app.routers.topo_graph import router as topo_graph_router
    from app.routers.tags import router as tags_router
    from app.routers.ext_cmdb import router as ext_cmdb_router
    from app.routers.alerts import router as alerts_router
    from app.routers.alert_console import router as alert_console_router
    from app.routers.alert_events import router as alert_events_router
    from app.routers.alert_silence import router as alert_silence_router
    from app.routers.alert_storm import router as alert_storm_router
    from app.routers.alert_webhooks import router as alert_webhooks_router
    from app.routers.anomaly import router as anomaly_router
    from app.routers.cluster_anomaly import router as cluster_anomaly_router
    from app.routers.hotspot import router as hotspot_router
    from app.routers.k8s_monitor import router as k8s_monitor_router
    from app.routers.k8s_resources import router as k8s_resources_router
    from app.routers.k8s_cert import router as k8s_cert_router
    from app.routers.containers import router as containers_router
    from app.routers.helm import router as helm_router
    from app.routers.blue_green import router as blue_green_router
    from app.routers.service_mesh import router as service_mesh_router
    from app.routers.ai_providers import router as ai_providers_router
    from app.routers.agent_chat import router as agent_chat_router
    from app.routers.agent_sse import router as agent_sse_router
    from app.routers.agent_workflow import router as agent_workflow_router
    from app.routers.agent_eval import router as agent_eval_router
    from app.routers.agent_ground_truth import router as agent_ground_truth_router
    from app.routers.ab_test import router as ab_test_router
    from app.routers.anomaly_eval import router as anomaly_eval_router
    from app.routers.sub_agents import router as sub_agents_router
    from app.routers.im_chatops import router as im_chatops_router
    from app.routers.edge_tunnel import router as edge_tunnel_router
    from app.routers.webssh import router as webssh_router
    from app.routers.sandbox import router as sandbox_router
    from app.routers.agent_deploy import router as agent_deploy_router
    from app.routers.agent_autonomous import router as agent_autonomous_router
    from app.routers.deploy import router as deploy_router
    from app.routers.offline_repo import router as offline_repo_router
    from app.routers.k8s_offline_deploy import router as k8s_offline_deploy_router
    from app.routers.sre import router as sre_router
    from app.routers.chaos import router as chaos_router
    from app.routers.inspection import router as inspection_router
    from app.routers.baseline import router as baseline_router
    from app.routers.remediation import router as remediation_router
    from app.routers.remediation_workflow import router as remediation_workflow_router
    from app.routers.remediation_effect import router as remediation_effect_router
    from app.routers.runbooks import router as runbooks_router
    from app.routers.knowledge import router as knowledge_router
    from app.routers.knowledge_documents import router as knowledge_documents_router
    from app.routers.knowledge_v2 import router as knowledge_v2_router
    from app.routers.knowledge_graph import router as knowledge_graph_router
    from app.routers.knowledge_autogen import router as knowledge_autogen_router
    from app.routers.smart_recommend import router as smart_recommend_router
    from app.routers.incidents import router as incidents_router
    from app.routers.dashboard import router as dashboard_router
    from app.routers.dashboard_config import router as dashboard_config_router
    from app.routers.ops_analytics import router as ops_analytics_router
    from app.routers.reports import router as reports_router
    from app.routers.report_schedules import router as report_schedules_router
    from app.routers.traces import router as traces_router
    from app.routers.traces_api import router as traces_api_router
    from app.routers.trace_anomaly import router as trace_anomaly_router
    from app.routers.trace_ingest import router as trace_ingest_router
    from app.routers.trace_rca import router as trace_rca_router
    from app.routers.trace_view import router as trace_view_router
    from app.routers.dtw import router as dtw_router
    from app.routers.pagerank_rca import router as pagerank_rca_router
    from app.routers.log_rca import router as log_rca_router
    from app.routers.log_anomaly import router as log_anomaly_router
    from app.routers.logs import router as logs_router
    from app.routers.auth import router as auth_router
    from app.routers.users import router as users_router
    from app.routers.roles import router as roles_router
    from app.routers.settings import router as settings_router
    from app.routers.system import router as system_router
    from app.routers.system_posture import router as system_posture_router
    from app.routers.audit import router as audit_router
    from app.routers.menu import router as menu_router
    from app.routers.license import router as license_router
    from app.routers.tenant_management import router as tenant_management_router
    from app.routers.tokens import router as tokens_router
    from app.routers.secrets_vault import router as secrets_vault_router
    from app.routers.skills import router as skills_router
    from app.routers.marketplace import router as marketplace_router
    from app.routers.multicluster import router as multicluster_router
    from app.routers.upgrade import router as upgrade_router
    from app.routers.network import router as network_router
    from app.routers.mcp import router as mcp_router
    from app.routers.git_knowledge import router as git_knowledge_router
    from app.routers.ws import router as ws_router
    from app.routers.api_v1 import router as api_v1_router
    from app.routers.mobile import router as mobile_router
    from app.routers.health_map import router as health_map_router
    from app.routers.network_test import router as network_test_router
    from app.routers.datasources import router as datasources_router
    from app.routers.es_integration import router as es_integration_router
    from app.routers.event_sources import router as event_sources_router
    from app.routers.events import router as events_router
    from app.routers.kafka_pipeline import router as kafka_pipeline_router
    from app.routers.netflow import router as netflow_router
    from app.routers.feature_store import router as feature_store_router
    from app.routers.ci_models import router as ci_models_router
    from app.routers.drain import router as drain_router
    from app.routers.granger import router as granger_router
    from app.routers.idice import router as idice_router
    from app.routers.trend_prediction import router as trend_prediction_router
    from app.routers.prediction_models import router as prediction_models_router
    from app.routers.predictions import router as predictions_router
    from app.routers.predictions_enhanced import router as predictions_enhanced_router
    from app.routers.pcadr import router as pcadr_router
    from app.routers.metrics import router as metrics_router
    from app.routers.notifications import router as notifications_router
    from app.routers.notification_templates import router as notification_templates_router
    from app.routers.correlation import router as correlation_router
    from app.routers.observability_correlation import router as observability_correlation_router
    from app.routers.script_exec import router as script_exec_router
    from app.routers.ansible import router as ansible_router
    from app.routers.change_workflow import router as change_workflow_router
    from app.routers.workflow import router as workflow_router
    from app.routers.chatops import router as chatops_router
    from app.routers.discovery import router as discovery_router
    from app.routers.diagnostic_tools import router as diagnostic_tools_router
    from app.routers.admin import router as admin_router
    from app.routers.alert_correlation import router as alert_correlation_router
    from app.routers.rag_eval import router as rag_eval_router
    from app.routers.security_audit import router as security_audit_router
    from app.routers.ai_insight import router as ai_insight_router

    app.include_router(assets_router)
    app.include_router(asset_changes_router)
    app.include_router(asset_discovery_router)
    app.include_router(lifecycle_router)
    app.include_router(topology_router)
    app.include_router(topology_path_router)
    app.include_router(topo_graph_router)
    app.include_router(tags_router)
    app.include_router(ext_cmdb_router)
    app.include_router(alerts_router)
    app.include_router(alert_console_router)
    app.include_router(alert_events_router)
    app.include_router(alert_silence_router)
    app.include_router(alert_storm_router)
    app.include_router(alert_webhooks_router)
    app.include_router(anomaly_router)
    app.include_router(cluster_anomaly_router)
    app.include_router(hotspot_router)
    app.include_router(k8s_monitor_router)
    app.include_router(k8s_resources_router)
    app.include_router(k8s_cert_router)
    app.include_router(containers_router)
    app.include_router(helm_router)
    app.include_router(blue_green_router)
    app.include_router(service_mesh_router)
    app.include_router(ai_providers_router)
    app.include_router(agent_chat_router)
    app.include_router(agent_sse_router)
    app.include_router(agent_workflow_router)
    app.include_router(agent_eval_router)
    app.include_router(agent_ground_truth_router)
    app.include_router(ab_test_router)
    app.include_router(anomaly_eval_router)
    app.include_router(sub_agents_router)
    app.include_router(im_chatops_router)
    app.include_router(edge_tunnel_router)
    app.include_router(webssh_router)
    app.include_router(sandbox_router)
    app.include_router(agent_deploy_router)
    app.include_router(agent_autonomous_router)
    app.include_router(deploy_router)
    app.include_router(offline_repo_router)
    app.include_router(k8s_offline_deploy_router)
    app.include_router(sre_router)
    app.include_router(chaos_router)
    app.include_router(inspection_router)
    app.include_router(baseline_router)
    app.include_router(remediation_router)
    app.include_router(remediation_workflow_router)
    app.include_router(remediation_effect_router)
    app.include_router(runbooks_router)
    app.include_router(knowledge_router)
    app.include_router(knowledge_documents_router)
    app.include_router(knowledge_v2_router)
    app.include_router(knowledge_graph_router)
    app.include_router(knowledge_autogen_router)
    app.include_router(smart_recommend_router)
    app.include_router(incidents_router)
    app.include_router(dashboard_router)
    app.include_router(dashboard_config_router)
    app.include_router(ops_analytics_router)
    app.include_router(reports_router)
    app.include_router(report_schedules_router)
    app.include_router(traces_router)
    app.include_router(traces_api_router)
    app.include_router(trace_anomaly_router)
    app.include_router(trace_ingest_router)
    app.include_router(trace_rca_router)
    app.include_router(trace_view_router)
    app.include_router(dtw_router)
    app.include_router(pagerank_rca_router)
    app.include_router(log_rca_router)
    app.include_router(log_anomaly_router)
    app.include_router(logs_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(settings_router)
    app.include_router(system_router)
    app.include_router(system_posture_router)
    app.include_router(audit_router)
    app.include_router(menu_router)
    app.include_router(license_router)
    app.include_router(tenant_management_router)
    app.include_router(tokens_router)
    app.include_router(secrets_vault_router)
    app.include_router(skills_router)
    app.include_router(marketplace_router)
    app.include_router(multicluster_router)
    app.include_router(upgrade_router)
    app.include_router(network_router)
    app.include_router(mcp_router)
    app.include_router(git_knowledge_router)
    app.include_router(ws_router)
    app.include_router(api_v1_router)
    app.include_router(mobile_router)
    app.include_router(health_map_router)
    app.include_router(network_test_router)
    app.include_router(datasources_router)
    app.include_router(es_integration_router)
    app.include_router(event_sources_router)
    app.include_router(events_router)
    app.include_router(kafka_pipeline_router)
    app.include_router(netflow_router)
    app.include_router(feature_store_router)
    app.include_router(ci_models_router)
    app.include_router(drain_router)
    app.include_router(granger_router)
    app.include_router(idice_router)
    app.include_router(trend_prediction_router)
    app.include_router(prediction_models_router)
    app.include_router(predictions_router)
    app.include_router(predictions_enhanced_router)
    app.include_router(pcadr_router)
    app.include_router(metrics_router)
    app.include_router(notifications_router)
    app.include_router(notification_templates_router)
    app.include_router(correlation_router)
    app.include_router(observability_correlation_router)
    app.include_router(script_exec_router)
    app.include_router(ansible_router)
    app.include_router(change_workflow_router)
    app.include_router(workflow_router)
    app.include_router(chatops_router)
    app.include_router(discovery_router)
    app.include_router(diagnostic_tools_router)
    app.include_router(admin_router)
    app.include_router(alert_correlation_router)
    app.include_router(rag_eval_router)
    app.include_router(security_audit_router)
    app.include_router(ai_insight_router)

