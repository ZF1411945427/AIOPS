#!/usr/bin/env python3
"""
E2E 场景测试 2: 登录 → 智能体配置 → 点"测试"按钮验证 AI 提供商连通性
捕获 alert 弹窗内容，判断连接是否成功。
"""
import os
import sys
from playwright.sync_api import sync_playwright

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

        # 用来捕获 alert 弹窗
        dialog_msg = {"text": None, "type": None}
        def handle_dialog(dialog):
            dialog_msg["text"] = dialog.message
            dialog_msg["type"] = dialog.type
            print(f"  [DIALOG {dialog.type}] {dialog.message}")
            dialog.dismiss()
        page.on("dialog", handle_dialog)

        # 捕获 console 日志
        consoles = []
        page.on("console", lambda m: consoles.append(f"[{m.type}] {m.text}"))

        # ---------- Step 1: 登录 ----------
        step("1. 登录 admin/admin123")
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.locator("input[placeholder='用户名']").fill("admin")
        page.locator("input[placeholder='密码']").fill("admin123")
        page.locator("button:has-text('登录')").click()
        page.wait_for_url(lambda u: not u.endswith("/login"), timeout=10000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        print("登录后 URL:", page.url)

        # ---------- Step 2: 进入智能体配置 ----------
        step("2. 进入智能体配置页面")
        page.goto(f"{BASE}/ai/providers", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT_DIR, "10_providers_list.png"), full_page=True)
        print("当前 URL:", page.url)

        # 确认列表中有我们的提供商
        body_text = page.inner_text("body")
        if "aicodee-MiniMax" in body_text:
            print("✅ 列表中找到 aicodee-MiniMax")
        else:
            print("❌ 列表中未找到 aicodee-MiniMax")
            browser.close()
            return False

        # ---------- Step 3: 点击"测试"按钮 ----------
        step("3. 点击 aicodee-MiniMax 的测试按钮")
        # 测试按钮: <button onclick="testProvider(1)" ...>测试</button>
        test_btn = page.locator("button:has-text('测试')")
        count = test_btn.count()
        print(f"找到 {count} 个测试按钮")

        # 点击前先截图
        page.screenshot(path=os.path.join(SHOT_DIR, "11_before_test.png"), full_page=True)

        # 点击测试按钮 (会触发 fetch + alert)
        test_btn.first.click()
        print("已点击测试按钮，等待响应...")

        # 等待 dialog (alert) 出现 — testProvider 是异步 fetch，可能要等几秒
        # 等最多 40 秒（外部 API 调用）
        for i in range(80):
            page.wait_for_timeout(500)
            if dialog_msg["text"] is not None:
                break
        page.screenshot(path=os.path.join(SHOT_DIR, "12_after_test.png"), full_page=True)

        # ---------- Step 4: 分析测试结果 ----------
        step("4. 分析连通性测试结果")
        if dialog_msg["text"] is not None:
            print(f"Alert 内容: {dialog_msg['text']}")
            is_success = "成功" in dialog_msg["text"] or "success" in dialog_msg["text"].lower()
            print(f"连通性: {'✅ 连接成功' if is_success else '❌ 连接失败'}")
            print(f"完整消息: {dialog_msg['text']}")
        else:
            print("❌ 未捕获到 alert 弹窗（可能请求超时或 JS 报错）")
            print("Console 日志:")
            for c in consoles[-10:]:
                print(f"  {c}")

        print(f"\n{'='*60}")
        result = dialog_msg["text"] is not None and ("成功" in dialog_msg["text"] or "success" in dialog_msg["text"].lower())
        print(f"场景测试 2 结果: {'✅ AI 提供商连通性正常' if result else '⚠️ 连通性测试未通过（可能 API Key 无效或网络不通）'}")
        print(f"{'='*60}")

        browser.close()
        return result

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
