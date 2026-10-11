import json, urllib.request
base='http://127.0.0.1:8000'
def req(path, data=None, token=None):
 r=urllib.request.Request(base+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
 return json.load(urllib.request.urlopen(r,timeout=12))
t=req('/auth/login', {'username':'admin','password':'admin'})['access_token']; st=req('/state',token=t); sc=req('/scheme',token=t)
print('time',st['simulation_time'],'calculation_error',st.get('calculation_error'))
for nid,v in st['equipment'].items():
 if v['type']=='elou':print(nid,v['name'],v['params'])
for e in sc['edges']:
 if e['target'].startswith('elo_') or e['source'].startswith('elo_'): print(e)
