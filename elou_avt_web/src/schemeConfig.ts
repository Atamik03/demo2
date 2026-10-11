import { FIELD_INSTRUMENTS } from './arm/instruments';
import type { PaletteItem, SchemeNodeData } from './types';
import type { MnemoItem, MnemoColDetail, MnemoFurDetail } from './mnemo/mnemoTypes';
import { PRESET_COLUMNS } from './mnemo/colPresets';
import { PRESET_FURNACES } from './mnemo/furPresets';

export const PALETTE: PaletteItem[] = [
  ...FIELD_INSTRUMENTS.map((item): PaletteItem => ({ type: 'field_instrument', label: `${item.code} · ${item.label}`, category: 'instrument', color: '#7c3aed', preset: item.code })),
  { type: 'source', label: 'Источник сырья', category: 'boundary', color: '#35d399' },
  { type: 'source', label: 'Входящая линия →', category: 'boundary', color: '#64748b', preset: 'line_reference_in' },
  { type: 'sink', label: 'Продолжение линии →', category: 'boundary', color: '#64748b', preset: 'line_reference' },
  { type: 'sink', label: 'Продукт / отбор', category: 'boundary', color: '#64748b' },
  { type: 'pump', label: 'Насос', category: 'equipment', color: '#35d399' },
  { type: 'valve', label: 'Регулирующий клапан', category: 'equipment', color: '#38bdf8' },
  { type: 'angle_valve', label: 'Угловой клапан', category: 'equipment', color: '#38bdf8' },
  { type: 'gate_valve', label: 'Задвижка', category: 'equipment', color: '#38bdf8' },
  // Смесителя в палитре нет: чтобы слить две линии, достаточно подвести их к
  // одному штуцеру — узел с несколькими входящими линиями движок считает
  // тройником. Тип оставлен в модели, чтобы старые схемы открывались.
  { type: 'splitter', label: 'Разъединитель потока', category: 'equipment', color: '#38bdf8' },
  { type: 'elou', label: 'ЭЛОУ (электродегидратор)', category: 'equipment', color: '#38bdf8' },
  { type: 'heat_exchanger', label: 'Теплообменник · нагрев', category: 'equipment', color: '#fb923c', preset: 'hx_heater' },
  { type: 'heat_exchanger', label: 'Теплообменник · охлаждение', category: 'equipment', color: '#38bdf8', preset: 'hx_cooler' },
  { type: 'heat_exchanger', label: 'АВЗ · Воздушное охлаждение', category: 'equipment', color: '#38bdf8', preset: 'air_cooler' },
  { type: 'heater', label: 'Печь', category: 'equipment', color: '#fb923c' },
  { type: 'heater', label: 'П-1 · Нагрев отбензиненной нефти', category: 'equipment', color: '#fb923c', preset: 'p1' },
  { type: 'heater', label: 'П-2 · Нефть в К-2 + подогрев низа К-1', category: 'equipment', color: '#fb923c', preset: 'p2' },
  { type: 'heater', label: 'П-3 · Подогрев низа К-1 (рибойлер К-4)', category: 'equipment', color: '#fb923c', preset: 'p3' },
  { type: 'heater', label: 'П-4 · Вторичная перегонка бензина', category: 'equipment', color: '#fb923c', preset: 'p4' },
  { type: 'heater', label: 'П-5 · Перегрев пара для регенерации', category: 'equipment', color: '#fb923c', preset: 'p5' },
  { type: 'column', label: 'Колонна ректификации', category: 'equipment', color: '#67e8f9' },
  { type: 'column', label: 'К-1 · Атмосферная колонна', category: 'equipment', color: '#67e8f9', preset: 'k1' },
  { type: 'column', label: 'К-2 · Атмосферная колонна', category: 'equipment', color: '#67e8f9', preset: 'k2' },
  { type: 'column', label: 'К-3 · Отпарная колонна', category: 'equipment', color: '#67e8f9', preset: 'k3' },
  { type: 'column', label: 'К-4 · Стабилизатор', category: 'equipment', color: '#67e8f9', preset: 'k4' },
  { type: 'column', label: 'К-7 · Газосепаратор', category: 'equipment', color: '#67e8f9', preset: 'k7' },
  { type: 'column', label: 'К-9 · Вторичная перегонка бензина', category: 'equipment', color: '#67e8f9', preset: 'k9' },
  { type: 'column', label: 'К-10 · Вторичная перегонка бензина', category: 'equipment', color: '#67e8f9', preset: 'k10' },
  { type: 'column', label: 'К-12/2-3б · Демеркаптанизация', category: 'equipment', color: '#67e8f9', preset: 'k12' },
  { type: 'column', label: 'К-12/4 · Реактор демеркаптанизации', category: 'equipment', color: '#67e8f9', preset: 'k12_4' },
  { type: 'tank', label: 'Ёмкость', category: 'equipment', color: '#38bdf8' },
  { type: 'separator', label: 'Сепаратор', category: 'equipment', color: '#38bdf8' },
  { type: 'separator_s1k', label: 'Сепаратор С-1К', category: 'equipment', color: '#38bdf8' },
];

