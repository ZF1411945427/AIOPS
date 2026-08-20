"""临时工具: 通过 WS 触发并盯着 K8s 集群计划部署, 自动应答 AI 决策。"""
import asyncio, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
PLAN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 11
AUTO = sys.argv[2] if len(sys.argv) > 2 else "fix"
async def main():
    import websockets
    url = f"ws://127.0.0.1:8000/k8s-offline/ws/plans/{PLAN_ID}/deploy"
    async with websockets.connect(url, max_size=None) as ws:
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=None)
                evt = json.loads(raw); t = evt.get("type")
                if t == "phase":
                    print(f"\n===== 阶段{evt.get('step')}: {evt.get('title')} =====", flush=True)
                elif t == "decide":
                    print(f"\n>>> AI需决策: {evt.get('question')}", flush=True)
                    print(f"    ~~ 自动选择: {AUTO}", flush=True)
                    await ws.send(json.dumps({"type": "decision", "choice": AUTO}))
                elif t == "complete":
                    print(f"\n=== COMPLETE: status={evt.get('status')} ===", flush=True); break
                elif t == "error":
                    print(f"\n=== ERROR: {evt.get('message')} ===", flush=True); break
                elif t in ("log", "output"):
                    msg = evt.get("message");
                    if msg is None: msg = evt.get("line", "")
                    node = evt.get("node", "")
                    print(f"   [{node}] {msg}" if node else f"   {msg}", flush=True)
                elif t == "preflight":
                    print(f"\n>>> AI预检: containerd安装={evt.get('containerd_install')} 策略={evt.get('strategy')}", flush=True)
                    for r in evt.get("risks", []): print(f"      风险: {r}", flush=True)
        except Exception as e:
            print("WS END:", e, flush=True)
asyncio.run(main())
