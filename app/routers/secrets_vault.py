"""集中凭据保险库 API（F3）。契约见 CONTRACT.md 第十八章。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import secret_vault
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/vault", tags=["vault"])


def _current_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.services.mobile_push_service import verify_login_token
                payload = verify_login_token(auth[7:])
                if payload:
                    user_id = payload.get("user_id")
            except Exception:
                pass
    return user_id


@router.get("/secrets")
def api_secret_list(request: Request, db: Session = Depends(get_db)):
    secrets = [secret_vault.to_dict(s) for s in secret_vault.list_secrets(db)]
    return JSONResponse({
        "ok": True,
        "secrets": secrets,
        "value_types": secret_vault.VALUE_TYPES,
        "scopes": secret_vault.SCOPES,
        "total": len(secrets),
    })


@router.get("/secrets/{secret_id}")
def api_secret_get(secret_id: int, db: Session = Depends(get_db)):
    secret = secret_vault.get_secret(db, secret_id)
    if not secret:
        return JSONResponse({"error": "凭据不存在"}, status_code=404)
    return JSONResponse({"ok": True, "secret": secret_vault.to_dict(secret)})


@router.post("/secrets")
async def api_secret_create(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    body.setdefault("created_by", _current_user_id(request))
    try:
        secret = secret_vault.create_secret(db, body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "secret": secret_vault.to_dict(secret)})


@router.put("/secrets/{secret_id}")
async def api_secret_update(secret_id: int, request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        secret = secret_vault.update_secret(db, secret_id, body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not secret:
        return JSONResponse({"error": "凭据不存在"}, status_code=404)
    return JSONResponse({"ok": True, "secret": secret_vault.to_dict(secret)})


@router.delete("/secrets/{secret_id}")
def api_secret_delete(secret_id: int, db: Session = Depends(get_db)):
    if not secret_vault.delete_secret(db, secret_id):
        return JSONResponse({"error": "凭据不存在"}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/secrets/resolve")
async def api_secret_resolve(request: Request, db: Session = Depends(get_db)):
    """测试引用解析：传入任意 dict/str，返回替换后的结果。"""
    body = await request.json()
    resolved = secret_vault.resolve_secret_refs(body, db)
    return JSONResponse({"ok": True, "resolved": resolved})


@router.get("/references")
def api_secret_references(db: Session = Depends(get_db)):
    refs = secret_vault.collect_references(db)
    return JSONResponse({"ok": True, "references": refs, "total": len(refs)})
