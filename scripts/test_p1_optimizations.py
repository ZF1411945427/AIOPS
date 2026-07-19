"""P1 优化任务端到端测试

测试项：
- 任务#4: /api/admin/domains 领域清单
- 任务#5: /ai/api/providers/health 健康度看板 + 熔断器
- 任务#6: /api/admin/background-tasks 后台任务看板 + 触发 + 暂停
- 任务#7: bundle 体积报告
"""

import json
import os
import sys
import urllib.request
import http.cookiejar

BASE = "http://127.0.0.1:8000"

# Windows UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)), cj


def login(op):
    data = json.dumps({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/login", data=data, headers={"Content-Type": "application/json"})
    r = op.open(req, timeout=10)
    body = json.loads(r.read())
    return body.get("ok") is True


def call(op, method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        r = op.open(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"error": "non-json"}
    except Exception as e:
        return 0, {"error": str(e)}


def main():
    op, _ = make_opener()
    if not login(op):
        print("[FAIL] 登录失败")
        sys.exit(1)
    print("[OK] 登录成功\n")

    results = []

    # ── 任务#4: 领域清单 ──
    print("=" * 60)
    print("任务#4: 路由领域分包 (/api/admin/domains)")
    print("=" * 60)
    code, data = call(op, "GET", "/api/admin/domains")
    print(f"GET /api/admin/domains -> {code}")
    if code == 200 and data.get("domains"):
        print(f"  域数量: {data.get('total_domains')}")
        print(f"  路由总数: {data.get('total_routers')}")
        for d in data["domains"]:
            print(f"  - {d['key']:<12} {d['label']:<10} {d['router_count']:>3} 个路由  {d['description'][:40]}")
        results.append(("任务#4 领域清单", True, f"{data.get('total_domains')} 域 / {data.get('total_routers')} 路由"))
    else:
        print(f"  FAIL: {data}")
        results.append(("任务#4 领域清单", False, str(data)))

    # 单个域详情
    code, data = call(op, "GET", "/api/admin/domains/assets")
    print(f"\nGET /api/admin/domains/assets -> {code}")
    if code == 200 and data.get("domain"):
        d = data["domain"]
        print(f"  域: {d['key']} | {d['label']} | 路由: {d['routers']}")
        results.append(("任务#4 单域详情", True, d["key"]))
    else:
        results.append(("任务#4 单域详情", False, str(data)))

    # 不存在的域
    code, data = call(op, "GET", "/api/admin/domains/nonexistent")
    print(f"GET /api/admin/domains/nonexistent -> {code} (预期 200 + warning)")
    results.append(("任务#4 不存在域兜底", code == 200 and "warning" in data, str(data)[:80]))

    # ── 任务#5: AI Provider 健康度 ──
    print("\n" + "=" * 60)
    print("任务#5: AI Provider 健康度 + 熔断器")
    print("=" * 60)
    code, data = call(op, "GET", "/ai/api/providers/health")
    print(f"GET /ai/api/providers/health -> {code}")
    if code == 200:
        print(f"  总数: {data.get('total')}")
        print(f"  closed: {data.get('closed_count')} | open: {data.get('opened_count')} | half_open: {data.get('half_open_count')}")
        if data.get("providers"):
            for p in data["providers"][:3]:
                h = p.get("health", {})
                print(f"  - #{p['id']} {p['name']:<20} state={h.get('state'):<10} success_rate={h.get('success_rate')} p95={h.get('p95_latency_ms')}ms")
        results.append(("任务#5 健康度看板", True, f"{data.get('total')} providers"))
    else:
        results.append(("任务#5 健康度看板", False, str(data)))

    # 重置单个熔断器（用 provider id=1，不存在则跳过）
    code, data = call(op, "GET", "/ai/api/providers")
    if code == 200 and data.get("providers"):
        pid = data["providers"][0]["id"]
        code2, data2 = call(op, "POST", f"/ai/api/providers/{pid}/reset-breaker")
        print(f"POST /ai/api/providers/{pid}/reset-breaker -> {code2} {data2.get('status')}")
        results.append(("任务#5 重置单熔断器", code2 == 200 and data2.get("status") == "ok", str(data2)[:80]))

    # 重置所有熔断器
    code, data = call(op, "POST", "/ai/api/providers/reset-all-breakers")
    print(f"POST /ai/api/providers/reset-all-breakers -> {code} {data.get('status')}")
    results.append(("任务#5 重置所有熔断器", code == 200 and data.get("status") == "ok", str(data)[:80]))

    # ── 任务#6: 后台任务看板 ──
    print("\n" + "=" * 60)
    print("任务#6: 后台任务看板")
    print("=" * 60)
    # 等待 15 秒让 background_loop 至少跑一轮
    print("等待 12 秒让后台任务至少跑一轮...")
    import time
    time.sleep(12)

    code, data = call(op, "GET", "/api/admin/background-tasks")
    print(f"GET /api/admin/background-tasks -> {code}")
    if code == 200 and data.get("tasks"):
        print(f"  任务数: {data.get('total')}")
        print(f"  运行中: {data.get('running_count')} | 失败: {data.get('failed_count')}")
        print(f"  轮询周期: {data.get('interval_seconds')}s")
        for t in data["tasks"][:5]:
            print(f"  - {t['name']:<20} 状态={t['last_status']:<10} 耗时={t['last_duration_ms']}ms 成功={t['success_count']} 失败={t['failure_count']}")
        results.append(("任务#6 任务看板", True, f"{data.get('total')} 任务"))
    else:
        print(f"  返回: {data}")
        results.append(("任务#6 任务看板", code == 200, str(data)[:100]))

    # 健康摘要
    code, data = call(op, "GET", "/api/admin/background-tasks/health")
    print(f"\nGET /api/admin/background-tasks/health -> {code}")
    if code == 200 and not data.get("warning"):
        print(f"  总任务: {data.get('total_tasks')} | 失败: {data.get('failed_count')} | 暂停: {data.get('disabled_count')}")
        print(f"  平均耗时: {data.get('avg_duration_ms')}ms | 最慢: {data.get('slowest_task')}")
        results.append(("任务#6 健康摘要", True, f"avg={data.get('avg_duration_ms')}ms"))
    else:
        results.append(("任务#6 健康摘要", False, str(data)[:80]))

    # 触发任务（用 alert_check，应该快速完成）
    code, data = call(op, "POST", "/api/admin/background-tasks/alert_check/trigger")
    print(f"\nPOST /api/admin/background-tasks/alert_check/trigger -> {code}")
    print(f"  返回: {data}")
    results.append(("任务#6 手动触发", code == 200 and data.get("ok") is True, str(data)[:80]))

    # 暂停任务
    code, data = call(op, "POST", "/api/admin/background-tasks/alert_check/pause")
    print(f"POST /api/admin/background-tasks/alert_check/pause -> {code}")
    print(f"  返回: {data}")
    results.append(("任务#6 暂停任务", code == 200 and data.get("ok") is True, str(data)[:80]))

    # 恢复任务
    code, data = call(op, "POST", "/api/admin/background-tasks/alert_check/pause")
    print(f"POST /api/admin/background-tasks/alert_check/pause (再切回) -> {code}")
    print(f"  返回: {data}")
    results.append(("任务#6 恢复任务", code == 200 and data.get("ok") is True and data.get("enabled") is True, str(data)[:80]))

    # 触发不存在的任务
    code, data = call(op, "POST", "/api/admin/background-tasks/nonexistent_task/trigger")
    print(f"\nPOST /api/admin/background-tasks/nonexistent_task/trigger -> {code} (预期失败)")
    results.append(("任务#6 不存在任务兜底", code == 200 and data.get("ok") is False, str(data)[:80]))

    # ── 任务#7: bundle 体积 ──
    print("\n" + "=" * 60)
    print("任务#7: 前端首屏体积")
    print("=" * 60)
    bundle_path = "frontend/dist/bundle-size.json"
    if os.path.exists(bundle_path):
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        print(f"  首 chunk 数: {bundle['total_chunks']}")
        print(f"  首屏 gzip: {bundle['first_screen_gzip_kb']} KB (阈值 500 KB)")
        print(f"  是否达标: {'是' if not bundle['over_threshold'] else '否'}")
        results.append(("任务#7 首屏体积", not bundle["over_threshold"], f"{bundle['first_screen_gzip_kb']} KB gzip"))
    else:
        print("  bundle-size.json 不存在，运行 python scripts/check_bundle_size.py")
        results.append(("任务#7 首屏体积", False, "no report"))

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, detail in results:
        flag = "[OK]  " if ok else "[FAIL]"
        print(f"  {flag} {name:<30} {detail[:60]}")
    print(f"\n  合计: {passed}/{total} 通过")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
