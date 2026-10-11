import json
s=json.load(open('elou_avt_twin/schemes/default.json',encoding='utf-8'))
for n in s['nodes']:
 if n['id'] in ['elo_14','elo_15','elo_16','elo_28','elo_29','elo_30','jun_23','tan_1']:
  print(n['id'],n['name'],n['x'],n['y'],n['params'])
