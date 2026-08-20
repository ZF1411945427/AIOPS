"""RAG 引擎单测: 切片/分词/TF-IDF/余弦相似度/索引/检索/文档归档。

覆盖 app/services/rag_service.py 核心链路。
"""
import json
import math
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import KbChunk, KbDocument
from app.services import rag_service


class TestChunk:
    def test_chunk_text_small(self):
        chunks = rag_service.chunk_text("hello world and some more text here for testing", chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert len(chunks[0]) >= 20

    def test_chunk_text_split(self):
        text = "word " * 200
        chunks = rag_service.chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) >= 2

    def test_chunk_text_empty(self):
        assert rag_service.chunk_text("", chunk_size=500, overlap=100) == []


class TestTokenize:
    def test_tokenize_english(self):
        toks = rag_service.tokenize("hello world")
        assert len(toks) >= 2
        assert "hello" in toks

    def test_tokenize_chinese(self):
        toks = rag_service.tokenize("你好世界")
        assert len(toks) >= 1

    def test_tokenize_empty(self):
        assert rag_service.tokenize("") == []


class TestTfidf:
    def test_build_tfidf_vector(self):
        tokens = ["a", "b", "a", "c"]
        idf = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 0.5}
        vec = rag_service.build_tfidf_vector(tokens, idf)
        assert "a" in vec
        assert "b" in vec
        assert vec["a"] > 0

    def test_tfidf_empty_tokens(self):
        assert rag_service.build_tfidf_vector([], {}) == {}


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = {"a": 1.0, "b": 2.0}
        sim = rag_service.cosine_similarity(v, v)
        assert sim == pytest.approx(1.0, rel=1e-4)

    def test_orthogonal_vectors(self):
        v1 = {"a": 1.0}
        v2 = {"b": 1.0}
        sim = rag_service.cosine_similarity(v1, v2)
        assert sim == pytest.approx(0.0, abs=1e-6)

    def test_zero_vector(self):
        sim = rag_service.cosine_similarity({}, {})
        assert sim == 0.0

    def test_partial_match(self):
        v1 = {"a": 1.0, "b": 0.0}
        v2 = {"a": 1.0, "c": 1.0}
        sim = rag_service.cosine_similarity(v1, v2)
        assert 0 < sim < 1.0


class TestDocumentCRUD:
    def test_create_document(self, db: Session):
        doc = rag_service.create_document(db, {
            "title": "测试文档", "content": "hello world",
            "source_type": "manual", "status": "pending",
        })
        assert doc.id is not None
        assert doc.title == "测试文档"

    def test_get_document_not_found(self, db: Session):
        assert rag_service.get_document(db, 99999) is None

    def test_list_documents(self, db: Session):
        rag_service.create_document(db, {
            "title": "doc1", "content": "a", "source_type": "manual", "status": "pending",
        })
        rag_service.create_document(db, {
            "title": "doc2", "content": "b", "source_type": "manual", "status": "pending",
        })
        docs = rag_service.list_documents(db)
        assert len(docs) >= 2

    def test_update_document(self, db: Session):
        doc = rag_service.create_document(db, {
            "title": "old", "content": "old content",
            "source_type": "manual", "status": "pending",
        })
        updated = rag_service.update_document(db, doc.id, {"title": "new"})
        assert updated is not None
        assert updated.title == "new"

    def test_delete_document(self, db: Session):
        doc = rag_service.create_document(db, {
            "title": "del", "content": "to delete",
            "source_type": "manual", "status": "pending",
        })
        rag_service.delete_document(db, doc.id)
        assert rag_service.get_document(db, doc.id) is None


class TestIndexAndSearch:
    def test_index_document_creates_chunks(self, db: Session):
        doc = rag_service.create_document(db, {
            "title": "索引测试", "content": "服务器 CPU 使用率过高 内存不足 磁盘 IO 繁忙",
            "source_type": "manual", "status": "pending",
        })
        ok, msg = rag_service.index_document(db, doc.id)
        assert ok, f"索引失败: {msg}"
        chunks = rag_service.list_chunks(db, doc.id)
        assert len(chunks) >= 1

    def test_index_empty_content(self, db: Session):
        doc = rag_service.create_document(db, {
            "title": "空文档", "content": "",
            "source_type": "manual", "status": "pending",
        })
        ok, _ = rag_service.index_document(db, doc.id)
        assert ok is False

    def test_vector_search_returns_results(self, db: Session):
        rag_service.invalidate_idf_cache()
        doc = rag_service.create_document(db, {
            "title": "知识文档",
            "content": "服务器 CPU 使用率过高 内存不足 磁盘 IO 繁忙 需要及时处理并恢复服务",
            "source_type": "manual", "asset_type": "server",
            "status": "pending", "tags": "cpu,memory",
        })
        rag_service.index_document(db, doc.id)
        results = rag_service.vector_search(db, "CPU 过高", top_k=3)
        assert len(results) >= 1
        assert results[0]["similarity"] > 0

    def test_vector_search_empty_query(self, db: Session):
        assert rag_service.vector_search(db, "") == []

    def test_vector_search_with_filter(self, db: Session):
        rag_service.invalidate_idf_cache()
        doc = rag_service.create_document(db, {
            "title": "server doc",
            "content": "linux 服务器配置 需要安装必要的监控组件并验证连通性",
            "source_type": "manual", "asset_type": "server",
            "status": "pending", "tags": "linux",
        })
        rag_service.index_document(db, doc.id)
        results = rag_service.vector_search(db, "linux", top_k=3, asset_type="server")
        assert len(results) >= 1
        results_none = rag_service.vector_search(db, "linux", top_k=3, asset_type="database")
        assert len(results_none) == 0


class TestArchiveCase:
    def test_archive_alert_case(self, db: Session):
        doc = rag_service.archive_alert_case(
            db, alert_id=1, title="CPU 高负载",
            content="CPU 使用率持续 95% 超过 10 分钟",
            tags="cpu,performance", asset_type="server",
        )
        assert doc is not None
        assert doc.source_type == "alert_case"
        assert "CPU 高负载" in doc.title

    def test_archive_incident_case(self, db: Session):
        doc = rag_service.archive_incident_case(
            db, incident_id=1, title="数据库连接失败",
            content="数据库连接池耗尽",
            tags="database,connection",
        )
        assert doc is not None
        assert doc.source_type == "incident_case"