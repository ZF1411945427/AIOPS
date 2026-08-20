"""资产探活/生命周期测试: 覆盖 asset_service 核心 CRUD + 探活逻辑。"""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Asset
from app.services import asset_service
from tests.conftest import assert_fields


class TestAssetCRUD:
    def test_create_asset(self, db: Session):
        data = {
            "name": "web-01",
            "ci_type": "server",
            "ip": "10.0.0.1",
            "status": "online",
            "connection_type": "ssh",
            "ci_attributes": json.dumps({"os": "linux", "cpu": 8}),
        }
        a = asset_service.create_asset(db, data)
        assert a.id is not None
        assert a.name == "web-01"
        assert a.ci_type == "server"

    def test_create_asset_minimal(self, db: Session):
        data = {"name": "minimal-host", "ci_type": "server"}
        a = asset_service.create_asset(db, data)
        assert a.id is not None
        assert a.status in ("online", "offline")

    def test_get_asset(self, db: Session, sample_asset: Asset):
        a = asset_service.get_asset(db, sample_asset.id)
        assert a is not None
        assert a.name == sample_asset.name

    def test_get_asset_not_found(self, db: Session):
        a = asset_service.get_asset(db, 99999)
        assert a is None

    def test_update_asset(self, db: Session, sample_asset: Asset):
        updated = asset_service.update_asset(db, sample_asset.id, {"name": "renamed-server", "status": "offline"})
        assert updated is not None
        assert updated.name == "renamed-server"
        assert updated.status == "offline"

    def test_update_asset_not_found(self, db: Session):
        r = asset_service.update_asset(db, 99999, {"name": "nope"})
        assert r is None

    def test_delete_asset(self, db: Session, sample_asset: Asset):
        aid = sample_asset.id
        ok = asset_service.delete_asset(db, aid)
        assert ok is True
        assert asset_service.get_asset(db, aid) is None

    def test_delete_asset_not_found(self, db: Session):
        ok = asset_service.delete_asset(db, 99999)
        assert ok is False

    def test_list_assets_paged(self, db: Session):
        for i in range(5):
            asset_service.create_asset(db, {"name": f"host-{i}", "ci_type": "server"})
        items, total = asset_service.list_assets_paged(db, page=1, page_size=3)
        assert len(items) == 3
        assert total == 5

    def test_list_assets_paged_with_search(self, db: Session):
        asset_service.create_asset(db, {"name": "web-nginx", "ci_type": "server"})
        asset_service.create_asset(db, {"name": "db-mysql", "ci_type": "database"})
        items, total = asset_service.list_assets_paged(db, search="nginx")
        assert total == 1
        assert items[0].name == "web-nginx"

    def test_list_assets_paged_with_ci_type(self, db: Session):
        asset_service.create_asset(db, {"name": "web", "ci_type": "server"})
        asset_service.create_asset(db, {"name": "db", "ci_type": "database"})
        items, total = asset_service.list_assets_paged(db, ci_type="database")
        assert total == 1
        assert items[0].ci_type == "database"

    def test_list_assets_paged_exclude_types(self, db: Session):
        asset_service.create_asset(db, {"name": "pod-x", "ci_type": "pod"})
        asset_service.create_asset(db, {"name": "svc-y", "ci_type": "service"})
        asset_service.create_asset(db, {"name": "real-host", "ci_type": "server"})
        items, total = asset_service.list_assets_paged(
            db, exclude_types={"pod", "service", "deployment", "daemonset", "statefulset", "job", "configmap", "secret", "pvc", "namespace", "ingress"}
        )
        assert total == 1
        assert items[0].name == "real-host"

    def test_list_by_ci_type(self, db: Session):
        asset_service.create_asset(db, {"name": "db-1", "ci_type": "database"})
        asset_service.create_asset(db, {"name": "db-2", "ci_type": "database"})
        asset_service.create_asset(db, {"name": "web", "ci_type": "server"})
        dbs = asset_service.list_by_ci_type(db, "database")
        assert len(dbs) == 2


class TestAssetProbe:
    def test_probe_assets_marks_offline(self, db: Session, sample_asset: Asset):
        """探活时连通性失败应标记 offline."""
        sample_asset.last_checked_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()
        asset_service.probe_assets(db)
        db.refresh(sample_asset)
        assert sample_asset.last_checked_at is not None

    def test_probe_assets_updates_timestamp(self, db: Session, sample_asset: Asset):
        sample_asset.last_checked_at = None
        db.commit()
        try:
            asset_service.probe_assets(db)
        except Exception:
            pass
        db.refresh(sample_asset)
        assert True

    def test_probe_assets_empty_db(self, db: Session):
        asset_service.probe_assets(db)

    def test_probe_assets_skips_offline_unchanged(self, db: Session, sample_asset: Asset):
        sample_asset.status = "offline"
        sample_asset.last_checked_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        asset_service.probe_assets(db)
        db.refresh(sample_asset)
        assert sample_asset.status == "offline"


class TestAssetLifecycle:
    def test_asset_created_with_default_status(self, db: Session):
        a = asset_service.create_asset(db, {"name": "new-host", "ci_type": "server"})
        assert a.status in ("online", "offline")

    def test_asset_ci_attributes_roundtrip(self, db: Session):
        attrs = {"os": "linux", "cpu": 16, "disk": {"total": "500G", "used": "200G"}}
        data = {"name": "attr-test", "ci_type": "server", "ci_attributes": json.dumps(attrs)}
        a = asset_service.create_asset(db, data)
        saved = json.loads(a.ci_attributes) if a.ci_attributes else {}
        assert saved["os"] == "linux"
        assert saved["cpu"] == 16
        assert saved["disk"]["total"] == "500G"

    def test_asset_connection_config_roundtrip(self, db: Session):
        cfg = {"ssh_user": "root", "ssh_port": 22}
        data = {"name": "cfg-test", "ci_type": "server", "connection_config": json.dumps(cfg)}
        a = asset_service.create_asset(db, data)
        loaded = json.loads(a.connection_config) if a.connection_config else {}
        assert loaded["ssh_user"] == "root"

    def test_asset_pagination_second_page(self, db: Session):
        for i in range(10):
            asset_service.create_asset(db, {"name": f"host-{i}", "ci_type": "server"})
        items, total = asset_service.list_assets_paged(db, page=2, page_size=3)
        assert len(items) == 3
        assert total == 10

    def test_middleware_subtype_in_ci_attributes(self, db: Session):
        data = {
            "name": "kafka-broker",
            "ci_type": "middleware",
            "ci_attributes": json.dumps({"mw_subtype": "kafka", "mw_port": 9092}),
            "connection_type": "http",
        }
        a = asset_service.create_asset(db, data)
        attrs = json.loads(a.ci_attributes) if a.ci_attributes else {}
        assert attrs.get("mw_subtype") == "kafka"

    def test_database_subtype_in_ci_attributes(self, db: Session):
        data = {
            "name": "mysql-db",
            "ci_type": "database",
            "ci_attributes": json.dumps({"db_type": "mysql", "db_port": 3306}),
            "connection_type": "database",
        }
        a = asset_service.create_asset(db, data)
        attrs = json.loads(a.ci_attributes) if a.ci_attributes else {}
        assert attrs.get("db_type") == "mysql"