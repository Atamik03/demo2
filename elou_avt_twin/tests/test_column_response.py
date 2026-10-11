"""Column inventory must respond independently to feed and outlet isolation."""
from types import SimpleNamespace
import pytest
from models.base import SimulationConfig
from scheme.model import ProcessScheme, SchemeNode as N, SchemeEdge as E
from simulation_core.engine import SimulationEngine
from equipment.columns import AtmosphericColumnK1, column_class_for
from equipment.distillation_column import DistillationColumn


def column_engine(valve_type='valve', feed=10):
    nodes = [N(id='src', type='source', params={'flow_kg_s': feed, 'pressure_bar': 5, 'temperature_c': 200}),
             N(id='col', type='column', params={'num_stages': 3, 'feed_stage': 1, 'sump_area': 1,
               'initial_level': 2, 'nominal_pressure': 200000, 'solver_n_iter': 2}),
             N(id='v', type=valve_type, params={'initial_position': 1, 'initial_open': 1}),
             N(id='bot', type='sink'), N(id='top', type='sink')]
    edges = [E(id='a', source='src', target='col'), E(id='b', source='col', source_port='bottoms', target='v'),
             E(id='c', source='v', target='bot'), E(id='d', source='col', source_port='distillate', target='top')]
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(ProcessScheme(nodes=nodes, edges=edges))
    return engine


def tick(engine, count=1):
    for _ in range(count):
        engine.step(engine.get_current_state(), dt=1)
    return engine.get_current_state()


@pytest.mark.parametrize('valve_type', ['valve', 'gate_valve'])
def test_closed_bottoms_accumulate_feed(valve_type):
    engine = column_engine(valve_type)
    before = tick(engine, 3).level['col']
    engine._equipment['v'].apply_action('SET_VALUE', 0)
    state = tick(engine, 8)
    assert engine.get_last_outputs()['v']['flow_out'] == 0
    assert state.level['col'] > before
    assert engine._vessel_q_in['col'] == pytest.approx(10)
    assert engine._vessel_q_out['col'] == 0
    assert state.node_params['col']['level_m'] == state.level['col']
    # Allow the valve stroke and one inventory tick before checking recovery.
    engine._equipment['v'].apply_action('SET_VALUE', 1)
    peak = tick(engine, 4).level['col']
    after = tick(engine, 12)
    assert engine.get_last_outputs()['v']['flow_out'] > 0
    assert after.level['col'] <= peak
    if valve_type == 'valve':
        assert after.level['col'] < peak


def test_more_feed_accumulates_faster_at_closed_bottoms():
    levels = []
    for feed in (10, 20):
        engine = column_engine('gate_valve', feed)
        engine._equipment['v'].apply_action('SET_VALUE', 0)
        levels.append(tick(engine, 8).level['col'])
    assert levels[1] - 2 == pytest.approx(2 * (levels[0] - 2))


def test_column_does_not_treat_stripping_steam_as_process_feed():
    nodes = [
        N(id='feed', type='source', params={'flow_kg_s': 10, 'temperature_c': 180}),
        N(id='steam', type='source', params={'flow_kg_s': 5, 'temperature_c': 700}),
        N(id='col', type='column', params={'num_stages': 3, 'feed_stage': 1, 'solver_n_iter': 2}),
        N(id='top', type='sink'), N(id='bottom', type='sink'),
    ]
    edges = [
        E(id='feed_col', source='feed', target='col', target_port='feed'),
        E(id='steam_col', source='steam', target='col', target_port='steam'),
        E(id='top_out', source='col', source_port='distillate', target='top'),
        E(id='bottom_out', source='col', source_port='bottoms', target='bottom'),
    ]
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(ProcessScheme(nodes=nodes, edges=edges))
    tick(engine, 3)
    out = engine.get_last_outputs()['col']
    assert out['distillate'].mass_flow + out['bottoms'].mass_flow == pytest.approx(10)


def test_default_scheme_has_no_startup_column_alarm():
    from scheme.model import load_scheme
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(load_scheme('schemes/default.json'))
    state = tick(engine, 12)
    column_alarm = [
        alarm for alarm in state.alarms
        if alarm.node_id in engine._node_map and engine._node_map[alarm.node_id].type == 'column'
    ]
    assert column_alarm == []


