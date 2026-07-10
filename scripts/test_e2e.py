"""模拟前端完整流程: 创建 -> 列表 -> 详情 -> 搜索"""
import sys, os, time
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, '.')

from app.database import get_session_for, get_db_mode
from app.models import KbDocument
from app.services import rag_engine_v2, vector_store, embedding_service

SessionLocal = get_session_for(get_db_mode())

# ===== Step 1: 创建文档 =====
print("[1] CREATE document...")
db = SessionLocal()
doc = KbDocument(
    title="E2E-RAG测试-MySQL故障",
    content="MySQL慢查询导致CPU飙升100%。排查步骤：1.执行SHOW PROCESSLIST查看当前查询 2.使用EXPLAIN分析执行计划 3.检查索引是否缺失。解决方案：添加复合索引、优化SQL语句、设置慢查询日志阈值。",
    source_type="manual", file_ext="txt", tags="mysql,慢查询",
    asset_type="database", severity="critical", status="pending",
)
db.add(doc); db.commit(); db.refresh(doc)
doc_id = doc.id
print(f"  Created doc id={doc_id}")
db.close()

# ===== Step 2: 索引（模拟上传后自动触发） =====
print("[2] INDEX to Milvus...")
db2 = SessionLocal()
t0 = time.time()
ok, msg = rag_engine_v2.index_document_v2(db2, doc_id)
elapsed = time.time() - t0
print(f"  Result: ok={ok}, msg={msg}, elapsed={elapsed:.1f}s")
db2.close()

if not ok:
    print("  FAIL: index failed")
    sys.exit(1)

# ===== Step 3: 列表（验证状态） =====
print("[3] LIST documents...")
db3 = SessionLocal()
docs = db3.query(KbDocument).filter(KbDocument.title.like("%E2E-RAG%")).all()
for d in docs:
    print(f"  id={d.id} title={d.title} status={d.status} chunks={d.chunk_count}")
assert any(d.status == "indexed" and d.chunk_count > 0 for d in docs), "No indexed doc found"
print("  OK: status=indexed, chunks > 0")
db3.close()

# ===== Step 4: 详情（模拟 openDetail） =====
print("[4] DETAIL (content + chunks)...")
db4 = SessionLocal()
doc = db4.query(KbDocument).filter(KbDocument.id == doc_id).first()
assert doc is not None, "Doc not found"
assert doc.content and len(doc.content) > 10, f"Content too short: {len(doc.content or '')}"

client = vector_store.get_client()
chunks = client.query(
    collection_name=vector_store._COLLECTION_NAME,
    filter=f"document_id == {doc_id}",
    output_fields=["chunk_index", "content"],
    limit=100,
)
print(f"  Content length: {len(doc.content)} chars")
print(f"  Chunks count: {len(chunks)}")
assert len(chunks) > 0, "Chunks should not be empty"
for c in chunks:
    print(f"    [{c.get('chunk_index')}] {c.get('content', '')[:80]}...")
print("  OK: content present, chunks not empty")
db4.close()

# ===== Step 5: 搜索 =====
print("[5] SEARCH (semantic + keyword)...")
q_emb = embedding_service.embed_query("MySQL CPU高怎么处理")
results = vector_store.search_by_vector(q_emb, top_k=3)
print(f"  Query: 'MySQL CPU高怎么处理'")
print(f"  Hits: {len(results)}")
for r in results:
    print(f"    score={r['score']:.4f} | {r['content'][:60]}...")
assert len(results) > 0, "Search should return results"
print("  OK: search works")

# ===== Cleanup =====
print("\n[CLEANUP]...")
vector_store.delete_by_document(doc_id)
db5 = SessionLocal()
doc5 = db5.query(KbDocument).filter(KbDocument.id == doc_id).first()
if doc5:
    db5.delete(doc5)
    db5.commit()
db5.close()
print("  Done")

print("\n===== ALL E2E TESTS PASSED =====")
