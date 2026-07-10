import requests
r = requests.post('http://localhost:8000/login', json={'username': 'admin', 'password': '1234'})
token = r.json().get('token', '')
r2 = requests.get('http://localhost:8000/knowledge/graph/api/graph', headers={'Authorization': f'Bearer {token}'})
d = r2.json()
print(f"nodes: {len(d.get('nodes', []))}, edges: {len(d.get('edges', []))}")
print(f"node_count: {d.get('node_count')}, edge_count: {d.get('edge_count')}")
for n in d.get('nodes', [])[:3]:
    print(f"  node: {n}")
for e in d.get('edges', [])[:3]:
    print(f"  edge: {e}")
