import json
import random
import re
from datetime import datetime
from typing import Optional

import paramiko
from sqlalchemy.orm import Session

from app.models import AutoRemediation, RemediationLog, Alert, AlertRule, Asset, PendingAction, AIProvider, RemediationWorkflow, DataSource, DiagnosisReport, KbDocument

# 关联分析短时缓存：同一 asset_id 60 秒内复用，避免每次 AI 分析都重复查询
_CORRELATION_CACHE = {}
_CORRELATION_CACHE_TTL = 60


def list_remediations(db: Session):
    return db.query(AutoRemediation).order_by(AutoRemediation.id.desc()).all()


def create_remediation(db: Session, data: dict):
    params_val = data.pop("params", {})
    if isinstance(params_val, dict):
        data["remediation_params"] = json.dumps(params_val, ensure_ascii=False)
    else:
        data["remediation_params"] = str(params_val) if params_val else ""
    r = AutoRemediation(**data)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def delete_remediation(db: Session, remediation_id: int):
    db.query(AutoRemediation).filter(AutoRemediation.id == remediation_id).delete()
    db.commit()


def get_remediation_logs(db: Session, limit: int = 50):
    return db.query(RemediationLog).order_by(RemediationLog.created_at.desc()).limit(limit).all()


def get_remediation_logs_paged(db: Session, page: int = 1, per_page: int = 20):
    """分页查询自愈执行记录，返回 (items, total, total_pages)."""
    q = db.query(RemediationLog).order_by(RemediationLog.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return items, total, total_pages


ACTIONS = {
    "restart": {"label": "重启服务", "template": "systemctl restart {service}"},
    "clean": {"label": "清理磁盘", "template": "清理 {target} 磁盘空间"},
    "scale": {"label": "扩缩容", "template": "adjust {target} replicas to {count}"},
    "script": {"label": "执行脚本", "template": "bash {script_path}"},
    "run_command": {"label": "执行命令", "template": "{command}"},
    "notify": {"label": "发送通知", "template": "notify {channel} {message}"},
}


# ── 确定性命令风险分类器（不依赖 LLM 自评，根据命令语义硬判定）──
# 只读命令白名单（首词匹配）：这些命令默认只读不修改系统状态
_READONLY_CMD_PREFIXES = {
    "ps", "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg",
    "df", "free", "top", "htop", "uptime", "ls", "stat", "file", "ll",
    "netstat", "ss", "who", "w", "last", "iostat", "vmstat", "sar", "mpstat",
    "dmesg", "date", "hostname", "uname", "id", "env", "pwd", "which", "whereis",
    "ping", "traceroute", "dig", "nslookup", "host",
    "lscpu", "lsmem", "lsblk", "lspci", "lsusb", "lsof",
}
# 变更关键词（命令中含这些词则判定为变更操作，需审批）
_MUTATING_KEYWORDS = {
    "restart", "start", "stop", "reload", "kill", "killall", "pkill",
    "rm ", "rmdir", "delete", "scale", "vacuum", "rotate",
    "mkfs", "dd ", "shutdown", "reboot", "halt", "poweroff",
    "chmod", "chown", "mv ", "cp ", "scp ", "rsync",
    "tee ", " > ", " >>",
}


def _classify_command_risk(action_type: str, command: str) -> tuple:
    """确定性命令风险分类器 — 根据 action_type + 命令语义硬判定风险等级与是否可自动执行.

    返回 (risk_level, auto_exec):
      - risk_level: low/medium/high
      - auto_exec: True=只读诊断可自动执行(免审批), False=变更操作需人工审批

    设计原则（fail-safe）：
    - 只读命令（ps/df/free/journalctl查看/kubectl get 等）→ low，自动执行
    - 变更命令（restart/kill/clean/scale/delete/vacuum 等）→ high，需审批
    - 未知命令 → medium，需审批（宁可多审不漏）
    - notify → low，自动执行
    """
    if action_type == "notify":
        return ("low", True)
    if action_type in ("restart", "clean", "scale", "script"):
        return ("high", False)
    if action_type == "workflow":
        return ("medium", False)

    # run_command: 解析命令内容判定
    cmd = (command or "").strip()
    if not cmd:
        return ("medium", False)
    cmd_lower = cmd.lower()

    # 含变更关键词 → 变更操作
    for kw in _MUTATING_KEYWORDS:
        if kw in cmd_lower:
            return ("high", False)

    first_word = cmd.split()[0].lower() if cmd.split() else ""

    # kubectl 只读子命令 vs 变更子命令
    if first_word == "kubectl":
        parts = cmd.split()
        if len(parts) > 1 and parts[1] in ("get", "describe", "logs", "top", "explain", "version", "cluster-info", "api-resources", "api-versions", "nodes", "events"):
            return ("low", True)
        return ("high", False)
    # docker 只读子命令 vs 变更子命令
    if first_word == "docker":
        parts = cmd.split()
        if len(parts) > 1 and parts[1] in ("ps", "stats", "logs", "inspect", "images", "version", "info", "top", "port", "history", "diff"):
            return ("low", True)
        return ("high", False)
    # systemctl status/is-active 只读 vs restart/stop 变更
    if first_word == "systemctl" or (first_word == "sudo" and len(cmd.split()) > 1 and cmd.split()[1] == "systemctl"):
        parts = cmd.split()
        sub = parts[2] if parts[0] == "sudo" else (parts[1] if len(parts) > 1 else "")
        if sub in ("status", "is-active", "is-enabled", "list-units", "list-unit-files", "show", "cat"):
            return ("low", True)
        return ("high", False)
    # journalctl 查看（无 --vacuum/--rotate）只读
    if first_word == "journalctl":
        if "vacuum" in cmd_lower or "rotate" in cmd_lower:
            return ("high", False)
        return ("low", True)
    # find: 含 -delete/-exec 变更，否则只读
    if first_word == "find":
        if "-delete" in cmd_lower or "-exec" in cmd_lower:
            return ("high", False)
        return ("low", True)
    # 白名单首词 → 只读
    if first_word in _READONLY_CMD_PREFIXES:
        return ("low", True)
    # 未知命令 → fail-safe 需审批
    return ("medium", False)


# 危险命令黑名单：阻止破坏性命令执行（不依赖 LLM 自律，入口硬拦截）
# 匹配即拒绝，防 rm -rf /、格式化、关机重启、fork bomb、覆盖磁盘、远程脚本管道执行等
_DANGEROUS_CMD_PATTERNS = [
    r"rm\s+-rf?\s+/(?:\s|$|\*)",       # rm -rf / 根目录删除
    r"\bmkfs(?:\.\w+)?\b",             # mkfs / mkfs.ext4 格式化
    r"\bdd\s+if=",                     # dd 磁盘写入
    r"\bshutdown\b",                   # 关机
    r"\breboot\b",                     # 重启
    r"\bhalt\b",                       # 停机
    r"\bpoweroff\b",                   # 关机
    r":\s*\(\)\s*\{.*\}",              # :(){:|:&};: fork bomb
    r"chmod\s+-R\s+\d+\s+/(?:\s|$)",   # chmod -R 777 / 递归改根权限
    r">\s*/dev/sd[a-z]",               # > /dev/sda 覆盖磁盘设备
    r"\bcurl\b[^|]*\|\s*(?:bash|sh)",  # curl ... | bash 远程脚本执行
    r"\bwget\b[^|]*\|\s*(?:bash|sh)",  # wget ... | bash 远程脚本执行
]
_DANGEROUS_CMD_RE = re.compile("|".join(_DANGEROUS_CMD_PATTERNS), re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════
# 诊断命令包 —— 按告警指标类型预定义只读诊断命令集（免审批自动执行）
# 设计原则：只读、快执行（<10s）、输出精简、覆盖关键诊断维度
# ══════════════════════════════════════════════════════════════════════
DIAGNOSIS_COMMAND_PACKS = {
    "cpu_usage": [
        {"cmd": "top -bn1 | head -20",              "desc": "系统负载概览", "timeout": 10},
        {"cmd": "ps aux --sort=-%cpu | head -10",    "desc": "CPU占用TOP10进程", "timeout": 10},
        {"cmd": "vmstat 1 3",                        "desc": "CPU详细统计(3次采样)", "timeout": 10},
        {"cmd": "uptime",                            "desc": "系统运行时间与负载", "timeout": 5},
    ],
    "memory_usage": [
        {"cmd": "free -m",                           "desc": "内存使用概览", "timeout": 5},
        {"cmd": "ps aux --sort=-%mem | head -10",    "desc": "内存占用TOP10进程", "timeout": 10},
        {"cmd": "cat /proc/meminfo | head -20",      "desc": "内存详情", "timeout": 5},
        {"cmd": "uptime",                            "desc": "系统运行时间与负载", "timeout": 5},
    ],
    "disk_usage": [
        {"cmd": "df -h",                                              "desc": "磁盘使用概览", "timeout": 5},
        {"cmd": "du -sh /var/log/* 2>/dev/null | sort -rh | head -10","desc": "日志目录大小TOP10", "timeout": 10},
        {"cmd": "find / -type f -size +100M 2>/dev/null | head -20",  "desc": "大文件排查(>100MB)", "timeout": 15},
        {"cmd": "lsblk",                                              "desc": "块设备信息", "timeout": 5},
    ],
    "k8s_pod_crash": [
        {"cmd": "kubectl describe pod {pod_name} -n {namespace}",         "desc": "Pod详情(事件/状态)", "timeout": 15},
        {"cmd": "kubectl logs {pod_name} -n {namespace} --tail=50",      "desc": "Pod日志最近50行", "timeout": 15},
        {"cmd": "kubectl top pod {pod_name} -n {namespace} 2>/dev/null", "desc": "Pod资源使用", "timeout": 10},
    ],
    "docker_container": [
        {"cmd": "docker stats {container_name} --no-stream",   "desc": "容器资源使用", "timeout": 10},
        {"cmd": "docker logs {container_name} --tail=50",       "desc": "容器日志最近50行", "timeout": 15},
        {"cmd": "docker inspect {container_name} --format='{{.State.Status}} {{.State.OOMKilled}} {{.RestartCount}}'", "desc": "容器状态/重启次数", "timeout": 10},
    ],
    "middleware": [
        {"cmd": "systemctl status {name} 2>/dev/null || ps aux | grep -E '{name}|{port}'", "desc": "中间件进程状态", "timeout": 5},
        {"cmd": "netstat -tlnp 2>/dev/null | grep {port}",      "desc": "中间件端口监听", "timeout": 5},
        {"cmd": "journalctl -u {name} --no-pager -n 30 2>/dev/null || echo 'no journalctl'", "desc": "服务日志(最近30行)", "timeout": 8},
    ],
    "_default": [
        {"cmd": "uptime",     "desc": "系统运行时间与负载", "timeout": 5},
        {"cmd": "df -h",      "desc": "磁盘使用概览", "timeout": 5},
        {"cmd": "free -m",    "desc": "内存使用概览", "timeout": 5},
        {"cmd": "ps aux --sort=-%cpu | head -5", "desc": "CPU TOP5", "timeout": 10},
    ],
}

# 指标名 → 命令包 key 的模糊匹配规则（metric_name 包含关键词即匹配）
_DIAGNOSIS_METRIC_KEYWORDS = {
    "cpu": "cpu_usage",
    "load": "cpu_usage",
    "memory": "memory_usage",
    "mem": "memory_usage",
    "disk": "disk_usage",
    "storage": "disk_usage",
    "pod_crash": "k8s_pod_crash",
    "oom": "k8s_pod_crash",
    "container": "docker_container",
    "docker": "docker_container",
    "svc_up": "middleware",
    "redis": "middleware",
    "memcached": "middleware",
    "mysql": "middleware",
    "kafka": "middleware",
    "rabbitmq": "middleware",
    "nacos": "middleware",
    "etcd": "middleware",
    "zookeeper": "middleware",
    "mongodb": "middleware",
    "postgres": "middleware",
}


def _match_diagnosis_pack(metric_name: str) -> str:
    """根据指标名匹配诊断命令包 key."""
    mn = (metric_name or "").lower()
    for keyword, pack_key in _DIAGNOSIS_METRIC_KEYWORDS.items():
        if keyword in mn:
            return pack_key
    return "_default"


def _fill_template(cmd: str, asset: "Asset | None", channel: str) -> str:
    """替换诊断命令中的占位符（{pod_name}, {namespace}, {container_name}, {port} 等）."""
    if not asset:
        return cmd
    if channel == "k8s":
        meta = _parse_k8s_meta(asset)
        cmd = cmd.replace("{pod_name}", meta.get("name", ""))
        cmd = cmd.replace("{namespace}", meta.get("namespace", "default"))
        cmd = cmd.replace("{cluster}", meta.get("cluster", ""))
    elif channel == "docker":
        container_name = (getattr(asset, "name", "") or "").strip()
        cmd = cmd.replace("{container_name}", container_name)
    # 中间件通用占位符
    try:
        raw_attrs = getattr(asset, "ci_attributes", "{}")
        if isinstance(raw_attrs, str):
            ci_attrs = json.loads(raw_attrs) if raw_attrs else {}
        else:
            ci_attrs = raw_attrs or {}
    except (json.JSONDecodeError, TypeError):
        ci_attrs = {}
    port = ci_attrs.get("mw_port", "")
    if port:
        cmd = cmd.replace("{port}", str(port))
    asset_name = (getattr(asset, "name", "") or "").strip()
    if asset_name:
        cmd = cmd.replace("{name}", asset_name)
    return cmd


def _execute_diagnostic_tool(db: Session, asset, tool_id: str, round_num: int = 0) -> dict:
    """执行单个诊断工具（只读），复用 diagnostic_tools 工具池 + 现有 SSH/K8s/Docker 通道.

    返回 {tool_id, tool_name, cmd, desc, output, exit_code, duration_ms, success, round_num}
    安全闸门：只允许 read_only 且非 custom 的内置工具，命令经 validate_command 校验。
    """
    from app.routers.diagnostic_tools import DIAGNOSTIC_TOOLS, validate_command
    tool = next((t for t in DIAGNOSTIC_TOOLS if t["id"] == tool_id), None)
    if not tool:
        return {"tool_id": tool_id, "tool_name": tool_id, "cmd": "", "desc": "",
                "output": f"工具 {tool_id} 不存在", "exit_code": -1, "duration_ms": 0,
                "success": False, "round_num": round_num}
    if tool.get("risk_level") != "read_only":
        return {"tool_id": tool_id, "tool_name": tool.get("name", tool_id), "cmd": "", "desc": "",
                "output": "只允许执行只读诊断工具", "exit_code": -1, "duration_ms": 0,
                "success": False, "round_num": round_num}
    if tool.get("custom"):
        return {"tool_id": tool_id, "tool_name": tool.get("name", tool_id), "cmd": "", "desc": "",
                "output": "迭代诊断不支持自定义工具", "exit_code": -1, "duration_ms": 0,
                "success": False, "round_num": round_num}

    cmd = tool.get("command") or ""
    if not cmd:
        return {"tool_id": tool_id, "tool_name": tool.get("name", tool_id), "cmd": "", "desc": "",
                "output": "工具无内置命令", "exit_code": -1, "duration_ms": 0,
                "success": False, "round_num": round_num}

    valid, msg = validate_command(cmd)
    if not valid:
        return {"tool_id": tool_id, "tool_name": tool.get("name", tool_id), "cmd": cmd, "desc": "",
                "output": f"命令安全校验失败: {msg}", "exit_code": -1, "duration_ms": 0,
                "success": False, "round_num": round_num}

    channel = _ci_channel(asset) if asset else "ssh"
    timeout = tool.get("timeout", 30)
    host_asset = asset
    if channel == "docker" and asset:
        parent_id = getattr(asset, "parent_id", None)
        if parent_id:
            host_asset = db.query(Asset).filter(Asset.id == parent_id).first() or asset

    t0 = datetime.now()
    success, output = False, "未找到目标资产"
    if asset and channel in ("ssh", "docker"):
        success, output = _remote_exec(host_asset, cmd, timeout=timeout)
    elif asset and channel == "k8s":
        success, output = _remote_exec(asset, cmd, timeout=timeout)
    elif asset:
        success, output = _remote_exec(asset, cmd, timeout=timeout)
    else:
        success, output = False, "未关联资产"

    duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
    return {
        "tool_id": tool_id,
        "tool_name": tool.get("name", tool_id),
        "cmd": cmd,
        "desc": tool.get("description", ""),
        "output": output[:2000] if output else "",
        "exit_code": 0 if success else -1,
        "duration_ms": duration_ms,
        "success": success,
        "round_num": round_num,
    }


def run_diagnosis(db: Session, alert_id: int, asset_id: int = None, metric_name: str = "", force: bool = False) -> dict:
    """执行自动诊断：按告警类型跑只读命令包，存入 diagnosis_reports 表.

    返回 {"ok": True/False, "report_id": int, "commands": [...]}
    - force=True 时忽略已有报告直接重新诊断
    - 命令全部只读，免审批自动执行
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return {"ok": False, "error": "告警不存在"}

    aid = asset_id or alert.asset_id
    mn = metric_name or alert.metric_name or ""
    asset = db.query(Asset).filter(Asset.id == aid).first() if aid else None

    # 去重：同 alert 已有 completed 诊断报告则跳过（force=True 时跳过）
    if not force:
        existing = db.query(DiagnosisReport).filter(
            DiagnosisReport.alert_id == alert_id,
            DiagnosisReport.status == DiagnosisReport.STATUS_COMPLETED,
        ).first()
        if existing:
            return {"ok": True, "report_id": existing.id, "cached": True,
                    "commands": json.loads(existing.commands_run) if existing.commands_run else []}

    # 创建报告记录（状态 running）
    report = DiagnosisReport(
        alert_id=alert_id,
        asset_id=aid,
        metric_name=mn,
        status=DiagnosisReport.STATUS_RUNNING,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 匹配诊断命令包
    pack_key = _match_diagnosis_pack(mn)
    pack = DIAGNOSIS_COMMAND_PACKS.get(pack_key, DIAGNOSIS_COMMAND_PACKS["_default"])

    # 确定执行通道
    channel = _ci_channel(asset) if asset else "ssh"
    host_asset = asset  # SSH 通道直接用资产本身

    # Docker 通道需要找宿主机（容器资产的 parent_id 指向宿主机）
    if channel == "docker" and asset:
        parent_id = getattr(asset, "parent_id", None)
        if parent_id:
            host_asset = db.query(Asset).filter(Asset.id == parent_id).first() or asset

    commands_run = []
    raw_parts = []

    # ── 复用同一 SSH 连接执行所有诊断命令（避免并发连接触发 MaxStartups 限流）──
    _shared_ssh = None
    if asset and channel in ("ssh", "docker") and host_asset:
        try:
            _shared_ssh = _ssh_connect(host_asset, timeout=15)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"诊断命令共享SSH连接失败: {e}")

    for item in pack:
        cmd_template = item["cmd"]
        desc = item.get("desc", "")
        cmd_timeout = item.get("timeout", 15)

        # 填充占位符
        cmd = _fill_template(cmd_template, asset, channel)

        # 执行命令
        t0 = datetime.now()
        success, output = False, "未找到目标资产"
        if asset and channel in ("ssh", "docker"):
            if _shared_ssh:
                # 复用共享连接
                try:
                    stdin, stdout, stderr = _shared_ssh.exec_command(cmd, timeout=cmd_timeout)
                    out = stdout.read().decode(errors="ignore").strip()
                    err = stderr.read().decode(errors="ignore").strip()
                    code = stdout.channel.recv_exit_status()
                    output = "\n".join(s for s in [out, err] if s) or f"exit_code={code}"
                    success = (code == 0)
                except Exception as e:
                    output = f"远程命令执行异常: {e}"
                    success = False
                    # 连接断了，尝试重连一次
                    try:
                        _shared_ssh = _ssh_connect(host_asset, timeout=15)
                        stdin, stdout, stderr = _shared_ssh.exec_command(cmd, timeout=cmd_timeout)
                        out = stdout.read().decode(errors="ignore").strip()
                        err = stderr.read().decode(errors="ignore").strip()
                        code = stdout.channel.recv_exit_status()
                        output = "\n".join(s for s in [out, err] if s) or f"exit_code={code}"
                        success = (code == 0)
                    except Exception:
                        pass
            elif host_asset:
                success, output = _remote_exec(host_asset, cmd, timeout=cmd_timeout)
        elif asset and channel == "k8s":
            success, output = _remote_exec(asset, cmd, timeout=cmd_timeout)
        elif asset:
            success, output = _remote_exec(asset, cmd, timeout=cmd_timeout)

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)

        cmd_result = {
            "cmd": cmd,
            "desc": desc,
            "output": output[:2000] if output else "",
            "duration_ms": duration_ms,
            "exit_code": 0 if success else -1,
        }
        commands_run.append(cmd_result)
        raw_parts.append(f"=== {desc} ===\n$ {cmd}\n{output[:2000]}\n")

    # 关闭共享连接
    if _shared_ssh:
        try:
            _shared_ssh.close()
        except Exception:
            pass

    # 更新报告状态
    report.commands_run = json.dumps(commands_run, ensure_ascii=False)
    report.raw_output = "\n".join(raw_parts)[:8000]
    report.status = DiagnosisReport.STATUS_COMPLETED
    report.finished_at = datetime.now()
    db.commit()

    return {
        "ok": True,
        "report_id": report.id,
        "cached": False,
        "commands": commands_run,
    }


def get_diagnosis_report(db: Session, report_id: int) -> dict:
    """获取诊断报告详情."""
    report = db.query(DiagnosisReport).filter(DiagnosisReport.id == report_id).first()
    if not report:
        return {"ok": False, "error": "诊断报告不存在"}
    return {
        "ok": True,
        "id": report.id,
        "alert_id": report.alert_id,
        "asset_id": report.asset_id,
        "metric_name": report.metric_name or "",
        "commands_run": json.loads(report.commands_run) if report.commands_run else [],
        "raw_output": report.raw_output or "",
        "summary": report.summary or "",
        "status": report.status or "",
        "created_at": report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else "",
        "finished_at": report.finished_at.strftime("%Y-%m-%d %H:%M:%S") if report.finished_at else "",
    }


def _check_dangerous_command(command: str) -> Optional[str]:
    """检测命令是否命中危险黑名单，命中返回原因，None 表示安全."""
    match = _DANGEROUS_CMD_RE.search(command)
    if match:
        return f"命令命中危险黑名单（匹配: {match.group(0)[:60]}），已拦截"
    return None


def _ssh_connect(asset: "Asset", timeout: int = 10) -> "paramiko.SSHClient":
    """通过资产记录的 connection_config 建立 SSH 连接.

    复用 metric_collector._ssh_connect 的连接逻辑，集中在此处避免循环依赖。
    connection_config JSON 结构: {"ssh_user":"root","ssh_password":"xxx","ssh_port":22}
    若资产自身无 SSH 凭证，自动查找同 IP 的 server 资产继承凭证。
    """
    config: dict = {}
    try:
        raw = getattr(asset, "connection_config", "{}") or "{}"
        if isinstance(raw, str) and raw:
            config = json.loads(raw)
        elif isinstance(raw, dict):
            config = raw
    except (json.JSONDecodeError, TypeError):
        config = {}

    host = getattr(asset, "ip", "") or ""
    if not host:
        raise ValueError(f"资产 {asset.name}(id={asset.id}) 无 IP 地址")

    port = config.get("ssh_port", 22)
    username = config.get("ssh_user", "root")
    password = config.get("ssh_password", "")

    # 如果资产自身无 SSH 凭证（如 database/middleware 只有 db_* 字段），找同 IP 的 server 资产继承
    if not config.get("ssh_user") and not config.get("ssh_password"):
        try:
            from app.database import get_session_for, get_db_mode
            from app.models import Asset as AssetModel
            _db = get_session_for(get_db_mode())()
            server = _db.query(AssetModel).filter(
                AssetModel.ip == host,
                AssetModel.connection_type == "ssh",
                AssetModel.id != asset.id
            ).first()
            if server:
                try:
                    raw2 = getattr(server, "connection_config", "{}") or "{}"
                    if isinstance(raw2, str) and raw2:
                        srv_cfg = json.loads(raw2)
                    else:
                        srv_cfg = raw2 or {}
                    port = srv_cfg.get("ssh_port", port)
                    username = srv_cfg.get("ssh_user", username)
                    password = srv_cfg.get("ssh_password", password)
                except Exception:
                    pass
            _db.close()
        except Exception:
            pass

    from app.services.ssh_helper import get_ssh_client
    ssh = get_ssh_client()
    ssh.connect(host, port=port, username=username, password=password,
                timeout=timeout, banner_timeout=timeout)
    return ssh


def _remote_exec(asset: Asset, command: str, timeout: int = 30, retries: int = 2) -> tuple:
    """在远程资产上执行单条命令，返回 (success, output).

    success 由 returncode==0 判定；output 合并 stdout+stderr 便于排错。
    SSH 连接失败、命令超时均返回 (False, 错误描述)，不抛异常给上层，
    由调用方决定如何包装返回（raise 或 return）。
    retries: SSH banner 失败时的重试次数（默认 2 次，应对 MaxStartups 限流）。
    """
    last_error = ""
    for attempt in range(retries + 1):
        try:
            ssh = _ssh_connect(asset, timeout=timeout)
        except Exception as e:
            last_error = str(e)
            if attempt < retries and "banner" in last_error.lower():
                import time
                time.sleep(1 + attempt)
                continue
            return (False, f"SSH 连接失败: {e}")
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            out = stdout.read().decode(errors="ignore").strip()
            err = stderr.read().decode(errors="ignore").strip()
            code = stdout.channel.recv_exit_status()
            output = "\n".join(s for s in [out, err] if s)
            return (code == 0, output or f"exit_code={code}")
        except Exception as e:
            last_error = str(e)
            if attempt < retries and "banner" in last_error.lower():
                import time
                time.sleep(1 + attempt)
                continue
            return (False, f"远程命令执行异常: {e}")
        finally:
            ssh.close()
    return (False, f"SSH 连接失败(重试{retries}次): {last_error}")


# 动作类型别名映射：兼容种子数据生成的非标准名
_ACTION_ALIASES = {
    "restart_service": "restart",
    "restart_pod": "restart",
    "clean_disk": "clean",
    "scale_up": "scale",
    "scale_down": "scale",
    "execute_command": "run_command",
    "run_script": "script",
    "notify_owner": "notify",
}

# ── 资产类型 → 执行通道分派（CI-Type-Aware Dispatch）──
# 传统主机/中间件/数据库：走 SSH + systemctl（有 SSH 入口 + systemd）
_SSH_CI_TYPES = {
    "server", "virtual_machine", "vm", "cloud_host",
    "database", "middleware",
    "network_device", "switch", "router", "firewall", "load_balancer", "loadbalancer",
    "storage_device", "storage",
}
# K8s 资源：走 K8s API（无 SSH 入口，无 systemd）
_K8S_CI_TYPES = {
    "kubernetes_cluster", "node",
    "deployment", "statefulset", "daemonset", "pod", "job", "cronjob",
    "service", "ingress", "configmap", "secret", "pvc", "pv", "hpa", "replicaset",
    "namespace",
}
# Docker 容器：走 Docker CLI（通过宿主机 SSH 执行 docker 命令）
_DOCKER_CI_TYPES = {"container"}


def _ci_channel(asset: "Asset") -> str:
    """根据资产 ci_type 判定执行通道：ssh / k8s / docker / unknown."""
    ci = (getattr(asset, "ci_type", "") or "").strip().lower()
    if ci in _K8S_CI_TYPES:
        return "k8s"
    if ci in _DOCKER_CI_TYPES:
        return "docker"
    if ci in _SSH_CI_TYPES:
        return "ssh"
    return "unknown"


def _parse_k8s_meta(asset: "Asset") -> dict:
    """从资产解析 K8s 元数据：cluster / namespace / name.

    优先读 ci_attributes JSON；回退用 name 里的 namespace/name 前缀；最后用 asset.k8s_cluster。
    """
    meta = {"cluster": "", "namespace": "default", "name": ""}
    # ci_attributes JSON
    try:
        raw = getattr(asset, "ci_attributes", "") or ""
        attrs = json.loads(raw) if isinstance(raw, str) and raw else (raw if isinstance(raw, dict) else {})
        if isinstance(attrs, dict):
            meta["cluster"] = attrs.get("k8s_cluster") or attrs.get("cluster") or ""
            meta["namespace"] = attrs.get("namespace") or "default"
    except Exception:
        pass
    # k8s_cluster 列兜底
    if not meta["cluster"]:
        meta["cluster"] = getattr(asset, "k8s_cluster", "") or ""
    # name 可能是 "namespace/name" 格式
    name = getattr(asset, "name", "") or ""
    if "/" in name:
        parts = name.split("/", 1)
        meta["namespace"] = parts[0] or meta["namespace"]
        meta["name"] = parts[1]
    else:
        meta["name"] = name
    return meta


def _get_k8s_client_for_asset(db: Session, asset: "Asset"):
    """根据资产的 cluster 名反查 DataSource(type=kubernetes) 建立 K8s client.

    返回 (CoreV1Api, AppsV1Api) 或 (None, None)（找不到数据源时）。
    复用 k8s_resources._get_k8s_client 的连接逻辑。
    """
    meta = _parse_k8s_meta(asset)
    cluster_name = meta["cluster"]
    ds = None
    if cluster_name:
        ds = db.query(DataSource).filter(
            DataSource.type == "kubernetes", DataSource.name == cluster_name
        ).first()
    if not ds:
        # 回退：取任意启用的 kubernetes 数据源
        ds = db.query(DataSource).filter(
            DataSource.type == "kubernetes", DataSource.enabled == True
        ).first()
    if not ds:
        return None, None, "未找到 K8s 数据源（cluster=" + cluster_name + "）"
    try:
        from app.routers.k8s_resources import _get_k8s_client
        core_v1, apps_v1, _ = _get_k8s_client(ds)
        return core_v1, apps_v1, None
    except Exception as e:
        return None, None, f"K8s 连接失败: {e}"


def _k8s_exec_restart(db: Session, asset: "Asset", params: dict) -> tuple:
    """K8s 资源重启：deployment→rollout restart，pod→delete pod，其他→拒绝."""
    meta = _parse_k8s_meta(asset)
    ci = (getattr(asset, "ci_type", "") or "").lower()
    core_v1, apps_v1, err = _get_k8s_client_for_asset(db, asset)
    if err or not apps_v1:
        return (False, err or "K8s AppsV1Api 初始化失败")
    try:
        if ci in ("deployment", "statefulset", "daemonset"):
            # rollout restart：patch annotation 触发滚动重启
            from datetime import datetime as _dt
            apps_v1.patch_namespaced_deployment(
                name=meta["name"], namespace=meta["namespace"],
                body={"spec": {"template": {"metadata": {"annotations": {
                    "kubectl.kubernetes.io/restartedAt": _dt.now().isoformat()}}}}},
            )
            return (True, f"K8s {ci} {meta['namespace']}/{meta['name']} rollout restart 已触发")
        elif ci == "pod":
            if not core_v1:
                return (False, "K8s CoreV1Api 初始化失败")
            core_v1.delete_namespaced_pod(name=meta["name"], namespace=meta["namespace"])
            return (True, f"K8s pod {meta['namespace']}/{meta['name']} 已删除（将由控制器重建）")
        else:
            return (False, f"K8s 资源类型 {ci} 不支持 restart 动作")
    except Exception as e:
        return (False, f"K8s restart 失败: {e}")


def _k8s_exec_scale(db: Session, asset: "Asset", params: dict) -> tuple:
    """K8s 扩缩容：deployment/statefulset → patch scale."""
    meta = _parse_k8s_meta(asset)
    ci = (getattr(asset, "ci_type", "") or "").lower()
    core_v1, apps_v1, err = _get_k8s_client_for_asset(db, asset)
    if err or not apps_v1:
        return (False, err or "K8s AppsV1Api 初始化失败")
    if ci not in ("deployment", "statefulset"):
        return (False, f"K8s 资源类型 {ci} 不支持 scale 动作（仅 deployment/statefulset）")
    replicas = params.get("replicas") or params.get("count") or 2
    try:
        replicas = int(replicas)
    except (TypeError, ValueError):
        return (False, f"非法 replicas 值: {replicas}")
    try:
        apps_v1.patch_namespaced_deployment_scale(
            name=meta["name"], namespace=meta["namespace"],
            body={"spec": {"replicas": replicas}},
        )
        return (True, f"K8s {ci} {meta['namespace']}/{meta['name']} 已扩缩容至 {replicas} 副本")
    except Exception as e:
        return (False, f"K8s scale 失败: {e}")


def _docker_exec_restart(db: Session, asset: "Asset", params: dict) -> tuple:
    """Docker 容器重启：通过宿主机 SSH 执行 docker restart.

    宿主机来源：asset.parent_id 指向的父资产（server/vm）；无父资产则拒绝。
    """
    parent_id = getattr(asset, "parent_id", None)
    if not parent_id:
        return (False, "Docker 容器未关联宿主机（parent_id 为空），无法通过 SSH 执行 docker restart")
    from app.models import Asset as _Asset
    host_asset = db.query(_Asset).filter(_Asset.id == parent_id).first()
    if not host_asset:
        return (False, f"宿主机资产 #{parent_id} 不存在")
    container_name = params.get("container") or params.get("name") or getattr(asset, "name", "")
    if not container_name:
        return (False, "缺少容器名参数")
    # 容器名防注入：只允许字母数字下划线-点
    if not all(c.isalnum() or c in "-_." for c in container_name):
        return (False, f"非法容器名: {container_name}")
    command = f"docker restart {container_name}"
    success, output = _remote_exec(host_asset, command, timeout=60)
    if success:
        return (True, f"Docker 容器 {container_name} 在宿主机 {host_asset.ip} 重启成功")
    return (False, f"Docker 容器 {container_name} 重启失败: {output}")


def _k8s_exec_command(command: str, core_v1, asset: "Asset", extra_hint: str = "") -> tuple:
    """通过 K8s API 在 pod 内执行命令（只读诊断或脚本）.

    先尝试 kubectl exec（SSH 到集群节点），回退到 K8s API exec 通道。
    core_v1 可传 None（自动尝试 kubectl 路径）。
    """
    meta = _parse_k8s_meta(asset)
    pod_name = meta.get("name", "")
    namespace = meta.get("namespace", "default")
    if not pod_name:
        return (False, "K8s 资产缺少 pod 名称")
    try:
        # 优先走 kubectl exec（如果集群节点有 kubelet 和 kubectl）
        # 回退到 K8s API exec
        if core_v1:
            import subprocess as _sp
            _cmd = f"kubectl exec {pod_name} -n {namespace} -- {command}"
            _r = _sp.run(_cmd, shell=True, capture_output=True, text=True, timeout=30)
            if _r.returncode == 0:
                return (True, f"{extra_hint} 执行完成: {_r.stdout[:500]}")
            return (False, f"{extra_hint} 执行失败: {_r.stderr[:300]}")
    except Exception as e:
        pass
    return (False, f"{extra_hint} 执行失败（无法在 K8s pod 内执行命令: {command[:80]}")


def _docker_exec_command(asset: "Asset", db: "Session", command: str, action_label: str) -> tuple:
    """通过宿主机 SSH 在 Docker 容器内执行命令."""
    parent_id = getattr(asset, "parent_id", None)
    if not parent_id:
        return (False, "Docker 容器未关联宿主机（parent_id 为空），无法通过 SSH 执行 docker exec")
    from app.models import Asset as _Asset
    host_asset = db.query(_Asset).filter(_Asset.id == parent_id).first()
    if not host_asset:
        return (False, f"宿主机资产 #{parent_id} 不存在")
    container_name = getattr(asset, "name", "") or ""
    if not container_name:
        return (False, "Docker 容器缺少 name")
    cmd = f"docker exec {container_name} {command}"
    success, output = _remote_exec(host_asset, cmd, timeout=30)
    if success:
        return (True, f"Docker 容器 {container_name} {action_label} 完成: {output[:500]}")
    return (False, f"Docker 容器 {container_name} {action_label} 失败: {output[:500]}")


def _get_correlation_cached(db: Session, asset_id: int, hours: int = 1) -> dict:
    """获取关联分析结果，带短时缓存（同一 asset_id 60 秒内复用）."""
    import time
    now = time.time()
    key = f"{asset_id}_{hours}"
    cached = _CORRELATION_CACHE.get(key)
    if cached and now - cached["ts"] < _CORRELATION_CACHE_TTL:
        return cached["data"]
    from app.routers.observability_correlation import run_correlation_analysis
    data = run_correlation_analysis(db, hours=hours, service="", asset_id=asset_id)
    _CORRELATION_CACHE[key] = {"ts": now, "data": data}
    return data



def execute_action(action_type: str, params: dict, asset: Asset, db: "Session | None" = None) -> tuple:
    """在资产上执行修复动作 — 按 ci_type 分派执行通道（CI-Type-Aware Dispatch）.

    通道分派：
    - ssh（传统主机/中间件/数据库）: SSH + systemctl / find / bash
    - k8s（deployment/pod/...）: K8s API（rollout restart / delete pod / patch scale）
    - docker（container）: 通过宿主机 SSH 执行 docker restart
    - unknown: 拒绝执行

    params 含业务参数（service/path/script 等）；asset 提供连接信息。
    db 仅 K8s/Docker 通道需要（用于反查 DataSource/父资产），SSH 通道可省略。
    返回 (success, message)。
    """
    # 别名自动转换
    action_type = _ACTION_ALIASES.get(action_type, action_type)
    channel = _ci_channel(asset)

    # notify 通道无关，所有类型通用
    if action_type == "notify":
        return (True, f"通知已发送: {getattr(asset, 'ip', '') or getattr(asset, 'name', '')}")

    # healthcheck 动作：三通道全量支持，只读自动执行
    if action_type == "healthcheck":
        if channel == "k8s":
            meta = _parse_k8s_meta(asset)
            ci = (getattr(asset, "ci_type", "") or "").lower()
            if ci in ("deployment", "statefulset", "daemonset"):
                cmd = f"kubectl rollout status {ci} {meta['name']} -n {meta['namespace']} --timeout=10s"
            elif ci == "pod":
                cmd = f"kubectl get pod {meta['name']} -n {meta['namespace']} -o jsonpath='{{.status.phase}}'"
            else:
                cmd = f"kubectl get pod {meta['name']} -n {meta['namespace']} -o jsonpath='{{.status.phase}}'"
            return _k8s_exec_command(cmd, core_v1=None, asset=asset, extra_hint="K8s 健康检查")
        if channel == "docker":
            return _docker_exec_command(asset, db, "sh -c 'echo ok || exit 1'", "Docker 健康检查")
        if channel == "ssh":
            service = params.get("service") or params.get("target", "")
            if service:
                cmd = f"systemctl is-active {service}"
                success, output = _remote_exec(asset, cmd, timeout=15)
                if success:
                    return (True, f"服务 {service} 在 {asset.ip} 运行正常")
                return (False, f"服务 {service} 在 {asset.ip} 状态异常: {output[:200]}")
            cmd = "uptime"
            success, output = _remote_exec(asset, cmd, timeout=10)
            if success:
                return (True, f"主机 {asset.ip} 运行正常: {output[:200]}")
            return (False, f"主机 {asset.ip} 无响应")
        return (False, f"healthcheck 不支持 ci_type={getattr(asset, 'ci_type', '?')}")

    # ── restart 动作：按通道分派 ──
    if action_type == "restart":
        if channel == "k8s":
            if db is None:
                return (False, "K8s restart 需要 db 参数（用于反查数据源）")
            return _k8s_exec_restart(db, asset, params)
        if channel == "docker":
            if db is None:
                return (False, "Docker restart 需要 db 参数（用于查宿主机）")
            return _docker_exec_restart(db, asset, params)
        if channel == "ssh":
            # 服务器/云主机不支持 restart（没有 systemd 服务名，SSH 不通是网络/主机问题）
            server_types = {"server", "virtual_machine", "vm", "cloud_host"}
            if getattr(asset, "ci_type", "") in server_types:
                return (False, f"服务器类型资产({asset.ci_type})不支持 restart 操作，请手动检查 SSH 连通性和主机状态")
            service_name = params.get("service") or params.get("target", "")
            if not service_name:
                return (False, "缺少参数: service")
            # 根据 ci_attributes 中的子类型纠正服务名（AI 可能用资产名代替实际服务名）
            try:
                raw_attrs = getattr(asset, "ci_attributes", "{}")
                if isinstance(raw_attrs, str):
                    ci_attrs = json.loads(raw_attrs) if raw_attrs else {}
                else:
                    ci_attrs = raw_attrs or {}
            except Exception:
                ci_attrs = {}
            subtype = ci_attrs.get("mw_subtype", "") or ci_attrs.get("db_type", "")
            if subtype:
                known_services = {
                    "redis": ["redis", "redis-server"],
                    "memcached": ["memcached"],
                    "mysql": ["mysqld", "mysql"],
                    "postgresql": ["postgresql", "postgresql-14", "postgresql-15"],
                    "mongodb": ["mongod", "mongodb"],
                    "nginx": ["nginx"],
                    "rabbitmq": ["rabbitmq-server"],
                    "nacos": ["nacos"],
                    "kafka": ["kafka"],
                    "zookeeper": ["zookeeper"],
                    "etcd": ["etcd"],
                    "minio": ["minio"],
                }
                if subtype in known_services:
                    expected = known_services[subtype]
                    if service_name not in expected:
                        old_service = service_name
                        service_name = expected[0]
                        params["service"] = service_name
            if not all(c.isalnum() or c in "-_." for c in service_name):
                return (False, f"非法服务名: {service_name}")
            command = f"sudo systemctl restart {service_name}"
            success, output = _remote_exec(asset, command, timeout=30)
            if not success:
                return (False, f"服务 {service_name} 在 {asset.ip} 重启失败: {output}")
            # 执行后健康检查：验证服务是否真正启动
            import time
            time.sleep(2)
            check_cmd = f"systemctl is-active {service_name}"
            check_ok, check_out = _remote_exec(asset, check_cmd, timeout=10)
            if check_ok and "active" in check_out.lower():
                return (True, f"服务 {service_name} 在 {asset.ip} 重启成功（验证: {check_out}）")
            return (False, f"服务 {service_name} 重启命令已执行但验证失败: {check_out}")
        return (False, f"资产 ci_type={getattr(asset, 'ci_type', '?')} 不在已知执行通道，拒绝 restart")

    # ── scale 动作：仅 K8s 通道有效 ──
    if action_type == "scale":
        if channel == "k8s":
            if db is None:
                return (False, "K8s scale 需要 db 参数")
            return _k8s_exec_scale(db, asset, params)
        return (False, f"scale 动作仅支持 K8s 资源（deployment/statefulset），当前 ci_type={getattr(asset, 'ci_type', '?')} 不支持")

    # ── clean 动作：仅 SSH 通道有效（K8s/Docker 无文件系统语义）──
    if action_type == "clean":
        if channel != "ssh":
            return (False, f"clean 动作仅支持有文件系统的主机（SSH 通道），当前 ci_type={getattr(asset, 'ci_type', '?')} 不支持")
        clean_path = params.get("path") or params.get("target", "/tmp")
        ALLOWED_CLEAN_PREFIXES = ("/tmp", "/var/log", "/var/cache", "/opt", "/home")
        clean_path = clean_path.rstrip("/")
        if clean_path == "/":
            return (False, "禁止清理根目录 /")
        if not clean_path.startswith(ALLOWED_CLEAN_PREFIXES):
            return (False, f"非法清理路径: {clean_path}，仅允许 /tmp /var/log /var/cache /opt /home 下路径")
        command = f"find {clean_path} -type f -mtime +7 -delete 2>/dev/null"
        success, output = _remote_exec(asset, command, timeout=60)
        if success:
            return (True, f"清理 {asset.ip}:{clean_path} 完成")
        return (False, f"清理 {asset.ip}:{clean_path} 失败: {output}")

    # ── script 动作：SSH 通道直接执行；K8s 通过 kubectl exec；Docker 通过 docker exec ──
    if action_type == "script":
        script_path = params.get("script") or params.get("target", "")
        if not script_path:
            return (False, "未指定脚本路径")
        # 脚本路径防注入：只允许字母数字下划线-点/斜杠
        if not all(c.isalnum() or c in "-_./" for c in script_path):
            return (False, f"非法脚本路径: {script_path}")
        if channel == "k8s":
            meta = _parse_k8s_meta(asset)
            command = f"kubectl exec {meta['name']} -n {meta['namespace']} -- bash {script_path}"
            return _k8s_exec_command(command, core_v1=None, asset=asset, extra_hint="K8s pod 内")
        if channel == "docker":
            container_name = getattr(asset, "name", "") or ""
            if not container_name:
                return (False, "Docker 容器缺少 name")
            return _docker_exec_command(asset, db, f"bash {script_path}", "执行脚本")
        if channel == "ssh":
            command = f"bash {script_path}"
            success, output = _remote_exec(asset, command, timeout=30)
            if success:
                return (True, f"脚本 {script_path} 在 {asset.ip} 执行完成: {output[:500]}")
            return (False, f"脚本 {script_path} 在 {asset.ip} 执行失败: {output[:500]}")
        return (False, f"script 动作不支持 ci_type={getattr(asset, 'ci_type', '?')}，仅支持 SSH/K8s/Docker")

    # ── run_command 动作：SSH 全量支持；K8s/Docker 仅放行只读命令 ──
    if action_type == "run_command":
        command = params.get("command") or params.get("target", "")
        if not command:
            return (False, "缺少参数: command")
        # 命令长度限制：防超长命令攻击（正常诊断命令不超过 1000 字符）
        if len(command) > 1000:
            return (False, f"命令过长（{len(command)} 字符，上限 1000）")
        # 危险命令黑名单拦截
        danger = _check_dangerous_command(command)
        if danger:
            return (False, danger)
        # K8s/Docker 通道：仅放行确定性分类器判定为只读(auto_exec=True)的命令
        if channel != "ssh":
            _cls_risk, _cls_auto = _classify_command_risk("run_command", command)
            if not _cls_auto:
                return (False, f"run_command 在 {channel} 通道仅支持只读命令，"
                        f"当前命令被判定为 {_cls_risk}（需审批变更），"
                        f"请用 restart/scale 专门动作或 SSH 通道资产")
        success, output = _remote_exec(asset, command, timeout=30)
        if success:
            return (True, f"命令在 {asset.ip} 执行完成: {output[:500]}")
        return (False, f"命令在 {asset.ip} 执行失败: {output[:500]}")

    return (False, f"未知操作类型: {action_type}")


def check_and_remediate(db: Session):
    """后台轮询：对触发中的告警生成待审批自愈动作（不直接执行）.

    改造点（fail-safe 审批闸门）：
    - 路径1（规则）：每条告警只匹配1条最优规则 → 生成1条 PendingAction(source=rule)
    - 路径2（AI）：对触发告警自动调 LLM 分析 → 生成1条 PendingAction(source=ai)
    - 每条告警最多产出 2 条方案（1规则 + 1AI），审批时人工择优执行，另一方案保留待手动取消
    - 去重：同 alert 当天已有对应来源的 PendingAction 则跳过
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    alerts = db.query(Alert).filter(Alert.status == "triggered").order_by(
        Alert.created_at.desc()
    ).limit(20).all()

    # ── 路径1：每条告警只匹配1条最优规则 → 生成1条 PendingAction(source=rule) ──
    for alert in alerts:
        # 去重：同 alert 当天已有 source=rule 的 PendingAction 则跳过
        has_rule_pa = False
        for pa in db.query(PendingAction).filter(
            PendingAction.alert_id == alert.id,
            PendingAction.created_at >= today_start,
        ).all():
            try:
                pl = json.loads(pa.action_payload) if pa.action_payload else {}
                if pl.get("source") == "rule":
                    has_rule_pa = True
                    break
            except Exception:
                pass
        if has_rule_pa:
            continue

        # 只取 rule_id 精确匹配的规则（不再用 rule_id=None 的通配规则匹配所有告警）
        rem = None
        if alert.rule_id:
            rem = db.query(AutoRemediation).filter(
                AutoRemediation.rule_id == alert.rule_id,
                AutoRemediation.enabled == True,
            ).first()
        if not rem:
            # 没有匹配的单动作规则 → 交给 AI 分析路径（path 2）处理
            # AI 会看到启用的工作流并动态填充 step_params，实现真正的 AI 自愈
            continue

        params = json.loads(rem.remediation_params) if rem.remediation_params else {}
        target = params.get("target", f"asset_{alert.asset_id}")
        action_label = ACTIONS.get(rem.action_type, {}).get("label", rem.action_type)
        title = f"规则自愈: {action_label} {target}"[:60]
        reason = f"规则#{rem.id}({rem.name}) 匹配告警#{alert.id}，建议执行 {action_label}"
        # 查关联资产，用于按 ci_type 生成对应通道的展示命令
        rule_asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
        payload = {
            "source": "rule",
            "remediation_id": rem.id,
            "remediation_name": rem.name or "",
            "action_type": rem.action_type,
            "params": params,
            "command": _build_rule_command(rem.action_type, params, rule_asset),
        }
        pa = PendingAction(
            alert_id=alert.id,
            title=title,
            action_type=rem.action_type,
            risk_level=_rule_risk_level(rem.action_type),
            reason=reason,
            status=PendingAction.STATUS_PENDING,
            action_payload=json.dumps(payload, ensure_ascii=False),
        )
        db.add(pa)
    db.commit()

    # ── 路径2：先跑自动诊断 → 再调 AI 分析（带诊断证据）──
    for alert in alerts:
        # 去重：同 alert 当天已有 AI 来源的 PendingAction 则跳过诊断
        exist_ai = False
        for pa in db.query(PendingAction).filter(
            PendingAction.alert_id == alert.id,
            PendingAction.created_at >= today_start,
        ).all():
            try:
                pl = json.loads(pa.action_payload) if pa.action_payload else {}
                if pl.get("source") == "ai":
                    exist_ai = True
                    break
            except Exception:
                pass
        if exist_ai:
            continue
        # 自动跑诊断命令（只读，免审批）
        try:
            run_diagnosis(db, alert.id, alert.asset_id, alert.metric_name or "")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"自动诊断失败 alert#{alert.id}: {e}")

    try:
        auto_ai_analyze_alerts(db, limit=1)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"auto_ai_analyze_alerts 失败: {e}")

    return []


