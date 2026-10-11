import pytest
from simulation_core.engine import SimulationEngine
from models.base import SimulationConfig, OperatorAction
from scheme.model import ProcessScheme, SchemeNode, SchemeEdge
from equipment.heat_exchanger import HeatExchanger
from models.stream import Stream


def test_closed_parallel_regulators_deadhead_all_upstream_pumps_and_reopen():
    nodes=[SchemeNode(id='s',type='source',params={'flow_kg_s':80}),SchemeNode(id='j',type='junction')]
    edges=[]
    for i in range(2):
        nodes.extend([SchemeNode(id=f'p{i}',type='pump'),SchemeNode(id=f'v{i}',type='valve'),SchemeNode(id=f't{i}',type='sink')])
        edges.extend([SchemeEdge(id=f'a{i}',source='s',target=f'p{i}'),SchemeEdge(id=f'b{i}',source=f'p{i}',target='j'),
          SchemeEdge(id=f'c{i}',source='j',target=f'v{i}'),SchemeEdge(id=f'd{i}',source=f'v{i}',target=f't{i}')])
    e=SimulationEngine(SimulationConfig());e.set_scheme(ProcessScheme(nodes=nodes,edges=edges))
    for _ in range(4):e.step(e.get_current_state(),dt=1)
    assert e.get_last_streams()['j:out'].mass_flow>0
    actions=[OperatorAction(timestamp=0,operator_id='test',equipment_id=f'v{i}',action_type='SET_VALUE',new_value=0) for i in range(2)]
    e.step(e.get_current_state(),operator_actions=actions,dt=1)
    for _ in range(12):e.step(e.get_current_state(),dt=1)
    for nid in ['s','p0','p1','j']:
        assert e.get_last_streams()[nid+':out'].mass_flow==0,nid
    assert all(stream.mass_flow == 0 for stream in e._last_edge_streams.values())
    for nid in ['p0','p1']:
        assert e.get_last_outputs()[nid]['flow_out']==0
        assert e.get_last_outputs()[nid]['mass_flow_kg_s']==0
    e.step(e.get_current_state(),operator_actions=[OperatorAction(timestamp=0,operator_id='test',equipment_id='v0',action_type='SET_VALUE',new_value=1)],dt=1)
    for _ in range(12):e.step(e.get_current_state(),dt=1)
    assert e.get_last_streams()['j:out'].mass_flow>0


class ConstantThermo:
    def calculate_cp(self,*args):return 2000
    def calculate_enthalpy(self,temperature,*args):return temperature*2000
    def temperature_from_enthalpy(self,enthalpy,*args):return enthalpy/2000


def test_equal_temperature_clears_old_duty_and_exposes_all_temperatures():
    hx=HeatExchanger('hx',{});hx.duty=12345
    a=Stream(temperature=298.15,pressure=200000,mass_flow=10)
    out=hx.step(1,hot_in=a,cold_in=a,thermo=ConstantThermo())
    assert out['duty']==0 and hx.duty==0
    assert out['t_hot_out']==out['t_cold_out']==298.15


def test_hot_utility_heats_oil_even_when_port_names_are_reversed():
    hx=HeatExchanger('hx',{'area':300,'u':300})
    oil=Stream(temperature=298.15,pressure=200000,mass_flow=10,enthalpy=596300)
    utility=Stream(temperature=473.15,pressure=200000,mass_flow=10,enthalpy=946300)
    out=hx.step(1,hot_in=oil,cold_in=utility,thermo=ConstantThermo())
    assert out['hot_out'].temperature>oil.temperature
    assert out['cold_out'].temperature<utility.temperature
    assert out['duty']>0


def header_engine():
    nodes = [SchemeNode(id='s', type='source', params={'flow_kg_s': 80}),
             SchemeNode(id='j', type='junction')]
    edges = []
    for i in range(2):
        nodes.extend([SchemeNode(id=f'p{i}', type='pump'),
                      SchemeNode(id=f'v{i}', type='valve'),
                      SchemeNode(id=f't{i}', type='sink')])
        edges.extend([SchemeEdge(id=f'a{i}', source='s', target=f'p{i}'),
                      SchemeEdge(id=f'b{i}', source=f'p{i}', target='j'),
                      SchemeEdge(id=f'c{i}', source='j', target=f'v{i}'),
                      SchemeEdge(id=f'd{i}', source=f'v{i}', target=f't{i}')])
    engine = SimulationEngine(SimulationConfig())
    engine.set_scheme(ProcessScheme(nodes=nodes, edges=edges))
    engine._hyd_tau = 0
    return engine


def settle(engine, actions=()):
    engine.step(engine.get_current_state(), operator_actions=list(actions), dt=1)
    for _ in range(12):
        engine.step(engine.get_current_state(), dt=1)
    streams = engine.get_last_streams()
    pump_total = sum(streams[f'p{i}:out'].mass_flow for i in range(2))
    valve_total = sum(streams[f'v{i}:out'].mass_flow for i in range(2))
    assert pump_total == pytest.approx(valve_total, abs=1e-5)
    assert streams['s:out'].mass_flow == pytest.approx(pump_total, abs=1e-5)
    for i in range(2):
        assert engine._last_edge_streams[f'd{i}'].mass_flow == pytest.approx(streams[f'v{i}:out'].mass_flow)
    return pump_total


