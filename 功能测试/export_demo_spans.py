import sqlite3, json
db = sqlite3.connect("/data/AIOPS/db/aiops.db")
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.execute("SELECT * FROM spans WHERE service_name LIKE 'demo-%' ORDER BY start_time")
rows = [dict(r) for r in cur.fetchall()]
print(json.dumps(rows, default=str, ensure_ascii=False))
