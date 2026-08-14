"""资源级 RBAC 权限服务：策略存取 + 用户权限判定（casbin_engine 的 DB 层）。

- role_permissions 表存 (role_id, resource, action)
- check_user_permission(user_id, resource, action)：superuser 绕过 + 角色策略命中
- 提供角色策略 CRUD，供 roles.py 使用
"""
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models import Role, RolePermission, User


def _user_role(db: Session, user_id: int) -> Optional[Tuple[int, str, bool]]:
    """返回 (role_id, role_name, is_system) 或 None。"""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return None
    # 兼容旧数据：User.role 直接是 admin/viewer/operator 字符串
    if u.role and u.role in ("admin", "viewer", "operator", "auditor"):
        # 尝试找到同名 role_id，找不到则视为内建角色
        role = db.query(Role).filter(Role.name == u.role).first()
        if role:
            return role.id, role.name, bool(role.is_system)
        return None, u.role, True
    if u.role_id:
        role = db.query(Role).filter(Role.id == u.role_id).first()
        if role:
            return role.id, role.name, bool(role.is_system)
    return None, "viewer", True


def _role_permissions(db: Session, role_id: int) -> Set[Tuple[str, str]]:
    perms = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
    return {(p.resource, p.action) for p in perms}


def user_permissions(db: Session, user_id: int) -> Dict[str, List[str]]:
    """返回用户实际拥有的资源权限矩阵 {resource: [action,...]}。
    内建角色做默认兜底（admin 全权限，viewer 只读，其余按策略表）。"""
    from app.casbin_engine import get_all_resources

    info = _user_role(db, user_id)
    if not info:
        return {}
    role_id, role_name, is_system = info

    # superuser：全部资源全部动作
    if role_name in ("admin", "superuser") or (is_system and role_name == "admin"):
        return {r: ["read", "write", "execute", "delete"] for r in get_all_resources()}

    perms = _role_permissions(db, role_id) if role_id else set()
    # viewer 内建只读
    if role_name == "viewer":
        return {r: ["read"] for r in get_all_resources()}
    # operator 内建：读+写（无删除/执行）
    if role_name == "operator":
        return {r: ["read", "write"] for r in get_all_resources()}
    # 无策略的角色：仅读（最小权限）
    matrix: Dict[str, Set[str]] = {}
    for resource, action in perms:
        matrix.setdefault(resource, set()).add(action)
    if not matrix:
        return {r: ["read"] for r in get_all_resources()}
    return {r: sorted(acts) for r, acts in matrix.items()}


def check_user_permission(db: Session, user_id: int, resource: str, action: str) -> bool:
    """判定用户是否可对 resource 执行 action。superuser 完全绕过。"""
    info = _user_role(db, user_id)
    if not info:
        return False
    role_id, role_name, is_system = info
    if role_name in ("admin", "superuser") or (is_system and role_name == "admin"):
        return True
    # 内建只读角色
    if role_name == "viewer":
        return action == "read"
    if role_name == "operator":
        return action in ("read", "write")
    if not role_id:
        return False
    return (resource, action) in _role_permissions(db, role_id)


def check_path_permission(db: Session, user_id: int, path: str, method: str) -> Optional[bool]:
    """HTTP 请求级判定：无法映射返回 None(不拦截)；有映射返回 True/False。"""
    from app.casbin_engine import resolve_request

    req = resolve_request(path, method)
    if req is None:
        return None
    resource, action = req
    return check_user_permission(db, user_id, resource, action)


# ─── 角色策略 CRUD ───
def get_role_permissions(db: Session, role_id: int) -> Dict[str, List[str]]:
    perms = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
    matrix: Dict[str, Set[str]] = {}
    for p in perms:
        matrix.setdefault(p.resource, set()).add(p.action)
    return {r: sorted(acts) for r, acts in matrix.items()}


def set_role_permissions(db: Session, role_id: int, matrix: Dict[str, List[str]]) -> None:
    """整体覆盖设置角色策略矩阵。matrix={resource: [action,...]}。"""
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for resource, actions in (matrix or {}).items():
        if not resource or not actions:
            continue
        for action in actions:
            if action not in ("read", "write", "execute", "delete"):
                continue
            db.add(RolePermission(role_id=role_id, resource=resource, action=action))
    db.commit()


def sync_admin_full_permissions(db: Session) -> int:
    """把 admin/superuser 角色的策略补全为全资源全动作（幂等），返回补丁数。"""
    from app.casbin_engine import get_all_resources

    roles = db.query(Role).filter(Role.name.in_(["admin", "superuser"])).all()
    patched = 0
    for role in roles:
        existing = {(p.resource, p.action) for p in
                    db.query(RolePermission).filter(RolePermission.role_id == role.id).all()}
        for r in get_all_resources():
            for a in ("read", "write", "execute", "delete"):
                if (r, a) not in existing:
                    db.add(RolePermission(role_id=role.id, resource=r, action=a))
                    patched += 1
    if patched:
        db.commit()
    return patched
