from safety.alarm_system import AlarmSystem
from simulation_core.engine import SimulationEngine
from models.base import SimulationConfig, OperatorAction
from models.scenario import ScenarioEvent
from scheme.model import ProcessScheme, SchemeNode, SchemeEdge, save_scheme, load_scheme


def test_acknowledgment_preserves_active_and_history_and_first_actor():
    system = AlarmSystem({})
    system.register_custom_alarm(12, 'pump_fault', description='Failure')
    alarm = system.get_active_alarms()[0]
    assert system.acknowledge_occurrence(alarm.id, 'operator-one')
    timestamp = alarm.acknowledged_at
    assert timestamp and alarm.occurred_at
    assert system.get_active_alarms()[0].id == alarm.id
    system.clear_alarm('pump_fault')
    assert system.acknowledge_occurrence(alarm.id, 'operator-two')
    saved = system.get_alarm_history()[0]
    assert saved.acknowledged_at == timestamp
    assert saved.acknowledged_by == 'operator-one'
    assert not system.acknowledge_occurrence('missing', 'operator')


def test_manual_holds_output_against_scenario_but_emergency_stop_works():
    engine = SimulationEngine(SimulationConfig())
    engine.set_scheme(ProcessScheme(nodes=[SchemeNode(id='v', type='valve')]))
    valve = engine._equipment['v']
    state = engine.get_current_state()
    def action(kind, value):
        engine._apply_action(OperatorAction(timestamp=0, operator_id='test', equipment_id='v', action_type=kind, new_value=value), state)
    action('SET_VALUE', .4)
    assert valve.state.control_mode == 'РУЧ'
    event = ScenarioEvent(timestamp=0, event_type='SET_PARAM', target_id='v', parameters={'flow': .8})
    engine._dispatch_scenario_event(event)
    assert valve.target_position == .4
    action('SET_MODE', 1)
    engine._dispatch_scenario_event(event)
    assert valve.target_position == .8
    action('SET_MODE', 0)
    engine.set_scheme(ProcessScheme(nodes=[SchemeNode(id='p', type='pump')]))
    pump = engine._equipment['p']
    pump.state.control_mode = 'РУЧ'
    engine._dispatch_scenario_event(ScenarioEvent(timestamp=0, event_type='SET_STATE', target_id='p', parameters={'state':'EMERGENCY_STOP'}))
    assert not pump.state.running


def test_remote_measurement_roundtrip_without_process_edge(tmp_path):
    scheme = ProcessScheme(nodes=[SchemeNode(id='s',type='source'),SchemeNode(id='t',type='sink'),
        SchemeNode(id='pi',type='field_instrument',x=200,y=300,params={'measurement_link':True,'source_edge_id':'pipe','pipe_fraction':.7})],
        edges=[SchemeEdge(id='pipe',source='s',target='t')])
    path = tmp_path / 'measurement.json'
    save_scheme(scheme,path)
    loaded = load_scheme(path)
    assert loaded == scheme
    assert len(loaded.edges) == 1