export const TYPE_COLORS: Record<string, string> = Object.fromEntries(PALETTE.map((p) => [p.type, p.color]));

// Human-readable labels/units for telemetry params (used in Inspector + on-scheme tags).
export const PARAM_LABELS: Record<string, { label: string; unit: string }> = {
  volumetric_flow_m3_h: { label: 'Объёмный расход', unit: 'м³/ч' },
  density_kg_m3: { label: 'Плотность', unit: 'кг/м³' },
  pressure_gauge_kgf_cm2: { label: 'Избыточное давление', unit: 'кгс/см² изб.' },
  level_pct: { label: 'Уровень по диапазону прибора', unit: '%' },
  weight_kg: { label: 'Масса', unit: 'кг' },
  concentration_pct: { label: 'Концентрация', unit: '%' },
  flow_kg_s: { label: 'Расход', unit: 'т/ч' },
  flow_t_h: { label: 'Расход', unit: 'т/ч' },
  feed_flow: { label: 'Расход сырья', unit: 'т/ч' },
  flow_m3_h: { label: 'Объёмный расход', unit: 'м³/ч' },
  mass_flow_kg_s: { label: 'Расход', unit: 'т/ч' },
  configured_flow_kg_s: { label: 'Заданный расход', unit: 'т/ч' },
  column_pressure: { label: 'Давление в колонне', unit: 'кгс/см² изб.' },
  column_temperature: { label: 'Температура в колонне', unit: '°C' },
  furnace_temperature: { label: 'Температура печи', unit: '°C' },
  in_flow: { label: 'Расход вход', unit: 'т/ч' },
  out_flow: { label: 'Расход выход', unit: 'т/ч' },
  gas_out_flow: { label: 'Расход газа', unit: 'т/ч' },
  water_out_flow: { label: 'Расход дренажа воды', unit: 'т/ч' },
  power_w: { label: 'Мощность', unit: 'кВт' },
  pressure_bar: { label: 'Избыточное давление', unit: 'кгс/см² изб.' },
  pressure_in_bar: { label: 'Избыточное давление на входе', unit: 'кгс/см² изб.' },
  pressure_out_bar: { label: 'Избыточное давление на выходе', unit: 'кгс/см² изб.' },
  temperature_c: { label: 'Температура', unit: '°C' },
  outlet_temp_c: { label: 'Температура выхода', unit: '°C' },
  top_temp_c: { label: 'Температура верха', unit: '°C' },
  bottom_temp_c: { label: 'Температура низа', unit: '°C' },
  t_cold_in_c: { label: 'Холодный вход', unit: '°C' },
  t_cold_out_c: { label: 'Холодный выход', unit: '°C' },
  t_hot_in_c: { label: 'Горячий вход', unit: '°C' },
  t_hot_out_c: { label: 'Горячий выход', unit: '°C' },
  t_out_c: { label: 'Температура выхода, поток 1', unit: '°C' },
  t_out2_c: { label: 'Температура выхода, поток 2', unit: '°C' },
  t_out3_c: { label: 'Температура выхода, поток 3', unit: '°C' },
  t_out4_c: { label: 'Температура выхода, поток 4', unit: '°C' },
  position: { label: 'Открытие', unit: '%' },
  open: { label: 'Состояние', unit: '' },
  blocked: { label: 'Линия изолирована', unit: '' },
  duty_w: { label: 'Тепловая нагрузка', unit: 'МВт' },
  fuel_flow: { label: 'Расход топлива', unit: 'т/ч' },
  distillate_flow: { label: 'Дистиллят', unit: 'т/ч' },
  side_draw_flow: { label: 'Боковой отбор', unit: 'т/ч' },
  bottoms_flow: { label: 'Кубовый остаток', unit: 'т/ч' },
  level_m: { label: 'Уровень', unit: 'м' },
  level_deviation_pct: { label: 'Рассогласование уровнемеров', unit: '%' },
  level_setpoint_m: { label: 'Уставка уровня', unit: 'м' },
  voltage_top_kv: { label: 'Верхний электрод', unit: 'кВ' },
  voltage_bottom_kv: { label: 'Нижний электрод', unit: 'кВ' },
  volume_m3: { label: 'Объём аппарата', unit: 'м³' },
  efficiency: { label: 'КПД', unit: '%' },
  speed_rpm: { label: 'Частота вращения', unit: 'об/мин' },
  volumetric_flow_m3_s: { label: 'Объёмный расход', unit: 'м³/ч' },
  pressure_rise_pa: { label: 'Напор', unit: 'кгс/см²' },
  npsha_pa: { label: 'Доступный кавитационный запас', unit: 'кгс/см²' },
  npshr_pa: { label: 'Требуемый кавитационный запас', unit: 'кгс/см²' },
  converged: { label: 'Сходимость', unit: '' },
};

