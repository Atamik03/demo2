"""Coupled pressure/flow balance for source-fed pump networks, including merges.

Vessels remain inventory boundaries. Exchanger channels are separate hydraulic
elements. The legacy tree solver still handles gravity drains and other lines.
"""
import numpy as np
from scipy.optimize import least_squares
from calculation_core.hydraulics.line_hydraulics import valve_resistance


def solve_pump_network(engine):
    nodes, equipment = engine._node_map, engine._equipment
    outgoing = {}
    for edge in engine._edges:
        outgoing.setdefault(edge.source, []).append(edge)
    boundaries = {'sink', 'tank', 'separator', 'separator_s1k', 'elou', 'column'}
    controls = {'valve', 'angle_valve'}
    result, vessel_in = {}, {}
    engine._pressure_sources = set()
    engine._blocked_hydraulic_inlets = set()
    # Build connected source regions, without crossing an inventory boundary.
    regions = []
    for sid, source in nodes.items():
        if source.type != 'source':
            continue
        elements, links, ends = {}, [], {}
        pending = [(sid, 'out')]
        seen = set()
        while pending:
            nid, port = pending.pop()
            if (nid, port) in seen:
                continue
            seen.add((nid, port))
            for edge in outgoing.get(nid, []):
                if edge.source_port != port:
                    continue
                target = nodes[edge.target]
                key = target.id
                outport = 'out'
                if target.type in ('heat_exchanger', 'heater'):
                    pairs = engine._HX_PORT_PAIRS if target.type == 'heat_exchanger' else engine._FURNACE_PORT_PAIRS
                    outport = pairs.get(edge.target_port)
                    if not outport:
                        continue
                    key += ':' + edge.target_port
                start = nid if nodes[nid].type not in ('heat_exchanger', 'heater') else next(
                    (k for k, v in elements.items() if v == (nid, port)), nid)
                links.append((start, key))
                if target.type in boundaries:
                    if target.type == 'sink':
                        pressure = float(target.params.get('pressure_bar', 1.01325)) * 1e5
                    else:
                        vs = engine._vessel_boundary(target.id)
                        pressure = vs['p_out']
                        if vs.get('full'):
                            # A full vessel closes its own inlet. Imposing the
                            # legacy artificial 1e9 Pa blocking pressure on the
                            # shared wire also blocked every other outlet and
                            # made parallel vessel/sink boundaries inconsistent.
                            blocked = key + ':blocked_inlet'
                            links[-1] = (start, blocked)
                            elements[blocked] = (target.id, '__blocked_inlet')
                            links.append((blocked, key))
                    ends[key] = pressure
                else:
                    elements[key] = (target.id, outport)
                    pending.append((target.id, outport))
        if any(nodes[nid].type == 'pump' for nid, _ in elements.values()) and ends:
            regions.append(({sid}, elements, set(links), ends))
    # Sources feeding the same equipment must be solved together.
    merged = []
    for sources, elements, links, ends in regions:
        for old in list(merged):
            if set(elements) & set(old[1]):
                sources |= old[0]; elements.update(old[1]); links |= old[2]; ends.update(old[3])
                merged.remove(old)
        merged.append((sources, elements, links, ends))

    for sources, elements, links, ends in merged:
        engine._pressure_sources.update(sources)
        engine._blocked_hydraulic_inlets.update(
            nid for nid, port in elements.values() if port == '__blocked_inlet')
        # Hydraulic wire connections identify one pressure, including tees.
        parent = {}
        def root(k):
            parent.setdefault(k, k)
            if parent[k] != k:
                parent[k] = root(parent[k])
            return parent[k]
        def join(a, b):
            parent[root(a)] = root(b)
        for a, b in sorted(links):
            join((a, 'out'), (b, 'in'))
        fixed = {root((s, 'out')): float(nodes[s].params.get('pressure_bar', 1.01325)) for s in sources}
        fixed.update({root((s, 'in')): p / 1e5 for s, p in ends.items()})
        keys = sorted(elements)
        pins = [root((k, 'in')) for k in keys]
        pouts = [root((k, 'out')) for k in keys]
        free = sorted((set(pins) | set(pouts)) - set(fixed))
        indexes = {p: i for i, p in enumerate(free)}
        incidence = np.zeros((len(free), len(keys)))
        resistance, head, closed = [], [], []
        for j, key in enumerate(keys):
            nid, _ = elements[key]; node = nodes[nid]; eq = equipment.get(nid)
            if pins[j] in indexes: incidence[indexes[pins[j]], j] -= 1
            if pouts[j] in indexes: incidence[indexes[pouts[j]], j] += 1
            k, h, shut = 0., lambda q: 0., elements[key][1] == '__blocked_inlet'
            if node.type == 'pump':
                shut = not eq.state.running or eq.state.failed or eq.speed_ratio <= 0
                h = lambda q, eq=eq: eq.curve.pressure_rise(q / 850., eq.speed_ratio)
            elif node.type in controls:
                k = valve_resistance(850., eq.cv, eq.position)
                shut = eq.position <= 1e-6
            elif node.type == 'gate_valve':
                shut = not eq.is_open
            elif node.type == 'heat_exchanger':
                k = engine._hx_channel_info(nid).get('k', 0.)
            else:
                k = engine._pipe_resistance(nid, 850.) or 0.
                static = engine._static_head(nid, 850.)
                h = lambda q, static=static: -static
            resistance.append(k); head.append(h); closed.append(shut)
        def pressures(x, ports):
            return np.array([fixed[p] if p in fixed else x[indexes[p]] for p in ports])
        def residual(x):
            q = x[len(free):]
            dp = pressures(x, pouts) - pressures(x, pins)
            loss = np.array([(resistance[j] * (q[j]*100)**2 - head[j](q[j]*100))/1e5 for j in range(len(keys))])
            # Complementarity models nonreturn flow: q=0 when back-pressure
            # exceeds pump head; otherwise pressure balance must be exact.
            slack = dp + loss
            # Fischer–Burmeister complementarity retains a flow derivative
            # at q=0. min(q, slack) stalled at blocked/restarting pumps and
            # could freeze the entire simulation as vessel pressures rose.
            balance = np.hypot(q, slack) - q - slack
            balance[np.array(closed)] = q[np.array(closed)]
            return np.concatenate((incidence @ q, balance))
        signature = tuple(keys)
        cache = getattr(engine, '_pump_network_guess', {})
        guess = cache.get(signature)
        if guess is None or len(guess) != len(free)+len(keys):
            guess = np.r_[np.full(len(free), 3.), np.full(len(keys), .5)]
        solution = least_squares(residual, guess, max_nfev=100, ftol=1e-9, xtol=1e-9, gtol=1e-9)
        if np.max(np.abs(residual(solution.x)), initial=0.) > 1e-5:
            # A stopped pump has q=0, where its quadratic curve has zero
            # derivative. Restart from a finite flow when it is switched on.
            guess = np.r_[np.full(len(free), 3.), np.full(len(keys), .5)]
            solution = least_squares(residual, guess, max_nfev=200, ftol=1e-9, xtol=1e-9, gtol=1e-9)
        if np.max(np.abs(residual(solution.x)), initial=0.) > 1e-5:
            guess = np.r_[np.full(len(free), max(fixed.values(), default=3.)), np.full(len(keys), .01)]
            solution = least_squares(residual, guess, max_nfev=200, ftol=1e-9, xtol=1e-9, gtol=1e-9)
        if np.max(np.abs(residual(solution.x)), initial=0.) > 1e-5:
            raise RuntimeError(f'Coupled pump network did not converge: sources={sorted(sources)}, residual={np.max(np.abs(residual(solution.x))):.6g}')
        cache[signature] = solution.x
        engine._pump_network_guess = cache
        q = np.maximum(0., solution.x[len(free):] * 100)
        q[q < 1e-6] = 0.
        pin, pout = pressures(solution.x, pins)*1e5, pressures(solution.x, pouts)*1e5
        local = {key: {'flow': float(q[j]), 'p_in': max(1000., float(pin[j])), 'p_out': max(1000., float(pout[j]))} for j, key in enumerate(keys)}
        for sid in sources:
            flow = sum(local[b]['flow'] for a, b in links if a == sid and b in local)
            p = float(nodes[sid].params.get('pressure_bar', 1.01325))*1e5
            local[sid] = {'flow': flow, 'p_in': p, 'p_out': p}
        for end, p in ends.items():
            flow = sum(local[a]['flow'] for a, b in links if b == end and a in local)
            if nodes[end].type != 'sink': vessel_in[end] = vessel_in.get(end, 0.) + flow
        result.update(local)
    return result, vessel_in
