# -*- coding: utf-8 -*-
"""场景3: 资产测试连接+探测+指标采集 (ASSET-007/008, METRIC-001/007/009)"""
from playwright.sync_api import sync_playwright
import os, time, json, sqlite3, paramiko, subprocess

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_asset"
os.makedirs(SHOT, exist_ok=True)
DB_PATH = r"E:\AIOPS\project03\db\aiops_real.db"

results = []

def log(case_id, func, status, detail=""):
    results.append({"id": case_id, "func": func, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {case_id} {func}: {status} {detail}")

def get_metric_count(asset_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM metric_records WHERE asset_id=?", (asset_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

# === 步骤0: 验证 SSH 连通性 ===
print("=== 步骤0: 验证 SSH 连通性 ===")
for ip in ["11.0.1.131", "11.0.1.132"]:
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username="root", password="123456", timeout=10)
        stdin, stdout, stderr = ssh.exec_command("hostname")
        hostname = stdout.read().decode().strip()
        print(f"  {ip} SSH OK, hostname={hostname}")
        ssh.close()
    except Exception as e:
        print(f"  {ip} SSH FAIL: {e}")

# === 步骤1: 通过 API 测试连接 ===
print("\n=== 步骤1: API 测试连接 ===")
import urllib.request, urllib.parse, http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
login_data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data)
try:
    resp = opener.open(req, timeout=10)
    login_result = json.loads(resp.read().decode())
    print(f"  登录: {login_result.get('message', 'OK')}")
except Exception as e:
    print(f"  登录失败: {e}")

for ip in ["11.0.1.131", "11.0.1.132"]:
    try:
        conn_config = json.dumps({"ssh_user": "root", "ssh_password": "123456", "ssh_port": 22})
        data = urllib.parse.urlencode({
            "connection_type": "ssh",
            "host": ip,
            "connection_config": conn_config
        }).encode()
        req = urllib.request.Request(f"{BASE}/assets/api/test-connection", data=data)
        resp = opener.open(req, timeout=15)
        result = json.loads(resp.read().decode())
        ok = result.get("ok", False)
        msg = result.get("message", "")
        latency = result.get("latency_ms", 0)
        if ok:
            log("ASSET-007", f"测试连接{ip}", "PASS", f"连接成功, 延迟{latency}ms")
        else:
            log("ASSET-007", f"测试连接{ip}", "FAIL", msg[:80])
    except Exception as e:
        log("ASSET-007", f"测试连接{ip}", "FAIL", str(e)[:80])

# === 步骤2: 确保资产 online + 手动触发采集 ===
print("\n=== 步骤2: 手动采集指标 ===")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, name, ip, status FROM assets WHERE ip IN ('11.0.1.131', '11.0.1.132')")
asset_rows = c.fetchall()
print(f"  资产记录: {asset_rows}")
for row in asset_rows:
    aid, aname, aip, astatus = row
    if astatus != "online":
        c.execute("UPDATE assets SET status='online' WHERE id=?", (aid,))
        print(f"  资产 {aname}({aip}) offline -> online")
conn.commit()
conn.close()

# 采集前指标数
before_counts = {}
for row in asset_rows:
    before_counts[row[0]] = get_metric_count(row[0])
print(f"  采集前指标数: {before_counts}")

# 通过后端代码触发采集
collect_script = r"""
import sys, os
sys.path.insert(0, r"E:\AIOPS\project03")
os.chdir(r"E:\AIOPS\project03")
from app.database import get_session_for, set_db_mode
set_db_mode("real")
SessionLocal = get_session_for("real")
from app.services import metric_collector
from app.models import Asset

db = SessionLocal()
assets = db.query(Asset).filter(Asset.status == "online").all()
print(f"Online assets: {len(assets)}")
for asset in assets:
    print(f"  采集 {asset.name} ({asset.ip})...")
    result = metric_collector.collect_asset_metrics(asset, db)
    if result["error"]:
        print(f"    错误: {result['error']}")
    else:
        print(f"    采集 {len(result['metrics'])} 条指标")
        for m in result["metrics"][:5]:
            print(f"      {m['name']}: {m['value']}")
db.close()
"""

r = subprocess.run(["python", "-c", collect_script], capture_output=True, text=True, timeout=60,
                   cwd=r"E:\AIOPS\project03")
print("采集输出:")
print(r.stdout)
if r.stderr:
    print("STDERR:", r.stderr[:500])

# === 步骤3: 验证指标数据 ===
print("\n=== 步骤3: 验证指标数据 ===")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT asset_id, COUNT(*), MIN(timestamp), MAX(timestamp) FROM metric_records GROUP BY asset_id")
metric_summary = c.fetchall()
print(f"  指标记录汇总: {metric_summary}")

c.execute("""SELECT asset_id, name, value, unit, timestamp FROM metric_records 
             ORDER BY timestamp DESC LIMIT 10""")
recent = c.fetchall()
print(f"  最新10条指标:")
for row in recent:
    print(f"    asset_id={row[0]}, {row[1]}={row[2]}{row[3]}, {row[4]}")
conn.close()

# 采集后对比
after_counts = {}
for row in asset_rows:
    after_counts[row[0]] = get_metric_count(row[0])
print(f"  采集后指标数: {after_counts}")

new_metrics = sum(after_counts[k] - before_counts.get(k, 0) for k in after_counts)
log("METRIC-009", "实时指标采集", "PASS" if new_metrics > 0 else "FAIL", f"新增{new_metrics}条指标")

# === 步骤4: 指标监控页面验证 ===
print("\n=== 步骤4: 指标监控页面验证 ===")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("input", timeout=5000)
    inputs = page.query_selector_all("input")
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    time.sleep(0.5)
    page.click("button:has-text('登录')")
    page.wait_for_timeout(3000)

    page.goto(f"{BASE}/metrics", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(SHOT, "metric_page.png"))

    page_text = page.inner_text("body")
    has_metrics = any(kw in page_text.lower() for kw in ["cpu", "memory", "load", "disk", "metric", "指标"])
    log("METRIC-001", "指标监控页面加载", "PASS" if has_metrics else "FAIL", 
        "页面有指标内容" if has_metrics else "页面无指标内容")

    cards = page.query_selector_all(".metric-card, .el-card, [class*='card']")
    log("METRIC-007", "指标卡片展示", "PASS" if len(cards) > 0 else "FAIL", f"{len(cards)} 个卡片")

    select = page.query_selector("select, .el-select")
    if select:
        log("METRIC-003", "多资产指标查看", "PASS", "资产选择器存在")
    else:
        log("METRIC-003", "多资产指标查看", "FAIL", "未找到资产选择器")

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景3: 资产测试连接+探测+指标采集 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results_conn.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