// Параметры потока (линии), которые можно показывать квадратиком на схеме.
// Значения берутся из телеметрии узла-источника; `phase` — среда в линии.
export const STREAM_PARAMS: Record<string, { label: string; unit: string }> = {
  phase: { label: 'Среда', unit: '' },
  flow_kg_s: { label: 'Расход', unit: 'т/ч' },
  temperature_c: { label: 'Температура', unit: '°C' },
  pressure_bar: { label: 'Избыточное давление', unit: 'кгс/см² изб.' },
};

// Default parameters for a freshly created node.
export const DEFAULT_PARAMS: Record<string, Record<string, unknown>> = {
  field_instrument: { instrument_code: 'PI', parameter: 'pressure_gauge_kgf_cm2', source_node_id: '' },
  source: { flow_kg_s: 100, temperature_c: 25, pressure_bar: 1.01325 },
  sink: {},
  pump: { nominal_volumetric_flow_m3_s: 0.1, efficiency_nominal: 0.75 },
  valve: { cv: 0.01, response_rate: 0.2 },
  angle_valve: { cv: 0.01, response_rate: 0.2 },
  gate_valve: { initial_open: 1 },
  elou: { vessel_area: 30.0, voltage_top_kv: 4.8, voltage_bottom_kv: 4.5, pressure_drop: 5000 },
  heat_exchanger: { u: 300.0, area: 200.0 },
  heater: { max_heat_duty: 50000000.0, response_tau: 60.0 },
  column: { num_stages: 20, feed_stage: 10 },
  tank: { level_mode: 'reflux', height_m: 6, vessel_area: 30, initial_level: 2 },
  separator: { level_mode: 'reflux' },
  separator_s1k: { level_mode: 'reflux' },
  mixer: { num_inputs: 2 },
  splitter: { num_outputs: 2 },
};

