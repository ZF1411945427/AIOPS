"""RAG 引擎 V2：文档切片 → Embedding → Milvus 存储 → 混合检索 → Reranker.

完整 Pipeline：
1. 文档解析（复用现有 rag_service.parse_document）
2. 智能切片（语义分界 > 段落 > 字符）
3. BGE-M3 Embedding 生成
4. Milvus 向量存储
5. 混合检索（BM25 关键词 + 向量语义）
6. Reranker 重排序
"""
import os
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import KbDocument, KbChunk
from app.services import rag_service
from app.services import embedding_service
from app.services import vector_store

from app.logger import logger


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

        # 使 BM25 缓存失效（下次查询时重建）
        invalidate_bm25_cache()

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
    rerank_mode: Optional[str] = None,
) -> List[Dict]:
    """混合检索：BM25 关键词 + 向量语义 + Reranker 重排序

    流程：
    1. BM25 关键词检索（从 Milvus 全量切片中筛选）
    2. 向量语义检索（BGE-M3 Embedding + 余弦相似度）
    3. 合并结果（去重）
    4. Reranker 重排序（经典版/智能版）
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
        from app.logger import logger
        logger.warning(f"向量检索失败: {e}")
        vector_results = []

    # 2. BM25 关键词检索（从向量结果中补充关键词匹配）
    bm25_results = _bm25_search(query, top_k=min(top_k * 2, 20))

    # 3. 合并去重
    merged = _merge_results(vector_results, bm25_results)

    # 4. Reranker 重排序
    if len(merged) > 1:
        merged = _rerank(query, merged, mode=rerank_mode)

    # 5. 返回 Top-K
    return merged[:top_k]


def _bm25_search(query: str, top_k: int = 10) -> List[Dict]:
    """BM25 关键词检索（基于 rank_bm25），带内存缓存"""
    try:
        from rank_bm25 import BM25Okapi
        import time as _time

        # ── BM25 索引缓存（TTL=300s，文档索引时自动失效）──
        global _bm25_cache
        _now = _time.time()
        if _bm25_cache is None or _now - _bm25_cache["ts"] > 300:
            client = vector_store.get_client()
            all_chunks = client.query(
                collection_name=vector_store._COLLECTION_NAME,
                output_fields=["document_id", "chunk_index", "content", "tags", "asset_type", "severity", "source_type", "doc_title"],
                limit=10000,
            )
            if not all_chunks:
                return []

            def tokenize(text):
                tokens = re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z0-9]+', text.lower())
                return tokens

            corpus = [c.get("content", "") for c in all_chunks]
            tokenized_corpus = [tokenize(doc) for doc in corpus]
            bm25 = BM25Okapi(tokenized_corpus)

            _bm25_cache = {
                "ts": _now,
                "bm25": bm25,
                "chunks": all_chunks,
                "max_score": 1e-6,
            }
            logger.info(f"BM25 索引重建完成: {len(all_chunks)} 个切片")

        bm25 = _bm25_cache["bm25"]
        all_chunks = _bm25_cache["chunks"]

        def tokenize(text):
            tokens = re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z0-9]+', text.lower())
            return tokens

        tokenized_query = tokenize(query)
        scores = bm25.get_scores(tokenized_query)

        import numpy as np
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            chunk = dict(all_chunks[idx])  # copy to avoid mutating cache
            chunk["score"] = round(float(scores[idx]) / max(scores.max(), 1e-6), 4)
            results.append(chunk)
        return results
    except Exception as e:
        logger.warning(f"BM25 检索失败: {e}")
        return []


_bm25_cache = None


def invalidate_bm25_cache():
    """文档索引后调用，使 BM25 缓存失效"""
    global _bm25_cache
    _bm25_cache = None


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


def _lightweight_rerank(query: str, results: List[Dict]) -> List[Dict]:
    """经典版 Reranker：基于多特征混合打分，无需额外模型下载，CPU 零开销.

    特征权重：
    1. 关键词匹配覆盖率 (40%)：query 中关键词在文档中出现的比例
    2. 向量语义相似度 (30%)：复用向量检索分数
    3. BM25 关键词分数 (20%)：复用 BM25 检索分数
    4. 文档长度归一化 (10%)：过长文档适当降权，避免信息稀释
    """
    if not query or not results:
        return results

    query_tokens = set(re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z0-9]+', query.lower()))
    if not query_tokens:
        return results

    max_len = max((len(r.get("content", "")) for r in results), default=1) or 1

    for r in results:
        content = r.get("content", "")
        content_lower = content.lower()
        content_tokens = set(re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z0-9]+', content_lower))

        matched = query_tokens & content_tokens
        coverage = len(matched) / len(query_tokens) if query_tokens else 0

        vector_score = r.get("vector_score", 0)
        bm25_score = r.get("bm25_score", 0)
        length_penalty = 1.0 - (len(content) / max_len) * 0.3

        rerank_score = (
            coverage * 0.40
            + min(float(vector_score), 1.0) * 0.30
            + min(float(bm25_score), 1.0) * 0.20
            + length_penalty * 0.10
        )

        r["rerank_score"] = round(rerank_score, 4)
        r["rerank_method"] = "classic"
        r["score"] = round(rerank_score, 4)

    results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return results


# ─── 智能版 Reranker (AuroraX) ──────────────────────────────────

_aurorax_model = None
_aurorax_tokenizer = None
_aurorax_checked = False
_rerank_mode = "classic"  # "classic" | "smart"


def _load_aurorax_model():
    """懒加载 AuroraX-Reranker 模型（需要 GPU + CUDA 版 PyTorch）"""
    global _aurorax_model, _aurorax_tokenizer, _aurorax_checked
    if _aurorax_checked:
        return _aurorax_model is not None
    _aurorax_checked = True

    try:
        import torch
        if not torch.cuda.is_available():
            logger.info("AuroraX Reranker: CUDA 不可用，智能版不可用")
            return False

        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        from app.config import PROJECT_ROOT
        model_path = str(PROJECT_ROOT / "models" / "AuroraX-Reranker-Base-v1.0")

        if not os.path.isdir(model_path):
            logger.info(f"AuroraX 模型目录不存在: {model_path}")
            return False

        logger.info("正在加载 AuroraX Reranker 模型...")
        _aurorax_tokenizer = AutoTokenizer.from_pretrained(model_path)
        _aurorax_model = AutoModelForSequenceClassification.from_pretrained(model_path)
        _aurorax_model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _aurorax_model = _aurorax_model.to(device)
        logger.info(f"AuroraX Reranker 加载成功，运行在 {device} 上")
        return True
    except Exception as e:
        logger.warning(f"AuroraX Reranker 加载失败: {e}")
        return False


def _aurorax_rerank(query: str, results: List[Dict]) -> List[Dict]:
    """智能版 Reranker：基于 AuroraX (ModernBert) 神经网络模型，需要 GPU."""
    if not query or not results:
        return results

    import torch

    if not _load_aurorax_model():
        return _lightweight_rerank(query, results)

    try:
        pairs = [(query, r.get("content", "")) for r in results]
        inputs = _aurorax_tokenizer(
            [p[0] for p in pairs],
            [p[1] for p in pairs],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        device = next(_aurorax_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = _aurorax_model(**inputs)
        logits = outputs.logits.squeeze(-1)
        scores = torch.sigmoid(logits).cpu().tolist()
        if isinstance(scores, float):
            scores = [scores]

        for r, s in zip(results, scores):
            r["rerank_score"] = round(float(s), 4)
            r["rerank_method"] = "smart"
            r["score"] = round(float(s), 4)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results
    except Exception as e:
        logger.warning(f"AuroraX Reranker 推理失败，降级到经典版: {e}")
        return _lightweight_rerank(query, results)


# ─── Reranker 统一入口 ──────────────────────────────────────────

def set_rerank_mode(mode: str):
    """设置 Reranker 模式：classic（经典版）| smart（智能版，需 GPU）"""
    global _rerank_mode
    if mode not in ("classic", "smart"):
        raise ValueError(f"不支持的 Reranker 模式: {mode}")
    if mode == "smart":
        if not _load_aurorax_model():
            raise ValueError(
                "智能版不可用：未检测到 GPU 或 AuroraX 模型未加载。"
                "请安装 CUDA 版 PyTorch 并确认 models/AuroraX-Reranker-Base-v1.0 已下载"
            )
    _rerank_mode = mode
    logger.info(f"Reranker 模式切换为: {mode}")


def get_rerank_mode() -> str:
    return _rerank_mode


def _rerank(query: str, results: List[Dict], mode: Optional[str] = None) -> List[Dict]:
    """统一 Reranker 入口：根据 mode 参数或全局设置选择经典版/智能版."""
    if not results or len(results) <= 1:
        return results

    use_mode = mode or _rerank_mode

    if use_mode == "smart":
        return _aurorax_rerank(query, results)
    return _lightweight_rerank(query, results)


def get_reranker_status() -> Dict:
    """获取 Reranker 状态（供前端展示）"""
    aurorax_available = False
    device = "none"

    if _aurorax_model is not None:
        aurorax_available = True
        import torch
        device = "cuda" if next(_aurorax_model.parameters()).device.type == "cuda" else "cpu"
    elif _aurorax_checked:
        aurorax_available = False

    return {
        "enabled": True,
        "mode": _rerank_mode,
        "classic": {
            "name": "经典版",
            "description": "多特征混合打分 (关键词覆盖40% + 向量30% + BM25 20% + 长度归一化10%)",
            "available": True,
            "speed": "0.07ms / 52 docs",
        },
        "smart": {
            "name": "智能版",
            "description": "AuroraX-Reranker (ModernBert, 300M params, GPU加速)",
            "available": aurorax_available,
            "device": device,
        },
    }
