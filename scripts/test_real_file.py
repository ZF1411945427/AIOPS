"""用真实文件测试上传速度"""
import os, sys, time
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, ".")

from app.database import get_session_for, get_db_mode
from app.models import KbDocument
from app.services import rag_engine_v2, vector_store, rag_service

FILE_PATH = r"D:\AIOPS\project07\功能测试\K8s运维故障排查手册.md"
SessionLocal = get_session_for(get_db_mode())

# 读取文件
with open(FILE_PATH, "r", encoding="utf-8") as f:
    content = f.read()

print(f"File: {os.path.basename(FILE_PATH)}")
print(f"Size: {len(content)} chars, {len(content.splitlines())} lines")

# 清理旧数据
db = SessionLocal()
old = db.query(KbDocument).filter(KbDocument.title.like("%K8s%排查手册%")).all()
for d in old:
    try: vector_store.delete_by_document(d.id)
    except: pass
    db.delete(d)
db.commit()
db.close()

# ===== 上传 1 =====
print("\n=== Upload 1 ===")
db = SessionLocal()
doc = KbDocument(
    title="K8s运维故障排查手册",
    content=content,
    source_type="upload",
    file_ext="md",
    tags="k8s,故障排查",
    asset_type="container",
    severity="warning",
    status="pending",
)
db.add(doc)
db.commit()
db.refresh(doc)
doc_id = doc.id
print(f"  Doc created: id={doc_id}")
db.close()

db2 = SessionLocal()
t0 = time.time()
ok, msg = rag_engine_v2.index_document_v2(db2, doc_id)
t1 = time.time()
db2.close()

# 验证状态
db3 = SessionLocal()
doc3 = db3.query(KbDocument).filter(KbDocument.id == doc_id).first()
status = doc3.status if doc3 else "N/A"
chunks_count = doc3.chunk_count if doc3 else 0
db3.close()

print(f"  Time: {t1-t0:.1f}s")
print(f"  Result: ok={ok}, msg={msg}")
print(f"  Status: {status}")
print(f"  Chunks: {chunks_count}")

# ===== 上传 2 (模型已缓存) =====
print("\n=== Upload 2 (cached) ===")
db4 = SessionLocal()
doc2 = KbDocument(
    title="K8s运维故障排查手册-v2",
    content=content,
    source_type="upload",
    file_ext="md",
    tags="k8s,故障排查",
    asset_type="container",
    severity="warning",
    status="pending",
)
db4.add(doc2)
db4.commit()
db4.refresh(doc2)
doc_id2 = doc2.id
db4.close()

db5 = SessionLocal()
t2 = time.time()
ok2, msg2 = rag_engine_v2.index_document_v2(db5, doc_id2)
t3 = time.time()
db5.close()

db6 = SessionLocal()
doc6 = db6.query(KbDocument).filter(KbDocument.id == doc_id2).first()
status2 = doc6.status if doc6 else "N/A"
chunks2 = doc6.chunk_count if doc6 else 0
db6.close()

print(f"  Time: {t3-t2:.1f}s")
print(f"  Result: ok={ok2}, msg={msg2}")
print(f"  Status: {status2}")
print(f"  Chunks: {chunks2}")

# ===== 上传 3 =====
print("\n=== Upload 3 ===")
db7 = SessionLocal()
doc4 = KbDocument(
    title="K8s运维故障排查手册-v3",
    content=content,
    source_type="upload",
    file_ext="md",
    tags="k8s",
    asset_type="container",
    severity="warning",
    status="pending",
)
db7.add(doc4)
db7.commit()
db7.refresh(doc4)
doc_id3 = doc4.id
db7.close()

db8 = SessionLocal()
t4 = time.time()
ok3, msg3 = rag_engine_v2.index_document_v2(db8, doc_id3)
t5 = time.time()
db8.close()

db9 = SessionLocal()
doc9 = db9.query(KbDocument).filter(KbDocument.id == doc_id3).first()
status3 = doc9.status if doc9 else "N/A"
chunks3 = doc9.chunk_count if doc9 else 0
db9.close()

print(f"  Time: {t5-t4:.1f}s")
print(f"  Result: ok={ok3}, msg={msg3}")
print(f"  Status: {status3}")
print(f"  Chunks: {chunks3}")

# cleanup
for did in [doc_id, doc_id2, doc_id3]:
    try: vector_store.delete_by_document(did)
    except: pass
    ddb = SessionLocal()
    dd = ddb.query(KbDocument).filter(KbDocument.id == did).first()
    if dd: ddb.delete(dd); ddb.commit()
    ddb.close()

print("\n=== DONE ===")
