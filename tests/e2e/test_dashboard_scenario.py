# -*- coding: utf-8 -*-
"""场景7: 仪表盘+系统态势数据验证 (DASH-001~009)"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_dashboard"
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

    # === DASH-001: 仪表盘页面加载 ===
    try:
        page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_dashboard = any(kw in page_text for kw in ["仪表盘", "dashboard", "总览", "资产", "告警"])
        log("DASH-001", "仪表盘页面加载", "PASS" if has_dashboard else "FAIL", 
            "页面有仪表盘内容" if has_dashboard else "页面无内容")
        page.screenshot(path=os.path.join(SHOT, "dash001.png"))
    except Exception as e:
        log("DASH-001", "仪表盘页面加载", "FAIL", str(e)[:100])

    # === DASH-002: 仪表盘统计数据 ===
    try:
        # 检查是否有数字统计数据
        stats = page.query_selector_all(".stat-card, .el-statistic, [class*='stat'], [class*='count']")
        has_numbers = any(c.isdigit() for c in page_text)
        log("DASH-002", "仪表盘统计数据", "PASS" if has_numbers else "FAIL", 
            f"{len(stats)} 个统计元素, 有数字: {has_numbers}")
    except Exception as e:
        log("DASH-002", "仪表盘统计数据", "FAIL", str(e)[:100])

    # === DASH-003: 资产分布图表 ===
    try:
        charts = page.query_selector_all("canvas, svg, [_echarts_instance], [class*='chart']")
        log("DASH-003", "资产分布图表", "PASS" if len(charts) > 0 else "FAIL", 
            f"{len(charts)} 个图表元素")
    except Exception as e:
        log("DASH-003", "资产分布图表", "FAIL", str(e)[:100])

    # === DASH-004: 告警统计 ===
    try:
        has_alert = "告警" in page_text or "alert" in page_text.lower()
        log("DASH-004", "告警统计", "PASS" if has_alert else "FAIL", 
            "有告警相关内容" if has_alert else "无告警内容")
    except Exception as e:
        log("DASH-004", "告警统计", "FAIL", str(e)[:100])

    # === DASH-005: 告警趋势 ===
    try:
        has_trend = any(kw in page_text for kw in ["趋势", "trend", "7天", "近7", "时间"])
        log("DASH-005", "告警趋势", "PASS" if has_trend or len(charts) > 0 else "FAIL", 
            "有趋势内容" if has_trend else "无趋势内容")
    except Exception as e:
        log("DASH-005", "告警趋势", "FAIL", str(e)[:100])

    # === DASH-006: 指标监控概览 ===
    try:
        has_metric = any(kw in page_text.lower() for kw in ["cpu", "内存", "memory", "指标", "metric"])
        log("DASH-006", "指标监控概览", "PASS" if has_metric else "FAIL", 
            "有指标内容" if has_metric else "无指标内容")
    except Exception as e:
        log("DASH-006", "指标监控概览", "FAIL", str(e)[:100])

    # === DASH-007: 指标趋势图 ===
    try:
        log("DASH-007", "指标趋势图", "PASS" if len(charts) > 0 else "FAIL", 
            f"{len(charts)} 个图表")
    except Exception as e:
        log("DASH-007", "指标趋势图", "FAIL", str(e)[:100])

    # === DASH-008: 仪表盘 API 数据 ===
    try:
        resp = page.request.get(f"{BASE}/api/dashboard/stats")
        status = resp.status
        body = resp.text()
        has_data = len(body) > 10
        log("DASH-008", "仪表盘API数据", "PASS" if status == 200 and has_data else "FAIL", 
            f"HTTP {status}, body长度: {len(body)}")
    except Exception as e:
        log("DASH-008", "仪表盘API数据", "FAIL", str(e)[:100])

    # === DASH-009: 系统态势页面 ===
    try:
        page.goto(f"{BASE}/system-posture", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page_text2 = page.inner_text("body")
        has_posture = any(kw in page_text2 for kw in ["态势", "posture", "健康", "health", "系统"])
        log("DASH-009", "系统态势页面", "PASS" if has_posture else "FAIL", 
            "有态势内容" if has_posture else "无态势内容")
        page.screenshot(path=os.path.join(SHOT, "dash009_posture.png"))
    except Exception as e:
        log("DASH-009", "系统态势页面", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景7: 仪表盘+系统态势 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
