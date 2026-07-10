"""RAG 引擎 V2：文档切片 → Embedding → Milvus 存储 → 混合检索 → Reranker.

完整 Pipeline：
1. 文档解析（复用现有 rag_service.parse_document）
2. 智能切片（语义分界 > 段落 > 字符）
3. BGE-M3 Embedding 生成
4. Milvus 向量存储
5. 混合检索（BM25 关键词 + 向量语义）
6. Reranker 重排序
"""
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import KbDocument, KbChunk
from app.services import rag_service
from app.services import embedding_service
from app.services import vector_store


# ─── 智能切片 ───────────────────────────────────────────────────

def smart_chunk(text: str, max_chars: int = 2000, overlap: int = 200) -> List[str]:
    """智能切片：合并小段落 + 超长段落按句子切分，支持重叠。
    
    策略：
    1. 按段落切分
    2. 合并连续小段落直到接近 max_chars
    3. 超长段落按句子硬切，带 overlap
    4. 过滤过短切片（< 50 字）
    """
    if not text or not text.strip():
        return []

    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # 第一步：合并小段落
    merged = []
    buffer = ""
    for para in paragraphs:
        if len(para) > max_chars:
            # 超长段落先 flush buffer，再单独处理
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(para)  # 标记为超长，后面按句子切
        elif len(buffer) + len(para) + 2 <= max_chars:
            buffer = (buffer + "\n\n" + para) if buffer else para
        else:
            if buffer:
                merged.append(buffer)
            buffer = para
    if buffer:
        merged.append(buffer)

    # 第二步：超长段落按句子切分
    chunks = []
    for item in merged:
        if len(item) <= max_chars:
            chunks.append(item)
        else:
            sentences = re.split(r'(?<=[。！？.!?\n])\s*', item)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) > max_chars and current:
                    chunks.append(current.strip())
                    if overlap > 0 and len(current) > overlap:
                        current = current[-overlap:] + " " + sent
                    else:
                        current = sent
                else:
                    current = current + " " + sent if current else sent
            if current.strip():
                chunks.append(current.strip())

    chunks = [c for c in chunks if len(c) >= 50]
    return chunks


# ─── 文档索引 ───────────────────────────────────────────────────

def index_document_v2(db: Session, document_id: int, mode: Optional[str] = None) -> Tuple[bool, str]:
    """将文档索引到 Milvus（线程安全版：内部创建独立 Session）
    
    1. 读取文档内容
    2. 智能切片
    3. BGE-M3 Embedding
    4. 存入 Milvus
    5. 更新文档切片信息
    
    返回: (success, message)
    """
    # 创建独立 Session（线程安全）
    from app.database import get_session_for, get_db_mode
    SessionLocal = get_session_for(get_db_mode())
    thread_db = SessionLocal()
    try:
        doc = thread_db.query(KbDocument).filter(KbDocument.id == document_id).first()
        if not doc:
            return False, "文档不存在"

        content = doc.content or ""
        if not content.strip():
            return False, "文档内容为空"

        # 智能切片
        chunks_text = smart_chunk(content)
        if not chunks_text:
            return False, "切片后无有效内容"

        # 批量 Embedding
        try:
            embeddings = embedding_service.embed_texts(chunks_text, mode)
        except Exception as e:
            return False, f"Embedding 生成失败: {e}"

        if not embeddings or len(embeddings) != len(chunks_text):
            return False, "Embedding 数量不匹配"

        # 删除旧切片（如果有）
        vector_store.delete_by_document(document_id)

        # 构建 Milvus 数据
        chunks_data = []
        for i, (text, emb) in enumerate(zip(chunks_text, embeddings)):
            chunks_data.append({
                "document_id": document_id,
                "chunk_index": i,
                "content": text,
                "embedding": emb,
                "tags": doc.tags or "",
                "asset_type": doc.asset_type or "",
                "severity": doc.severity or "",
                "source_type": doc.source_type or "",
                "doc_title": doc.title or "",
            })

        # 批量插入 Milvus
        vector_store.insert_chunks(chunks_data)

        # 更新文档状态
        doc.chunk_count = len(chunks_text)
        doc.status = "indexed"
        thread_db.commit()

        return True, f"索引完成：{len(chunks_text)} 个切片"
    except Exception as e:
        thread_db.rollback()
        return False, f"索引异常：{e}"
    finally:
        thread_db.close()


# ─── 混合检索 ───────────────────────────────────────────────────

