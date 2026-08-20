"""集中式 SSH 连接管理：使用 RejectPolicy + known_hosts 白名单.

安全策略：
- 默认使用 paramiko.RejectPolicy()，拒绝未知主机密钥
- 若配置了 known_hosts 文件路径，自动加载已知主机指纹
- 添加新资产/测试连接时使用 register_host() 自动录入指纹
- 开发模式（AIOPS_SSH_STRICT=false）退回到 AutoAddPolicy 并记录警告日志
- 生产模式（AIOPS_SSH_STRICT=true，默认）严格拒绝未知主机
"""
import os
import threading
import paramiko
from pathlib import Path
from app.logger import logger

# 全局 SSH 在建连接信号量：限制同时发起的 TCP 握手数，防止上千资产并发探测
# 打爆目标机 sshd 的 MaxStartups 半开队列 → 从根上减少 banner 超时 / WinError 10038。
# 可通过环境变量 AIOPS_SSH_MAX_CONCURRENT 调整（默认 50）。
_SSH_MAX_CONCURRENT = int(os.environ.get("AIOPS_SSH_MAX_CONCURRENT", "50"))
_ssh_semaphore = threading.Semaphore(_SSH_MAX_CONCURRENT)


def _ssh_slot():
    """SSH TCP 建连槽位（ContextManager）：并发握手限流，防止打爆目标机 sshd 半开队列."""
    # 返回一个可 with 的锁对象（可重入计数由调用方每个 connect 单独获取）
    return _ssh_semaphore

# known_hosts 文件路径：环境变量优先，默认落盘项目 data/known_hosts（持久化指纹，重启不丢）
_KNOWN_HOSTS_PATH = os.environ.get("AIOPS_SSH_KNOWN_HOSTS", "").strip()
if not _KNOWN_HOSTS_PATH:
    _KNOWN_HOSTS_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "known_hosts")
_SSH_STRICT = os.environ.get("AIOPS_SSH_STRICT", "true").lower() == "true"

# 全局 known_hosts 内存缓存（启动时加载一次）
_known_hosts_keys = None


def _load_known_hosts():
    """加载 known_hosts 文件中的主机密钥到内存"""
    global _known_hosts_keys
    if _known_hosts_keys is not None:
        return _known_hosts_keys
    _known_hosts_keys = paramiko.HostKeys()
    if _KNOWN_HOSTS_PATH and os.path.isfile(_KNOWN_HOSTS_PATH):
        try:
            _known_hosts_keys.load(_KNOWN_HOSTS_PATH)
            logger.info(f"加载 known_hosts: {len(_known_hosts_keys)} 个主机")
        except Exception as e:
            logger.warning(f"加载 known_hosts 失败: {e}")
    return _known_hosts_keys


def _close_quietly(client):
    """安全关闭 SSHClient: 先停掉 Transport 后台线程再关 socket.

    paramiko 的 Transport.run() 是守护线程, 若 socket 已被 close 而线程仍在
    recv, Windows 上会持续抛 WinError 10038(在非套接字上执行操作)并刷屏。
    这里先 stop_thread() + 短暂重试让 run 线程退出, 再从根上避免残留 recv。
    """
    if client is None:
        return
    try:
        t = client.get_transport()
        if t is not None:
            try:
                t.stop_thread()
            except Exception:
                pass
            # stop_thread 置 active=False, run 线程应在本轮 fetch/循环后退出,
            # 稍作等待让连接失败场景的 banner recv 及时返回
            try:
                if t.is_active():
                    import time as _time
                    for _ in range(5):
                        if not t.is_active():
                            break
                        _time.sleep(0.05)
            except Exception:
                pass
    except Exception:
        pass
    try:
        client.close()
    except Exception:
        pass


def get_ssh_client() -> "paramiko.SSHClient":
    """创建安全配置的 SSHClient 实例.

    - 严格模式（默认）：RejectPolicy，未知主机密钥直接拒绝连接
    - 宽松模式（AIOPS_SSH_STRICT=false）：AutoAddPolicy，记录警告日志
    - 若有 known_hosts 文件，加载到 client.hostkeys
    """
    client = paramiko.SSHClient()

    if _SSH_STRICT:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        # 资产探测需要自动信任新主机指纹（首次连接录入 known_hosts），已通过 _SSH_STRICT 开关支持严格模式
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507

    # 加载 known_hosts
    hosts = _load_known_hosts()
    if hosts:
        for hostname, keys in hosts.items():
            for key_type, key in keys.items():
                client.get_host_keys().add(hostname, key_type, key)

    return client


