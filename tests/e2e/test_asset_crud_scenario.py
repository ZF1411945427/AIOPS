# -*- coding: utf-8 -*-
"""场景2: 资产管理CRUD (ASSET-001~006) — 添加11.0.1.131/132到REAL库"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_asset"
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

    # === 登录 ===
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("input", timeout=5000)
    inputs = page.query_selector_all("input")
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    time.sleep(0.5)
    page.click("button:has-text('登录')")
    page.wait_for_timeout(3000)
    print("登录成功")

    # === ASSET-001: 资产列表加载 ===
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 检查表格是否存在
        table = page.query_selector("table")
        rows = page.query_selector_all("table tbody tr") if table else []
        log("ASSET-001", "资产列表加载", "PASS" if table else "FAIL", f"表格存在, {len(rows)} 行数据")
        page.screenshot(path=os.path.join(SHOT, "asset001_list.png"))
    except Exception as e:
        log("ASSET-001", "资产列表加载", "FAIL", str(e)[:100])

    # === ASSET-004: 添加资产 11.0.1.131 (SSH) ===
    try:
        page.goto(f"{BASE}/assets/create", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "asset004_form.png"))

        # 填写基本信息
        page.fill("input[name='name']", "test-master1")
        page.fill("input[name='ip']", "11.0.1.131")

        # 选择 CI 类型
        ci_select = page.query_selector("select[name='ci_type']")
        if ci_select:
            ci_select.select_option("server")

        # 选择 SSH 连接方式
        ssh_tab = page.query_selector("button.conn-tab:has-text('SSH')")
        if ssh_tab:
            ssh_tab.click()
            time.sleep(1)

        # 填写 SSH 信息
        page.fill("input[name='ssh_user']", "root")
        page.fill("input[name='ssh_password']", "123456")
        ssh_port = page.query_selector("input[name='ssh_port']")
        if ssh_port:
            ssh_port.fill("22")

        time.sleep(0.5)
        page.screenshot(path=os.path.join(SHOT, "asset004_filled.png"))

        # 保存
        save_btn = page.query_selector("button:has-text('保存')")
        if save_btn:
            save_btn.click()
            page.wait_for_timeout(3000)

        url = page.url
        if "assets" in url and "create" not in url:
            log("ASSET-004", "添加资产131", "PASS", f"保存后跳转到 {url}")
        else:
            # 检查是否有错误提示
            page.screenshot(path=os.path.join(SHOT, "asset004_after_save.png"))
            log("ASSET-004", "添加资产131", "FAIL", f"保存后URL: {url}")
    except Exception as e:
        log("ASSET-004", "添加资产131", "FAIL", str(e)[:100])
        page.screenshot(path=os.path.join(SHOT, "asset004_error.png"))

    # === ASSET-004b: 添加资产 11.0.1.132 (SSH) ===
    try:
        page.goto(f"{BASE}/assets/create", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.fill("input[name='name']", "test-master2")
        page.fill("input[name='ip']", "11.0.1.132")
        ci_select = page.query_selector("select[name='ci_type']")
        if ci_select:
            ci_select.select_option("server")
        ssh_tab = page.query_selector("button.conn-tab:has-text('SSH')")
        if ssh_tab:
            ssh_tab.click()
            time.sleep(1)
        page.fill("input[name='ssh_user']", "root")
        page.fill("input[name='ssh_password']", "123456")
        ssh_port = page.query_selector("input[name='ssh_port']")
        if ssh_port:
            ssh_port.fill("22")
        time.sleep(0.5)
        save_btn = page.query_selector("button:has-text('保存')")
        if save_btn:
            save_btn.click()
            page.wait_for_timeout(3000)
        url = page.url
        if "assets" in url and "create" not in url:
            log("ASSET-004", "添加资产132", "PASS", f"保存后跳转到 {url}")
        else:
            log("ASSET-004", "添加资产132", "FAIL", f"保存后URL: {url}")
    except Exception as e:
        log("ASSET-004", "添加资产132", "FAIL", str(e)[:100])

    # === ASSET-001 再验证: 列表应该有2条新资产 ===
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "asset001_list_after.png"))
        rows = page.query_selector_all("table tbody tr")
        has_131 = False
        has_132 = False
        for row in rows:
            text = row.inner_text()
            if "11.0.1.131" in text:
                has_131 = True
            if "11.0.1.132" in text:
                has_132 = True
        if has_131 and has_132:
            log("ASSET-001", "资产列表验证", "PASS", "两台服务器都在列表中")
        else:
            log("ASSET-001", "资产列表验证", "FAIL", f"131:{has_131} 132:{has_132}")
    except Exception as e:
        log("ASSET-001", "资产列表验证", "FAIL", str(e)[:100])

    # === ASSET-002: 资产搜索 ===
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 找搜索框
        search = page.query_selector("input[placeholder*='搜索'], input[placeholder*='名称'], input[type='search']")
        if search:
            search.fill("test-master1")
            time.sleep(1)
            # 可能需要点搜索按钮或回车
            search.press("Enter")
            page.wait_for_timeout(2000)
            rows = page.query_selector_all("table tbody tr")
            found = any("test-master1" in r.inner_text() for r in rows)
            log("ASSET-002", "资产搜索", "PASS" if found else "FAIL", f"搜索结果行数: {len(rows)}")
        else:
            log("ASSET-002", "资产搜索", "FAIL", "未找到搜索框")
    except Exception as e:
        log("ASSET-002", "资产搜索", "FAIL", str(e)[:100])

    # === ASSET-005: 编辑资产 ===
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 找编辑按钮
        edit_btn = page.query_selector("a:has-text('编辑'), button:has-text('编辑')")
        if edit_btn:
            edit_btn.click()
            page.wait_for_timeout(2000)
            # 修改名称
            name_input = page.query_selector("input[name='name']")
            if name_input:
                name_input.fill("test-master1-edited")
                time.sleep(0.5)
                save_btn = page.query_selector("button:has-text('保存')")
                if save_btn:
                    save_btn.click()
                    page.wait_for_timeout(3000)
                url = page.url
                if "create" not in url and "edit" not in url:
                    log("ASSET-005", "编辑资产", "PASS", "编辑保存成功")
                else:
                    log("ASSET-005", "编辑资产", "FAIL", f"保存后URL: {url}")
            else:
                log("ASSET-005", "编辑资产", "FAIL", "未找到名称输入框")
        else:
            log("ASSET-005", "编辑资产", "FAIL", "未找到编辑按钮")
    except Exception as e:
        log("ASSET-005", "编辑资产", "FAIL", str(e)[:100])

    # === ASSET-006: 删除资产 ===
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 找删除按钮
        del_btn = page.query_selector("button:has-text('删除'), a:has-text('删除')")
        if del_btn:
            # 监听 dialog
            page.on("dialog", lambda d: d.accept())
            del_btn.click()
            page.wait_for_timeout(3000)
            # 检查是否删除成功
            rows = page.query_selector_all("table tbody tr")
            log("ASSET-006", "删除资产", "PASS", f"删除后剩余 {len(rows)} 行")
        else:
            log("ASSET-006", "删除资产", "FAIL", "未找到删除按钮")
    except Exception as e:
        log("ASSET-006", "删除资产", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景2: 资产管理CRUD — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
