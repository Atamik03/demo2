from models.stream import Stream
from safety.instruments import measurements
from models.base import SimulationConfig
from scheme.model import ProcessScheme, SchemeEdge, SchemeNode
from simulation_core.engine import SimulationEngine


def test_field_instrument_converts_si_flow_to_regulation_tonnes_per_hour():
    scheme = ProcessScheme(
        nodes=[SchemeNode(id="fi", type="field_instrument", params={
            "parameter": "flow_t_h", "source_edge_id": "line",
        })],
        edges=[SchemeEdge(id="line", source="source", target="sink")],
    )
    value = measurements(
        scheme,
        state=type("State", (), {"node_params": {}})(),
        streams={"source:out": Stream(mass_flow=10, temperature=300, pressure=200000)},
        edge_streams={},
    )
    assert value["fi"]["flow_t_h"] == 36


def test_field_instrument_exposes_excess_pressure_in_regulation_unit():
    scheme = ProcessScheme(nodes=[SchemeNode(id="pi", type="field_instrument", params={
        "parameter": "pressure_gauge_kgf_cm2", "source_node_id": "src",
    })])
    state = type("State", (), {"node_params": {"src": {"pressure_bar": 2.0}}})()
    value = measurements(scheme, state=state, streams={}, edge_streams={})
    assert value["pi"]["pressure_gauge_kgf_cm2"] > 0.99


def test_hydraulic_writeback_respects_a_valve_regulatory_flow_limit():
    scheme = ProcessScheme(
        nodes=[
            SchemeNode(id="source", type="source", params={"flow_kg_s": 5, "pressure_bar": 5}),
            SchemeNode(id="valve", type="valve", params={"cv": 1, "initial_position": 1,
                                                             "max_flow_kg_s": 0.5}),
            SchemeNode(id="sink", type="sink"),
        ],
        edges=[
            SchemeEdge(id="source-valve", source="source", target="valve"),
            SchemeEdge(id="valve-sink", source="valve", target="sink"),
        ],
    )
    engine = SimulationEngine(SimulationConfig(hydraulics_tau=0))
    engine.set_scheme(scheme)
    for _ in range(3):
        engine.step(engine.get_current_state(), dt=1)
    assert engine.get_last_outputs()["valve"]["flow_out"] <= 0.5
