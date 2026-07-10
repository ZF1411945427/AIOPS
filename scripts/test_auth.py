"""Test upload speed - async indexing"""
import time, requests

FILE = r"D:\AIOPS\project07\功能测试\K8s运维故障排查手册.md"
URL = "http://localhost:8000"

s = requests.Session()
# Try following redirects
r = s.post(f"{URL}/auth/api/login", json={"username": "admin", "password": "admin123"}, allow_redirects=True)
print(f"Login: {r.status_code} - type={r.headers.get('content-type', '')[:50]}")
print(f"Cookies: {dict(s.cookies)}")

# Test if we can access API
r = s.get(f"{URL}/knowledge/v2/stats")
print(f"Stats: {r.status_code} - {r.text[:200]}")

r = s.get(f"{URL}/knowledge/v2/documents/list")
print(f"List: {r.status_code} - {r.text[:200]}")