// Node card size per type (width x height) — compact, matches the symbol.
export const NODE_SIZES: Record<string, { w: number; h: number }> = {
  field_instrument: { w: 104, h: 48 },
  source: { w: 72, h: 40 },
  sink: { w: 72, h: 40 },
  pump: { w: 104, h: 64 },
  valve: { w: 40, h: 56 },
  angle_valve: { w: 84, h: 76 },
  gate_valve: { w: 40, h: 56 },
  mixer: { w: 144, h: 114 },
  splitter: { w: 144, h: 114 },
  junction: { w: 10, h: 10 },
  elou: { w: 120, h: 66 },
  // Компактная карточка: не перекрывает соседние трубопроводы кликабельной
  // областью и оставляет место для редактирования изломов линии.
  heat_exchanger: { w: 100, h: 56 },
  heater: { w: 118, h: 88 },
  // Обычная колонна должна читаться как высокий вертикальный аппарат даже
  // до выбора детального пресета К-1…К-12.
  column: { w: 76, h: 220 },
  tank: { w: 140, h: 70 },
  separator: { w: 140, h: 70 },
  separator_s1k: { w: 140, h: 70 },
};

export function nodeSize(type: string) {
  return NODE_SIZES[type] ?? { w: 120, h: 80 };
}

/** Габарит карточки узла с учётом пресета детальной колонны/печи. */
/** Width of a line-reference callout: text, padding and the arrow point. */
export function lineReferenceWidth(name = ''): number {
  // Cyrillic and Latin capitals are a little wider than digits/punctuation.
  // This is intentionally a stable approximation so node dimensions do not
  // depend on fonts loading after React Flow has placed its handles.
  const textWidth = [...name].reduce((total, char) => total + (
    /[А-ЯЁA-Z]/.test(char) ? 6.2 : char === ' ' ? 3 : 5.5
  ), 0);
  return Math.max(92, Math.min(320, Math.ceil(textWidth + 28)));
}

/**
 * Размер обычной граничной плашки (источник или приёмник потока).
 *
 * Эти плашки содержат только название потока. Раньше для всех них
 * использовался размер 72×40, поэтому длинное название переносилось на
 * несколько строк, а третья строка уходила за границы прямоугольника.
 * Делаем плашку шире по тексту и увеличиваем её по высоте только если
 * перенос всё-таки необходим.
 */
export function boundaryLabelSize(name = ''): { w: number; h: number } {
  const label = name.trim() || 'Поток';
  const glyphWidth = (char: string): number => (
    /[А-ЯЁA-Z]/.test(char) ? 6.2 : char === ' ' ? 3 : /[,.:/-]/.test(char) ? 3.5 : 5.7
  );
  const textWidth = [...label].reduce((total, char) => total + glyphWidth(char), 0);
  const w = Math.max(72, Math.min(184, Math.ceil(textWidth + 20)));
  const available = w - 12;
  let lines = 1;
  let current = 0;
  for (const word of label.split(/\s+/)) {
    const wordWidth = [...word].reduce((total, char) => total + glyphWidth(char), 0);
    const next = current ? current + 3 + wordWidth : wordWidth;
    if (current && next > available) {
      lines += 1;
      current = wordWidth;
    } else {
      current = next;
    }
  }
  return { w, h: Math.max(40, 14 + lines * 12) };
}

export function nodeSizeFor(n: { type: string; name?: string; params?: Record<string, unknown> }): { w: number; h: number } {
  if (n.params?.line_reference) return { w: lineReferenceWidth(n.name), h: 40 };
  if (n.type === 'source' || n.type === 'sink') return boundaryLabelSize(n.name);
  const d = n.params?.mnemo as MnemoColDetail | MnemoFurDetail | undefined;
  if (d?.vb?.w && d?.nodeW) {
    const nw = d.nodeW;
    return { w: nw + 8, h: Math.round((nw * d.vb.h) / d.vb.w) + 26 };
  }
  const preset = n.params?.preset as string | undefined;
  const pc = preset ? PRESET_COLUMNS[preset] : undefined;
  const pf = preset ? PRESET_FURNACES[preset] : undefined;
  const cfg = pc?.config ?? pf?.config;
  if (cfg?.vb?.w && cfg.nodeW) {
    const nw = cfg.nodeW;
    return { w: nw + 8, h: Math.round((nw * cfg.vb.h) / cfg.vb.w) + 26 };
  }
  return nodeSize(n.type);
}

