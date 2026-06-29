# -*- coding: utf-8 -*-
"""场景1: 认证与登录 (AUTH-001~007)"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_auth"
os.makedirs(SHOT, exist_ok=True)

results = []

def log(case_id, func, status, detail=""):
    results.append({"id": case_id, "func": func, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {case_id} {func}: {status} {detail}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    # === AUTH-001: 正常登录 ===
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
        page.wait_for_selector("input", timeout=5000)
        # 填写用户名
        inputs = page.query_selector_all("input")
        if len(inputs) >= 2:
            inputs[0].fill("admin")
            inputs[1].fill("admin123")
        else:
            page.fill("input[placeholder*='用户'], input[type='text']", "admin")
            page.fill("input[placeholder*='密码'], input[type='password']", "admin123")
        time.sleep(0.5)
        # 点击登录
        page.click("button:has-text('登录')")
        page.wait_for_timeout(3000)
        url = page.url
        if "login" not in url:
            log("AUTH-001", "正常登录", "PASS", f"跳转到 {url}")
            page.screenshot(path=os.path.join(SHOT, "auth001_login_success.png"))
        else:
            log("AUTH-001", "正常登录", "FAIL", f"仍在登录页 {url}")
            page.screenshot(path=os.path.join(SHOT, "auth001_fail.png"))
    except Exception as e:
        log("AUTH-001", "正常登录", "FAIL", str(e)[:100])

    # === AUTH-002: 错误密码 ===
    try:
        # 先退出
        page.goto(f"{BASE}/logout", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=10000)
        page.wait_for_selector("input", timeout=5000)
        inputs = page.query_selector_all("input")
        inputs[0].fill("admin")
        inputs[1].fill("wrongpassword")
        time.sleep(0.5)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(2000)
        url = page.url
        if "login" in url:
            log("AUTH-002", "错误密码登录", "PASS", "停留在登录页")
            page.screenshot(path=os.path.join(SHOT, "auth002_wrong_pwd.png"))
        else:
            log("AUTH-002", "错误密码登录", "FAIL", f"不应跳转: {url}")
    except Exception as e:
        log("AUTH-002", "错误密码登录", "FAIL", str(e)[:100])

    # === AUTH-003: 空用户名 ===
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=10000)
        page.wait_for_selector("input", timeout=5000)
        inputs = page.query_selector_all("input")
        inputs[0].fill("")
        inputs[1].fill("admin123")
        time.sleep(0.5)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(2000)
        url = page.url
        if "login" in url:
            log("AUTH-003", "空用户名登录", "PASS", "停留在登录页")
        else:
            log("AUTH-003", "空用户名登录", "FAIL", f"不应跳转: {url}")
    except Exception as e:
        log("AUTH-003", "空用户名登录", "FAIL", str(e)[:100])

    # === AUTH-004: 空密码 ===
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=10000)
        page.wait_for_selector("input", timeout=5000)
        inputs = page.query_selector_all("input")
        inputs[0].fill("admin")
        inputs[1].fill("")
        time.sleep(0.5)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(2000)
        url = page.url
        if "login" in url:
            log("AUTH-004", "空密码登录", "PASS", "停留在登录页")
        else:
            log("AUTH-004", "空密码登录", "FAIL", f"不应跳转: {url}")
    except Exception as e:
        log("AUTH-004", "空密码登录", "FAIL", str(e)[:100])

    # === AUTH-005: 退出登录 ===
    try:
        # 先登录
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=10000)
        page.wait_for_selector("input", timeout=5000)
        inputs = page.query_selector_all("input")
        inputs[0].fill("admin")
        inputs[1].fill("admin123")
        time.sleep(0.5)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(3000)
        # 退出
        page.goto(f"{BASE}/logout", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(2000)
        url = page.url
        if "login" in url:
            log("AUTH-005", "退出登录", "PASS", "跳转到登录页")
        else:
            log("AUTH-005", "退出登录", "FAIL", f"未跳转到登录页: {url}")
    except Exception as e:
        log("AUTH-005", "退出登录", "FAIL", str(e)[:100])

    # === AUTH-006: 未登录访问受保护页面 ===
    try:
        # 用无 session 的 context
        ctx2 = browser.new_context(viewport={"width": 1400, "height": 900})
        page2 = ctx2.new_page()
        page2.goto(f"{BASE}/assets", wait_until="networkidle", timeout=10000)
        page2.wait_for_timeout(2000)
        url = page2.url
        if "login" in url:
            log("AUTH-006", "未登录访问受保护页面", "PASS", "重定向到登录页")
        else:
            log("AUTH-006", "未登录访问受保护页面", "FAIL", f"未重定向: {url}")
        ctx2.close()
    except Exception as e:
        log("AUTH-006", "未登录访问受保护页面", "FAIL", str(e)[:100])

    # === AUTH-007: 登录后 session 保持 ===
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=10000)
        page.wait_for_selector("input", timeout=5000)
        inputs = page.query_selector_all("input")
        inputs[0].fill("admin")
        inputs[1].fill("admin123")
        time.sleep(0.5)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(3000)
        url_before = page.url
        # 刷新
        page.reload(wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(2000)
        url_after = page.url
        if "login" not in url_after:
            log("AUTH-007", "登录后 session 保持", "PASS", "刷新后仍登录")
        else:
            log("AUTH-007", "登录后 session 保持", "FAIL", "刷新后掉登录")
    except Exception as e:
        log("AUTH-007", "登录后 session 保持", "FAIL", str(e)[:100])

    browser.close()

# 输出结果
print("\n" + "="*60)
print("场景1: 认证与登录 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

# 保存 JSON
with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: {os.path.join(SHOT, 'results.json')}")
