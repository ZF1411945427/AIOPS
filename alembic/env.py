from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# ── AIOps 项目适配 ──────────────────────────────────────────
# 接入项目全部 SQLAlchemy 模型(Base.metadata 聚合, 与 app/main.py 的 create_all 同源)
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  (触发全部模型注册)

# 迁移目标: 与 app/main.py create_all 使用同一 metadata, 双轨不打架
target_metadata = Base.metadata

# 数据库 URL 优先环境变量 AIOPS_DB_URL, 缺省回退 demo SQLite 库
_DEFAULT_DB_URL = (
    f"sqlite:///{_PROJECT_ROOT / 'db' / 'aiops.db'}"
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# sqlalchemy.url 由环境变量覆盖(不在 ini 写死生产地址)
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("AIOPS_DB_URL", _DEFAULT_DB_URL).replace("%", "%%"),
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    url = config.get_main_option("sqlalchemy.url")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