/** Символ мнемосхемы для узла (пресет детальной колонны или печи). */
export function mnemoForNode(params: Record<string, unknown>): Partial<MnemoItem> | undefined {
  const d = params.mnemo as MnemoColDetail | MnemoFurDetail | undefined;
  if (d?.vb?.w && d?.nodeW) {
    const preset = params.preset as string | undefined;
    const isFur = !!preset && !!PRESET_FURNACES[preset];
    return { t: isFur ? 'fur' : 'col', w: d.nodeW, detail: d };
  }
  const preset = params.preset as string | undefined;
  const pc = preset ? PRESET_COLUMNS[preset] : undefined;
  if (pc?.config?.vb?.w && pc.config.nodeW) return { t: 'col', w: pc.config.nodeW, detail: pc.config };
  const pf = preset ? PRESET_FURNACES[preset] : undefined;
  if (pf?.config?.vb?.w && pf.config.nodeW) return { t: 'fur', w: pf.config.nodeW, detail: pf.config };
  return undefined;
}

export function defaultName(type: string): string {
  const p = PALETTE.find((x) => x.type === type);
  return p ? p.label : type;
}

let counter = 0;
/** Сгенерировать уникальный id объекта (prefix_n), не пересекающийся с уже
 *  существующими. Схемы, загруженные с бэкенда, имеют свои id (source_5,
 *  col_32, ...), поэтому простой счётчик-инкремент может выдать дубликат:
 *  новый узел затирает существующий с тем же id, и его связи «сами собой»
 *  переезжают на новый элемент. */
export function nextId(type: string, taken?: Iterable<string>): string {
  counter += 1;
  const prefix = type === 'source' || type === 'sink' ? type : type.slice(0, 3);
  const used = new Set(taken ?? []);
  let max = counter;
  for (const id of used) {
    if (!id.startsWith(`${prefix}_`)) continue;
    const n = Number(id.slice(prefix.length + 1));
    if (Number.isFinite(n)) max = Math.max(max, n + 1);
  }
  let id = `${prefix}_${max}`;
  while (used.has(id)) {
    max += 1;
    id = `${prefix}_${max}`;
  }
  return id;
}

/** Создать узел. Для детальных колонн передаётся ключ пресета (k1..k4):
 *  в params кладётся конфиг мнемосимвола (detail), число тарелок и стадия питания. */
export function createNode(
  type: string,
  x: number,
  y: number,
  preset?: string,
  existingIds?: Iterable<string>,
): SchemeNodeData {
  const node: SchemeNodeData = {
    id: nextId(type, existingIds),
    type,
    name: defaultName(type),
    x: 0,
    y: 0,
    params: { ...(DEFAULT_PARAMS[type] ?? {}) },
  };
  if (type === 'field_instrument') {
    const instrument = FIELD_INSTRUMENTS.find((item) => item.code === preset) ?? FIELD_INSTRUMENTS[0];
    node.name = `${instrument.code}-${node.id.split('_').pop()}`;
    node.params = { ...node.params, instrument_code: instrument.code, parameter: instrument.parameter, position_tag: node.name };
  }
  if (preset === 'line_reference' || preset === 'line_reference_in') {
    node.name = preset === 'line_reference_in' ? 'С участка / листа' : 'На участок / лист';
    node.params = { ...node.params, line_reference: true };
  }
  if (preset === 'air_cooler') {
    node.name = 'АВЗ · Аппарат воздушного захолаживания';
    node.params = { ...node.params, preset, cooling_medium: 'air', ambient_temperature_c: 25 };
  }
  if (preset === 'hx_heater' || preset === 'hx_cooler') {
    const thermal_role = preset === 'hx_cooler' ? 'cooler' : 'heater';
    node.name = thermal_role === 'cooler' ? 'Холодильник' : 'Нагреватель';
    node.params = { ...node.params, thermal_role };
  }
  if (preset) {
    const pc = PRESET_COLUMNS[preset];
    const pf = PRESET_FURNACES[preset];
    const p = pc ?? pf;
    if (p) {
      node.name = p.label;
      node.params = {
        ...node.params,
        preset,
        mnemo: p.config,
      };
      if (pc) {
        node.params.num_stages = pc.numStages;
        node.params.feed_stage = pc.feedStage;
      }
    }
  }
  const { w, h } = nodeSizeFor(node);
  node.x = Math.round(x - w / 2);
  node.y = Math.round(y - h / 2);
  return node;
}

