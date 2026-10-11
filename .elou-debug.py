import json,sys
sys.path.insert(0,'elou_avt_twin')
from simulation_core.engine import SimulationEngine
from models.base import SimulationConfig
from scheme.model import ProcessScheme
s=ProcessScheme.model_validate_json(open('elou_avt_twin/schemes/default.json',encoding='utf-8').read()); e=SimulationEngine(SimulationConfig());e.set_scheme(s)
for n in ['elo_14','elo_15','elo_16','elo_28','elo_29','elo_30']:
 print(n,e._outlet_line_capacity(n,'oil_out'))
for i in range(10):
 e.step(e.get_current_state(),dt=1)
 print(i,[(n,round(e.get_last_outputs().get(n,{}).get('in_flow',-1),2),round(e.get_last_outputs().get(n,{}).get('out_flow',-1),2),round(e.get_last_outputs().get(n,{}).get('level',-1),3)) for n in ['elo_14','elo_15','elo_16','elo_28','elo_29','elo_30']])
