"""Field instrument values and documented limits, in explicit engineering units."""
import json
import math
import re
from pathlib import Path
from scheme.telemetry import pipe_telemetry

DOCUMENT_LIMITS = json.loads(Path(__file__).with_name('instrument_limits.json').read_text(encoding='utf-8'))
UNITS = {'pressure_bar':'бар','pressure_gauge_kgf_cm2':'кгс/см² изб.','temperature_c':'°C','flow_kg_s':'кг/с',
         'flow_t_h':'т/ч',
         'volumetric_flow_m3_h':'м³/ч','level_m':'м','level_pct':'%','level_deviation_pct':'%',
         'density_kg_m3':'кг/м³','position':'%',
         'top_temp_c':'°C','bottom_temp_c':'°C',
         't_out_c':'°C','t_out2_c':'°C','t_out3_c':'°C','t_out4_c':'°C'}


def tag_key(value):
    return re.sub(r'\s+', '', value.upper().translate(str.maketrans({'Р':'P','Т':'T','А':'A','С':'C','Н':'H','К':'K','В':'B','О':'O'})))


def instrument_limits(node):
    documented = DOCUMENT_LIMITS.get(tag_key(str(node.params.get('position_tag', node.name))), {})
    parameter = node.params.get('parameter', 'pressure_bar')
    # Convert the confirmed gauge pressure limits when an existing instrument
    # is configured to read absolute bar. Do not silently change its units.
    converted = dict(documented)
    if documented.get('parameter') == 'pressure_gauge_kgf_cm2' and parameter == 'pressure_bar':
        for key in ('low_low','low','high','high_high'):
            if key in converted: converted[key] = (converted[key]*98066.5+101325)/100000
        converted['parameter'] = parameter
    if converted.get('parameter') != parameter: converted = {}
    explicit = node.params.get('alarm_limits')
    if isinstance(explicit, dict):
        converted.update({k:v for k,v in explicit.items() if k in ('low_low','low','high','high_high')})
    source = node.params.get('alarm_source')
    if isinstance(source, str) and source.strip():
        converted['source'] = source.strip()
    return converted


def measurements(scheme, state, streams, edge_streams, previous_measurements=None):
    pipes = pipe_telemetry(scheme, streams, edge_streams)
    result = {}
    for node in scheme.nodes:
        if node.type != 'field_instrument': continue
        cfg = node.params
        parameter = str(cfg.get('parameter', 'pressure_bar'))
        # A display tag can retain the engineering parameter used by its
        # limits (for example ``temperature_c``), while reading a more
        # specific value from equipment telemetry such as a heat exchanger's
        # hot-side outlet temperature.
        source_parameter = str(cfg.get('source_parameter', parameter))
        edge_id, source_id = cfg.get('source_edge_id'), cfg.get('source_node_id')
        source = pipes.get(edge_id, {}).get('params', {}) if edge_id else state.node_params.get(source_id, {})
        value = source.get(source_parameter)
        # A furnace has several outlet passes.  A thermocouple can point to
        # one of them through ``source_node_id`` and t_out[_N]_c even though
        # the source node's aggregate telemetry has no single temperature.
        if value is None and source_id and parameter.startswith('t_out') and parameter.endswith('_c'):
            port = parameter[2:-2]  # t_out_c -> out, t_out2_c -> out2
            stream = streams.get(f'{source_id}:{port}')
            if stream is not None and stream.mass_flow > 1e-9:
                value = stream.temperature - 273.15
        if value is None and parameter == 'pressure_gauge_kgf_cm2' and isinstance(source.get('pressure_bar'), (int,float)):
            gauge_pressure = (source['pressure_bar'] * 100000 - 101325) / 98066.5
            # Atmospheric equipment may differ from 1 atm only by rounding.
            value = 0.0 if abs(gauge_pressure) < 0.005 else gauge_pressure
        # The simulation keeps mass flow in SI (kg/s), while the regulation
        # and the operator's flow-control loops use tonnes per hour.
        if value is None and parameter == 'flow_t_h' and isinstance(source.get('flow_kg_s'), (int, float)):
            value = source['flow_kg_s'] * 3.6
        if parameter in ('level_pct', 'level_deviation_pct') and isinstance(source.get('level_m'), (int,float)):
            lo, hi = cfg.get('range_min_m'), cfg.get('range_max_m')
            if isinstance(lo,(int,float)) and isinstance(hi,(int,float)) and hi>lo:
                level_pct = (source['level_m']-lo)/(hi-lo)*100
                value = level_pct if parameter == 'level_pct' else abs(float(cfg.get('duplicate_offset_pct', 0.0)))
        # A modelled common header can represent two physical, parallel
        # diaphragm measurements.  The factor retains the documented reading
        # of each diaphragm while the totaliser continues to show their sum.
        factor = cfg.get('measurement_factor', 1.0)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                value *= float(factor)
            except (TypeError, ValueError):
                pass
        valid = isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
        # A stopped stream has no new temperature sample.  Keep the last valid
        # instrument value visible during the alarm instead of blinking to a
        # dash; ``stale`` distinguishes it from a live measurement.
        previous = (previous_measurements or {}).get(node.id, {})
        previous_value = previous.get(parameter) if isinstance(previous, dict) else None
        has_previous = (isinstance(previous_value, (int, float))
                        and not isinstance(previous_value, bool)
                        and math.isfinite(previous_value))
        result[node.id] = {
            parameter: value if valid else (previous_value if has_previous else None),
            'measurement_status': (
                'ok' if valid else 'stale' if has_previous
                else 'Нет показания: проверьте источник, параметр и диапазон'
            ),
        }
    return result