def hybrid_search(
    query: str,
    top_k: int = 5,
    asset_type: Optional[str] = None,
    severity: Optional[str] = None,
    tags: Optional[str] = None,
    mode: Optional[str] = None,
) -> List[Dict]:
    """混合检索：BM25 关键词 + 向量语义 + Reranker 重排序
    
    流程：
    1. BM25 关键词检索（从 Milvus 全量切片中筛选）
    2. 向量语义检索（BGE-M3 Embedding + 余弦相似度）
    3. 合并结果（去重）
    4. Reranker 重排序（bge-reranker-v2-m3）
    5. 返回 Top-K
    """
    if not query or not query.strip():
        return []

    # 1. 向量语义检索
    try:
        query_embedding = embedding_service.embed_query(query, mode)
        vector_results = vector_store.search_by_vector(
            query_embedding, top_k=min(top_k * 2, 20),
            asset_type=asset_type, severity=severity, tags=tags,
        )
    except Exception as e:
        print(f"[rag_v2] 向量检索失败: {e}")
        vector_results = []

    # 2. BM25 关键词检索（从向量结果中补充关键词匹配）
    bm25_results = _bm25_search(query, top_k=min(top_k * 2, 20))

    # 3. 合并去重
    merged = _merge_results(vector_results, bm25_results)

    # 4. Reranker 重排序
    if len(merged) > 1:
        merged = _rerank(query, merged)

    # 5. 返回 Top-K
    return merged[:top_k]


def _bm25_search(query: str, top_k: int = 10) -> List[Dict]:
    """BM25 关键词检索（基于 rank_bm25）"""
    try:
        from rank_bm25 import BM25Okapi
        client = vector_store.get_client()
        # 获取所有切片
        all_chunks = client.query(
            collection_name=vector_store._COLLECTION_NAME,
            output_fields=["document_id", "chunk_index", "content", "tags", "asset_type", "severity", "source_type", "doc_title"],
            limit=10000,
        )
        if not all_chunks:
            return []

        # 简单分词（中英文混合）
        def tokenize(text):
            tokens = re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z0-9]+', text.lower())
            return tokens

        corpus = [c.get("content", "") for c in all_chunks]
        tokenized_corpus = [tokenize(doc) for doc in corpus]

        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = tokenize(query)
        scores = bm25.get_scores(tokenized_query)

        # 取 Top-K
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = all_chunks[idx]
            chunk["score"] = round(float(scores[idx]) / max(scores.max(), 1e-6), 4)  # 归一化
            results.append(chunk)
        return results
    except Exception as e:
        print(f"[rag_v2] BM25 检索失败: {e}")
        return []


def _merge_results(vector_results: List[Dict], bm25_results: List[Dict]) -> List[Dict]:
    """合并向量检索和 BM25 检索结果，去重并计算综合分数"""
    seen = {}  # document_id + chunk_index -> result

    # 向量结果权重 0.7，BM25 权重 0.3
    for r in vector_results:
        key = f"{r['document_id']}_{r['chunk_index']}"
        r["vector_score"] = r.get("score", 0)
        r["bm25_score"] = 0
        r["score"] = r["vector_score"] * 0.7
        seen[key] = r

    for r in bm25_results:
        key = f"{r['document_id']}_{r['chunk_index']}"
        if key in seen:
            seen[key]["bm25_score"] = r.get("score", 0)
            seen[key]["score"] += r.get("score", 0) * 0.3
        else:
            r["vector_score"] = 0
            r["bm25_score"] = r.get("score", 0)
            r["score"] = r["bm25_score"] * 0.3
            seen[key] = r

    results = list(seen.values())
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def _rerank(query: str, results: List[Dict]) -> List[Dict]:
    """使用 BGE-Reranker 对结果重排序（优雅降级：模型不可用时跳过）"""
    try:
        from sentence_transformers import CrossEncoder
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        reranker_model = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

        # 懒加载 reranker 模型
        if not hasattr(_rerank, "_model") or _rerank._model is None:
            print(f"[rag_v2] 加载 Reranker 模型: {reranker_model}")
            try:
                from huggingface_hub import snapshot_download
                model_path = snapshot_download(reranker_model, local_files_only=True)
                _rerank._model = CrossEncoder(model_path)
            except Exception as e:
                print(f"[rag_v2] Reranker 模型不可用，跳过重排序: {e}")
                _rerank._model = False  # 标记为不可用
                return results
            print("[rag_v2] Reranker 模型加载完成")

        if _rerank._model is False:
            return results

        model = _rerank._model

        # 构建 query-document 对
        pairs = [(query, r.get("content", "")) for r in results]
        scores = model.predict(pairs)

        # 更新分数并重新排序
        for r, s in zip(results, scores):
            r["rerank_score"] = round(float(s), 4)
            r["score"] = round(float(s), 4)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results
    except Exception as e:
        print(f"[rag_v2] Reranker 跳过: {e}")
        return results
        return results


_rerank._model = None
