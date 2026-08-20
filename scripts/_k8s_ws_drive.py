import asyncio
import json
import os
import sys
import time
import urllib.request

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(RUNS_DIR, exist_ok=True)
LOG = os.path.join(RUNS_DIR, "_k8s_deploy19.log")

PLAN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 19
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 3600


def _login():
    req = urllib.request.Request(
        "http://127.0.0.1:8000/login",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    return d["token"]


def main():
    token = _login()
    import websockets

    hdr = {"Authorization": f"Bearer {token}"}
    url = f"ws://127.0.0.1:8000/k8s-offline/ws/plans/{PLAN_ID}/deploy"
    f = open(LOG, "a", encoding="utf-8")
    start = time.time()
    done = False
    try:
        async def _run():
            nonlocal done
            async with websockets.connect(url, additional_headers=hdr,
                                          open_timeout=30, ping_interval=None) as ws:
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=90)
                    except asyncio.TimeoutError:
                        pass
                    if not raw:
                        continue
                    try:
                        evt = json.loads(raw)
                    except Exception:
                        continue
                    line = json.dumps(evt, ensure_ascii=False)
                    t = time.strftime("%H:%M:%S")
                    # 精简 log/status/phase 事件，保留其余
                    et = evt.get("type")
                    if et in ("log",):
                        f.write(f"[{t}][log] {evt.get('node','')} {evt.get('message','')}\n")
                        f.flush()
                    elif et == "phase":
                        f.write(f"[{t}][phase] step={evt.get('step')} {evt.get('title')}\n")
                        f.flush()
                    elif et in ("status", "complete", "error"):
                        f.write(f"[{t}][{et}] {line}\n")
                        f.flush()
                        if et in ("complete", "error"):
                            done = True
                            break
                    elif time.time() - start < 2:
                        f.write(f"[{t}][{et}] {line}\n")
                        f.flush()
                    if time.time() - start > DURATION:
                        break
            # done 循环
        asyncio.run(_run())
    except Exception as e:
        f.write(f"SOCKET_ERROR: {e}\n")
        f.flush()
    finally:
        f.close()


if __name__ == "__main__":
    main()
