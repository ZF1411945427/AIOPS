"""Check indexing status"""
import requests

URL = "http://localhost:8000"
s = requests.Session()
r = s.post(f"{URL}/login", json={"username": "admin", "password": "1234"})
token = r.json().get("token", "")
s.headers["Authorization"] = f"Bearer {token}"

r = s.get(f"{URL}/knowledge/v2/documents/list")
data = r.json()
for doc in data.get("documents", []):
    print(f"  [{doc['id']}] {doc['title']} - status: {doc['status']}, chunks: {doc.get('chunk_count', 0)}")

r = s.get(f"{URL}/knowledge/v2/stats")
print(f"\nStats: {r.json()}")
