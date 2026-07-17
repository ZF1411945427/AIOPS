import subprocess
import sys
import os
import atexit
import signal

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
# 根据 OS 选择对应 VM 二进制
if sys.platform.startswith("win"):
    _vm_bin_name = "victoria-metrics-windows-amd64-prod.exe"
else:
    _vm_bin_name = "victoria-metrics-prod"
VM_BIN = os.path.join(BIN_DIR, _vm_bin_name)
VM_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "victoriametrics")
VM_PORT = 8428
VM_ADDR = f"0.0.0.0:{VM_PORT}"

_vm_proc = None


def _is_vm_running():
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", VM_PORT))
        sock.close()
        return result == 0
    except Exception:
        return False


def _start_victoria_metrics():
    global _vm_proc
    if _is_vm_running():
        print(f"[VM] VictoriaMetrics already running on :{VM_PORT}, skip.")
        return

    os.makedirs(VM_DATA_DIR, exist_ok=True)

    try:
        _vm_proc = subprocess.Popen(
            [VM_BIN, "-storageDataPath", VM_DATA_DIR, "-httpListenAddr", VM_ADDR],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT,
        )
        print(f"[VM] VictoriaMetrics started (pid={_vm_proc.pid}), http://127.0.0.1:{VM_PORT}")
    except Exception as e:
        print(f"[VM] Failed to start VictoriaMetrics: {e}")


def _stop_victoria_metrics():
    global _vm_proc
    if _vm_proc and _vm_proc.poll() is None:
        try:
            _vm_proc.terminate()
            _vm_proc.wait(timeout=5)
            print("[VM] VictoriaMetrics stopped.")
        except Exception:
            try:
                _vm_proc.kill()
            except Exception:
                pass
    _vm_proc = None


if __name__ == "__main__":
    _start_victoria_metrics()
    atexit.register(_stop_victoria_metrics)

    def _signal_handler(signum, frame):
        _stop_victoria_metrics()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
