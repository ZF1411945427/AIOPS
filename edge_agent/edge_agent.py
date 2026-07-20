"""AIOps Edge Agent — 主机侧轻量守护进程。

功能：
1. 启动时主动 WebSocket 拨出到云端（wss://cloud/edge/tunnel/connect）
2. 携带 tunnel_token + agent_id + 主机信息注册
3. 每 30s 发心跳
4. 接收云端命令并本地执行（subprocess / PTY）
5. 接收 WebSSH PTY 请求，启动本地 PTY 并双向转发
6. 断线自动重连（指数退避，最大 60s）

主机侧零监听端口，所有通信走已建立的反向隧道。

用法：
  python edge_agent.py --cloud https://cloud.example.com --token <tunnel_token>
  python edge_agent.py --cloud ws://127.0.0.1:8000 --token <token>  # 本地开发

打包为单二进制：pyinstaller --onefile edge_agent.py
打包为 systemd service：见 edge_agent.service 模板
"""
import argparse
import asyncio
import json
import os
import platform
import socket
import subprocess
import sys
import time
import uuid
import hashlib
import signal
from datetime import datetime

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print("缺少依赖：pip install websockets")
    sys.exit(1)

try:
    import urllib.request
    import urllib.parse
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


# ─── agent_id 生成（主机名 + MAC 哈希）───────────────

def get_agent_id() -> str:
    """生成稳定的 agent_id（主机名 + MAC 地址哈希）。"""
    hostname = platform.node()
    mac = uuid.getnode()
    mac_str = ":".join(f"{(mac >> (8*i)) & 0xff:02x}" for i in range(5, -1, -1))
    raw = f"{hostname}|{mac_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_host_info() -> dict:
    """收集主机信息。"""
    hostname = platform.node()
    os_type = platform.system().lower()
    if os_type.startswith("linux"):
        os_type = "linux"
    elif os_type.startswith("win"):
        os_type = "windows"
    elif os_type.startswith("darwin"):
        os_type = "macos"

    # 获取所有 IP
    ip_addresses = []
    try:
        hostname_socket = socket.gethostname()
        ip_addresses = list(set(socket.gethostbyname_ex(hostname_socket)[2]))
    except Exception:
        pass
    # 加上外网 IP（通过访问云端时云端看到的）
    ip_addresses = [ip for ip in ip_addresses if not ip.startswith("127.")]

    return {
        "hostname": hostname,
        "os_type": os_type,
        "ip_addresses": ip_addresses,
        "agent_version": "1.0.0",
    }


# ─── 命令执行 ─────────────────────────────────────────────