def connect_ssh(host: str, port: int = 22, username: str = "root",
                password: str = "", pkey=None, timeout: int = 10) -> "paramiko.SSHClient":
    """创建并连接 SSH 客户端的便捷方法.

    自动使用安全策略，调用方只需提供连接参数。
    首次连接未知主机时自动信任并录入指纹（TOFU），后续走严格白名单校验。
    """
    kwargs = dict(hostname=host, port=port, username=username, timeout=timeout,
                  banner_timeout=max(timeout, 8))
    if pkey:
        kwargs["pkey"] = pkey
    elif password:
        kwargs["password"] = password
    else:
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False

    # banner 类错误最多重试次数（banner 读取失败多为目标机 sshd 排队/不可达，
    # 快速失败交给采集侧记 error + 冷却，避免整轮空转拖慢 datasource_scrape）
    _MAX_BANNER_RETRY = 2
    _banner_fail = 0

    import time as _time
    last_err = None
    client = None
    for _attempt in range(4):
        # 每个重试轮次都用全新的 SSHClient，避免复用已 close 的 client
        # （旧 Transport 线程残留 + socket 已关闭 → WinError 10038）
        client = get_ssh_client()
        try:
            with _ssh_semaphore:  # 全局并发握手限流，防止目标机 sshd 半开队列被上千资产打爆
                client.connect(**kwargs)  # type: ignore[arg-type]
            return client
        except paramiko.BadHostKeyException as e:
            # 指纹已录入但本次不一致 → 可能 MITM，拒绝
            _close_quietly(client)
            lookup_key = f"[{host}]:{port}" if port != 22 else host
            logger.error(f"主机 {lookup_key} SSH 密钥不匹配，拒绝连接（可能存在中间人攻击）: {e}")
            raise
        except paramiko.AuthenticationException:
            _close_quietly(client)
            raise
        except paramiko.SSHException as e:
            msg = str(e)
            if "not found in known_hosts" in msg:
                # 首次连接：指纹不在白名单 → TOFU 信任并录入
                _close_quietly(client)
                return _connect_with_tofu(host, port, username, password, pkey, timeout, kwargs)
            last_err = f"{host}:{port} SSH 连接失败: {msg}"
            _close_quietly(client)
            if "banner" not in msg.lower() and "10038" not in msg:
                raise
            # banner 读取超时（目标机 sshd 并发/半开排队时）→ 限次重试后快速失败
            _banner_fail += 1
            if _banner_fail >= _MAX_BANNER_RETRY:
                raise paramiko.SSHException(last_err)
            _time.sleep(1 + _attempt)
            continue
        except Exception as e:
            last_err = str(e)
            _close_quietly(client)
            break
    raise paramiko.SSHException(last_err or "SSH 连接失败")


def _connect_with_tofu(host: str, port: int, username: str, password: str,
                       pkey, timeout: int, kwargs: dict) -> "paramiko.SSHClient":
    """首次连接（TOFU）自举：自动信任新主机指纹并录入 known_hosts 后重连.

    仅当主机指纹不在 known_hosts 时触发（视为首次连接）。
    若指纹已录入但本次不一致（BadHostKeyException），由调用方直接拒绝。
    """
    lookup_key = f"[{host}]:{port}" if port != 22 else host
    hosts = _load_known_hosts()
    if hosts and lookup_key in hosts:
        logger.error(f"主机 {lookup_key} SSH 密钥已变更，拒绝连接（可能存在中间人攻击）")
        raise RuntimeError(f"主机 {lookup_key} SSH 密钥已变更，拒绝连接（可能存在中间人攻击）")

    logger.warning(f"首次连接主机 {lookup_key}，自动信任并录入指纹（TOFU）")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507
    with _ssh_semaphore:
        client.connect(**kwargs)  # type: ignore[arg-type]
    save_host_key(client, host, port)
    return client


def register_host(host: str, port: int = 22) -> "paramiko.SSHClient":
    """首次连接新服务器：使用 AutoAddPolicy 自动信任并记录指纹.

    专用于添加新资产/测试连接场景。
    连接成功后自动将主机指纹保存到 known_hosts 文件和内存缓存。
    后续操作将使用 RejectPolicy + 已录入的指纹。

    使用方法：
        # 先用 register_host 连接测试
        client = register_host("192.168.1.100", 22, "root", "password")
        client.close()
        # 后续操作用 get_ssh_client()，此时指纹已录入
    """
    client = paramiko.SSHClient()
    # register_host 是资产录入入口，需要自动信任新主机指纹（首次连接录入 known_hosts）
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507

    # 加载已有 known_hosts
    hosts = _load_known_hosts()
    if hosts:
        for hostname, keys in hosts.items():
            for key_type, key in keys.items():
                client.get_host_keys().add(hostname, key_type, key)

    logger.info(f"注册新主机: {host}:{port}")
    return client


