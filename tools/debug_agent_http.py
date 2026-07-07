import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

# Login
r = client.post('/login', json={'username': 'admin', 'password': 'admin123'})
print(f'Login: {r.status_code}')
cookie_val = r.cookies.get('session')
print(f'Session: {cookie_val[:40] if cookie_val else "none"}...')

# Call agent
r2 = client.post(
    '/agent/chat/send',
    json={'session_id': None, 'message': 'ping'},
    cookies={'session': cookie_val}
)
print(f'Agent chat: {r2.status_code}')
if r2.status_code == 200:
    data = r2.json()
    print(f'Reply (first 200): {data.get("reply", "")[:200]}')
    print(f'Pending: {len(data.get("pending_actions", []))}')
else:
    print(f'Error body: {r2.text[:500]}')
