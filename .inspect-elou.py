import json
s=json.load(open('elou_avt_twin/schemes/default.json',encoding='utf-8'))
for n in s['nodes']:
 if n['type']=='elou':print(n['id'],n['name'],n['params'])
for n in s['nodes']:
 if n['id'].startswith('gat_') or n['id'].startswith('tan_1'):print(n['id'],n['name'],n['type'],n['params'])
