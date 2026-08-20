from dataclasses import dataclass, field
from email.mime.text import MIMEText
from smtplib import SMTP, SMTPException
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class EmailAuthConfig(BaseAuthConfig):
    smtp_host: str = field(default="", metadata={"required": True, "sensitive": False, "description": "SMTP 服务器地址"})
    smtp_port: int = field(default=587, metadata={"required": False, "sensitive": False, "description": "SMTP 端口"})
    smtp_user: str = field(default="", metadata={"required": True, "sensitive": False, "description": "SMTP 用户名"})
    smtp_password: str = field(default="", metadata={"required": True, "sensitive": True, "description": "SMTP 密码"})
    use_tls: bool = field(default=True, metadata={"required": False, "sensitive": False, "description": "启用 TLS"})
    from_addr: str = field(default="", metadata={"required": True, "sensitive": False, "description": "发件人地址"})
    to_addrs: str = field(default="", metadata={"required": True, "sensitive": False, "description": "收件人地址（逗号分隔）"})

    def __post_init__(self):
        self.smtp_host = self.smtp_host or ""
        self.smtp_port = self.smtp_port or 587
        self.smtp_user = self.smtp_user or ""
        self.smtp_password = self.smtp_password or ""
        self.use_tls = self.use_tls if isinstance(self.use_tls, bool) else True
        self.from_addr = self.from_addr or ""
        self.to_addrs = self.to_addrs or ""


class EmailProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="email",
        display_name="Email",
        category=ProviderCategory.NOTIFICATION,
        description="邮件通知集成，通过 SMTP 发送告警邮件",
        tags=["notification", "email", "smtp", "alerting"],
        icon="email",
        auth_config_class=EmailAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> EmailAuthConfig:
        return EmailAuthConfig.from_dict(auth_config)

    def _connect(self) -> SMTP:
        cfg = self.auth_config
        smtp = SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
        smtp.ehlo()
        if cfg.use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(cfg.smtp_user, cfg.smtp_password)
        return smtp

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.smtp_host or not cfg.smtp_user or not cfg.smtp_password:
            return False, "SMTP 配置不完整（host / user / password）"
        try:
            smtp = self._connect()
            smtp.quit()
            return True, "SMTP 连接正常"
        except SMTPException as e:
            return False, f"SMTP 连接失败: {e}"
        except Exception as e:
            return False, f"SMTP 异常: {e}"

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        if not cfg.from_addr or not cfg.to_addrs:
            return {"success": False, "message": "发件人或收件人地址未配置"}

        title = alert.get("title", "AIOps 告警通知")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")

        body = f"""告警级别: {severity}
标题: {title}

详情:
{message}

---
AIOps 监控系统
"""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[AIOps] {severity.upper()} - {title}"
        msg["From"] = cfg.from_addr
        msg["To"] = cfg.to_addrs

        to_list = [addr.strip() for addr in cfg.to_addrs.split(",") if addr.strip()]

        try:
            smtp = self._connect()
            smtp.sendmail(cfg.from_addr, to_list, msg.as_string())
            smtp.quit()
            return {"success": True, "message": f"邮件已发送至 {len(to_list)} 个收件人"}
        except SMTPException as e:
            return {"success": False, "message": f"邮件发送失败: {e}"}
        except Exception as e:
            return {"success": False, "message": f"邮件异常: {e}"}

    def dispose(self):
        pass