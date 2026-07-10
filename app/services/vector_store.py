"""Milvus 向量存储服务：Collection 管理、向量 CRUD.

使用 Milvus Lite（本地文件存储），部署到 Linux 时可无缝切换到 Milvus Standalone。
"""
import os
import json
from typing import Dict, List, Optional
from pathlib import Path

from pymilvus import MilvusClient, DataType

# 配置
_MILVUS_DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "docker" / "milvus" / "kb_v2.db")
_COLLECTION_NAME = "kb_chunks_v2"
_DIMENSION = 512  # BGE-small-zh 输出维度

# 全局客户端
_client: Optional[MilvusClient] = None


def get_client() -> MilvusClient:
    """获取 Milvus 客户端（单例）"""
    global _client
    if _client is not None:
        return _client
    os.makedirs(os.path.dirname(_MILVUS_DB_PATH), exist_ok=True)
    _client = MilvusClient(_MILVUS_DB_PATH)
    _ensure_collection()
    if _client.has_collection(_COLLECTION_NAME):
        _client.load_collection(_COLLECTION_NAME)
    return _client


def _ensure_collection():
    """确保 Collection 存在，不存在则创建"""
    client = _client
    if client.has_collection(_COLLECTION_NAME):
        return
    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=_DIMENSION)
    schema.add_field("document_id", DataType.INT64)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("content", DataType.VARCHAR, max_length=8192)
    schema.add_field("tags", DataType.VARCHAR, max_length=512)
    schema.add_field("asset_type", DataType.VARCHAR, max_length=64)
    schema.add_field("severity", DataType.VARCHAR, max_length=32)
    schema.add_field("source_type", DataType.VARCHAR, max_length=32)
    schema.add_field("doc_title", DataType.VARCHAR, max_length=512)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", metric_type="COSINE", index_type="FLAT")

    client.create_collection(
        collection_name=_COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )
    client.load_collection(_COLLECTION_NAME)
    print(f"[vector] Collection '{_COLLECTION_NAME}' 创建并加载完成")


def insert_chunks(chunks: List[Dict]):
    """批量插入切片向量
    
    chunks: [{"document_id": int, "chunk_index": int, "content": str,
              "embedding": List[float], "tags": str, "asset_type": str,
              "severity": str, "source_type": str, "doc_title": str}]
    """
    client = get_client()
    data = []
    for c in chunks:
        data.append({
            "embedding": c["embedding"],
            "document_id": c["document_id"],
            "chunk_index": c["chunk_index"],
            "content": c["content"][:8000],
            "tags": c.get("tags", ""),
            "asset_type": c.get("asset_type", ""),
            "severity": c.get("severity", ""),
            "source_type": c.get("source_type", ""),
            "doc_title": c.get("doc_title", ""),
        })
    if data:
        client.insert(collection_name=_COLLECTION_NAME, data=data)
        client.load_collection(_COLLECTION_NAME)


def search_by_vector(
    query_embedding: List[float],
    top_k: int = 5,
    score_threshold: float = 0.0,
    asset_type: Optional[str] = None,
    severity: Optional[str] = None,
    tags: Optional[str] = None,
) -> List[Dict]:
    """向量相似度检索
    
    返回: [{"id": int, "document_id": int, "content": str, "score": float, ...}]
    """
    client = get_client()
    search_params = {"metric_type": "COSINE", "params": {}}

    # 构建过滤条件
    filter_expr = None
    conditions = []
    if asset_type:
        conditions.append(f'asset_type == "{asset_type}"')
    if severity:
        conditions.append(f'severity == "{severity}"')
    if tags:
        conditions.append(f'tags like "%{tags}%"')
    if conditions:
        filter_expr = " and ".join(conditions)

    results = client.search(
        collection_name=_COLLECTION_NAME,
        data=[query_embedding],
        limit=min(top_k, 20),
        output_fields=["document_id", "chunk_index", "content", "tags", "asset_type", "severity", "source_type", "doc_title"],
        search_params=search_params,
        filter=filter_expr,
    )

    items = []
    for hits in results:
        for hit in hits:
            score = hit.get("distance", 0)
            if score < score_threshold:
                continue
            entity = hit.get("entity", {})
            items.append({
                "id": hit.get("id"),
                "document_id": entity.get("document_id"),
                "chunk_index": entity.get("chunk_index"),
                "content": entity.get("content", ""),
                "score": round(score, 4),
                "tags": entity.get("tags", ""),
                "asset_type": entity.get("asset_type", ""),
                "severity": entity.get("severity", ""),
                "source_type": entity.get("source_type", ""),
                "doc_title": entity.get("doc_title", ""),
            })
    return items


def delete_by_document(document_id: int):
    """删除指定文档的所有切片"""
    client = get_client()
    client.delete(
        collection_name=_COLLECTION_NAME,
        filter=f'document_id == {document_id}',
    )
    client.load_collection(_COLLECTION_NAME)


def get_stats() -> Dict:
    """获取统计信息"""
    client = get_client()
    try:
        info = client.get_collection_stats(_COLLECTION_NAME)
        return {
            "total_chunks": info.get("row_count", 0),
            "collection": _COLLECTION_NAME,
            "dimension": _DIMENSION,
        }
    except Exception:
        return {"total_chunks": 0, "collection": _COLLECTION_NAME, "dimension": _DIMENSION}
