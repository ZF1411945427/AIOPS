"""RAG V2 完整流程测试"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["EMBEDDING_MODE"] = "bge-m3"

# ─── 测试 1: 手动创建文档 ───
print("=" * 60)
print("测试 1: 手动创建文档 + 自动索引")
print("=" * 60)

from app.database import get_session_for, get_db_mode
from app.models import KbDocument
from app.services import rag_engine_v2, vector_store

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()

# 清理旧测试数据
old_docs = db.query(KbDocument).filter(KbDocument.title.like("%RAG测试%")).all()
for d in old_docs:
    vector_store.delete_by_document(d.id)
    db.delete(d)
db.commit()
print(f"  清理旧测试数据: {len(old_docs)} 条")

# 创建测试文档
test_content = """
# Redis 常见故障排查手册

## 1. Redis 连接池耗尽

### 症状
应用报错 `Could not get a resource from the pool`，Redis 连接数飙升。

### 排查步骤
1. 执行 `redis-cli info clients` 查看当前连接数
2. 执行 `redis-cli client list` 查看连接详情
3. 检查应用端连接池配置（最大连接数、超时时间）

### 解决方案
- 增大 maxTotal 配置（建议 200-500）
- 设置合理的连接超时（建议 3000ms）
- 监控连接池使用率，设置告警阈值

## 2. Redis 内存溢出 OOM

### 症状
Redis 日志出现 `OOM command not allowed`，写入操作被拒绝。

### 排查步骤
1. 执行 `redis-cli info memory` 查看内存使用
2. 执行 `redis-cli --bigkeys` 扫描大 Key
3. 检查是否有未设置过期时间的 Key

### 解决方案
- 设置 maxmemory 和 maxmemory-policy
- 清理无用的大 Key
- 对大数据集使用 Hash 分片

## 3. Redis 主从同步延迟

### 症状
从节点读到旧数据，主从数据不一致。

### 排查步骤
1. 执行 `redis-cli info replication` 查看同步状态
2. 检查网络带宽和延迟
3. 检查 RDB/AOF 配置

### 解决方案
- 避免在主节点执行耗时操作
- 增大 repl-backlog-size
- 考虑使用 Redis Cluster 分片
"""

doc = KbDocument(
    title="RAG测试-Redis故障排查手册",
    content=test_content.strip(),
    source_type="manual",
    file_ext="txt",
    tags="redis,故障排查",
    asset_type="database",
    severity="warning",
    status="pending",
)
db.add(doc)
db.commit()
db.refresh(doc)
doc_id = doc.id
print(f"  创建文档 ID={doc_id}, 标题={doc.title}")

# ─── 测试 2: 索引到 Milvus ───
print("\n" + "=" * 60)
print("测试 2: 索引到 Milvus (BGE-M3 Embedding)")
print("=" * 60)

start = time.time()
success, msg = rag_engine_v2.index_document_v2(db, doc_id)
elapsed = time.time() - start
print(f"  结果: {success}, 消息: {msg}, 耗时: {elapsed:.1f}s")

if not success:
    print("  FAIL - 索引失败，终止测试")
    sys.exit(1)

# 验证文档状态
db.refresh(doc)
print(f"  文档状态: {doc.status}")
print(f"  切片数量: {doc.chunk_count}")
assert doc.status == "indexed", f"状态应为 indexed, 实际: {doc.status}"
assert doc.chunk_count > 0, f"切片数量应 > 0, 实际: {doc.chunk_count}"
print("  [OK] 索引成功")

# ─── 测试 3: 验证 Milvus 数据 ───
print("\n" + "=" * 60)
print("测试 3: 验证 Milvus 中的切片数据")
print("=" * 60)

client = vector_store.get_client()
results = client.query(
    collection_name=vector_store._COLLECTION_NAME,
    filter=f"document_id == {doc_id}",
    output_fields=["chunk_index", "content", "tags", "doc_title"],
    limit=100,
)
print(f"  Milvus 中切片数: {len(results)}")
assert len(results) > 0, "Milvus 中应有切片数据"

for i, r in enumerate(results[:3]):
    content_preview = r.get("content", "")[:80]
    print(f"  [{r.get('chunk_index')}] {content_preview}...")

if len(results) > 3:
    print(f"  ... 共 {len(results)} 条")
print("  [OK] Milvus 数据正确")

# ─── 测试 4: 向量搜索 ───
print("\n" + "=" * 60)
print("测试 4: 向量语义搜索")
print("=" * 60)

from app.services.embedding_service import embed_query
q_emb = embed_query("Redis连接池满了怎么办")
search_results = vector_store.search_by_vector(q_emb, top_k=3)
print(f"  查询: 'Redis连接池满了怎么办'")
print(f"  结果数: {len(search_results)}")
for r in search_results:
    print(f"  score={r['score']:.4f} | {r['content'][:60]}...")
assert len(search_results) > 0, "搜索应有结果"
print("  [OK] 向量搜索正常")

# ─── 测试 5: 混合搜索 ───
print("\n" + "=" * 60)
print("测试 5: 混合检索 (BM25 + 向量)")
print("=" * 60)

hybrid_results = rag_engine_v2.hybrid_search(
    query="Redis OOM 内存溢出",
    top_k=3,
)
print(f"  查询: 'Redis OOM 内存溢出'")
print(f"  结果数: {len(hybrid_results)}")
for r in hybrid_results:
    score = r.get("rerank_score") or r.get("score", 0)
    print(f"  score={score:.4f} | {r['content'][:60]}...")
assert len(hybrid_results) > 0, "混合搜索应有结果"
print("  [OK] 混合搜索正常")

# ─── 测试 6: API 路由注册检查 ───
print("\n" + "=" * 60)
print("测试 6: API 路由注册检查")
print("=" * 60)

from app.main import app
routes = [r.path for r in app.routes]
v2_routes = [r for r in routes if "/knowledge/v2" in r]
print(f"  V2 路由数: {len(v2_routes)}")
for r in v2_routes:
    print(f"    {r}")
assert any("/knowledge/v2/documents/{doc_id}/detail" in r for r in v2_routes), "详情接口未注册"
assert any("/knowledge/v2/search" in r for r in v2_routes), "搜索接口未注册"
assert any("/knowledge/v2/documents/upload" in r for r in v2_routes), "上传接口未注册"
print("  [OK] 路由注册正确")

# ─── 测试 7: 前端 openDetail 逻辑检查 ───
print("\n" + "=" * 60)
print("测试 7: 前端代码检查")
print("=" * 60)

vue_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "src", "views", "KnowledgeDocumentsView.vue")
with open(vue_file, "r", encoding="utf-8") as f:
    vue_content = f.read()

# 检查智能版 openDetail 是否调用 V2 接口
assert "v2Prefix" in vue_content and "documents/" in vue_content, "前端应使用 V2 接口"
assert "/detail" in vue_content, "前端应调用 /detail 接口"
assert "smartMode.value" in vue_content, "前端应有 smartMode 判断"
print("  [OK] 前端代码正确")

# ─── 清理 ───
print("\n" + "=" * 60)
print("清理测试数据")
print("=" * 60)
vector_store.delete_by_document(doc_id)
db.delete(doc)
db.commit()
db.close()
print("  [OK] 清理完成")

print("\n" + "=" * 60)
print("[DONE] 全部 7 项测试通过!")
print("=" * 60)
