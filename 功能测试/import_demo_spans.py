"""把服务器3导出的 demo spans 导入本地数据库"""
import sqlite3, json, os
from datetime import datetime

DB_PATH = r"E:\AIOPS\project04\db\aiops.db"
JSON_PATH = r"E:\AIOPS\project04\功能测试\demo_spans_export.json"

with open(JSON_PATH, "r", encoding="utf-8") as f:
    spans = json.load(f)

print(f"loaded {len(spans)} demo spans from export")

db = sqlite3.connect(DB_PATH)
cur = db.cursor()

# 检查已有的 demo spans（避免重复导入）
cur.execute("SELECT COUNT(*) FROM spans WHERE service_name LIKE 'demo-%'")
existing = cur.fetchone()[0]
print(f"existing demo spans in local db: {existing}")

if existing > 0:
    print("demo spans already exist, skipping import")
else:
    inserted = 0
    for sp in spans:
        # 解析时间字符串
        start_time = sp["start_time"]
        end_time = sp["end_time"]
        # 去重检查
        cur.execute("SELECT id FROM spans WHERE trace_id=? AND span_id=?", (sp["trace_id"], sp["span_id"]))
        if cur.fetchone():
            continue
        cur.execute("""INSERT INTO spans (trace_id, span_id, parent_span_id, service_name, operation_name,
            start_time, end_time, duration_ms, status, tags, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sp["trace_id"], sp["span_id"], sp.get("parent_span_id",""), sp["service_name"],
             sp["operation_name"], start_time, end_time, sp["duration_ms"], sp["status"],
             sp.get("tags","{}"), sp.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))))
        inserted += 1
    db.commit()
    print(f"inserted {inserted} demo spans into local db")

# 验证
cur.execute("SELECT service_name, COUNT(*) FROM spans GROUP BY service_name")
rows = cur.fetchall()
print("\nlocal db services after import:")
for r in rows:
    print(f"  {r[0]}: {r[1]}")
cur.execute("SELECT COUNT(*) FROM spans")
print(f"total spans: {cur.fetchone()[0]}")
db.close()
