"""域模型: agent (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class AIProvider(Base):
    """LLM 模型提供商配置"""
    __tablename__ = "ai_providers"

    PROVIDER_OPENAI = "openai_compatible"
    PROVIDER_CHOICES = [PROVIDER_OPENAI]

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    provider_type = Column(String(32), default=PROVIDER_OPENAI)
    base_url = Column(String(255), default="")
    api_key_encrypted = Column(Text, default="")
    default_model = Column(String(128), default="")
    temperature = Column(Float, default=0.2)
    max_tokens = Column(Integer, default=10000)
    timeout_seconds = Column(Integer, default=30)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def set_api_key(self, value):
        from cryptography.fernet import Fernet
        import hashlib, base64
        from app.config import PROVIDER_ENCRYPT_SEED
        value = (value or "").strip()
        if not value:
            self.api_key_encrypted = ""
            return
        seed = PROVIDER_ENCRYPT_SEED.encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
        self.api_key_encrypted = Fernet(key).encrypt(value.encode("utf-8")).decode("utf-8")

    def get_api_key(self):
        if not self.api_key_encrypted:
            return ""
        try:
            from cryptography.fernet import Fernet
            import hashlib, base64
            from app.config import PROVIDER_ENCRYPT_SEED
            seed = PROVIDER_ENCRYPT_SEED.encode("utf-8")
            key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
            return Fernet(key).decrypt(self.api_key_encrypted.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""


class SecretVault(Base):
    """集中凭据保险库：加密存储连接密码/Token/API Key，连接配置只存 {{secret:name}} 引用"""
    __tablename__ = "secret_vaults"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(String(256), default="")
    value_type = Column(String(32), default="password")
    scope = Column(String(64), default="global")
    secret_value_encrypted = Column(Text, default="")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AgentConfig(Base):
    """Agent 配置"""
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, default="default")
    default_provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    system_prompt = Column(Text, default="")
    welcome_message = Column(String(255), default="你好，我可以帮你查询资源、分析告警、生成运维任务等。")
    suggested_questions = Column(Text, default="[]")
    is_enabled = Column(Boolean, default=True)
    allow_action_execution = Column(Boolean, default=True)
    require_confirmation = Column(Boolean, default=True)
    max_history_messages = Column(Integer, default=12)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_suggested_questions(self):
        try:
            return json.loads(self.suggested_questions) if self.suggested_questions else []
        except (json.JSONDecodeError, TypeError):
            return []


class SubAgent(Base):
    """子智能体（Sub-agent）定义 — 按域分派的专家 Agent。

    Coordinator Agent 根据用户消息关键词路由到对应子专家，
    子专家使用专属 system_prompt + 工具白名单，实现 Multi-Agent Orchestration。
    domain 取值: sre / network / database / middleware / k8s / general
    """
    __tablename__ = "sub_agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)          # 如 "sre_expert"
    display_name = Column(String(128), default="")                   # 如 "SRE 可靠性专家"
    domain = Column(String(32), nullable=False)                      # sre/network/database/middleware/k8s/general
    description = Column(Text, default="")
    system_prompt = Column(Text, default="")
    tool_whitelist = Column(Text, default="[]")                      # JSON 数组，工具名白名单；空数组=继承全部工具
    keywords = Column(Text, default="[]")                            # JSON 数组，路由关键词
    icon = Column(String(16), default="🤖")                          # 前端展示图标
    color = Column(String(16), default="#6366f1")                    # 前端展示颜色
    is_enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_tool_whitelist(self):
        try:
            return json.loads(self.tool_whitelist) if self.tool_whitelist else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_keywords(self):
        try:
            return json.loads(self.keywords) if self.keywords else []
        except (json.JSONDecodeError, TypeError):
            return []


class ChatSession(Base):
    """AI 会话"""
    __tablename__ = "chat_sessions"

    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"

    MODE_AGENT = "agent"
    MODE_CHAT = "chat"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(128), default="新会话")
    status = Column(String(16), default=STATUS_ACTIVE)
    context = Column(Text, default="{}")
    last_message_at = Column(DateTime, default=lambda: datetime.now())
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    provider_id = Column(Integer, nullable=True)
    mode = Column(String(16), default=MODE_AGENT)
    linked_asset_ids = Column(Text, default="[]")
    sub_agent = Column(String(64), default="auto")  # auto/sre/network/database/middleware/k8s/general


class ChatMessage(Base):
    """会话消息"""
    __tablename__ = "chat_messages"

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"

    TYPE_TEXT = "text"
    TYPE_ANALYSIS = "analysis"
    TYPE_ACTION = "action"
    TYPE_ERROR = "error"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(16), nullable=False)
    message_type = Column(String(16), default=TYPE_TEXT)
    message_content = Column(Text, default="")
    citations = Column(Text, default="[]")
    tool_calls = Column(Text, default="[]")
    metadata_json = Column("metadata", Text, default="{}")
    sub_agent = Column(String(64), default="")  # 该消息归属的子智能体（空=会话默认）
    created_at = Column(DateTime, default=lambda: datetime.now())


class MCPServer(Base):
    """MCP 服务注册"""
    __tablename__ = "mcp_servers"

    TYPE_HTTP = "http"
    TYPE_PLATFORM_BUILTIN = "platform_builtin"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    server_type = Column(String(16), default=TYPE_PLATFORM_BUILTIN)
    endpoint = Column(String(255), default="")
    description = Column(String(255), default="")
    auth_config = Column(Text, default="{}")
    tool_whitelist = Column(Text, default="[]")
    is_builtin = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class PendingAction(Base):
    """待确认动作"""
    __tablename__ = "pending_actions"

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"

    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_EXECUTING = "executing"
    STATUS_CANCELED = "canceled"
    STATUS_EXECUTED = "executed"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    run_id = Column(Integer, nullable=True)
    node_run_id = Column(Integer, nullable=True)
    action_type = Column(String(64), nullable=False)
    title = Column(String(128), default="")
    risk_level = Column(String(16), default=RISK_LOW)
    reason = Column(String(500), nullable=True)
    status = Column(String(16), default=STATUS_PENDING)
    action_payload = Column(Text, default="{}")
    result_payload = Column(Text, default="{}")
    review_result = Column(Text, default="")  # A4: LLM reviewer 二签结果 JSON
    confirmed_by = Column(String(64), default="")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ToolInvocation(Base):
    """工具调用记录"""
    __tablename__ = "tool_invocations"

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    tool_name = Column(String(64), nullable=False)
    status = Column(String(16), default=STATUS_PENDING)
    latency_ms = Column(Integer, default=0)
    request_payload = Column(Text, default="{}")
    response_summary = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())


class BackgroundJob(Base):
    """后台异步任务状态追踪（支持长耗时任务如安装、部署）"""
    __tablename__ = "background_jobs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)  # UUID，供外部轮询
    action_type = Column(String(64), nullable=False)  # install_package / run_command / restart_service 等
    title = Column(String(128), default="")
    status = Column(String(16), default=STATUS_PENDING)  # pending / running / success / failed / canceled
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(256), default="")  # 当前步骤描述
    result_payload = Column(Text, default="{}")  # JSON 最终结果
    error_message = Column(String(512), default="")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    pending_action_id = Column(Integer, ForeignKey("pending_actions.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class AgentEvaluation(Base):
    __tablename__ = "agent_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    provider_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(64), default="")
    task_type = Column(String(32), default="chat")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    round_count = Column(Integer, default=0)
    tool_call_count = Column(Integer, default=0)
    is_success = Column(Boolean, default=True)
    has_hallucination = Column(Boolean, default=False)
    completion_rate = Column(Float, default=1.0)
    feedback = Column(String(16), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


class ABTestConfig(Base):
    __tablename__ = "ab_test_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    provider_a_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    provider_b_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=True)
    model_a = Column(String(64), default="")
    model_b = Column(String(64), default="")
    split_ratio = Column(String(8), default="50/50")
    metric = Column(String(32), default="latency")
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class ABTestRecord(Base):
    __tablename__ = "ab_test_records"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("ab_test_configs.id"), nullable=True, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    group = Column(String(8), default="a")
    provider_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(64), default="")
    latency_ms = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    is_success = Column(Boolean, default=True)
    user_feedback = Column(String(16), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)


class AgentGroundTruth(Base):
    """Agent 评估 GroundTruth 测试集"""
    __tablename__ = "agent_ground_truths"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    category = Column(String(32), default="qa")           # qa / tool_call / rag / reasoning
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, default="")
    expected_tools = Column(Text, default="[]")           # JSON array of expected tool names
    tags = Column(String(256), default="")
    difficulty = Column(String(16), default="medium")     # easy / medium / hard
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AgentGroundTruthRun(Base):
    """GroundTruth 测试执行记录"""
    __tablename__ = "agent_ground_truth_runs"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("agent_ground_truths.id"), nullable=False, index=True)
    session_id = Column(Integer, nullable=True)
    provider_id = Column(Integer, nullable=True)
    model_name = Column(String(64), default="")
    actual_answer = Column(Text, default="")
    actual_tools = Column(Text, default="[]")
    answer_score = Column(Float, default=0.0)             # 语义相似度 0~1
    tool_score = Column(Float, default=0.0)               # 工具调用匹配度 0~1
    total_score = Column(Float, default=0.0)              # 综合评分
    latency_ms = Column(Integer, default=0)
    error = Column(String(512), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class AutonomousCycle(Base):
    """自主 AI Agent 巡检闭环记录。"""
    __tablename__ = "autonomous_cycles"

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(String(36), default=lambda: str(uuid.uuid4()), index=True)
    status = Column(String(16), default=STATUS_RUNNING)
    phase = Column(String(16), default="perceive")  # perceive / analyze / act / verify
    summary = Column(String(500), default="")
    detail = Column(Text, default="")
    issues_found = Column(Text, default="[]")        # JSON: [{asset_id, metric, severity, description}]
    actions_taken = Column(Text, default="[]")        # JSON: [{action_type, asset_id, command, result, success}]
    llm_analysis = Column(Text, default="")           # LLM 原始分析输出
    error_message = Column(String(500), default="")
    asset_count = Column(Integer, default=0)
    issue_count = Column(Integer, default=0)
    action_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(), index=True)
    finished_at = Column(DateTime, nullable=True)


class AIInsightRecord(Base):
    """AI 分析历史记录沉淀 - 跨指标/日志/链路三页"""
    __tablename__ = "ai_insight_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, default=0)
    source_type = Column(String(16), nullable=False, index=True)  # metrics / logs / traces
    title = Column(String(256), default="")
    question = Column(Text, default="")
    analysis = Column(Text, default="")
    meta_json = Column(Text, default="{}")  # {provider, metric_count, source_name, trend_data, etc}
    provider = Column(String(64), default="")
    score = Column(Integer, default=0)  # 0-100 AI 自评分数
    created_at = Column(DateTime, default=lambda: datetime.now())
