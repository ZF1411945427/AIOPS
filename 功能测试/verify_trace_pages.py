"""验证两个功能页面的 API: 接入指引 + 链路追踪"""
import requests, json

BASE = "http://127.0.0.1:8000"
s = requests.Session()

# 1. 登录
r = s.post(f"{BASE}/login", json={"username": "admin", "password": "admin123"}, timeout=10)
print(f"[login] status={r.status_code} body={r.text[:200]}")
print(f"[login] cookies={dict(s.cookies)}")
print()

# 2. 接入指引页 API: ingest-status
r = s.get(f"{BASE}/api/v1/traces/ingest-status", timeout=10)
st = r.json()
print(f"[ingest-status] total_spans={st['total_spans']} total_traces={st['total_traces']}")
print(f"[ingest-status] services({len(st['services'])}): {st['services']}")
print(f"[ingest-status] latest_span_time={st['latest_span_time']}")
print(f"[ingest-status] otlp_endpoint={st['otlp_endpoint']}")
print()

# 3. 接入指引页 API: agent-guide
r = s.get(f"{BASE}/api/v1/traces/agent-guide", timeout=10)
g = r.json()
print(f"[agent-guide] otlp_endpoint={g.get('otlp_endpoint')}")
print(f"[agent-guide] guide types({len(g.get('guides',{}))}): {list(g.get('guides',{}).keys())}")
for k, v in g.get("guides", {}).items():
    print(f"  - {k}: {v.get('title')} ({v.get('type')}) -> {len(v.get('steps',[]))} steps")
print()

# 4. 链路追踪页 API: 列表(筛选 demo-frontend)
r = s.get(f"{BASE}/api/traces", params={"service": "demo-frontend", "limit": 10}, timeout=10)
d = r.json()
print(f"[trace-list] total={d['total']} services({len(d['services'])}): {d['services']}")
print(f"[trace-list] demo-frontend traces: {len(d['traces'])}")
for t in d["traces"]:
    print(f"  - {t['trace_id'][:24]}... root={t['root_service']}/{t['root_operation']} spans={t['span_count']} dur={t['total_duration_ms']}ms status={t['worst_status']}")
print()

# 5. 链路追踪页 API: 单条 trace 详情(取第一条 demo trace)
if d["traces"]:
    tid = d["traces"][0]["trace_id"]
    r = s.get(f"{BASE}/api/traces/{tid}", timeout=10)
    td = r.json()
    print(f"[trace-detail] trace_id={tid[:24]}... total_spans={td['total_spans']} root_dur={td['root_duration_ms']}ms")
    print(f"[trace-detail] services: {td['services']}")
    print(f"[trace-detail] topology edges: {td['topology']['edges']}")
    print(f"[trace-detail] spans ({len(td['spans'])}):")
    for sp in td["spans"]:
        parent = sp["parent_span_id"][:8] if sp["parent_span_id"] else "ROOT"
        print(f"  - {sp['span_id'][:8]} parent={parent} {sp['service_name']}/{sp['operation_name']} dur={sp['duration_ms']}ms status={sp['status']}")
