import hashlib
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ApiToken


def generate_token() -> str:
    return "aio_" + secrets.token_hex(24)


def list_tokens(db: Session):
    return db.query(ApiToken).order_by(ApiToken.id.desc()).all()


def create_token(db: Session, name: str, permissions: str = "read"):
    token_str = generate_token()
    token = ApiToken(
        name=name,
        token=token_str,
        permissions=permissions,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def delete_token(db: Session, token_id: int):
    db.query(ApiToken).filter(ApiToken.id == token_id).delete()
    db.commit()


def validate_token(db: Session, token_str: str) -> ApiToken | None:
    if not token_str:
        return None
    return db.query(ApiToken).filter(
        ApiToken.token == token_str,
        ApiToken.enabled == True,
    ).first()


def use_token(db: Session, token: ApiToken):
    token.last_used_at = datetime.now()
    db.commit()


