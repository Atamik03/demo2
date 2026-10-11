import pytest
from scheme.model import ProcessScheme, SchemeNode, SchemeEdge
from simulation_core.engine import SimulationEngine
from models.base import SimulationConfig, OperatorAction
from safety.instruments import instrument_limits
from scheme.telemetry import pipe_telemetry


def engine_for(nodes, edges):
    engine=SimulationEngine(SimulationConfig(hydraulics_tau=0))
    engine.set_scheme(ProcessScheme(nodes=nodes,edges=edges))
    return engine


def test_self_loop_does_not_stop_or_multiply_feed():
    e=engine_for([SchemeNode(id='s',type='source',params={'flow_kg_s':30}),
      SchemeNode(id='j',type='junction'),SchemeNode(id='v',type='valve'),SchemeNode(id='t',type='sink')],
      [SchemeEdge(id='a',source='s',target='j'),SchemeEdge(id='bad',source='j',target='j'),
       SchemeEdge(id='b',source='j',target='v'),SchemeEdge(id='c',source='v',target='t')])
    for _ in range(8): e.step(e.get_current_state(),dt=1)
    assert e.get_last_streams()['j:out'].mass_flow <= 30
    assert 'v:out' in e.get_last_streams()
    assert e._column_of_bottoms_valve('v')[0] is None
    assert all(edge.source!=edge.target for edge in e._edges)


def test_real_recycle_upstream_search_terminates():
    e=engine_for([SchemeNode(id='a',type='junction'),SchemeNode(id='b',type='junction'),SchemeNode(id='v',type='valve')],
      [SchemeEdge(id='ab',source='a',target='b'),SchemeEdge(id='ba',source='b',target='a'),SchemeEdge(id='bv',source='b',target='v')])
    assert e._column_of_bottoms_valve('v') == (None,[])


def test_instrument_reads_branch_and_raises_bound_alarm(monkeypatch):
    e=engine_for([SchemeNode(id='s',type='source',params={'flow_kg_s':20}),
      SchemeNode(id='t1',type='sink'),SchemeNode(id='t2',type='sink'),
      SchemeNode(id='fi',name='FI-TEST',type='field_instrument',params={'source_edge_id':'a','parameter':'flow_kg_s','alarm_limits':{'high':9,'high_high':11}})],
      [SchemeEdge(id='a',source='s',target='t1'),SchemeEdge(id='b',source='s',target='t2')])
    monkeypatch.setattr(e, '_solve_line_hydraulics', lambda: {})  # isolate conservation when no hydraulic branch solution exists
    state=e.step(e.get_current_state(),dt=1)
    assert state.node_params['fi']['flow_kg_s']==10
    alarm=next(a for a in state.alarms if a.parameter=='fi_measurement')
    assert alarm.node_id=='fi' and alarm.threshold==9
    assert 'FI-TEST' in alarm.description
    telemetry=pipe_telemetry(e._scheme,e.get_last_streams(),e._last_edge_streams)
    assert telemetry['a']['params']['flow_kg_s']+telemetry['b']['params']['flow_kg_s']==20


def test_documented_pressure_limits_convert_gauge_to_absolute():
    node=SchemeNode(id='pi',type='field_instrument',name='PRSA 204',params={'parameter':'pressure_bar'})
    limits=instrument_limits(node)
    assert limits['high']==pytest.approx((4.5*98066.5+101325)/100000)
    assert limits['high_high']==pytest.approx((4.8*98066.5+101325)/100000)
    node.params['parameter']='temperature_c'
    assert instrument_limits(node)=={}


def test_missing_binding_is_not_a_zero_reading_or_false_low_alarm():
    e=engine_for([SchemeNode(id='pi',type='field_instrument',params={'source_edge_id':'missing','parameter':'pressure_bar','alarm_limits':{'low':2}})],[])
    state=e.step(e.get_current_state(),dt=1)
    assert state.node_params['pi']['pressure_bar'] is None
    assert not state.alarms
    assert 'pi_measurement' in e.get_alarm_setpoints()

def test_exchanger_keeps_process_flow_when_utility_is_missing():
    from equipment.heat_exchanger import HeatExchanger
    from models.stream import Stream
    hx=HeatExchanger('hx',{})
    inlet=Stream(temperature=350,pressure=200000,mass_flow=8)
    hx.duty=500000
    result=hx.step(1,hot_in=inlet,cold_in=None,thermo=None)
    assert result['hot_out'] is inlet
    assert result['cold_out'] is None
    assert result['duty']==0 and hx.duty==0
    assert result['t_hot_out']==350

