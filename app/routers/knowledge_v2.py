"""知识库 V2 API：基于 Milvus + BGE-M3 的生产级 RAG.

功能：
- 文档上传/创建/删除
- 智能切片 + BGE-M3 Embedding + Milvus 存储
- 混合检索（BM25 + 向量 + Reranker）
- Embedding 模式切换（bge-m3 / openai）
"""
import asyncio
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KbDocument
from app.services import embedding_service, vector_store, rag_engine_v2

router = APIRouter(prefix="/knowledge/v2", tags=["knowledge_v2"])


def _bg_index_document(doc_id: int, mode: str):
    """后台索引文档（在独立线程中运行）"""
    import traceback
    from app.database import get_session_for, get_db_mode
    _Session = get_session_for(get_db_mode())
    _db = _Session()
    try:
        ok, msg = rag_engine_v2.index_document_v2(_db, doc_id, mode)
        _d = _db.query(KbDocument).filter(KbDocument.id == doc_id).first()
        if _d:
            _d.status = "indexed" if ok else "failed"
            _db.commit()
        print(f"[bg_index] doc={doc_id} ok={ok} msg={msg}", flush=True)
    except Exception as e:
        print(f"[bg_index] doc={doc_id} EXCEPTION: {e}", flush=True)
        traceback.print_exc()
        try:
            _d = _db.query(KbDocument).filter(KbDocument.id == doc_id).first()
            if _d:
                _d.status = "failed"
                _db.commit()
        except Exception:
            pass
    finally:
        _db.close()

# 上传文件存储目录
_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "kb_v2"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_EXT = {"md", "txt", "markdown", "pdf", "docx"}
_MAX_FILE_SIZE = 10 * 1024 * 1024


def _doc_to_dict(d):
    return {
        "id": d.id, "title": d.title, "source_type": d.source_type or "",
        "file_ext": d.file_ext or "", "chunk_count": d.chunk_count or 0,
        "status": d.status or "pending", "tags": d.tags or "",
        "asset_type": d.asset_type or "", "severity": d.severity or "warning",
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
        "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M:%S") if d.updated_at else None,
    }


# ─── 文档管理 ───────────────────────────────────────────────────

