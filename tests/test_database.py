"""database.py 双模式 + Postgres URL 生产模式支持测试。"""
import app.database as db


def test_default_is_sqlite():
    url = db.get_db_url_for("demo")
    assert url.startswith("sqlite:///")
    assert db._is_sqlite(url)


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


def test_url_isolation_demo_real(monkeypatch):
    monkeypatch.setattr(db, "_AIOPS_DB_URL", "")
    assert db._get_db_url("demo") != db._get_db_url("real")


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
