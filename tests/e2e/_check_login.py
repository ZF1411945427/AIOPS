
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context().new_page()
    page.goto("http://127.0.0.1:8000/login", wait_until="networkidle")
    time.sleep(3)
    inputs = page.query_selector_all("input")
    buttons = page.query_selector_all("button")
    print("Inputs: %d" % len(inputs))
    for inp in inputs:
        nm = inp.get_attribute("name")
        tp = inp.get_attribute("type")
        ph = inp.get_attribute("placeholder")
        print("  input: name=%s type=%s placeholder=%s" % (nm, tp, ph))
    print("Buttons: %d" % len(buttons))
    for btn in buttons:
        print("  button: text=%s" % btn.text_content().strip()[:30])
    
    # 看看之前成功的 auth 脚本
    page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    time.sleep(3)
    inputs2 = page.query_selector_all("input")
    print("\nRoot Inputs: %d" % len(inputs2))
    for inp in inputs2:
        nm = inp.get_attribute("name")
        tp = inp.get_attribute("type")
        ph = inp.get_attribute("placeholder")
        print("  input: name=%s type=%s placeholder=%s" % (nm, tp, ph))
    browser.close()
