import requests, json
BASE = "http://39.96.51.45:8000"
s = requests.Session()

# 1. 前端首页
r = s.get(BASE + "/", allow_redirects=False, timeout=10)
loc = r.headers.get("location", "")
print("[1] frontend / -> %d location=%s" % (r.status_code, loc))

# 2. 登录
r = s.post(BASE + "/login", json={"username":"admin","password":"admin123"}, timeout=10)
print("[2] login -> %d %s" % (r.status_code, r.text[:100]))
print("    cookies: %s" % dict(s.cookies))

# 3. 调链路追踪列表
r = s.get(BASE + "/api/traces", params={"limit":20}, timeout=10)
d = r.json()
traces = d.get("traces", [])
print("[3] /api/traces -> %d total=%s returned=%d" % (r.status_code, d.get("total"), len(traces)))
print("    services: %s" % d.get("services"))
print("    前5条 trace:")
for i, t in enumerate(traces[:5]):
    tid = t["trace_id"][:24]
    print("      %d. %s... %s/%s %s spans=%s dur=%sms" % (
        i, tid, t["root_service"], t["root_operation"], t["start_time"], t["span_count"], t["total_duration_ms"]))

# 4. 接入指引状态
r = s.get(BASE + "/api/v1/traces/ingest-status", timeout=10)
st = r.json()
print("[4] ingest-status -> total_spans=%s total_traces=%s services=%d" % (
    st["total_spans"], st["total_traces"], len(st["services"])))
print("    latest_span_time=%s" % st["latest_span_time"])
print("    demo services present: %s" % [x for x in st["services"] if "demo" in x])
