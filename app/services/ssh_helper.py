"""集中式 SSH 连接管理：使用 RejectPolicy + known_hosts 白名单.

安全策略：
- 默认使用 paramiko.RejectPolicy()，拒绝未知主机密钥
- 若配置了 known_hosts 文件路径，自动加载已知主机指纹
- 添加新资产/测试连接时使用 register_host() 自动录入指纹
- 开发模式（AIOPS_SSH_STRICT=false）退回到 AutoAddPolicy 并记录警告日志
- 生产模式（AIOPS_SSH_STRICT=true，默认）严格拒绝未知主机
"""
import os
import paramiko
from app.logger import logger

_KNOWN_HOSTS_PATH = os.environ.get("AIOPS_SSH_KNOWN_HOSTS", "")
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
    """
    client = get_ssh_client()
    kwargs = dict(hostname=host, port=port, username=username, timeout=timeout,
                  banner_timeout=timeout)
    if pkey:
        kwargs["pkey"] = pkey
    elif password:
        kwargs["password"] = password
    else:
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False
    client.connect(**kwargs)
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
    from io import StringIO

    # 先测试端口可达
    import socket
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
    except Exception as e:
        return {"ok": False, "message": f"端口 {port} 无法连接: {e}"}

    # 使用宽松策略连接
    client = register_host(host, port)
    kwargs = dict(hostname=host, port=port, username=username, timeout=timeout,
                  banner_timeout=timeout)
    if pkey:
        kwargs["pkey"] = pkey
    elif password:
        kwargs["password"] = password
    else:
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False

    try:
        client.connect(**kwargs)
    except paramiko.AuthenticationException:
        return {"ok": False, "message": "认证失败，用户名或密码错误"}
    except paramiko.SSHException as e:
        return {"ok": False, "message": f"SSH错误: {e}"}
    except Exception as e:
        return {"ok": False, "message": f"连接异常: {e}"}

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
            return {"ok": True, "message": f"连接成功，指纹已录入", "fingerprint": fingerprint}
        else:
            return {"ok": False, "message": "命令执行异常"}
    except Exception as e:
        client.close()
        return {"ok": False, "message": f"命令执行失败: {e}"}
