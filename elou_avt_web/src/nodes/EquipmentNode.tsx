import { memo, createContext, useContext, useEffect, useMemo } from 'react';
import type { ReactElement, PointerEvent as ReactPointerEvent } from 'react';
import { Handle, Position, useReactFlow, useUpdateNodeInternals } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import type { NodeTelemetry, AlarmData } from '../types';
import type { MnemoItem, MnemoColDetail, MnemoFurDetail, ColDetailNozzle } from '../mnemo/mnemoTypes';
import type { MnemoLive } from '../mnemo/sources';
import { itemBBox, renderItem } from '../mnemo/symbols';
import { TYPE_COLORS, nodeSize, boundaryLabelSize, lineReferenceWidth, PARAM_LABELS, fmtParam } from '../schemeConfig';

export type EquipmentNodeData = {
  nodeType: string;
  name: string;
  telemetry: NodeTelemetry | null;
  schemeParams?: Record<string, unknown>;
  size?: { w: number; h: number };
  scale?: number;
  mnemo?: Partial<MnemoItem>;
  disp?: string[];
  tags?: Record<string, TagCfg>;
  alarms?: AlarmData[];
};

/** Per-square configuration: display name, position offset and scale. */
export interface TagCfg {
  label?: string;
  dx?: number;
  dy?: number;
  scale?: number;
}

export interface SchemeEditorActions {
  edit: boolean;
  onTagChange: (nodeId: string, key: string, patch: Partial<TagCfg>) => void;
  onRenameNode: (nodeId: string, name: string) => void;
  /** Точки излома линии: строго прямые углы, количество не ограничено. */
  onEdgeWaypoints: (edgeId: string, pts: { x: number; y: number }[]) => void;
  /**
   * Запомнить состояние перед изменением (для отмены). Вызывается в начале
   * жеста, а не на каждое движение мыши, иначе стек отмены забили бы
   * промежуточные кадры перетаскивания.
   */
  onHistoryMark: () => void;
  onScaleNode: (nodeId: string, scale: number) => void;
  onEdgeTagChange: (edgeId: string, key: string, patch: Partial<TagCfg>) => void;
  /** Отвод от линии: в точку врезки ставится тройник, от него идёт ветвь. */
  onEdgeBranch: (
    edgeId: string,
    targetNodeId: string,
    targetHandle: string,
    teeAt: { x: number; y: number },
    incoming?: boolean,
  ) => void;
}

export const SchemeEditorContext = createContext<SchemeEditorActions>({
  edit: false,
  onTagChange: () => {},
  onRenameNode: () => {},
  onEdgeWaypoints: () => {},
  onHistoryMark: () => {},
  onScaleNode: () => {},
  onEdgeTagChange: () => {},
  onEdgeBranch: () => {},
});

export type EquipmentNode = Node<EquipmentNodeData, 'equipment'>;

const HANDLE_STYLE = { width: 7, height: 7, background: 'var(--bg)', border: '1.5px solid var(--accent)' };

/**
 * ReactFlow node type -> mnemo symbol drawn exactly like avt4.html.
 */
const SYMBOL: Record<string, Partial<MnemoItem>> = {
  source: { t: 'box', w: 72, h: 24 },
  sink: { t: 'box', w: 72, h: 24 },
  pump: { t: 'pump' },
  valve: { t: 'valve', vt: 'cv' },
  angle_valve: { t: 'valve', vt: 'angle' },
  gate_valve: { t: 'valve', vt: 'gate' },
  mixer: { t: 'mix' },
  splitter: { t: 'mix' },
  elou: { t: 'ed', w: 120, h: 44, lv: 'lv' },
  heat_exchanger: { t: 'hx', w: 132, h: 40 },
  heater: { t: 'fur', w: 118, h: 66 },
  column: { t: 'col', w: 68, h: 200, tr: 16, sump: 34, lv: 'lv' },
  // Приказ №251-П: приложение 5, рисунок 83, горизонтальный аппарат.
  tank: { t: 'vves', w: 132, h: 56, lv: 'lv' },
  separator: { t: 'vves', w: 132, h: 56, lv: 'lv', lvw: 'lvw' },
  separator_s1k: { t: 'vves', w: 132, h: 56, lv: 'lv', lvw: 'lvw' },
};

