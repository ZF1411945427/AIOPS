"""域模型: auth (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(String(256), default="")
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RoleMenu(Base):
    __tablename__ = "role_menus"
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    menu_key = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now())


class RolePermission(Base):
    """资源级 RBAC 策略（对齐 Ongrid Casbin resource:action 策略矩阵）。

    resource=alert/asset/incident/deploy/k8s/user/role/config/report/...;
    action=read/write/execute/delete。superuser 角色自动拥有全部权限（绕过策略）。
    """
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    resource = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # read / write / execute / delete
    created_at = Column(DateTime, default=lambda: datetime.now())
    __table_args__ = (UniqueConstraint("role_id", "resource", "action", name="uq_role_permission"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), default="admin")
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now())


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    permissions = Column(String(256), default="read")
    last_used_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(16), default="active")
    quota_assets = Column(Integer, default=1000)
    quota_users = Column(Integer, default=50)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AuditLog(Base):
    """审计日志表：所有写操作（POST/PUT/PATCH/DELETE）由中间件自动记录。

    覆盖：资产变更 / 审批 / 配置修改 / 脚本执行 / Token 管理 / 用户权限变更 等。
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), default="")
    method = Column(String(16), nullable=False)           # GET / POST / PUT / PATCH / DELETE
    path = Column(String(256), nullable=False, index=True)        # 实际请求路径（含资源 ID，如 /api/tags/5）
    route_path = Column(String(256), default="", index=True)      # 路由模板路径（如 /api/tags/{tag_id}），用于覆盖率精确匹配
    action = Column(String(64), default="")               # create / update / delete / approve / login 等
    target_type = Column(String(64), default="")          # asset / incident / user / config / token 等
    target_id = Column(String(64), default="")            # 目标资源 ID（字符串以兼容 UUID）
    status_code = Column(Integer, default=0)              # HTTP 响应状态码
    ip = Column(String(64), default="")
    user_agent = Column(String(256), default="")
    request_body = Column(Text, default="")               # 请求体（脱敏后，密码字段已屏蔽）
    response_summary = Column(String(256), default="")    # 响应摘要
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
