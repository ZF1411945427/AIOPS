"""验证链路追踪页面 API: 列表(不带筛选) + 详情"""
import requests, json

BASE = "http://127.0.0.1:8000"
s = requests.Session()
s.post(f"{BASE}/login", json={"username": "admin", "password": "admin123"}, timeout=10)

# 列表(不带筛选, 看全部 15 条 trace)
r = s.get(f"{BASE}/api/traces", params={"limit": 20}, timeout=10)
d = r.json()
print(f"[trace-list] total={d['total']} returned={len(d['traces'])}")
print(f"[trace-list] services({len(d['services'])}): {d['services']}")
print("[trace-list] traces:")
for t in d["traces"]:
    print(f"  - {t['trace_id'][:24]}... root={t['root_service']}/{t['root_operation']} spans={t['span_count']} dur={t['total_duration_ms']}ms status={t['worst_status']} time={t['start_time']}")
print()

# 找 demo trace 的 trace_id (从列表中找 root_service=demo-frontend 的)
demo_traces = [t for t in d["traces"] if "demo" in (t.get("root_service") or "")]
print(f"[demo traces] found {len(demo_traces)} demo traces")
if demo_traces:
    tid = demo_traces[0]["trace_id"]
    print(f"[demo traces] using trace_id={tid}")
else:
    # fallback: 用已知的 demo trace_id
    tid = "e655a15ffe553ea096fb53b9664e6e0b"
    print(f"[demo traces] fallback trace_id={tid}")

# 详情
r = s.get(f"{BASE}/api/traces/{tid}", timeout=10)
td = r.json()
print(f"\n[trace-detail] trace_id={tid[:24]}... total_spans={td['total_spans']} root_dur={td['root_duration_ms']}ms")
print(f"[trace-detail] services: {td['services']}")
print(f"[trace-detail] topology edges: {td['topology']['edges']}")
print(f"[trace-detail] spans ({len(td['spans'])}):")
for sp in td["spans"]:
    parent = sp["parent_span_id"][:8] if sp["parent_span_id"] else "ROOT"
    print(f"  - {sp['span_id'][:8]} parent={parent} {sp['service_name']}/{sp['operation_name']} dur={sp['duration_ms']}ms status={sp['status']}")
