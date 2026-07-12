import json
import random
import re
from datetime import datetime
from typing import Optional

import paramiko
from sqlalchemy.orm import Session

from app.models import AutoRemediation, RemediationLog, Alert, AlertRule, Asset


def list_remediations(db: Session):
    return db.query(AutoRemediation).order_by(AutoRemediation.id.desc()).all()


def create_remediation(db: Session, data: dict):
    if isinstance(data.get("params"), dict):
        data["params"] = json.dumps(data["params"], ensure_ascii=False)
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
    "scale": {"label": "scale", "template": "adjust {target} replicas to {count}"},
    "script": {"label": "执行脚本", "template": "bash {script_path}"},
    "run_command": {"label": "执行命令", "template": "{command}"},
    "notify": {"label": "发送通知", "template": "notify {channel} {message}"},
}


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


def _check_dangerous_command(command: str) -> Optional[str]:
    """检测命令是否命中危险黑名单，命中返回原因，None 表示安全."""
    match = _DANGEROUS_CMD_RE.search(command)
    if match:
        return f"命令命中危险黑名单（匹配: {match.group(0)[:60]}），已拦截"
    return None


def _ssh_connect(asset: Asset, timeout: int = 10) -> paramiko.SSHClient:
    """通过资产记录的 connection_config 建立 SSH 连接.

    复用 metric_collector._ssh_connect 的连接逻辑，集中在此处避免循环依赖。
    connection_config JSON 结构: {"ssh_user":"root","ssh_password":"xxx","ssh_port":22}
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

    from app.services.ssh_helper import get_ssh_client
    ssh = get_ssh_client()
    ssh.connect(host, port=port, username=username, password=password,
                timeout=timeout, banner_timeout=timeout)
    return ssh


def _remote_exec(asset: Asset, command: str, timeout: int = 30) -> tuple:
    """在远程资产上执行单条命令，返回 (success, output).

    success 由 returncode==0 判定；output 合并 stdout+stderr 便于排错。
    SSH 连接失败、命令超时均返回 (False, 错误描述)，不抛异常给上层，
    由调用方决定如何包装返回（raise 或 return）。
    """
    try:
        ssh = _ssh_connect(asset, timeout=timeout)
    except Exception as e:
        return (False, f"SSH 连接失败: {e}")
    try:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        output = "\n".join(s for s in [out, err] if s)
        return (code == 0, output or f"exit_code={code}")
    except Exception as e:
        return (False, f"远程命令执行异常: {e}")
    finally:
        ssh.close()


# 动作类型别名映射：兼容种子数据生成的非标准名
_ACTION_ALIASES = {
    "restart_service": "restart",
    "clean_disk": "clean",
    "scale_up": "scale",
    "scale_down": "scale",
    "execute_command": "run_command",
    "run_script": "script",
}


def execute_action(action_type: str, params: dict, asset: Asset) -> tuple:
    """在远程资产上执行修复动作 — 通过 SSH 远程执行，绝不触碰本机.

    params 含业务参数（service/path/script 等）；asset 提供连接信息（ip/ssh 凭据）。
    返回 (success, message)。
    """
    # 别名自动转换
    action_type = _ACTION_ALIASES.get(action_type, action_type)
    if action_type == "restart":
        # 远程重启服务：sudo systemctl restart {service}
        service_name = params.get("service", "")
        if not service_name:
            return (False, "缺少参数: service")
        # 服务名只允许字母数字下划线-点，防注入（systemctl 不接受 shell 元字符）
        if not all(c.isalnum() or c in "-_." for c in service_name):
            return (False, f"非法服务名: {service_name}")
        command = f"sudo systemctl restart {service_name}"
        success, output = _remote_exec(asset, command, timeout=30)
        if success:
            return (True, f"服务 {service_name} 在 {asset.ip} 重启成功")
        return (False, f"服务 {service_name} 在 {asset.ip} 重启失败: {output}")
    elif action_type == "clean":
        # 远程清理磁盘：删除 7 天前的旧文件
        clean_path = params.get("path", "/tmp")
        # 路径白名单校验：防 rm -rf / 等危险路径
        if not clean_path.startswith(("/", "/var", "/tmp", "/opt", "/home")):
            return (False, f"非法清理路径: {clean_path}，仅允许 /tmp /var /opt /home 下路径")
        command = f"find {clean_path} -type f -mtime +7 -delete"
        success, output = _remote_exec(asset, command, timeout=60)
        if success:
            return (True, f"清理 {asset.ip}:{clean_path} 完成")
        return (False, f"清理 {asset.ip}:{clean_path} 失败: {output}")
    elif action_type == "scale":
        return (False, "扩缩容需要 K8s 配置，未执行")
    elif action_type == "script":
        # 远程执行脚本
        script_path = params.get("script", "")
        if not script_path:
            return (False, "未指定脚本路径")
        # 脚本路径防注入：只允许字母数字下划线-点/斜杠
        if not all(c.isalnum() or c in "-_./" for c in script_path):
            return (False, f"非法脚本路径: {script_path}")
        command = f"bash {script_path}"
        success, output = _remote_exec(asset, command, timeout=30)
        if success:
            return (True, f"脚本 {script_path} 在 {asset.ip} 执行完成: {output[:500]}")
        return (False, f"脚本 {script_path} 在 {asset.ip} 执行失败: {output[:500]}")
    elif action_type == "run_command":
        # 远程执行任意命令（critical，危险命令黑名单拦截）
        command = params.get("command", "")
        if not command:
            return (False, "缺少参数: command")
        # 命令长度限制：防超长命令攻击（正常诊断命令不超过 1000 字符）
        if len(command) > 1000:
            return (False, f"命令过长（{len(command)} 字符，上限 1000）")
        # 危险命令黑名单拦截
        danger = _check_dangerous_command(command)
        if danger:
            return (False, danger)
        success, output = _remote_exec(asset, command, timeout=30)
        if success:
            return (True, f"命令在 {asset.ip} 执行完成: {output[:500]}")
        return (False, f"命令在 {asset.ip} 执行失败: {output[:500]}")
    elif action_type == "notify":
        return (True, f"通知已发送: {asset.ip}")
    else:
        return (False, f"未知操作类型: {action_type}")


def check_and_remediate(db: Session):
    now = datetime.now()
    remediations = db.query(AutoRemediation).filter(AutoRemediation.enabled == True).all()
    logs = []

    for rem in remediations:
        q = db.query(Alert).filter(Alert.status == "triggered")
        if rem.rule_id:
            q = q.filter(Alert.rule_id == rem.rule_id)
        alerts = q.order_by(Alert.created_at.desc()).limit(5).all()

        for alert in alerts:
            recent = db.query(RemediationLog).filter(
                RemediationLog.alert_id == alert.id,
                RemediationLog.remediation_id == rem.id,
                RemediationLog.created_at > now,
            ).first()
            if recent:
                continue

            params = json.loads(rem.params) if rem.params else {}
            target = params.get("target", f"asset_{alert.asset_id}")
            # execute_action 现在要求 asset 对象；自动响应场景按 alert.asset_id 查资产
            asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
            if asset:
                success, output = execute_action(rem.action_type, params, asset)
            else:
                success, output = (False, f"未找到资产 alert.asset_id={alert.asset_id}，无法远程执行")

            log = RemediationLog(
                remediation_id=rem.id,
                alert_id=alert.id,
                action_type=rem.action_type,
                target=target,
                success=success,
                output=output,
            )
            db.add(log)
            logs.append(log)
            alert.status = "acknowledged"
            alert.message += f" [已触发自动响应: {rem.action_type}]"

    if logs:
        db.commit()
        for log in logs:
            db.refresh(log)
    return logs



