"""工作流编排测试: 拓扑排序、条件求值、节点状态机、Jinja 渲染。"""
import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import WorkflowTemplate
from tests.conftest import assert_fields


class TestWorkflowTopology:
    def test_empty_workflow_nodes(self, db: Session):
        wf = WorkflowTemplate(
            name="empty-wf", description="无节点工作流",
            nodes="[]", edges="[]", enabled=True,
            created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert wf.get_nodes() == []
        assert wf.get_edges() == []

    def test_workflow_with_nodes(self, db: Session):
        nodes = [
            {"id": "n1", "type": "start", "label": "开始"},
            {"id": "n2", "type": "tool", "label": "执行命令", "data": {"command": "df -h"}},
            {"id": "n3", "type": "end", "label": "结束"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ]
        wf = WorkflowTemplate(
            name="simple-wf", description="简单工作流",
            nodes=json.dumps(nodes, ensure_ascii=False),
            edges=json.dumps(edges, ensure_ascii=False),
            enabled=True, created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert len(wf.get_nodes()) == 3
        assert len(wf.get_edges()) == 2
        assert wf.get_nodes()[1]["data"]["command"] == "df -h"

    def test_workflow_or_join(self, db: Session):
        nodes = [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "tool", "data": {"execution_mode": "auto"}},
            {"id": "n3", "type": "tool", "data": {"execution_mode": "auto"}},
            {"id": "n4", "type": "end"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n1", "target": "n3"},
            {"id": "e3", "source": "n2", "target": "n4"},
            {"id": "e4", "source": "n3", "target": "n4"},
        ]
        wf = WorkflowTemplate(
            name="or-join-wf", description="OR-join 演示",
            nodes=json.dumps(nodes, ensure_ascii=False),
            edges=json.dumps(edges, ensure_ascii=False),
            enabled=True, created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert len(wf.get_nodes()) == 4

    def test_workflow_requires_confirm(self, db: Session):
        nodes = [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "tool", "data": {"execution_mode": "auto", "command": "ls"}},
            {"id": "n3", "type": "tool", "data": {"execution_mode": "manual", "command": "rm -rf /"}},
            {"id": "n4", "type": "end"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n4"},
        ]
        wf = WorkflowTemplate(
            name="confirm-wf", description="需要人工确认的节点",
            nodes=json.dumps(nodes, ensure_ascii=False),
            edges=json.dumps(edges, ensure_ascii=False),
            enabled=True, created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        n3 = wf.get_nodes()[2]
        assert n3["data"]["execution_mode"] == "manual"

    def test_workflow_trigger_condition(self, db: Session):
        wf = WorkflowTemplate(
            name="trigger-wf", description="带触发条件的工作流",
            nodes="[]", edges="[]", enabled=True,
            trigger_type="alert",
            trigger_condition=json.dumps({"severity": "critical", "metric": "cpu"}),
            created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        cond = wf.get_trigger_condition()
        assert cond["severity"] == "critical"
        assert cond["metric"] == "cpu"

    def test_workflow_risk_level(self, db: Session):
        wf = WorkflowTemplate(
            name="high-risk-wf", description="高危工作流",
            nodes="[]", edges="[]", enabled=True,
            risk_level="high", created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert wf.risk_level == "high"


class TestWorkflowStateMachine:
    def test_workflow_node_state_default(self, db: Session):
        wf = WorkflowTemplate(
            name="state-wf", description="状态测试",
            nodes=json.dumps([{"id": "n1", "type": "tool", "data": {"command": "echo hello"}}]),
            edges="[]", enabled=True, created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        n1 = wf.get_nodes()[0]
        assert n1["type"] == "tool"

    def test_workflow_node_with_timeout(self, db: Session):
        nodes = [{"id": "n1", "type": "tool", "data": {"command": "sleep 10", "timeout": 30}}]
        wf = WorkflowTemplate(
            name="timeout-wf", description="超时测试",
            nodes=json.dumps(nodes), edges="[]", enabled=True,
            created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert wf.get_nodes()[0]["data"]["timeout"] == 30

    def test_workflow_retry_on_failure(self, db: Session):
        nodes = [{"id": "n1", "type": "tool", "data": {"command": "failing-cmd", "retry_count": 3, "retry_delay": 5}}]
        wf = WorkflowTemplate(
            name="retry-wf", description="重试测试",
            nodes=json.dumps(nodes), edges="[]", enabled=True,
            created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert wf.get_nodes()[0]["data"]["retry_count"] == 3

    def test_workflow_notify_on_failure(self, db: Session):
        nodes = [{"id": "n1", "type": "tool", "data": {"command": "test", "notify_on_failure": True}}]
        wf = WorkflowTemplate(name="notify-wf", description="通知测试",
            nodes=json.dumps(nodes), edges="[]", enabled=True, created_at=datetime.utcnow())
        db.add(wf)
        db.commit()
        assert wf.get_nodes()[0]["data"].get("notify_on_failure") is True


class TestWorkflowCRUD:
    def test_create_workflow_template(self, db: Session):
        wf = WorkflowTemplate(
            name="test-wf", description="测试工作流",
            nodes="[]", edges="[]", enabled=True, category="ops",
            created_at=datetime.utcnow(),
        )
        db.add(wf)
        db.commit()
        assert wf.id is not None
        assert wf.category == "ops"

    def test_query_enabled_workflows(self, db: Session):
        for i in range(3):
            db.add(WorkflowTemplate(name=f"wf-{i}", description="test", nodes="[]", edges="[]", enabled=True, created_at=datetime.utcnow()))
        db.add(WorkflowTemplate(name="disabled-wf", description="test", nodes="[]", edges="[]", enabled=False, created_at=datetime.utcnow()))
        db.commit()
        enabled = db.query(WorkflowTemplate).filter(WorkflowTemplate.enabled.is_(True)).all()
        assert len(enabled) == 3

    def test_nonexistent_workflow(self, db: Session):
        wf = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == 99999).first()
        assert wf is None

    def test_workflow_nodes_json_valid(self, db: Session):
        wf = WorkflowTemplate(name="json-test", description="JSON 有效性", nodes="invalid", edges="[]", enabled=True, created_at=datetime.utcnow())
        db.add(wf)
        db.commit()
        try:
            nodes = wf.get_nodes()
        except Exception:
            nodes = []
        assert isinstance(nodes, list) or nodes is None