const NOMINAL_LEVEL_H = 4;

/** Build a minimal MnemoLive from one node's telemetry. */
function buildLive(t: NodeTelemetry | null, color: string, height = NOMINAL_LEVEL_H): MnemoLive {
  const pct = (): number => {
    if (!t) return 0;
    const lv = t.params?.level_m;
    if (typeof lv !== 'number' || !Number.isFinite(lv)) return 0;
    return Math.min(100, Math.max(0, (lv / Math.max(height, 0.01)) * 100));
  };
  let fuel = 0;
  if (t) {
    const f = t.params?.fuel_flow;
    if (typeof f === 'number' && Number.isFinite(f)) fuel = f;
  }
  return {
    ctrl: () => undefined,
    sval: () => null,
    lvl: () => pct(),
    lw: () => pct(),
    flowColor: () => color,
    run: () => (t?.failed ? 'fail' : t?.running ? 'run' : 'off'),
    equip: () => undefined,
    gate: () => t?.params?.open === true,
    valve: () => {
      if (t?.failed) return 'fail';
      if (t?.type === 'gate_valve') return t.params?.open === true ? 'open' : 'closed';
      const pos = t?.params?.position;
      if (typeof pos !== 'number' || !Number.isFinite(pos)) return 'mid';
      return pos >= 99 ? 'open' : pos <= 1 ? 'closed' : 'mid';
    },
    param: () => null,
    fireOn: fuel > 0.15,
    edVolt: true,
  };
}

const handles = (type: string, schemeParams?: Record<string, unknown>) => {
  const left = (top: number) => ({ ...HANDLE_STYLE, top: `${top}%` });
  const right = (top: number) => ({ ...HANDLE_STYLE, top: `${top}%` });
  const mid = () => ({ ...HANDLE_STYLE, left: '50%' });
  const bottom = (at: number) => ({ ...HANDLE_STYLE, left: `${at}%` });

  switch (type) {
    case 'junction':
      // Тройник — точка на трубе, а не аппарат: штуцеры совмещены с центром,
      // поэтому и магистраль, и отвод выходят ровно из места врезки.
      return (
        <>
          <Handle type="target" position={Position.Left} id="in"
            style={{ ...HANDLE_STYLE, width: 1, height: 1, opacity: 0, left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
          <Handle type="source" position={Position.Right} id="out"
            style={{ ...HANDLE_STYLE, width: 1, height: 1, opacity: 0, left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }} />
        </>
      );
    case 'source':
      return <Handle type="source" position={Position.Right} id="out" style={right(50)} />;
    case 'sink':
      return <Handle type="target" position={Position.Left} id="in" style={left(50)} />;
    case 'heat_exchanger':
      return (
        <>
          <Handle type="target" position={Position.Left} id="hot_in" style={left(38.5)} />
          <Handle type="source" position={Position.Right} id="hot_out" style={right(38.5)} />
          <Handle type="target" position={Position.Top} id="cold_in" style={bottom(16.25)} />
          <Handle type="source" position={Position.Bottom} id="cold_out" style={bottom(81.25)} />
        </>
      );
    case 'column':
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(50)} />
          <Handle type="source" position={Position.Right} id="distillate" style={right(30)} />
          <Handle type="source" position={Position.Right} id="bottoms" style={right(70)} />
        </>
      );
    case 'separator_s1k':
      // С-1К: входы слева и справа, выходы сверху и снизу.
      return (
        <>
          <Handle type="target" position={Position.Left} id="in_l" style={left(50)} />
          <Handle type="target" position={Position.Right} id="in_r" style={right(50)} />
          <Handle type="source" position={Position.Top} id="out_t" style={mid()} />
          <Handle type="source" position={Position.Bottom} id="out_b" style={mid()} />
        </>
      );
    case 'mixer': {
      // Смеситель объединяет n потоков: n входов слева, один выход справа.
      const n = typeof schemeParams?.num_inputs === 'number' ? Math.max(1, Math.min(8, schemeParams.num_inputs)) : 2;
      return (
        <>
          {Array.from({ length: n }, (_, i) => (
            <Handle
              key={`in${i}`}
              type="target"
              position={Position.Left}
              id={`in${i}`}
              style={left(n === 1 ? 50 : 20 + (i * 60) / (n - 1))}
            />
          ))}
          <Handle type="source" position={Position.Right} id="out" style={right(50)} />
        </>
      );
    }
    case 'splitter': {
      // Разъединитель делит поток на n ветвей: один вход слева, n выходов
      // справа (зеркально смесителю).
      const n = typeof schemeParams?.num_outputs === 'number' ? Math.max(1, Math.min(8, schemeParams.num_outputs)) : 2;
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(50)} />
          {Array.from({ length: n }, (_, i) => (
            <Handle
              key={`out${i}`}
              type="source"
              position={Position.Right}
              id={`out${i}`}
              style={right(n === 1 ? 50 : 20 + (i * 60) / (n - 1))}
            />
          ))}
        </>
      );
    }
    case 'elou':
      // ЭЛОУ: вход сырья слева, выход нефти справа, выход солевого
      // раствора снизу (нефть отдельным потоком не выводится).
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(50)} />
          <Handle type="source" position={Position.Right} id="oil_out" style={right(50)} />
          <Handle type="source" position={Position.Bottom} id="out" style={mid()} />
        </>
      );
    case 'tank':
      // Верхний штуцер — отвод паров, нижний — дренаж воды у Е-1.
      // Нефтепродукт остаётся на отдельном боковом выходе.
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(50)} />
          <Handle type="source" position={Position.Right} id="out" style={right(50)} />
          <Handle type="source" position={Position.Top} id="gas_out" style={mid()} />
          <Handle type="source" position={Position.Bottom} id="water_out" style={mid()} />
        </>
      );
    case 'heater':
      // П-1: печь с 5 секциями подогрева — по одной паре вход/выход на
      // секцию (основная нефть, боковые потоки и паро-перегреватель ПП).
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(10)} />
          <Handle type="target" position={Position.Left} id="in2" style={left(30)} />
          <Handle type="target" position={Position.Left} id="in3" style={left(50)} />
          <Handle type="target" position={Position.Left} id="in4" style={left(70)} />
          <Handle type="target" position={Position.Left} id="pp_in" style={left(90)} />
          <Handle type="source" position={Position.Right} id="out" style={right(10)} />
          <Handle type="source" position={Position.Right} id="out2" style={right(30)} />
          <Handle type="source" position={Position.Right} id="out3" style={right(50)} />
          <Handle type="source" position={Position.Right} id="out4" style={right(70)} />
          <Handle type="source" position={Position.Right} id="pp_out" style={right(90)} />
        </>
      );
    default:
      return (
        <>
          <Handle type="target" position={Position.Left} id="in" style={left(50)} />
          <Handle type="source" position={Position.Right} id="out" style={right(50)} />
        </>
      );
  }
};

