"""AI 运维沙盒管理 API — 独立模块，不影响现有功能。

提供：
- 全局沙盒配置读写
- 细粒度策略 CRUD
- 沙盒决策模拟（test/evaluate）
- 沙盒执行日志查询
"""
from fastapi import APIRouter
from typing import Optional

from app.services import sandbox_service

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/api/config")
def get_config():
    """获取全局沙盒配置。"""
    return sandbox_service.get_config()


@router.post("/api/config")
def update_config(data: dict):
    """更新全局沙盒配置。"""
    cfg = sandbox_service.update_config(data)
    return {"ok": True, "config": cfg}


@router.get("/api/policies")
def list_policies():
    """列出所有沙盒策略。"""
    return sandbox_service.list_policies()


@router.post("/api/policies")
def create_policy(data: dict):
    """创建沙盒策略。"""
    p = sandbox_service.create_policy(data)
    return {"ok": True, "policy": p}


@router.put("/api/policies/{policy_id}")
def update_policy(policy_id: int, data: dict):
    """更新沙盒策略。"""
    p = sandbox_service.update_policy(policy_id, data)
    if not p:
        return {"ok": False, "message": "策略不存在"}
    return {"ok": True, "policy": p}


@router.delete("/api/policies/{policy_id}")
def delete_policy(policy_id: int):
    """删除沙盒策略。"""
    ok = sandbox_service.delete_policy(policy_id)
    return {"ok": ok, "message": "已删除" if ok else "策略不存在"}


@router.post("/api/evaluate")
def evaluate(data: dict):
    """模拟一次沙盒决策（不真正执行，用于测试闭环）。

    入参示例：
      {
        "action_type": "restart",
        "tool_name": "execute_restart_service",
        "asset_id": 1,
        "command": "systemctl restart nginx",
        "risk_level": "high",
        "session_id": 0,
        "user_id": 0,
        "role_id": 0
      }
    """
    result = sandbox_service.evaluate_request(
        action_type=str(data.get("action_type", "")),
        tool_name=str(data.get("tool_name", "")),
        asset_id=int(data.get("asset_id", 0) or 0),
        command=str(data.get("command", "")),
        risk_level=str(data.get("risk_level", "medium")),
        session_id=int(data.get("session_id", 0) or 0),
        user_id=int(data.get("user_id", 0) or 0),
        role_id=int(data.get("role_id", 0) or 0),
    )
    return result


@router.get("/api/logs")
def list_logs(limit: Optional[int] = 100):
    """查询沙盒执行日志。"""
    return sandbox_service.list_execution_logs(limit)


@router.get("/api/risk-levels")
def risk_levels():
    """返回风险等级枚举。"""
    return {"levels": sandbox_service.RISK_ORDER}


@router.get("/api/scope-types")
def scope_types():
    """返回作用范围类型枚举。"""
    return {"types": ["global", "role", "user", "session"]}