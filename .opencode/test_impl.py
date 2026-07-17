import urllib.request, json, urllib.error

login_data = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/login', data=login_data, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req, timeout=5)
login_resp = json.loads(r.read().decode())
token = login_resp.get('token', '')
print(f'Login OK, token={token[:30]}...')

def test(path):
    req = urllib.request.Request(f'http://127.0.0.1:8000{path}')
    req.add_header('Authorization', f'Bearer {token}')
    try:
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read().decode())
        print(f'OK {path}')
        return data
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode('utf-8', 'ignore')
        print(f'ERR {path}: {e.code} {body}')
        return None

test('/knowledge/api/unified-search?q=test')
test('/trace-anomaly/api/configs')
test('/agent/api/ground-truth/tests')
test('/agent/api/ground-truth/stats')
test('/anomaly/api/benchmark/stats?days=90')
test('/anomaly/api/benchmark?page=1&per_page=5')
test('/anomaly/api/benchmark/recommend')

r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/menu', headers={'Authorization': f'Bearer {token}'}), timeout=10)
menu = json.loads(r.read().decode())
flat = []
def walk(items):
    for i in items:
        flat.append(i.get('key',''))
        if 'items' in i: walk(i['items'])
data = menu.get('items', menu) if isinstance(menu, dict) else menu
walk(data)
print(f'MENU: {len(flat)} keys loaded')
keys_to_check = ['kb-documents','kb-graph','smart-recommend','trace-anomaly-config','agent-ground-truth','k8s-hpa-recommend','k8s-resource-optimize']
for k in keys_to_check:
    print(f'  {"OK" if k in flat else "MISSING"} menu key="{k}"')
