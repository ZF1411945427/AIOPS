"""database.py 双模式 + PG 默认生产路径支持测试。"""
import app.database as db


def test_default_is_postgres(monkeypatch):
    """解耦铁律: 未显式指定 AIOPS_DB_URL 时, 默认连接 PostgreSQL 生产库(不再回退 SQLite 文件)。"""
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "")
    monkeypatch.setattr(db, "_DEFAULT_PG_URL", "postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops")
    url = db.get_db_url_for("demo")
    assert url.startswith("postgresql://")
    assert not db._is_sqlite(url)


def test_mode_switch_engines():
    engines = db.get_all_engines()
    assert set(engines.keys()) == {"demo", "real"}
    db.set_db_mode("real")
    assert db.get_db_mode() == "real"
    db.set_db_mode("demo")


def test_aiopps_db_url_override(monkeypatch):
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "postgresql://u:p@db:5432/aiops")
    assert db.get_db_url_for("demo") == "postgresql://u:p@db:5432/aiops"
    assert db.get_db_url_for("real") == "postgresql://u:p@db:5432/aiops"
    assert not db._is_sqlite(db.get_db_url_for("demo"))


def test_sqlite_explicit_in_memory(monkeypatch):
    """测试/CI 显式指定 SQLite 内存库仍可用(双轨兼容, 不影响生产)。"""
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "sqlite:///:memory:")
    assert db.get_db_url_for("demo") == "sqlite:///:memory:"
    assert db._is_sqlite(db.get_db_url_for("demo"))


def test_pg_engine_is_postgresql(monkeypatch):
    """默认(未设 AIOPS_DB_URL 且无 SQLite 覆盖)engine 方言应为 PG。"""
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "")
    monkeypatch.setattr(db, "_DEFAULT_PG_URL", "postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops")
    eng = db._create_engine_for("demo")
    assert eng.dialect.name == "postgresql"
    assert "postgresql://" in str(eng.url)


def test_missing_driver_clear_error(monkeypatch):
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "postgresql://u:p@db:5432/aiops")

    def _fake_create_engine(*a, **k):
        raise ModuleNotFoundError("No module named 'psycopg2'")

    monkeypatch.setattr(db, "create_engine", _fake_create_engine)
    try:
        db._create_engine_for("demo")
    except RuntimeError as e:
        assert "psycopg2" in str(e)
    else:
        raise AssertionError("缺少驱动时应抛清晰 RuntimeError")