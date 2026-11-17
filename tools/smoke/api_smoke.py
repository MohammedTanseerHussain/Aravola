import time
from fastapi.testclient import TestClient
from videomerger.api.app import app

c = TestClient(app)
print('health', c.get('/health').status_code, c.get('/api/health').json())
print('caps', c.get('/api/capabilities').status_code)
fx = c.get('/api/effects').json()['effects']; print('effects', len(fx))
r = c.post('/api/projects', json={'name':'API smoke','format':'landscape','width':320,'height':240,'fps':12})
print('create', r.status_code, r.json()['id'])
pid = r.json()['id']
r = c.post(f'/api/projects/{pid}/clips', json={'clip':{'kind':'video','path':'output/src_a.mp4','name':'a'}})
print('add clip', r.status_code, r.json()['clip']['id'])
cid = r.json()['clip']['id']
print('timeline', c.get(f'/api/projects/{pid}/timeline').json())
r = c.get(f'/api/projects/{pid}/preview.png', params={'time':0.5,'width':160,'height':120}); print('preview', r.status_code, r.headers.get('content-type'), len(r.content))
r = c.post('/api/titles/card', json={'main_text':'SMOKE','sub_text':'api','width':320,'height':240,'time':1.0}); print('title', r.status_code, len(r.content))
r = c.post('/api/effects/film_burn/apply', json={'path':'output/src_a.mp4','time':0.5,'params':{'intensity':0.8}}); print('effect', r.status_code, len(r.content))
r = c.put(f'/api/projects/{pid}/clips/{cid}/effects/color_filter', json={'params':{'style':'BW Memories','intensity':1.0}}); print('set effect', r.status_code, list(r.json()['clip']['effects']))
r = c.post(f'/api/projects/{pid}/export', json={'output_name':'api_smoke.mp4','fps':12}); print('export', r.status_code, r.json())
jid = r.json()['id']
for i in range(60):
    j = c.get(f'/api/jobs/{jid}').json()
    if j['status'] in ('done','error','cancelled'):
        break
    time.sleep(0.5)
print('job', j)
if j['status'] == 'done':
    d = c.get(f'/api/jobs/{jid}/download'); print('download', d.status_code, len(d.content))
print('undo', c.post(f'/api/projects/{pid}/undo').status_code)
print('redo', c.post(f'/api/projects/{pid}/redo').status_code)
