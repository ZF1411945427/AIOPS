from app.services.rag_engine_v2 import hybrid_search


def search_with_rerank(
    query: str,
    top_k: int = 5,
    rerank_mode: str = "classic",
    **kwargs,
):
    """两阶段检索：向量+BM25 召回 → Reranker 重排。

    rerank_mode:
      - "classic": 轻量规则重排（CPU，无额外依赖）
      - "smart": AuroraX-Reranker GPU 重排（需要 GPU）
      - "none": 不重排，直接返回混合召回结果
    """
    return hybrid_search(
        query=query,
        top_k=top_k,
        rerank_mode=rerank_mode,
        **kwargs,
    )
