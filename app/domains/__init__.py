"""领域驱动分包注册中心

按业务域归类 100+ 路由，提供清晰的领域边界视图。
- 不改变现有 `app/routers/*.py` 的 import 路径（向后兼容）
- 通过 `DOMAIN_REGISTRY` 暴露领域 → 路由模块映射
- `main.py` 按域分组 include_router，新模块接入有清晰模板
- `/api/admin/domains` 端点列出所有领域及路由清单
"""

from app.domains.registry import DOMAIN_REGISTRY, DOMAIN_ORDER, get_domain_summary, get_routers_for_domain

__all__ = ["DOMAIN_REGISTRY", "DOMAIN_ORDER", "get_domain_summary", "get_routers_for_domain"]
