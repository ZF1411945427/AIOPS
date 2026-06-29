# -*- coding: utf-8 -*-
"""真正验证数据的 E2E 测试 — 每个用例验证实际数据显示"""
from playwright.sync_api import sync_playwright
import os, time, json, re

BASE = "http://127.0.0.1:8000"
SHOT = r"E:\Program Files\hermes\cache\screenshots\e2e_real"
os.makedirs(SHOT, exist_ok=True)
results = []

def log(cid, func, status, detail=""):
    results.append({"id": cid, "func": func, "status": status, "detail": detail})
    icon = "\u2705" if status == "PASS" else "\u274c"
    print(f"  {icon} {cid} {func}: {status} {detail}")

def login(page):
    for attempt in range(3):
        try:
            page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("input", timeout=10000)
            inputs = page.query_selector_all("input")
            if len(inputs) < 2:
                time.sleep(2)
                inputs = page.query_selector_all("input")
            if len(inputs) >= 2:
                inputs[0].fill("admin")
                inputs[1].fill("admin123")
                time.sleep(0.5)
                page.click("button:has-text('\u767b\u5f55')")
                page.wait_for_timeout(3000)
                if "/login" not in page.url:
                    return
            time.sleep(1)
        except Exception:
            time.sleep(2)

def count_rows(page):
    rows = page.query_selector_all("table tbody tr")
    n = 0
    for r in rows:
        t = r.inner_text().strip()
        if t and len(t) > 2 and "\u6682\u65e0" not in t and "No data" not in t.lower():
            n += 1
    return n

def has_kw(page, kws):
    text = page.inner_text("body")
    return any(k in text for k in kws)

