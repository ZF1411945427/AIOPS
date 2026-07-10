import sys, traceback
sys.path.insert(0, '.')
from app.database import get_session_for, get_db_mode
from app.models import KbDocument
from app.services import rag_engine_v2

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
doc = db.query(KbDocument).filter(KbDocument.id == 4).first()
print(f"Doc: {doc.id}, status={doc.status}, content_len={len(doc.content or '')}")
db.close()

db2 = SessionLocal()
try:
    ok, msg = rag_engine_v2.index_document_v2(db2, 4)
    print(f"Result: ok={ok}, msg={msg}")
except Exception as e:
    traceback.print_exc()
db2.close()
