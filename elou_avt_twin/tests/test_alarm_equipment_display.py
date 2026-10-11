import pytest
from safety.alarm_system import AlarmSystem, AlarmSetpoint
from models.base import SimulationConfig, Severity
from scheme.model import ProcessScheme, SchemeNode, SchemeEdge
from simulation_core.engine import SimulationEngine
from equipment.params_spec import editor_spec, coerce
from equipment.pump import Pump
from equipment.valve import Valve
from equipment.heat_exchanger import HeatExchanger
from equipment.passports import match_passports


def test_threshold_direction_zero_and_live_values():
    alarm = AlarmSystem({'p': AlarmSetpoint('p', low_low=0, low=10, high=80, high_high=100)})
    first = alarm.evaluate(1, {'p': 0})[0]
    assert first.threshold == 0
    assert first.severity == Severity.CRITICAL
    assert alarm.evaluate(2, {'p': -1}) == []
    assert alarm.get_active_alarms()[0].id == first.id
    assert alarm.get_active_alarms()[0].actual_value == -1
    high = alarm.evaluate(3, {'p': 120})[0]
    assert high.id != first.id and high.threshold == 100
    alarm.evaluate(4, {'p': 50})
    assert not alarm.get_active_alarms()
    assert len(alarm.get_alarm_history()) == 2


def test_failure_event_without_process_thresholds():
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(ProcessScheme(nodes=[SchemeNode(id='src',type='source'),
      SchemeNode(id='p',name='H-1',type='pump'),SchemeNode(id='sink',type='sink')],
      edges=[SchemeEdge(id='a',source='src',target='p'),SchemeEdge(id='b',source='p',target='sink')]))
    engine.inject_failure('p','MECHANICAL_FAILURE')
    for _ in range(3):engine.step(engine.get_current_state(),dt=1)
    faults=[a for a in engine.get_current_state().alarms if a.parameter=='p_failure']
    assert len(faults)==1 and faults[0].node_id=='p' and faults[0].severity==Severity.CRITICAL
    assert len([a for a in engine._alarm_system.get_alarm_history() if a.parameter=='p_failure'])==1
    engine._equipment['p'].reset()
    engine.step(engine.get_current_state(),dt=1)
    assert not any(a.parameter=='p_failure' for a in engine.get_current_state().alarms)


def test_lone_high_high_limits_are_not_dropped():
    engine=SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(ProcessScheme(nodes=[SchemeNode(id='c',type='column',params={'limits':{
      'level_high_high':3,'temperature_top_high_high':650,'temperature_bottom_low_low':250}})]))
    limits=engine.get_alarm_setpoints()
    assert limits['c_level']['high_high']==3
    assert limits['c_temperature_top']['high_high']==650
    assert limits['c_temperature_bottom']['low_low']==250


def rows(kind, eq, params=None):
    return {r['key']:r for r in editor_spec(kind,eq,SchemeNode(id='n',type=kind,params=params or {}))}


def test_pump_spec_uses_effective_curve_and_si_roundtrip():
    pump=Pump('p',{'mass_capacity_kg_s':106.25,'delta_p':500000})
    r=rows('pump',pump)
    assert r['nominal_volumetric_flow_m3_s']['value']==450
    assert r['nominal_volumetric_flow_m3_s']['unit']=='м³/ч'
    assert coerce('nominal_volumetric_flow_m3_s',450,'pump')==pytest.approx(.125)
    assert r['nominal_head_pa']['value']==5
    assert 'nominal_head' not in r and 'nominal_flow' not in r


def test_default_valve_and_exchanger_editor_units():
    assert rows('valve',Valve('v',{}))['initial_position']['value']==70
    assert rows('angle_valve',Valve('v',{}))['initial_position']['value']==70
    hx=rows('heat_exchanger',HeatExchanger('h',{}))
    assert hx['delta_p']['value']==.1
    assert coerce('delta_p',.1,'heat_exchanger')==pytest.approx(10132.5)
    assert coerce('initial_position',70,'valve')==pytest.approx(.7)


def test_passports_match_explicit_positions_only():
    docs,complete=match_passports(SchemeNode(id='p',type='pump',name='Н1-Б'))
    assert complete and docs[0]['flow_m3_h']==450 and docs[0]['speed_rpm']==2980
    docs,complete=match_passports(SchemeNode(id='h',type='heat_exchanger',name='Т-1/1, T-1/2. T-1/3'))
    assert complete and sum(r['area_m2'] for r in docs)==1074
    docs,complete=match_passports(SchemeNode(id='h',type='heat_exchanger',name='Х-4/1-3'))
    assert complete and len(docs)==3
    assert match_passports(SchemeNode(id='p',type='pump',name='Насос'))==([],False)
    assert not match_passports(SchemeNode(id='h',type='heat_exchanger',name='X-5,6, X-7'))[1]
