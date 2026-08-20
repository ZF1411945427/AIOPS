"""register runtime-compat columns as formal alembic revision

将 app/main.py 中 _MIGRATIONS 的幂等补列收敛为正式 alembic 迁移版本,
alembic 版本树真正前进, 与运行时 create_all + _MIGRATIONS 兜底双轨兼容。

该脚本对"已存在列"幂等跳过(inspector 检查), 因此:
  - 全新库 (create_all 已建全列): 全部跳过, 仅标记版本
  - 旧库 (缺列): 逐列补上
  - PG / SQLite 双方言均可执行

Revision ID: a1b2c3d4e5f6
Revises: 49a88c9920b7
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '49a88c9920b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── 与 app/main.py _MIGRATIONS 保持同步的唯一数据源 ──────────────
# 新增补充列时: 两边同步追加(本脚本 + main.py), 并用 tools/check_migrations.py 校验
_MIGRATION_COLUMNS: dict[str, list[str]] = {
    "pending_actions": [
        "reason VARCHAR(500)",
        "run_id INTEGER",
        "node_run_id INTEGER",
        "review_result TEXT DEFAULT ''",
    ],
    "agent_workflow_node_runs": [
        "requires_confirm BOOLEAN DEFAULT 0",
        "pending_action_id INTEGER",
    ],
    "agent_workflow_runs": [
        "triggered_by VARCHAR(64)",
    ],
    "oncall_schedules": [
        "is_auto_rotate BOOLEAN DEFAULT 0",
        "holidays TEXT DEFAULT '[]'",
    ],
    "chaos_runs": [
        "is_auto_recovered BOOLEAN DEFAULT 0",
    ],
    "inspection_records": [
        "triggered_by_alert_id INTEGER",
    ],
    "knowledge_base": [
        "source_type VARCHAR(32) DEFAULT 'manual'",
        "sop_steps TEXT DEFAULT '[]'",
        "version_number INTEGER DEFAULT 1",
        "change_log TEXT DEFAULT ''",
    ],
    "knowledge_drafts": [
        "source_type VARCHAR(32) DEFAULT 'auto'",
        "reject_reason TEXT DEFAULT ''",
        "sop_steps TEXT DEFAULT '[]'",
    ],
    "alert_rules": [
        "kind VARCHAR(24) DEFAULT 'metric_raw'",
        "config_json TEXT DEFAULT '{}'",
    ],
    "incidents": [
        "approver_id INTEGER",
        "review_comment TEXT DEFAULT ''",
        "impact VARCHAR(32) DEFAULT 'high'",
        "description TEXT DEFAULT ''",
    ],
    "users": [
        "role_id INTEGER",
    ],
    "chat_sessions": [
        "provider_id INTEGER",
        "mode VARCHAR(16) DEFAULT 'agent'",
        "linked_asset_ids TEXT DEFAULT '[]'",
        "sub_agent VARCHAR(64) DEFAULT 'auto'",
    ],
    "notification_channels": [
        "bidirectional BOOLEAN DEFAULT 0",
        "callback_token VARCHAR(128) DEFAULT ''",
        "callback_secret VARCHAR(128) DEFAULT ''",
        "default_sub_agent VARCHAR(64) DEFAULT 'auto'",
    ],
    "assets": [
        "edge_agent_id VARCHAR(64) DEFAULT ''",
        "online_since DATETIME",
    ],
    "alerts": [
        "archived BOOLEAN DEFAULT 0",
        "last_notified_at DATETIME",
    ],
    "trace_anomaly_configs": [
        "check_window_minutes INTEGER DEFAULT 30",
    ],
    "audit_logs": [
        "route_path VARCHAR(256) DEFAULT ''",
    ],
    "diagnosis_reports": [
        "round_num INTEGER DEFAULT 0",
    ],
    "remediation_logs": [
        "remediation_type VARCHAR(16) DEFAULT 'rule'",
    ],
    "remediation_effects": [
        "remediation_type VARCHAR(16) DEFAULT 'rule'",
    ],
    "deploy_plans": [
        "environment_probe_json TEXT DEFAULT '{}'",
        "env_analysis_json TEXT DEFAULT '{}'",
        "deploy_report_json TEXT DEFAULT '{}'",
        "test_results_json TEXT DEFAULT '{}'",
        "execution_history_json TEXT DEFAULT '[]'",
        "cleanup_history_json TEXT DEFAULT '[]'",
        "last_deployed_at DATETIME",
        "deploy_count INTEGER DEFAULT 0",
        "dag_json TEXT DEFAULT '{}'",
        "ai_decision_log_json TEXT DEFAULT '[]'",
        "strategy VARCHAR(32) DEFAULT 'auto'",
        "risk_score INTEGER DEFAULT 0",
        "health_gate_json TEXT DEFAULT '[]'",
        "deployment_feature_json TEXT DEFAULT '{}'",
        "artifact_download_path VARCHAR(512) DEFAULT ''",
        "artifact_auto_download BOOLEAN DEFAULT 1",
        "use_offline BOOLEAN DEFAULT 0",
        "http_proxy VARCHAR(256) DEFAULT ''",
        "https_proxy VARCHAR(256) DEFAULT ''",
        "no_proxy VARCHAR(512) DEFAULT ''",
    ],
    "deploy_steps": [
        "diagnosis TEXT DEFAULT ''",
        "fix_command TEXT DEFAULT ''",
        "retry_count INTEGER DEFAULT 0",
        "precheck_result TEXT DEFAULT ''",
    ],
    "metric_dashboard_cards": [
        "user_id INTEGER DEFAULT 0",
        "hours INTEGER DEFAULT 24",
        "w INTEGER DEFAULT 2",
        "h INTEGER DEFAULT 1",
        "order INTEGER DEFAULT 0",
    ],
    "chat_messages": [
        "sub_agent VARCHAR(64) DEFAULT ''",
    ],
    "k8s_cluster_plans": [
        "http_proxy VARCHAR(256) DEFAULT ''",
        "https_proxy VARCHAR(256) DEFAULT ''",
        "no_proxy VARCHAR(512) DEFAULT ''",
        "untaint_master BOOLEAN DEFAULT 0",
    ],
    "sandbox_policies": [
        "allowed_workdirs TEXT DEFAULT '[]'",
    ],
    "component_installs": [
        "report_json TEXT DEFAULT ''",
        "deploy_params TEXT DEFAULT '{}'",
    ],
    "component_catalog": [
        "param_schema TEXT DEFAULT '[]'",
    ],
}


def _col_for(col_def: str) -> "sa.Column":
    """解析列定义字符串为 sqlalchemy Column, 保留类型与 DEFAULT 语义。"""
    # 拆出列名与其后定义
    parts = col_def.split(maxsplit=1)
    name = parts[0]
    tail = parts[1] if len(parts) > 1 else ""
    # 提取类型: DEFAULT 关键字之前是类型
    type_sql = tail.split(" DEFAULT")[0].strip() if "DEFAULT" in tail else tail.strip()
    type_map = {
        "INTEGER": sa.Integer(),
        "BOOLEAN": sa.Boolean(),
        "DATETIME": sa.DateTime(),
        "VARCHAR(500)": sa.String(500),
        "VARCHAR(256)": sa.String(256),
        "VARCHAR(128)": sa.String(128),
        "VARCHAR(64)": sa.String(64),
        "VARCHAR(32)": sa.String(32),
        "VARCHAR(24)": sa.String(24),
        "VARCHAR(16)": sa.String(16),
        "VARCHAR(512)": sa.String(512),
    }
    col_type = type_map.get(type_sql.upper(), sa.Text())
    server_default = None
    if "DEFAULT" in tail:
        raw = tail.split(" DEFAULT", 1)[1].strip()
        server_default = sa.text(raw)
    return sa.Column(name, col_type, server_default=server_default)


def _existing_columns(bind, table: str) -> set[str]:
    """返回表当前已有列名集合; 表不存在则返回空集(create_all 会负责建表)。"""
    insp = reflection.Inspector.from_engine(bind)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    """逐表补列(alembic 正式版本), 已存在列幂等跳过。"""
    bind = op.get_bind()
    for table, col_defs in _MIGRATION_COLUMNS.items():
        existing = _existing_columns(bind, table)
        missing = [cd for cd in col_defs if cd.split(maxsplit=1)[0] not in existing]
        for col_def in missing:
            op.add_column(table, _col_for(col_def))


def downgrade() -> None:
    """回滚: 移除此版本补充的列(仅移除本版本新增列, 保守起见仅删缺失补齐的列)。"""
    # 反向: 数据安全考虑, downgrade 默认保留列, 只回滚版本号。如需真删列走独立迁移。
    pass