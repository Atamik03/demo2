from types import SimpleNamespace

import pytest

from models.base import SimulationConfig
from scheme.model import ProcessScheme, SchemeNode, SchemeEdge
from simulation_core.engine import SimulationEngine


def test_parameter_endpoint_updates_separate_runtime_source_and_heat(monkeypatch):
    import api_server as api

    saved = ProcessScheme(nodes=[
        SchemeNode(id='oil', type='source', params={'temperature_c': 25, 'flow_kg_s': 40}),
        SchemeNode(id='utility', type='source', params={'temperature_c': 25, 'flow_kg_s': 40}),
        SchemeNode(id='hx', type='heat_exchanger'),
        SchemeNode(id='a', type='sink'), SchemeNode(id='b', type='sink'),
    ], edges=[
        SchemeEdge(id='i1', source='oil', target='hx', target_port='hot_in'),
        SchemeEdge(id='i2', source='utility', target='hx', target_port='cold_in'),
        SchemeEdge(id='o1', source='hx', source_port='hot_out', target='a'),
        SchemeEdge(id='o2', source='hx', source_port='cold_out', target='b'),
    ])
    engine = SimulationEngine(SimulationConfig())
    engine.set_scheme(saved.model_copy(deep=True))
    engine._hyd_tau = 0
    step = lambda: engine.step(engine.get_current_state(), dt=1)
    step()
    assert engine.get_last_outputs()['hx']['duty'] == 0
    monkeypatch.setattr(api, 'scheme_store', saved)
    monkeypatch.setattr(api, 'twin', SimpleNamespace(_engine=engine))
    monkeypatch.setattr(api, '_save_current_scheme', lambda: None)
    monkeypatch.setattr(api, '_safe_step', step)
    monkeypatch.setattr(api, '_refresh_snapshot', lambda: None)
    monkeypatch.setattr(api, '_snapshot_state', lambda: {})

    api.update_equipment_params(api.EquipmentParamsRequest(
        equipment_id='utility', params={'temperature_c': 180, 'flow_kg_s': 30}))

    assert saved.node('utility').params['temperature_c'] == 180
    live = engine.get_last_streams()['utility:out']
    assert live.temperature == pytest.approx(453.15)
    assert live.mass_flow == pytest.approx(30)
    output = engine.get_last_outputs()['hx']
    assert output['hot_out'].temperature > output['t_hot_in'] + 10
    assert output['duty'] > 0