async def execute_command(command: str, timeout: int = 30) -> dict:
    """本地执行 shell 命令，返回结果。"""
    try:
        is_windows = platform.system().lower().startswith("win")
        shell = ["cmd", "/c"] if is_windows else ["sh", "-c"]
        proc = await asyncio.create_subprocess_exec(
            *shell, command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"exit_code": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


# ─── PTY 会话管理 ─────────────────────────────────────────

class PtySession:
    """本地 PTY 会话（Linux 用 pty.openpty，Windows 退化为 subprocess）。"""
    def __init__(self, pty_id: str, cols: int = 80, rows: int = 24):
        self.pty_id = pty_id
        self.cols = cols
        self.rows = rows
        self.proc = None
        self.master_fd = None
        self.reader_task = None

    async def start(self):
        is_windows = platform.system().lower().startswith("win")
        if is_windows:
            # Windows 无 PTY，退化为 cmd 子进程（无交互式）
            self.proc = await asyncio.create_subprocess_exec(
                "cmd.exe", "/K",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # Linux/macOS 用 pty
            import pty as _pty
            self.master_fd, slave_fd = _pty.openpty()
            # 设置窗口大小
            try:
                import fcntl, termios, struct
                winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass
            self.proc = await asyncio.create_subprocess_exec(
                "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh",
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                start_new_session=True,
            )
            os.close(slave_fd)

    async def read_output(self, ws, pty_id: str):
        """持续读取 PTY 输出并发回云端。"""
        try:
            if self.master_fd is not None:
                # Linux PTY
                loop = asyncio.get_event_loop()
                while True:
                    try:
                        data = await loop.run_in_executor(None, os.read, self.master_fd, 4096)
                        if not data:
                            break
                        text = data.decode("utf-8", errors="replace")
                        await ws.send_json({"type": "pty_output", "pty_id": pty_id, "data": text})
                    except (OSError, Exception):
                        break
            else:
                # Windows subprocess
                while True:
                    line = await self.proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    await ws.send_json({"type": "pty_output", "pty_id": pty_id, "data": text})
        except Exception as e:
            pass

    def write_input(self, data: str):
        if self.master_fd is not None:
            os.write(self.master_fd, data.encode("utf-8"))
        elif self.proc and self.proc.stdin:
            self.proc.stdin.write(data.encode("utf-8"))
            try:
                self.proc.stdin.drain()
            except Exception:
                pass

    def resize(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        if self.master_fd is not None:
            try:
                import fcntl, termios, struct
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

    async def close(self):
        try:
            if self.master_fd is not None:
                os.close(self.master_fd)
            if self.proc:
                self.proc.kill()
                await self.proc.wait()
        except Exception:
            pass


_PTY_SESSIONS: dict = {}  # pty_id -> PtySession


# ─── 主连接循环 ─────────────────────────────────────────

async def connect_to_cloud(cloud_url: str, token: str, agent_id: str):
    """连接云端并处理消息。"""
    host_info = get_host_info()
    # 构造 ws url
    if cloud_url.startswith("http://"):
        ws_url = cloud_url.replace("http://", "ws://")
        http_url = cloud_url
    elif cloud_url.startswith("https://"):
        ws_url = cloud_url.replace("https://", "wss://")
        http_url = cloud_url
    else:
        ws_url = cloud_url
        http_url = "http://" + cloud_url.replace("ws://", "").replace("wss://", "")
    ws_url = ws_url.rstrip("/") + "/edge/tunnel/connect"

    print(f"[{datetime.now().isoformat()}] 连接云端: {ws_url}")
    print(f"  agent_id: {agent_id}")
    print(f"  hostname: {host_info['hostname']}")
    print(f"  os_type:  {host_info['os_type']}")

    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=60, close_timeout=5) as ws:
            print(f"[{datetime.now().isoformat()}] ✅ 已连接云端")
            # 发送注册
            await ws.send(json.dumps({
                "type": "register",
                "agent_id": agent_id,
                "tunnel_token": token,
                **host_info,
            }))

            # 心跳任务
            async def heartbeat():
                while True:
                    try:
                        await asyncio.sleep(30)
                        await ws.send(json.dumps({"type": "heartbeat"}))
                    except Exception:
                        break

            # HTTP 轮询任务：定期获取待执行命令
            async def poll_commands():
                while True:
                    try:
                        await asyncio.sleep(1)  # 每 1s 轮询一次
                        params = urllib.parse.urlencode({"agent_id": agent_id})
                        poll_url = f"{http_url.rstrip('/')}/edge/commands/pending?{params}"
                        req = urllib.request.Request(poll_url)
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            commands = data.get("commands", [])
                            for cmd in commands:
                                await handle_command(cmd, ws)
                    except Exception as e:
                        pass  # 轮询失败静默重试

            hb_task = asyncio.create_task(heartbeat())
            poll_task = asyncio.create_task(poll_commands())

            # 消息处理循环（主要处理 exec_result 和 pty 消息）
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    m_type = msg.get("type", "")
                    if m_type == "registered":
                        print(f"[{datetime.now().isoformat()}] ✅ 注册成功 session_id={msg.get('session_id')}")
                    elif m_type == "heartbeat_ack":
                        pass  # 心跳确认
                    elif m_type == "exec":
                        # 直接通过 WebSocket 发来的命令（备用通道）
                        await handle_command(msg, ws)
                    elif m_type == "pty_open":
                        pty_id = msg.get("pty_id")
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        print(f"[{datetime.now().isoformat()}] 开启 PTY: pty_id={pty_id}")
                        session = PtySession(pty_id, cols, rows)
                        await session.start()
                        _PTY_SESSIONS[pty_id] = session
                        session.reader_task = asyncio.create_task(session.read_output(ws, pty_id))
                    elif m_type == "pty_input":
                        pty_id = msg.get("pty_id")
                        data = msg.get("data", "")
                        session = _PTY_SESSIONS.get(pty_id)
                        if session:
                            session.write_input(data)
                    elif m_type == "pty_resize":
                        pty_id = msg.get("pty_id")
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        session = _PTY_SESSIONS.get(pty_id)
                        if session:
                            session.resize(cols, rows)
                    elif m_type == "pty_close":
                        pty_id = msg.get("pty_id")
                        session = _PTY_SESSIONS.pop(pty_id, None)
                        if session:
                            await session.close()
                        await ws.send(json.dumps({"type": "pty_exit", "pty_id": pty_id, "exit_code": 0}))
                    elif m_type == "error":
                        print(f"[{datetime.now().isoformat()}] ❌ 云端错误: {msg.get('message')}")
                except json.JSONDecodeError:
                    pass

            hb_task.cancel()
            poll_task.cancel()
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] ❌ 连接异常: {e}")
        raise


async def handle_command(msg, ws):
    """处理从 HTTP 轮询或 WebSocket 收到的命令。"""
    m_type = msg.get("type", "")
    if m_type == "exec":
        command = msg.get("command", "")
        log_id = msg.get("log_id")
        timeout = msg.get("timeout", 30)
        print(f"[{datetime.now().isoformat()}] 执行命令: {command[:80]}")
        result = await execute_command(command, timeout)
        await ws.send(json.dumps({
            "type": "exec_result",
            "log_id": log_id,
            **result,
        }))
        print(f"[{datetime.now().isoformat()}] ✅ 已回传结果 exit_code={result.get('exit_code')}")


async def main_loop(cloud_url: str, token: str, agent_id: str):
    """主循环：断线自动重连（指数退避，最大 60s）。"""
    backoff = 1
    max_backoff = 60
    while True:
        try:
            await connect_to_cloud(cloud_url, token, agent_id)
            backoff = 1  # 成功连接后重置退避
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 断线，{backoff}s 后重连...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


def main():
    parser = argparse.ArgumentParser(description="AIOps Edge Agent — 主机侧反向隧道守护进程")
    parser.add_argument("--cloud", required=True, help="云端地址（如 wss://cloud.example.com 或 http://127.0.0.1:8000）")
    parser.add_argument("--token", required=True, help="tunnel_token（由云端管理员生成）")
    parser.add_argument("--agent-id", default="", help="指定 agent_id（默认自动生成）")
    args = parser.parse_args()

    agent_id = args.agent_id or get_agent_id()
    print(f"AIOps Edge Agent 启动")
    print(f"  云端: {args.cloud}")
    print(f"  agent_id: {agent_id}")

    # 优雅退出
    def on_signal(sig, frame):
        print(f"\n[{datetime.now().isoformat()}] 收到退出信号，清理 PTY 会话...")
        for pty_id, session in list(_PTY_SESSIONS.items()):
            asyncio.get_event_loop().run_until_complete(session.close())
        sys.exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        asyncio.run(main_loop(args.cloud, args.token, agent_id))
    except KeyboardInterrupt:
        print("退出")


if __name__ == "__main__":
    main()
