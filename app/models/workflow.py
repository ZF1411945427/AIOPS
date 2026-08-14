"""域模型: workflow (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class WorkflowTemplate(Base):
    """SOP 工作流模板（可复用的运维剧本，DAG 节点编排）"""
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(64), default="generic")
    trigger_type = Column(String(32), default="manual")
    trigger_condition = Column(Text, default="")
    nodes = Column(Text, default="[]")
    edges = Column(Text, default="[]")
    risk_level = Column(String(32), default="medium")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_nodes(self):
        try:
            return json.loads(self.nodes) if self.nodes else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_edges(self):
        try:
            return json.loads(self.edges) if self.edges else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_trigger_condition(self):
        try:
            return json.loads(self.trigger_condition) if self.trigger_condition else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowRun(Base):
    """工作流执行实例"""
    __tablename__ = "workflow_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_ABORTED = "aborted"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    title = Column(String(256), nullable=False)
    status = Column(String(32), default=STATUS_PENDING)
    context = Column(Text, default="{}")
    trigger_source = Column(String(32), default="ai")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_context(self):
        try:
            return json.loads(self.context) if self.context else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowNodeRun(Base):
    """节点执行记录"""
    __tablename__ = "workflow_node_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=False)
    node_name = Column(String(128), default="")
    action_type = Column(String(64), nullable=False)
    payload = Column(Text, default="{}")
    status = Column(String(32), default=STATUS_PENDING)
    result = Column(Text, default="")
    requires_confirm = Column(Boolean, default=False)
    pending_action_id = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_payload(self):
        try:
            return json.loads(self.payload) if self.payload else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_result(self):
        try:
            return json.loads(self.result) if self.result else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class AgentWorkflow(Base):
    """智能体工作流编排定义（可视化画布拖拽生成）"""
    __tablename__ = "agent_workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(64), default="generic")
    nodes = Column(Text, default="[]")
    edges = Column(Text, default="[]")
    inputs_schema = Column(Text, default="[]")
    outputs_schema = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    published = Column(Boolean, default=False)
    trigger_type = Column(String(32), default="manual")
    trigger_condition = Column(Text, default="{}")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    def get_nodes(self):
        try:
            return json.loads(self.nodes) if self.nodes else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_edges(self):
        try:
            return json.loads(self.edges) if self.edges else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_inputs_schema(self):
        try:
            return json.loads(self.inputs_schema) if self.inputs_schema else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_outputs_schema(self):
        try:
            return json.loads(self.outputs_schema) if self.outputs_schema else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_trigger_condition(self):
        """告警触发条件（JSON）。空/非法返回 {}（= 匹配所有告警）。"""
        try:
            return json.loads(self.trigger_condition) if self.trigger_condition else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class AgentWorkflowRun(Base):
    """智能体工作流执行实例"""
    __tablename__ = "agent_workflow_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_ABORTED = "aborted"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("agent_workflows.id"), nullable=True)
    workflow_snapshot = Column(Text, default="{}")
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    status = Column(String(32), default=STATUS_PENDING)
    inputs = Column(Text, default="{}")
    runtime_context = Column(Text, default="{}")
    outputs = Column(Text, default="{}")
    trigger_source = Column(String(32), default="api")
    error = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    triggered_by = Column(String(64), default="")

    def get_workflow_snapshot(self):
        try:
            return json.loads(self.workflow_snapshot) if self.workflow_snapshot else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_inputs(self):
        try:
            return json.loads(self.inputs) if self.inputs else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_runtime_context(self):
        try:
            return json.loads(self.runtime_context) if self.runtime_context else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_outputs(self):
        try:
            return json.loads(self.outputs) if self.outputs else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class AgentWorkflowNodeRun(Base):
    """智能体工作流节点执行记录"""
    __tablename__ = "agent_workflow_node_runs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_AWAITING_CONFIRM = "awaiting_confirm"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("agent_workflow_runs.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=False)
    node_type = Column(String(32), nullable=False)
    node_name = Column(String(128), default="")
    run_config = Column(Text, default="{}")
    status = Column(String(32), default=STATUS_PENDING)
    output = Column(Text, default="{}")
    error = Column(Text, default="")
    requires_confirm = Column(Boolean, default=False)
    pending_action_id = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())

    def get_config(self):
        try:
            return json.loads(self.run_config) if self.run_config else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_output(self):
        try:
            return json.loads(self.output) if self.output else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class WorkflowAuditLog(Base):
    """智能体工作流操作审计日志（不可抵赖）"""
    __tablename__ = "workflow_audit_logs"

    ACTION_RUN_START = "run_start"
    ACTION_NODE_AUTO_EXEC = "node_auto_exec"
    ACTION_NODE_CONFIRM = "node_confirm"
    ACTION_NODE_CANCEL = "node_cancel"
    ACTION_RUN_ABORT = "run_abort"
    ACTION_NODE_RETRY = "node_retry"
    ACTION_NODE_FORCE_CONFIRM = "node_force_confirm"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    node_run_id = Column(Integer, nullable=True)
    workflow_id = Column(Integer, nullable=True)
    action = Column(String(32), nullable=False)
    operator = Column(String(64), default="")
    tool_name = Column(String(64), default="")
    execution_mode = Column(String(16), default="")
    risk_level = Column(String(16), default="")
    detail = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now())
