import requests
r = requests.post('http://localhost:8000/login', json={'username': 'admin', 'password': 'admin123'})
print(f'Status: {r.status_code}')
ct = r.headers.get('content-type', '')
print(f'Content-Type: {ct}')
print(f'Body: {r.text[:500]}')