/**
 * У АВЗ через пучок идёт один технологический (газовый) поток. Воздух —
 * окружающая охлаждающая среда, поэтому для него нет трубопроводных штуцеров.
 */
function airCoolerHandles(item: MnemoItem, g: NodeGeom): ReactElement {
  const w = item.w || 132;
  const bodyH = Math.max(item.h || 30, (w * 104) / 156);
  const inlet = posFor(g, item.x, item.y + (18 * bodyH) / 104);
  const outlet = posFor(g, item.x + w, item.y + (18 * bodyH) / 104);
  const pointStyle = (p: { left: number; top: number }) => ({
    ...HANDLE_STYLE,
    left: `${p.left}%`,
    top: `${p.top}%`,
    right: 'auto',
    bottom: 'auto',
    transform: 'translate(-50%, -50%)',
  });
  return (
    <>
      <Handle type="target" position={Position.Left} id="hot_in" style={pointStyle(inlet)} />
      <Handle type="source" position={Position.Right} id="hot_out" style={pointStyle(outlet)} />
    </>
  );
}

/**
 * Хэндлы детальной колонны по отросткам пресета: каждый штуцер — точка
 * подключения потока ровно на его конце (фланце). Направление берётся из
 * `dir` отростка (3 выхода, остальные — входы).
 */
type NodeGeom = {
  s: number;
  viewScale: number;
  offX: number;
  offY: number;
  /** Фактическая ширина DOM-карточки, к которой применяются проценты handle. */
  cardW: number;
  cardH: number;
  nodeW: number;
  offLeft: number;
  offTop: number;
  bx0: number;
  by0: number;
  bh: number;
  itemX: number;
  itemY: number;
};

