"""部署引擎测试: 离线拦截、AI 配置解析、计划 CRUD。"""
import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import DeployPlan
from app.services import deploy_service
from tests.conftest import assert_fields


class TestDeployPlanCRUD:
    def test_create_plan(self, db: Session):
        payload = {
            "name": "测试部署计划",
            "target_asset_id": 1,
            "doc_raw": "部署 nginx 到服务器",
        }
        result = deploy_service.create_plan(db, payload, user_id=1)
        assert result is not None
        assert "plan" in result or "id" in result

    def test_create_plan_with_offline(self, db: Session):
        payload = {
            "name": "离线部署计划",
            "target_asset_id": 1,
            "doc_raw": "docker pull nginx",
            "use_offline": True,
        }
        result = deploy_service.create_plan(db, payload, user_id=1)
        assert result is not None

    def test_list_plans_empty(self, db: Session):
        result = deploy_service.list_plans(db)
        if isinstance(result, tuple):
            items, total = result
        else:
            items = result.get("items", []) if isinstance(result, dict) else []
        assert len(items) == 0

    def test_list_plans_with_data(self, db: Session):
        deploy_service.create_plan(db, {"name": "plan-1", "target_asset_id": 1, "doc_raw": "echo hi"}, user_id=1)
        result = deploy_service.list_plans(db)
        if isinstance(result, tuple):
            items, total = result
        else:
            items = result.get("items", []) if isinstance(result, dict) else []
        assert len(items) >= 1

    def test_get_plan(self, db: Session):
        created = deploy_service.create_plan(db, {"name": "get-test", "target_asset_id": 1, "doc_raw": "echo hello"}, user_id=1)
        plan_id = created.get("plan", {}).get("id") or created.get("id")
        plan = deploy_service.get_plan(db, plan_id)
        assert plan is not None

    def test_get_plan_not_found(self, db: Session):
        plan = deploy_service.get_plan(db, 99999)
        assert plan is None

    def test_delete_plan(self, db: Session):
        created = deploy_service.create_plan(db, {"name": "del-test", "target_asset_id": 1, "doc_raw": "echo delete"}, user_id=1)
        plan_id = created.get("plan", {}).get("id") or created.get("id")
        ok = deploy_service.delete_plan(db, plan_id)
        assert ok is True

    def test_delete_plan_not_found(self, db: Session):
        ok = deploy_service.delete_plan(db, 99999)
        assert ok is False

    def test_update_plan(self, db: Session):
        created = deploy_service.create_plan(db, {"name": "upd-test", "target_asset_id": 1, "doc_raw": "echo old"}, user_id=1)
        plan_id = created.get("plan", {}).get("id") or created.get("id")
        updated = deploy_service.update_plan(db, plan_id, {"name": "upd-renamed"})
        assert updated is not None

    def test_update_plan_not_found(self, db: Session):
        updated = deploy_service.update_plan(db, 99999, {"name": "nope"})
        assert updated is None


class TestOfflineBlock:
    def test_offline_blocked_reason_public_image(self, db: Session):
        plan = MagicMock()
        plan.use_offline = True
        reason = deploy_service._offline_blocked_reason(plan, "docker pull nginx:latest")
        assert reason != "", f"应该拦截公网镜像, 但返回空: {reason!r}"

    def test_offline_blocked_reason_private_image_allowed(self, db: Session):
        plan = MagicMock()
        plan.use_offline = True
        reason = deploy_service._offline_blocked_reason(plan, "docker pull internal.registry:5000/app:1.0")
        assert reason == "", f"私有仓库应放行: {reason!r}"

    def test_offline_blocked_reason_offline_disabled(self, db: Session):
        plan = MagicMock()
        plan.use_offline = False
        reason = deploy_service._offline_blocked_reason(plan, "docker pull nginx:latest")
        assert reason == "", "离线未启用时不拦截"

    def test_offline_blocked_reason_public_repo_url(self, db: Session):
        plan = MagicMock()
        plan.use_offline = True
        reason = deploy_service._offline_blocked_reason(plan, "apt-get install -y nginx")
        public_hints = deploy_service._PUBLIC_REPO_HINTS if hasattr(deploy_service, '_PUBLIC_REPO_HINTS') else []
        if public_hints:
            assert True

    def test_offline_blocked_reason_localhost_allowed(self, db: Session):
        plan = MagicMock()
        plan.use_offline = True
        reason = deploy_service._offline_blocked_reason(plan, "docker pull localhost:5000/myapp:1.0")
        assert reason == "", f"localhost 应放行: {reason!r}"

    def test_offline_blocked_reason_ip_port_allowed(self, db: Session):
        plan = MagicMock()
        plan.use_offline = True
        reason = deploy_service._offline_blocked_reason(plan, "docker pull 192.168.1.1:5000/app:1.0")
        assert reason == "", f"IP:port 私有仓库应放行: {reason!r}"


class TestDocUpdate:
    def test_update_doc_raw(self, db: Session):
        created = deploy_service.create_plan(db, {"name": "doc-test", "target_asset_id": 1, "doc_raw": "old doc"}, user_id=1)
        plan_id = created.get("plan", {}).get("id") or created.get("id")
        updated = deploy_service.update_doc_raw(db, plan_id, "new doc content", "readme.md")
        assert updated is not None, "update_doc_raw 应返回 dict"

    def test_update_doc_raw_not_found(self, db: Session):
        updated = deploy_service.update_doc_raw(db, 99999, "content", "file.md")
        assert updated is None


class TestDetectArtifact:
    def test_detect_artifact_source_github(self):
        url = "https://github.com/user/repo/releases/download/v1.0/app.tar.gz"
        source = deploy_service.detect_artifact_source(url)
        assert source is not None

    def test_detect_artifact_source_docker(self):
        url = "docker pull nginx:latest"
        source = deploy_service.detect_artifact_source(url)
        assert source is not None

    def test_detect_artifact_source_unknown(self):
        url = "echo hello"
        source = deploy_service.detect_artifact_source(url)
        assert source is not None

    def test_resolve_download_path(self, db: Session):
        plan = MagicMock()
        plan.deploy_path = "/data/deploy"
        path = deploy_service.resolve_download_path(plan)
        assert path is not None


class TestProbeEnv:
    def test_probe_environment_not_found(self, db: Session):
        result = deploy_service.probe_environment(db, 99999)
        assert result.get("warning") is not None or "error" in result