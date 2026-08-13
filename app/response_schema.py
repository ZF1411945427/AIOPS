"""统一 API 契约辅助(H1, 低风险方案) - 不引入全局响应 envelope(避免破坏前端), 提供:
1) 统一错误结构 pydantic 模型
2) 可选 success/fail 响应辅助(供新增端点选用)
3) response_model 契约锚点, 让 FastAPI 自动做 OpenAPI/序列化校验

前端 request.js 读: response.data 顶层字段(data.warning/items/total) 与
error.response.data.detail/message/error。因此错误结构必须保留这些键。
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """统一错误结构(兼容前端读取的 detail/message/error 键)。"""
    ok: bool = False
    code: int = Field(default=400, description="业务/HTTP 错误码")
    message: str = Field(default="", description="人类可读错误")
    detail: Optional[str] = None  # 兼容 request.js 读 detail
    error: Optional[str] = None   # 兼容部分 handler 读 error
    data: Any = None


def ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    """统一成功体(兼容前端读顶层 data 字段: 保留原数据作为 data, 并带 ok/status)."""
    return {"ok": True, "code": 0, "message": message, "data": data}


def fail(message: str, code: int = 400, detail: Optional[str] = None) -> Dict[str, Any]:
    """统一失败体(兼容前端读 message/detail/error)."""
    return {"ok": False, "code": code, "message": message,
            "detail": detail or message, "error": message, "data": None}
