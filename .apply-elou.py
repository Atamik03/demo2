import json, urllib.request
base='http://127.0.0.1:8000'
def request(path, payload=None, token=None):
 r=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
 return json.load(urllib.request.urlopen(r,timeout=20))
token=request('/auth/login', {'username':'admin','password':'admin'})['access_token']
for nid, top, bottom in [('elo_14',4.8,4.5),('elo_15',4.8,4.5),('elo_16',4.8,4.5),('elo_28',16.5,16.5),('elo_29',16.5,16.5),('elo_30',16.5,16.5)]:
 request('/equipment/params', {'equipment_id':nid,'params':{'voltage_top_kv':top,'voltage_bottom_kv':bottom}}, token)
state=request('/state', token=token)
print('t=',state['simulation_time'],'error=',state.get('calculation_error'))
for nid in ['elo_14','elo_15','elo_16','elo_28','elo_29','elo_30']:
 p=state['equipment'][nid]['params'];print(nid, p.get('level_m'),p.get('in_flow'),p.get('out_flow'),p.get('voltage_top_kv'),p.get('voltage_bottom_kv'))