@router.get("/documents/list")
def list_documents(search: str = "", db: Session = Depends(get_db)):
    try:
        q = db.query(KbDocument)
        if search:
            q = q.filter(KbDocument.title.contains(search))
        items = q.order_by(KbDocument.id.desc()).all()
        stats = vector_store.get_stats()
        return JSONResponse({
            "items": [_doc_to_dict(d) for d in items],
            "total": len(items),
            "vector_chunks": stats.get("total_chunks", 0),
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=500)


@router.get("/documents/{doc_id}/detail")
def get_document_detail(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = db.query(KbDocument).filter(KbDocument.id == doc_id).first()
        if not doc:
            return JSONResponse({"error": "文档不存在"}, status_code=404)

        # 从 Milvus 获取该文档的切片
        chunks = []
        try:
            client = vector_store.get_client()
            results = client.query(
                collection_name=vector_store._COLLECTION_NAME,
                filter=f'document_id == {doc_id}',
                output_fields=["chunk_index", "content", "tags", "asset_type", "severity", "source_type", "doc_title"],
                limit=10000,
            )
            chunks = [{"id": i.get("chunk_index"), "content": i.get("content", "")} for i in results]
            chunks.sort(key=lambda x: x.get("id", 0))
        except Exception:
            pass

        return JSONResponse({
            "doc": _doc_to_dict(doc),
            "content": doc.content or "",
            "chunks": chunks,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    title: str = Form(""),
    tags: str = Form(""),
    asset_type: str = Form(""),
    severity: str = Form("warning"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext not in _ALLOWED_EXT:
            return JSONResponse({"ok": False, "error": f"不支持的文件类型 .{ext}"}, status_code=400)

        content_bytes = await file.read()
        if len(content_bytes) > _MAX_FILE_SIZE:
            return JSONResponse({"ok": False, "error": f"文件过大（{len(content_bytes)//1024}KB），限制 10MB"}, status_code=400)

        safe_name = (file.filename or "upload.txt").replace("/", "_").replace("\\", "_")
        saved_path = _UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        with open(saved_path, "wb") as f:
            f.write(content_bytes)

        text = rag_service_parse(str(saved_path), ext)
        doc_title = title.strip() if title.strip() else (file.filename or "未命名文档")

        doc = KbDocument(
            title=doc_title[:256], content=text, source_type="upload",
            file_path=str(saved_path), file_ext=ext, tags=tags,
            asset_type=asset_type, severity=severity, status="pending",
            created_by=request.session.get("user_id"),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        t = threading.Thread(target=_bg_index_document, args=(doc.id, embedding_service.get_embedding_mode()), daemon=True)
        t.start()

        return JSONResponse({"ok": True, "id": doc.id, "message": "文件已上传，索引在后台处理中"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/documents/create")
async def create_document(payload: dict = {}, db: Session = Depends(get_db)):
    try:
        title = payload.get("title", "").strip()
        content = payload.get("content", "")
        if not title or not content:
            return JSONResponse({"ok": False, "error": "标题和内容不能为空"}, status_code=400)

        doc = KbDocument(
            title=title[:256], content=content, source_type="manual",
            file_ext="txt", tags=payload.get("tags", ""),
            asset_type=payload.get("asset_type", ""),
            severity=payload.get("severity", "warning"),
            status="pending", created_by=payload.get("created_by"),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        t = threading.Thread(target=_bg_index_document, args=(doc.id, embedding_service.get_embedding_mode()), daemon=True)
        t.start()

        return JSONResponse({"ok": True, "id": doc.id, "message": "文档已创建，索引在后台处理中"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/documents/{doc_id}/delete")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = db.query(KbDocument).filter(KbDocument.id == doc_id).first()
        if not doc:
            return JSONResponse({"ok": False, "error": "文档不存在"}, status_code=404)

        # 删除 Milvus 中的切片
        vector_store.delete_by_document(doc_id)

        # 删除上传文件
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass

        db.delete(doc)
        db.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(doc_id: int, db: Session = Depends(get_db)):
    try:
        doc = db.query(KbDocument).filter(KbDocument.id == doc_id).first()
        if not doc:
            return JSONResponse({"ok": False, "error": "文档不存在"}, status_code=404)

        if doc.file_path and os.path.exists(doc.file_path):
            ext = doc.file_ext or ""
            doc.content = rag_service_parse(doc.file_path, ext)
            db.commit()

        doc.status = "pending"
        db.commit()

        t = threading.Thread(target=_bg_index_document, args=(doc.id, embedding_service.get_embedding_mode()), daemon=True)
        t.start()

        return JSONResponse({"ok": True, "id": doc_id, "message": "重新索引在后台处理中"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ─── 语义检索 ───────────────────────────────────────────────────

@router.get("/search")
async def search(
    q: str = "",
    top_k: int = 5,
    asset_type: str = "",
    severity: str = "",
    tags: str = "",
    db: Session = Depends(get_db),
):
    if not q:
        return JSONResponse({"items": [], "total": 0, "message": "缺少检索参数 q"})

    results = await asyncio.to_thread(
        rag_engine_v2.hybrid_search,
        query=q, top_k=min(top_k, 20),
        asset_type=asset_type or None,
        severity=severity or None,
        tags=tags or None,
    )

    # 补充文档信息
    for r in results:
        doc_id = r.get("document_id")
        if doc_id:
            doc = db.query(KbDocument).filter(KbDocument.id == doc_id).first()
            if doc:
                r["doc_title"] = doc.title
                r["source_type"] = doc.source_type

    return JSONResponse({"count": len(results), "query": q, "items": results})


# ─── Embedding 模式管理 ─────────────────────────────────────────

@router.get("/embedding/mode")
def get_embedding_mode():
    return {"mode": embedding_service.get_embedding_mode()}


@router.post("/embedding/mode")
def set_embedding_mode(payload: dict = {}):
    mode = payload.get("mode", "bge-m3")
    if mode not in ("bge-m3", "openai"):
        return JSONResponse({"ok": False, "error": "不支持的模式"}, status_code=400)
    embedding_service.set_embedding_mode(mode)
    return {"ok": True, "mode": mode}


# ─── 统计信息 ───────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    try:
        total_docs = db.query(KbDocument).count()
        indexed_docs = db.query(KbDocument).filter(KbDocument.status == "indexed").count()
        vector_stats = vector_store.get_stats()
        return JSONResponse({
            "total_docs": total_docs,
            "indexed_docs": indexed_docs,
            "total_chunks": vector_stats.get("total_chunks", 0),
            "embedding_mode": embedding_service.get_embedding_mode(),
            "embedding_dimension": embedding_service.get_embedding_dimension(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── 工具函数 ───────────────────────────────────────────────────

def rag_service_parse(file_path: str, ext: str) -> str:
    """复用 rag_service 的文档解析"""
    from app.services.rag_service import parse_document
    return parse_document(file_path, ext)
