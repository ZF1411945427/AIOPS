from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
import threading

# ── 双数据库：demo (展示) / real (真实测试) ──
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
_DEMO_DB = os.path.join(_DB_DIR, "aiops.db")        # 原始 demo 数据
_REAL_DB = os.path.join(_DB_DIR, "aiops_real.db")   # 真实测试数据

# 生产模式：AIOPS_DB_URL 指向 Postgres/MySQL 等，覆盖 SQLite 双库。
# 例：postgresql://user:pass@host:5432/aiops
_AIOPS_DB_URL = os.environ.get("AIOPS_DB_URL", "").strip()


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _get_db_url(mode: str) -> str:
    if _AIOPS_DB_URL:
        return _AIOPS_DB_URL
    path = _DEMO_DB if mode == "demo" else _REAL_DB
    return f"sqlite:///{path}"


def _create_engine_for(mode: str):
    url = _get_db_url(mode)
    if _is_sqlite(url):
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        @event.listens_for(eng, "connect")
        def _set_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.close()

        return eng

    # 生产数据库(Postgres/MySQL)：无 SQLite 专属参数
    try:
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
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
