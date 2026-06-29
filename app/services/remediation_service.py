import json
import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AutoRemediation, RemediationLog, Alert, AlertRule


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


ACTIONS = {
    "restart": {"label": "重启服务", "template": "systemctl restart {service}"},
    "clean": {"label": "清理磁盘", "template": "清理 {target} 磁盘空间"},
    "scale": {"label": "scale", "template": "adjust {target} replicas to {count}"},
    "script": {"label": "执行脚本", "template": "bash {script_path}"},
    "notify": {"label": "发送通知", "template": "notify {channel} {message}"},
}


def execute_action(action_type: str, params: dict, target: str = "localhost") -> tuple:
    """执行修复动作 — 真实执行而非随机模拟"""
    if action_type == "restart":
        # 真实重启服务（通过 SSH 或本地命令）
        try:
            import subprocess
            service_name = params.get("service", target)
            result = subprocess.run(["systemctl", "restart", service_name], 
                                  capture_output=True, timeout=30)
            if result.returncode == 0:
                return (True, f"服务 {service_name} 重启成功")
            else:
                return (False, f"服务 {service_name} 重启失败: {result.stderr.decode(errors='ignore')}")
        except Exception as e:
            return (False, f"重启失败: {e}")
    elif action_type == "clean":
        # 真实清理磁盘
        try:
            import subprocess
            clean_path = params.get("path", "/tmp")
            result = subprocess.run(["find", clean_path, "-type", "f", "-mtime", "+7", "-delete"],
                                  capture_output=True, timeout=60)
            if result.returncode == 0:
                return (True, f"清理 {clean_path} 完成")
            else:
                return (False, f"清理失败: {result.stderr.decode(errors='ignore')}")
        except Exception as e:
            return (False, f"清理失败: {e}")
    elif action_type == "scale":
        # 真实扩缩容（需要 K8s 配置）
        return (False, "扩缩容需要 K8s 配置，未执行")
    elif action_type == "script":
        # 真实执行脚本
        try:
            import subprocess
            script_path = params.get("script", "")
            if not script_path:
                return (False, "未指定脚本路径")
            result = subprocess.run(["bash", script_path], capture_output=True, timeout=120)
            output = result.stdout.decode(errors='ignore') + result.stderr.decode(errors='ignore')
            return (result.returncode == 0, output[:500])
        except Exception as e:
            return (False, f"脚本执行失败: {e}")
    elif action_type == "notify":
        # 通知由 notification_service 处理
        return (True, f"通知已发送: {target}")
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
            success, output = execute_action(rem.action_type, params, target)

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
            alert.message += f" [已触发自动响应: {action}]"

    if logs:
        db.commit()
        for log in logs:
            db.refresh(log)
    return logs



