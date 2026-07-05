import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:8000'
s = requests.Session()
r = s.post(f'{BASE}/login', data={'username': 'admin', 'password': 'admin123'}, allow_redirects=False)
print(f'login: {r.status_code}')

GET_APIS = [
    ('K8s overview', '/k8s/api/overview'),
    ('K8s statefulsets', '/k8s/api/statefulsets'),
    ('K8s daemonsets', '/k8s/api/daemonsets'),
    ('K8s services', '/k8s/api/services'),
    ('K8s ingresses', '/k8s/api/ingresses'),
    ('K8s configmaps', '/k8s/api/configmaps'),
    ('K8s secrets', '/k8s/api/secrets'),
    ('K8s hpas', '/k8s/api/hpas'),
    ('K8s pvcs', '/k8s/api/pvcs'),
    ('K8s pvs', '/k8s/api/pvs'),
    ('K8s monitor', '/k8s-monitor/api/list'),
    ('Containers overview', '/containers/api/overview'),
    ('Containers docker', '/containers/api/docker'),
    ('Containers pods', '/containers/api/pods'),
    ('Containers deployments', '/containers/api/deployments'),
    ('Containers topology graph', '/containers/topology/graph'),
    ('Knowledge list', '/knowledge/api/list'),
    ('Knowledge documents list', '/knowledge/documents/api/list'),
    ('Knowledge graph', '/knowledge/graph/api/graph'),
    ('Runbooks list', '/runbooks/api/list'),
    ('Smart recommend', '/smart-recommend/api/recommend?alert_id=1'),
    ('Lifecycle list', '/lifecycle/api/list'),
    ('Topology list', '/topology/api/list'),
    ('Api v1 docs', '/api/v1/api/docs'),
]

ok = 0
fail = 0
for name, path in GET_APIS:
    try:
        r = s.get(f'{BASE}{path}', timeout=15)
        marker = 'OK' if r.status_code == 200 else 'FAIL'
        if r.status_code == 200:
            ok += 1
        else:
            fail += 1
        try:
            data = r.json()
            keys = list(data.keys())[:6] if isinstance(data, dict) else f'list[{len(data)}]'
            print(f'[{marker}] {name:30s} {r.status_code} keys={keys}')
        except Exception:
            print(f'[{marker}] {name:30s} {r.status_code} (non-json) len={len(r.text)}')
    except Exception as e:
        fail += 1
        print(f'[ERR ] {name:30s} {e}')

HTML_FALLBACK = [
    ('k8s-monitor', '/k8s-monitor'),
    ('topology', '/topology'),
    ('topology/path', '/topology/path'),
    ('lifecycle', '/lifecycle'),
    ('k8s/overview', '/k8s/overview'),
    ('containers/topology', '/containers/topology'),
    ('containers/pods', '/containers/pods'),
    ('containers/deployments', '/containers/deployments'),
    ('k8s/statefulsets', '/k8s/statefulsets'),
    ('k8s/daemonsets', '/k8s/daemonsets'),
    ('k8s/services', '/k8s/services'),
    ('k8s/ingresses', '/k8s/ingresses'),
    ('k8s/configmaps', '/k8s/configmaps'),
    ('k8s/secrets', '/k8s/secrets'),
    ('k8s/hpas', '/k8s/hpas'),
    ('k8s/pvcs', '/k8s/pvcs'),
    ('k8s/pvs', '/k8s/pvs'),
    ('containers', '/containers'),
    ('containers/docker', '/containers/docker'),
    ('knowledge', '/knowledge'),
    ('knowledge/documents', '/knowledge/documents'),
    ('knowledge/graph', '/knowledge/graph'),
    ('smart-recommend', '/smart-recommend'),
    ('runbooks', '/runbooks'),
    ('api/v1/docs', '/api/v1/docs'),
]

print('\n--- HTML fallback ---')
fb_ok = 0
fb_fail = 0
for name, path in HTML_FALLBACK:
    try:
        r = s.get(f'{BASE}{path}', timeout=15)
        if r.status_code == 200:
            fb_ok += 1
            print(f'[OK]   {name:25s} {r.status_code}')
        else:
            fb_fail += 1
            print(f'[FAIL] {name:25s} {r.status_code}')
    except Exception as e:
        fb_fail += 1
        print(f'[ERR ] {name:25s} {e}')

print(f'\n=== API: {ok} OK / {fail} FAIL ===')
print(f'=== HTML fallback: {fb_ok} OK / {fb_fail} FAIL ===')
