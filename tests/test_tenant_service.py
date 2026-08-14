"""租户服务单测: 默认租户守卫 / CRUD / 序列化。
"""
from types import SimpleNamespace
from datetime import datetime

from app.services import tenant_service


def _tenant(**kw):
    base = dict(id=1, name="默认租户", code="default", status="active",
                quota_assets=10000, quota_users=1000,
                created_at=datetime(2026, 1, 1, 0, 0, 0), updated_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


class FakeDB:
    """最小 fake db: 内存行列表 + add/commit/refresh/delete 记录。"""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.deleted = []
        self.commits = 0

    def query(self, model):
        return FakeQuery(self.rows)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)
        if obj in self.rows:
            self.rows.remove(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        obj.id = getattr(obj, "id", None) or 1


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **k):
        return FakeQuery(self._rows)

    def order_by(self, *a, **k):
        return FakeQuery(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


def test_get_or_create_returns_existing():
    db = FakeDB([_tenant(id=5)])
    t = tenant_service.get_or_create_default_tenant(db)
    assert t.id == 5
    assert db.commits == 0  # 已有则不开新


def test_get_or_create_creates_default():
    db = FakeDB([])
    t = tenant_service.get_or_create_default_tenant(db)
    assert t.id == 1
    assert db.commits == 1
    assert db.added[0].code == "default"


def test_ensure_tenant_exists():
    assert tenant_service.ensure_tenant_exists(FakeDB([_tenant()]), 1) is True
    assert tenant_service.ensure_tenant_exists(FakeDB([]), 1) is False


def test_list_tenants_serializes():
    rows = [_tenant(id=1, code="a"), _tenant(id=2, code="b")]
    out = tenant_service.list_tenants(FakeDB(rows))
    assert [t["code"] for t in out] == ["a", "b"]


def test_get_tenant_returns_dict_or_none():
    assert tenant_service.get_tenant(FakeDB([_tenant()]), 1)["code"] == "default"
    assert tenant_service.get_tenant(FakeDB([]), 99) is None


def test_create_tenant():
    db = FakeDB([])
    out = tenant_service.create_tenant(db, {"name": "新租户", "code": "new", "quota_assets": 500})
    assert out["code"] == "new"
    assert out["quota_assets"] == 500
    assert db.added[0].name == "新租户"


def test_update_tenant_partial():
    db = FakeDB([_tenant()])
    out = tenant_service.update_tenant(db, 1, {"name": "改名", "status": "disabled"})
    assert out["name"] == "改名"
    assert out["status"] == "disabled"
    assert out["code"] == "default"  # 未改字段保留


def test_update_tenant_missing_returns_none():
    assert tenant_service.update_tenant(FakeDB([]), 9, {"name": "x"}) is None


def test_delete_default_tenant_forbidden():
    db = FakeDB([_tenant(id=1)])
    assert tenant_service.delete_tenant(db, 1) is False
    assert len(db.deleted) == 0


def test_delete_tenant():
    db = FakeDB([_tenant(id=2, code="x")])
    assert tenant_service.delete_tenant(db, 2) is True
    assert len(db.deleted) == 1


def test_tenant_mode_enabled(monkeypatch):
    monkeypatch.setattr(tenant_service, "get_config", lambda db, k, d: "true")
    assert tenant_service.is_tenant_mode_enabled(None) is True
    monkeypatch.setattr(tenant_service, "get_config", lambda db, k, d: "false")
    assert tenant_service.is_tenant_mode_enabled(None) is False
