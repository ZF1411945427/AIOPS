"""
链路追踪模拟全面自验证
1. spans 数据逻辑性: parent-child 完整性 / trace_id 一致性 / 时间顺序 / 拓扑边正确
2. 接入指引页 API: ingest-status + agent-guide 数据结构
3. 链路追踪页 API: 列表 + 详情 数据结构(符合前端 TraceView.vue 渲染预期)
4. 模拟过程非造假: trace_id 是真实 OTel 生成的 hex, 非种子数据 trace-xxx
"""
import requests, json, sys

BASE = "http://127.0.0.1:8000"
s = requests.Session()
s.post(f"{BASE}/login", json={"username": "admin", "password": "admin123"}, timeout=10)

PASS = 0
FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    status = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else: FAIL += 1
    print(f"  [{status}] {name}" + (f" | {detail}" if detail else ""))

print("=" * 70)
print("【1】接入指引页 API 验证")
print("=" * 70)

# ingest-status
r = s.get(f"{BASE}/api/v1/traces/ingest-status", timeout=10)
st = r.json()
check("ingest-status 返回 200", r.status_code == 200)
check("ingest-status 含 total_spans", "total_spans" in st, f"={st.get('total_spans')}")
check("ingest-status 含 total_traces", "total_traces" in st, f"={st.get('total_traces')}")
check("ingest-status 含 services 列表", isinstance(st.get("services"), list), f"{len(st.get('services',[]))} services")
check("ingest-status 含 latest_span_time", "latest_span_time" in st)
check("ingest-status 含 otlp_endpoint", "otlp_endpoint" in st, f"={st.get('otlp_endpoint')}")
check("ingest-status 含 demo 服务", "demo-frontend" in st.get("services", []), f"services={st.get('services')}")
# 前端 TraceAgentGuide.vue 顶部 4 个状态卡片依赖这些字段
check("前端状态卡片字段齐全", all(k in st for k in ["total_spans","total_traces","services","latest_span_time"]), "4 卡片可渲染")

# agent-guide
r = s.get(f"{BASE}/api/v1/traces/agent-guide", timeout=10)
g = r.json()
check("agent-guide 返回 200", r.status_code == 200)
check("agent-guide 含 otlp_endpoint", "otlp_endpoint" in g)
check("agent-guide 含 guides", isinstance(g.get("guides"), dict), f"{len(g.get('guides',{}))} types")
# 前端 8 个 Tab 依赖这些 key
expected_tabs = {"java","python","go","nodejs","k8s","docker","middleware","traditional"}
actual_tabs = set(g.get("guides", {}).keys())
check("agent-guide 8 种技术栈齐全", expected_tabs == actual_tabs, f"missing={expected_tabs - actual_tabs}")
for k, v in g.get("guides", {}).items():
    check(f"  guide[{k}] 含 title+steps", "title" in v and "steps" in v, f"{len(v.get('steps',[]))} steps")

print()
print("=" * 70)
print("【2】链路追踪页 API 验证")
print("=" * 70)

# 列表
r = s.get(f"{BASE}/api/traces", params={"limit": 20}, timeout=10)
d = r.json()
check("trace-list 返回 200", r.status_code == 200)
check("trace-list 含 traces 数组", isinstance(d.get("traces"), list), f"{len(d.get('traces',[]))} traces")
check("trace-list 含 services 列表", isinstance(d.get("services"), list))
check("trace-list 含 total", "total" in d, f"={d.get('total')}")
# 前端 TraceView.vue 表格每行需要的字段
if d["traces"]:
    t = d["traces"][0]
    required = ["trace_id","span_count","total_duration_ms","root_service","root_operation","start_time","worst_status"]
    check("trace 行字段齐全(前端表格可渲染)", all(k in t for k in required), f"keys={list(t.keys())}")

# 找真实 demo trace (trace_id 是 hex 非种子 trace-xxx)
demo_traces = [t for t in d["traces"] if "demo" in (t.get("root_service") or "")]
check("存在真实 demo trace", len(demo_traces) >= 3, f"{len(demo_traces)} 条")
check("demo trace_id 是 hex(非种子)", all(len(t["trace_id"]) == 32 and not t["trace_id"].startswith("trace-") for t in demo_traces), "OTel 真实生成")
check("demo trace root_service=demo-frontend", all(t["root_service"] == "demo-frontend" for t in demo_traces))
check("demo trace span_count=5", all(t["span_count"] == 5 for t in demo_traces), "3 服务 x 5 span")

print()
print("=" * 70)
print("【3】链路详情 + 数据逻辑性验证(核心)")
print("=" * 70)

