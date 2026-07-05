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

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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


@router.get("", response_class=HTMLResponse)
def doc_list(
    request: Request,
    search: str = "",
    source_type: str = "",
    db: Session = Depends(get_db),
):
    items = rag_service.list_documents(db, search=search, source_type=source_type)
    # 统计
    from app.models import KbChunk
    total_chunks = db.query(KbChunk).count()
    indexed_count = sum(1 for d in items if d.status == "indexed")
    return templates.TemplateResponse("knowledge_documents.html", {
        "request": request,
        "items": items,
        "search": search,
        "source_type": source_type,
        "total_docs": len(items),
        "indexed_count": indexed_count,
        "total_chunks": total_chunks,
    })


@router.get("/search", response_class=JSONResponse)
def doc_search(
    query: str,
    top_k: int = 5,
    asset_type: str = "",
    severity: str = "",
    tags: str = "",
    db: Session = Depends(get_db),
):
    """RAG 语义检索 JSON 接口（供前端 AJAX + MCP 工具调用）."""
    results = rag_service.vector_search(
        db, query=query, top_k=min(top_k, 20),
        asset_type=asset_type or None,
        severity=severity or None,
        tags=tags or None,
    )
    return {"count": len(results), "query": query, "items": results}


@router.get("/{doc_id}", response_class=HTMLResponse)
def doc_detail(doc_id: int, request: Request, db: Session = Depends(get_db)):
    doc = rag_service.get_document(db, doc_id)
    if not doc:
        return RedirectResponse("/knowledge/documents", status_code=303)
    chunks = rag_service.list_chunks(db, doc_id)
    # 截断切片内容预览（避免页面过长）
    chunk_previews = [
        {"index": c.chunk_index, "content": c.content[:300], "token_count": c.token_count}
        for c in chunks[:20]
    ]
    return templates.TemplateResponse("knowledge_document_detail.html", {
        "request": request,
        "doc": doc,
        "chunks": chunk_previews,
        "chunk_total": len(chunks),
    })


@router.post("/create")
def doc_create(
    request: Request,
    title: str = Form(...),
    content: str = Form(""),
    tags: str = Form(""),
    asset_type: str = Form(""),
    severity: str = Form("warning"),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    doc = rag_service.create_document(db, {
        "title": title,
        "content": content,
        "source_type": "manual",
        "file_ext": "txt",
        "tags": tags,
        "asset_type": asset_type,
        "severity": severity,
        "status": "pending",
        "created_by": user_id,
    })
    # 自动索引
    rag_service.index_document(db, doc.id)
    return RedirectResponse(f"/knowledge/documents/{doc.id}", status_code=303)


@router.post("/upload")
async def doc_upload(
    request: Request,
    title: str = Form(""),
    tags: str = Form(""),
    asset_type: str = Form(""),
    severity: str = Form("warning"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    # 校验扩展名
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in _ALLOWED_EXT:
        return RedirectResponse(
            f"/knowledge/documents?error=不支持的文件类型 .{ext}，仅支持 {', '.join(sorted(_ALLOWED_EXT))}",
            status_code=303,
        )
    # 读取内容（带大小限制）
    content_bytes = await file.read()
    if len(content_bytes) > _MAX_FILE_SIZE:
        return RedirectResponse(
            f"/knowledge/documents?error=文件过大（{len(content_bytes)//1024}KB），限制 10MB",
            status_code=303,
        )
    # 保存原始文件
    safe_name = (file.filename or "upload.txt").replace("/", "_").replace("\\", "_")
    saved_path = _UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    with open(saved_path, "wb") as f:
        f.write(content_bytes)
    # 解析文档
    text = rag_service.parse_document(str(saved_path), ext)
    # 标题：用户填了用用户的，否则用文件名
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
        "created_by": user_id,
    })
    # 自动索引
    success, msg = rag_service.index_document(db, doc.id)
    if not success:
        doc.status = "failed"
        db.commit()
    return RedirectResponse(f"/knowledge/documents/{doc.id}", status_code=303)


@router.post("/{doc_id}/reindex")
def doc_reindex(doc_id: int, db: Session = Depends(get_db)):
    doc = rag_service.get_document(db, doc_id)
    if not doc:
        return RedirectResponse("/knowledge/documents", status_code=303)
    # 如果有原始文件路径，重新解析
    if doc.file_path and os.path.exists(doc.file_path):
        doc.content = rag_service.parse_document(doc.file_path, doc.file_ext)
        db.commit()
    rag_service.index_document(db, doc_id)
    return RedirectResponse(f"/knowledge/documents/{doc_id}", status_code=303)


@router.post("/{doc_id}/delete")
def doc_delete(doc_id: int, db: Session = Depends(get_db)):
    doc = rag_service.get_document(db, doc_id)
    # 删除原始文件
    if doc and doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass
    rag_service.delete_document(db, doc_id)
    return RedirectResponse("/knowledge/documents", status_code=303)
