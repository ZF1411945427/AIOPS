"""RAG 检索质量评估服务（P2 任务#10）

把"RAG 效果好坏全靠主观"变成"有量化指标"。

标注集来源:
- 从 knowledge_base 表（已审批通过的知识）自动构造
- query = 知识 title 或 symptom（前 N 字）
- relevant_doc_id = 知识关联的 KbDocument（通过 KbChunk.document_id 反查）

评估指标:
- recall@k: 前 k 个结果中包含相关文档的比例
- MRR: 平均倒数排名（第一个相关文档排名倒数的平均）
- nDCG@k: 归一化折损累计增益
- 平均检索延迟: 每次 hybrid_search 耗时

缓存:
- 评估结果进程内缓存 60s，避免重复跑
- 可强制刷新
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import KnowledgeBase, KbDocument, KbChunk


# ── 评估结果缓存 ──
_EVAL_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_EVAL_TTL = 60.0  # 60 秒缓存


def _build_eval_dataset(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """从 knowledge_base 自动构造评估标注集"""
    kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.id.desc()).limit(limit).all()
    dataset: List[Dict[str, Any]] = []
    for kb in kbs:
        # 用 title 或 symptom 作为 query
        query = (kb.title or "").strip()
        if not query:
            continue
        # 找到该知识关联的文档（通过 KbChunk.document_id 反查，或 KbDocument.kb_id）
        doc_ids: set = set()
        # KbDocument.kb_id 直接关联
        docs = db.query(KbDocument).filter(KbDocument.kb_id == kb.id).all()
        for d in docs:
            doc_ids.add(d.id)
        # 通过 KbChunk 间接关联（按 tags / asset_type 模糊匹配）
        if not doc_ids and kb.tags:
            tag_list = [t.strip() for t in (kb.tags or "").split(",") if t.strip()]
            if tag_list:
                # 用第一个 tag 匹配 KbDocument.tags
                first_tag = tag_list[0]
                tag_docs = db.query(KbDocument).filter(KbDocument.tags.like(f"%{first_tag}%")).limit(3).all()
                for d in tag_docs:
                    doc_ids.add(d.id)
        # 如果完全找不到关联文档，跳过（无法评估）
        if not doc_ids:
            continue
        dataset.append({
            "query": query,
            "kb_id": kb.id,
            "kb_title": kb.title,
            "relevant_doc_ids": sorted(doc_ids),
            "tags": kb.tags or "",
            "asset_type": kb.asset_type or "",
        })
    return dataset


def _recall_at_k(retrieved_doc_ids: List[int], relevant_doc_ids: List[int], k: int) -> float:
    """recall@k: 前 k 个结果中包含相关文档的比例"""
    if not relevant_doc_ids:
        return 0.0
    top_k = retrieved_doc_ids[:k]
    hits = sum(1 for d in top_k if d in relevant_doc_ids)
    return hits / len(relevant_doc_ids)


def _mrr(retrieved_doc_ids: List[int], relevant_doc_ids: List[int]) -> float:
    """MRR: 第一个相关文档排名倒数的平均（这里返回单条记录的倒数排名）"""
    for i, did in enumerate(retrieved_doc_ids, start=1):
        if did in relevant_doc_ids:
            return 1.0 / i
    return 0.0


def _ndcg_at_k(retrieved_doc_ids: List[int], relevant_doc_ids: List[int], k: int) -> float:
    """nDCG@k: 归一化折损累计增益

    DCG = sum(rel_i / log2(i+1)) for i in 1..k
    IDCG = 理想排序的 DCG
    nDCG = DCG / IDCG
    """
    if not relevant_doc_ids:
        return 0.0
    # 二值相关性: 命中=1，未命中=0
    rels = [1.0 if d in relevant_doc_ids else 0.0 for d in retrieved_doc_ids[:k]]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))
    # 理想排序: 相关文档全部排在前 len(relevant_doc_ids) 位
    ideal_len = min(len(relevant_doc_ids), k)
    ideal_rels = [1.0] * ideal_len + [0.0] * (k - ideal_len)
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_rels))
    return dcg / idcg if idcg > 0 else 0.0


def run_eval(db: Session, top_k: int = 5, limit: int = 50) -> Dict[str, Any]:
    """运行 RAG 检索质量评估"""
    from app.services.rag_engine_v2 import hybrid_search

    t0 = time.time()
    dataset = _build_eval_dataset(db, limit=limit)

    if not dataset:
        return {
            "warning": "未构造到评估样本（需 knowledge_base 有关联的 KbDocument）",
            "summary": {
                "sample_count": 0, "recall_at_5": 0, "mrr": 0, "ndcg_at_5": 0,
                "avg_latency_ms": 0, "elapsed_ms": int((time.time() - t0) * 1000),
                "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "samples": [],
        }

    samples: List[Dict[str, Any]] = []
    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    latency_sum = 0.0
    success_count = 0

    for item in dataset:
        query = item["query"]
        relevant = item["relevant_doc_ids"]
        try:
            t1 = time.time()
            results = hybrid_search(query, top_k=top_k * 2)  # 多检索一些用于评估
            latency_ms = (time.time() - t1) * 1000
        except Exception as e:
            logger.warning(f"RAG eval: hybrid_search 失败 query={query!r}: {e}")
            samples.append({
                **item,
                "retrieved_doc_ids": [],
                "recall_at_k": 0.0,
                "mrr": 0.0,
                "ndcg_at_k": 0.0,
                "latency_ms": 0.0,
                "error": str(e),
            })
            continue

        retrieved_doc_ids = [r.get("document_id") for r in results if r.get("document_id") is not None]
        r_at_k = _recall_at_k(retrieved_doc_ids, relevant, top_k)
        mrr_v = _mrr(retrieved_doc_ids, relevant)
        ndcg_v = _ndcg_at_k(retrieved_doc_ids, relevant, top_k)

        samples.append({
            **item,
            "retrieved_doc_ids": retrieved_doc_ids[:top_k * 2],
            "retrieved_count": len(retrieved_doc_ids),
            "recall_at_k": round(r_at_k, 4),
            "mrr": round(mrr_v, 4),
            "ndcg_at_k": round(ndcg_v, 4),
            "latency_ms": round(latency_ms, 2),
        })
        recall_sum += r_at_k
        mrr_sum += mrr_v
        ndcg_sum += ndcg_v
        latency_sum += latency_ms
        success_count += 1

    n = max(success_count, 1)
    summary = {
        "sample_count": len(dataset),
        "success_count": success_count,
        "top_k": top_k,
        "recall_at_k": round(recall_sum / n, 4),
        "mrr": round(mrr_sum / n, 4),
        "ndcg_at_k": round(ndcg_sum / n, 4),
        "avg_latency_ms": round(latency_sum / n, 2),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {
        "summary": summary,
        "samples": samples,
    }


def get_eval_cached(db: Session, top_k: int = 5, limit: int = 50, force_refresh: bool = False) -> Dict[str, Any]:
    """带 60s 缓存的评估"""
    now = time.time()
    cache_key = f"{top_k}:{limit}"
    if (not force_refresh
            and _EVAL_CACHE["data"] is not None
            and _EVAL_CACHE.get("key") == cache_key
            and now - _EVAL_CACHE["ts"] < _EVAL_TTL):
        return _EVAL_CACHE["data"]
    data = run_eval(db, top_k=top_k, limit=limit)
    _EVAL_CACHE["ts"] = now
    _EVAL_CACHE["key"] = cache_key
    _EVAL_CACHE["data"] = data
    return data


def get_dataset(db: Session, limit: int = 50) -> Dict[str, Any]:
    """获取当前评估数据集（不跑检索，只展示标注集）"""
    dataset = _build_eval_dataset(db, limit=limit)
    return {
        "total": len(dataset),
        "samples": dataset,
    }
