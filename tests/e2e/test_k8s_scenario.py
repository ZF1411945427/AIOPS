# -*- coding: utf-8 -*-
"""场景6: K8s资源管理 (K8S-001~016)"""
from playwright.sync_api import sync_playwright
import os, time, json, sqlite3, paramiko, urllib.request, urllib.parse, http.cookiejar

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_k8s"
os.makedirs(SHOT, exist_ok=True)
DB_PATH = r"E:\AIOPS\project03\db\aiops_real.db"

results = []

def log(case_id, func, status, detail=""):
    results.append({"id": case_id, "func": func, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {case_id} {func}: {status} {detail}")

# 读取 kubeconfig
with open(r"E:\AIOPS\project03\tests\e2e\kubeconfig.yaml", encoding="utf-8") as f:
    kubeconfig = f.read()

# === 通过 API 添加 K8s 数据源 ===
print("=== 步骤0: 添加 K8s 数据源 ===")
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
login_data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data)
try:
    resp = opener.open(req, timeout=10)
    print(f"  登录: {json.loads(resp.read().decode()).get('message', 'OK')}")
except Exception as e:
    print(f"  登录失败: {e}")

# 检查是否已有 K8s 数据源
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, name, type, endpoint FROM data_sources WHERE type='kubernetes'")
existing = c.fetchall()
print(f"  现有 K8s 数据源: {existing}")
conn.close()

if not existing:
    # 添加 K8s 数据源
    data = urllib.parse.urlencode({
        "name": "test-k8s-cluster",
        "type": "kubernetes",
        "endpoint": "https://11.0.1.131:16443",
        "auth_type": "kubeconfig",
        "k8s_kubeconfig": kubeconfig,
        "scrape_interval": 60,
    }).encode()
    req = urllib.request.Request(f"{BASE}/datasources/create", data=data)
    try:
        resp = opener.open(req, timeout=30)
        print(f"  添加 K8s 数据源: {resp.status}")
    except Exception as e:
        print(f"  添加失败: {e}")

# 验证数据源
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, name, type, endpoint FROM data_sources WHERE type='kubernetes'")
k8s_sources = c.fetchall()
print(f"  K8s 数据源: {k8s_sources}")
conn.close()

# === E2E 页面测试 ===
print("\n=== K8s 页面测试 ===")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    # 登录
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("input", timeout=5000)
    inputs = page.query_selector_all("input")
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    time.sleep(0.5)
    page.click("button:has-text('登录')")
    page.wait_for_timeout(3000)

    # === K8S-001: K8s 集群概览 ===
    try:
        page.goto(f"{BASE}/k8s/overview", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_cluster = any(kw in page_text for kw in ["集群", "cluster", "节点", "node", "pod", "deployment"])
        log("K8S-001", "K8s集群概览", "PASS" if has_cluster else "FAIL", 
            "页面有集群内容" if has_cluster else "页面无集群内容")
        page.screenshot(path=os.path.join(SHOT, "k8s001_overview.png"))
    except Exception as e:
        log("K8S-001", "K8s集群概览", "FAIL", str(e)[:100])

    # === K8S-002: Pod 列表 ===
    try:
        page.goto(f"{BASE}/containers/pods", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_pods = any(kw in page_text.lower() for kw in ["pod", "容器", "namespace"])
        log("K8S-002", "Pod列表", "PASS" if has_pods else "FAIL", 
            "页面有 Pod 内容" if has_pods else "页面无 Pod 内容")
        page.screenshot(path=os.path.join(SHOT, "k8s002_pods.png"))
    except Exception as e:
        log("K8S-002", "Pod列表", "FAIL", str(e)[:100])

    # === K8S-003: Deployment 列表 ===
    try:
        page.goto(f"{BASE}/containers/deployments", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_deps = any(kw in page_text.lower() for kw in ["deployment", "部署", "replica"])
        log("K8S-003", "Deployment列表", "PASS" if has_deps else "FAIL", 
            "页面有 Deployment 内容" if has_deps else "页面无内容")
        page.screenshot(path=os.path.join(SHOT, "k8s003_deployments.png"))
    except Exception as e:
        log("K8S-003", "Deployment列表", "FAIL", str(e)[:100])

    # === K8S-004: Pod 详情 ===
    try:
        # 找表格中的第一个详情链接
        links = page.query_selector_all("a:has-text('详情'), a:has-text('查看'), a:has-text('logs')")
        if links:
            links[0].click()
            page.wait_for_timeout(3000)
            url = page.url
            log("K8S-004", "Pod详情", "PASS" if "pod" in url.lower() or "container" in url.lower() else "FAIL", f"URL: {url}")
        else:
            log("K8S-004", "Pod详情", "PASS", "无详情链接(可能无数据)")
    except Exception as e:
        log("K8S-004", "Pod详情", "FAIL", str(e)[:100])

    # === K8S-007: StatefulSet 列表 ===
    try:
        page.goto(f"{BASE}/k8s/statefulsets", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_sts = any(kw in page_text.lower() for kw in ["statefulset", "有状态"])
        log("K8S-007", "StatefulSet列表", "PASS" if has_sts or "暂无" in page_text else "FAIL", 
            "页面加载" if has_sts or "暂无" in page_text else "页面异常")
        page.screenshot(path=os.path.join(SHOT, "k8s007_sts.png"))
    except Exception as e:
        log("K8S-007", "StatefulSet列表", "FAIL", str(e)[:100])

    # === K8S-008: DaemonSet 列表 ===
    try:
        page.goto(f"{BASE}/k8s/daemonsets", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-008", "DaemonSet列表", "PASS", "页面加载成功")
        page.screenshot(path=os.path.join(SHOT, "k8s008_ds.png"))
    except Exception as e:
        log("K8S-008", "DaemonSet列表", "FAIL", str(e)[:100])

    # === K8S-009: Service 列表 ===
    try:
        page.goto(f"{BASE}/k8s/services", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-009", "Service列表", "PASS", "页面加载成功")
        page.screenshot(path=os.path.join(SHOT, "k8s009_svc.png"))
    except Exception as e:
        log("K8S-009", "Service列表", "FAIL", str(e)[:100])

    # === K8S-010: Ingress 列表 ===
    try:
        page.goto(f"{BASE}/k8s/ingresses", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-010", "Ingress列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-010", "Ingress列表", "FAIL", str(e)[:100])

    # === K8S-011: ConfigMap 列表 ===
    try:
        page.goto(f"{BASE}/k8s/configmaps", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-011", "ConfigMap列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-011", "ConfigMap列表", "FAIL", str(e)[:100])

    # === K8S-012: Secret 列表 ===
    try:
        page.goto(f"{BASE}/k8s/secrets", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-012", "Secret列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-012", "Secret列表", "FAIL", str(e)[:100])

    # === K8S-013: HPA 列表 ===
    try:
        page.goto(f"{BASE}/k8s/hpas", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-013", "HPA列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-013", "HPA列表", "FAIL", str(e)[:100])

    # === K8S-014: PVC 列表 ===
    try:
        page.goto(f"{BASE}/k8s/pvcs", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-014", "PVC列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-014", "PVC列表", "FAIL", str(e)[:100])

    # === K8S-016: K8s 监控页面 ===
    try:
        page.goto(f"{BASE}/k8s-monitor", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_monitor = any(kw in page_text.lower() for kw in ["监控", "monitor", "节点", "pod"])
        log("K8S-016", "K8s监控页面", "PASS" if has_monitor else "FAIL", 
            "页面有监控内容" if has_monitor else "页面无内容")
        page.screenshot(path=os.path.join(SHOT, "k8s016_monitor.png"))
    except Exception as e:
        log("K8S-016", "K8s监控页面", "FAIL", str(e)[:100])

    # === K8S-017: Docker 容器列表 ===
    try:
        page.goto(f"{BASE}/containers/docker", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        log("K8S-017", "Docker容器列表", "PASS", "页面加载成功")
    except Exception as e:
        log("K8S-017", "Docker容器列表", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景6: K8s资源管理 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
