"""Correct crude-oil preheat header conservation and instrument readings."""
from __future__ import annotations
import json
from pathlib import Path

SCHEME = Path(__file__).resolve().parents[1] / 'schemes' / 'default.json'


def main() -> None:
    data = json.loads(SCHEME.read_text(encoding='utf-8'))
    nodes = {node['id']: node for node in data['nodes']}

    # The configured 100 kg/s is the total crude-oil feed.  N-1A/B/V share it;
    # it is not a separate demand for each parallel pump branch.
    source = nodes['source_189']['params']
    source['enforce_configured_flow'] = True
        for pump_id in ('pum_7', 'pum_8', 'pum_9'):
        nodes[pump_id]['params']['conserve_inlet_flow'] = True

    # Keep graphical self-links on the header from taking process flow and
    # distribute the metered total evenly to the three heat-exchange trains.
    nodes['jun_14']['params']['outlet_flow_split'] = {'jun_14': 0.0, 'jun_15': 1.0}
    for valve_id in ('val_21', 'val_22', 'val_23'):
        nodes[valve_id]['params']['max_flow_kg_s'] = 100.0 / 3.0
    # The three heated streams must merge before ELOU rather than becoming
    # zero-flow branches because a hydraulic tree terminates at the vessel.
    for gate_id in ('gat_24', 'gat_26', 'gat_27'):
        nodes[gate_id]['params']['outlet_flow_split'] = {'jun_21': 1.0}

    # The model has one common header where the real unit has two diaphragm
    # channels.  Show each channel as half of the header total; the totaliser
    # remains the full measured feed.
    for instrument_id in ('fie_17', 'fie_18', 'fie_19'):
        nodes[instrument_id]['params']['source_edge_id'] = 'source_189-pum_8-1790699613501'
        nodes[instrument_id]['params']['source_node_id'] = ''
    for instrument_id in ('fie_17', 'fie_18'):
        nodes[instrument_id]['params']['measurement_factor'] = 0.5
    nodes['fie_19']['params'].pop('measurement_factor', None)

    SCHEME.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Corrected source_189 header, N-1 branch splits, ELOU merge and FQR scaling.')

if __name__ == '__main__':
    main()
