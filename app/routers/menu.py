import json
import os
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, RoleMenu

router = APIRouter(prefix="/api/menu", tags=["menu"])

_config_path = os.path.join(os.path.dirname(__file__), "menu_config.json")
if os.path.exists(_config_path):
    with open(_config_path, "r", encoding="utf-8") as f:
        DEFAULT_MENU = json.load(f)
else:
    DEFAULT_MENU = []


def _collect_all_keys(groups: list) -> set:
    """收集菜单中所有 key（含嵌套）"""
    keys = set()
    for g in groups:
        keys.add(g["key"])
        for item in g.get("items", []):
            keys.add(item["key"])
            for sub in item.get("items", []):
                keys.add(sub["key"])
    return keys


@router.get("")
def get_menu(request: Request, db: Session = Depends(get_db), role_id: int = None):
    """获取菜单配置，按当前用户角色过滤。role_id 参数仅管理员预览用。"""
    menu = DEFAULT_MENU

    user_id = request.session.get("user_id")
    if not user_id:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            from app.services.mobile_push_service import verify_login_token
            payload = verify_login_token(auth[7:])
            if payload:
                user_id = payload.get("user_id")

    effective_role_id = role_id
    if effective_role_id is None and user_id:
        from app.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            effective_role_id = user.role_id

    if effective_role_id:
        role_menu_keys = set(
            rm.menu_key for rm in db.query(RoleMenu).filter(RoleMenu.role_id == effective_role_id).all()
        )
        if role_menu_keys:
            filtered = []
            for g in menu:
                items = []
                for item in g.get("items", []):
                    ikey = item["key"]
                    if ikey in role_menu_keys:
                        items.append(item)
                    elif "items" in item:
                        sub_items = [s for s in item["items"] if s["key"] in role_menu_keys]
                        if sub_items:
                            item_copy = dict(item)
                            item_copy["items"] = sub_items
                            items.append(item_copy)
                if items or g["key"] in role_menu_keys:
                    group_copy = dict(g)
                    group_copy["items"] = items
                    filtered.append(group_copy)
            return filtered

    return menu
