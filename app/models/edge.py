"""域模型: edge (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class EdgeSession(Base):
    """Edge Agent 反向隧道会话。

    edge agent 启动时主动 WebSocket 拨出到云端，云端为此连接创建一个 EdgeSession。
    云端通过 EdgeSession.id 路由 WebSSH / 命令执行到对应 edge agent。
    主机侧零监听端口，所有命令走已建立的反向隧道。
    """
    __tablename__ = "edge_sessions"

    STATUS_ONLINE = "online"
    STATUS_OFFLINE = "offline"
    STATUS_RECONNECTING = "reconnecting"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(64), unique=True, nullable=False, index=True)  # edge agent 唯一标识（主机名+MAC 哈希）
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)       # 关联资产（首次连接时绑定）
    hostname = Column(String(128), default="")
    os_type = Column(String(32), default="linux")                            # linux / windows / macos
    ip_addresses = Column(Text, default="[]")                                # JSON 数组
    agent_version = Column(String(32), default="")
    status = Column(String(16), default=STATUS_OFFLINE)
    tunnel_token = Column(String(128), default="")                           # 隧道认证 token（edge agent 拨出时携带）
    last_heartbeat_at = Column(DateTime, nullable=True)
    connected_at = Column(DateTime, nullable=True)
    disconnected_at = Column(DateTime, nullable=True)
    reconnect_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_ip_addresses(self):
        try:
            return json.loads(self.ip_addresses) if self.ip_addresses else []
        except (json.JSONDecodeError, TypeError):
            return []


class DiagnosisReport(Base):
    """诊断报告 —— 自愈流程的"证据链"，记录自动诊断阶段执行的只读命令及输出."""
    __tablename__ = "diagnosis_reports"

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    metric_name = Column(String(100), default="")
    commands_run = Column(Text, default="[]")     # JSON: [{cmd, desc, output, duration_ms, exit_code, tool_id, round_num}]
    raw_output = Column(Text, default="")          # 拼接后的完整输出（供 AI prompt 注入）
    summary = Column(String(500), default="")      # 一句话摘要（可选，后期可由 AI 生成）
    status = Column(String(20), default=STATUS_RUNNING)
    round_num = Column(Integer, default=0)         # 诊断轮次：0=静态初诊，1..N=AI 驱动补诊轮次
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


class EdgeCommandLog(Base):
    """Edge Agent 命令执行审计日志（全程审计）。"""
    __tablename__ = "edge_command_logs"

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("edge_sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)                                 # 发起用户
    username = Column(String(64), default="")
    command = Column(Text, default="")                                       # 执行的命令
    cwd = Column(String(256), default="")                                    # 工作目录
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    status = Column(String(16), default=STATUS_RUNNING)
    client_ip = Column(String(64), default="")                               # 发起端 IP（浏览器侧）
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


class SandboxConfig(Base):
    """AI 运维沙盒全局配置（单行）。

    用于控制 AI Agent 在节点上的作用范围。本模块独立，
    暂不侵入 agent_service / remediation_service / edge_tunnel_service 现有执行链。
    """
    __tablename__ = "sandbox_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), default="default")
    is_enabled = Column(Boolean, default=False)                              # 沙盒总开关（默认关闭）
    dry_run_mode = Column(Boolean, default=False)                            # 干运行模式：记录但不执行
    max_actions_per_session = Column(Integer, default=10)                    # 单会话最大执行次数
    max_actions_per_day = Column(Integer, default=50)                        # 单日最大执行次数
    max_risk_level = Column(String(16), default="critical")                  # 允许最大风险等级
    execution_window_start = Column(String(5), default="")                   # 写操作允许开始 "HH:MM"
    execution_window_end = Column(String(5), default="")                     # 写操作允许结束 "HH:MM"
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class SandboxPolicy(Base):
    """AI 运维沙盒细粒度策略。

    按作用范围（global/role/user/session）限定 AI Agent 可操作的资产、工具、命令、风险等级、执行配额。
    黑名单优先级高于白名单。
    """
    __tablename__ = "sandbox_policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, default="")
    scope_type = Column(String(16), default="global")                        # global / role / user / session
    scope_id = Column(Integer, default=0)
    allowed_asset_ids = Column(Text, default="[]")                           # JSON 数组
    blocked_asset_ids = Column(Text, default="[]")                           # JSON 数组
    allowed_tools = Column(Text, default="[]")                               # JSON 数组
    blocked_tools = Column(Text, default="[]")                               # JSON 数组
    allowed_commands = Column(Text, default="[]")                            # JSON 数组（命令前缀白名单）
    blocked_commands = Column(Text, default="[]")                            # JSON 数组（支持正则）
    max_risk_level = Column(String(16), default="critical")
    max_actions_per_day = Column(Integer, default=0)                         # 0=继承全局
    require_second_approval = Column(Boolean, default=False)                 # 高危操作是否需二级审批
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_allowed_asset_ids(self):
        return self._parse_json(self.allowed_asset_ids)

    def get_blocked_asset_ids(self):
        return self._parse_json(self.blocked_asset_ids)

    def get_allowed_tools(self):
        return self._parse_json(self.allowed_tools)

    def get_blocked_tools(self):
        return self._parse_json(self.blocked_tools)

    def get_allowed_commands(self):
        return self._parse_json(self.allowed_commands)

    def get_blocked_commands(self):
        return self._parse_json(self.blocked_commands)

    @staticmethod
    def _parse_json(raw):
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []


class SandboxExecutionLog(Base):
    """AI 运维沙盒执行日志（模拟 vs 真实，全程审计）。"""
    __tablename__ = "sandbox_execution_logs"

    MODE_DRY_RUN = "dry_run"
    MODE_LIVE = "live"
    DECISION_ALLOWED = "allowed"
    DECISION_REJECTED = "rejected"
    DECISION_DRY_RUN = "dry_run"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, default=0)                                  # 关联会话 ID
    action_type = Column(String(32), default="")                             # restart/clean/scale/script/run_command
    tool_name = Column(String(64), default="")                               # MCP 工具名
    asset_id = Column(Integer, default=0)                                    # 目标资产 ID
    risk_level = Column(String(16), default="medium")
    mode = Column(String(8), default=MODE_LIVE)                              # dry_run / live
    payload = Column(Text, default="{}")                                     # 动作参数（JSON）
    decision = Column(String(16), default=DECISION_ALLOWED)                  # allowed / rejected / dry_run
    reject_reason = Column(String(255), default="")
    approved_by = Column(Integer, default=0)                                 # 审批人 ID
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
