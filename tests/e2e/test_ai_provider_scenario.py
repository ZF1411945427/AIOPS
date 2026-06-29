#!/usr/bin/env python3
"""
E2E 场景测试: 模拟用户登录 → 进入智能体配置 → 添加 AI 提供商 → 保存
使用 Playwright 模拟真实用户操作链路。
"""
import os
import sys
from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8000"
SHOT_DIR = r"E:\Program Files\hermes\cache\screenshots\e2e_ai_provider"
os.makedirs(SHOT_DIR, exist_ok=True)

def step(msg):
    print(f"\n{'='*60}\n[STEP] {msg}\n{'='*60}")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # ---------- Step 1: 打开登录页 ----------
        step("1. 打开登录页")
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT_DIR, "01_login_page.png"), full_page=True)
        print("URL:", page.url)
        print("Title:", page.title())

        # ---------- Step 2: 填写用户名密码并登录 ----------
        step("2. 填写账号 admin/admin123 并登录")
        # Element Plus el-input: locate by placeholder
        username_input = page.locator("input[placeholder='用户名']")
        password_input = page.locator("input[placeholder='密码']")
        username_input.fill("admin")
        password_input.fill("admin123")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOT_DIR, "02_login_filled.png"), full_page=True)
        print("已填写用户名/密码")

        # 点击登录按钮
        login_btn = page.locator("button:has-text('登录')")
        login_btn.click()
        # 等待跳转离开 /login
        page.wait_for_url(lambda u: not u.endswith("/login"), timeout=10000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT_DIR, "03_after_login.png"), full_page=True)
        print("登录后 URL:", page.url)

        # ---------- Step 3: 进入智能体配置页面 ----------
        step("3. 进入智能体配置页面 (/ai/providers)")
        page.goto(f"{BASE}/ai/providers", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT_DIR, "04_ai_providers.png"), full_page=True)
        print("当前 URL:", page.url)
        # 打印页面标题
        h1 = page.locator("h1").all_text_contents()
        print("页面 H1:", h1)

        # ---------- Step 4: 点击"添加模型提供商" ----------
        step("4. 点击添加模型提供商")
        # 查找包含"添加"或"新增"文字的按钮/链接
        add_btn = page.locator("a:has-text('添加'), button:has-text('添加'), a:has-text('新增'), button:has-text('新增'), a:has-text('添加模型'), a[href*='create']")
        count = add_btn.count()
        print(f"找到 {count} 个添加按钮")
        if count == 0:
            # 尝试更宽泛的搜索
            all_links = page.locator("a").all_text_contents()
            print("所有链接文字:", [l.strip() for l in all_links if l.strip()][:20])
            all_btns = page.locator("button").all_text_contents()
            print("所有按钮文字:", [b.strip() for b in all_btns if b.strip()][:20])
        add_btn.first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(SHOT_DIR, "05_provider_form.png"), full_page=True)
        print("表单页 URL:", page.url)

        # ---------- Step 5: 填写 AI 提供商表单 ----------
        step("5. 填写 AI 提供商表单")
        # 表单字段: name, base_url, default_model, api_key
        name_input = page.locator("input[name='name']")
        baseurl_input = page.locator("input[name='base_url']")
        model_input = page.locator("input[name='default_model']")
        apikey_input = page.locator("input[name='api_key']")

        name_input.fill("aicodee-MiniMax")
        baseurl_input.fill("https://v2.aicodee.com")
        model_input.fill("MiniMax-M2.7-highspeed")
        apikey_input.fill("sk-123456")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOT_DIR, "06_form_filled.png"), full_page=True)
        print("已填写表单:")
        print("  名称: aicodee-MiniMax")
        print("  Base URL: https://v2.aicodee.com")
        print("  模型: MiniMax-M2.7-highspeed")
        print("  API Key: sk-******")

        # ---------- Step 6: 点击保存 ----------
        step("6. 点击保存按钮")
        save_btn = page.locator("button.btn-primary:has-text('保存')")
        save_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOT_DIR, "07_after_save.png"), full_page=True)
        print("保存后 URL:", page.url)

        # ---------- Step 7: 验证新增的提供商出现在列表 ----------
        step("7. 验证新增的 AI 提供商")
        page_text = page.inner_text("body")
        checks = {
            "aicodee-MiniMax": "aicodee-MiniMax" in page_text,
            "https://v2.aicodee.com": "v2.aicodee.com" in page_text,
            "MiniMax-M2.7-highspeed": "MiniMax-M2.7-highspeed" in page_text,
        }
        for k, v in checks.items():
            print(f"  {'✅' if v else '❌'} 列表包含: {k}")

        all_pass = all(checks.values())
        page.screenshot(path=os.path.join(SHOT_DIR, "08_final_verify.png"), full_page=True)
        print(f"\n{'='*60}")
        print(f"场景测试结果: {'✅ 全部通过' if all_pass else '❌ 存在失败项'}")
        print(f"{'='*60}")

        browser.close()
        return all_pass

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
