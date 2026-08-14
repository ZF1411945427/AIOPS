import json
import re
import subprocess
from datetime import datetime

from app.models import DataSource


_PKI_PATTERNS_KUBEADM = [
    "/etc/kubernetes/pki/*.crt",
    "/etc/kubernetes/pki/etcd/*.crt",
]
_CONFIG_PATTERN_KUBEADM = "/etc/kubernetes/*.conf"

_PKI_PATTERNS_K3S = [
    "/var/lib/rancher/k3s/server/tls/*.crt",
]
_CONFIG_PATTERN_K3S = "/var/lib/rancher/k3s/server/cred/*.yaml"

_PKI_PATTERNS_RKE = [
    "/etc/kubernetes/ssl/*.pem",
]
_CONFIG_PATTERN_RKE = "/etc/kubernetes/ssl/kubeconfig*.yaml"

_PKI_PATTERNS_OPENSHIFT = [
    "/etc/kubernetes/static-pod-resources/**/*.crt",
]
_CONFIG_PATTERN_OPENSHIFT = "/etc/kubernetes/*.conf"

DISTRO_CONFIG = {
    "kubeadm": {
        "label": "kubeadm",
        "detect_cmds": ["ls /etc/kubernetes/pki/apiserver.crt 2>/dev/null"],
        "pki_patterns": _PKI_PATTERNS_KUBEADM,
        "config_pattern": _CONFIG_PATTERN_KUBEADM,
        "renew_cmd": "kubeadm certs renew all 2>&1 || echo '__RENEW_FAILED__'",
        "renew_hint": "",
    },
    "k3s": {
        "label": "K3s",
        "detect_cmds": ["ls /var/lib/rancher/k3s/server/tls/server.crt 2>/dev/null"],
        "pki_patterns": _PKI_PATTERNS_K3S,
        "config_pattern": _CONFIG_PATTERN_K3S,
        "renew_cmd": "k3s certificate rotate 2>&1 || echo '__RENEW_FAILED__'",
        "renew_hint": "K3s 续期后需重启 server 生效",
    },
    "rke": {
        "label": "RKE",
        "detect_cmds": ["ls /etc/kubernetes/ssl/kube-apiserver.pem 2>/dev/null"],
        "pki_patterns": _PKI_PATTERNS_RKE,
        "config_pattern": _CONFIG_PATTERN_RKE,
        "renew_cmd": "rke cert rotate 2>&1 || echo '__RENEW_FAILED__'",
        "renew_hint": "RKE 续期需在 RKE 工作节点执行 `rke cert rotate`",
    },
    "openshift": {
        "label": "OpenShift",
        "detect_cmds": ["ls /etc/kubernetes/static-pod-resources/ 2>/dev/null"],
        "pki_patterns": _PKI_PATTERNS_OPENSHIFT,
        "config_pattern": _CONFIG_PATTERN_OPENSHIFT,
        "renew_cmd": "oc adm certificate rotate 2>&1 || echo '__RENEW_FAILED__'",
        "renew_hint": "OpenShift 建议通过 OCP 控制台或 `oc` 命令更新证书",
    },
    "binary": {
        "label": "自定义路径",
        "detect_cmds": [],
        "pki_patterns": [],
        "config_pattern": "",
        "renew_cmd": "",
        "renew_hint": "自定义安装，请手动更新证书或配置 renew_command",
    },
    "cloud": {
        "label": "云托管集群",
        "detect_cmds": [],
        "pki_patterns": [],
        "config_pattern": "",
        "renew_cmd": "",
        "renew_hint": "云托管集群不支持通过此工具续期，请通过云控制台操作",
    },
}

DETECT_ORDER = ["kubeadm", "k3s", "rke", "openshift"]


