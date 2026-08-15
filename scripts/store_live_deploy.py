"""组件商店真实部署测试 (11.0.1.133 虚机, 走 11.0.1.1:7897 代理拉 docker 镜像)

验证: 部署成功 / MCP 生效 / AI 优化成功 / 漏洞检查与修复
用法: python scripts/store_live_deploy.py [component] 
  component: redis | nginx | mysql (默认 redis)
"""
import sys
import json
import time
import urllib.request
import urllib.parse
import http.cookiejar
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
ASSET_ID = 193              # vm-11.0.1.133
HTTP_PROXY = "http://11.0.1.1:7897"
NO_PROXY = "127.0.0.1,localhost,.local,11.0.1.133"


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    form = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/login", data=form,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        op.open(req, timeout=10)
    except Exception as e:
        print("login err", e)
    return op


def api_get(op, path):
    req = urllib.request.Request(f"{BASE}{path}")
    return json.loads(op.open(req, timeout=30).read().decode(errors="replace"))


def api_post(op, path, body, timeout=600):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(op.open(req, timeout=timeout).read().decode(errors="replace"))


def post(op, path, body, timeout=600):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(op.open(req, timeout=timeout).read().decode(errors="replace"))


def main():
    comp_name = sys.argv[1] if len(sys.argv) > 1 else "redis"
    op = make_opener()
    catalog = api_get(op, "/component-market/api/catalog")["items"]
    comp = next((c for c in catalog if c["name"] == comp_name), None)
    if not comp:
        print("组件不存在:", comp_name)
        return
    print("=" * 60)
    print(f"[1/4] 真实部署 {comp['display_name']} ({comp['name']}) -> 11.0.1.133 代理 {HTTP_PROXY}")
    print("=" * 60)
    r = post(op, "/component-market/api/deploy", {
        "component_id": comp["id"], "asset_id": ASSET_ID, "deploy_type": "docker",
        "deploy_path": f"/data/aiops-components/{comp['name']}",
        "http_proxy": HTTP_PROXY, "https_proxy": HTTP_PROXY, "no_proxy": NO_PROXY,
    })
    ok = r.get("ok")
    print("deploy ok:", ok)
    print((r.get("deploy_log") or "")[:2000])
    install_id = (r.get("install") or {}).get("id")
    if not ok or not install_id:
        print("部署未成功, 结束")
        return
    print("\ninstall_id =", install_id)

    time.sleep(2)

    print("\n" + "=" * 60)
    print("[2/4] 全面体检 (健康 / 配置 / 漏洞 / AI)")
    print("=" * 60)
    fc = post(op, f"/component-market/api/installs/{install_id}/full-check", {})
    print("ok:", fc.get("ok"))
    res = fc.get("result") or {}
    print("overall_status:", res.get("overall_status"))
    print("health:", json.dumps(res.get("health"), ensure_ascii=False)[:500])
    print("config:", json.dumps(res.get("config"), ensure_ascii=False)[:400])
    print("vuln:", json.dumps(res.get("vuln"), ensure_ascii=False)[:400])
    print("ai:", json.dumps(res.get("ai"), ensure_ascii=False)[:800])

    print("\n" + "=" * 60)
    print("[3/4] 组件对话 MCP 生效验证 (redis_monitor)")
    print("=" * 60)
    try:
        mcp = post(op, "/api/agent/tools/call", {"tool": "redis_monitor",
                                                 "args": {"asset_id": ASSET_ID}}, timeout=60)
        print(json.dumps(mcp, ensure_ascii=False)[:800])
    except Exception as e:
        print("MCP 调用路径尝试:", e)


if __name__ == "__main__":
    main()
