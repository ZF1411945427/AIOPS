"""集中凭据保险库（Secrets Vault，F3）。

- 加密存储：Fernet（VAULT_ENCRYPT_SEED 派生 key），列表/详情一律返回掩码 `***` + `has_value`
- 引用注入：连接配置写 `{{secret:<name>}}`，在「使用点」通过 `resolve_secret_refs` 递归替换为解密值
- 契约见 CONTRACT.md 第十八章
"""
import base64
import hashlib
import re

from app.config import VAULT_ENCRYPT_SEED
from app.models import SecretVault

_REF_PATTERN = re.compile(r"\{\{secret:([^{}:\s]+)\}\}")

VALUE_TYPES = ("password", "token", "api_key", "private_key", "custom")
SCOPES = ("global", "data_source", "asset")


def _fernet_key():
    from cryptography.fernet import Fernet
    seed = VAULT_ENCRYPT_SEED.encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed).digest()))


def encrypt_secret_value(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return _fernet_key().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret_value(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet_key().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


# ─── CRUD ───

def list_secrets(db):
    return db.query(SecretVault).order_by(SecretVault.id.desc()).all()


def get_secret(db, secret_id: int):
    return db.query(SecretVault).filter(SecretVault.id == secret_id).first()


def get_secret_by_name(db, name: str):
    return db.query(SecretVault).filter(SecretVault.name == name).first()


def create_secret(db, data: dict):
    name = (data.get("name") or "").strip()
    if not name or _REF_PATTERN.search(name) or any(ch.isspace() for ch in name):
        raise ValueError("name 不能为空，且不能包含空格、{、}")
    if get_secret_by_name(db, name):
        raise ValueError(f"凭据名称已存在: {name}")
    value = encrypt_secret_value(data.get("secret_value") or "")
    secret = SecretVault(
        name=name,
        description=(data.get("description") or "").strip(),
        value_type=data.get("value_type") or "password",
        scope=data.get("scope") or "global",
        secret_value_encrypted=value,
        created_by=data.get("created_by"),
    )
    db.add(secret)
    db.commit()
    db.refresh(secret)
    return secret


def update_secret(db, secret_id: int, data: dict):
    secret = get_secret(db, secret_id)
    if not secret:
        return None
    if "name" in data:
        new_name = (data.get("name") or "").strip()
        if new_name and new_name != secret.name:
            if get_secret_by_name(db, new_name):
                raise ValueError(f"凭据名称已存在: {new_name}")
            secret.name = new_name
    if "description" in data:
        secret.description = (data.get("description") or "").strip()
    if "value_type" in data and data.get("value_type"):
        secret.value_type = data["value_type"]
    if "scope" in data and data.get("scope"):
        secret.scope = data["scope"]
    # 空值 = 不更新（沿用 CONTRACT.md 第五章规则）
    if data.get("secret_value"):
        secret.secret_value_encrypted = encrypt_secret_value(data["secret_value"])
    db.commit()
    db.refresh(secret)
    return secret


def delete_secret(db, secret_id: int):
    secret = get_secret(db, secret_id)
    if not secret:
        return False
    db.delete(secret)
    db.commit()
    return True


def to_dict(secret: SecretVault) -> dict:
    """对外输出：一律掩码，绝不回显明文。"""
    return {
        "id": secret.id,
        "name": secret.name,
        "description": secret.description or "",
        "value_type": secret.value_type or "password",
        "scope": secret.scope or "global",
        "value_masked": "***",
        "has_value": bool(secret.secret_value_encrypted),
        "created_by": secret.created_by,
        "created_at": secret.created_at.strftime("%Y-%m-%d %H:%M:%S") if secret.created_at else None,
        "updated_at": secret.updated_at.strftime("%Y-%m-%d %H:%M:%S") if secret.updated_at else None,
    }


# ─── 引用注入 ───

def _get_db():
    from app.database import get_db_mode, get_session_for
    return get_session_for(get_db_mode())()


def _resolve_refs_str(text: str, lookup: dict) -> str:
    """替换字符串中的 {{secret:name}} 占位符；未找到的引用原样保留（fail-open）。"""
    def _sub(m: re.Match):
        name = m.group(1)
        val = lookup.get(name)
        if val is None:
            return m.group(0)
        return val
    return _REF_PATTERN.sub(_sub, text)


def resolve_secret_refs(value, db=None):
    """递归解析引用注入。value 可为 str / dict / list / 标量。

    仅当实际存在可用的 db（或未传 db 时临时开启会话）才解析；
    解析失败时返回原始值，保证 fail-open。
    """
    if isinstance(value, str):
        if not _REF_PATTERN.search(value):
            return value
        own_session = db is None
        if own_session:
            db = _get_db()
        try:
            lookup = {}
            for name in set(_REF_PATTERN.findall(value)):
                try:
                    secret = get_secret_by_name(db, name)
                    lookup[name] = decrypt_secret_value(secret.secret_value_encrypted) if secret else None
                except Exception:
                    return value
            return _resolve_refs_str(value, lookup)
        finally:
            if own_session:
                try:
                    db.close()
                except Exception:
                    pass
    if isinstance(value, dict):
        return {k: resolve_secret_refs(v, db) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_secret_refs(v, db) for v in value]
    return value


def find_secret_refs(text: str) -> list:
    """提取文本中所有 {{secret:name}} 引用（去重保序）。"""
    if not text:
        return []
    seen = []
    for name in _REF_PATTERN.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def collect_references(db):
    """扫描 data_sources.auth_config，返回引用使用情况（含失效引用标记）。"""
    from app.models import DataSource
    refs = {}
    for source in db.query(DataSource).all():
        cfg = source.auth_config or ""
        for name in find_secret_refs(cfg):
            if name not in refs:
                refs[name] = {"secret_name": name, "sources": [], "exists": bool(get_secret_by_name(db, name))}
            refs[name]["sources"].append({"source_id": source.id, "source_name": source.name, "source_type": source.type})
    return list(refs.values())
