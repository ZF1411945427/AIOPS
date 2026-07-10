"""Clean test: upload 3 files, check background indexing"""
import sys, time, requests
sys.path.insert(0, '.')

# Clean old test docs
from app.database import get_session_for, get_db_mode
from app.models import KbDocument
from app.services import vector_store

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
old = db.query(KbDocument).filter(KbDocument.title.like("%K8s%排查手册%")).all()
for d in old:
    try: vector_store.delete_by_document(d.id)
    except: pass
    db.delete(d)
db.commit()
db.close()
print("Cleaned old docs")

URL = "http://localhost:8000"
FILE = r"D:\AIOPS\project07\功能测试\K8s运维故障排查手册.md"

s = requests.Session()
r = s.post(f"{URL}/login", json={"username": "admin", "password": "1234"})
token = r.json().get("token", "")
s.headers["Authorization"] = f"Bearer {token}"
print(f"Login OK")

# Upload 3 files
for i in range(3):
    t0 = time.time()
    with open(FILE, "rb") as f:
        r = s.post(f"{URL}/knowledge/v2/documents/upload",
                   files={"file": (f"K8s{i+1}.md", f, "text/markdown")},
                   data={"title": f"K8s排查手册{i+1}", "tags": "k8s"})
    elapsed = time.time() - t0
    data = r.json()
    print(f"Upload {i+1}: {elapsed:.2f}s - ok={data.get('ok')}, id={data.get('id')}")

# Wait for background indexing
print("\nWaiting 120s for background indexing...")
for check in range(12):
    time.sleep(10)
    r = s.get(f"{URL}/knowledge/v2/stats")
    stats = r.json()
    indexed = stats.get("indexed_docs", 0)
    total = stats.get("total_docs", 0)
    chunks = stats.get("total_chunks", 0)
    print(f"  [{(check+1)*10}s] indexed={indexed}/{total}, chunks={chunks}")
    if indexed >= 3:
        print("All 3 docs indexed!")
        break

# Final check
r = s.get(f"{URL}/knowledge/v2/documents/list")
data = r.json()
for doc in data.get("documents", []):
    print(f"  [{doc['id']}] {doc['title']} - status: {doc['status']}, chunks: {doc.get('chunk_count', 0)}")
