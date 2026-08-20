from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool
from app.config import AIOPS_DB_URL, AIOPS_PG_URL
import os
import threading

# ── 双数据库：demo (展示) / real (真实测试) ──
# PG 为唯一生产路径; 开发/测试可通过 AIOPS_DB_URL 显式指向任意库(含 SQLite 内存库)。
# 所有连接串默认值统一在 app/config.py 中配置，通过 .env 文件覆盖。
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _get_db_url(mode: str) -> str:
    # 显式 AIOPS_DB_URL 优先; 否则走 AIOPS_PG_URL 生产默认。
    if AIOPS_DB_URL:
        return AIOPS_DB_URL
    return AIOPS_PG_URL


def _create_engine_for(mode: str):
    url = _get_db_url(mode)
    if _is_sqlite(url):
        # SQLite 内存库(:memory:)必须用 StaticPool 保持单一持久连接,
        # 否则每个新连接都是独立空库 → create_all 的表查不到(nested case)。
        # 文件型 SQLite 用 QueuePool; 增大 pool_size 应对后台工作流多线程。
        _wp = StaticPool if ":memory:" in url else None
        pool_kw = {}
        if not _wp:
            pool_kw["pool_size"] = 20
            pool_kw["max_overflow"] = 40
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=_wp,
            pool_pre_ping=True,
            pool_recycle=3600,
            **pool_kw,
        )

        @event.listens_for(eng, "connect")
        def _set_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.close()

        return eng

    # 生产数据库(Postgres/MySQL)：无 SQLite 专属参数
    # 连接池调大(pool_size=20/max_overflow=40 → 60)以应对后台大量并发服务一次性抢连,
    # 否则 asset_probe(SSH 探测 90s)/datasource_scrape 等长任务持有连接期间, 其余任务与 API 会
    # QueuePool limit reached → 全部转圈超时(惊群风暴)。与文件型 SQLite 池大小保持一致。
    try:
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=20,
            max_overflow=40,
        )
    except ModuleNotFoundError as _e:
        raise RuntimeError(
            f"连接 {url.split('@')[-1]} 失败: 缺少数据库驱动 {_e.name}. "
            f"请安装对应驱动, 如 Postgres: pip install psycopg2-binary"
        ) from _e

# 当前模式：demo / real，进程内全局状态（生产模式下两模式共用同一 URL）
_current_mode = "demo"
_mode_lock = threading.Lock()


def get_db_mode() -> str:
    return _current_mode


def set_db_mode(mode: str):
    global _current_mode
    with _mode_lock:
        _current_mode = mode


# 预建 engine，切换时零延迟；生产模式 demo/real 共享同一连接池
_engine_demo = _create_engine_for("demo")
_engine_real = _create_engine_for("real")
_engines = {"demo": _engine_demo, "real": _engine_real}

