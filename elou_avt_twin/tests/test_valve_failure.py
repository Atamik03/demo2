"""A valve failure must change the hydraulic process, not only its HMI state."""

from models.base import SimulationConfig
from scheme.model import ProcessScheme, SchemeEdge, SchemeNode
from simulation_core.engine import SimulationEngine


def test_failed_control_valve_fails_closed_and_stops_line_flow():
    scheme = ProcessScheme(
        nodes=[
            SchemeNode(id="src", type="source", params={"flow_kg_s": 10.0, "pressure_bar": 5.0}),
            SchemeNode(id="fv", type="valve", params={"initial_position": 1.0}),
            SchemeNode(id="sink", type="sink"),
        ],
        edges=[
            SchemeEdge(id="source-valve", source="src", target="fv"),
            SchemeEdge(id="valve-sink", source="fv", target="sink"),
        ],
    )
    engine = SimulationEngine(SimulationConfig(hydraulics_tau=0))
    engine.set_scheme(scheme)
    engine.step(engine.get_current_state(), dt=1)
    assert engine.get_last_outputs()["fv"]["flow_out"] > 0

    engine._equipment["fv"].inject_failure("MECHANICAL_FAILURE")
    engine.step(engine.get_current_state(), dt=1)
    assert engine.get_last_outputs()["fv"]["flow_out"] == 0
    assert engine.get_last_streams()["fv:out"].mass_flow == 0


def test_manual_closure_stops_a_flow_controller_valve():
    """The flow-controller flag must not bypass the actual valve position."""
    scheme = ProcessScheme(
        nodes=[
            SchemeNode(id="src", type="source", params={"flow_kg_s": 10.0, "pressure_bar": 5.0}),
            SchemeNode(id="fv", type="valve", params={
                "initial_position": 1.0, "response_rate": 1.0, "flow_controller": True,
            }),
            SchemeNode(id="sink", type="sink"),
        ],
        edges=[
            SchemeEdge(id="source-valve", source="src", target="fv"),
            SchemeEdge(id="valve-sink", source="fv", target="sink"),
        ],
    )
    engine = SimulationEngine(SimulationConfig(hydraulics_tau=0))
    engine.set_scheme(scheme)
    engine.step(engine.get_current_state(), dt=1)
    engine._equipment["fv"].apply_action("SET_VALUE", 0)
    engine.step(engine.get_current_state(), dt=1)

    assert engine.get_last_outputs()["fv"]["flow_out"] == 0