def _build_rule_command(action_type: str, params: dict, asset: "Asset | None" = None) -> str:
    """根据动作类型 + 资产类型构造可读命令字符串（用于审批展示，与执行层一致）.

    展示-执行一致性（Display-Execution Parity）：展示的命令必须与 execute_action 实际执行的命令通道一致。
    - SSH 通道（server/vm/...）: systemctl restart / find / bash
    - K8s 通道（deployment/pod/...）: kubectl rollout restart / kubectl delete pod / kubectl scale
    - Docker 通道（container）: docker restart
    无 asset 时回退按 action_type 推断（向后兼容）。
    """
    channel = _ci_channel(asset) if asset else "ssh"
    ci = (getattr(asset, "ci_type", "") or "").lower() if asset else ""
    # K8s 元数据（仅 k8s 通道用）
    meta = _parse_k8s_meta(asset) if asset and channel == "k8s" else {}

    if action_type in ("restart", "restart_service"):
        if channel == "k8s":
            if ci in ("deployment", "statefulset", "daemonset"):
                ns, nm = meta.get("namespace", "default"), meta.get("name", "")
                if not nm:
                    return f"kubectl rollout restart deployment ⚠缺deployment名 -n {ns}"
                return f"kubectl rollout restart deployment {nm} -n {ns}"
            if ci == "pod":
                ns, nm = meta.get("namespace", "default"), meta.get("name", "")
                if not nm:
                    return f"kubectl delete pod ⚠缺pod名 -n {ns}"
                return f"kubectl delete pod {nm} -n {ns}"
            return f"K8s {ci} restart ⚠该资源类型不支持restart"
        if channel == "docker":
            cn = params.get("container") or params.get("name") or (getattr(asset, "name", "") if asset else "")
            if not cn:
                return "docker restart ⚠缺容器名"
            return f"docker restart {cn}"
        # ssh 通道
        svc = params.get("service") or params.get("target", "")
        if not svc:
            return "systemctl restart ⚠缺service名"
        return f"systemctl restart {svc}".strip()
    if action_type == "restart_pod":
        # 显式 restart_pod 动作：强制 K8s 语义
        ns = params.get("namespace") or meta.get("namespace", "default")
        label = params.get("label", "")
        nm = params.get("name") or meta.get("name", "")
        if nm:
            return f"kubectl delete pod {nm} -n {ns}"
        if not label:
            return f"kubectl delete pod -n {ns} ⚠缺label或pod名"
        return f"kubectl delete pod -n {ns} -l {label} --ignore-not-found".strip()
    if action_type in ("clean", "clean_disk"):
        if channel != "ssh":
            return f"clean ⚠仅支持SSH通道主机，当前ci_type={ci or '?'}"
        path = params.get("path") or params.get("target", "/tmp")
        return f"find {path} -type f -mtime +7 -delete"
    if action_type == "script":
        if channel != "ssh":
            return f"script ⚠仅支持SSH通道主机，当前ci_type={ci or '?'}"
        sc = params.get("script") or params.get("target", "")
        if not sc:
            return "bash ⚠缺脚本路径"
        return f"bash {sc}".strip()
    if action_type == "run_command":
        if channel != "ssh":
            return f"run_command ⚠仅支持SSH通道主机，当前ci_type={ci or '?'}"
        return params.get("command") or params.get("target", "") or "⚠缺命令"
    if action_type in ("scale", "scale_up"):
        if channel != "k8s":
            return f"scale ⚠仅支持K8s资源，当前ci_type={ci or '?'}"
        ns = meta.get("namespace", "default")
        dep = params.get("deployment") or params.get("target", "") or meta.get("name", "")
        replicas = params.get("replicas") or params.get("count", 2)
        if not dep:
            return f"kubectl scale deployment ⚠缺deployment名 --replicas={replicas} -n {ns}"
        return f"kubectl scale deployment {dep} --replicas={replicas} -n {ns}".strip()
    if action_type in ("notify", "notify_owner"):
        ch = params.get("channel", "email")
        tpl = params.get("template") or params.get("target", "alert")
        return f"notify via {ch}: {tpl}"
    return action_type


