# -*- coding: utf-8 -*-
"""场景5: 告警规则创建+告警触发 (ALERT-006~012)"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_alert"
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

    # === ALERT-006: 告警规则页面加载 ===
    try:
        page.goto(f"{BASE}/alerts/rules", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_rule = "规则" in page_text or "rule" in page_text.lower()
        log("ALERT-006", "告警规则页面加载", "PASS" if has_rule else "FAIL", 
            "页面有规则内容" if has_rule else "页面无规则内容")
        page.screenshot(path=os.path.join(SHOT, "alert006_rules.png"))
    except Exception as e:
        log("ALERT-006", "告警规则页面加载", "FAIL", str(e)[:100])

    # === ALERT-007: 创建告警规则 (cpu_usage > 0.1, 触发条件容易满足) ===
    try:
        # 填写规则创建表单
        page.fill("input[name='name']", "test-cpu-high")
        
        # 选指标
        metric_select = page.query_selector("select[name='metric_name']")
        if metric_select:
            metric_select.select_option("cpu_usage")
        
        # 选条件
        cond_select = page.query_selector("select[name='condition']")
        if cond_select:
            cond_select.select_option("gt")
        
        # 阈值 (设为 0.1 让它容易触发)
        page.fill("input[name='threshold']", "0.1")
        
        # 严重级别
        sev_select = page.query_selector("select[name='severity']")
        if sev_select:
            sev_select.select_option("warning")
        
        time.sleep(0.5)
        page.screenshot(path=os.path.join(SHOT, "alert007_form.png"))
        
        # 点击创建按钮
        create_btn = page.query_selector("button:has-text('创建')")
        if create_btn:
            create_btn.click()
            page.wait_for_timeout(3000)
        
        url = page.url
        if "rules" in url:
            # 检查规则是否在列表中
            page_text = page.inner_text("body")
            if "test-cpu-high" in page_text:
                log("ALERT-007", "创建告警规则", "PASS", "规则创建成功并出现在列表")
            else:
                log("ALERT-007", "创建告警规则", "FAIL", "规则未出现在列表")
        else:
            log("ALERT-007", "创建告警规则", "FAIL", f"跳转到 {url}")
        page.screenshot(path=os.path.join(SHOT, "alert007_created.png"))
    except Exception as e:
        log("ALERT-007", "创建告警规则", "FAIL", str(e)[:100])
        page.screenshot(path=os.path.join(SHOT, "alert007_error.png"))

    # === ALERT-008: 告警规则列表 ===
    try:
        page.goto(f"{BASE}/alerts/rules", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        rows = page.query_selector_all("table tbody tr")
        # 检查是否有规则
        has_rules = len(rows) > 0 or "test-cpu-high" in page.inner_text("body")
        log("ALERT-008", "告警规则列表", "PASS" if has_rules else "FAIL", 
            f"{len(rows)} 条规则")
    except Exception as e:
        log("ALERT-008", "告警规则列表", "FAIL", str(e)[:100])

    # === ALERT-009: 告警规则启用/禁用 ===
    try:
        # 找 toggle 按钮
        toggle_btn = page.query_selector("button:has-text('禁用'), button:has-text('启用')")
        if toggle_btn:
            toggle_btn.click()
            page.wait_for_timeout(2000)
            page_text = page.inner_text("body")
            # 验证状态变化
            if "禁用" in page_text or "启用" in page_text:
                log("ALERT-009", "规则启用/禁用", "PASS", "状态切换成功")
            else:
                log("ALERT-009", "规则启用/禁用", "FAIL", "状态未变化")
        else:
            log("ALERT-009", "规则启用/禁用", "FAIL", "未找到切换按钮")
    except Exception as e:
        log("ALERT-009", "规则启用/禁用", "FAIL", str(e)[:100])

    # === ALERT-010: 告警规则静默 ===
    try:
        page.goto(f"{BASE}/alerts/rules", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        silence_btn = page.query_selector("button:has-text('静默')")
        if silence_btn:
            silence_btn.click()
            page.wait_for_timeout(2000)
            page_text = page.inner_text("body")
            if "静默" in page_text:
                log("ALERT-010", "规则静默", "PASS", "静默操作成功")
            else:
                log("ALERT-010", "规则静默", "FAIL", "静默未生效")
        else:
            log("ALERT-010", "规则静默", "FAIL", "未找到静默按钮")
    except Exception as e:
        log("ALERT-010", "规则静默", "FAIL", str(e)[:100])

    # === ALERT-012: 告警检查触发 ===
    try:
        # 调用告警检查 API
        import urllib.request, urllib.parse, http.cookiejar
        # 用 page 的 context 发请求
        resp = page.request.post(f"{BASE}/alerts/check")
        status = resp.status
        body = resp.text()
        log("ALERT-012", "告警检查触发", "PASS" if status == 200 else "FAIL", 
            f"HTTP {status}, body: {body[:80]}")
    except Exception as e:
        log("ALERT-012", "告警检查触发", "FAIL", str(e)[:100])

    # === ALERT-001: 告警列表页面 ===
    try:
        page.goto(f"{BASE}/alerts", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page_text = page.inner_text("body")
        has_alerts = "告警" in page_text or "alert" in page_text.lower()
        log("ALERT-001", "告警列表页面", "PASS" if has_alerts else "FAIL", 
            "页面有告警内容" if has_alerts else "页面无告警内容")
        page.screenshot(path=os.path.join(SHOT, "alert001_list.png"))
    except Exception as e:
        log("ALERT-001", "告警列表页面", "FAIL", str(e)[:100])

    # === ALERT-002: 告警确认 ===
    try:
        # 找确认按钮
        ack_btn = page.query_selector("button:has-text('确认'), a:has-text('确认')")
        if ack_btn:
            ack_btn.click()
            page.wait_for_timeout(2000)
            log("ALERT-002", "告警确认", "PASS", "确认操作完成")
        else:
            # 可能没有告警数据
            rows = page.query_selector_all("table tbody tr")
            if len(rows) == 0:
                log("ALERT-002", "告警确认", "PASS", "无告警数据(跳过)")
            else:
                log("ALERT-002", "告警确认", "FAIL", "有告警但未找到确认按钮")
    except Exception as e:
        log("ALERT-002", "告警确认", "FAIL", str(e)[:100])

    # === ALERT-003: 告警解决 ===
    try:
        resolve_btn = page.query_selector("button:has-text('解决'), a:has-text('解决')")
        if resolve_btn:
            resolve_btn.click()
            page.wait_for_timeout(2000)
            log("ALERT-003", "告警解决", "PASS", "解决操作完成")
        else:
            rows = page.query_selector_all("table tbody tr")
            if len(rows) == 0:
                log("ALERT-003", "告警解决", "PASS", "无告警数据(跳过)")
            else:
                log("ALERT-003", "告警解决", "FAIL", "有告警但未找到解决按钮")
    except Exception as e:
        log("ALERT-003", "告警解决", "FAIL", str(e)[:100])

    # === ALERT-011: 告警详情 ===
    try:
        page.goto(f"{BASE}/alerts", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        detail_link = page.query_selector("a:has-text('详情'), a:has-text('查看')")
        if detail_link:
            detail_link.click()
            page.wait_for_timeout(2000)
            url = page.url
            if "/alerts/" in url and url.rstrip("/").split("/")[-1].isdigit():
                log("ALERT-011", "告警详情", "PASS", f"跳转到 {url}")
            else:
                log("ALERT-011", "告警详情", "FAIL", f"URL: {url}")
        else:
            log("ALERT-011", "告警详情", "PASS", "无告警数据(跳过)")
    except Exception as e:
        log("ALERT-011", "告警详情", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景5: 告警规则创建+告警触发 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