function columnHandles(nozzles: ColDetailNozzle[], g: NodeGeom): ReactElement[] {
  const el: ReactElement[] = [];
  for (let i = 0; i < nozzles.length; i++) {
    const nz = nozzles[i];
    if (!nz.port) continue;
    let from: { x: number; y: number } | undefined;
    let to: { x: number; y: number } | undefined;
    if (nz.from && nz.to) {
      from = nz.from;
      to = nz.to;
    } else if (nz.pts && nz.pts.length >= 2) {
      const q = nz.pts[nz.pts.length - 2];
      const p = nz.pts[nz.pts.length - 1];
      from = { x: q[0], y: q[1] };
      to = { x: p[0], y: p[1] };
    }
    if (!from || !to) continue;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const horizontal = Math.abs(dx) >= Math.abs(dy);
    const out = nz.dir === 'out';
    const sx = g.itemX + to.x * g.s;
    const sy = g.itemY + to.y * g.s;
    const left = ((g.offLeft + g.offX + (sx - g.bx0) * g.viewScale) / g.cardW) * 100;
    const top = ((g.offTop + g.offY + (sy - g.by0) * g.viewScale) / g.cardH) * 100;
    const pos = horizontal
      ? to.x > from.x ? Position.Right : Position.Left
      : to.y > from.y ? Position.Bottom : Position.Top;
    el.push(
      <Handle
        key={`c${i}`}
        type={out ? 'source' : 'target'}
        position={pos}
        id={nz.port ?? 'in'}
        style={{ ...HANDLE_STYLE, left: `${left}%`, top: `${top}%`, transform: 'translate(-50%, -50%)' }}
      />,
    );
  }
  return el;
}

const posFor = (g: NodeGeom, sx: number, sy: number) => {
  const left = ((g.offLeft + g.offX + (sx - g.bx0) * g.viewScale) / g.cardW) * 100;
  const top = ((g.offTop + g.offY + (sy - g.by0) * g.viewScale) / g.cardH) * 100;
  return { left, top };
};

function symbolHandles(item: MnemoItem, g: NodeGeom): ReactElement[] {
  if (item.vt === 'angle') {
    const inP = posFor(g, item.x - 30, item.y);
    const outP = posFor(g, item.x, item.y);
    return [
      <Handle key="in" type="target" position={Position.Left} id="in" style={{ ...HANDLE_STYLE, top: `${inP.top}%` }} />,
      <Handle key="out" type="source" position={Position.Bottom} id="out" style={{ ...HANDLE_STYLE, left: `${outP.left}%` }} />,
    ];
  }
  const inP = posFor(g, item.x - 26, item.y);
  const outP = posFor(g, item.x + 26, item.y);
  return [
    <Handle key="in" type="target" position={Position.Left} id="in" style={{ ...HANDLE_STYLE, top: `${inP.top}%` }} />,
    <Handle key="out" type="source" position={Position.Right} id="out" style={{ ...HANDLE_STYLE, top: `${outP.top}%` }} />,
  ];
}

/** Точки подключений УГО теплообменника в точности совпадают с концами линий. */
function heatExchangerHandles(item: MnemoItem, g: NodeGeom): ReactElement[] {
  const w = item.w || 160;
  const bodyH = Math.max(item.h || 30, (w * 130) / 160);
  const at = (sx: number, sy: number) => posFor(g, item.x + sx, item.y + sy);
  const hotIn = at((32 * w) / 160, (50 * bodyH) / 130);
  const hotOut = at((128 * w) / 160, (50 * bodyH) / 130);
  const coldIn = at((44 * w) / 160, (30 * bodyH) / 130);
  const coldOut = at((116 * w) / 160, (80 * bodyH) / 130);
  const style = (p: { left: number; top: number }) => ({
    ...HANDLE_STYLE,
    left: `${p.left}%`,
    top: `${p.top}%`,
    // У классов Position.Left/Right/Top/Bottom есть свои right/bottom.
    // Сбрасываем их: иначе браузер растягивает абсолютное позиционирование
    // и точка визуально уезжает от конца штуцера.
    right: 'auto',
    bottom: 'auto',
    transform: 'translate(-50%, -50%)',
  });
  return [
    <Handle key="hot_in" type="target" position={Position.Left} id="hot_in" style={style(hotIn)} />,
    <Handle key="hot_out" type="source" position={Position.Right} id="hot_out" style={style(hotOut)} />,
    <Handle key="cold_in" type="target" position={Position.Top} id="cold_in" style={style(coldIn)} />,
    <Handle key="cold_out" type="source" position={Position.Bottom} id="cold_out" style={style(coldOut)} />,
  ];
}

