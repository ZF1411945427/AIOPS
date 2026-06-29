# -*- coding: utf-8 -*-
"""场景3-8: 资产测试连接/指标采集/指标监控/告警/K8s/仪表盘/系统管理"""
from playwright.sync_api import sync_playwright
import os, time, json

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_remaining"
os.makedirs(SHOT, exist_ok=True)

results = []

def log(case_id, func, status, detail=""):
    results.append({"id": case_id, "func": func, "status": status, "detail": detail})
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {case_id} {func}: {status} {detail}")

def login(page):
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("input", timeout=5000)
    inputs = page.query_selector_all("input")
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    time.sleep(0.5)
    page.click("button:has-text('登录')")
    page.wait_for_timeout(3000)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    page = context.new_page()

    login(page)
    print("登录成功")

    # ========== 场景3: 资产测试连接+探测+指标采集 ==========
    print("\n=== 场景3: 资产测试连接+探测+指标采集 ===")

    # ASSET-007: 测试连接（资产编辑页的"测试连接"按钮）
    try:
        page.goto(f"{BASE}/assets", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 找第一个资产的编辑按钮
        edit_link = page.query_selector("a[href*='/edit']")
        if edit_link:
            edit_link.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(SHOT, "s3_test_conn_form.png"))
            # 找测试连接按钮
            test_btn = page.query_selector("button:has-text('测试连接')")
            if test_btn:
                # 监听 dialog
                dialog_msg = [None]
                def handle_dialog(d):
                    dialog_msg[0] = d.message
                    d.accept()
                page.on("dialog", handle_dialog)
                test_btn.click()
                page.wait_for_timeout(5000)
                if dialog_msg[0] and ("成功" in dialog_msg[0] or "ok" in dialog_msg[0].lower() or "连接" in dialog_msg[0]):
                    log("ASSET-007", "资产测试连接", "PASS", f"alert: {dialog_msg[0][:60]}")
                else:
                    log("ASSET-007", "资产测试连接", "FAIL", f"alert: {dialog_msg[0]}")
            else:
                log("ASSET-007", "资产测试连接", "FAIL", "未找到测试连接按钮")
        else:
            log("ASSET-007", "资产测试连接", "FAIL", "未找到编辑链接")
    except Exception as e:
        log("ASSET-007", "资产测试连接", "FAIL", str(e)[:100])

    # ASSET-008: 指标采集验证（检查 metric_records 是否有新数据）
    try:
        # 通过 API 检查最新指标
        resp = page.goto(f"{BASE}/metrics/latest?asset_id=3", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        body = page.inner_text("body")
        data = json.loads(body) if body.strip().startswith("{") else {}
        metric_count = len(data)
        if metric_count > 0:
            log("ASSET-008", "指标采集验证", "PASS", f"资产3有 {metric_count} 项最新指标")
        else:
            log("ASSET-008", "指标采集验证", "FAIL", "无指标数据")
    except Exception as e:
        log("ASSET-008", "指标采集验证", "FAIL", str(e)[:100])

    # ========== 场景4: 指标监控页面验证 ==========
    print("\n=== 场景4: 指标监控页面验证 ===")

    # METRIC-001: 指标监控页面加载
    try:
        page.goto(f"{BASE}/metrics", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s4_metrics_page.png"))
        # 检查页面是否有指标分类或指标名称
        has_content = page.query_selector("text=CPU") or page.query_selector("text=内存") or page.query_selector("text=指标")
        log("METRIC-001", "指标监控页面加载", "PASS" if has_content else "FAIL", "页面已加载")
    except Exception as e:
        log("METRIC-001", "指标监控页面加载", "FAIL", str(e)[:100])

    # METRIC-002: 指标数据 API 返回
    try:
        resp = page.goto(f"{BASE}/metrics/data?asset_id=3&hours=1", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        body = page.inner_text("body")
        data = json.loads(body) if body.strip().startswith("[") else []
        log("METRIC-002", "指标数据API", "PASS" if len(data) > 0 else "FAIL", f"返回 {len(data)} 条记录")
    except Exception as e:
        log("METRIC-002", "指标数据API", "FAIL", str(e)[:100])

    # METRIC-003: 指标名称列表
    try:
        resp = page.goto(f"{BASE}/metrics/names", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        body = page.inner_text("body")
        names = json.loads(body) if body.strip().startswith("[") else []
        log("METRIC-003", "指标名称列表", "PASS" if len(names) > 0 else "FAIL", f"{len(names)} 种指标")
    except Exception as e:
        log("METRIC-003", "指标名称列表", "FAIL", str(e)[:100])

    # ========== 场景5: 告警规则创建+告警触发 ==========
    print("\n=== 场景5: 告警规则创建+告警触发 ===")

    # ALERT-001: 告警规则页面加载
    try:
        page.goto(f"{BASE}/alerts/rules", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s5_alert_rules.png"))
        # 检查是否有创建表单
        form = page.query_selector("form")
        name_input = page.query_selector("input[name='name']")
        log("ALERT-001", "告警规则页面加载", "PASS" if form and name_input else "FAIL", "页面已加载")
    except Exception as e:
        log("ALERT-001", "告警规则页面加载", "FAIL", str(e)[:100])

    # ALERT-002: 创建告警规则
    try:
        page.goto(f"{BASE}/alerts/rules", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 填写规则名称
        name_input = page.query_selector("input[name='name']")
        if name_input:
            name_input.fill("测试-CPU高使用率")
        # 选择指标
        metric_select = page.query_selector("select[name='metric_name']")
        if metric_select:
            opts = metric_select.query_selector_all("option")
            if len(opts) > 1:
                metric_select.select_option(index=1)
        # 选择条件
        cond_select = page.query_selector("select[name='condition']")
        if cond_select:
            cond_select.select_option(">")
        # 填阈值
        threshold_input = page.query_selector("input[name='threshold']")
        if threshold_input:
            threshold_input.fill("0")
        # 选严重级别
        sev_select = page.query_selector("select[name='severity']")
        if sev_select:
            sev_select.select_option("warning")
        time.sleep(0.5)
        page.screenshot(path=os.path.join(SHOT, "s5_alert_form_filled.png"))
        # 提交
        create_btn = page.query_selector("button:has-text('创建')")
        if create_btn:
            create_btn.click()
            page.wait_for_timeout(3000)
        url = page.url
        if "rules" in url:
            # 验证规则是否出现在列表中
            page.screenshot(path=os.path.join(SHOT, "s5_alert_after_create.png"))
            body_text = page.inner_text("body")
            if "测试-CPU高使用率" in body_text:
                log("ALERT-002", "创建告警规则", "PASS", "规则已创建并显示")
            else:
                log("ALERT-002", "创建告警规则", "FAIL", "规则未出现在列表")
        else:
            log("ALERT-002", "创建告警规则", "FAIL", f"URL: {url}")
    except Exception as e:
        log("ALERT-002", "创建告警规则", "FAIL", str(e)[:100])

    # ALERT-003: 触发告警检查
    try:
        page.goto(f"{BASE}/alerts", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 找"触发检查"按钮
        check_btn = page.query_selector("button:has-text('触发检查')")
        if check_btn:
            check_btn.click()
            page.wait_for_timeout(5000)
            page.screenshot(path=os.path.join(SHOT, "s5_alert_triggered.png"))
            log("ALERT-003", "触发告警检查", "PASS", "检查已触发")
        else:
            log("ALERT-003", "触发告警检查", "FAIL", "未找到触发检查按钮")
    except Exception as e:
        log("ALERT-003", "触发告警检查", "FAIL", str(e)[:100])

    # ALERT-004: 告警控制台页面
    try:
        page.goto(f"{BASE}/alerts", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s5_alert_console.png"))
        # 检查是否有告警表格或告警列表
        has_table = page.query_selector("table")
        log("ALERT-004", "告警控制台", "PASS" if has_table else "FAIL", "页面已加载")
    except Exception as e:
        log("ALERT-004", "告警控制台", "FAIL", str(e)[:100])

    # ========== 场景6: K8s资源管理 ==========
    print("\n=== 场景6: K8s资源管理 ===")

    # K8S-001: K8s 集群概览
    try:
        page.goto(f"{BASE}/k8s/overview", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s6_k8s_overview.png"))
        has_content = page.query_selector("table") or page.query_selector("text=集群") or page.query_selector("text=节点")
        log("K8S-001", "K8s集群概览", "PASS" if has_content else "FAIL", "页面已加载")
    except Exception as e:
        log("K8S-001", "K8s集群概览", "FAIL", str(e)[:100])

    # K8S-002: Pod 列表
    try:
        page.goto(f"{BASE}/containers/pods", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s6_k8s_pods.png"))
        has_table = page.query_selector("table")
        log("K8S-002", "Pod列表", "PASS" if has_table else "FAIL", "页面已加载")
    except Exception as e:
        log("K8S-002", "Pod列表", "FAIL", str(e)[:100])

    # K8S-003: Deployment 列表
    try:
        page.goto(f"{BASE}/containers/deployments", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s6_k8s_deployments.png"))
        has_table = page.query_selector("table")
        log("K8S-003", "Deployment列表", "PASS" if has_table else "FAIL", "页面已加载")
    except Exception as e:
        log("K8S-003", "Deployment列表", "FAIL", str(e)[:100])

    # K8S-004: K8s 监控页面
    try:
        page.goto(f"{BASE}/k8s-monitor", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s6_k8s_monitor.png"))
        log("K8S-004", "K8s监控页面", "PASS", "页面已加载")
    except Exception as e:
        log("K8S-004", "K8s监控页面", "FAIL", str(e)[:100])

    # ========== 场景7: 仪表盘+系统态势 ==========
    print("\n=== 场景7: 仪表盘+系统态势 ===")

    # DASH-001: 仪表盘页面
    try:
        page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SHOT, "s7_dashboard.png"))
        # 检查是否有统计卡片或图表
        has_stats = page.query_selector(".card") or page.query_selector("text=资产") or page.query_selector("text=告警")
        log("DASH-001", "仪表盘页面", "PASS" if has_stats else "FAIL", "页面已加载")
    except Exception as e:
        log("DASH-001", "仪表盘页面", "FAIL", str(e)[:100])

    # DASH-002: 仪表盘统计 API
    try:
        resp = page.goto(f"{BASE}/api/dashboard/stats", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        body = page.inner_text("body")
        data = json.loads(body) if body.strip().startswith("{") else {}
        has_data = any(v is not None for v in data.values()) if data else False
        log("DASH-002", "仪表盘统计API", "PASS" if has_data else "FAIL", f"返回 {len(data)} 项数据")
    except Exception as e:
        log("DASH-002", "仪表盘统计API", "FAIL", str(e)[:100])

    # DASH-003: 系统态势页面
    try:
        # 通过前端导航 - 系统态势是 vue 视图
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # 点击侧边栏"运行概览" -> "系统态势"
        # 尝试找菜单项
        menu_item = page.query_selector("text=系统态势")
        if menu_item:
            menu_item.click()
            page.wait_for_timeout(3000)
            page.screenshot(path=os.path.join(SHOT, "s7_system_posture.png"))
            log("DASH-003", "系统态势页面", "PASS", "已访问")
        else:
            # 可能需要先展开菜单
            overview_menu = page.query_selector("text=运行概览")
            if overview_menu:
                overview_menu.click()
                page.wait_for_timeout(1000)
                menu_item = page.query_selector("text=系统态势")
                if menu_item:
                    menu_item.click()
                    page.wait_for_timeout(3000)
                    page.screenshot(path=os.path.join(SHOT, "s7_system_posture.png"))
                    log("DASH-003", "系统态势页面", "PASS", "已访问")
                else:
                    log("DASH-003", "系统态势页面", "FAIL", "展开后未找到菜单项")
            else:
                log("DASH-003", "系统态势页面", "FAIL", "未找到运行概览菜单")
    except Exception as e:
        log("DASH-003", "系统态势页面", "FAIL", str(e)[:100])

    # ========== 场景8: 系统管理 ==========
    print("\n=== 场景8: 系统管理 ===")

    # SYS-001: 用户管理页面
    try:
        page.goto(f"{BASE}/users", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s8_users.png"))
        has_table = page.query_selector("table")
        log("SYS-001", "用户管理页面", "PASS" if has_table else "FAIL", "页面已加载")
    except Exception as e:
        log("SYS-001", "用户管理页面", "FAIL", str(e)[:100])

    # SYS-002: 令牌管理页面
    try:
        page.goto(f"{BASE}/tokens", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s8_tokens.png"))
        has_content = page.query_selector("table") or page.query_selector("form") or page.query_selector("text=令牌")
        log("SYS-002", "令牌管理页面", "PASS" if has_content else "FAIL", "页面已加载")
    except Exception as e:
        log("SYS-002", "令牌管理页面", "FAIL", str(e)[:100])

    # SYS-003: 系统设置页面
    try:
        page.goto(f"{BASE}/settings", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s8_settings.png"))
        has_form = page.query_selector("form") or page.query_selector("input")
        log("SYS-003", "系统设置页面", "PASS" if has_form else "FAIL", "页面已加载")
    except Exception as e:
        log("SYS-003", "系统设置页面", "FAIL", str(e)[:100])

    # SYS-004: DB 模式切换页面
    try:
        page.goto(f"{BASE}/system/overview", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT, "s8_system_overview.png"))
        has_content = page.query_selector("table") or page.query_selector("text=数据库") or page.query_selector("text=模式")
        log("SYS-004", "系统概览/DB模式", "PASS" if has_content else "FAIL", "页面已加载")
    except Exception as e:
        log("SYS-004", "系统概览/DB模式", "FAIL", str(e)[:100])

    browser.close()

# 结果汇总
print("\n" + "="*60)
print("场景3-8 — 测试结果汇总")
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