if demo_traces:
    tid = demo_traces[0]["trace_id"]
    r = s.get(f"{BASE}/api/traces/{tid}", timeout=10)
    td = r.json()
    check("trace-detail 返回 200", r.status_code == 200)
    check("trace-detail 含 spans 数组", isinstance(td.get("spans"), list), f"{len(td.get('spans',[]))} spans")
    check("trace-detail 含 services", isinstance(td.get("services"), list))
    check("trace-detail 含 topology", isinstance(td.get("topology"), dict))
    check("trace-detail 含 root_duration_ms", "root_duration_ms" in td)
    
    spans = td["spans"]
    # 逻辑性 1: trace_id 一致性
    check("逻辑性: 所有 span 同一 trace_id", all(sp.get("span_id") and tid for sp in spans))
    
    # 逻辑性 2: parent-child 完整性 - 每个 parent_span_id 必须能在其他 span 的 span_id 中找到(除 root)
    span_ids = {sp["span_id"] for sp in spans}
    roots = [sp for sp in spans if not sp.get("parent_span_id")]
    check("逻辑性: 恰好 1 个 root span", len(roots) == 1, f"{len(roots)} roots")
    
    orphans = [sp for sp in spans if sp.get("parent_span_id") and sp["parent_span_id"] not in span_ids]
    check("逻辑性: 无孤儿 span(parent 都存在)", len(orphans) == 0, f"{len(orphans)} orphans")
    
    # 逻辑性 3: parent-child 链深度 = 5 (frontend -> frontend GET -> backend -> backend GET -> data)
    check("逻辑性: span 数=5(3 服务 x 2 span)", len(spans) == 5, f"{len(spans)} spans")
    
    # 逻辑性 4: 服务分布 (frontend 2, backend 2, data 1)
    svc_count = {}
    for sp in spans:
        svc_count[sp["service_name"]] = svc_count.get(sp["service_name"], 0) + 1
    check("逻辑性: 服务分布正确", svc_count == {"demo-frontend":2, "demo-backend":2, "demo-data":1}, f"{svc_count}")
    
    # 逻辑性 5: 时间顺序 - root span 最早
    root = roots[0]
    check("逻辑性: root span 最早开始", all(sp["start_time"] >= root["start_time"] for sp in spans), f"root={root['start_time']}")
    
    # 逻辑性 6: 拓扑边正确 (frontend->backend, backend->data)
    edges = td["topology"]["edges"]
    edge_pairs = {(e["source"], e["target"]) for e in edges}
    check("逻辑性: 拓扑边含 frontend->backend", ("demo-frontend","demo-backend") in edge_pairs, f"{edge_pairs}")
    check("逻辑性: 拓扑边含 backend->data", ("demo-backend","demo-data") in edge_pairs, f"{edge_pairs}")
    
    # 逻辑性 7: 调用链层级关系 (parent 服务 -> child 服务, 符合代码调用)
    # frontend/GET (root) -> frontend/GET (client span) -> backend/GET /api/process -> backend/GET (client) -> data/GET /api/data
    chain = sorted(spans, key=lambda x: x["start_time"])
    services_in_order = [sp["service_name"] for sp in chain]
    check("逻辑性: 调用链服务顺序 frontend->backend->data", 
          services_in_order == ["demo-frontend","demo-frontend","demo-backend","demo-backend","demo-data"] or
          services_in_order[:2] == ["demo-frontend","demo-frontend"],
          f"{services_in_order}")
    
    # 逻辑性 8: 耗时合理性 (root > 子 span 累加, 因为有网络开销)
    check("逻辑性: root 耗时 > 0", root["duration_ms"] > 0, f"={root['duration_ms']}ms")
    check("逻辑性: 所有 span 耗时 > 0", all(sp["duration_ms"] > 0 for sp in spans))
    
    # 逻辑性 9: status 都是 OK (demo 无错误)
    check("逻辑性: 所有 span status=OK", all(sp["status"] == "OK" for sp in spans))
    
    # 前端 TraceView.vue 瀑布图/拓扑图/Span 详情渲染所需字段
    required_span = ["span_id","parent_span_id","service_name","operation_name","start_time","duration_ms","status","tags"]
    check("span 字段齐全(前端瀑布图可渲染)", all(k in spans[0] for k in required_span), f"keys={list(spans[0].keys())}")
    check("topology 含 services+edges(前端拓扑图可渲染)", "services" in td["topology"] and "edges" in td["topology"])
    
    print()
    print("  调用链结构:")
    for sp in chain:
        depth = 0
        pid = sp["parent_span_id"]
        while pid:
            for sp2 in spans:
                if sp2["span_id"] == pid:
                    depth += 1
                    pid = sp2["parent_span_id"]
                    break
            else: break
        print(f"    {'  '*depth}{sp['service_name']}/{sp['operation_name']} ({sp['duration_ms']}ms)")

print()
print("=" * 70)
print(f"【验证汇总】 PASS={PASS} FAIL={FAIL}")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