const TAG_STACK = 52;

function MnemoEquipmentNode({ id, data, selected }: NodeProps<EquipmentNode>) {
  const { nodeType, name, telemetry, size, scale, mnemo, disp, tags, alarms, schemeParams } = data;
  const { edit, onTagChange, onRenameNode, onScaleNode, onHistoryMark } = useContext(SchemeEditorContext);
  const { getZoom } = useReactFlow();
  const updateNodeInternals = useUpdateNodeInternals();
  const scaleFactor = Math.max(0.3, Math.min(3, scale ?? 1));
  // Граничные плашки растут вместе с названием потока. Учитываем сохранённый
  // размер как нижнюю границу, чтобы не сжать вручную расширенную плашку.
  const boundarySize = (nodeType === 'source' || nodeType === 'sink') && !schemeParams?.line_reference
    ? boundaryLabelSize(name)
    : undefined;
  const rawSize = boundarySize
    ? {
        w: Math.max(size?.w ?? 0, boundarySize.w),
        h: Math.max(size?.h ?? 0, boundarySize.h),
      }
    : (size ?? nodeSize(nodeType));
  const box = { w: rawSize.w * scaleFactor, h: rawSize.h * scaleFactor };
  const color = telemetry?.failed ? '#f87171' : TYPE_COLORS[nodeType] ?? '#38bdf8';
  const presetMnemo = schemeParams?.mnemo as Partial<MnemoItem> | undefined;
  // УГО холодильника воздушного охлаждения выбирается для аппаратов,
  // обозначенных АВЗ/АВГ, и для нового элемента палитры.
  const isAirCooler = nodeType === 'heat_exchanger' && (
    schemeParams?.preset === 'air_cooler' || /(?:^|[\s,])АВ[ЗГ][\s-]*\d/i.test(name)
  );
  const heatExchangerRole = schemeParams?.thermal_role === 'cooler' ||
    (schemeParams?.thermal_role !== 'heater' && /^[ХX]\s*-/i.test(name.trim()))
    ? 'cooler'
    : 'heater';
  const defaultMnemo = isAirCooler
    ? { t: 'air', w: 132, h: 92 }
    : nodeType === 'heat_exchanger'
      ? { t: 'hx', w: 160, h: 130, st: heatExchangerRole }
      : SYMBOL[nodeType] ?? {};
  const item: MnemoItem = {
    t: 'box',
    x: 0,
    y: 0,
    n: name,
    ...(mnemo ?? presetMnemo ?? defaultMnemo),
  };
  if (boundarySize) {
    // SVG рисуется с отступом 3 px с каждой стороны. Его собственный box
    // должен повторять размер карточки, иначе текст оказывается ниже рамки.
    item.w = Math.max(1, box.w - 6);
    item.h = Math.max(1, box.h - 6);
  }
  if (nodeType === 'gate_valve' || nodeType === 'valve' || nodeType === 'angle_valve') item.gate = id;
  const bb = itemBBox(item);
  const live = buildLive(telemetry, color, Number(schemeParams?.height_m) || (nodeType === 'tank' ? 6 : NOMINAL_LEVEL_H));
  const svgW = box.w - 6;
  const svgH = Math.max(box.h - 6, (bb[3] * svgW) / bb[2]);
  const detail = item.detail as MnemoColDetail | MnemoFurDetail | undefined;
  const colNozzles = (detail as MnemoColDetail | undefined)?.sections?.flatMap((s) => s.nozzles ?? []) ?? [];
  const furFlows = (detail as MnemoFurDetail | undefined)?.flows ?? [];
  const presetNozzles: ColDetailNozzle[] = [...colNozzles, ...furFlows];
  const usePresetHandles = presetNozzles.some((n) => n.port);
  const geom = useMemo(() => {
    const nodeW = item.w || detail?.nodeW || 130;
    const s = nodeW / (detail?.vb.w || 640);
    const viewScale = Math.min(svgW / bb[2], svgH / bb[3]);
    return {
      s,
      viewScale,
      offX: (svgW - bb[2] * viewScale) / 2,
      offY: (svgH - bb[3] * viewScale) / 2,
      cardW: box.w,
      cardH: svgH + 6,
      nodeW,
      offLeft: (box.w - svgW) / 2,
      offTop: (svgH + 6 - svgH) / 2,
      bx0: bb[0],
      by0: bb[1],
      bh: bb[3],
      itemX: item.x,
      itemY: item.y,
    };
  }, [svgW, svgH, bb, item.w, item.x, item.y, detail, box.w]);
  const isValve = nodeType === 'valve' || nodeType === 'gate_valve' || nodeType === 'angle_valve';
  const nodeHandles = usePresetHandles
    ? columnHandles(presetNozzles, geom)
    : isAirCooler
      ? airCoolerHandles(item, geom)
      : nodeType === 'heat_exchanger'
        ? heatExchangerHandles(item, geom)
      : isValve
      ? symbolHandles(item, geom)
      : handles(nodeType, schemeParams);

  // React Flow кэширует геометрию handle. Обновляем её после изменения
  // габарита или вида УГО, чтобы точка и реальный якорь линии не расходились.
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, updateNodeInternals, nodeType, isAirCooler, item.t, item.w, item.h, box.w, svgH]);
  const dispParams = (disp ?? []).filter((k) => telemetry?.params?.[k] !== null && telemetry?.params?.[k] !== undefined);

  const failed = !!telemetry?.failed;
  const nodeAlarms = alarms ?? [];
  const critical = !failed && nodeAlarms.some((a) => a.severity === 'CRITICAL');
  const warning = !failed && !critical && nodeAlarms.some((a) => a.severity !== 'CRITICAL');
  const state = failed ? 'fault' : critical ? 'alarm' : warning ? 'warning' : 'normal';

  // Состояние и мигание рамки шкалы уровня (использует символ 'vves').
  item.state = state;
  item.unacked = !failed && (critical || warning);
  // Обозначение уровня: 'флегма' (тёмная жидкость + вода) либо 'вода'.
  item.lmode = schemeParams?.level_mode === 'water' ? 'water' : 'reflux';

  const renameNode = () => {
    const n = window.prompt('Название узла:', name);
    if (n && n.trim() && n.trim() !== name) onRenameNode(id, n.trim());
  };

  const startTagDrag = (e: ReactPointerEvent, key: string, cfg: TagCfg | undefined, index: number) => {
    e.stopPropagation();
    e.preventDefault();
    onHistoryMark();
    const zoom = getZoom();
    const baseX = cfg?.dx ?? box.w + 10;
    const baseY = cfg?.dy ?? index * TAG_STACK;
    const sx = e.clientX;
    const sy = e.clientY;
    const onMove = (ev: PointerEvent) => {
      onTagChange(id, key, { dx: baseX + (ev.clientX - sx) / zoom, dy: baseY + (ev.clientY - sy) / zoom });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startScaleDrag = (e: ReactPointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    onHistoryMark();
    const zoom = getZoom();
    const base = scaleFactor;
    const sx = e.clientX;
    const onMove = (ev: PointerEvent) => {
      const next = Math.max(0.3, Math.min(3, base + (ev.clientX - sx) / 250 / zoom));
      onScaleNode(id, Number(next.toFixed(2)));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startTagScale = (e: ReactPointerEvent, key: string, cfg: TagCfg | undefined) => {
    e.stopPropagation();
    e.preventDefault();
    const zoom = getZoom();
    const base = cfg?.scale ?? 1;
    const sx = e.clientX;
    const onMove = (ev: PointerEvent) => {
      const scale = Math.max(0.4, Math.min(3, base + (ev.clientX - sx) / 150 / zoom));
      onTagChange(id, key, { scale });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const renameTag = (key: string, cfg: TagCfg | undefined) => {
    const meta = PARAM_LABELS[key];
    const n = window.prompt('Название квадратика:', cfg?.label ?? meta?.label ?? key);
    if (n !== null) { onHistoryMark(); onTagChange(id, key, { label: n.trim() || undefined }); }
  };

  // Тройник — не аппарат, а точка врезки на трубе: рисуем просто узелок,
  // без карточки, подписи и квадратиков параметров.
  if (nodeType === 'field_instrument') {
    const positionTag = String(schemeParams?.position_tag ?? name);
    const parameter = String(schemeParams?.parameter ?? 'pressure_bar');
    const value = telemetry?.params[parameter];
    const valid = typeof value === 'number' && Number.isFinite(value);
    const critical = nodeAlarms.some(a => a.severity === 'CRITICAL');
    const warning = nodeAlarms.length > 0;
    const failed = telemetry?.failed === true;
    const background = failed ? '#ffa500' : critical ? '#ff0000' : warning ? '#ffff00' : '#d9d9d9';
    const foreground = failed ? '#ffa500' : critical ? '#ff0000' : warning ? '#ffff00' : '#ffffff';
    const isPaz = schemeParams?.system === 'ПАЗ' || /^[A-Z]*Z/i.test(positionTag);
    const pazState = telemetry?.params.paz_state;
    return <div className={`field-instrument${selected ? ' sel' : ''}`} style={{ width: 104 * scaleFactor, padding: 0 }} title={`${positionTag} · ${name}`}>
      {edit && <Handle type="source" position={Position.Right} id="measurement" className="measurement-handle"
        title="Протяните измерительную связь к трубе или штуцеру аппарата" />}
      {/* Приказ № 251-П, раздел 7.4.2, рисунки 7–9: TAG, значение, единица; ромб ПАЗ. */}
      <svg width={104 * scaleFactor} height={48 * scaleFactor} viewBox="0 0 104 48" aria-label={`Прибор КИП ${positionTag}`}>
        <rect x="8" y="1" width="95" height="46" fill={background} stroke="#8c8c8c" strokeWidth="0.6" />
        <text x="55.5" y="12" textAnchor="middle" fill="#111" fontSize="10"
          textLength={positionTag.length > 15 ? 90 : undefined} lengthAdjust="spacingAndGlyphs">{positionTag}</text>
        <rect x="9" y="16" width="93" height="22" fill="#404040" />
        <text x="55.5" y="33" textAnchor="middle" fill={foreground} fontSize={failed ? 14 : 17} fontFamily="Arial, sans-serif">
          {failed ? 'ОТКАЗ' : valid ? fmtParam(parameter, value, false).replace('.', ',') : '—'}
        </text>
        <text x="100" y="45" textAnchor="end" fill="#111" fontSize="8">{PARAM_LABELS[parameter]?.unit ?? ''}</text>
        {isPaz && <path d="M8 10 L15 17 L8 24 L1 17 Z" stroke="#777" strokeWidth="0.6"
          fill={pazState === 'tripped' ? '#ff0000' : pazState === 'active' ? '#ffff00' : '#ffffff'}>
          <title>{pazState === 'tripped' ? 'ПАЗ сработала' : pazState === 'active' ? 'ПАЗ активна' : pazState === 'bypassed' ? 'ПАЗ отключена' : 'Нет данных о состоянии ПАЗ'}</title>
        </path>}
      </svg>
    </div>;
  }

  if (schemeParams?.line_reference === true && (nodeType === 'sink' || nodeType === 'source')) {
    const width = lineReferenceWidth(name);
    const shoulder = width - 16;
    return <div className={`line-reference${selected ? ' sel' : ''}${edit ? ' handles-visible' : ' handles-hidden'}`} style={{width,height:40}}
      title={nodeType === 'source' ? 'Входящая линия: двойной щелчок меняет источник' : 'Продолжение линии: двойной щелчок меняет назначение'}
      onDoubleClick={edit ? e => { e.stopPropagation(); renameNode(); } : undefined}>
      <svg width={width} height="40" viewBox={`0 0 ${width} 40`}>
        <path d={`M1 8 H${shoulder} L${width - 2} 20 L${shoulder} 32 H1 Z`} fill="var(--panel)" stroke="currentColor" />
        <text x="8" y="24" fontSize="11" fill="currentColor">{name}</text>
      </svg>
      <Handle type={nodeType === 'source' ? 'source' : 'target'} position={nodeType === 'source' ? Position.Right : Position.Left}
        id={nodeType === 'source' ? 'out' : 'in'} style={{...HANDLE_STYLE,top:'50%'}} />
    </div>;
  }

  if (nodeType === 'junction') {
    return (
      <div
        className={`mn-junction${selected ? ' sel' : ''}${edit ? ' handles-visible' : ' handles-hidden'}`}
        title={name}
        style={{
          width: 10, height: 10, borderRadius: '50%',
          background: color, border: '1px solid var(--bg)',
        }}
        onContextMenu={edit ? (e) => {
          e.preventDefault();
          e.stopPropagation();
          window.dispatchEvent(new CustomEvent('node-context-menu', { detail: { id, x: e.clientX, y: e.clientY } }));
        } : undefined}
      >
        {nodeHandles}
      </div>
    );
  }

  return (
    <div
      className={`mn-node state-${state}${nodeType === 'heat_exchanger' ? ' mn-node-hx' : ''}${selected ? ' sel' : ''}${scaleFactor !== 1 ? ' scaled' : ''}${edit ? ' handles-visible' : ' handles-hidden'}`}
      style={{ width: box.w, height: svgH + 6 }}
      onDoubleClick={edit ? (e) => { e.stopPropagation(); renameNode(); } : undefined}
      onContextMenu={edit ? (e) => {
        e.preventDefault();
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent('node-context-menu', { detail: { id, x: e.clientX, y: e.clientY } }));
      } : undefined}
    >
      <svg
        viewBox={`${bb[0]} ${bb[1]} ${bb[2]} ${bb[3]}`}
        width={svgW}
        height={svgH}
      >
        {renderItem(item, live)}
      </svg>
      {telemetry?.control_mode && <span className={`mode-mark equipment-mode-mark ${telemetry.control_mode === 'АВТ' ? 'auto' : 'manual'}`}
        title={telemetry.control_mode === 'АВТ' ? 'Автоматический режим' : 'Ручной режим'}>
        {telemetry.control_mode === 'АВТ' ? 'А' : 'Р'}
      </span>}
      {edit && scaleFactor !== 1 && (
        <div className="mn-node-scale-badge" title="Масштаб узла">{Math.round(scaleFactor * 100)}%</div>
      )}
      {edit && (
        <div className="mn-node-scale-handle" onPointerDown={startScaleDrag} title="Масштаб узла (тянуть вправо/влево)" />
      )}
      {dispParams.length > 0 && (
        <div className="mn-node-tags">
          {dispParams.map((k, j) => {
            const meta = PARAM_LABELS[k];
            const cfg = tags?.[k];
            const v = telemetry?.params?.[k];
            const num = typeof v === 'number' && Number.isFinite(v);
            const boolV = typeof v === 'boolean';
            const disp = failed ? 'ОТКАЗ' : boolV ? (v ? 'ОТКР' : 'ЗАКР') : num ? fmtParam(k, v, false) : '—';
            return (
              <div
                key={k}
                className={`mn-node-tag state-${state}${edit ? ' tag-editable' : ''}`}
                style={{
                  left: cfg?.dx ?? box.w + 10,
                  top: cfg?.dy ?? j * TAG_STACK,
                  transform: `scale(${cfg?.scale ?? 1})`,
                  transformOrigin: 'top left',
                }}
                onPointerDown={edit ? (e) => startTagDrag(e, k, cfg, j) : undefined}
                onDoubleClick={edit ? (e) => { e.stopPropagation(); renameTag(k, cfg); } : undefined}
              >
                <div className="tag">{cfg?.label ?? meta?.label ?? k}</div>
                <div className={`val${failed ? ' text' : ''}`}>{disp}</div>
                <div className="unit">{meta?.unit ?? ''}</div>
                {edit && (
                  <div
                    className="mn-node-tag-scale"
                    onPointerDown={(e) => startTagScale(e, k, cfg)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
      {state === 'alarm' || state === 'fault' ? (
        <span className="mn-node-alarm">АВАРИЯ</span>
      ) : null}
      {nodeHandles}
    </div>
  );
}

export default memo(MnemoEquipmentNode);
