"""安全模块：密码加盐哈希 + 验证 + 危险命令检测.

密码方案：bcrypt 加盐（向前兼容 sha256 无盐旧密码）
"""
import hashlib
import re
import os
import bcrypt
from fastapi import Request
from app.config import DANGEROUS_PATTERNS, COMMAND_WHITELIST


def hash_password(password: str) -> str:
    """bcrypt 加盐哈希，返回 'bcrypt$<hash>' 格式"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return f"bcrypt${hashed.decode('utf-8')}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码，兼容旧 sha256 无盐哈希和新的 bcrypt 加盐哈希"""
    if not password_hash:
        return False
    # 新格式：bcrypt$<hash>
    if password_hash.startswith("bcrypt$"):
        try:
            stored = password_hash[7:].encode("utf-8")
            return bcrypt.checkpw(password.encode("utf-8"), stored)
        except Exception:
            return False
    # 旧格式：sha256 无盐（向前兼容）
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return legacy == password_hash


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """检测危险命令，返回 (是否危险, 匹配的模式/原因)"""
    if not command:
        return False, ""
    cmd_lower = command.lower().strip()
    # 白名单模式（可选）：只允许白名单内的命令前缀
    if COMMAND_WHITELIST:
        _allowed = False
        for _w in COMMAND_WHITELIST:
            if cmd_lower.startswith(_w.lower()):
                _allowed = True
                break
        if not _allowed:
            return True, f"命令不在白名单中（白名单: {', '.join(COMMAND_WHITELIST[:5])}...）"
    # 黑名单模式：匹配危险模式
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower, re.IGNORECASE):
            return True, pattern
    return False, ""


def safe_error(e: Exception, message: str = "操作失败") -> dict:
    """安全错误响应：记录完整错误到日志，返回通用消息给前端.

    用法: return JSONResponse(safe_error(e, "创建失败"), status_code=500)
    """
    import traceback
    from app.logger import logger
    logger.error(f"{message}: {e}\n{traceback.format_exc()}")
    return {"error": message}


def require_admin(request: Request):
    """FastAPI 依赖：检查当前用户是否为 admin 角色，否则返回 403"""
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")
    from app.database import get_session_for, get_db_mode
    from app.models import User
    db = get_session_for(get_db_mode())()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.role != "admin":
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="需要管理员权限")
    finally:
        db.close()


# 仅允许 http/https 协议（防 SSRF / file:// 读取 / gopher 协议攻击）
_SAFE_URL_SCHEMES = ("http", "https")
_SAFE_URL_RE = re.compile(r"^[A-Za-z0-9_\-.@:/\?&=#%~+]{1,2048}$")


def validate_url_scheme(url: str) -> tuple[bool, str]:
    """校验 URL 协议是否安全（仅允许 http/https），防 SSRF。

    返回 (是否安全, 原因)。用于 urlopen / requests 调用前的校验。
    """
    if not url or not isinstance(url, str):
        return False, "URL 为空"
    url = url.strip()
    if not _SAFE_URL_RE.match(url):
        return False, "URL 含非法字符或过长"
    lower = url.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return True, "ok"
    if "://" in lower:
        scheme = lower.split("://", 1)[0]
        return False, f"不允许的协议: {scheme}（仅允许 http/https）"
    return False, "URL 缺少协议（需 http:// 或 https://）"