// Human-readable display of a telemetry value with units.
export function fmtValue(v: unknown, unit = ''): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return `${v.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}${unit}`;
}

// ---------------------------------------------------------------------------
// Потоки / фазы технологических линий. Палитра — «Тип продукта» (HEX из
// легенды мнемосхемы). Выбирается в редакторе схемы и определяет цвет линии.
// ---------------------------------------------------------------------------

export interface PhaseMeta {
  id: string;
  label: string;
  color: string;
}

export const PHASE_TYPES: PhaseMeta[] = [
  { id: 'gas_haz', label: 'Опасные газы', color: '#FFD965' },
  { id: 'liq', label: 'Неопасные жидкости', color: '#0070C0' },
  { id: 'oil', label: 'Нефть и нефтепродукты', color: '#000000' },
  { id: 'gas', label: 'Неопасные газы', color: '#00B0F0' },
  { id: 'reag', label: 'Реагенты', color: '#9966FF' },
  { id: 'drain', label: 'Дренажные жидкости', color: '#7F6000' },
  { id: 'other', label: 'Прочие продукты', color: '#54426A' },
];

export const DEFAULT_PHASE = 'oil';

// Устаревшие id/kind старых схем -> тип продукта.
const PHASE_ALIASES: Record<string, string> = {
  process: 'oil',
  hot: 'gas',
  cooling: 'liq',
  crude: 'oil',
  des: 'oil',
  atb: 'oil',
  naph: 'oil',
  ker: 'oil',
  dt: 'oil',
  go: 'oil',
  maz: 'oil',
  gaz: 'gas_haz',
  fuel: 'gas_haz',
  steam: 'gas',
  water: 'liq',
  reag: 'reag',
  sig: 'other',
};

function resolvePhase(id: string): string {
  return PHASE_ALIASES[id] ?? id;
}

export function phaseMeta(id: string): PhaseMeta {
  const resolved = resolvePhase(id);
  return PHASE_TYPES.find((p) => p.id === resolved) ?? PHASE_TYPES[2];
}

export function normalizePhase(kind: string): string {
  const resolved = resolvePhase(kind);
  return PHASE_TYPES.some((p) => p.id === resolved) ? resolved : DEFAULT_PHASE;
}

// Контрастный цвет текста поверх заданного фона.
export function contrastText(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const lum = 0.299 * r + 0.587 * g + 0.114 * b;
  return lum > 150 ? '#111' : '#fff';
}

/** API/history retain SI; all UI surfaces apply the same display conversion. */
export function displayParamValue(key: string, value: number): number {
  if (['flow_kg_s', 'feed_flow', 'in_flow', 'out_flow', 'gas_out_flow', 'water_out_flow',
    'fuel_flow', 'distillate_flow', 'side_draw_flow', 'bottoms_flow', 'mass_flow_kg_s',
    'configured_flow_kg_s'].includes(key)) return value * 3.6;
  if (['pressure_bar', 'pressure_in_bar', 'pressure_out_bar', 'column_pressure_bar'].includes(key)) {
    return (value * 100000 - 101325) / 98066.5;
  }
  if (key === 'column_pressure') return (value - 101325) / 98066.5;
  if (key === 'column_temperature' || key === 'furnace_temperature') return value - 273.15;
  if (key === 'volumetric_flow_m3_s') return value * 3600;
  if (['pressure_rise_pa', 'npsha_pa', 'npshr_pa'].includes(key)) return value / 98066.5;
  if (key === 'power_w') return value / 1000;
  if (key === 'duty_w') return value / 1e6;
  if (key === 'efficiency') return value * 100;
  return value;
}
export function fmtParam(key: string, value: unknown, withUnit = true): string {
  return fmtValue(typeof value === 'number' ? displayParamValue(key, value) : value,
    withUnit ? PARAM_LABELS[key]?.unit ?? '' : '');
}
