"""代码/git 知识库 API(P2-5)。契约见 CONTRACT.md。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import git_knowledge_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/git-knowledge", tags=["git-knowledge"])


def _current_user_id(request: Request) -> int:
    uid = request.session.get("user_id")
    if not uid:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.services.mobile_push_service import verify_login_token
                payload = verify_login_token(auth[7:])
                if payload:
                    uid = payload.get("user_id")
            except Exception:
                pass
    return uid


@router.get("/repos")
def api_repo_list(request: Request, db: Session = Depends(get_db)):
    return JSONResponse({"ok": True, "repos": git_knowledge_service.list_repos(db)})


@router.post("/repos")
def api_repo_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    try:
        r = git_knowledge_service.create_repo(db, payload, created_by=_current_user_id(request))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "repo": git_knowledge_service._repo_dict(r)})


@router.post("/repos/{repo_id}/sync")
def api_repo_sync(repo_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = git_knowledge_service.sync_repo(db, repo_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    if not result.get("ok"):
        return JSONResponse({"ok": False, "error": result.get("error")}, status_code=500)
    return JSONResponse({"ok": True, "repo": git_knowledge_service._repo_dict(git_knowledge_service.get_repo(db, repo_id)),
                         "message": f"同步完成，索引 {result['file_count']} 个文件"})


@router.delete("/repos/{repo_id}")
def api_repo_delete(repo_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        git_knowledge_service.delete_repo(db, repo_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
    return JSONResponse({"ok": True, "message": "已删除仓库及其索引文档"})


@router.post("/search")
def api_code_search(request: Request, payload: dict, db: Session = Depends(get_db)):
    query = str(payload.get("query") or "").strip()
    if not query:
        return JSONResponse({"ok": False, "error": "缺少 query"}, status_code=400)
    try:
        result = git_knowledge_service.search_code(db, query, payload.get("repo"))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "result": result})
