"""Test upload with bge-small-zh model"""
import time, requests

URL = "http://localhost:8000"
FILE = r"D:\AIOPS\project07\功能测试\K8s运维故障排查手册.md"

s = requests.Session()
r = s.post(f"{URL}/login", json={"username": "admin", "password": "1234"})
token = r.json().get("token", "")
headers = {"Authorization": f"Bearer {token}"}

# Check model info
r = s.get(f"{URL}/knowledge/v2/stats", headers=headers)
print(f"Stats: {r.json()}")

# Upload 1 (first time, model loads)
t0 = time.time()
with open(FILE, "rb") as f:
    r = s.post(f"{URL}/knowledge/v2/documents/upload",
               files={"file": ("test.md", f, "text/markdown")},
               data={"title": "小模型测试1", "tags": "test"},
               headers=headers)
upload_time = time.time() - t0
doc_id = r.json().get("id")
print(f"\nUpload 1: {upload_time:.2f}s (API response)")

# Wait for background indexing
print("Waiting for indexing...")
for i in range(30):
    time.sleep(3)
    r = s.get(f"{URL}/knowledge/v2/documents/{doc_id}/detail", headers=headers)
    detail = r.json()
    status = detail.get("doc", {}).get("status", "?")
    chunks = detail.get("doc", {}).get("chunk_count", 0)
    print(f"  [{(i+1)*3}s] status={status}, chunks={chunks}")
    if status == "indexed":
        total = time.time() - t0
        print(f"\nDONE! Total: {total:.1f}s (upload: {upload_time:.2f}s + indexing: {total-upload_time:.1f}s)")
        break
