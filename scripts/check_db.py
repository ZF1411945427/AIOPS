"""Check docs directly from DB"""
import sys
sys.path.insert(0, '.')
from app.database import get_session_for, get_db_mode
from app.models import KbDocument

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
docs = db.query(KbDocument).all()
for d in docs:
    print(f"  [{d.id}] {d.title} - status: {d.status}, chunks: {d.chunk_count}, ext: {d.file_ext}")
db.close()