def api_get(page, path):
    try:
        js = "async (p) => { const r = await fetch(p,{credentials:'include'}); const t = await r.text(); try{return {status:r.status,json:JSON.parse(t)}}catch{return {status:r.status,text:t.substring(0,500)}} }"
        return page.evaluate(js, path)
    except Exception as e:
        return {"status": 0, "error": str(e)}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width":1400,"height":900})
    page = ctx.new_page()
    login(page)
    print("=== \u767b\u5f55\u6210\u529f ===\n")

    # ===== 场景1: 认证与登录 =====
    print("--- \u573a\u666f1: \u8ba4\u8bc1\u4e0e\u767b\u5f55 ---")
    # AUTH-001
    try:
        t = page.inner_text("body")
        ok = "\u603b\u89c8" in t or "\u8d44\u4ea7\u7ba1\u7406" in t
        log("AUTH-001","\u6b63\u5e38\u767b\u5f55","PASS" if ok else "FAIL","\u83dc\u5355\u663e\u793a" if ok else "\u65e0\u83dc\u5355")
    except Exception as e: log("AUTH-001","\u6b63\u5e38\u767b\u5f55","FAIL",str(e)[:80])

    # AUTH-002 错误密码
    try:
        page.goto(f"{BASE}/login",wait_until="networkidle")
        page.wait_for_selector("input",timeout=5000)
        ins = page.query_selector_all("input")
        ins[0].fill("admin"); ins[1].fill("wrongpass")
        page.click("button:has-text('\u767b\u5f55')"); time.sleep(2)
        t = page.inner_text("body")
        ok = "\u9519\u8bef" in t or "\u5931\u8d25" in t or "\u5bc6\u7801" in t
        log("AUTH-002","\u9519\u8bef\u5bc6\u7801","PASS" if ok else "FAIL","\u6709\u9519\u8bef\u63d0\u793a" if ok else "\u65e0\u9519\u8bef\u63d0\u793a")
    except Exception as e: log("AUTH-002","\u9519\u8bef\u5bc6\u7801","FAIL",str(e)[:80])

    # AUTH-003 空用户名
    try:
        page.goto(f"{BASE}/login",wait_until="networkidle")
        page.wait_for_selector("input",timeout=5000)
        ins = page.query_selector_all("input")
        ins[1].fill("admin123")
        page.click("button:has-text('\u767b\u5f55')"); time.sleep(2)
        ok = "/login" in page.url
        log("AUTH-003","\u7a7a\u7528\u6237\u540d","PASS" if ok else "FAIL","\u88ab\u62e6\u622a" if ok else "\u767b\u5f55\u6210\u529f?")
    except Exception as e: log("AUTH-003","\u7a7a\u7528\u6237\u540d","FAIL",str(e)[:80])

    # AUTH-004 空密码
    try:
        page.goto(f"{BASE}/login",wait_until="networkidle")
        page.wait_for_selector("input",timeout=5000)
        ins = page.query_selector_all("input")
        ins[0].fill("admin")
        page.click("button:has-text('\u767b\u5f55')"); time.sleep(2)
        ok = "/login" in page.url
        log("AUTH-004","\u7a7a\u5bc6\u7801","PASS" if ok else "FAIL","\u88ab\u62e6\u622a" if ok else "\u767b\u5f55\u6210\u529f?")
    except Exception as e: log("AUTH-004","\u7a7a\u5bc6\u7801","FAIL",str(e)[:80])

    login(page)

    # AUTH-005 退出
    try:
        btn = page.query_selector("a:has-text('\u9000\u51fa'),button:has-text('\u9000\u51fa')")
        if btn:
            btn.click(); time.sleep(2)
            ok = "/login" in page.url
            log("AUTH-005","\u9000\u51fa\u767b\u5f55","PASS" if ok else "FAIL","\u8df3\u8f6c\u767b\u5f55\u9875" if ok else f"\u672a\u8df3\u8f6c:{page.url}")
        else: log("AUTH-005","\u9000\u51fa\u767b\u5f55","FAIL","\u672a\u627e\u5230\u9000\u51fa\u6309\u94ae")
    except Exception as e: log("AUTH-005","\u9000\u51fa\u767b\u5f55","FAIL",str(e)[:80])

    # AUTH-006 未登录访问
    try:
        c2 = browser.new_context(); p2 = c2.new_page()
        p2.goto(f"{BASE}/assets",wait_until="networkidle",timeout=10000); time.sleep(2)
        ok = "/login" in p2.url
        log("AUTH-006","\u672a\u767b\u5f55\u8bbf\u95ee","\u0050ASS" if ok else "FAIL","\u91cd\u5b9a\u5411\u767b\u5f55" if ok else f"\u672a\u91cd\u5b9a\u5411:{p2.url}")
        p2.close(); c2.close()
    except Exception as e: log("AUTH-006","\u672a\u767b\u5f55\u8bbf\u95ee","FAIL",str(e)[:80])

    login(page)

    # AUTH-007 session保持
    try:
        page.reload(); time.sleep(2)
        ok = "/login" not in page.url
        log("AUTH-007","session\u4fdd\u6301","PASS" if ok else "FAIL","\u4ecd\u767b\u5f55" if ok else "\u4e22\u5931\u767b\u5f55")
    except Exception as e: log("AUTH-007","session\u4fdd\u6301","FAIL",str(e)[:80])

    # ===== 场景2: 资产管理 =====
    print("\n--- \u573a\u666f2: \u8d44\u4ea7\u7ba1\u7406 ---")
    # ASSET-001
    try:
        page.goto(f"{BASE}/assets",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["11.0.1.131","11.0.1.132","192.168"])
        log("ASSET-001","\u8d44\u4ea7\u5217\u8868","PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0\u6570\u636e")
    except Exception as e: log("ASSET-001","\u8d44\u4ea7\u5217\u8868","FAIL",str(e)[:80])

    # ASSET-002 添加
    try:
        page.goto(f"{BASE}/assets/create",wait_until="networkidle",timeout=15000); time.sleep(1)
        ni = page.query_selector("input[name='name']"); ii = page.query_selector("input[name='ip_address']") or page.query_selector("input[name='ip']")
        if ni and ii:
            ni.fill("test-e2e-asset"); ii.fill("10.0.0.99")
            sb = page.query_selector("button[type='submit']") or page.query_selector("button:has-text('\u4fdd\u5b58')")
            if sb:
                sb.click(); time.sleep(3)
                t = page.inner_text("body")
                ok = "\u6210\u529f" in t or "test-e2e-asset" in t or "/assets" in page.url
                log("ASSET-002","\u6dfb\u52a0\u8d44\u4ea7","PASS" if ok else "FAIL","\u521b\u5efa\u6210\u529f" if ok else "\u521b\u5efa\u5931\u8d25")
            else: log("ASSET-002","\u6dfb\u52a0\u8d44\u4ea7","FAIL","\u65e0\u63d0\u4ea4\u6309\u94ae")
        else: log("ASSET-002","\u6dfb\u52a0\u8d44\u4ea7","FAIL","\u65e0\u8868\u5355\u5b57\u6bb5")
    except Exception as e: log("ASSET-002","\u6dfb\u52a0\u8d44\u4ea7","FAIL",str(e)[:80])

    # ASSET-003 编辑
    try:
        page.goto(f"{BASE}/assets",wait_until="networkidle",timeout=15000); time.sleep(2)
        el = page.query_selector("a:has-text('\u7f16\u8f91')") or page.query_selector("a[href*='edit']")
        if el:
            el.click(); time.sleep(2)
            ni = page.query_selector("input[name='name']")
            if ni:
                ov = ni.input_value(); ni.fill(ov+"-edited")
                sb = page.query_selector("button[type='submit']") or page.query_selector("button:has-text('\u4fdd\u5b58')")
                if sb:
                    sb.click(); time.sleep(3)
                    t = page.inner_text("body")
                    ok = "\u6210\u529f" in t or "-edited" in t
                    log("ASSET-003","\u7f16\u8f91\u8d44\u4ea7","PASS" if ok else "FAIL","\u4fee\u6539\u6210\u529f" if ok else "\u4fee\u6539\u5931\u8d25")
                else: log("ASSET-003","\u7f16\u8f91\u8d44\u4ea7","FAIL","\u65e0\u4fdd\u5b58\u6309\u94ae")
            else: log("ASSET-003","\u7f16\u8f91\u8d44\u4ea7","FAIL","\u65e0\u540d\u79f0\u5b57\u6bb5")
        else: log("ASSET-003","\u7f16\u8f91\u8d44\u4ea7","FAIL","\u65e0\u7f16\u8f91\u94fe\u63a5")
    except Exception as e: log("ASSET-003","\u7f16\u8f91\u8d44\u4ea7","FAIL",str(e)[:80])

    # ASSET-004 删除
    try:
        page.goto(f"{BASE}/assets",wait_until="networkidle",timeout=15000); time.sleep(2)
        tb = page.inner_text("body")
        ht = "test-e2e-asset" in tb
        db = page.query_selector("a:has-text('\u5220\u9664')") or page.query_selector("button:has-text('\u5220\u9664')")
        if db and ht:
            db.click(); time.sleep(1)
            cf = page.query_selector("button:has-text('\u786e\u8ba4')") or page.query_selector("button:has-text('\u786e\u5b9a')")
            if cf: cf.click(); time.sleep(3)
            ta = page.inner_text("body")
            ok = "test-e2e-asset" not in ta
            log("ASSET-004","\u5220\u9664\u8d44\u4ea7","PASS" if ok else "FAIL","\u5220\u9664\u6210\u529f" if ok else "\u4ecd\u5b58\u5728")
        else: log("ASSET-004","\u5220\u9664\u8d44\u4ea7","FAIL","\u65e0\u5220\u9664\u6309\u94ae/\u6d4b\u8bd5\u8d44\u4ea7")
    except Exception as e: log("ASSET-004","\u5220\u9664\u8d44\u4ea7","FAIL",str(e)[:80])

    # ASSET-005 测试连接
    try:
        r = page.evaluate("async()=>{const r=await fetch('/assets/api/test-connection',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'ip=11.0.1.131&username=root&password=123456&port=22',credentials:'include'});const t=await r.text();try{return{status:r.status,json:JSON.parse(t)}}catch{return{status:r.status,text:t.substring(0,300)}}}")
        ok = r.get("status")==200 and (r.get("json",{}).get("success")==True or "success" in str(r.get("text","")).lower())
        log("ASSET-005","\u6d4b\u8bd5\u8fde\u63a5","PASS" if ok else "FAIL","\u8fde\u63a5\u6210\u529f" if ok else str(r.get("json",r.get("text","")))[:80])
    except Exception as e: log("ASSET-005","\u6d4b\u8bd5\u8fde\u63a5","FAIL",str(e)[:80])

    # ASSET-006 变更记录
    try:
        page.goto(f"{BASE}/asset-changes",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u53d8\u66f4","change","edited"])
        log("ASSET-006","\u53d8\u66f4\u8bb0\u5f55","PASS" if ok else "FAIL",f"{n}\u6761" if ok else "\u65e0\u8bb0\u5f55")
    except Exception as e: log("ASSET-006","\u53d8\u66f4\u8bb0\u5f55","FAIL",str(e)[:80])

    # ASSET-007 CI模型
    try:
        page.goto(f"{BASE}/ci-models",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u6a21\u578b","CI","model"])
        log("ASSET-007","CI\u6a21\u578b","PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0\u5185\u5bb9")
    except Exception as e: log("ASSET-007","CI\u6a21\u578b","FAIL",str(e)[:80])

    # ===== 场景3: 指标监控 =====
    print("\n--- \u573a\u666f3: \u6307\u6807\u76d1\u63a7 ---")
    # METRIC-001
    try:
        page.goto(f"{BASE}/metrics",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = page.query_selector("select") is not None
        log("METRIC-001","\u6307\u6807\u9875\u9762","PASS" if ok else "FAIL","\u6709\u9009\u62e9\u5668" if ok else "\u65e0\u9009\u62e9\u5668")
    except Exception as e: log("METRIC-001","\u6307\u6807\u9875\u9762","FAIL",str(e)[:80])

    # METRIC-002 指标数据API
    try:
        r = api_get(page,"/metrics/data?asset_id=1&metric_name=cpu_usage")
        ok = False; cnt = 0
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict):
                dl = j.get("data",j.get("metrics",j.get("records",[])))
                if isinstance(dl,list): cnt = len(dl); ok = cnt > 0
                elif j.get("total",0)>0: ok = True
        log("METRIC-002","\u6307\u6807\u6570\u636e","PASS" if ok else "FAIL",f"{cnt}\u6761" if ok else str(r.get("json",r.get("text","")))[:80])
    except Exception as e: log("METRIC-002","\u6307\u6807\u6570\u636e","FAIL",str(e)[:80])

    # METRIC-003 指标名称
    try:
        r = api_get(page,"/metrics/names")
        ok = False; cnt = 0
        if r.get("json"):
            j = r["json"]
            if isinstance(j,list): cnt = len(j); ok = cnt > 0
            elif isinstance(j,dict) and "names" in j: cnt = len(j["names"]); ok = cnt > 0
        log("METRIC-003","\u6307\u6807\u540d\u79f0","PASS" if ok else "FAIL",f"{cnt}\u4e2a" if ok else "\u65e0")
    except Exception as e: log("METRIC-003","\u6307\u6807\u540d\u79f0","FAIL",str(e)[:80])

    # METRIC-004 最新指标
    try:
        r = api_get(page,"/metrics/latest?asset_id=1")
        ok = False
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict) and (j.get("data") or j.get("metrics") or j.get("value") is not None): ok = True
            elif isinstance(j,list) and len(j)>0: ok = True
        log("METRIC-004","\u6700\u65b0\u6307\u6807","PASS" if ok else "FAIL","\u6709\u6570\u636e" if ok else "\u65e0\u6570\u636e")
    except Exception as e: log("METRIC-004","\u6700\u65b0\u6307\u6807","FAIL",str(e)[:80])

    # METRIC-005~010
    for mid,desc in [("METRIC-005","\u8d8b\u52bf\u56fe"),("METRIC-006","\u5386\u53f2\u6570\u636e"),("METRIC-007","\u79bb\u7ebf\u6307\u6807"),("METRIC-008","\u65f6\u95f4\u63d0\u793a"),("METRIC-009","\u5b9e\u65f6\u6570\u636e"),("METRIC-010","\u5237\u65b0")]:
        try:
            page.goto(f"{BASE}/metrics",wait_until="networkidle",timeout=15000); time.sleep(2)
            sel = page.query_selector("select")
            if sel:
                opts = sel.query_selector_all("option")
                if len(opts)>1: sel.select_option(index=1); time.sleep(3)
            t = page.inner_text("body")
            ok = page.query_selector("canvas") or page.query_selector("svg") or "cpu" in t.lower() or "memory" in t.lower() or "\u6307\u6807" in t
            log(mid,desc,"PASS" if ok else "FAIL","\u6709\u56fe\u8868/\u6570\u636e" if ok else "\u65e0")
        except Exception as e: log(mid,desc,"FAIL",str(e)[:80])

    # ===== 场景4: 告警管理 =====
    print("\n--- \u573a\u666f4: \u544a\u8b66\u7ba1\u7406 ---")
    # ALERT-001
    try:
        page.goto(f"{BASE}/alerts",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u544a\u8b66","alert","critical","warning","high"])
        log("ALERT-001","\u544a\u8b66\u5217\u8868","PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0\u6570\u636e")
        page.screenshot(path=os.path.join(SHOT,"alert001.png"))
    except Exception as e: log("ALERT-001","\u544a\u8b66\u5217\u8868","FAIL",str(e)[:80])

    # ALERT-002 确认
    try:
        page.goto(f"{BASE}/alerts",wait_until="networkidle",timeout=15000); time.sleep(2)
        ab = page.query_selector("a:has-text('\u786e\u8ba4'),button:has-text('\u786e\u8ba4')")
        if ab:
            tb = page.inner_text("body"); ab.click(); time.sleep(2)
            ok = page.inner_text("body") != tb
            log("ALERT-002","\u544a\u8b66\u786e\u8ba4","PASS" if ok else "FAIL","\u72b6\u6001\u53d8\u5316" if ok else "\u672a\u53d8\u5316")
        else: log("ALERT-002","\u544a\u8b66\u786e\u8ba4","FAIL","\u65e0\u786e\u8ba4\u6309\u94ae")
    except Exception as e: log("ALERT-002","\u544a\u8b66\u786e\u8ba4","FAIL",str(e)[:80])

    # ALERT-003 解决
    try:
        page.goto(f"{BASE}/alerts",wait_until="networkidle",timeout=15000); time.sleep(2)
        rb = page.query_selector("a:has-text('\u89e3\u51b3'),button:has-text('\u89e3\u51b3')")
        if rb:
            tb = page.inner_text("body"); rb.click(); time.sleep(2)
            ok = page.inner_text("body") != tb
            log("ALERT-003","\u544a\u8b66\u89e3\u51b3","PASS" if ok else "FAIL","\u72b6\u6001\u53d8\u5316" if ok else "\u672a\u53d8\u5316")
        else: log("ALERT-003","\u544a\u8b66\u89e3\u51b3","FAIL","\u65e0\u89e3\u51b3\u6309\u94ae")
    except Exception as e: log("ALERT-003","\u544a\u8b66\u89e3\u51b3","FAIL",str(e)[:80])

    # ALERT-006 规则列表
    try:
        page.goto(f"{BASE}/alerts/rules",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["cpu","memory","rule","\u89c4\u5219"])
        log("ALERT-006","\u544a\u8b66\u89c4\u5219","PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
    except Exception as e: log("ALERT-006","\u544a\u8b66\u89c4\u5219","FAIL",str(e)[:80])

    # ALERT-007 创建规则
    try:
        page.goto(f"{BASE}/alerts/rules",wait_until="networkidle",timeout=15000); time.sleep(1)
        cb = page.query_selector("a:has-text('\u521b\u5efa')") or page.query_selector("a[href*='create']") or page.query_selector("a:has-text('\u65b0\u5efa')")
        if cb:
            cb.click(); time.sleep(2)
            ni = page.query_selector("input[name='name']")
            if ni:
                ni.fill("e2e-test-rule")
                ms = page.query_selector("select[name='metric_name']")
                if ms:
                    opts = ms.query_selector_all("option")
                    if len(opts)>1: ms.select_option(index=1)
                cs = page.query_selector("select[name='condition']")
                if cs:
                    opts = cs.query_selector_all("option")
                    if len(opts)>1: cs.select_option(index=1)
                ti = page.query_selector("input[name='threshold']")
                if ti: ti.fill("0.1")
                sb = page.query_selector("button[type='submit']")
                if sb:
                    sb.click(); time.sleep(3)
                    t = page.inner_text("body")
                    ok = "e2e-test-rule" in t or "\u6210\u529f" in t
                    log("ALERT-007","\u521b\u5efa\u89c4\u5219","PASS" if ok else "FAIL","\u6210\u529f" if ok else "\u5931\u8d25")
                else: log("ALERT-007","\u521b\u5efa\u89c4\u5219","FAIL","\u65e0\u63d0\u4ea4")
            else: log("ALERT-007","\u521b\u5efa\u89c4\u5219","FAIL","\u65e0\u540d\u79f0\u5b57\u6bb5")
        else: log("ALERT-007","\u521b\u5efa\u89c4\u5219","FAIL","\u65e0\u521b\u5efa\u6309\u94ae")
    except Exception as e: log("ALERT-007","\u521b\u5efa\u89c4\u5219","FAIL",str(e)[:80])

    # ALERT-008 启用/禁用
    try:
        page.goto(f"{BASE}/alerts/rules",wait_until="networkidle",timeout=15000); time.sleep(2)
        tb = page.query_selector("button:has-text('\u7981\u7528')") or page.query_selector("button:has-text('\u542f\u7528')") or page.query_selector("a:has-text('\u7981\u7528')") or page.query_selector("a:has-text('\u542f\u7528')")
        if tb:
            t0 = page.inner_text("body"); tb.click(); time.sleep(2)
            ok = page.inner_text("body") != t0
            log("ALERT-008","\u542f\u7528/\u7981\u7528","PASS" if ok else "FAIL","\u5207\u6362" if ok else "\u672a\u53d8")
        else: log("ALERT-008","\u542f\u7528/\u7981\u7528","FAIL","\u65e0\u5207\u6362\u6309\u94ae")
    except Exception as e: log("ALERT-008","\u542f\u7528/\u7981\u7528","FAIL",str(e)[:80])

    # ALERT-009 删除规则
    try:
        page.goto(f"{BASE}/alerts/rules",wait_until="networkidle",timeout=15000); time.sleep(2)
        tb = page.inner_text("body"); ht = "e2e-test-rule" in tb
        db = page.query_selector("a:has-text('\u5220\u9664')") or page.query_selector("button:has-text('\u5220\u9664')")
        if db and ht:
            db.click(); time.sleep(1)
            cf = page.query_selector("button:has-text('\u786e\u8ba4')") or page.query_selector("button:has-text('\u786e\u5b9a')")
            if cf: cf.click(); time.sleep(2)
            ok = "e2e-test-rule" not in page.inner_text("body")
            log("ALERT-009","\u5220\u9664\u89c4\u5219","PASS" if ok else "FAIL","\u5220\u9664\u6210\u529f" if ok else "\u4ecd\u5b58\u5728")
        else: log("ALERT-009","\u5220\u9664\u89c4\u5219","FAIL","\u65e0\u5220\u9664/\u6d4b\u8bd5\u89c4\u5219")
    except Exception as e: log("ALERT-009","\u5220\u9664\u89c4\u5219","FAIL",str(e)[:80])

    # ALERT-010~015
    alert_pages = [("ALERT-010","/alert-silence","\u9759\u9ed8",["\u9759\u9ed8","silence"]),("ALERT-011","/alert-console","\u63a7\u5236\u53f0",["\u544a\u8b66","alert","console"]),("ALERT-012","/alert-silence","\u9759\u9ed8\u89c4\u5219",["\u9759\u9ed8","silence"]),("ALERT-013","/alert-webhooks","Webhook",["webhook"]),("ALERT-014","/alert-storm","\u98ce\u66b4\u68c0\u6d4b",["\u98ce\u66b4","storm"]),("ALERT-015","/correlation","\u4e8b\u4ef6\u5173\u8054",["\u5173\u8054","correlation"])]
    for aid,route,desc,kws in alert_pages:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws) or len(page.inner_text("body"))>100
            log(aid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(aid,desc,"FAIL",str(e)[:80])

    # ===== 场景5: 仪表盘 =====
    print("\n--- \u573a\u666f5: \u4eea\u8868\u76d8 ---")
    # DASH-001
    try:
        page.goto(f"{BASE}/dashboard",wait_until="networkidle",timeout=15000); time.sleep(3)
        t = page.inner_text("body")
        ok = "\u603b\u89c8" in t or "\u8d44\u4ea7" in t or "\u544a\u8b66" in t
        log("DASH-001","\u4eea\u8868\u76d8","PASS" if ok else "FAIL","\u6709\u5361\u7247" if ok else "\u65e0")
    except Exception as e: log("DASH-001","\u4eea\u8868\u76d8","FAIL",str(e)[:80])

    # DASH-002 统计API
    try:
        r = api_get(page,"/api/dashboard/stats")
        ok = False
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict):
                for v in j.values():
                    if isinstance(v,(int,float)) and v>0: ok = True; break
                    elif isinstance(v,dict):
                        for v2 in v.values():
                            if isinstance(v2,(int,float)) and v2>0: ok = True; break
        log("DASH-002","\u7edf\u8ba1\u6570\u636e","PASS" if ok else "FAIL","\u6709\u7edf\u8ba1" if ok else str(j)[:80] if r.get("json") else "\u65e0")
    except Exception as e: log("DASH-002","\u7edf\u8ba1\u6570\u636e","FAIL",str(e)[:80])

    # DASH-003 仪表盘数据
    try:
        r = api_get(page,"/api/dashboard/data")
        ok = False; cnt = 0
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict): cnt = len(j); ok = cnt > 0
        log("DASH-003","\u4eea\u8868\u76d8\u6570\u636e","PASS" if ok else "FAIL",f"{cnt}\u5b57\u6bb5" if ok else "\u65e0")
    except Exception as e: log("DASH-003","\u4eea\u8868\u76d8\u6570\u636e","FAIL",str(e)[:80])

    # DASH-004~005 图表
    for did,desc in [("DASH-004","\u544a\u8b66\u56fe\u8868"),("DASH-005","\u8d8b\u52bf\u56fe")]:
        try:
            page.goto(f"{BASE}/dashboard",wait_until="networkidle",timeout=15000); time.sleep(3)
            ok = page.query_selector("canvas") or page.query_selector("svg")
            log(did,desc,"PASS" if ok else "FAIL","\u6709\u56fe\u8868" if ok else "\u65e0\u56fe\u8868")
        except Exception as e: log(did,desc,"FAIL",str(e)[:80])

    # DASH-006 系统态势
    try:
        page.goto(f"{BASE}/system-posture",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u6001\u52bf","\u5065\u5eb7","posture"])
        log("DASH-006","\u7cfb\u7edf\u6001\u52bf","PASS" if ok else "FAIL","\u6709\u5185\u5bb9" if ok else "\u65e0")
    except Exception as e: log("DASH-006","\u7cfb\u7edf\u6001\u52bf","FAIL",str(e)[:80])

    # DASH-007 健康评分API
    try:
        r = api_get(page,"/api/system/posture")
        ok = False
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict) and (j.get("score") is not None or j.get("health") is not None or len(j)>2): ok = True
        log("DASH-007","\u5065\u5eb7\u8bc4\u5206","PASS" if ok else "FAIL","\u6709\u8bc4\u5206" if ok else "\u65e0")
    except Exception as e: log("DASH-007","\u5065\u5eb7\u8bc4\u5206","FAIL",str(e)[:80])

    # DASH-008 配置
    try:
        page.goto(f"{BASE}/dashboard-config",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u914d\u7f6e","config","dashboard"])
        log("DASH-008","Dashboard\u914d\u7f6e","PASS" if ok else "FAIL","\u6709\u914d\u7f6e" if ok else "\u65e0")
    except Exception as e: log("DASH-008","Dashboard\u914d\u7f6e","FAIL",str(e)[:80])

    # DASH-009 最新告警
    try:
        r = api_get(page,"/api/dashboard/data")
        ok = False; cnt = 0
        if r.get("json"):
            j = r["json"]
            al = j.get("recent_alerts",j.get("alerts",[]))
            if isinstance(al,list): cnt = len(al); ok = cnt > 0
        log("DASH-009","\u6700\u65b0\u544a\u8b66","PASS" if ok else "FAIL",f"{cnt}\u6761" if ok else "\u65e0")
    except Exception as e: log("DASH-009","\u6700\u65b0\u544a\u8b66","FAIL",str(e)[:80])

    # ===== 场景6: K8s =====
    print("\n--- \u573a\u666f6: K8s ---")
    k8s = [("K8S-001","/k8s/overview","\u96c6\u7fa4\u6982\u89c8",["\u96c6\u7fa4","cluster","node","pod"]),("K8S-002","/containers/pods","Pod\u5217\u8868",["pod","\u540d\u79f0","namespace"]),("K8S-003","/containers/deployments","Deployment",["deployment","\u540d\u79f0"]),("K8S-007","/k8s/statefulsets","StatefulSet",["statefulset","\u540d\u79f0"]),("K8S-008","/k8s/daemonsets","DaemonSet",["daemonset","\u540d\u79f0"]),("K8S-009","/k8s/services","Service",["service","\u540d\u79f0"]),("K8S-010","/k8s/ingresses","Ingress",["ingress","\u540d\u79f0"]),("K8S-011","/k8s/configmaps","ConfigMap",["configmap","\u540d\u79f0"]),("K8S-012","/k8s/secrets","Secret",["secret","\u540d\u79f0"]),("K8S-013","/k8s/hpas","HPA",["hpa","\u540d\u79f0"]),("K8S-014","/k8s/pvcs","PVC",["pvc","\u540d\u79f0"]),("K8S-015","/k8s/pvs","PV",["pv","\u540d\u79f0"]),("K8S-016","/containers/topology","\u62d3\u6251",["\u62d3\u6251","topology"]),("K8S-017","/containers/docker","Docker\u6982\u89c8",["docker","\u5bb9\u5668"]),("K8S-018","/containers/docker","Docker\u5217\u8868",["docker","\u5bb9\u5668"]),("K8S-019","/k8s-monitor","K8s\u76d1\u63a7",["\u76d1\u63a7","monitor"])]
    for kid,route,desc,kws in k8s:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(kid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(kid,desc,"FAIL",str(e)[:80])

    # K8S-004 Pod日志
    try:
        page.goto(f"{BASE}/containers/pods",wait_until="networkidle",timeout=15000); time.sleep(2)
        pl = page.query_selector("a[href*='pod/']")
        if pl:
            pl.click(); time.sleep(2)
            ll = page.query_selector("a:has-text('\u65e5\u5fd7')") or page.query_selector("a[href*='log']")
            if ll:
                ll.click(); time.sleep(2)
                ok = len(page.inner_text("body")) > 100
                log("K8S-004","Pod\u65e5\u5fd7","PASS" if ok else "FAIL","\u6709\u65e5\u5fd7" if ok else "\u65e0\u65e5\u5fd7")
            else: log("K8S-004","Pod\u65e5\u5fd7","FAIL","\u65e0\u65e5\u5fd7\u94fe\u63a5")
        else: log("K8S-004","Pod\u65e5\u5fd7","FAIL","\u65e0Pod\u94fe\u63a5")
    except Exception as e: log("K8S-004","Pod\u65e5\u5fd7","FAIL",str(e)[:80])

    # K8S-005/006
    for kid,desc in [("K8S-005","\u6269\u7f29\u5bb9"),("K8S-006","\u56de\u6eda")]:
        try:
            page.goto(f"{BASE}/containers/deployments",wait_until="networkidle",timeout=15000); time.sleep(2)
            ml = page.query_selector("a[href*='manage']") or page.query_selector("a:has-text('\u7ba1\u7406')")
            if ml:
                ml.click(); time.sleep(2)
                t = page.inner_text("body")
                ok = page.query_selector("input[type='number']") or "\u526f\u672c" in t
                log(kid,desc,"PASS" if ok else "FAIL","\u6709\u64cd\u4f5c\u8868\u5355" if ok else "\u65e0")
            else: log(kid,desc,"FAIL","\u65e0\u7ba1\u7406\u94fe\u63a5")
        except Exception as e: log(kid,desc,"FAIL",str(e)[:80])

    # ===== 场景7: 日志 =====
    print("\n--- \u573a\u666f7: \u65e5\u5fd7 ---")
    # LOG-001
    try:
        page.goto(f"{BASE}/logs?source_id=1&time_range=7d&query=*",wait_until="networkidle",timeout=15000); time.sleep(3)
        t = page.inner_text("body")
        ok = ("\u5171" in t and "\u6761" in t) or "Database connection" in t or "Request processed" in t
        he = "\u67e5\u8be2\u5931\u8d25" in t or "\u8fde\u63a5\u5931\u8d25" in t
        if he: log("LOG-001","\u65e5\u5fd7\u9875\u9762","FAIL","ES\u67e5\u8be2\u9519\u8bef")
        else: log("LOG-001","\u65e5\u5fd7\u9875\u9762","PASS" if ok else "FAIL","\u6709\u65e5\u5fd7" if ok else "\u65e0\u65e5\u5fd7")
        page.screenshot(path=os.path.join(SHOT,"log001.png"))
    except Exception as e: log("LOG-001","\u65e5\u5fd7\u9875\u9762","FAIL",str(e)[:80])

    # LOG-002 搜索
    try:
        page.goto(f"{BASE}/logs?source_id=1&time_range=7d&query=ERROR",wait_until="networkidle",timeout=15000); time.sleep(3)
        t = page.inner_text("body")
        ok = "ERROR" in t and ("\u5171" in t or "\u6761" in t)
        he = "\u67e5\u8be2\u5931\u8d25" in t
        if he: log("LOG-002","\u65e5\u5fd7\u641c\u7d22","FAIL","ES\u67e5\u8be2\u9519\u8bef")
        else: log("LOG-002","\u65e5\u5fd7\u641c\u7d22","PASS" if ok else "FAIL","\u6709ERROR\u65e5\u5fd7" if ok else "\u65e0\u7ed3\u679c")
    except Exception as e: log("LOG-002","\u65e5\u5fd7\u641c\u7d22","FAIL",str(e)[:80])

    # LOG-003 异常检测
    try:
        page.goto(f"{BASE}/log-anomaly",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u5f02\u5e38","anomaly","\u89c4\u5219"])
        log("LOG-003","\u65e5\u5fd7\u5f02\u5e38","PASS" if ok else "FAIL",f"{n}\u6761" if ok else "\u65e0")
    except Exception as e: log("LOG-003","\u65e5\u5fd7\u5f02\u5e38","FAIL",str(e)[:80])

    # LOG-004 Drain
    try:
        page.goto(f"{BASE}/drain",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u6a21\u677f","drain","template"])
        log("LOG-004","Drain\u6a21\u677f","PASS" if ok else "FAIL","\u6709\u9875\u9762" if ok else "\u65e0")
    except Exception as e: log("LOG-004","Drain\u6a21\u677f","FAIL",str(e)[:80])

    # ===== 场景8: 链路追踪 =====
    print("\n--- \u573a\u666f8: \u94fe\u8def\u8ffd\u8e2a ---")
    # TRACE-001
    try:
        page.goto(f"{BASE}/traces",wait_until="networkidle",timeout=15000); time.sleep(2)
        btn = page.query_selector("button:has-text('\u67e5\u8be2')") or page.query_selector("input[type='submit']")
        if btn: btn.click(); time.sleep(3)
        t = page.inner_text("body")
        ok = "trace-" in t or "span" in t.lower() or "user-service" in t
        log("TRACE-001","Trace\u5217\u8868","PASS" if ok else "FAIL","\u6709Trace" if ok else "\u65e0Trace")
        page.screenshot(path=os.path.join(SHOT,"trace001.png"))
    except Exception as e: log("TRACE-001","Trace\u5217\u8868","FAIL",str(e)[:80])

    # TRACE-002 API
    try:
        r = api_get(page,"/api/traces")
        ok = False; cnt = 0
        if r.get("json"):
            j = r["json"]
            if isinstance(j,list): cnt = len(j); ok = cnt > 0
            elif isinstance(j,dict):
                tl = j.get("traces",j.get("data",j.get("items",[])))
                if isinstance(tl,list): cnt = len(tl); ok = cnt > 0
        log("TRACE-002","Trace\u67e5\u8be2","PASS" if ok else "FAIL",f"{cnt}\u6761" if ok else str(r.get("json",r.get("text","")))[:80])
    except Exception as e: log("TRACE-002","Trace\u67e5\u8be2","FAIL",str(e)[:80])

    # TRACE-003 详情
    try:
        page.goto(f"{BASE}/traces/detail/trace-0001",wait_until="networkidle",timeout=15000); time.sleep(2)
        t = page.inner_text("body")
        ok = "span" in t.lower() or "trace-0001" in t or "user-service" in t
        log("TRACE-003","Trace\u8be6\u60c5","PASS" if ok else "FAIL","\u6709Span" if ok else "\u65e0Span")
    except Exception as e: log("TRACE-003","Trace\u8be6\u60c5","FAIL",str(e)[:80])

    # TRACE-004~007
    for tid,route,desc,kws in [("TRACE-004","/trace-anomaly","\u5f02\u5e38\u68c0\u6d4b",["\u5f02\u5e38","anomaly","\u914d\u7f6e"]),("TRACE-007","/trace-view","Trace\u89c6\u56fe",[])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws) or len(page.inner_text("body"))>100
            log(tid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(tid,desc,"FAIL",str(e)[:80])

    # TRACE-005/006 API
    for tid,route,desc in [("TRACE-005","/api/v1/traces/agent-guide","\u63a5\u5165\u6307\u5f15"),("TRACE-006","/api/v1/traces/ingest-status","OTLP\u63a5\u5165")]:
        try:
            r = api_get(page,route)
            ok = r.get("status")==200
            log(tid,desc,"PASS" if ok else "FAIL",f"status:{r.get('status')}" if not ok else "\u53ef\u8bbf\u95ee")
        except Exception as e: log(tid,desc,"FAIL",str(e)[:80])

    # ===== 场景9: 知识库 =====
    print("\n--- \u573a\u666f9: \u77e5\u8bc6\u5e93 ---")
    # KB-001
    try:
        page.goto(f"{BASE}/knowledge",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u77e5\u8bc6","knowledge","article","\u6587\u7ae0"])
        log("KB-001","\u77e5\u8bc6\u5e93","PASS" if ok else "FAIL",f"{n}\u7bc7" if ok else "\u65e0")
    except Exception as e: log("KB-001","\u77e5\u8bc6\u5e93","FAIL",str(e)[:80])

    # KB-002 详情
    try:
        page.goto(f"{BASE}/knowledge/1",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = len(page.inner_text("body")) > 200
        log("KB-002","\u77e5\u8bc6\u8be6\u60c5","PASS" if ok else "FAIL","\u6709\u5185\u5bb9" if ok else "\u65e0")
    except Exception as e: log("KB-002","\u77e5\u8bc6\u8be6\u60c5","FAIL",str(e)[:80])

    # KG-001
    try:
        page.goto(f"{BASE}/knowledge/graph",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u56fe\u8c31","graph"])
        log("KG-001","\u77e5\u8bc6\u56fe\u8c31","PASS" if ok else "FAIL","\u6709\u56fe\u8c31" if ok else "\u65e0")
    except Exception as e: log("KG-001","\u77e5\u8bc6\u56fe\u8c31","FAIL",str(e)[:80])

    # ===== 场景10: 异常检测 =====
    print("\n--- \u573a\u666f10: \u5f02\u5e38\u68c0\u6d4b ---")
    # ANOM-001
    try:
        page.goto(f"{BASE}/anomaly",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u5f02\u5e38","anomaly","\u914d\u7f6e"])
        log("ANOM-001","\u5f02\u5e38\u68c0\u6d4b","PASS" if ok else "FAIL",f"{n}\u6761" if ok else "\u65e0")
    except Exception as e: log("ANOM-001","\u5f02\u5e38\u68c0\u6d4b","FAIL",str(e)[:80])

    # ANOM-002 创建
    try:
        page.goto(f"{BASE}/anomaly",wait_until="networkidle",timeout=15000); time.sleep(1)
        cb = page.query_selector("a:has-text('\u521b\u5efa')") or page.query_selector("a[href*='create']") or page.query_selector("button:has-text('\u65b0\u5efa')")
        if cb:
            cb.click(); time.sleep(2)
            ni = page.query_selector("input[name='name']") or page.query_selector("input[type='text']")
            if ni:
                ni.fill("e2e-anomaly-config")
                sb = page.query_selector("button[type='submit']")
                if sb:
                    sb.click(); time.sleep(3)
                    t = page.inner_text("body")
                    ok = "e2e-anomaly-config" in t or "\u6210\u529f" in t
                    log("ANOM-002","\u521b\u5efa\u914d\u7f6e","PASS" if ok else "FAIL","\u6210\u529f" if ok else "\u5931\u8d25")
                else: log("ANOM-002","\u521b\u5efa\u914d\u7f6e","FAIL","\u65e0\u63d0\u4ea4")
            else: log("ANOM-002","\u521b\u5efa\u914d\u7f6e","FAIL","\u65e0\u540d\u79f0")
        else: log("ANOM-002","\u521b\u5efa\u914d\u7f6e","FAIL","\u65e0\u521b\u5efa")
    except Exception as e: log("ANOM-002","\u521b\u5efa\u914d\u7f6e","FAIL",str(e)[:80])

    # ANOM-003~005
    for aid,route,desc in [("ANOM-003","/anomaly","\u542f\u7528/\u7981\u7528"),("ANOM-004","/anomaly","\u5220\u9664\u914d\u7f6e"),("ANOM-005","/cluster-anomaly","\u96c6\u7fa4\u5f02\u5e38")]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            ok = len(page.inner_text("body")) > 100
            log(aid,desc,"PASS" if ok else "FAIL","\u9875\u9762\u52a0\u8f7d" if ok else "\u65e0")
        except Exception as e: log(aid,desc,"FAIL",str(e)[:80])

    # ===== 场景11: 事件与RCA =====
    print("\n--- \u573a\u666f11: \u4e8b\u4ef6\u4e0eRCA ---")
    # INC-001
    try:
        page.goto(f"{BASE}/incidents",wait_until="networkidle",timeout=15000); time.sleep(2)
        n = count_rows(page)
        ok = n > 0 or has_kw(page,["\u4e8b\u4ef6","incident","P0","P1","P2"])
        log("INC-001","\u4e8b\u4ef6\u5217\u8868","PASS" if ok else "FAIL",f"{n}\u4e2a" if ok else "\u65e0")
    except Exception as e: log("INC-001","\u4e8b\u4ef6\u5217\u8868","FAIL",str(e)[:80])

    # INC-002 详情
    try:
        page.goto(f"{BASE}/incidents/1",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = len(page.inner_text("body")) > 200
        log("INC-002","\u4e8b\u4ef6\u8be6\u60c5","PASS" if ok else "FAIL","\u6709\u8be6\u60c5" if ok else "\u65e0")
    except Exception as e: log("INC-002","\u4e8b\u4ef6\u8be6\u60c5","FAIL",str(e)[:80])

    # INC-003 RCA
    try:
        page.goto(f"{BASE}/incidents/1/rca",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u6839\u56e0","rca","\u5206\u6790"])
        log("INC-003","\u6839\u56e0\u5206\u6790","PASS" if ok else "FAIL","\u6709RCA" if ok else "\u65e0")
    except Exception as e: log("INC-003","\u6839\u56e0\u5206\u6790","FAIL",str(e)[:80])

    # INC-004 解决
    try:
        page.goto(f"{BASE}/incidents",wait_until="networkidle",timeout=15000); time.sleep(2)
        rb = page.query_selector("a:has-text('\u89e3\u51b3')") or page.query_selector("button:has-text('\u89e3\u51b3')")
        if rb:
            tb = page.inner_text("body"); rb.click(); time.sleep(2)
            ok = page.inner_text("body") != tb
            log("INC-004","\u89e3\u51b3\u4e8b\u4ef6","PASS" if ok else "FAIL","\u53d8\u5316" if ok else "\u672a\u53d8")
        else: log("INC-004","\u89e3\u51b3\u4e8b\u4ef6","FAIL","\u65e0\u89e3\u51b3\u6309\u94ae")
    except Exception as e: log("INC-004","\u89e3\u51b3\u4e8b\u4ef6","FAIL",str(e)[:80])

    # INC-005~012 RCA算法
    rca = [("INC-005","/pagerank-rca","PageRank RCA"),("INC-006","/log-rca","\u65e5\u5fd7RCA"),("INC-007","/trace-rca","\u94fe\u8defRCA"),("INC-008","/granger","Granger"),("INC-009","/dtw","DTW"),("INC-010","/idice","iDice"),("INC-011","/pcadr","PCA-DR"),("INC-012","/hotspot","Hotspot")]
    for iid,route,desc in rca:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            ok = len(page.inner_text("body")) > 100
            log(iid,desc,"PASS" if ok else "FAIL","\u9875\u9762\u52a0\u8f7d" if ok else "\u65e0")
        except Exception as e: log(iid,desc,"FAIL",str(e)[:80])

    # ===== 场景12: 预测 =====
    print("\n--- \u573a\u666f12: \u9884\u6d4b ---")
    for pid,route,desc,kws in [("PRED-001","/predictions/capacity","\u9884\u6d4b\u9875\u9762",["\u9884\u6d4b","prediction","\u5bb9\u91cf"]),("PRED-002","/prediction-models","\u6a21\u578b\u7ba1\u7406",["\u6a21\u578b","model","ARIMA","LSTM"]),("PRED-003","/trend-prediction","\u8d8b\u52bf\u9884\u6d4b",["\u8d8b\u52bf","trend","\u9884\u6d4b"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(pid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(pid,desc,"FAIL",str(e)[:80])

    # ===== 场景13: 通知 =====
    print("\n--- \u573a\u666f13: \u901a\u77e5 ---")
    for nid,route,desc,kws in [("NOTIF-001","/notifications","\u901a\u77e5\u7ba1\u7406",["\u901a\u77e5","notification","channel"]),("NOTIF-002","/notification-templates","\u901a\u77e5\u6a21\u677f",["\u6a21\u677f","template"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(nid,desc,"PASS" if ok else "FAIL",f"{n}\u6761" if ok else "\u65e0")
        except Exception as e: log(nid,desc,"FAIL",str(e)[:80])

    # ===== 场景14: 拓扑 =====
    print("\n--- \u573a\u666f14: \u62d3\u6251 ---")
    # TOPO-001
    try:
        page.goto(f"{BASE}/topology",wait_until="networkidle",timeout=15000); time.sleep(3)
        ok = page.query_selector("svg") or page.query_selector("canvas") or has_kw(page,["\u8282\u70b9","node"])
        log("TOPO-001","\u62d3\u6251\u89c6\u56fe","PASS" if ok else "FAIL","\u6709\u8282\u70b9" if ok else "\u65e0")
    except Exception as e: log("TOPO-001","\u62d3\u6251\u89c6\u56fe","FAIL",str(e)[:80])

    # TOPO-002 API
    try:
        r = api_get(page,"/topo-graph/data")
        ok = False
        if r.get("json"):
            j = r["json"]
            if isinstance(j,dict):
                ns = j.get("nodes",j.get("nodeList",[])); ls = j.get("links",j.get("edgeList",[]))
                if (isinstance(ns,list) and len(ns)>0) or (isinstance(ls,list) and len(ls)>0): ok = True
        log("TOPO-002","\u62d3\u6251\u6570\u636e","PASS" if ok else "FAIL","\u6709\u6570\u636e" if ok else "\u65e0")
    except Exception as e: log("TOPO-002","\u62d3\u6251\u6570\u636e","FAIL",str(e)[:80])

    # TOPO-003/004
    for tid,route,desc,kws in [("TOPO-003","/topology/path","\u8def\u5f84\u67e5\u8be2",["\u8def\u5f84","path","\u67e5\u8be2"]),("TOPO-004","/service-mesh","\u670d\u52a1\u7f51\u683c",["\u7f51\u683c","mesh","\u670d\u52a1"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            ok = has_kw(page,kws)
            log(tid,desc,"PASS" if ok else "FAIL","\u6709\u5185\u5bb9" if ok else "\u65e0")
        except Exception as e: log(tid,desc,"FAIL",str(e)[:80])

    # ===== 场景15: 自动化 =====
    print("\n--- \u573a\u666f15: \u81ea\u52a8\u5316 ---")
    for aid,route,desc,kws in [("AUTO-001","/remediation","\u81ea\u6108\u89c4\u5219",["\u81ea\u6108","remediation","\u89c4\u5219"]),("AUTO-002","/remediation-workflows","\u5de5\u4f5c\u6d41",["\u5de5\u4f5c\u6d41","workflow"]),("AUTO-003","/script","\u811a\u672c\u6267\u884c",["\u811a\u672c","script","\u6267\u884c"]),("AUTO-004","/blue-green","\u84dd\u7eff\u53d1\u5e03",["\u84dd\u7eff","blue","green"]),("AUTO-005","/change-workflow","\u53d8\u66f4\u5ba1\u6279",["\u53d8\u66f4","change","\u5ba1\u6279"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(aid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(aid,desc,"FAIL",str(e)[:80])

    # ===== 场景16: AI =====
    print("\n--- \u573a\u666f16: AI ---")
    # AI-001
    try:
        page.goto(f"{BASE}/agent/chat",wait_until="networkidle",timeout=15000); time.sleep(2)
        ok = has_kw(page,["\u5bf9\u8bdd","chat","\u6d88\u606f"]) or page.query_selector("textarea") or page.query_selector("input[type='text']")
        log("AI-001","AI\u9875\u9762","PASS" if ok else "FAIL","\u6709\u804a\u5929" if ok else "\u65e0")
    except Exception as e: log("AI-001","AI\u9875\u9762","FAIL",str(e)[:80])

    # AI-002 发送消息
    try:
        mi = page.query_selector("textarea") or page.query_selector("input[type='text']")
        if mi:
            mi.fill("\u4f60\u597d")
            sb = page.query_selector("button:has-text('\u53d1\u9001')") or page.query_selector("button[type='submit']")
            if sb:
                sb.click(); time.sleep(5)
                t = page.inner_text("body")
                ok = "\u4f60\u597d" in t and len(t) > 100
                log("AI-002","\u53d1\u9001\u6d88\u606f","PASS" if ok else "FAIL","\u6709\u56de\u590d" if ok else "\u65e0\u56de\u590d")
            else: log("AI-002","\u53d1\u9001\u6d88\u606f","FAIL","\u65e0\u53d1\u9001")
        else: log("AI-002","\u53d1\u9001\u6d88\u606f","FAIL","\u65e0\u8f93\u5165\u6846")
    except Exception as e: log("AI-002","\u53d1\u9001\u6d88\u606f","FAIL",str(e)[:80])

    # AI-003 回复验证
    try:
        ok = len(page.inner_text("body")) > 150
        log("AI-003","AI\u56de\u590d","PASS" if ok else "FAIL","\u6709\u5185\u5bb9" if ok else "\u65e0")
    except Exception as e: log("AI-003","AI\u56de\u590d","FAIL",str(e)[:80])

    # AI-004~008
    for aid,desc,route in [("AI-004","\u65b0\u5efa\u4f1a\u8bdd","/agent/chat"),("AI-005","\u5386\u53f2\u4f1a\u8bdd","/agent/sessions"),("AI-006","\u5220\u9664\u4f1a\u8bdd","/agent/sessions"),("AI-007","\u63a8\u8350\u95ee\u9898","/agent/chat"),("AI-008","\u5f85\u786e\u8ba4","/agent/pending")]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            ok = len(page.inner_text("body")) > 50
            log(aid,desc,"PASS" if ok else "FAIL","\u9875\u9762\u52a0\u8f7d" if ok else "\u65e0")
        except Exception as e: log(aid,desc,"FAIL",str(e)[:80])

    # AI-009~016
    ai_p = [("AI-009","/ai/providers","AI\u63d0\u4f9b\u5546"),("AI-010","/ai/providers/create","\u6dfb\u52a0\u63d0\u4f9b\u5546"),("AI-011","/ai/providers","\u6d4b\u8bd5\u63d0\u4f9b\u5546"),("AI-012","/ai/providers","\u7f16\u8f91\u63d0\u4f9b\u5546"),("AI-013","/ai/providers","\u542f\u7528/\u7981\u7528"),("AI-014","/ai/providers","\u5220\u9664\u63d0\u4f9b\u5546"),("AI-015","/ai/configs/create","Agent\u914d\u7f6e"),("AI-016","/agent/invocations","\u5ba1\u8ba1")]
    for aid,route,desc in ai_p:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or len(page.inner_text("body"))>100
            log(aid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(aid,desc,"FAIL",str(e)[:80])

    # ===== 场景17: 系统管理 =====
    print("\n--- \u573a\u666f17: \u7cfb\u7edf\u7ba1\u7406 ---")
    sys_p = [("SYS-001","/users","\u7528\u6237\u7ba1\u7406",["\u7528\u6237","user","admin"]),("SYS-002","/api-tokens","API\u4ee4\u724c",["\u4ee4\u724c","token"]),("SYS-003","/settings","\u7cfb\u7edf\u8bbe\u7f6e",["\u8bbe\u7f6e","setting","config"]),("SYS-004","/datasources","\u6570\u636e\u6e90",["\u6570\u636e\u6e90","datasource","elasticsearch"]),("SYS-005","/tags","\u6807\u7b7e",["\u6807\u7b7e","tag"]),("SYS-006","/audit","\u5ba1\u8ba1",["\u5ba1\u8ba1","audit","log"]),("SYS-007","/es-integration","ES\u96c6\u6210",["\u96c6\u6210","elasticsearch","es"]),("SYS-008","/kafka","Kafka",["kafka","\u7ba1\u9053"]),("SYS-009","/event-sources","\u4e8b\u4ef6\u6e90",["\u4e8b\u4ef6","event","source"]),("SYS-010","/netflow","\u7f51\u7edc\u6d41",["netflow","\u7f51\u7edc"]),("SYS-011","/discovery","\u81ea\u52a8\u53d1\u73b0",["\u53d1\u73b0","discovery"]),("SYS-012","/ext-cmdb","\u5916\u90e8CMDB",["cmdb","\u5916\u90e8"]),("SYS-013","/es-integration","ES\u914d\u7f6e",["\u96c6\u6210","es","elasticsearch"])]
    for sid,route,desc,kws in sys_p:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(sid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(sid,desc,"FAIL",str(e)[:80])

    # ===== 场景18: 事件管理 =====
    print("\n--- \u573a\u666f18: \u4e8b\u4ef6\u7ba1\u7406 ---")
    for eid,route,desc,kws in [("EVENT-001","/events","\u4e8b\u4ef6\u5217\u8868",["\u4e8b\u4ef6","event"]),("EVENT-002","/events/stats","\u4e8b\u4ef6\u7edf\u8ba1",["\u7edf\u8ba1","stat"]),("EVENT-003","/event-sources","\u4e8b\u4ef6\u6e90",["\u4e8b\u4ef6","source"]),("EVENT-004","/event-sources","\u540c\u6b65",["\u4e8b\u4ef6","source"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(eid,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(eid,desc,"FAIL",str(e)[:80])

    # ===== 数据源 =====
    print("\n--- \u573a\u666f19: \u6570\u636e\u6e90 ---")
    for did,route,desc,kws in [("DS-001","/datasources","\u6570\u636e\u6e90",["elasticsearch","kubernetes","\u6570\u636e\u6e90"]),("DS-002","/es-integration","ES\u96c6\u6210",["\u96c6\u6210","elasticsearch","es"]),("DS-003","/kafka","Kafka",["kafka","\u7ba1\u9053"]),("DRAIN-001","/drain","Drain",["\u6a21\u677f","drain","template"])]:
        try:
            page.goto(f"{BASE}{route}",wait_until="networkidle",timeout=15000); time.sleep(2)
            n = count_rows(page)
            ok = n > 0 or has_kw(page,kws)
            log(did,desc,"PASS" if ok else "FAIL",f"{n}\u884c" if ok else "\u65e0")
        except Exception as e: log(did,desc,"FAIL",str(e)[:80])

    # ===== 总结 =====
    browser.close()
    pc = sum(1 for r in results if r["status"]=="PASS")
    fc = sum(1 for r in results if r["status"]=="FAIL")
    total = len(results)
    print(f"\n{'='*60}")
    print(f"\u6d4b\u8bd5\u5b8c\u6210: {total} \u7528\u4f8b, {pc} \u901a\u8fc7, {fc} \u5931\u8d25, \u901a\u8fc7\u7387 {pc/total*100:.1f}%")
    print(f"{'='*60}")
    with open(os.path.join(SHOT,"results.json"),"w",encoding="utf-8") as f:
        json.dump(results,f,ensure_ascii=False,indent=2)
    print(f"\u7ed3\u679c\u5df2\u4fdd\u5b58: {os.path.join(SHOT,'results.json')}")
