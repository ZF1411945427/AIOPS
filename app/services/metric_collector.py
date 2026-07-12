"""SSH 指标采集器 - 通过 SSH 连接资产执行命令采集真实系统指标"""
import json
import socket
import paramiko
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import MetricRecord, Asset


# 采集命令（兼容 CentOS/Ubuntu 等 Linux 发行版）
COLLECT_COMMANDS = {
    # === CPU (5) ===
    "cpu_usage": "top -bn1 | awk '/Cpu/{print $2}'",
    "cpu_iowait": "top -bn1 | awk '/Cpu/{print $10}'",
    "loadavg_1min": "cut -d' ' -f1 /proc/loadavg",
    "loadavg_5min": "cut -d' ' -f2 /proc/loadavg",
    "loadavg_15min": "cut -d' ' -f3 /proc/loadavg",
    # === 内存 (3) ===
    "memory_usage": "free | awk '/Mem:/{print int($3/$2*100)}'",
    "memory_available": "free | awk '/Mem:/{print $7}'",
    "swap_usage": "free | awk '/Swap:/{if($2>0) print int($3/$2*100); else print 0}'",
    # === 磁盘 (2) ===
    "disk_usage": "df -P / | awk 'NR==2{print $5}' | tr -d %",
    "disk_inode_usage": "df -iP / | awk 'NR==2{print $5}' | tr -d %",
    # === 网络 (4) ===
    "network_rx_bytes": "cat /proc/net/dev | awk '/eth0|ens|eno/{print $2}' | head -1",
    "network_tx_bytes": "cat /proc/net/dev | awk '/eth0|ens|eno/{print $10}' | head -1",
    "tcp_established": "netstat -an 2>/dev/null | grep -c ESTABLISHED",
    "tcp_time_wait": "netstat -an 2>/dev/null | grep -c TIME_WAIT",
    # === 系统 (4) ===
    "uptime_seconds": "awk '{print int($1)}' /proc/uptime",
    "process_count": "ls /proc | grep -c '^[0-9]'",
    "zombie_process": "ps -eo stat 2>/dev/null | grep -c '^Z'",
    "open_files": "cat /proc/sys/fs/file-nr | awk '{print $1}'",
    # === 应用连接 (3) ===
    "ssh_connections": "netstat -an 2>/dev/null | grep -c ':22 '",
    "http_connections": "netstat -an 2>/dev/null | grep -cE ':80 |:443 '",
    "mysql_connections": "netstat -an 2>/dev/null | grep -c ':3306 '",
}

METRIC_UNITS = {
    "cpu_usage": "%", "cpu_iowait": "%",
    "loadavg_1min": "", "loadavg_5min": "", "loadavg_15min": "",
    "memory_usage": "%", "memory_available": "MB", "swap_usage": "%",
    "disk_usage": "%", "disk_inode_usage": "%",
    "network_rx_bytes": "bytes", "network_tx_bytes": "bytes",
    "tcp_established": "", "tcp_time_wait": "",
    "uptime_seconds": "s", "process_count": "", "zombie_process": "", "open_files": "",
    "ssh_connections": "", "http_connections": "", "mysql_connections": "",
}


def _ssh_connect(asset, timeout=10):
    """建立 SSH 连接"""
    config = {}
    try:
        raw = getattr(asset, "connection_config", "{}")
        if isinstance(raw, str) and raw:
            config = json.loads(raw)
        elif raw:
            config = raw
    except (json.JSONDecodeError, TypeError):
        config = {}

    host = getattr(asset, "ip", "")
    port = config.get("ssh_port", 22)
    username = config.get("ssh_user", "root")
    password = config.get("ssh_password", "")

    if not host:
        return None

    from app.services.ssh_helper import get_ssh_client
    ssh = get_ssh_client()
    ssh.connect(host, port=port, username=username, password=password,
                timeout=timeout, banner_timeout=timeout)
    return ssh


def _parse_value(raw):
    """把命令输出解析成 float"""
    if not raw:
        return None
    try:
        first = raw.strip().splitlines()[0].strip()
        return round(float(first), 2)
    except (ValueError, IndexError):
        return None


def collect_asset_metrics(asset, db):
    """采集单个资产的指标"""
    result = {"metrics": [], "error": None}
    try:
        ssh = _ssh_connect(asset)
        if not ssh:
            result["error"] = "no ip"
            return result

        now = datetime.now()
        for name, cmd in COLLECT_COMMANDS.items():
            try:
                stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
                raw = stdout.read().decode(errors="ignore").strip()
                val = _parse_value(raw)
                if val is not None:
                    db.add(MetricRecord(
                        asset_id=asset.id,
                        name=name,
                        value=val,
                        unit=METRIC_UNITS.get(name, ""),
                        timestamp=now,
                    ))
                    result["metrics"].append({"name": name, "value": val})
            except Exception:
                pass

        ssh.close()
        db.commit()
    except Exception as e:
        result["error"] = str(e)
    return result


def collect_all_metrics(db):
    """采集所有 online 资产的指标"""
    assets = db.query(Asset).filter(Asset.status == "online").all()
    summary = {"total": len(assets), "success": 0, "failed": 0, "metrics_collected": 0, "errors": []}
    for asset in assets:
        r = collect_asset_metrics(asset, db)
        if r["error"]:
            summary["failed"] += 1
            summary["errors"].append(asset.name + ": " + r["error"])
        else:
            summary["success"] += 1
            summary["metrics_collected"] += len(r["metrics"])
    return summary