def test_k1_level_falls_after_one_documented_feed_regulator_fails_closed():
    """K-1 inventory must react to a real FRC failure, not a fictional valve."""
    from scheme.model import load_scheme
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(load_scheme('schemes/default.json'))
    state = tick(engine, 20)
    before = state.level['col_32']

    engine._equipment['val_44'].inject_failure('MECHANICAL_FAILURE')
    state = tick(engine, 30)

    assert engine.get_last_outputs()['val_44']['flow_out'] == 0
    assert engine._vessel_q_out['col_32'] > engine._vessel_q_in['col_32']
    assert state.level['col_32'] < before


def test_k1_level_falls_when_all_desalted_oil_feed_regulators_are_closed():
    """All three desalted-oil feed regulators must reduce K-1 inventory.

    FRC-458, FRC-459 and FRC-460 are the valves drawn on the three
    desalted-oil passes.  They must be process inputs to K-1, rather than
    decorative faceplates whose closing leaves the column feed unchanged.
    """
    from scheme.model import load_scheme

    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(load_scheme('schemes/default.json'))
    state = tick(engine, 10)
    before = state.level['col_32']

    levels = [before]
    for valve_id in ('val_44', 'val_45', 'val_46'):
        engine._equipment[valve_id].apply_action('SET_VALUE', 0)
        levels.append(tick(engine, 8).level['col_32'])

    assert engine.get_last_outputs()['val_44']['flow_out'] == 0
    assert engine.get_last_outputs()['val_45']['flow_out'] == 0
    assert engine.get_last_outputs()['val_46']['flow_out'] == 0
    drops = [levels[i] - levels[i + 1] for i in range(3)]
    assert all(drop > 0 for drop in drops)
    assert drops[1] > drops[0]
    assert drops[2] > drops[1]


def test_k1_temperature_limits_match_operating_regime():
    limits = AtmosphericColumnK1('k1').params['limits']
    assert limits['temperature_top_high_high'] == pytest.approx(423.15)
    assert limits['temperature_bottom_high_high'] == pytest.approx(553.15)


def test_k10_does_not_inherit_k1_configuration():
    assert column_class_for('col_141', {'preset': 'k10'}) is DistillationColumn


def test_active_default_columns_preserve_process_feed_mass():
    from scheme.model import load_scheme
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(load_scheme('schemes/default.json'))
    tick(engine, 30)
    checked = []
    for node_id, node in engine._node_map.items():
        if node.type != 'column':
            continue
        ports = node.params.get('process_feed_ports', ['in', 'feed', 'feed1', 'feed2', 'feed3', 'feed4'])
        feed_mass = sum(
            stream.mass_flow
            for edge in engine._scheme.edges
            if edge.target == node_id and edge.target_port in ports
            for stream in [engine._last_edge_streams.get(edge.id)]
            if stream is not None
        )
        if feed_mass <= 1e-9:
            continue
        out = engine.get_last_outputs()[node_id]
        product_mass = sum(out[key].mass_flow for key in ('distillate', 'side_draw', 'bottoms') if out.get(key) is not None)
        assert product_mass == pytest.approx(feed_mass)
        checked.append(node_id)
    # The working scheme includes the explicitly connected K-1 feed sources
    # in addition to the K-2 and secondary-fractionation columns.
    assert set(checked) == {'col_32', 'col_64', 'col_140', 'col_141'}


def test_closed_gate_is_not_reopened_by_hydraulic_relaxation():
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(ProcessScheme(nodes=[N(id='s',type='source',params={'flow_kg_s':10,'pressure_bar':5}),
      N(id='g',type='gate_valve'),N(id='t',type='sink')],edges=[E(id='a',source='s',target='g'),E(id='b',source='g',target='t')]))
    tick(engine, 3)
    engine._equipment['g'].apply_action('CLOSE')
    tick(engine)
    assert engine.get_last_outputs()['g']['flow_out'] == 0
    assert engine.get_last_streams()['g:out'].mass_flow == 0


def test_api_reports_each_columns_own_level(monkeypatch):
    import api_server as api
    scheme = ProcessScheme(nodes=[N(id='c1',type='column'),N(id='c2',type='column'),N(id='e1',type='elou')])
    monkeypatch.setattr(api, 'scheme_store', scheme)
    outputs = {'c1':{'level':1.2}, 'c2':{'level':3.4}, 'e1':{'level':2.7}}
    engine = SimpleNamespace(get_last_outputs=lambda:outputs,get_last_streams=lambda:{},_equipment={})
    twin = SimpleNamespace(_engine=engine,get_state=lambda:SimpleNamespace(level={'column':1.2,'elou':99}))
    data = api._build_node_telemetry(twin)
    assert data['c1']['params']['level_m'] == 1.2
    assert data['c2']['params']['level_m'] == 3.4
    assert data['e1']['params']['level_m'] == 2.7
