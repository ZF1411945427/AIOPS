"""Test full async flow"""
import sys, time, requests
sys.path.insert(0, '.')

URL = "http://localhost:8000"
FILE = r"D:\AIOPS\project07\功能测试\K8s运维故障排查手册.md"

# Login
s = requests.Session()
r = s.post(f"{URL}/login", json={"username": "admin", "password": "1234"})
token = r.json().get("token", "")
print(f"Login: ok={r.json().get('ok')}, token_len={len(token)}")

# Check initial stats
headers = {"Authorization": f"Bearer {token}"}
r = s.get(f"{URL}/knowledge/v2/stats", headers=headers)
print(f"Initial stats: {r.json()}")

# Upload one doc
t0 = time.time()
with open(FILE, "rb") as f:
    r = s.post(f"{URL}/knowledge/v2/documents/upload",
               files={"file": ("test.md", f, "text/markdown")},
               data={"title": "上传测试", "tags": "test"},
               headers=headers)
upload_time = time.time() - t0
resp = r.json()
print(f"\nUpload: {upload_time:.2f}s - ok={resp.get('ok')}, id={resp.get('id')}")

# Poll for indexing completion
doc_id = resp.get("id")
print(f"Waiting for doc {doc_id} to be indexed...")
for i in range(30):
    time.sleep(5)
    r = s.get(f"{URL}/knowledge/v2/stats", headers=headers)
    stats = r.json()
    r2 = s.get(f"{URL}/knowledge/v2/documents/{doc_id}/detail", headers=headers)
    detail = r2.json()
    doc_status = detail.get("doc", {}).get("status", "unknown")
    chunks = detail.get("doc", {}).get("chunk_count", 0)
    print(f"  [{(i+1)*5}s] status={doc_status}, chunks={chunks}, total_indexed={stats.get('indexed_docs', 0)}")
    if doc_status == "indexed":
        print(f"  DONE in {(i+1)*5}s!")
        break
