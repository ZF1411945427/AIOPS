import json
import socket
import paramiko
import subprocess
from datetime import datetime

class ConnectionTester:
    """多类型连接测试器"""

    @staticmethod
    def test(connection_type: str, host: str, config: dict) -> dict:
        """测试连接，返回 {ok, message, latency_ms}"""
        try:
            if connection_type == "ssh":
                return ConnectionTester._test_ssh(host, config)
            elif connection_type == "kubernetes":
                return ConnectionTester._test_kubernetes(config)
            elif connection_type == "snmp":
                return ConnectionTester._test_snmp(host, config)
            elif connection_type == "http":
                return ConnectionTester._test_http(host, config)
            elif connection_type == "database":
                return ConnectionTester._test_database(host, config)
            else:
                return {"ok": False, "message": f"未知连接类型: {connection_type}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @staticmethod
    def _test_ssh(host: str, config: dict) -> dict:
        """测试 SSH 连接"""
        if not host:
            return {"ok": False, "message": "IP地址不能为空"}

        port = config.get("ssh_port", 22)
        username = config.get("ssh_user", "root")
        password = config.get("ssh_password", "")
        private_key = config.get("ssh_private_key", "")
        timeout = 10

        start = datetime.now()

        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
        except Exception as e:
            return {"ok": False, "message": f"端口 {port} 无法连接: {e}"}

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if private_key:
                try:
                    from io import StringIO
                    key_obj = paramiko.RSAKey.from_private_key(StringIO(private_key))
                except:
                    try:
                        key_obj = paramiko.ECDSAKey.from_private_key(StringIO(private_key))
                    except:
                        key_obj = paramiko.Ed25519Key.from_private_key(StringIO(private_key))
                ssh.connect(host, port=port, username=username, pkey=key_obj, timeout=timeout, banner_timeout=timeout)
            elif password:
                ssh.connect(host, port=port, username=username, password=password, timeout=timeout, banner_timeout=timeout)
            else:
                ssh.connect(host, port=port, username=username, timeout=timeout, banner_timeout=timeout, look_for_keys=False, allow_agent=False)

            stdin, stdout, stderr = ssh.exec_command("echo ok", timeout=5)
            result = stdout.read().decode().strip()
            ssh.close()

            if result == "ok":
                latency = (datetime.now() - start).total_seconds() * 1000
                return {"ok": True, "message": f"连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
            else:
                return {"ok": False, "message": "命令执行异常"}
        except paramiko.AuthenticationException:
            return {"ok": False, "message": "认证失败，用户名或密码错误"}
        except paramiko.SSHException as e:
            if "Unable to connect" in str(e):
                return {"ok": False, "message": f"SSH服务不可用: {e}"}
            return {"ok": False, "message": f"SSH错误: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"连接异常: {e}"}

    @staticmethod
    def _test_kubernetes(config: dict) -> dict:
        """测试 Kubernetes 连接"""
        try:
            from kubernetes import client, config as k8s_config
            from kubernetes.client.rest import ApiException

            kubeconfig = config.get("kubeconfig", "")
            api_server = config.get("api_server", "")
            token = config.get("token", "")
            namespace = config.get("namespace", "default")

            if kubeconfig:
                try:
                    k8s_config.load_kube_config_from_dict(json.loads(kubeconfig))
                except:
                    return {"ok": False, "message": "Kubeconfig 格式错误"}
            elif api_server and token:
                try:
                    configuration = client.Configuration()
                    configuration.host = api_server
                    configuration.api_key = {"authorization": f"Bearer {token}"}
                    configuration.verify_ssl = False
                    client.Configuration.set_default(configuration)
                except Exception as e:
                    return {"ok": False, "message": f"K8s API 配置错误: {e}"}
            else:
                return {"ok": False, "message": "缺少 kubeconfig 或 api_server/token"}

            v1 = client.CoreV1Api()
            start = datetime.now()
            v1.list_namespace(limit=1)
            latency = (datetime.now() - start).total_seconds() * 1000

            return {"ok": True, "message": f"K8s 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
        except ImportError:
            return {"ok": False, "message": "未安装 kubernetes 库"}
        except ApiException as e:
            return {"ok": False, "message": f"K8s API 错误: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"K8s 连接异常: {e}"}

    @staticmethod
    def _test_snmp(host: str, config: dict) -> dict:
        """测试 SNMP 连接"""
        if not host:
            return {"ok": False, "message": "IP地址不能为空"}

        community = config.get("snmp_community", "public")
        oid = config.get("snmp_oid", "1.3.6.1.2.1.1.1.0")
        version = config.get("snmp_version", "2c")
        timeout = 10

        try:
            import netsnmp
        except ImportError:
            try:
                result = subprocess.run(
                    ["snmpget", "-v", "2c" if version == "2c" else "1", "-c", community, host, oid, "-t", str(timeout)],
                    capture_output=True, text=True, timeout=timeout + 5
                )
                start = datetime.now()
                if result.returncode == 0 and result.stdout.strip():
                    latency = (datetime.now() - start).total_seconds() * 1000
                    return {"ok": True, "message": f"SNMP 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
                else:
                    return {"ok": False, "message": f"SNMP 查询失败: {result.stderr or result.stdout}"}
            except FileNotFoundError:
                return {"ok": False, "message": "未安装 snmpwalk/snmpget"}
            except Exception as e:
                return {"ok": False, "message": f"SNMP 异常: {e}"}

        start = datetime.now()
        try:
            var = netsnmp.Varbind(oid)
            result = netsnmp.snmpget(var, Version=2 if version == "2c" else 1, DestHost=host, Community=community, Timeout=timeout * 1000000)
            latency = (datetime.now() - start).total_seconds() * 1000
            if result and result[0]:
                return {"ok": True, "message": f"SNMP 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
            else:
                return {"ok": False, "message": "SNMP 查询无响应"}
        except Exception as e:
            return {"ok": False, "message": f"SNMP 异常: {e}"}

    @staticmethod
    def _test_http(host: str, config: dict) -> dict:
        """测试 HTTP/HTTPS API 连接"""
        url = config.get("http_url", "")
        if not url:
            if host:
                url = f"http://{host}"
            else:
                return {"ok": False, "message": "URL 不能为空"}

        username = config.get("http_user", "")
        password = config.get("http_password", "")
        headers = config.get("http_headers", {})
        timeout = config.get("http_timeout", 10)

        start = datetime.now()
        try:
            import requests
            auth = None
            if username and password:
                auth = (username, password)

            kwargs = {"timeout": timeout, "headers": headers, "auth": auth}
            if not url.startswith("https") and not url.startswith("http"):
                url = f"http://{url}"

            resp = requests.get(url, **kwargs)
            latency = (datetime.now() - start).total_seconds() * 1000

            if resp.status_code < 500:
                return {"ok": True, "message": f"HTTP {resp.status_code} (延迟 {latency:.0f}ms)", "latency_ms": latency}
            else:
                return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.reason}"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "message": "连接失败，服务不可达"}
        except requests.exceptions.Timeout:
            return {"ok": False, "message": "连接超时"}
        except Exception as e:
            return {"ok": False, "message": f"HTTP 异常: {e}"}

    @staticmethod
    def _test_database(host: str, config: dict) -> dict:
        """测试数据库连接"""
        if not host:
            return {"ok": False, "message": "主机不能为空"}

        db_type = config.get("db_type", "mysql")
        port = config.get("db_port", 3306 if db_type == "mysql" else 5432)
        username = config.get("db_user", "")
        password = config.get("db_password", "")
        database = config.get("db_name", "")
        timeout = 10

        start = datetime.now()
        try:
            if db_type == "mysql":
                import pymysql
                conn = pymysql.connect(
                    host=host, port=int(port), user=username, password=password,
                    database=database if database else None, connect_timeout=timeout
                )
                conn.close()
            elif db_type == "postgresql":
                import psycopg2
                conn = psycopg2.connect(
                    host=host, port=int(port), user=username, password=password,
                    dbname=database if database else None, connect_timeout=timeout
                )
                conn.close()
            elif db_type == "redis":
                import redis
                r = redis.Redis(host=host, port=int(port), password=password or None, socket_connect_timeout=timeout)
                r.ping()
            else:
                return {"ok": False, "message": f"不支持的数据库类型: {db_type}"}

            latency = (datetime.now() - start).total_seconds() * 1000
            return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
        except ImportError as e:
            return {"ok": False, "message": f"缺少驱动: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"连接失败: {e}"}


def test_asset_connection(asset) -> dict:
    """测试资产连接"""
    connection_type = getattr(asset, 'connection_type', 'ssh')
    config = {}
    try:
        raw = getattr(asset, 'connection_config', '{}')
        if isinstance(raw, str):
            config = json.loads(raw) if raw else {}
        else:
            config = raw or {}
    except (json.JSONDecodeError, TypeError):
        config = {}

    host = getattr(asset, 'ip', '')

    if connection_type == "ssh":
        config["ssh_port"] = getattr(asset, 'ssh_port', 22)
        config["ssh_user"] = getattr(asset, 'ssh_user', 'root')
        config["ssh_password"] = getattr(asset, 'ssh_password', '')
    elif connection_type == "database":
        config["db_type"] = getattr(asset, 'db_type', 'mysql')
        config["db_port"] = getattr(asset, 'db_port', 3306)
        config["db_user"] = getattr(asset, 'db_user', '')
        config["db_password"] = getattr(asset, 'db_password', '')
        config["db_name"] = getattr(asset, 'db_name', '')

    return ConnectionTester.test(connection_type, host, config)
