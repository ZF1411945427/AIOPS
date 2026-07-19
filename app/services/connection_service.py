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
            elif connection_type == "winrm":
                return ConnectionTester._test_winrm(host, config)
            elif connection_type == "kubernetes":
                return ConnectionTester._test_kubernetes(host, config)
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
        """测试 SSH 连接（添加新资产专用：自动注册主机指纹）"""
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
            from app.services.ssh_helper import test_and_register_ssh
            from io import StringIO

            pkey = None
            if private_key:
                try:
                    pkey = paramiko.RSAKey.from_private_key(StringIO(private_key))
                except:
                    try:
                        pkey = paramiko.ECDSAKey.from_private_key(StringIO(private_key))
                    except:
                        pkey = paramiko.Ed25519Key.from_private_key(StringIO(private_key))

            result = test_and_register_ssh(
                host=host, port=port, username=username,
                password=password, pkey=pkey, timeout=timeout,
            )

            if result["ok"]:
                latency = (datetime.now() - start).total_seconds() * 1000
                result["latency_ms"] = latency
                result["message"] = f"{result['message']} (延迟 {latency:.0f}ms)"

            return result

        except paramiko.AuthenticationException:
            return {"ok": False, "message": "认证失败，用户名或密码错误"}
        except paramiko.SSHException as e:
            if "Unable to connect" in str(e):
                return {"ok": False, "message": f"SSH服务不可用: {e}"}
            return {"ok": False, "message": f"SSH错误: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"连接异常: {e}"}

    @staticmethod
    def _test_winrm(host: str, config: dict) -> dict:
        """测试 WinRM 连接（Windows 资产专用）"""
        if not host:
            return {"ok": False, "message": "IP地址不能为空"}

        winrm_user = config.get("winrm_user", "Administrator")
        winrm_password = config.get("winrm_password", "")
        winrm_port = config.get("winrm_port", 5985)
        winrm_transport = config.get("winrm_transport", "ntlm")
        winrm_ssl = config.get("winrm_ssl", False)
        scheme = "https" if winrm_ssl else "http"
        endpoint = f"{scheme}://{host}:{winrm_port}/wsman"
        timeout = 10

        start = datetime.now()

        try:
            import winrm as pywinrm
            session = pywinrm.Session(
                endpoint,
                auth=(winrm_user, winrm_password),
                transport=winrm_transport,
                server_cert_validation="ignore" if winrm_ssl else "validate",
            )
            r = session.run_cmd("whoami")
            latency = (datetime.now() - start).total_seconds() * 1000

            if r.status_code == 0:
                return {
                    "ok": True,
                    "message": f"WinRM 连接成功 (用户: {r.std_out.strip()}, 延迟 {latency:.0f}ms)",
                    "latency_ms": latency,
                }
            else:
                return {"ok": False, "message": f"WinRM 命令执行失败 (exit={r.status_code}): {r.std_err}"}

        except ImportError:
            return {"ok": False, "message": "pywinrm 未安装，请执行: pip install pywinrm"}
        except Exception as e:
            return {"ok": False, "message": f"WinRM 连接异常: {e}"}

    @staticmethod
    def _test_kubernetes(host: str, config: dict) -> dict:
        """测试 Kubernetes 连接

        统一字段名: k8s_api_server / k8s_token（见 CONTRACT.md）
        host 参数（asset.ip）作为 api_server 的 fallback。
        """
        try:
            from kubernetes import client, config as k8s_config
            from kubernetes.client.rest import ApiException

            kubeconfig = config.get("kubeconfig", "")
            api_server = config.get("k8s_api_server") or host or ""
            token = config.get("k8s_token") or ""

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
                    configuration.verify_ssl = config.get("verify_ssl", False)
                    client.Configuration.set_default(configuration)
                except Exception as e:
                    return {"ok": False, "message": f"K8s API 配置错误: {e}"}
            else:
                return {"ok": False, "message": "缺少 kubeconfig 或 k8s_api_server/k8s_token"}

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
        version = config.get("snmp_version", "v2c")
        timeout = 10

        try:
            import netsnmp
        except ImportError:
            try:
                result = subprocess.run(
                    ["snmpget", "-v", "2c" if version.lstrip("v") == "2c" else "1", "-c", community, host, oid, "-t", str(timeout)],
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
            result = netsnmp.snmpget(var, Version=2 if version.lstrip("v") == "2c" else 1, DestHost=host, Community=community, Timeout=timeout * 1000000)
            latency = (datetime.now() - start).total_seconds() * 1000
            if result and result[0]:
                return {"ok": True, "message": f"SNMP 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
            else:
                return {"ok": False, "message": "SNMP 查询无响应"}
        except Exception as e:
            return {"ok": False, "message": f"SNMP 异常: {e}"}

    @staticmethod
    def _test_http(host: str, config: dict) -> dict:
        """测试 HTTP/HTTPS API 连接

        认证字段: http_auth (basic/bearer) + http_credential (见 CONTRACT.md)
        当 config 含 mw_subtype 时，路由到 _test_middleware（按中间件子类型选择健康检查路径）。
        """
        if config.get("mw_subtype"):
            return ConnectionTester._test_middleware(host, config)

        url = config.get("http_url", "")
        if not url:
            if host:
                url = f"http://{host}"
            else:
                return {"ok": False, "message": "URL 不能为空"}

        http_auth_mode = config.get("http_auth", "")
        http_credential = config.get("http_credential", "")
        timeout = 10

        start = datetime.now()
        try:
            import requests

            auth = None
            headers = {}
            if http_auth_mode == "basic" and http_credential:
                if ":" in http_credential:
                    user, pwd = http_credential.split(":", 1)
                    auth = (user, pwd)
                else:
                    auth = (http_credential, "")
            elif http_auth_mode == "bearer" and http_credential:
                headers["Authorization"] = f"Bearer {http_credential}"

            if not url.startswith("https") and not url.startswith("http"):
                url = f"http://{url}"

            resp = requests.get(url, timeout=timeout, headers=headers, auth=auth)
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
        """测试数据库连接

        支持的 db_type（见 CONTRACT.md 第八章 8.2）：
        mysql / postgresql / redis / oracle / sqlserver / mongodb /
        elasticsearch / tidb / clickhouse / dameng / oceanbase / mariadb / sqlite
        """
        db_type = config.get("db_type", "mysql")
        port = config.get("db_port", 3306)
        username = config.get("db_user", "")
        password = config.get("db_password", "")
        database = config.get("db_name", "")
        timeout = 10

        if db_type == "sqlite":
            if not database:
                return {"ok": False, "message": "SQLite 需要指定数据库文件路径 (db_name 字段)"}
            import os
            if os.path.isfile(database):
                return {"ok": True, "message": f"SQLite 文件存在: {database}", "latency_ms": 0}
            return {"ok": False, "message": f"SQLite 文件不存在: {database}"}

        if not host:
            return {"ok": False, "message": "主机不能为空"}

        start = datetime.now()
        try:
            # MySQL 协议兼容（mysql / mariadb / tidb / oceanbase）
            if db_type in ("mysql", "mariadb", "tidb", "oceanbase"):
                import pymysql
                conn = pymysql.connect(
                    host=host, port=int(port), user=username, password=password,
                    database=database if database else None, connect_timeout=timeout
                )
                latency = (datetime.now() - start).total_seconds() * 1000
                result = {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
                try:
                    perm_result = ConnectionTester._check_mysql_permissions_conn(conn, username)
                    result["permission_check"] = perm_result
                except Exception as e:
                    result["permission_check"] = {"error": str(e)}
                conn.close()
                return result

            elif db_type == "postgresql":
                import psycopg2
                conn = psycopg2.connect(
                    host=host, port=int(port), user=username, password=password,
                    dbname=database if database else None, connect_timeout=timeout
                )
                latency = (datetime.now() - start).total_seconds() * 1000
                conn.close()
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            elif db_type == "redis":
                import redis
                r = redis.Redis(host=host, port=int(port), password=password or None, socket_connect_timeout=timeout)
                r.ping()
                latency = (datetime.now() - start).total_seconds() * 1000
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            elif db_type == "oracle":
                try:
                    import oracledb
                except ImportError:
                    try:
                        import cx_Oracle as oracledb
                    except ImportError:
                        return {"ok": False, "message": "缺少驱动: oracledb，请执行 pip install oracledb"}
                dsn = oracledb.makedsn(host, int(port), service_name=database or None)
                conn = oracledb.connect(user=username, password=password, dsn=dsn)
                latency = (datetime.now() - start).total_seconds() * 1000
                conn.close()
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            elif db_type == "sqlserver":
                try:
                    import pymssql
                except ImportError:
                    return {"ok": False, "message": "缺少驱动: pymssql，请执行 pip install pymssql"}
                conn = pymssql.connect(
                    server=host, port=int(port), user=username, password=password,
                    database=database if database else None, login_timeout=timeout
                )
                latency = (datetime.now() - start).total_seconds() * 1000
                conn.close()
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            elif db_type == "mongodb":
                try:
                    import pymongo
                except ImportError:
                    return {"ok": False, "message": "缺少驱动: pymongo，请执行 pip install pymongo"}
                if username and password:
                    uri = f"mongodb://{username}:{password}@{host}:{port}/{database or ''}"
                else:
                    uri = f"mongodb://{host}:{port}/{database or ''}"
                client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout * 1000)
                client.admin.command("ping")
                latency = (datetime.now() - start).total_seconds() * 1000
                client.close()
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            elif db_type == "elasticsearch":
                import requests as _req
                url = f"http://{host}:{int(port)}/_cluster/health"
                auth = (username, password) if username and password else None
                resp = _req.get(url, timeout=timeout, auth=auth)
                latency = (datetime.now() - start).total_seconds() * 1000
                if resp.status_code < 500:
                    return {"ok": True, "message": f"{db_type} 连接成功 (HTTP {resp.status_code}, 延迟 {latency:.0f}ms)", "latency_ms": latency}
                return {"ok": False, "message": f"{db_type} HTTP {resp.status_code}: {resp.reason}"}

            elif db_type == "clickhouse":
                import requests as _req
                url = f"http://{host}:{int(port)}/?query=SELECT%201"
                auth = (username, password) if username and password else None
                resp = _req.get(url, timeout=timeout, auth=auth)
                latency = (datetime.now() - start).total_seconds() * 1000
                if resp.status_code == 200:
                    return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}
                return {"ok": False, "message": f"{db_type} HTTP {resp.status_code}: {resp.reason}"}

            elif db_type == "dameng":
                try:
                    import dmPython
                except ImportError:
                    # 驱动未安装时回退到 TCP 端口连通性测试
                    return ConnectionTester._tcp_only(host, port, db_type)
                conn = dmPython.connect(user=username, password=password, server=host, port=int(port))
                latency = (datetime.now() - start).total_seconds() * 1000
                conn.close()
                return {"ok": True, "message": f"{db_type} 连接成功 (延迟 {latency:.0f}ms)", "latency_ms": latency}

            else:
                return {"ok": False, "message": f"不支持的数据库类型: {db_type}"}
        except ImportError as e:
            return {"ok": False, "message": f"缺少驱动: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"连接失败: {e}"}

    @staticmethod
    def _tcp_only(host: str, port, db_type: str) -> dict:
        """无驱动时回退到 TCP 端口连通性测试"""
        start = datetime.now()
        try:
            sock = socket.create_connection((host, int(port)), timeout=10)
            sock.close()
            latency = (datetime.now() - start).total_seconds() * 1000
            return {"ok": True, "message": f"{db_type} 端口连通 (延迟 {latency:.0f}ms, 未做认证)", "latency_ms": latency}
        except Exception as e:
            return {"ok": False, "message": f"{db_type} 端口不通: {e}"}

    @staticmethod
    def _test_middleware(host: str, config: dict) -> dict:
        """测试中间件连接（按 mw_subtype 选择健康检查路径，见 CONTRACT.md 第八章 8.1）

        connection_type='http' 且 config 含 mw_subtype 时由 _test_http 路由到此。
        """
        mw_subtype = (config.get("mw_subtype") or "").lower()
        mw_port = config.get("mw_port", 80)
        mw_admin_url = config.get("mw_admin_url", "")
        timeout = 10

        # TCP 端口连通类（无标准 HTTP 健康检查接口）
        tcp_only_types = {"kafka", "rocketmq", "zookeeper"}
        if mw_subtype in tcp_only_types:
            return ConnectionTester._tcp_only(host, mw_port, mw_subtype)

        # 各中间件的健康检查路径（mw_subtype -> health path）
        health_paths = {
            "nginx": "/",
            "apache": "/",
            "tomcat": "/",
            "jetty": "/",
            "weblogic": "/console",
            "websphere": "/ibm/console",
            "wildfly": "/",
            "rabbitmq": "/api/overview",
            "activemq": "/api/jolokia/",
            "pulsar": "/admin/v2/brokers/healthcheck",
            "nacos": "/nacos/v1/ns/operator/metrics",
            "apollo": "/health",
            "consul": "/v1/status/leader",
            "eureka": "/eureka/apps",
            "etcd": "/health",
            "sentinel": "/health",
            "apisix": "/apisix/status",
            "kong": "/status",
            "spring_cloud_gateway": "/actuator/health",
            "haproxy": "/stats",
            "seata": "/health",
            "minio": "/minio/health/live",
        }

        path = health_paths.get(mw_subtype, "/")

        # 拼接 URL：优先使用 mw_admin_url，否则用 host:port + path
        if mw_admin_url:
            url = mw_admin_url
            if not url.endswith(path) and mw_subtype != "":
                # admin_url 已含路径时不再追加
                if not url.rstrip("/").endswith(path.rstrip("/")):
                    url = url.rstrip("/") + path
        else:
            if not host:
                return {"ok": False, "message": "中间件主机不能为空"}
            url = f"http://{host}:{int(mw_port)}{path}"

        if not url.startswith("http"):
            url = f"http://{url}"

        http_auth_mode = config.get("http_auth", "")
        http_credential = config.get("http_credential", "")

        start = datetime.now()
        try:
            import requests
            auth = None
            headers = {}
            if http_auth_mode == "basic" and http_credential:
                if ":" in http_credential:
                    user, pwd = http_credential.split(":", 1)
                    auth = (user, pwd)
                else:
                    auth = (http_credential, "")
            elif http_auth_mode == "bearer" and http_credential:
                headers["Authorization"] = f"Bearer {http_credential}"

            resp = requests.get(url, timeout=timeout, headers=headers, auth=auth)
            latency = (datetime.now() - start).total_seconds() * 1000

            # 2xx/3xx/401/403 都算"服务存活"（401/403 说明需认证但服务在）
            if resp.status_code < 500:
                return {
                    "ok": True,
                    "message": f"{mw_subtype or 'middleware'} 连接成功 (HTTP {resp.status_code}, 延迟 {latency:.0f}ms)",
                    "latency_ms": latency,
                }
            return {"ok": False, "message": f"{mw_subtype or 'middleware'} HTTP {resp.status_code}: {resp.reason}"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "message": f"{mw_subtype or 'middleware'} 连接失败，服务不可达"}
        except requests.exceptions.Timeout:
            return {"ok": False, "message": f"{mw_subtype or 'middleware'} 连接超时"}
        except Exception as e:
            return {"ok": False, "message": f"{mw_subtype or 'middleware'} 连接异常: {e}"}

    @staticmethod
    def _check_mysql_permissions_conn(conn, user: str) -> dict:
        """从已有 MySQL 连接检测账号权限"""
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM mysql.user WHERE User=%s AND Host=%s", (user, "%"))
            privs = []
            if cur.description:
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    priv_map = dict(zip(cols, row))
                    for col, val in priv_map.items():
                        if val in (True, 1, "Y", "y"):
                            privs.append(col)

            try:
                # SHOW GRANTS 不支持参数化绑定，先对用户名做白名单校验防注入
                import re as _re
                if not _re.match(r"^[A-Za-z0-9_\-.@ ]{1,64}$", user or ""):
                    grants = []
                else:
                    _safe_user = (user or "").replace("'", "''")
                    cur.execute(f"SHOW GRANTS FOR '{_safe_user}'@'%'")
                    grants = [r[0] for r in cur.fetchall()]
            except Exception:
                grants = []

            ddl = [p for p in privs if p in ("Drop_priv", "Alter_priv", "Create_priv", "Index_priv", "References_priv")]
            dml = [p for p in privs if p in ("Insert_priv", "Update_priv", "Delete_priv", "Execute_priv")]
            dcl = [p for p in privs if p in ("Grant_priv", "Super_priv", "Shutdown_priv", "Process_priv", "File_priv")]
            read = [p for p in privs if p in ("Select_priv", "Show_db_priv", "Show_view_priv", "Lock_tables_priv")]

            has_grant = "Grant_priv" in privs or any("GRANT OPTION" in g for g in grants)
            is_super = "Super_priv" in privs

            if has_grant or is_super or ddl or "File_priv" in privs:
                risk_level, risk_label, risk_desc = "high", "🔴 高危", "该账号拥有极高危权限，AI 可能导致数据丢失或权限失控"
            elif dml:
                risk_level, risk_label, risk_desc = "medium", "⚠️ 警告", "该账号拥有 DML 权限，AI 可修改业务数据"
            elif read and not dml and not ddl:
                risk_level, risk_label, risk_desc = "safe", "✅ 安全", "该账号仅有读权限，AI 仅能查询无法修改数据"
            else:
                risk_level, risk_label, risk_desc = "unknown", "❓ 未知", "无法明确判定权限等级"

            return {
                "risk_level": risk_level,
                "risk_label": risk_label,
                "risk_desc": risk_desc,
                "privileges": {"read": read, "dml": dml, "ddl": ddl, "dcl": dcl},
                "has_grant_option": has_grant,
                "is_super_user": is_super,
            }
        finally:
            cur.close()


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
