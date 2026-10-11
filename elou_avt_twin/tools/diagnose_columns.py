"""Print the live default-scheme column balance without changing the plant."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.base import SimulationConfig
from scheme.model import load_scheme
from simulation_core.engine import SimulationEngine
from calculation_core.solver.mesh_solver import DistillationSolver


def main() -> None:
    engine = SimulationEngine(SimulationConfig(random_seed=42))
    engine.set_scheme(load_scheme("schemes/default.json"))
    state = engine.get_current_state()
    for _ in range(18):
        state = engine.step(state, dt=1.0)

    outputs = engine.get_last_outputs()
    for node_id in ("col_32", "col_64"):
        node = engine._node_map[node_id]
        out = outputs[node_id]
        vessel = engine._vessel_state[node_id]
        incoming = [
            (edge.id, edge.target_port, round(stream.mass_flow, 4), round(stream.temperature - 273.15, 2))
            for edge in engine._scheme.edges
            if edge.target == node_id
            for stream in [engine._last_edge_streams.get(edge.id)]
            if stream is not None
        ]
        print(node_id, node.params.get("num_stages"), node.params.get("feed_stage"))
        print("  inputs", incoming)
        print("  products", {
            key: round(stream.mass_flow, 4)
            for key, stream in out.items()
            if key in ("distillate", "side_draw", "bottoms") and stream is not None
        })
        print("  converged", out.get("converged"), "level", round(vessel["level"], 4),
              "setpoint", vessel["setpoint"], "area", vessel["area"],
              "qin", round(engine._vessel_q_in.get(node_id, 0.0), 4),
              "qout", round(engine._vessel_q_out.get(node_id, 0.0), 4),
              "line_capacity", engine._outlet_line_capacity(node_id, "bottoms"))

    for node_id in ("val_5", "pum_68", "pum_69", "pum_70", "pum_71"):
        eq = engine._equipment.get(node_id)
        if eq is None:
            continue
        out = outputs.get(node_id, {})
        print(node_id, "state", vars(eq.state), "flow_out", out.get("flow_out"),
              "capacity", getattr(eq, "current_capacity", lambda *_: None)(850.0))

    k2 = engine._node_map["col_64"]
    k2_feed = next(
        stream for edge_id, stream in engine._last_edge_streams.items()
        if edge_id == "jun_72-col_64-1791058061857"
    )
    for iterations in (160, 320, 640):
        result = DistillationSolver(
            k2.params["num_stages"], k2.params["feed_stage"], engine.thermo,
            pressure=engine._equipment["col_64"].pressure,
            top_cut=engine._equipment["col_64"].params.get("top_cut"),
        ).solve(k2_feed, reflux_ratio=2.0, boilup_ratio=1.5,
                n_iter=iterations, tol=3e-3)
        profile = result.get("T_profile") or []
        print("k2 solver", iterations, result.get("converged"),
              result.get("temperature_iterations"),
              (round(profile[0] - 273.15, 2), round(profile[-1] - 273.15, 2)) if profile else None)
    for damping in (0.1, 0.5, 0.7):
        solver = DistillationSolver(
            k2.params["num_stages"], k2.params["feed_stage"], engine.thermo,
            pressure=engine._equipment["col_64"].pressure,
            top_cut=engine._equipment["col_64"].params.get("top_cut"),
        )
        solver._omega = damping
        result = solver.solve(k2_feed, reflux_ratio=2.0, boilup_ratio=1.5,
                              n_iter=320, tol=3e-3)
        profile = result.get("T_profile") or []
        print("k2 damping", damping, result.get("converged"), result.get("temperature_iterations"),
              (round(profile[0] - 273.15, 2), round(profile[-1] - 273.15, 2)) if profile else None)


if __name__ == "__main__":
    main()
