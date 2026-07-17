"""
多租户迁移脚本：创建 tenants 表 + 核心表加 tenant_id 字段
用法: python app/migrations/add_tenant_tables.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import get_all_engines
from sqlalchemy import text

TABLES_WITH_TENANT = [
    "alerts", "assets", "incidents", "chat_sessions", "chat_messages",
    "metric_records", "notification_logs", "remediation_workflows",
    "inspection_tasks", "inspection_records", "inspection_templates",
    "knowledge_base", "kb_documents", "kb_chunks", "knowledge_drafts",
    "oncall_schedules", "pending_actions", "reports", "runbooks",
    "agent_configs", "agent_evaluations", "agent_workflows",
    "tool_invocations", "mcp_servers",
]

def migrate():
    for mode, eng in get_all_engines().items():
        print(f"\n=== Migrating {mode} ===")
        with eng.connect() as conn:
            # 1. 创建 tenants 表
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenants (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(128) NOT NULL UNIQUE,
                        code VARCHAR(64) NOT NULL UNIQUE,
                        status VARCHAR(16) DEFAULT 'active',
                        quota_assets INTEGER DEFAULT 1000,
                        quota_users INTEGER DEFAULT 50,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                print(f"  [OK] tenants table")
            except Exception as e:
                print(f"  [SKIP] tenants: {e}")

            # 2. 插入默认租户
            try:
                conn.execute(text("""
                    INSERT OR IGNORE INTO tenants (id, name, code, status, quota_assets, quota_users)
                    VALUES (1, '默认租户', 'default', 'active', 10000, 1000)
                """))
                conn.commit()
                print(f"  [OK] default tenant")
            except Exception as e:
                print(f"  [SKIP] default tenant: {e}")

            # 3. 核心表加 tenant_id 字段
            for table in TABLES_WITH_TENANT:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)"))
                    conn.commit()
                    print(f"  [ADD] {table}.tenant_id")
                except Exception as e:
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        print(f"  [EXISTS] {table}.tenant_id")
                    else:
                        print(f"  [SKIP] {table}.tenant_id: {e}")

            # 4. 给现有数据设置默认 tenant_id=1
            for table in TABLES_WITH_TENANT:
                try:
                    conn.execute(text(f"UPDATE {table} SET tenant_id=1 WHERE tenant_id IS NULL"))
                    conn.commit()
                    print(f"  [SET] {table}.tenant_id=1 for existing rows")
                except Exception as e:
                    print(f"  [SKIP SET] {table}: {e}")

if __name__ == "__main__":
    migrate()
    print("\nDone.")