def _ssh_exec(host: str, user: str, password: str, port: int, commands: list, timeout: int = 25) -> dict:
    try:
        import paramiko
    except ImportError:
        paramiko = None

    results = []
    if paramiko:
        try:
            from app.services.ssh_helper import connect_ssh
            client = connect_ssh(host, port=port, username=user, password=password, timeout=8)
            for cmd in commands:
                _, out, err = client.exec_command(cmd, timeout=timeout)
                results.append((cmd, out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")))
            client.close()
            return {"ok": True, "results": results}
        except Exception as e:
            if host in ("127.0.0.1", "localhost"):
                try:
                    for cmd in commands:
                        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                           encoding="utf-8", errors="replace", timeout=timeout)
                        results.append((cmd, p.stdout, p.stderr))
                    return {"ok": True, "results": results, "fallback": "local"}
                except Exception as e2:
                    return {"ok": False, "error": f"SSH 失败且本地回退失败: {e2}"}
            return {"ok": False, "error": f"SSH 连接失败: {e}"}
    else:
        return {"ok": False, "error": "未安装 paramiko"}


def _parse_enddate(output: str):
    m = re.search(r"notAfter=([^\r\n]+)", output)
    if not m:
        return None, "无法解析 enddate"
    try:
        dt = datetime.strptime(m.group(1).strip(), "%b %d %H:%M:%S %Y %Z")
        return dt, None
    except ValueError:
        try:
            dt = datetime.strptime(m.group(1).strip(), "%b %d %H:%M:%S %Y")
            return dt, None
        except ValueError:
            return None, f"日期格式无法解析: {m.group(1).strip()}"


def _cert_label(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    mapping = {
        "apiserver.crt": "kube-apiserver 服务证书",
        "apiserver-kubelet-client.crt": "kube-apiserver 连接 kubelet 客户端证书",
        "apiserver-etcd-client.crt": "kube-apiserver 连接 etcd 客户端证书",
        "front-proxy-client.crt": "front-proxy 客户端证书",
        "admin.conf": "admin kubeconfig",
        "kubelet.conf": "kubelet kubeconfig",
        "controller-manager.conf": "controller-manager kubeconfig",
        "scheduler.conf": "scheduler kubeconfig",
        "server.crt": "K3s server 证书",
        "client-admin.crt": "K3s admin 客户端证书",
        "client-kube-apiserver.crt": "K3s apiserver 客户端证书",
        "client-kube-controller-manager.crt": "K3s controller-manager 客户端证书",
        "client-kube-scheduler.crt": "K3s scheduler 客户端证书",
        "client-kubelet.crt": "K3s kubelet 客户端证书",
        "kube-apiserver.pem": "RKE apiserver 证书",
        "kube-controller-manager.pem": "RKE controller-manager 证书",
        "kube-scheduler.pem": "RKE scheduler 证书",
        "kube-apiserver-proxy.pem": "RKE apiserver-proxy 证书",
        "kube-node.pem": "RKE node 证书",
    }
    if base in mapping:
        return mapping[base]
    crt_base = base.replace(".pem", ".crt")
    return mapping.get(crt_base, base)


def _detect_distro(ssh_host: str, ssh_user: str, ssh_password: str, ssh_port: int) -> tuple:
    """单次 SSH 连接内并行探测所有发行版特征路径，避免离线主机逐项超时。"""
    cmds = []
    mapping = []
    for distro_key in DETECT_ORDER:
        for c in DISTRO_CONFIG[distro_key]["detect_cmds"]:
            cmds.append(c)
            mapping.append(distro_key)
    if not cmds:
        return "binary", "自定义路径"
    ssh = _ssh_exec(ssh_host, ssh_user, ssh_password, ssh_port, cmds, timeout=12)
    if ssh.get("ok"):
        for idx, (_, out, _err) in enumerate(ssh["results"]):
            if out.strip():
                distro_key = mapping[idx]
                return distro_key, DISTRO_CONFIG[distro_key]["label"]
    return "binary", "自定义路径"


def _collect_cert_files(ssh_host, ssh_user, ssh_password, ssh_port, distro_key, extra_patterns):
    distro = DISTRO_CONFIG[distro_key]
    commands = []
    for pattern in distro["pki_patterns"]:
        commands.append(f"ls -1 {pattern} 2>/dev/null")
    if distro["config_pattern"]:
        commands.append(f"ls -1 {distro['config_pattern']} 2>/dev/null")
    for pattern in (extra_patterns or []):
        commands.append(f"ls -1 {pattern} 2>/dev/null")

    if not commands:
        return [], "未配置证书路径，请指定 cert_paths"

    ssh = _ssh_exec(ssh_host, ssh_user, ssh_password, ssh_port, commands)
    if not ssh.get("ok"):
        return [], ssh.get("error", "SSH 执行失败")

    cert_files = []
    for _, out, _err in ssh["results"]:
        for line in out.splitlines():
            line = line.strip()
            if line and line not in cert_files:
                cert_files.append(line)

    if not cert_files:
        return [], "未找到证书文件。请确认集群类型和证书路径。"
    return cert_files, None


def _parse_certs(ssh_host, ssh_user, ssh_password, ssh_port, cert_files):
    """单次 SSH 连接内批量解析所有证书有效期。"""
    certs = []
    if not cert_files:
        return certs

    cmds = []
    for path in cert_files:
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        if ext == "crt":
            cmds.append(f"openssl x509 -in {path} -noout -subject -enddate 2>/dev/null || echo 'PARSE_FAILED'")
        elif ext == "pem":
            cmds.append(
                f"openssl x509 -in {path} -noout -subject -enddate 2>/dev/null || "
                f"openssl req -in {path} -noout -subject 2>/dev/null || echo 'PARSE_FAILED'"
            )
        elif ext == "conf" or ext == "yaml":
            cmds.append(
                f"tmpf=$(mktemp); "
                f"grep client-certificate-data {path} 2>/dev/null | awk '{{print $2}}' | base64 -d > $tmpf 2>/dev/null; "
                f"if [ -s $tmpf ]; then openssl x509 -in $tmpf -noout -subject -enddate 2>/dev/null; "
                f"else echo 'PARSE_FAILED'; fi; rm -f $tmpf"
            )
        else:
            continue

    if not cmds:
        return certs

    ssh2 = _ssh_exec(ssh_host, ssh_user, ssh_password, ssh_port, cmds, timeout=40)
    results = ssh2["results"] if ssh2.get("ok") else []

    for i, path in enumerate(cert_files):
        out = results[i][1] if i < len(results) else ""
        if "PARSE_FAILED" in out:
            certs.append({
                "path": path,
                "name": _cert_label(path),
                "subject": "",
                "not_after": "",
                "days_left": None,
                "status": "error",
                "parse_error": "无法解析此文件格式",
            })
            continue

        enddate, err = _parse_enddate(out)
        subject = ""
        sm = re.search(r"subject=(.+)", out)
        if sm:
            subject = sm.group(1).strip()

        days_left = None
        status = "error"
        if enddate:
            days_left = int((enddate - datetime.now()).total_seconds() // 86400)
            if days_left < 0:
                status = "expired"
            elif days_left <= 30:
                status = "expiring"
            elif days_left <= 90:
                status = "warning"
            else:
                status = "ok"
        elif err:
            status = "error"

        certs.append({
            "path": path,
            "name": _cert_label(path),
            "subject": subject,
            "not_after": enddate.strftime("%Y-%m-%d %H:%M:%S") if enddate else "",
            "days_left": days_left,
            "status": status,
            "parse_error": err,
        })
    return certs


def _inspect_via_api(ds: DataSource, cfg: dict) -> dict:
    try:
        from kubernetes import client, config as k8s_config
    except ImportError:
        return {"cluster": ds.name, "ok": False, "error": "缺少 kubernetes Python 包", "distro": "cloud"}

    try:
        if cfg.get("kubeconfig"):
            k8s_config.load_kube_config_from_dict(cfg["kubeconfig"])
            api_client = client.ApiClient()
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            configuration = client.Configuration()
            configuration.host = cfg["k8s_api_server"]
            configuration.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            configuration.verify_ssl = cfg.get("verify_ssl", False)
            configuration.timeout = 15
            api_client = client.ApiClient(configuration=configuration)
        else:
            return {"cluster": ds.name, "ok": False, "error": "缺少 k8s_api_server/k8s_token 配置", "distro": "cloud"}
    except Exception as e:
        return {"cluster": ds.name, "ok": False, "error": f"K8s API 连接失败: {e}", "distro": "cloud"}

    v1 = client.CoreV1Api(api_client=api_client)
    try:
        secrets = v1.list_namespaced_secret("kube-system", label_selector="")
    except Exception as e:
        api_client.close()
        return {"cluster": ds.name, "ok": False, "error": f"读取 kube-system Secrets 失败: {e}", "distro": "cloud"}

    cert_candidates = []
    for secret in secrets.items:
        name = secret.metadata.name or ""
        data = secret.data or {}
        if any(k.endswith((".crt", ".pem", "cert")) for k in data):
            cert_candidates.append((name, data))

    certs = []
    for secret_name, data in cert_candidates:
        for key, b64_val in data.items():
            if not key.endswith((".crt", ".pem")) and "cert" not in key.lower():
                continue
            import base64
            try:
                pem_bytes = base64.b64decode(b64_val)
                pem_text = pem_bytes.decode("utf-8", "replace")
            except Exception:
                continue
            if "BEGIN CERTIFICATE" not in pem_text:
                continue
            import tempfile
            import os
            tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False)
            try:
                tmpf.write(pem_text)
                tmpf.close()
                p = subprocess.run(
                    f"openssl x509 -in {tmpf.name} -noout -subject -enddate 2>/dev/null",
                    shell=True, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=10,
                )
                out = p.stdout
                enddate, err = _parse_enddate(out)
                subject = ""
                sm = re.search(r"subject=(.+)", out)
                if sm:
                    subject = sm.group(1).strip()
                days_left = None
                status = "error"
                if enddate:
                    days_left = int((enddate - datetime.now()).total_seconds() // 86400)
                    if days_left < 0:
                        status = "expired"
                    elif days_left <= 30:
                        status = "expiring"
                    elif days_left <= 90:
                        status = "warning"
                    else:
                        status = "ok"
                certs.append({
                    "path": f"secret:{secret_name}/{key}",
                    "name": f"{secret_name}/{key}",
                    "subject": subject,
                    "not_after": enddate.strftime("%Y-%m-%d %H:%M:%S") if enddate else "",
                    "days_left": days_left,
                    "status": status,
                    "parse_error": err,
                })
            finally:
                os.unlink(tmpf.name)

    api_client.close()

    if not certs:
        return {"cluster": ds.name, "ok": False, "error": "未在 kube-system Secret 中找到可解析的证书", "distro": "cloud"}

    summary = {"total": len(certs), "ok": 0, "warning": 0, "expiring": 0, "expired": 0, "error": 0}
    for c in certs:
        if c["status"] in summary:
            summary[c["status"]] += 1

    return {
        "cluster": ds.name,
        "ok": True,
        "endpoint": ds.endpoint or "",
        "distro": "cloud",
        "distro_label": "云托管集群",
        "inspect_method": "K8s API (Secret)",
        "inspect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "certs": certs,
        "summary": summary,
    }


def inspect_cluster(ds: DataSource) -> dict:
    cfg = {}
    if ds.auth_config:
        try:
            cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else (ds.auth_config or {})
        except Exception:
            cfg = {}

    ssh_host = cfg.get("ssh_host") or ""
    ssh_user = cfg.get("ssh_user") or "root"
    ssh_password = cfg.get("ssh_password") or ""
    ssh_port = int(cfg.get("ssh_port") or 22)
    extra_patterns = cfg.get("cert_paths")
    if isinstance(extra_patterns, str):
        try:
            extra_patterns = json.loads(extra_patterns)
        except Exception:
            extra_patterns = []
    user_distro = cfg.get("k8s_distro", "auto")

    if user_distro == "cloud" or not ssh_host:
        if cfg.get("k8s_api_server") or cfg.get("kubeconfig"):
            return _inspect_via_api(ds, cfg)
        if not ssh_host:
            return {"cluster": ds.name, "ok": False, "error": "数据源未配置 ssh_host 或 k8s_api_server，无法巡检证书"}

    if user_distro and user_distro != "auto" and user_distro in DISTRO_CONFIG:
        distro_key = user_distro
        distro_label = DISTRO_CONFIG[distro_key]["label"]
    else:
        distro_key, distro_label = _detect_distro(ssh_host, ssh_user, ssh_password, ssh_port)

    # SSH 检测失败/不可达但配置了 API Server → 自动回退 API 巡检
    if distro_key == "binary" and not extra_patterns and (cfg.get("k8s_api_server") or cfg.get("kubeconfig")):
        return _inspect_via_api(ds, cfg)

    cert_files, err = _collect_cert_files(ssh_host, ssh_user, ssh_password, ssh_port, distro_key, extra_patterns)
    if err:
        return {"cluster": ds.name, "ok": False, "error": err, "distro": distro_key, "distro_label": distro_label}

    certs = _parse_certs(ssh_host, ssh_user, ssh_password, ssh_port, cert_files)

    summary = {"total": len(certs), "ok": 0, "warning": 0, "expiring": 0, "expired": 0, "error": 0}
    for c in certs:
        if c["status"] in summary:
            summary[c["status"]] += 1

    return {
        "cluster": ds.name,
        "ok": True,
        "endpoint": ds.endpoint or "",
        "ssh_host": ssh_host,
        "distro": distro_key,
        "distro_label": distro_label,
        "inspect_method": "SSH",
        "inspect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "certs": certs,
        "summary": summary,
    }


def renew_cluster(ds: DataSource, force: bool = False) -> dict:
    cfg = {}
    if ds.auth_config:
        try:
            cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else (ds.auth_config or {})
        except Exception:
            cfg = {}

    ssh_host = cfg.get("ssh_host") or ""
    ssh_user = cfg.get("ssh_user") or "root"
    ssh_password = cfg.get("ssh_password") or ""
    ssh_port = int(cfg.get("ssh_port") or 22)
    user_distro = cfg.get("k8s_distro", "auto")

    if not ssh_host:
        return {"ok": False, "error": "数据源未配置 ssh_host，无法续期"}

    if user_distro and user_distro != "auto" and user_distro in DISTRO_CONFIG:
        distro_key = user_distro
    else:
        distro_key, _ = _detect_distro(ssh_host, ssh_user, ssh_password, ssh_port)

    distro = DISTRO_CONFIG.get(distro_key, DISTRO_CONFIG["binary"])
    renew_cmd = cfg.get("renew_command") or distro["renew_cmd"]

    if not renew_cmd:
        return {"ok": False, "error": distro["renew_hint"], "distro": distro_key}

    commands = [renew_cmd]
    if distro_key in ("kubeadm",):
        commands.append("ls /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/manifests/etcd.yaml 2>/dev/null || true")

    ssh = _ssh_exec(ssh_host, ssh_user, ssh_password, ssh_port, commands)
    if not ssh.get("ok"):
        return {"ok": False, "error": ssh.get("error", "SSH 执行失败"), "distro": distro_key}

    renew_out = ssh["results"][0][1] if ssh["results"] else ""
    manifest_out = ssh["results"][1][1] if len(ssh["results"]) > 1 else ""

    failed = "__RENEW_FAILED__" in renew_out
    apiserver_manifest = "kube-apiserver.yaml" in manifest_out
    etcd_manifest = "etcd.yaml" in manifest_out
    restart_hint = distro["renew_hint"]
    if apiserver_manifest or etcd_manifest:
        restart_hint = "已检测到静态 Pod manifest，kubelet 将自动重启 kube-apiserver/etcd（约需 1-2 分钟）"
    elif not restart_hint:
        restart_hint = "续期完成，请确认组件是否需要手动重启"

    return {
        "ok": not failed,
        "cluster": ds.name,
        "distro": distro_key,
        "output": renew_out,
        "restart_hint": restart_hint,
        "error": None if not failed else "续期命令执行失败，请查看输出",
    }