"""
给 users 表添加 tenant_id 字段，关联到 tenants 表
用法: python app/migrations/add_user_tenant.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import get_all_engines
from sqlalchemy import text

def migrate():
    for mode, eng in get_all_engines().items():
        print(f"\n=== Migrating {mode} ===")
        with eng.connect() as conn:
            # 1. 添加 tenant_id 列
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)"))
                conn.commit()
                print(f"  [ADD] users.tenant_id")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  [EXISTS] users.tenant_id")
                else:
                    print(f"  [SKIP] users.tenant_id: {e}")

            # 2. 给现有用户设置默认 tenant_id=1
            try:
                conn.execute(text("UPDATE users SET tenant_id=1 WHERE tenant_id IS NULL"))
                conn.commit()
                print(f"  [SET] users.tenant_id=1 for existing users")
            except Exception as e:
                print(f"  [SKIP SET] users: {e}")

if __name__ == "__main__":
    migrate()
    print("\nDone.")
