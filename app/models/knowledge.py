"""域模型: knowledge (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text

from app.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    symptom = Column(Text, default="")
    root_cause = Column(Text, default="")
    solution = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    source_type = Column(String(32), default="manual")
    sop_steps = Column(Text, default="[]")
    version_number = Column(Integer, default=1)
    change_log = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class AlertKbLink(Base):
    __tablename__ = "alert_kb_links"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    kb_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)


class Runbook(Base):
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    category = Column(String(64), default="general")
    symptom = Column(Text, default="")
    diagnosis = Column(Text, default="")
    steps = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class KbDocument(Base):
    """知识库文档（支持上传 md/txt/pdf/docx，可关联 KnowledgeBase 条目或独立存在）"""
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=True)
    title = Column(String(256), nullable=False)
    source_type = Column(String(32), default="manual")   # manual / upload / alert_case / incident_case
    file_path = Column(String(512), default="")          # 上传文件原始存储路径
    file_ext = Column(String(16), default="")            # 文件扩展名 md/txt/pdf/docx
    content = Column(Text, default="")                   # 全文内容
    chunk_count = Column(Integer, default=0)             # 切片数量
    status = Column(String(32), default="pending")       # pending / indexed / failed
    tags = Column(String(256), default="")
    asset_type = Column(String(32), default="")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)  # 关联具体资产（部署报告用）
    severity = Column(String(32), default="warning")
    index_engine = Column(String(16), default="v1")        # v1 / v2 / both（标识索引归属引擎）
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class KbChunk(Base):
    """文档切片 + 向量索引（embedding 存 JSON 字符串，兼容 SQLite；升级 pgvector 后改 vector 类型）"""
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)        # 切片序号
    content = Column(Text, nullable=False)               # 切片文本
    embedding = Column(Text, default="")                 # 向量 JSON 字符串
    embedding_mode = Column(String(32), default="tfidf") # tfidf / provider
    token_count = Column(Integer, default=0)
    tags = Column(String(256), default="")
    asset_type = Column(String(32), default="")
    severity = Column(String(32), default="warning")
    created_at = Column(DateTime, default=lambda: datetime.now())


class KnowledgeDraft(Base):
    __tablename__ = "knowledge_drafts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    symptom = Column(Text, default="")
    root_cause = Column(Text, default="")
    solution = Column(Text, default="")
    tags = Column(String(256), default="")
    severity = Column(String(32), default="warning")
    asset_type = Column(String(32), default="")
    source_data = Column(Text, default="")
    source_type = Column(String(32), default="auto")
    sop_steps = Column(Text, default="[]")
    status = Column(String(16), default="pending")
    reject_reason = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
