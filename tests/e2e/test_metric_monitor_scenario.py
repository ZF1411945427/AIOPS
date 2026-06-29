# -*- coding: utf-8 -*-
"""场景4: 指标监控页面验证 (METRIC-001~010)"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_metric"
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

    # === METRIC-001: 指标监控页面加载 ===
    try:
        page.goto(f"{BASE}/metrics", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page_text = page.inner_text("body")
        has_metrics = any(kw in page_text.lower() for kw in ["cpu", "memory", "load", "disk", "指标"])
        log("METRIC-001", "指标监控页面加载", "PASS" if has_metrics else "FAIL", 
            "页面有指标内容" if has_metrics else "页面无指标内容")
        page.screenshot(path=os.path.join(SHOT, "metric001.png"))
    except Exception as e:
        log("METRIC-001", "指标监控页面加载", "FAIL", str(e)[:100])

    # === METRIC-002: 指标分类展示 ===
    try:
        categories = []
        for kw in ["CPU", "内存", "内存", "负载", "磁盘", "网络"]:
            if kw in page_text:
                categories.append(kw)
        log("METRIC-002", "指标分类展示", "PASS" if len(categories) >= 2 else "FAIL", 
            f"找到 {len(categories)} 种分类: {categories}")
    except Exception as e:
        log("METRIC-002", "指标分类展示", "FAIL", str(e)[:100])

    # === METRIC-003: 多资产指标查看 ===
    try:
        select = page.query_selector("select, .el-select")
        log("METRIC-003", "多资产指标查看", "PASS" if select else "FAIL", 
            "资产选择器存在" if select else "未找到资产选择器")
    except Exception as e:
        log("METRIC-003", "多资产指标查看", "FAIL", str(e)[:100])

    # === METRIC-004: 单资产指标详情 ===
    try:
        cards = page.query_selector_all(".metric-card, .el-card, [class*='card']")
        log("METRIC-004", "单资产指标详情", "PASS" if len(cards) > 0 else "FAIL", 
            f"{len(cards)} 个指标卡片")
    except Exception as e:
        log("METRIC-004", "单资产指标详情", "FAIL", str(e)[:100])

    # === METRIC-005: 指标趋势图 ===
    try:
        charts = page.query_selector_all("canvas, svg, [class*='chart'], .echarts-chart, [_echarts_instance]")
        log("METRIC-005", "指标趋势图", "PASS" if len(charts) > 0 else "FAIL", 
            f"{len(charts)} 个图表元素")
    except Exception as e:
        log("METRIC-005", "指标趋势图", "FAIL", str(e)[:100])

    # === METRIC-006: 指标历史数据 ===
    try:
        # 检查页面是否有时间相关数据
        has_time = any(kw in page_text for kw in ["时间", "timestamp", "采集", "最后"])
        log("METRIC-006", "指标历史数据", "PASS" if has_time else "FAIL", 
            "有时间标注" if has_time else "无时间标注")
    except Exception as e:
        log("METRIC-006", "指标历史数据", "FAIL", str(e)[:100])

    # === METRIC-007: 离线资产历史指标标注 ===
    try:
        has_offline_label = any(kw in page_text for kw in ["离线", "offline", "历史数据"])
        log("METRIC-007", "离线资产历史指标标注", "PASS" if has_offline_label else "FAIL", 
            "有离线标注" if has_offline_label else "无离线标注")
    except Exception as e:
        log("METRIC-007", "离线资产历史指标标注", "FAIL", str(e)[:100])

    # === METRIC-008: 离线资产时间提示 ===
    try:
        has_time_hint = "最后采集" in page_text or "采集时间" in page_text
        log("METRIC-008", "离线资产时间提示", "PASS" if has_time_hint else "FAIL", 
            "有采集时间提示" if has_time_hint else "无采集时间提示")
    except Exception as e:
        log("METRIC-008", "离线资产时间提示", "FAIL", str(e)[:100])

    # === METRIC-009: 实时指标数据 ===
    try:
        # 刷新页面看看是否有最新数据
        page.reload(wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page_text2 = page.inner_text("body")
        # 检查是否有近期的数据 (今天)
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        today_short = datetime.datetime.now().strftime("%m-%d")
        has_recent = today in page_text2 or today_short in page_text2
        log("METRIC-009", "实时指标数据", "PASS" if has_recent else "FAIL", 
            f"有今日数据({today_short})" if has_recent else "未找到今日数据")
        page.screenshot(path=os.path.join(SHOT, "metric009_realtime.png"))
    except Exception as e:
        log("METRIC-009", "实时指标数据", "FAIL", str(e)[:100])

    # === METRIC-010: 指标数据导出/刷新 ===
    try:
        # 检查是否有刷新按钮
        refresh_btn = page.query_selector("button:has-text('刷新'), button:has-text('refresh'), [class*='refresh']")
        log("METRIC-010", "指标数据刷新", "PASS" if refresh_btn else "FAIL", 
            "有刷新按钮" if refresh_btn else "无刷新按钮")
    except Exception as e:
        log("METRIC-010", "指标数据刷新", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景4: 指标监控页面验证 — 测试结果汇总")
print("="*60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(f"通过: {passed}/{len(results)}  失败: {failed}/{len(results)}")
for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"  {icon} {r['id']} {r['func']}: {r['status']} {r['detail']}")

with open(os.path.join(SHOT, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
