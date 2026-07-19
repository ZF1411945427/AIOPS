"""知识库文档管理 + RAG 检索接口.

功能：
- 文档上传（md/txt/pdf/docx）→ 解析 → 切片 → TF-IDF 向量化 → 入库
- 手动创建文本文档
- 文档 CRUD + 重新索引
- RAG 语义检索（JSON 接口，供前端 + MCP 工具调用）
"""
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.services import rag_service

router = APIRouter(prefix="/knowledge/documents", tags=["knowledge_documents"])
templates = get_templates()

# 上传文件存储目录
_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "kb"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 允许的文件扩展名
_ALLOWED_EXT = {"md", "txt", "markdown", "pdf", "docx"}
# 文件大小限制 10MB
_MAX_FILE_SIZE = 10 * 1024 * 1024


def _doc_to_dict(d):
    return {
        "id": d.id,
        "kb_id": d.kb_id,
        "title": d.title,
        "source_type": d.source_type or "",
        "file_path": d.file_path or "",
        "file_ext": d.file_ext or "",
        "content": d.content or "",
        "chunk_count": d.chunk_count or 0,
        "status": d.status or "pending",
        "tags": d.tags or "",
        "asset_type": d.asset_type or "",
        "severity": d.severity or "warning",
        "index_engine": getattr(d, "index_engine", "v1") or "v1",
        "created_by": d.created_by,
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
        "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M:%S") if d.updated_at else None,
    }


def _chunk_to_dict(c):
    return {
        "id": c.id,
        "document_id": c.document_id,
        "chunk_index": c.chunk_index,
        "content": c.content,
        "token_count": c.token_count or 0,
        "tags": c.tags or "",
        "asset_type": c.asset_type or "",
        "severity": c.severity or "warning",
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
    }


@router.get("/search", response_class=JSONResponse)
def doc_search(
    query: str = "",
    q: str = "",
    top_k: int = 5,
    asset_type: str = "",
    severity: str = "",
    tags: str = "",
    db: Session = Depends(get_db)):
    # 兼容 q 和 query 两种参数名
    query = query or q
    if not query:
        return JSONResponse({"items": [], "total": 0, "message": "缺少检索参数 query/q"})
    results = rag_service.vector_search(
        db, query=query, top_k=min(top_k, 20),
        asset_type=asset_type or None,
        severity=severity or None,
        tags=tags or None)
    return {"count": len(results), "query": query, "items": results}


@router.get("/api/list")
def api_doc_list(
    search: str = "",
    source_type: str = "",
    db: Session = Depends(get_db)):
    try:
        items = rag_service.list_documents(db, search=search, source_type=source_type)
        from app.models import KbChunk
        total_chunks = db.query(KbChunk).count()
        indexed_count = sum(1 for d in items if d.status == "indexed")
        return JSONResponse({
            "items": [_doc_to_dict(d) for d in items],
            "total_docs": len(items),
            "indexed_count": indexed_count,
            "total_chunks": total_chunks,
            "search": search,
            "source_type": source_type,
        })
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": []}, status_code=200)


@router.get("/api/{doc_id}")
def api_doc_detail(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = rag_service.get_document(db, doc_id)
        if not doc:
            return JSONResponse({"error": "not found"}, status_code=404)
        chunks = rag_service.list_chunks(db, doc_id)
        return JSONResponse({
            "doc": _doc_to_dict(doc),
            "chunks": [_chunk_to_dict(c) for c in chunks],
            "chunk_total": len(chunks),
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/create")
def api_doc_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        doc = rag_service.create_document(db, {
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "source_type": "manual",
            "file_ext": "txt",
            "tags": payload.get("tags", ""),
            "asset_type": payload.get("asset_type", ""),
            "severity": payload.get("severity", "warning"),
            "status": "pending",
            "created_by": payload.get("created_by"),
        })
        rag_service.index_document(db, doc.id)
        return JSONResponse({"ok": True, "id": doc.id, "item": _doc_to_dict(doc)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/upload")
async def api_doc_upload(
    request: Request,
    title: str = Form(""),
    tags: str = Form(""),
    asset_type: str = Form(""),
    severity: str = Form("warning"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)):
    try:
        user_id = request.session.get("user_id")
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext not in _ALLOWED_EXT:
            return JSONResponse(
                {"ok": False, "error": f"不支持的文件类型 .{ext}，仅支持 {', '.join(sorted(_ALLOWED_EXT))}"},
                status_code=400)
        content_bytes = await file.read()
        if len(content_bytes) > _MAX_FILE_SIZE:
            return JSONResponse(
                {"ok": False, "error": f"文件过大（{len(content_bytes)//1024}KB），限制 10MB"},
                status_code=400)
        safe_name = (file.filename or "upload.txt").replace("/", "_").replace("\\", "_").replace("..", "_")
        saved_path = _UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(content_bytes)
        text = rag_service.parse_document(str(saved_path), ext)
        doc_title = title.strip() if title.strip() else (file.filename or "未命名文档")
        doc = rag_service.create_document(db, {
            "title": doc_title[:256],
            "content": text,
            "source_type": "upload",
            "file_path": str(saved_path),
            "file_ext": ext,
            "tags": tags,
            "asset_type": asset_type,
            "severity": severity,
            "status": "pending",
            "index_engine": "v1",
            "created_by": user_id,
        })
        success, msg = rag_service.index_document(db, doc.id)
        if not success:
            doc.status = "failed"
            db.commit()
        return JSONResponse({"ok": True, "id": doc.id, "item": _doc_to_dict(doc)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/{doc_id}/reindex")
def api_doc_reindex(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = rag_service.get_document(db, doc_id)
        if not doc:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        if doc.file_path and os.path.exists(doc.file_path):
            doc.content = rag_service.parse_document(doc.file_path, doc.file_ext)
            db.commit()
        success, msg = rag_service.index_document(db, doc_id)
        return JSONResponse({"ok": success, "id": doc_id, "message": msg, "item": _doc_to_dict(doc)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/{doc_id}/delete")
def api_doc_delete(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = rag_service.get_document(db, doc_id)
        if not doc:
            return JSONResponse({"ok": False, "error": "文档不存在"}, status_code=404)
        # 同时清理 Milvus 侧（防止 V2 索引残留孤儿向量）
        try:
            from app.services import vector_store
            vector_store.delete_by_document(doc_id)
        except Exception:
            pass
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass
        rag_service.delete_document(db, doc_id)
        return JSONResponse({"ok": True, "id": doc_id})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)
