"""
给 pending_actions 表添加 alert_id 字段，关联到 alerts 表
用法: python app/migrations/add_pending_action_alert_id.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import get_all_engines
from sqlalchemy import text

def migrate():
    for mode, eng in get_all_engines().items():
        print(f"\n=== Migrating {mode} ===")
        with eng.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE pending_actions ADD COLUMN alert_id INTEGER REFERENCES alerts(id)"))
                conn.commit()
                print(f"  [ADD] pending_actions.alert_id")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  [EXISTS] pending_actions.alert_id")
                else:
                    print(f"  [SKIP] pending_actions.alert_id: {e}")

if __name__ == "__main__":
    migrate()
    print("\nDone.")