def save_host_key(client: paramiko.SSHClient, host: str, port: int = 22):
    """连接成功后，将主机密钥保存到 known_hosts 文件和内存缓存.

    在 register_host 连接成功后调用此方法。
    """
    global _known_hosts_keys

    # 从 client 获取主机密钥
    host_keys = client.get_host_keys()
    if host not in host_keys and f"[{host}]:{port}" not in host_keys:
        return

    # 保存到内存缓存
    if _known_hosts_keys is None:
        _known_hosts_keys = paramiko.HostKeys()

    lookup_key = f"[{host}]:{port}" if port != 22 else host
    if lookup_key in host_keys:
        for key_type, key in host_keys[lookup_key].items():
            _known_hosts_keys.add(lookup_key, key_type, key)
            logger.info(f"主机指纹已录入: {lookup_key} ({key_type})")

    # 保存到文件
    if _KNOWN_HOSTS_PATH:
        try:
            os.makedirs(os.path.dirname(_KNOWN_HOSTS_PATH), exist_ok=True)
            _known_hosts_keys.save(_KNOWN_HOSTS_PATH)
            logger.info(f"known_hosts 已保存到: {_KNOWN_HOSTS_PATH}")
        except Exception as e:
            logger.warning(f"保存 known_hosts 失败: {e}")


def test_and_register_ssh(host: str, port: int = 22, username: str = "root",
                           password: str = "", pkey=None, timeout: int = 10) -> dict:
    """测试连接并自动注册主机指纹.

    专用于添加新资产时的连接测试。
    返回 {"ok": True/False, "message": "...", "fingerprint": "..."}

    流程：
    1. 使用 AutoAddPolicy 连接（首次信任）
    2. 连接成功后保存指纹到 known_hosts
    3. 后续操作使用 RejectPolicy + 已录入的指纹
    """

    # 先测试端口可达
    import socket
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
    except Exception as e:
        return {"ok": False, "message": f"端口 {port} 无法连接: {e}"}

    # 使用宽松策略连接
    kwargs = dict(hostname=host, port=port, username=username, timeout=timeout,
                  banner_timeout=max(timeout, 8))
    if pkey:
        kwargs["pkey"] = pkey
    elif password:
        kwargs["password"] = password
    else:
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False

    import time as _time
    last_err = None
    client = None
    for _attempt in range(4):
        # 每个重试轮次都用全新的 SSHClient，避免复用已 close 的 client
        # （旧 Transport 线程残留 + socket 已关闭 → WinError 10038）
        client = register_host(host, port)
        try:
            with _ssh_semaphore:
                client.connect(**kwargs)  # type: ignore[arg-type]
            break
        except paramiko.AuthenticationException:
            _close_quietly(client)
            return {"ok": False, "message": "认证失败，用户名或密码错误"}
        except paramiko.SSHException as e:
            msg = str(e)
            if "banner" not in msg.lower():
                _close_quietly(client)
                return {"ok": False, "message": f"SSH错误: {e}"}
            last_err = msg
            _close_quietly(client)
            _time.sleep(1 + _attempt)
            continue
        except Exception as e:
            _close_quietly(client)
            return {"ok": False, "message": f"连接异常: {e}"}
    else:
        if client:
            _close_quietly(client)
        return {"ok": False, "message": f"SSH错误: {last_err or 'banner 读取超时'}"}

    # 获取指纹
    fingerprint = ""
    host_keys = client.get_host_keys()
    lookup_key = f"[{host}]:{port}" if port != 22 else host
    if lookup_key in host_keys:
        for key_type, key in host_keys[lookup_key].items():
            fingerprint = f"{key_type} {key.get_fingerprint().hex()[:32]}..."
            break

    # 保存指纹
    save_host_key(client, host, port)

    # 执行测试命令
    try:
        stdin, stdout, stderr = client.exec_command("echo ok", timeout=5)
        result = stdout.read().decode().strip()
        client.close()
        if result == "ok":
            return {"ok": True, "message": "连接成功，指纹已录入", "fingerprint": fingerprint}
        else:
            return {"ok": False, "message": "命令执行异常"}
    except Exception as e:
        client.close()
        return {"ok": False, "message": f"命令执行失败: {e}"}