# 每个模式各自维护 SessionLocal 工厂
_SessionLocal_demo = sessionmaker(autocommit=False, autoflush=False, bind=_engine_demo)
_SessionLocal_real = sessionmaker(autocommit=False, autoflush=False, bind=_engine_real)
_SessionLocals = {"demo": _SessionLocal_demo, "real": _SessionLocal_real}


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖注入：根据当前模式返回对应数据库的 session"""
    db = _SessionLocals[_current_mode]()
    try:
        yield db
    finally:
        db.close()


def get_all_engines():
    """返回 {mode: engine}，用于建表、初始化等批量操作"""
    return _engines


def get_session_for(mode: str):
    """获取指定模式的 SessionLocal 工厂"""
    return _SessionLocals[mode]


def get_db_url_for(mode: str) -> str:
    """返回当前数据库连接 URL（用于诊断/展示）。"""
    return _get_db_url(mode)


# ── 方言安全迁移工具 ──────────────────────────────────────────
# 手写 SQLite 方言的 `ALTER TABLE ... ADD/DROP COLUMN` 在 PostgreSQL 上会导致:
#   1) 重复执行报 DuplicateColumn → `except: pass` 不回滚 → 事务被标记 aborted
#   2) 后续同一 session 的任何查询报 `current transaction is aborted`
# 这里封装成方言安全 + 幂等 + 独立事务(出错自动回滚)的工具, 供启动期兼容旧库列演进。
from sqlalchemy.orm import Session as _SA_Session
from sqlalchemy import text as _SA_text


def _dialect_name(db: "_SA_Session") -> str:
    return db.bind.dialect.name


def _pg_column_exists(db: "_SA_Session", table: str, column: str) -> bool:
    row = db.execute(_SA_text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).first()
    return row is not None


def _sqlite_column_exists(db: "_SA_Session", table: str, column: str) -> bool:
    rows = db.execute(_SA_text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def column_exists(db: "_SA_Session", table: str, column: str) -> bool:
    try:
        if _dialect_name(db) == "postgresql":
            return _pg_column_exists(db, table, column)
        return _sqlite_column_exists(db, table, column)
    except Exception:
        return False


def safe_add_columns(db: "_SA_Session", table: str, coldefs: "list[str]") -> None:
    """方言安全补列: PG 用 ADD COLUMN IF NOT EXISTS, SQLite 检查列存在跳过; 独立事务防污染。"""
    if _dialect_name(db) == "postgresql":
        for coldef in coldefs:
            colname = coldef.split()[0].strip().strip('"')
            try:
                db.execute(_SA_text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {coldef}'))
                db.commit()
            except Exception:
                db.rollback()
        return
    # SQLite: 保留原"列存在则跳过"语义
    for coldef in coldefs:
        colname = coldef.split()[0].strip().strip('"')
        try:
            if not _sqlite_column_exists(db, table, colname):
                db.execute(_SA_text(f"ALTER TABLE {table} ADD COLUMN {coldef}"))
            db.commit()
        except Exception:
            db.rollback()


def safe_drop_columns(db: "_SA_Session", table: str, columns: "list[str]") -> None:
    """方言安全删列: PG 用 ALTER TABLE DROP COLUMN IF EXISTS; SQLite 检查列存在才删。"""
    if _dialect_name(db) == "postgresql":
        for col in columns:
            try:
                db.execute(_SA_text(f'ALTER TABLE {table} DROP COLUMN IF EXISTS "{col}"'))
                db.commit()
            except Exception:
                db.rollback()
        return
    for col in columns:
        try:
            if _sqlite_column_exists(db, table, col):
                db.execute(_SA_text(f"ALTER TABLE {table} DROP COLUMN {col}"))
            db.commit()
        except Exception:
            db.rollback()


# ── 跨方言时间分组/格式化表达式 ──────────────────────────────
# SQLite 的 strftime()/date()/datetime() 在 PostgreSQL 上不存在(或语义不同)。
# 提供方言感知的时间分组与格式化, 供 SQLAlchemy 查询在双库共用。
from sqlalchemy import func as _func


def time_trunc_expr(db: "_SA_Session", column, granularity: "str"):
    """跨方言按小时/天/月截断时间并输出文本。
    granularity: 'hour' | 'day' | 'month'
    SQLite -> strftime(...); PostgreSQL -> to_char(date_trunc(...))"""
    if _dialect_name(db) == "postgresql":
        fmts = {"hour": "YYYY-MM-DD HH24:00", "day": "YYYY-MM-DD", "month": "YYYY-MM"}
        return _func.to_char(_func.date_trunc(granularity, column), fmts.get(granularity, "YYYY-MM-DD"))
    fmts = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}
    return _func.strftime(fmts.get(granularity, "%Y-%m-%d"), column)


def date_prefix_expr(db: "_SA_Session", column):
    """跨方言取日期前缀(YYYY-MM-DD): SQLite date() / PG to_char(date_trunc('day'))."""
    if _dialect_name(db) == "postgresql":
        return _func.to_char(column, "YYYY-MM-DD")
    return _func.date(column)


