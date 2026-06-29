#!/usr/bin/env python3
"""
E2E 场景测试 3: 登录 → 进入 AI 智能助手 → 发送消息 → 验证 AI 回复
模拟用户与 AI 对话的完整链路。
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

        # ---------- Step 2: 通过侧边栏菜单进入 AI 智能助手 ----------
        step("2. 点击侧边栏 AIOps 智能体 → AI 智能助手")
        # 菜单是 el-menu，子菜单 "AIOps 智能体" 需要先展开，再点 "AI 智能助手"
        # 先展开子菜单
        submenu = page.locator("li.el-sub-menu:has-text('AIOps 智能体')")
        if submenu.count() > 0:
            # 点击子菜单标题展开
            submenu.locator(".el-sub-menu__title").click()
            page.wait_for_timeout(800)
            print("已展开 AIOps 智能体 子菜单")

        # 点击 "AI 智能助手" 菜单项 (index=agent-chat)
        chat_menu = page.locator("li.el-menu-item:has-text('AI 智能助手')")
        if chat_menu.count() > 0:
            chat_menu.click()
            page.wait_for_timeout(2000)
            print("已点击 AI 智能助手 菜单项")
        else:
            # fallback: 直接调用 window._navigateTo
            page.evaluate("window._navigateTo && window._navigateTo('agent-chat')")
            page.wait_for_timeout(2000)
            print("使用 _navigateTo fallback 进入")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(SHOT_DIR, "20_chat_page.png"), full_page=True)

        # 检查页面是否加载了聊天界面
        chat_input = page.locator("input.chat-input")
        send_btn = page.locator("button.send-btn")
        print(f"聊天输入框存在: {chat_input.count() > 0}")
        print(f"发送按钮存在: {send_btn.count() > 0}")

        if chat_input.count() == 0:
            print("❌ 未找到聊天输入框，可能页面未正确加载")
            print("Console 日志:")
            for c in consoles[-10:]:
                print(f"  {c}")
            browser.close()
            return False

        # ---------- Step 3: 发送消息 ----------
        step("3. 发送消息: 你好，请介绍一下你能做什么")
        chat_input.fill("你好，请介绍一下你能做什么")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOT_DIR, "21_msg_typed.png"), full_page=True)
        print("已输入消息")

        # 发送: 在输入框按 Enter (Vue 绑定了 @keyup.enter="sendMessage")
        chat_input.press("Enter")
        print("已按 Enter 发送消息")

        # 等待 AI 回复 — loading 指示器出现然后消失
        # 等待 "AI 正在思考..." 出现
        loading = page.locator("text=AI 正在思考")
        try:
            loading.wait_for(state="visible", timeout=5000)
            print("检测到 'AI 正在思考...' 加载指示器")
            page.screenshot(path=os.path.join(SHOT_DIR, "22_ai_thinking.png"), full_page=True)
        except Exception:
            print("未检测到加载指示器（可能回复太快）")

        # 等待 AI 回复出现 — 等待 .msg-bubble.assistant 出现
        assistant_msg = page.locator(".msg-bubble.assistant .msg-content")
        print("等待 AI 回复...")
        try:
            assistant_msg.last.wait_for(state="visible", timeout=90000)
        except Exception:
            print("等待超时，继续检查...")

        # 额外等待确保内容稳定
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SHOT_DIR, "23_ai_reply.png"), full_page=True)

        # ---------- Step 4: 验证 AI 回复 ----------
        step("4. 验证 AI 回复内容")
        msg_bubbles = assistant_msg.all()
        print(f"找到 {len(msg_bubbles)} 条 assistant 消息")
        reply_text = ""
        if msg_bubbles:
            reply_text = msg_bubbles[-1].inner_text()
            print(f"AI 回复 (前 500 字): {reply_text[:500]}")

        has_reply = len(reply_text.strip()) > 0
        is_error = "请求失败" in reply_text or "error" in reply_text.lower()

        print(f"\n{'='*60}")
        if has_reply and not is_error:
            print(f"场景测试 3 结果: ✅ AI 对话正常，收到有效回复 ({len(reply_text)} 字)")
        elif has_reply and is_error:
            print(f"场景测试 3 结果: ⚠️ AI 返回了错误消息")
            print(f"错误内容: {reply_text[:200]}")
        else:
            print(f"场景测试 3 结果: ❌ 未收到 AI 回复")
        print(f"{'='*60}")

        # 打印 console 日志
        if consoles:
            print("\nConsole 日志 (最后 10 条):")
            for c in consoles[-10:]:
                print(f"  {c}")

        browser.close()
        return has_reply and not is_error

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
