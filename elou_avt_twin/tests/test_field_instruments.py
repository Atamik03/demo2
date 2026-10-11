from models.base import SimulationConfig
from scheme.model import ProcessScheme, SchemeEdge, SchemeNode, load_scheme, save_scheme
from scheme.validator import validate_scheme
from simulation_core.engine import SimulationEngine
from scheme.telemetry import pipe_telemetry
from models.stream import Stream
import pytest


def instrument_scheme():
    return ProcessScheme(nodes=[
        SchemeNode(id="src", type="source", params={"flow_kg_s": 10}),
        SchemeNode(id="sink", type="sink"),
        SchemeNode(id="pi", type="field_instrument", name="PI-101", x=120, y=80,
                   params={"instrument_code": "PI", "source_node_id": "src",
                           "parameter": "pressure_bar", "arm_area": "elou"}),
    ], edges=[SchemeEdge(id="flow", source="src", target="sink")])


def test_field_instrument_roundtrip(tmp_path):
    scheme = instrument_scheme()
    assert validate_scheme(scheme).is_valid
    path = tmp_path / "instruments.json"
    save_scheme(scheme, path)
    assert load_scheme(path).model_dump() == scheme.model_dump()


def test_field_instrument_cannot_carry_process_flow():
    scheme = instrument_scheme()
    scheme.edges.append(SchemeEdge(id="invalid", source="src", target="pi"))
    assert not validate_scheme(scheme).is_valid


def test_instrument_does_not_change_simulation():
    scheme = instrument_scheme()
    plain = scheme.model_copy(deep=True)
    plain.nodes = [node for node in plain.nodes if node.type != "field_instrument"]
    baseline = SimulationEngine(SimulationConfig(random_seed=42))
    observed = SimulationEngine(SimulationConfig(random_seed=42))
    baseline.set_scheme(plain)
    observed.set_scheme(scheme)
    for _ in range(3):
        baseline.step(baseline.get_current_state(), dt=1.0)
        observed.step(observed.get_current_state(), dt=1.0)
    observed_state = observed.get_current_state().model_dump()
    observed_state["node_params"].pop("pi", None)  # observation is now exposed separately
    assert baseline.get_current_state().model_dump() == observed_state
    assert baseline.get_last_streams().keys() == observed.get_last_streams().keys()


def test_pipe_binding_and_bends_survive_save(tmp_path):
    scheme = instrument_scheme()
    scheme.nodes[-1].params.update(source_edge_id="flow", source_node_id="", pipe_fraction=0.35, position_tag="PI-101A")
    scheme.edges[0] = SchemeEdge(id="flow", source="src", target="sink", waypoints=[{"x": 20, "y": 30}, {"x": 80, "y": 30}])
    path = tmp_path / "pipe.json"
    save_scheme(scheme, path)
    assert load_scheme(path).model_dump() == scheme.model_dump()


def test_pipe_telemetry_uses_exact_source_port():
    scheme = ProcessScheme(edges=[
        SchemeEdge(id="top", source="column", source_port="distillate", target="tank"),
        SchemeEdge(id="bottom", source="column", source_port="bottoms", target="tank2"),
        SchemeEdge(id="missing", source="column", source_port="out", target="tank3"),
    ])
    streams = {
        "column:distillate": Stream(temperature=350, pressure=200000, mass_flow=2),
        "column:bottoms": Stream(temperature=500, pressure=300000, mass_flow=8),
    }
    result = pipe_telemetry(scheme, streams)
    assert result["top"]["params"]["flow_kg_s"] == 2
    assert result["bottom"]["params"]["flow_kg_s"] == 8
    assert result["top"]["params"]["pressure_bar"] == 2
    assert result["top"]["params"]["temperature_c"] == pytest.approx(76.85)
    assert "missing" not in result


def test_stopped_pipe_does_not_expose_stale_temperature_as_live_measurement():
    scheme = ProcessScheme(edges=[SchemeEdge(id="closed", source="valve", target="sink")])
    # The stream keeps its thermodynamic state after a valve shuts.  The HMI
    # must show the static pressure, but not present that old temperature as a
    # live flowing measurement.
    streams = {"valve:out": Stream(temperature=420, pressure=200000, mass_flow=0)}
    params = pipe_telemetry(scheme, streams)["closed"]["params"]
    assert params["flow_kg_s"] == 0
    assert params["temperature_c"] is None
    assert params["pressure_bar"] == 2