def _rule_risk_level(action_type: str) -> str:
    """规则动作默认风险等级（供审批参考）."""
    if action_type in ("restart", "scale"):
        return PendingAction.RISK_MEDIUM
    if action_type in ("clean", "script", "run_command"):
        return PendingAction.RISK_HIGH
    if action_type == "notify":
        return PendingAction.RISK_LOW
    return PendingAction.RISK_MEDIUM


def auto_ai_analyze_alerts(db: Session, limit: int = 1):
    """对触发中的告警自动调 AI 分析，生成 PendingAction(source=ai).

    限流：每轮最多分析 limit 条（默认 1，防 LLM token 爆炸 + 防后台任务超时）。
    去重：同 alert 当天已有 source=ai 的 PendingAction 则跳过。
    无可用 AI Provider 时静默跳过（不阻塞规则路径）。
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    alerts = db.query(Alert).filter(Alert.status == "triggered").order_by(
        Alert.created_at.desc()
    ).limit(20).all()

    analyzed = 0
    for alert in alerts:
        if analyzed >= limit:
            break
        # 去重：同 alert 当天已有 AI 来源的 PendingAction
        exist_ai = False
        for pa in db.query(PendingAction).filter(
            PendingAction.alert_id == alert.id,
            PendingAction.created_at >= today_start,
        ).all():
            try:
                pl = json.loads(pa.action_payload) if pa.action_payload else {}
                if pl.get("source") == "ai":
                    exist_ai = True
                    break
            except Exception:
                pass
        if exist_ai:
            continue
        # 调 AI 分析（内部已生成 PendingAction，source=ai）
        try:
            result = ai_self_heal_analyze(db, alert.id)
            if result.get("ok"):
                analyzed += 1
        except Exception:
            pass


def get_triggered_alerts(db: Session, limit: int = 30):
    """获取触发中的告警列表（供 AI 自愈工作台使用）."""
    alerts = (
        db.query(Alert, Asset.name, Asset.ip)
        .outerjoin(Asset, Alert.asset_id == Asset.id)
        .filter(Alert.status == "triggered")
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for a, aname, aip in alerts:
        asset_name = f"{aname}({aip or ''})" if aname else ""
        result.append({
            "id": a.id,
            "rule_id": a.rule_id,
            "asset_id": a.asset_id,
            "asset_name": asset_name,
            "metric_name": a.metric_name or "",
            "severity": a.severity or "info",
            "message": a.message or "",
            "actual_value": a.actual_value,
            "threshold": a.threshold,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
            "status": a.status or "",
        })
    return result


# AI 自愈分析返回 JSON 的已知字段（按 system_prompt 定义）
_AI_HEAL_JSON_FIELDS = [
    "root_cause", "impact", "diagnosis_reasoning", "risk_level",
    "recommended_workflow_id", "action_type", "command",
    "command_description", "command_explanation", "step_params",
]


def _parse_lenient_ai_json(content: str) -> dict:
    """容错解析 AI 返回的 JSON：字符串值内可能含未转义双引号（如 "SSH 连接失败"）.

    策略：标准 json.loads 失败时，按已知字段名定位，用下一个字段名/闭合括号作为值边界截取。
    """
    # 先尝试标准解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(content, strict=False)
    except json.JSONDecodeError:
        pass
    # lenient：按字段名定位提取
    import re
    result = {}
    # 找所有字段名的位置："field_name"
    field_positions = []
    for f in _AI_HEAL_JSON_FIELDS:
        m = re.search(r'"' + re.escape(f) + r'"\s*:\s*', content)
        if m:
            field_positions.append((m.end(), f))
    if not field_positions:
        return {}
    field_positions.sort()
    for i, (pos, fname) in enumerate(field_positions):
        # 值的结束位置：下一个字段开始，或最后一个 }
        if i + 1 < len(field_positions):
            end = field_positions[i + 1][0]
            # 回退到上一个逗号/换行（去掉字段间的 ",\n  "nextfield）
            # 从 pos 到 end 之间，找最后一个未被引号包裹的逗号
            segment = content[pos:end]
            # 去掉尾部 `,` 和空白和下一个字段名前缀
            segment = re.sub(r',\s*"[^"]*"\s*:\s*$', '', segment).rstrip()
        else:
            # 最后一个字段：到 } 结束
            brace = content.rfind("}")
            segment = content[pos:brace if brace > pos else len(content)]
        # 去掉首尾引号和空白
        segment = segment.strip()
        if segment.startswith('"'):
            segment = segment[1:]
        if segment.endswith('"'):
            segment = segment[:-1]
        # 反转义常见转义
        segment = segment.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
        # 尝试转数字/bool/null/JSON
        if fname in ("recommended_workflow_id",):
            try:
                result[fname] = int(segment) if segment not in ("null", "") else None
            except (ValueError, TypeError):
                result[fname] = None if segment in ("null", "") else segment
        elif fname == "step_params":
            try:
                result[fname] = json.loads(segment) if segment else {}
            except Exception:
                result[fname] = {}
        else:
            result[fname] = segment
    return result


def ai_self_heal_analyze(db: Session, alert_id: int) -> dict:
    """AI 自愈分析：分析告警根因 + 生成修复建议 + 创建待审批动作.

    改造点：AI 分析时同时评估是否匹配已有自愈工作流（Playbook），
    - 匹配则推荐执行该工作流（多步骤全自动），action_type='workflow'
    - 不匹配则走单步动作（run_command/restart/clean/notify）
    形成「已知场景走 Playbook，未知场景走 AI 单步」的分级自愈策略。
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return {"ok": False, "error": "告警不存在"}

    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return {"ok": False, "error": "未配置启用的 AI Provider"}

    # ── 去重：同 metric_name + asset_id + 当天已有 pending 的 AI 方案则复用 ──
    # 同一告警分组（相同指标+资产）根因相同，整组只需一个 AI 方案
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    # 找出同 metric+asset 当天所有 triggered 告警的 ID 集合
    same_group_alert_ids = set()
    if alert.metric_name and alert.asset_id:
        same_group_alerts = db.query(Alert.id).filter(
            Alert.metric_name == alert.metric_name,
            Alert.asset_id == alert.asset_id,
            Alert.status == "triggered",
        ).all()
        same_group_alert_ids = {r.id for r in same_group_alerts}
    same_group_alert_ids.add(alert_id)  # 至少包含当前告警自身
    # 在这些告警中找当天已有 pending 的 AI 方案
    for _pa in db.query(PendingAction).filter(
        PendingAction.alert_id.in_(list(same_group_alert_ids)),
        PendingAction.status == PendingAction.STATUS_PENDING,
        PendingAction.created_at >= today_start,
    ).all():
        try:
            _pl = json.loads(_pa.action_payload) if _pa.action_payload else {}
            if _pl.get("source") == "ai":
                return {"ok": True, "dedup": True, "pending_action_id": _pa.id,
                        "analysis": {"root_cause": _pl.get("root_cause", ""),
                                     "impact": _pl.get("impact", ""),
                                     "risk_level": _pa.risk_level or "medium",
                                     "action_type": _pa.action_type,
                                     "command": _pl.get("command", ""),
                                     "command_description": _pa.reason or "",
                                     "command_explanation": _pl.get("command_explanation", "")}}
        except Exception:
            pass

    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    # 构造资产类型感知的上下文（引导 AI 按通道给命令）
    if asset:
        ci = (asset.ci_type or "").lower()
        channel = _ci_channel(asset)
        channel_hint = {
            "ssh": "传统主机/中间件（SSH+systemctl 通道）— restart 用 systemctl restart {服务名}",
            "k8s": "K8s 资源（K8s API 通道）— deployment 用 kubectl rollout restart，pod 用 kubectl delete pod，scale 用 kubectl scale",
            "docker": "Docker 容器（宿主机 SSH+docker 通道）— restart 用 docker restart {容器名}",
            "unknown": "未知资产类型 — 请用 notify 通知人工处理",
        }.get(channel, "")
        meta = _parse_k8s_meta(asset) if channel == "k8s" else {}
        k8s_meta_str = f"，namespace={meta.get('namespace','')}，cluster={meta.get('cluster','')}" if channel == "k8s" else ""
        asset_info = f"资产: {asset.name}(ip={asset.ip}, ci_type={asset.ci_type}{k8s_meta_str})\n执行通道: {channel_hint}"
    else:
        asset_info = "未关联资产"

    # ── 查询已启用的自愈工作流，供 AI 评估匹配 ──
    workflows = db.query(RemediationWorkflow).filter(RemediationWorkflow.enabled == True).all()
    wf_lines = []
    wf_id_map = {}  # id -> name，用于校验 AI 返回的 workflow_id
    for w in workflows:
        try:
            steps = json.loads(w.steps) if isinstance(w.steps, str) else (w.steps or [])
            step_names = [s.get("action", str(s)) if isinstance(s, dict) else str(s) for s in steps]
        except Exception:
            step_names = []
        wf_lines.append(f"  - 工作流ID={w.id} 名称={w.name} 步骤={step_names}")
        wf_id_map[w.id] = w.name
    workflow_catalog = "\n".join(wf_lines) if wf_lines else "  （无已配置工作流）"

    system_prompt = """你是一名资深 SRE 运维专家。你的任务是根据告警信息和自动诊断结果，分析故障根因并生成修复方案。

请严格输出 JSON，不要包含其他内容：
{
  "root_cause": "根因分析（详细，200字内，必须引用诊断输出中的具体数据）",
  "impact": "影响评估（100字内）",
  "diagnosis_reasoning": "推理链：从诊断证据→根因结论→修复建议的完整推理过程（300字内，逐条引用诊断命令的输出数据作为证据）",
  "risk_level": "风险等级：low/medium/high/critical",
  "recommended_workflow_id": null,
  "action_type": "修复动作类型：workflow / run_command / restart / clean / notify",
  "command": "具体的修复命令（当 action_type 非 workflow 时必填）",
  "command_description": "方案要做什么的通俗说明（30字内）",
  "command_explanation": "命令详细解释（面向非技术人员的审批人，100-200字）",
  "step_params": {},
  "diagnosis_sufficient": true,
  "next_tools": []
}

⚠️ 迭代诊断规则（重要）：
- 如果当前诊断输出已经能明确根因（如 ps 显示具体进程占 CPU 95%），设 diagnosis_sufficient=true，next_tools=[]，并给出完整修复方案
- 如果诊断数据不足以确定根因，设 diagnosis_sufficient=false，在 next_tools 中推荐最多 5 个需要执行的诊断工具 ID（从下方工具清单中选），修复方案字段可留空
- next_tools 中的 tool_id 必须是工具清单中真实存在的，不要编造
- 优先选择针对性强的 Focused 工具，不要重复已执行的工具

⚠️ 根因分析要求：
- 必须引用诊断输出中的具体数据（如"ps aux 显示 java 进程 PID=12345 占 CPU 95%"）
- 不能只说"CPU 过高"，要指出具体是什么进程/服务导致的
- 如果诊断数据不足以确定根因，明确说明还需要什么信息

⚠️ 推理链（diagnosis_reasoning）要求（这是审批人判断是否执行修复的关键依据）：
- 格式：① 诊断发现 → ② 根因判断 → ③ 修复逻辑
- 示例："① 诊断发现：ps aux 显示 nginx: worker 进程占用 CPU 95%（PID=5678），vmstat 显示 us=95 sy=3，系统负载 15.2（4核）。② 根因判断：nginx worker 进程异常占用 CPU，可能是请求量过大或存在死循环。③ 修复逻辑：重启 nginx 可以终止异常 worker 进程并重新 fork 新进程，恢复正常处理能力。"

决策规则（按优先级）：
1. 若已有工作流能覆盖该故障场景（步骤匹配且合理），设 recommended_workflow_id 为该工作流 ID，action_type="workflow"，command 可留空
2. 若无匹配工作流，按单步动作决策：run_command（诊断/修复命令）/ restart（重启服务）/ clean（清理磁盘）/ notify（仅通知）
3. recommended_workflow_id 必须是给定工作流列表中的真实 ID，不确定时填 null
4. 禁止高危命令：rm -rf、reboot、shutdown、mkfs、dd

⚠️ 关键要求（参数具体化 + 资产类型感知）：
- 必须根据资产的 ci_type 和执行通道给出对应类型的命令，不同通道命令完全不同：
  · 传统主机(server/vm/database/middleware) → restart 用 "systemctl restart {服务名}"
  · K8s 资源(deployment/pod) → restart 用 "kubectl rollout restart deployment {name} -n {ns}" 或 "kubectl delete pod {name} -n {ns}"，scale 用 "kubectl scale deployment {name} --replicas=N -n {ns}"
  · Docker 容器(container) → restart 用 "docker restart {容器名}"
  · 未知类型 → 用 notify 通知人工处理，不要盲目执行
- 推荐工作流时，必须根据根因分析在 step_params 中填入每个步骤的具体参数，不能留空让系统瞎猜。
  例如 CPU 高告警定位到是 nginx 引起，workflow 步骤含 restart_service，则 step_params 应为：
  {"restart_service": {"service": "nginx"}, "notify": {"channel": "email", "template": "alert"}}
- 单步 restart 时 command 必须是完整可执行命令（如 "systemctl restart nginx" 或 "kubectl rollout restart deployment nginx -n prod"），不能只写服务名。
- 服务名/资源名必须是真实存在的（如 nginx/mysql/redis 或 deployment 名），绝不能用 IP 地址或资产名当服务名。
- K8s 资源若需 namespace，从资产信息的 namespace 字段获取。

⚠️ 命令解释（command_explanation）要求（面向不懂命令行的审批人）：
- 必须用通俗语言说明：① 这条命令会做什么操作 ② 操作会影响什么（会中断服务吗？会丢数据吗？） ③ 操作完成后预期效果
- 示例："systemctl restart nginx 命令会重启 Nginx Web 服务器。重启期间（约 5-10 秒）所有 HTTP 请求会暂时无法连接，已建立的长连接会断开。重启后 Nginx 会重新加载配置并恢复服务，之前的请求日志不会丢失。"
- 不能只说"重启服务"，必须说清楚影响范围和恢复预期"""

    # ── 查找该告警的所有诊断报告（初诊 round=0 + AI 补诊轮次），累积诊断证据 ──
    existing_reports = db.query(DiagnosisReport).filter(
        DiagnosisReport.alert_id == alert_id,
        DiagnosisReport.status == DiagnosisReport.STATUS_COMPLETED,
    ).order_by(DiagnosisReport.id.asc()).all()
    all_diag_outputs = []
    for r in existing_reports:
        all_diag_outputs.append({
            "round": r.round_num or 0,
            "output": r.raw_output or "",
            "commands": json.loads(r.commands_run) if r.commands_run else [],
        })

    # ── 查询多维关联分析数据（告警+指标+日志+链路），注入 AI prompt ──
    # 让自愈 AI 不只看本机诊断，还看到同时段的告警风暴/指标异常/日志报错/链路错误
    correlation_section = ""
    if asset and asset.id:
        try:
            corr_data = _get_correlation_cached(db, asset.id, hours=1)
            corr_alerts = corr_data.get("alerts", [])
            corr_metrics = corr_data.get("metric_anomalies", [])
            corr_logs = corr_data.get("log_anomalies", [])
            corr_changes = corr_data.get("change_records", [])
            if corr_alerts or corr_metrics or corr_logs:
                parts = ["【多维关联分析（最近1小时）】"]
                if corr_alerts:
                    parts.append(f"  同期告警({len(corr_alerts)}条):")
                    for a in corr_alerts[:5]:
                        parts.append(f"    - [{a.get('severity','')}] {a.get('metric_name','')} {a.get('message','')[:80]}")
                if corr_metrics:
                    parts.append(f"  指标异常({len(corr_metrics)}项):")
                    for m in corr_metrics[:5]:
                        parts.append(f"    - {m.get('metric_name','')}: {m.get('description','')[:80]}")
                if corr_logs:
                    parts.append(f"  日志异常({len(corr_logs)}条):")
                    for l in corr_logs[:3]:
                        parts.append(f"    - [{l.get('level','')}] {l.get('message','')[:80]}")
                if corr_changes:
                    parts.append(f"  近期变更({len(corr_changes)}条):")
                    for c in corr_changes[:3]:
                        parts.append(f"    - {c.get('description','')[:80]}")
                correlation_section = "\n".join(parts)
        except Exception:
            pass  # 关联分析失败不阻塞主流程

    # ── 查询该资产关联的部署知识文档，注入 AI prompt ──
    deployment_section = ""
    if asset and asset.id:
        try:
            deploy_docs = db.query(KbDocument).filter(
                KbDocument.asset_id == asset.id,
                KbDocument.status == "indexed",
            ).order_by(KbDocument.id.desc()).limit(5).all()
            if deploy_docs:
                doc_parts = []
                for dd in deploy_docs:
                    title = dd.title or ""
                    content = (dd.content or "")[:2000]
                    doc_parts.append(f"【{title}】\n{content}")
                deployment_section = f"""
═══ 该资产的部署知识文档（供参考安装方式/服务名/配置路径）═══
{"".join(doc_parts)}
═══════════════════════════════════════════════════════════════

⚠️ 请参考以上部署文档确定正确的服务名、安装方式（systemd/docker/手动部署）、配置路径等信息，避免给出错误的服务名或命令。"""
        except Exception:
            pass

    # ── 构造诊断工具清单（供 AI 选择补诊工具）──
    from app.routers.diagnostic_tools import DIAGNOSTIC_TOOLS
    valid_tool_ids = {t["id"] for t in DIAGNOSTIC_TOOLS if not t.get("custom") and t.get("risk_level") == "read_only"}
    tool_catalog_lines = [f"  - {t['id']}: {t['name']}（{t.get('description', '')}）"
                          for t in DIAGNOSTIC_TOOLS
                          if not t.get("custom") and t.get("risk_level") == "read_only"]
    tool_catalog = "\n".join(tool_catalog_lines)

    # 已执行的工具 ID（避免重复推荐）
    executed_tool_ids = set()
    for diag in all_diag_outputs:
        for cmd in diag["commands"]:
            tid = cmd.get("tool_id")
            if tid:
                executed_tool_ids.add(tid)

    # ── 迭代诊断 + AI 分析循环（最多 5 轮，每轮最多 5 个工具）──
    MAX_ROUNDS = 5
    MAX_TOOLS_PER_ROUND = 5
    final_analysis = None
    latest_report_id = existing_reports[-1].id if existing_reports else None

    from app.services.agent_service import call_llm
    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            # 构造累积诊断上下文（所有轮次输出）
            diag_parts = []
            for diag in all_diag_outputs:
                rn = diag["round"]
                label = "静态初诊" if rn == 0 else f"第{rn}轮补诊"
                diag_parts.append(f"── {label} ──\n{diag['output'][:4000]}")
            diag_combined = "\n\n".join(diag_parts) if diag_parts else "（暂无诊断数据）"
            diagnosis_section = f"""
以下是对该告警自动执行的诊断命令及输出（只读命令，已自动执行）：
══════════════════════════════════════
{diag_combined[:12000]}
══════════════════════════════════════

⚠️ 请务必基于以上诊断结果分析根因，不要忽略诊断输出中的关键信息。
如果诊断输出显示具体进程/服务名，在推荐修复命令时应引用这些真实信息。"""

            is_final_round = (round_num == MAX_ROUNDS)

            # 构造工具清单提示（仅非最终轮次显示）
            tools_hint = ""
            if not is_final_round:
                tools_hint = f"""
可选诊断工具清单（若需补诊，从其中选择 next_tools）：
{tool_catalog}

已执行的工具: {', '.join(sorted(executed_tool_ids)) if executed_tool_ids else '无'}
请勿重复推荐已执行的工具。"""

            user_prompt = f"""告警信息：
- ID: {alert.id}
- 指标: {alert.metric_name or '-'}
- 级别: {alert.severity or '-'}
- 消息: {alert.message or '-'}
- 实际值: {alert.actual_value}
- 阈值: {alert.threshold}
- 时间: {alert.created_at or '-'}
{asset_info}
{correlation_section}
{diagnosis_section}
{deployment_section}
{tools_hint}

已有自愈工作流清单：
{workflow_catalog}

请分析并输出 JSON。若推荐工作流，recommended_workflow_id 必须是上述清单中的 ID。"""

            # 调 AI
            resp = call_llm(provider, [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], timeout_override=120)
            if resp.get("error"):
                return {"ok": False, "error": f"AI 调用失败: {resp['error']}"}
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return {"ok": False, "error": "AI 返回为空（LLM 调用成功但无返回内容，请检查 AI Provider 配置）"}
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            try:
                analysis = json.loads(content)
            except json.JSONDecodeError:
                try:
                    analysis = json.loads(content, strict=False)
                except json.JSONDecodeError:
                    analysis = _parse_lenient_ai_json(content)
                    if not analysis:
                        import logging
                        logging.getLogger(__name__).warning(
                            f"AI 自愈分析 JSON 解析失败 alert#{alert_id} round#{round_num}\n原始内容(前2000字符):\n{content[:2000]}"
                        )
                        return {"ok": False, "error": "AI 返回的 JSON 格式错误，无法解析", "raw_content": content[:1000]}

            # 检查 AI 是否认为诊断充分
            diagnosis_sufficient = analysis.get("diagnosis_sufficient", True)
            next_tools = analysis.get("next_tools") or []

            if is_final_round or diagnosis_sufficient or not next_tools:
                final_analysis = analysis
                break

            # 过滤 next_tools：只保留有效且未执行的工具
            next_tools = [t for t in next_tools
                          if isinstance(t, str) and t in valid_tool_ids and t not in executed_tool_ids]
            next_tools = next_tools[:MAX_TOOLS_PER_ROUND]

            if not next_tools:
                final_analysis = analysis
                break

            # 执行补诊工具
            round_commands = []
            round_raw_parts = []
            for tool_id in next_tools:
                result = _execute_diagnostic_tool(db, asset, tool_id, round_num)
                round_commands.append(result)
                round_raw_parts.append(
                    f"=== {result.get('tool_name', tool_id)} (round {round_num}) ===\n"
                    f"$ {result.get('cmd', '')}\n{result.get('output', '')[:2000]}\n"
                )
                executed_tool_ids.add(tool_id)

            # 存入 DiagnosisReport
            report = DiagnosisReport(
                alert_id=alert_id,
                asset_id=alert.asset_id,
                metric_name=alert.metric_name or "",
                commands_run=json.dumps(round_commands, ensure_ascii=False),
                raw_output="\n".join(round_raw_parts)[:8000],
                status=DiagnosisReport.STATUS_COMPLETED,
                round_num=round_num,
                finished_at=datetime.now(),
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            latest_report_id = report.id

            all_diag_outputs.append({
                "round": round_num,
                "output": report.raw_output,
                "commands": round_commands,
            })

        # ── 用最终分析结果生成 PendingAction ──
        if not final_analysis:
            return {"ok": False, "error": "AI 迭代诊断循环结束但未产出分析结果"}

        analysis = final_analysis
        diagnosis_report_id = latest_report_id

        risk_level = analysis.get("risk_level", "medium")
        if risk_level not in ("low", "medium", "high", "critical"):
            risk_level = "medium"

        # ── 解析 AI 推荐的工作流（校验 ID 真实存在）──
        rec_wf_id_raw = analysis.get("recommended_workflow_id")
        rec_wf_id = None
        rec_wf_name = ""
        if rec_wf_id_raw is not None:
            try:
                rec_wf_id = int(rec_wf_id_raw)
            except (TypeError, ValueError):
                rec_wf_id = None
        if rec_wf_id is not None and rec_wf_id not in wf_id_map:
            rec_wf_id = None
        if rec_wf_id is not None:
            rec_wf_name = wf_id_map[rec_wf_id]

        action_type_raw = analysis.get("action_type", "notify")
        command = analysis.get("command", "")
        command_desc = analysis.get("command_description", "")
        command_explanation = analysis.get("command_explanation", "")

        # ── 决定最终 action_type：推荐工作流优先，否则单步 ──
        if rec_wf_id is not None and action_type_raw == "workflow":
            action_type = "workflow"
            step_params_ai = analysis.get("step_params") or {}
            if not isinstance(step_params_ai, dict):
                step_params_ai = {}
            action_payload = {"workflow_id": rec_wf_id, "source": "ai", "step_params": step_params_ai, "diagnosis_report_id": diagnosis_report_id}
            title = f"AI 自愈: 执行工作流 #{rec_wf_id} {rec_wf_name}"[:60]
        else:
            action_type = action_type_raw if action_type_raw in ("run_command", "restart", "clean", "notify") else "notify"
            action_payload = {"command": command, "source": "ai", "diagnosis_report_id": diagnosis_report_id, "command_explanation": command_explanation}
            if action_type == "restart":
                action_payload = {"service": command.replace("systemctl restart ", "").strip(), "command": command, "source": "ai", "diagnosis_report_id": diagnosis_report_id, "command_explanation": command_explanation}
            elif action_type == "clean":
                action_payload = {"path": "/tmp", "command": command, "source": "ai", "diagnosis_report_id": diagnosis_report_id, "command_explanation": command_explanation}
            title = f"AI 自愈: {command_desc or command}"[:60]

        # ── 确定性风险分类（覆盖 AI 自评，不依赖 LLM）──
        classified_risk, auto_exec = _classify_command_risk(action_type, command)
        risk_level = classified_risk

        # 详细根因 + 推理链（供审批人判断是否执行）
        root_cause = analysis.get("root_cause", "")
        diagnosis_reasoning = analysis.get("diagnosis_reasoning", "")
        impact = analysis.get("impact", "")
        reason = f"根因: {root_cause}"
        if diagnosis_reasoning:
            reason += f"\n\n推理链: {diagnosis_reasoning}"

        action_payload["diagnosis_reasoning"] = diagnosis_reasoning
        action_payload["root_cause"] = root_cause
        action_payload["impact"] = impact

        pending = PendingAction(
            alert_id=alert.id,
            title=title,
            action_type=action_type,
            risk_level=risk_level,
            reason=reason[:1000],
            status=PendingAction.STATUS_PENDING,
            action_payload=json.dumps(action_payload, ensure_ascii=False),
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)

        if auto_exec:
            exec_result = _auto_execute_readonly(db, pending, asset, alert)
            return {
                "ok": True,
                "auto_executed": True,
                "analysis": {
                    "root_cause": analysis.get("root_cause", ""),
                    "impact": analysis.get("impact", ""),
                    "risk_level": risk_level,
                    "action_type": action_type,
                    "command": command,
                    "command_description": command_desc,
                    "recommended_workflow_id": rec_wf_id,
                    "recommended_workflow_name": rec_wf_name,
                },
                "pending_action_id": pending.id,
                "pending_action_title": pending.title,
                "exec_result": exec_result,
                "diagnosis_report_id": diagnosis_report_id,
            }

        return {
            "ok": True,
            "auto_executed": False,
            "analysis": {
                "root_cause": analysis.get("root_cause", ""),
                "impact": analysis.get("impact", ""),
                "risk_level": risk_level,
                "action_type": action_type,
                "command": command,
                "command_description": command_desc,
                "recommended_workflow_id": rec_wf_id,
                "recommended_workflow_name": rec_wf_name,
            },
            "pending_action_id": pending.id,
            "pending_action_title": pending.title,
            "diagnosis_report_id": diagnosis_report_id,
        }
    except Exception as e:
        return {"ok": False, "error": f"AI 分析失败: {e}"}


def _auto_execute_readonly(db: Session, pa: PendingAction, asset, alert) -> dict:
    """只读诊断命令自动执行（免审批闸门），结果写入 pending + log.

    与 confirm_ai_action 的区别：
    - 不改变告警状态（告警仍 triggered，等真正的修复动作）
    - 不设 confirmed_by（标记为 auto）
    - 仍写 RemediationLog 便于审计
    """
    payload = {}
    try:
        payload = json.loads(pa.action_payload) if pa.action_payload else {}
    except Exception:
        pass

    pa.status = PendingAction.STATUS_EXECUTING
    db.commit()

    success, output = False, "未找到目标资产"
    if asset:
        success, output = execute_action(pa.action_type, payload, asset, db)

    pa.status = PendingAction.STATUS_EXECUTED if success else PendingAction.STATUS_FAILED
    pa.result_payload = json.dumps({"output": output[:1000], "auto_executed": True}, ensure_ascii=False)
    pa.confirmed_by = "auto"
    pa.confirmed_at = datetime.now()
    db.commit()

    log = RemediationLog(
        remediation_id=None,
        alert_id=pa.alert_id,
        action_type=pa.action_type,
        target=asset.name if asset else "",
        is_success=success,
        output=f"[自动执行-只读诊断] {output[:400]}",
    )
    db.add(log)
    db.commit()

    return {"success": success, "output": output[:500]}


def get_ai_pending_actions(db: Session, status: str = "all", limit: int = 50):
    """获取待审批动作（含规则自愈 source=rule 与 AI 自愈 source=ai）."""
    q = db.query(PendingAction).filter(
        PendingAction.alert_id.isnot(None),
        PendingAction.run_id.is_(None),
    )
    if status != "all":
        q = q.filter(PendingAction.status == status)
    items = q.order_by(PendingAction.id.desc()).limit(limit).all()
    result = []
    for pa in items:
        alert_msg = ""
        if pa.alert_id:
            alert = db.query(Alert).filter(Alert.id == pa.alert_id).first()
            if alert:
                alert_msg = alert.message or ""
        payload = {}
        try:
            payload = json.loads(pa.action_payload) if pa.action_payload else {}
        except Exception:
            pass
        source = payload.get("source", "ai")
        # 对 workflow 类型解析工作流步骤，供前端展示具体执行内容
        workflow_steps = None
        wf_name = ""
        wf_id = payload.get("workflow_id") if pa.action_type == "workflow" else None
        if wf_id is not None:
            wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first()
            if wf:
                wf_name = wf.name or ""
                # AI 给出的每步具体参数（如 {"restart_service": {"service": "nginx"}}）
                ai_step_params = payload.get("step_params") or {}
                if not isinstance(ai_step_params, dict):
                    ai_step_params = {}
                # 查关联资产，用于按 ci_type 生成对应通道的展示命令
                wf_asset = None
                if alert and alert.asset_id:
                    wf_asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
                try:
                    steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
                    workflow_steps = []
                    for idx, s in enumerate(steps, 1):
                        if isinstance(s, dict):
                            s_action = s.get("action", "notify")
                            s_name = s.get("step", "")
                            s_params = {k: v for k, v in s.items() if k not in ("step", "action")}
                            # 优先用 AI 给的该步参数（key 优先 action 名，回退 step 名）
                            ai_p = ai_step_params.get(s_action) or ai_step_params.get(s_name)
                            if isinstance(ai_p, dict) and ai_p:
                                s_params = {**s_params, **ai_p}
                            # 按 ci_type 生成对应通道的展示命令（含缺参警告，与执行层一致）
                            real_cmd = _build_rule_command(s_action, s_params, wf_asset)
                            workflow_steps.append(
                                f"{idx}. {real_cmd}  ← {s_name}" if s_name else f"{idx}. {real_cmd}"
                            )
                        else:
                            workflow_steps.append(f"{idx}. {s}")
                except Exception:
                    workflow_steps = None
        # ── 查关联诊断报告（供前端展示诊断过程折叠面板，含多轮补诊）──
        diagnosis_commands = []
        diag_report_id = payload.get("diagnosis_report_id")
        if pa.alert_id:
            try:
                diag_reports = db.query(DiagnosisReport).filter(
                    DiagnosisReport.alert_id == pa.alert_id,
                    DiagnosisReport.status == DiagnosisReport.STATUS_COMPLETED,
                ).order_by(DiagnosisReport.id.asc()).all()
                for dr in diag_reports:
                    try:
                        cmds = json.loads(dr.commands_run) if dr.commands_run else []
                        for c in cmds:
                            if "round_num" not in c:
                                c["round_num"] = dr.round_num or 0
                        diagnosis_commands.extend(cmds)
                    except Exception:
                        pass
                if not diag_report_id and diag_reports:
                    diag_report_id = diag_reports[-1].id
            except Exception:
                pass

        result.append({
            "id": pa.id,
            "alert_id": pa.alert_id,
            "alert_message": alert_msg[:80],
            "title": pa.title or "",
            "action_type": pa.action_type or "",
            "risk_level": pa.risk_level or "low",
            "reason": pa.reason or "",
            "status": pa.status or "pending",
            "command": payload.get("command", ""),
            "command_explanation": payload.get("command_explanation", ""),
            "workflow_id": wf_id,
            "workflow_name": wf_name,
            "workflow_steps": workflow_steps,
            "source": source,
            "remediation_id": payload.get("remediation_id") if source == "rule" else None,
            "result_message": "",
            "diagnosis_commands": diagnosis_commands,
            "diagnosis_report_id": diag_report_id,
            "root_cause": payload.get("root_cause", ""),
            "diagnosis_reasoning": payload.get("diagnosis_reasoning", ""),
            "impact": payload.get("impact", ""),
            "created_at": pa.created_at.strftime("%Y-%m-%d %H:%M:%S") if pa.created_at else "",
        })
    return result


def confirm_ai_action(db: Session, action_id: int, username: str = "admin") -> dict:
    """确认 AI 自愈动作并执行.

    支持两种动作类型：
    - workflow: 执行 AI 推荐的多步骤自愈工作流（循环执行 steps，失败即停）
    - 单步动作: run_command/restart/clean/notify（走 execute_action）
    """
    pa = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not pa:
        return {"ok": False, "error": "动作不存在"}
    if pa.status != PendingAction.STATUS_PENDING:
        return {"ok": False, "error": f"动作状态不是待确认（当前: {pa.status}）"}

    pa.status = PendingAction.STATUS_CONFIRMED
    pa.confirmed_by = username
    pa.confirmed_at = datetime.now()
    db.commit()

    payload = {}
    try:
        payload = json.loads(pa.action_payload) if pa.action_payload else {}
    except Exception:
        pass

    alert = db.query(Alert).filter(Alert.id == pa.alert_id).first() if pa.alert_id else None
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert and alert.asset_id else None

    # ── workflow 类型：多步骤执行（复用 RemediationWorkflow 引擎）──
    if pa.action_type == "workflow":
        wf_id = payload.get("workflow_id")
        wf = db.query(RemediationWorkflow).filter(RemediationWorkflow.id == wf_id).first() if wf_id else None
        if not wf:
            pa.status = PendingAction.STATUS_FAILED
            pa.result_payload = json.dumps({"output": f"工作流 #{wf_id} 不存在"}, ensure_ascii=False)
            db.commit()
            return {"ok": True, "success": False, "output": f"工作流 #{wf_id} 不存在"}
        try:
            steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
        except Exception:
            steps = []

        step_outputs = []
        all_success = True
        target_name = asset.name if asset else f"asset_{alert.asset_id}" if alert else ""
        # AI 给出的每步具体参数（如 {"restart_service": {"service": "nginx"}}）
        ai_step_params = payload.get("step_params") or {}
        if not isinstance(ai_step_params, dict):
            ai_step_params = {}
        for idx, step in enumerate(steps):
            if isinstance(step, dict):
                step_action = step.get("action", "notify")
                step_params = {k: v for k, v in step.items() if k not in ("step", "action")}
            else:
                step_action = str(step)
                step_params = {}
            # 优先用 AI 给的该步参数（key 优先用 action 名，回退 step 名）
            ai_p = ai_step_params.get(step_action) or ai_step_params.get(step.get("step", "")) if isinstance(step, dict) else None
            if isinstance(ai_p, dict) and ai_p:
                step_params = {**step_params, **ai_p}
            # 直接调 execute_action（内部按 ci_type 通道分派 + 缺参判断，缺关键参数会返回 False）
            if not asset:
                s_success, s_output = False, f"未找到资产，无法执行步骤 {idx+1}"
            else:
                s_success, s_output = execute_action(step_action, step_params, asset, db)
            step_outputs.append(f"[Step {idx+1}/{len(steps)} {step_action}] {'OK' if s_success else 'FAIL'}: {s_output[:200]}")
            # 每步落 RemediationLog
            log = RemediationLog(
                remediation_id=wf.id,
                remediation_type="workflow",
                alert_id=pa.alert_id,
                action_type=step_action,
                target=target_name,
                is_success=s_success,
                output=f"[Step {idx+1}/{len(steps)}] {s_output[:400]}",
            )
            db.add(log)
            db.commit()
            try:
                from app.services.remediation_effect_service import track_effect
                track_effect(log.id, db)
            except Exception:
                pass
            if not s_success:
                all_success = False
                break  # 失败即停，避免后续步骤雪崩
        db.commit()
        output = "\n".join(step_outputs)
        pa.status = PendingAction.STATUS_EXECUTED if all_success else PendingAction.STATUS_FAILED
        pa.result_payload = json.dumps({"output": output[:1000], "workflow_id": wf_id, "workflow_name": wf.name}, ensure_ascii=False)
        db.commit()
        if alert:
            alert.status = "acknowledged"
            alert.message += f" [AI 自愈执行工作流: {wf.name}]"
            db.commit()
        # 执行成功后自动沉淀知识
        if all_success and pa.alert_id:
            try:
                from app.services.knowledge_autogen_service import generate_draft
                generate_draft(pa.alert_id, db, force=True)
            except Exception:
                pass
        return {"ok": True, "success": all_success, "output": output[:500],
                "workflow_id": wf_id, "workflow_name": wf.name}

    # ── 单步动作 ──
    success, output = False, "未找到目标资产"
    # 规则来源(source=rule)的参数嵌套在 payload["params"]；AI 来源参数在 payload 顶层
    source = payload.get("source", "ai")
    exec_params = payload.get("params", payload) if source == "rule" else payload
    remediation_id_for_log = payload.get("remediation_id") if source == "rule" else None
    if asset:
        success, output = execute_action(pa.action_type, exec_params, asset, db)

    pa.status = PendingAction.STATUS_EXECUTED if success else PendingAction.STATUS_FAILED
    pa.result_payload = json.dumps({"output": output[:1000]}, ensure_ascii=False)
    db.commit()

    _alert_status_before = alert.status if alert else "triggered"
    if alert:
        alert.status = "acknowledged"
        alert.message += f" [自愈执行: {pa.action_type}]"
        db.commit()

    log = RemediationLog(
        remediation_id=remediation_id_for_log,
        remediation_type="rule",
        alert_id=pa.alert_id,
        action_type=pa.action_type,
        target=asset.name if asset else "",
        is_success=success,
        output=output[:500],
    )
    db.add(log)
    db.commit()
    try:
        from app.services.remediation_effect_service import track_effect
        track_effect(log.id, db, status_before=_alert_status_before)
    except Exception:
        pass

    # ── 执行成功后自动沉淀知识（复用智能助手知识生成能力）──
    if success and pa.alert_id:
        try:
            from app.services.knowledge_autogen_service import generate_draft
            generate_draft(pa.alert_id, db, force=True)
        except Exception:
            pass  # 知识沉淀失败不阻塞主流程

    return {"ok": True, "success": success, "output": output[:500]}


def cancel_ai_action(db: Session, action_id: int) -> dict:
    """取消 AI 自愈动作."""
    pa = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not pa:
        return {"ok": False, "error": "动作不存在"}
    if pa.status != PendingAction.STATUS_PENDING:
        return {"ok": False, "error": f"动作状态不是待确认（当前: {pa.status}）"}
    pa.status = PendingAction.STATUS_CANCELED
    db.commit()
    return {"ok": True}


def reanalyze_with_failure_context(db: Session, failed_action_id: int) -> dict:
    """基于失败经验重新分析，生成新修复方案.

    保留原始诊断上下文，注入失败命令+错误输出，让 AI 换个思路。
    """
    pa = db.query(PendingAction).filter(PendingAction.id == failed_action_id).first()
    if not pa:
        return {"ok": False, "error": "动作不存在"}
    if pa.status != PendingAction.STATUS_FAILED:
        return {"ok": False, "error": f"只有失败的动作才能重新分析（当前: {pa.status}）"}

    payload = {}
    try:
        payload = json.loads(pa.action_payload) if pa.action_payload else {}
    except Exception:
        pass

    # 找关联的告警和资产
    alert = db.query(Alert).filter(Alert.id == pa.alert_id).first() if pa.alert_id else None
    if not alert:
        return {"ok": False, "error": "关联告警不存在"}
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None

    # 找原始诊断报告
    diag_report = None
    diag_report_id = payload.get("diagnosis_report_id")
    if diag_report_id:
        diag_report = db.query(DiagnosisReport).filter(DiagnosisReport.id == diag_report_id).first()
    if not diag_report:
        diag_report = db.query(DiagnosisReport).filter(
            DiagnosisReport.alert_id == alert.id,
            DiagnosisReport.status == DiagnosisReport.STATUS_COMPLETED,
        ).order_by(DiagnosisReport.id.desc()).first()

    # 读取原始诊断输出
    diag_output = ""
    if diag_report and diag_report.raw_output:
        diag_output = diag_report.raw_output[:6000]

    # 读取失败信息
    failed_command = payload.get("command", "")
    result_payload = {}
    try:
        result_payload = json.loads(pa.result_payload) if pa.result_payload else {}
    except Exception:
        pass
    failed_output = result_payload.get("output", "")

    # AI 配置
    from app.models import AIProvider
    provider = db.query(AIProvider).filter(AIProvider.enabled == True).first()
    if not provider:
        return {"ok": False, "error": "未配置 AI 提供商"}

    # 构建资产信息
    asset_info = ""
    if asset:
        ci_type = getattr(asset, 'ci_type', '') or ''
        asset_info = f"- 资产: {asset.name} (ID={asset.id}, 类型={ci_type}"
        # 收集扩展属性
        try:
            from app.models import CIAttribute
            attrs = db.query(CIAttribute).filter(CIAttribute.asset_id == asset.id).all()
            if attrs:
                extra = ", ".join(f"{a.attr_key}={a.attr_value}" for a in attrs if a.attr_value)
                asset_info += f", {extra}" if extra else ""
        except Exception:
            pass
        asset_info += ")"

    # 查询可用工作流
    from app.models import RemediationWorkflow
    wf_lines = []
    wf_id_map = {}
    for w in db.query(RemediationWorkflow).filter(RemediationWorkflow.enabled == True).all():
        try:
            steps = json.loads(w.steps) if isinstance(w.steps, str) else (w.steps or [])
        except Exception:
            steps = []
        step_names = [s.get("step", s.get("action", "?")) if isinstance(s, dict) else str(s) for s in steps]
        wf_lines.append(f"  ID={w.id} 名称={w.name} 步骤=[{', '.join(step_names)}]")
        wf_id_map[w.id] = w.name
    workflow_catalog = "\n".join(wf_lines) if wf_lines else "  （无已配置工作流）"

    system_prompt = """你是一名资深 SRE 运维专家。之前的修复尝试失败了，现在需要你换一个思路。

请严格输出 JSON，不要包含其他内容：
{
  "root_cause": "根因分析（可更新，200字内）",
  "impact": "影响评估（100字内）",
  "diagnosis_reasoning": "推理链：从失败经验→新判断→新修复方案（300字内）",
  "risk_level": "风险等级：low/medium/high/critical",
  "recommended_workflow_id": null,
  "action_type": "修复动作类型：workflow / run_command / restart / clean / notify",
  "command": "新的修复命令",
  "command_description": "方案要做什么的通俗说明（30字内）",
  "command_explanation": "命令详细解释（面向非技术人员的审批人，100-200字）",
  "step_params": {}
}

⚠️ 失败分析要求：
- 上一条命令执行失败，你必须分析失败原因（如：服务名不对、权限不够、安装方式不同等）
- 根据失败原因调整方案，不能重复同样的错误
- 如果是服务名问题，尝试用其他方式定位真实服务名（如 docker ps、systemctl list-units）
- 如果是权限问题，建议通知人工处理
- 如果是安装方式问题（如 Docker 安装而非 systemd），换用对应的命令

⚠️ 推理链要求：
- 格式：① 失败原因分析 → ② 新的修复思路 → ③ 为什么这个新方案能成功
- 必须明确说明上一条命令为什么失败，以及新方案如何避免同样的问题

决策规则（按优先级）：
1. 若已有工作流能覆盖该场景，设 recommended_workflow_id，action_type="workflow"
2. 否则按单步动作决策
3. 禁止高危命令：rm -rf、reboot、shutdown、mkfs、dd

⚠️ 命令解释（command_explanation）要求：
- 用通俗语言说明：① 这条命令做什么 ② 影响什么 ③ 预期效果"""

    # 构建 user_prompt
    failure_section = f"""
═══ 上一次修复尝试（已失败）═══
命令: {failed_command}
失败输出: {failed_output}
═══════════════════════════════════

⚠️ 请分析上一条命令为什么失败，并给出不同的修复方案。不要重复同样的错误。"""

    diagnosis_section = ""
    if diag_output:
        diagnosis_section = f"""
以下是对该告警自动执行的诊断命令及输出：
═══════════════════════════════════════
{diag_output}
═══════════════════════════════════════"""

    # ── 查询该资产关联的部署知识文档 ──
    deployment_section = ""
    if asset and asset.id:
        try:
            deploy_docs = db.query(KbDocument).filter(
                KbDocument.asset_id == asset.id,
                KbDocument.status == "indexed",
            ).order_by(KbDocument.id.desc()).limit(5).all()
            if deploy_docs:
                doc_parts = []
                for dd in deploy_docs:
                    title = dd.title or ""
                    content = (dd.content or "")[:2000]
                    doc_parts.append(f"【{title}】\n{content}")
                deployment_section = f"""
═══ 该资产的部署知识文档 ═══
{"".join(doc_parts)}
═══════════════════════════════

⚠️ 请参考以上部署文档确定正确的服务名、安装方式、配置路径，避免给出错误的命令。"""
        except Exception:
            pass

    user_prompt = f"""告警信息：
- ID: {alert.id}
- 指标: {alert.metric_name or '-'}
- 级别: {alert.severity or '-'}
- 消息: {alert.message or '-'}
- 实际值: {alert.actual_value}
- 阈值: {alert.threshold}
- 时间: {alert.created_at or '-'}
{asset_info}
{diagnosis_section}
{deployment_section}
{failure_section}

已有自愈工作流清单：
{workflow_catalog}

请分析并输出 JSON。上次失败了，请换一个思路。"""

    from app.services.agent_service import call_llm
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        if resp.get("error"):
            return {"ok": False, "error": f"AI 调用失败: {resp['error']}"}
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return {"ok": False, "error": f"AI 调用失败: {e}"}

    # 解析 JSON
    import re
    content = content.strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        analysis = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', content)
        if m:
            analysis = json.loads(m.group())
        else:
            return {"ok": False, "error": f"AI 输出无法解析: {content[:200]}"}

    # 提取结果
    rec_wf_id = analysis.get("recommended_workflow_id")
    if rec_wf_id is not None:
        try:
            rec_wf_id = int(rec_wf_id)
        except (TypeError, ValueError):
            rec_wf_id = None
    if rec_wf_id is not None and rec_wf_id not in wf_id_map:
        rec_wf_id = None
    rec_wf_name = wf_id_map.get(rec_wf_id, "")

    action_type_raw = analysis.get("action_type", "notify")
    command = analysis.get("command", "")
    command_desc = analysis.get("command_description", "")
    command_explanation = analysis.get("command_explanation", "")

    # 决定 action_type
    if rec_wf_id is not None and action_type_raw == "workflow":
        action_type = "workflow"
        step_params_ai = analysis.get("step_params") or {}
        if not isinstance(step_params_ai, dict):
            step_params_ai = {}
        new_payload = {"workflow_id": rec_wf_id, "source": "ai", "step_params": step_params_ai, "diagnosis_report_id": diag_report.id if diag_report else None}
        title = f"AI 换思路: 执行工作流 #{rec_wf_id} {rec_wf_name}"[:60]
    else:
        action_type = action_type_raw if action_type_raw in ("run_command", "restart", "clean", "notify") else "notify"
        new_payload = {"command": command, "source": "ai", "diagnosis_report_id": diag_report.id if diag_report else None, "command_explanation": command_explanation}
        if action_type == "restart":
            new_payload = {"service": command.replace("systemctl restart ", "").strip(), "command": command, "source": "ai", "diagnosis_report_id": diag_report.id if diag_report else None, "command_explanation": command_explanation}
        elif action_type == "clean":
            new_payload = {"path": "/tmp", "command": command, "source": "ai", "diagnosis_report_id": diag_report.id if diag_report else None, "command_explanation": command_explanation}
        title = f"AI 换思路: {command_desc or command}"[:60]

    # 风险分类
    classified_risk, auto_exec = _classify_command_risk(action_type, command)

    # 保留原始根因，追加失败经验
    root_cause = analysis.get("root_cause", "")
    diagnosis_reasoning = analysis.get("diagnosis_reasoning", "")
    impact = analysis.get("impact", "")
    reason = f"根因: {root_cause}"
    if diagnosis_reasoning:
        reason += f"\n\n推理链: {diagnosis_reasoning}"

    new_payload["diagnosis_reasoning"] = diagnosis_reasoning
    new_payload["root_cause"] = root_cause
    new_payload["impact"] = impact

    # 创建新的 PendingAction
    new_pa = PendingAction(
        alert_id=alert.id,
        title=title,
        action_type=action_type,
        risk_level=classified_risk,
        reason=reason[:1000],
        status=PendingAction.STATUS_PENDING,
        action_payload=json.dumps(new_payload, ensure_ascii=False),
    )
    db.add(new_pa)
    db.commit()
    db.refresh(new_pa)

    return {
        "ok": True,
        "pending_action_id": new_pa.id,
        "analysis": {
            "root_cause": root_cause,
            "impact": impact,
            "risk_level": classified_risk,
            "action_type": action_type,
            "command": command,
            "command_description": command_desc,
        },
    }


def reanalyze_alert(db: Session, alert_id: int) -> dict:
    """对指定告警重新 AI 分析：取消旧 PA，让 AI 重新审视并推荐方案（含工作流+step_params）."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # 取消今日针对该告警的所有 pending PA
    old_pas = db.query(PendingAction).filter(
        PendingAction.alert_id == alert_id,
        PendingAction.status == PendingAction.STATUS_PENDING,
        PendingAction.created_at >= today_start,
    ).all()
    for pa in old_pas:
        pa.status = PendingAction.STATUS_CANCELED
    db.commit()

    # 重新 AI 分析（在同一模块内直接调用）
    result = ai_self_heal_analyze(db, alert_id)
    return result

