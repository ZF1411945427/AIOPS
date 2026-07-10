import hashlib, sys
sys.path.insert(0, '.')
from app.database import get_session_for, get_db_mode
from app.models import User

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
users = db.query(User).all()
for u in users:
    print(f"User: {u.username}, hash: {u.password_hash}")
db.close()

# Check what admin123 hashes to
h = hashlib.sha256('admin123'.encode()).hexdigest()
print(f"admin123 hash: {h}")
