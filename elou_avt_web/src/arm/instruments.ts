import type { NodeTelemetry } from '../types';

export const FIELD_INSTRUMENTS = [
  { code: 'PI', label: 'Манометр', parameter: 'pressure_gauge_kgf_cm2' },
  { code: 'TI', label: 'Термометр', parameter: 'temperature_c' },
  { code: 'FI', label: 'Расходомер', parameter: 'flow_t_h' },
  { code: 'LI', label: 'Уровнемер', parameter: 'level_m' },
] as const;

/** A field instrument observes equipment; it is not part of the process flow. */
export function instrumentTelemetry(
  params: Record<string, unknown> | undefined,
  equipment: Record<string, NodeTelemetry>,
  streams: Record<string, NodeTelemetry> = {},
  instrumentId?: string,
): NodeTelemetry | null {
  const own = instrumentId ? equipment[instrumentId] : undefined;
  const parameter = String(params?.parameter ?? 'pressure_bar');
  // The backend keeps one numeric sample on a field-instrument node.  A local
  // draft can contain an obsolete parameter key after the saved scheme has
  // been corrected (for example `temperature_c` instead of `t_out_c`).  In
  // that case show the valid sample under the requested display key instead
  // of rendering an empty instrument until the page is reloaded.
  if (own?.params.measurement_status === 'ok') {
    if (Object.prototype.hasOwnProperty.call(own.params, parameter)) return own;
    const measured = Object.entries(own.params).find(([key, value]) => (
      key !== 'source_edge_id'
      && key !== 'source_node_id'
      && key !== 'measurement_status'
      && typeof value === 'number'
      && Number.isFinite(value)
    ));
    if (measured) return { ...own, params: { ...own.params, [parameter]: measured[1] } };
  }
  if (own && Object.prototype.hasOwnProperty.call(own.params, parameter)
    && own.params.source_edge_id === (params?.source_edge_id ?? '')
    && own.params.source_node_id === (params?.source_node_id ?? '')) return own;
  const pipe = String(params?.source_edge_id ?? '');
  const source = pipe ? streams[pipe] : equipment[String(params?.source_node_id ?? '')];
  if (!source || Object.prototype.hasOwnProperty.call(source.params, parameter)) return source ?? null;
  // During the first render the backend may not have produced the separate
  // instrument sample yet. Derive the display quantity from the live pipe so
  // KIP never briefly switches to a different unit or an empty readout.
  const raw = source.params;
  const gaugePressure = typeof raw.pressure_bar === 'number'
    ? (raw.pressure_bar * 100000 - 101325) / 98066.5
    : undefined;
  const value = parameter === 'flow_t_h' && typeof raw.flow_kg_s === 'number'
    ? raw.flow_kg_s * 3.6
    : parameter === 'pressure_gauge_kgf_cm2' && gaugePressure !== undefined
      ? (Math.abs(gaugePressure) < 0.005 ? 0 : gaugePressure)
      : undefined;
  const factor = Number(params?.measurement_factor ?? 1);
  const adjusted = value === undefined || !Number.isFinite(factor) ? value : value * factor;
  return adjusted === undefined ? source : { ...source, params: { ...raw, [parameter]: adjusted } };
}

export function instrumentParameter(tag: string): string {
  const code = tag.split(' ')[0].replace(/Р/g,'P').replace(/Т/g,'T').replace(/А/g,'A').replace(/С/g,'C');
  if (code === 'QR' && /5-[КK]3D/i.test(tag)) return 'density_kg_m3';
  return ({F:'flow_t_h',T:'temperature_c',P:'pressure_gauge_kgf_cm2',L:'level_m',H:'position',W:'weight_kg',Q:'concentration_pct'})[code[0] as 'F'] ?? '';
}
