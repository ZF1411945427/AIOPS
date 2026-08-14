"""域模型: skill (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from app.database import Base


class Skill(Base):
    """技能(SKILL.md)注册表 - 对齐 Ongrid internal/skill + biz/skill(F1)。"""
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True)  # frontmatter.name, use_skill 入参名
    description = Column(String(512), default="")
    version = Column(String(32), default="1.0.0")
    author = Column(String(128), default="")
    license = Column(String(64), default="")
    category = Column(String(64), default="")
    risk_level = Column(String(32), default="read_only")  # read_only / interactive / danger
    keywords = Column(Text, default="[]")      # JSON list
    tools_required = Column(Text, default="[]")  # JSON list of MCP tool names
    content = Column(Text, default="")          # SKILL.md 全文(frontmatter + 正文)
    source = Column(String(32), default="builtin")  # builtin / upload / marketplace
    file_path = Column(String(512), default="")     # builtin 相对路径
    enabled = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


class SkillExecution(Base):
    """技能执行审计 - use_skill/manual 触发记录(F1 可审计执行)。"""
    __tablename__ = "skill_executions"
    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, index=True)
    skill_name = Column(String(128), default="", index=True)
    tool = Column(String(64), default="use_skill")  # use_skill / manual
    status = Column(String(16), default="success")  # success / failed
    input_summary = Column(Text, default="")
    output_summary = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    executed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