def command(nid, kind, value):
    return OperatorAction(timestamp=0, operator_id='test', equipment_id=nid,
                          action_type=kind, new_value=value)


def test_partial_opening_and_speed_change_actual_header_flow():
    e = header_engine()
    q70 = settle(e)
    q100 = settle(e, [command(f'v{i}', 'SET_VALUE', 1) for i in range(2)])
    assert q100 > q70 * 1.05
    half = settle(e, [command(f'p{i}', 'SET_SPEED', e._equipment[f'p{i}'].nominal_speed / 2) for i in range(2)])
    assert half == pytest.approx(q100 / 2, rel=.01)
    restored = settle(e, [command(f'p{i}', 'SET_SPEED', e._equipment[f'p{i}'].nominal_speed) for i in range(2)])
    assert restored == pytest.approx(q100, rel=.01)


def test_unequal_header_branches_conserve_mass():
    e = header_engine()
    settle(e, [command('v0', 'SET_VALUE', .3), command('v1', 'SET_VALUE', .8)])
    streams = e.get_last_streams()
    assert streams['v0:out'].mass_flow < streams['v1:out'].mass_flow
    settle(e, [command('v0', 'SET_VALUE', 0)])
    assert e.get_last_streams()['v0:out'].mass_flow == 0
    assert e.get_last_streams()['v1:out'].mass_flow > 0


def test_external_source_temperature_reaches_exchanger_through_engine():
    nodes = [SchemeNode(id='oil', type='source', params={'temperature_c': 28, 'flow_kg_s': 40}),
             SchemeNode(id='utility', type='source', params={'temperature_c': 28, 'flow_kg_s': 40}),
             SchemeNode(id='hx', type='heat_exchanger'),
             SchemeNode(id='a', type='sink'), SchemeNode(id='b', type='sink')]
    edges = [SchemeEdge(id='i1', source='oil', target='hx', target_port='hot_in'),
             SchemeEdge(id='i2', source='utility', target='hx', target_port='cold_in'),
             SchemeEdge(id='o1', source='hx', source_port='hot_out', target='a'),
             SchemeEdge(id='o2', source='hx', source_port='cold_out', target='b')]
    e = SimulationEngine(SimulationConfig())
    e.set_scheme(ProcessScheme(nodes=nodes, edges=edges))
    e.step(e.get_current_state(), dt=1)
    assert e.get_last_outputs()['hx']['duty'] == 0
    e._node_map['utility'].params['temperature_c'] = 180
    e.step(e.get_current_state(), dt=1)
    out = e.get_last_outputs()['hx']
    assert out['hot_out'].temperature > out['t_hot_in'] + 10
    assert out['cold_out'].temperature < out['t_cold_in']
    assert out['hot_out'].mass_flow == pytest.approx(40)
    assert out['cold_out'].mass_flow == pytest.approx(40)
    assert out['duty'] > 0


def test_full_vessel_on_header_does_not_block_parallel_outlet():
    e = SimulationEngine(SimulationConfig())
    e.set_scheme(ProcessScheme(nodes=[
        SchemeNode(id='s', type='source'), SchemeNode(id='p', type='pump'),
        SchemeNode(id='j', type='junction'), SchemeNode(id='tank', type='tank'),
        SchemeNode(id='sink', type='sink'),
    ], edges=[
        SchemeEdge(id='a', source='s', target='p'),
        SchemeEdge(id='b', source='p', target='j'),
        SchemeEdge(id='c', source='j', target='tank'),
        SchemeEdge(id='d', source='j', target='sink'),
    ]))
    e._hyd_tau = 0
    for _ in range(3):
        vessel = e._vessel_boundary('tank')
        vessel['full'] = True
        vessel['level'] = vessel['height']
        e.step(e.get_current_state(), dt=1)
        streams = e._last_edge_streams
        assert streams['c'].mass_flow == 0
        assert streams['d'].mass_flow > 0
        assert streams['a'].mass_flow == pytest.approx(streams['d'].mass_flow, abs=1e-5)


def test_open_electro_dehydrator_balances_normal_throughput_and_exposes_voltages():
    e = SimulationEngine(SimulationConfig())
    e.set_scheme(ProcessScheme(nodes=[
        SchemeNode(id='s', type='source', params={'flow_kg_s': 180}),
        SchemeNode(id='ed', type='elou', params={'vessel_area': 30, 'height_m': 4,
                                                   'voltage_top_kv': 4.8, 'voltage_bottom_kv': 4.5}),
        SchemeNode(id='sink', type='sink'),
    ], edges=[SchemeEdge(id='in', source='s', target='ed'),
              SchemeEdge(id='out', source='ed', source_port='oil_out', target='sink')]))
    e._hyd_tau = 0
    initial = e._vessel_boundary('ed')['level']
    for _ in range(120):
        e.step(e.get_current_state(), dt=1)
    out = e.get_last_outputs()['ed']
    assert out['level'] == pytest.approx(initial, abs=.01)
    assert out['in_flow'] == pytest.approx(out['out_flow'], rel=.001)
    assert e._equipment['ed'].voltage_top_kv == 4.8
    assert e._equipment['ed'].voltage_bottom_kv == 4.5
