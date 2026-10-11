"""Measurements at each pipe's source port, in the UI's display units."""

from scheme.model import ProcessScheme


def pipe_telemetry(scheme: ProcessScheme, streams: dict, edge_streams=None) -> dict:
    result = {}
    for edge in scheme.edges:
        if edge.source == edge.target:
            continue
        # Some pass-through links do not receive a dedicated edge snapshot,
        # although their source-port stream is live.  Fall back to that port
        # so instruments placed on a furnace outlet keep a valid indication.
        stream = edge_streams.get(edge.id) if edge_streams is not None else None
        if stream is None:
            stream = streams.get(f"{edge.source}:{edge.source_port}")
        if stream is None:
            continue
        source_node = scheme.node(edge.source)
        steam_limit = (source_node.params.get("pp_flow_limit_kg_s")
                       if source_node is not None and edge.source_port.startswith("pp") else None)
        if isinstance(steam_limit, (int, float)):
            stream = stream.copy_with(mass_flow=min(stream.mass_flow, max(0.0, float(steam_limit))))
        # Температура имеет смысл как измерение *текущего потока*. При
        # нулевом расходе Stream всё ещё содержит температуру последнего
        # заполнившего трубу продукта, но это не должно выглядеть как работа
        # линии: клапан уже перекрыл поток и теплообмен остановился.
        # Давление оставляем — это статическое давление в отсечённой линии.
        flowing = stream.mass_flow > 1e-9
        result[edge.id] = {
            "type": "stream", "name": edge.id,
            "running": None, "failed": None, "failure_mode": None,
            "params": {
                "pressure_bar": stream.pressure / 100000.0,
                "temperature_c": stream.temperature - 273.15 if flowing else None,
                "flow_kg_s": stream.mass_flow,
                "volumetric_flow_m3_h": stream.mass_flow / stream.density * 3600 if flowing else 0.0,
                "density_kg_m3": stream.density,
                "pressure_gauge_kgf_cm2": (stream.pressure - 101325) / 98066.5,
            },
        }
    return result
