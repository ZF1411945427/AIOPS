"""代码/git 知识库同步(P2-5) - clone 仓库、索引为知识文档、提供代码搜索。

契约: CONTRACT.md(P2-5 说明)。仓库 clone 到 <PROJECT_ROOT>/repo_cache/<name>,
文件以 source_type="git" 存入 kb_documents(供 RAG/知识检索);代码搜索直接对
repo_cache 做内容 grep(快、免索引)。
"""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import GitRepo, KbDocument

import logging
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_CACHE = PROJECT_ROOT / "repo_cache"

# 索引源码/文本扩展名
_INDEXABLE_EXT = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".c", ".cpp", ".h",
    ".sh", ".sql", ".yaml", ".yml", ".json", ".md", ".txt", ".toml", ".ini",
    ".conf", ".xml", ".html", ".css", ".vue",
}
_SKIP_DIRS = {".git", "node_modules", "dist", "build", "target", "venv", ".venv", "__pycache__", ".idea", ".vscode"}


def _repo_dict(r: GitRepo) -> Dict[str, Any]:
    return {
        "id": r.id, "name": r.name, "url": r.url, "branch": r.branch,
        "local_path": r.local_path, "status": r.status, "file_count": r.file_count,
        "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
        "error_msg": r.error_msg,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


def list_repos(db: Session) -> List[Dict[str, Any]]:
    return [_repo_dict(r) for r in db.query(GitRepo).order_by(GitRepo.name).all()]


def get_repo(db: Session, repo_id: int) -> Optional[GitRepo]:
    return db.query(GitRepo).filter(GitRepo.id == repo_id).first()


def create_repo(db: Session, data: Dict[str, Any], created_by: Optional[int] = None) -> GitRepo:
    name = str(data.get("name") or "").strip()
    url = str(data.get("url") or "").strip()
    if not name or not url:
        raise ValueError("name 和 url 不能为空")
    if db.query(GitRepo).filter(GitRepo.name == name).first():
        raise ValueError(f"仓库 {name} 已存在")
    r = GitRepo(name=name, url=url, branch=str(data.get("branch") or "main"),
                local_path="", status="pending", created_by=created_by)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def delete_repo(db: Session, repo_id: int) -> None:
    r = get_repo(db, repo_id)
    if not r:
        raise ValueError("仓库不存在")
    local = (r.local_path or "").strip()
    db.delete(r)
    db.commit()
    if local and Path(local).exists():
        import shutil
        try:
            shutil.rmtree(local, ignore_errors=True)
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    # 删除该仓库的 git 源文档
    db.query(KbDocument).filter(
        KbDocument.source_type == "git",
        KbDocument.file_path.like(f"__git__/{r.name}%"),
    ).delete()
    db.commit()


def sync_repo(db: Session, repo_id: int) -> Dict[str, Any]:
    """clone/拉取仓库并索引为知识文档。"""
    r = get_repo(db, repo_id)
    if not r:
        raise ValueError("仓库不存在")
    local_dir = REPO_CACHE / r.name
    local_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not (local_dir / ".git").exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", r.branch, r.url, str(local_dir)],
                capture_output=True, text=True, timeout=180, check=True)
            r.status = "ready"
        else:
            subprocess.run(["git", "-C", str(local_dir), "pull", "--ff-only"],
                           capture_output=True, text=True, timeout=120, check=True)
            r.status = "ready"
    except subprocess.CalledProcessError as e:
        r.status = "error"
        r.error_msg = (e.stderr or e.stdout or str(e))[:2000]
        db.commit()
        return {"ok": False, "error": r.error_msg}
    r.local_path = str(local_dir)
    # 索引: 先删旧 git 文档再重建
    old = db.query(KbDocument).filter(
        KbDocument.source_type == "git",
        KbDocument.file_path.like(f"__git__/{r.name}%"),
    ).all()
    file_count = 0
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _INDEXABLE_EXT:
                continue
            full = Path(root) / fn
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            rel = full.relative_to(local_dir).as_posix()
            doc = next((d for d in old if d.file_path == f"__git__/{r.name}/{rel}"), None)
            if doc is None:
                doc = KbDocument(title=f"[git/{r.name}] {rel}", source_type="git",
                                 file_path=f"__git__/{r.name}/{rel}",
                                 file_ext=ext.lstrip("."), content=content,
                                 tags=f"git,{r.name}", status="indexed")
                db.add(doc)
            else:
                doc.content = content
                doc.title = f"[git/{r.name}] {rel}"
                doc.status = "indexed"
            file_count += 1
    # 删除仓库中已不存在的旧文档
    keep_paths = set()
    for root, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn)[1].lower() in _INDEXABLE_EXT:
                keep_paths.add(f"__git__/{r.name}/" + (Path(root) / fn).relative_to(local_dir).as_posix())
    for d in old:
        if d.file_path not in keep_paths:
            db.delete(d)
    r.file_count = file_count
    r.last_sync_at = datetime.now()
    db.commit()
    return {"ok": True, "file_count": file_count, "local_path": str(local_dir)}


def search_code(db: Session, query: str, repo_name: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """对已同步仓库做代码搜索(内容 grep)。"""
    query = (query or "").strip()
    if not query:
        raise ValueError("缺少搜索关键词")
    results: List[Dict[str, Any]] = []
    repos = [r for r in db.query(GitRepo).filter(GitRepo.status == "ready").all()
             if not repo_name or r.name == repo_name]
    pat = re.compile(re.escape(query), re.IGNORECASE)
    for r in repos:
        if not r.local_path or not Path(r.local_path).exists():
            continue
        for root, dirs, files in os.walk(r.local_path):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in _INDEXABLE_EXT:
                    continue
                full = Path(root) / fn
                try:
                    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                for i, line in enumerate(lines):
                    if pat.search(line):
                        rel = full.relative_to(Path(r.local_path)).as_posix()
                        snippet = line.strip()[:200]
                        results.append({
                            "repo": r.name,
                            "path": rel,
                            "line": i + 1,
                            "snippet": snippet,
                        })
                        if len(results) >= limit * 3:
                            break
                if len(results) >= limit * 3:
                    break
            if len(results) >= limit * 3:
                break
    return {"query": query, "total": len(results), "results": results[:limit]}
