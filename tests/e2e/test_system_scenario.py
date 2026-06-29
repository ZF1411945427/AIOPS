# -*- coding: utf-8 -*-
"""场景8: 系统管理 (SYS-001~012) — 用户/令牌/DB切换/审计/设置
修正版: 使用正确路由 (/api-tokens, /api/system/overview, /api/audit/logs) 和正确表单选择器
"""
from playwright.sync_api import sync_playwright
import os, time, json, uuid

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_system"
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

    # 登录
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("input", timeout=5000)
    inputs = page.query_selector_all("input")
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    time.sleep(0.5)
    page.click("button:has-text('登录')")
    page.wait_for_timeout(3000)

    # === SYS-001: 用户管理页面 ===
    try:
        page.goto(f"{BASE}/users", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_users = "用户" in page_text or "user" in page_text.lower()
        log("SYS-001", "用户管理页面", "PASS" if has_users else "FAIL",
            "有用户内容" if has_users else "无用户内容")
        page.screenshot(path=os.path.join(SHOT, "sys001_users.png"))
    except Exception as e:
        log("SYS-001", "用户管理页面", "FAIL", str(e)[:100])

    # === SYS-002: 创建用户 (修正: name=username/password, button=添加) ===
    test_user = f"e2e_user_{uuid.uuid4().hex[:6]}"
    try:
        page.goto(f"{BASE}/users", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 先点击"添加用户"展开折叠表单
        toggle_btn = page.query_selector("button:has-text('添加用户')")
        if toggle_btn:
            toggle_btn.click()
            page.wait_for_timeout(1000)
        username_input = page.query_selector("input[name='username']")
        password_input = page.query_selector("input[name='password']")
        if username_input and password_input:
            username_input.fill(test_user)
            password_input.fill("test123456")
            role_select = page.query_selector("select[name='role']")
            if role_select:
                role_select.select_option("operator")
            # 用 Enter 键提交表单（按钮 force click 在折叠表单上不可靠）
            password_input.press("Enter")
            page.wait_for_timeout(3000)
            page_text = page.inner_text("body")
            if test_user in page_text:
                log("SYS-002", "创建用户", "PASS", f"用户 {test_user} 创建成功")
            else:
                log("SYS-002", "创建用户", "FAIL", "用户未出现在列表")
        else:
            log("SYS-002", "创建用户", "FAIL", "未找到用户名/密码输入框")
        page.screenshot(path=os.path.join(SHOT, "sys002_create_user.png"))
    except Exception as e:
        log("SYS-002", "创建用户", "FAIL", str(e)[:100])

    # === SYS-003: 用户列表 ===
    try:
        page.goto(f"{BASE}/users", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        rows = page.query_selector_all("table tbody tr")
        log("SYS-003", "用户列表", "PASS" if len(rows) >= 1 else "FAIL", f"{len(rows)} 个用户")
        page.screenshot(path=os.path.join(SHOT, "sys003_user_list.png"))
    except Exception as e:
        log("SYS-003", "用户列表", "FAIL", str(e)[:100])

    # === SYS-004: 系统设置页面 ===
    try:
        page.goto(f"{BASE}/settings", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_settings = "设置" in page_text or "setting" in page_text.lower()
        log("SYS-004", "系统设置页面", "PASS" if has_settings else "FAIL",
            "有设置内容" if has_settings else "无设置内容")
        page.screenshot(path=os.path.join(SHOT, "sys004_settings.png"))
    except Exception as e:
        log("SYS-004", "系统设置页面", "FAIL", str(e)[:100])

    # === SYS-005: 系统概览 API (修正: /api/system/overview 返回 JSON) ===
    try:
        resp = page.request.get(f"{BASE}/api/system/overview")
        body = json.loads(resp.text())
        has_overview = "assets" in body or "metrics_count_1h" in body
        detail = f"assets={body.get('assets',{}).get('total','?')}, metrics_1h={body.get('metrics_count_1h','?')}"
        log("SYS-005", "系统概览API", "PASS" if has_overview else "FAIL", detail)
    except Exception as e:
        log("SYS-005", "系统概览API", "FAIL", str(e)[:100])

    # === SYS-006: 审计日志 API (修正: /api/audit/logs 返回 JSON 数组) ===
    try:
        resp = page.request.get(f"{BASE}/api/audit/logs")
        body = json.loads(resp.text())
        is_list = isinstance(body, list)
        log("SYS-006", "审计日志API", "PASS" if is_list else "FAIL",
            f"返回 {len(body)} 条审计记录" if is_list else f"非数组: {str(body)[:80]}")
    except Exception as e:
        log("SYS-006", "审计日志API", "FAIL", str(e)[:100])

    # === SYS-007: API 令牌页面 (修正: /api-tokens) ===
    try:
        page.goto(f"{BASE}/api-tokens", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_tokens = "令牌" in page_text or "token" in page_text.lower()
        log("SYS-007", "API令牌页面", "PASS" if has_tokens else "FAIL",
            "有令牌内容" if has_tokens else "无令牌内容")
        page.screenshot(path=os.path.join(SHOT, "sys007_tokens.png"))
    except Exception as e:
        log("SYS-007", "API令牌页面", "FAIL", str(e)[:100])

    # === SYS-008: 创建 API 令牌 (修正: name=name, button=生成) ===
    test_token_name = f"e2e_token_{uuid.uuid4().hex[:6]}"
    try:
        page.goto(f"{BASE}/api-tokens", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 先点击"生成新令牌"展开折叠表单
        toggle_btn = page.query_selector("button:has-text('生成新令牌')")
        if toggle_btn:
            toggle_btn.click()
            page.wait_for_timeout(1000)
        name_input = page.query_selector("input[name='name']")
        if name_input:
            name_input.fill(test_token_name)
            # 用 Enter 键提交表单（按钮 force click 在折叠表单上不可靠）
            name_input.press("Enter")
            page.wait_for_timeout(3000)
            page_text = page.inner_text("body")
            if test_token_name in page_text:
                log("SYS-008", "创建API令牌", "PASS", f"令牌 {test_token_name} 创建成功")
            else:
                log("SYS-008", "创建API令牌", "FAIL", "令牌未出现在列表")
        else:
            log("SYS-008", "创建API令牌", "FAIL", "未找到name输入框")
        page.screenshot(path=os.path.join(SHOT, "sys008_create_token.png"))
    except Exception as e:
        log("SYS-008", "创建API令牌", "FAIL", str(e)[:100])

    # === SYS-010: 数据库模式查询 (修正: /api/system/db-mode) ===
    try:
        resp = page.request.get(f"{BASE}/api/system/db-mode")
        body = json.loads(resp.text())
        current_mode = body.get("mode", "unknown")
        log("SYS-010", "数据库模式查询", "PASS" if current_mode in ("demo", "real") else "FAIL",
            f"当前模式: {current_mode}")
    except Exception as e:
        log("SYS-010", "数据库模式查询", "FAIL", str(e)[:100])

    # === SYS-011: DB 切换 API (修正: POST form data) ===
    try:
        resp1 = page.request.post(f"{BASE}/api/system/db-switch", data={"mode": "demo"})
        body1 = json.loads(resp1.text())
        resp2 = page.request.post(f"{BASE}/api/system/db-switch", data={"mode": "real"})
        body2 = json.loads(resp2.text())
        final_mode = body2.get("mode", "unknown")
        log("SYS-011", "数据库切换", "PASS" if final_mode == "real" else "FAIL",
            f"切回 real: {final_mode}")
    except Exception as e:
        log("SYS-011", "数据库切换", "FAIL", str(e)[:100])

    # === SYS-015: 数据源管理 ===
    try:
        page.goto(f"{BASE}/datasources", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_ds = "数据源" in page_text or "datasource" in page_text.lower()
        log("SYS-015", "数据源管理", "PASS" if has_ds else "FAIL",
            "有数据源内容" if has_ds else "无数据源内容")
        page.screenshot(path=os.path.join(SHOT, "sys015_datasources.png"))
    except Exception as e:
        log("SYS-015", "数据源管理", "FAIL", str(e)[:100])

    # === SYS-022: 系统菜单 ===
    try:
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        menu_items = page.query_selector_all(".el-menu-item, .sidebar-item, nav a")
        log("SYS-022", "系统菜单", "PASS" if len(menu_items) > 3 else "FAIL",
            f"{len(menu_items)} 个菜单项")
        page.screenshot(path=os.path.join(SHOT, "sys022_menu.png"))
    except Exception as e:
        log("SYS-022", "系统菜单", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景8: 系统管理 — 测试结果汇总 (修正版)")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: {os.path.join(SHOT, 'results.json')}")
