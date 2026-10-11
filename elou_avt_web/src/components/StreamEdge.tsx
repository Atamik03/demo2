import { memo, useContext, useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { BaseEdge, useReactFlow } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';
import { SchemeEditorContext } from '../nodes/EquipmentNode';
import type { TagCfg } from '../nodes/EquipmentNode';
import { STREAM_PARAMS, phaseMeta, fmtParam } from '../schemeConfig';

/**
 * Поток (ребро мнемосхемы): ортогональная линия со сглаженными углами.
 * В режиме редактирования линию можно перетаскивать мышью в любом
 * направлении — сдвиг по двум осям (offsetX/offsetY) позволяет развести
 * параллельные линии и передвинуть их вдоль потока.
 * Свойства потока выводятся квадратиками у средней части линии.
 * В режиме SCADA линия некликабельна.
 */

export interface StreamEdgeData {
  phase?: string;
  disp?: string[];
  tags?: Record<string, TagCfg>;
  sourceTelemetry?: {
    failed?: boolean | null;
    params?: Record<string, number | boolean | string | null>;
  } | null;
}

type Point = { x: number; y: number };

const DIR: Record<string, Point> = {
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  top: { x: 0, y: -1 },
  bottom: { x: 0, y: 1 },
};

const LEAD = 20;
const TAG_W = 92;
const TAG_H = 54;
const TAG_STACK = 56;
const CORNER_R = 12;

/** Строит путь со сглаженными углами: каждый поворот 90° превращается в
 *  плавную дугу (кубическая кривая Безье), геометрия трассы не меняется. */
function smoothPath(pts: Point[]): string {
  if (pts.length < 3) {
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join('');
  }
  let d = `M${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1];
    const b = pts[i];
    const c = pts[i + 1];
    const l1 = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    const l2 = Math.abs(c.x - b.x) + Math.abs(c.y - b.y);
    if (l1 === 0 || l2 === 0) {
      d += `L${b.x} ${b.y}`;
      continue;
    }
    const r = Math.min(CORNER_R, l1 / 2, l2 / 2);
    const p1 = { x: b.x - ((b.x - a.x) / l1) * r, y: b.y - ((b.y - a.y) / l1) * r };
    const p2 = { x: b.x + ((c.x - b.x) / l2) * r, y: b.y + ((c.y - b.y) / l2) * r };
    const k = r * 0.5523;
    const c1 = { x: b.x - ((b.x - a.x) / l1) * k, y: b.y - ((b.y - a.y) / l1) * k };
    const c2 = { x: b.x + ((c.x - b.x) / l2) * k, y: b.y + ((c.y - b.y) / l2) * k };
    d += `L${p1.x} ${p1.y}`;
    d += `C${c1.x} ${c1.y} ${c2.x} ${c2.y} ${p2.x} ${p2.y}`;
  }
  const last = pts[pts.length - 1];
  d += `L${last.x} ${last.y}`;
  return d;
}

/** Шаг привязки точек излома, px холста. */
export const SNAP = 10;
/** На таком расстоянии точка излома «прилипает» к оси соседней точки. */


export const snap = (v: number) => Math.round(v / SNAP) * SNAP;

/**
 * Ортогональная трасса через точки излома (углы сглаживаются).
 *
 * Все участки строго горизонтальные или вертикальные: между соседними
 * точками вставляется угол 90°, направление чередуется, поэтому линия не
 * «плывёт» и каждая точка излома — жёсткий якорь. Точек может быть сколько
 * угодно. Возвращает также точку-якорь для квадратиков свойств и сами
 * вершины трассы.
 */
function orthogonalPath(
  sx: number,
  sy: number,
  sourcePosition: string,
  tx: number,
  ty: number,
  targetPosition: string,
  waypoints: Point[],
  sourceLead = LEAD, targetLead = LEAD,
): { path: string; anchor: Point; horizontal: boolean; points: Point[] } {
  const s: Point = { x: sx, y: sy };
  const t: Point = { x: tx, y: ty };
  const ds = DIR[sourcePosition] ?? DIR.right;
  const dt = DIR[targetPosition] ?? DIR.left;
  const so: Point = { x: s.x + ds.x * sourceLead, y: s.y + ds.y * sourceLead };
  const to: Point = { x: t.x + dt.x * targetLead, y: t.y + dt.y * targetLead };

  const nodes: Point[] = [s, so, ...waypoints, to, t];
  const pts: Point[] = [nodes[0]];
  // Первый участок идёт вдоль штуцера, дальше направление чередуется.
  let horiz = ds.x !== 0;
  for (let i = 1; i < nodes.length; i++) {
    const a = pts[pts.length - 1];
    const b = nodes[i];
    if (a.x === b.x && a.y === b.y) continue;
    if (a.x === b.x) { pts.push(b); horiz = false; continue; }
    if (a.y === b.y) { pts.push(b); horiz = true; continue; }
    // Последний участок перед входом в штуцер обязан идти вдоль него.
    const intoStub = targetLead > 0 && i === nodes.length - 2;
    const goHoriz = intoStub ? dt.x === 0 : horiz;
    pts.push(goHoriz ? { x: b.x, y: a.y } : { x: a.x, y: b.y }, b);
    horiz = !goHoriz;
  }
  const clean = pts.filter(
    (p, i, arr) => i === 0 || p.x !== arr[i - 1].x || p.y !== arr[i - 1].y,
  );

  // Якорь подписей — середина самого длинного участка.
  let anchor: Point = clean[Math.floor(clean.length / 2)] ?? s;
  let horizontal = true;
  let best = -1;
  for (let i = 1; i < clean.length; i++) {
    const a = clean[i - 1];
    const b = clean[i];
    const len = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    if (len > best) {
      best = len;
      anchor = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      horizontal = a.y === b.y;
    }
  }
  return { path: smoothPath(clean), anchor, horizontal, points: clean };
}

function StreamTags({
  id,
  data,
  anchor,
  horizontal,
}: {
  id: string;
  data: StreamEdgeData;
  anchor: Point;
  horizontal: boolean;
}) {
  const { edit, onEdgeTagChange, onHistoryMark } = useContext(SchemeEditorContext);
  const { getZoom } = useReactFlow();
  const disp = data.disp ?? [];
  const tags = data.tags ?? {};
  const src = data.sourceTelemetry;
  const phase = phaseMeta(data.phase ?? 'crude');

  if (disp.length === 0) return null;

  const startDrag = (e: ReactPointerEvent, key: string, cfg: TagCfg | undefined, index: number) => {
    e.stopPropagation();
    e.preventDefault();
    onHistoryMark();
    const zoom = getZoom();
    const baseX = cfg?.dx ?? 0;
    const baseY = cfg?.dy ?? 0;
    const sx = e.clientX;
    const sy = e.clientY;
    const onMove = (ev: PointerEvent) => {
      onEdgeTagChange(id, key, { dx: baseX + (ev.clientX - sx) / zoom, dy: baseY + (ev.clientY - sy) / zoom });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startScale = (e: ReactPointerEvent, key: string, cfg: TagCfg | undefined) => {
    e.stopPropagation();
    e.preventDefault();
    onHistoryMark();
    const zoom = getZoom();
    const base = cfg?.scale ?? 1;
    const sx = e.clientX;
    const onMove = (ev: PointerEvent) => {
      const scale = Math.max(0.4, Math.min(3, base + (ev.clientX - sx) / 150 / zoom));
      onEdgeTagChange(id, key, { scale });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const rename = (key: string, cfg: TagCfg | undefined) => {
    const meta = STREAM_PARAMS[key];
    const n = window.prompt('Название квадратика:', cfg?.label ?? meta?.label ?? key);
    if (n !== null) { onHistoryMark(); onEdgeTagChange(id, key, { label: n.trim() || undefined }); }
  };

  return (
    <g>
      {disp.map((k, j) => {
        const cfg = tags[k];
        const meta = STREAM_PARAMS[k];
        const failed = !!src?.failed;
        let text: string;
        if (failed) {
          text = 'ОТКАЗ';
        } else if (k === 'phase') {
          text = phase.label;
        } else {
          const v = src?.params?.[k];
          text = typeof v === 'number' && Number.isFinite(v)
            ? fmtParam(k, v)
            : typeof v === 'boolean'
              ? v ? 'ДА' : 'НЕТ'
              : '—';
        }
        const state = failed ? 'fault' : 'normal';
        const left = horizontal
          ? anchor.x - TAG_W / 2 + (cfg?.dx ?? 0)
          : anchor.x + 18 + j * (TAG_W + 6) + (cfg?.dx ?? 0);
        const top = horizontal
          ? anchor.y + 18 + j * TAG_STACK + (cfg?.dy ?? 0)
          : anchor.y - TAG_H / 2 + (cfg?.dy ?? 0);
        return (
          <foreignObject
            key={k}
            x={left}
            y={top}
            width={TAG_W}
            height={TAG_H}
            style={{ overflow: 'visible', pointerEvents: edit ? 'auto' : 'none' }}
          >
            <div
              className={`mn-node-tag edge-tag state-${state}${edit ? ' tag-editable' : ''}`}
              style={{
                transform: `scale(${cfg?.scale ?? 1})`,
                transformOrigin: '0 0',
              }}
              onPointerDown={edit ? (e) => startDrag(e, k, cfg, j) : undefined}
              onDoubleClick={edit ? (e) => { e.stopPropagation(); rename(k, cfg); } : undefined}
            >
              <div className="tag">{cfg?.label ?? meta?.label ?? k}</div>
              <div className={`val${failed ? ' text' : ''}`}>{text}</div>
              <div className="unit">{meta?.unit ?? ''}</div>
              {edit && (
                <div
                  className="mn-node-tag-scale"
                  onPointerDown={(e) => startScale(e, k, cfg)}
                />
              )}
            </div>
          </foreignObject>
        );
      })}
    </g>
  );
}

function StreamEdge({ id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition,
  targetPosition, markerEnd, style, pathOptions, data }: EdgeProps) {
  const { edit, onEdgeWaypoints, onEdgeBranch, onHistoryMark } = useContext(SchemeEditorContext);
  const { screenToFlowPosition, getNode } = useReactFlow();
  const sourceJunction = getNode(source)?.data.nodeType === 'junction';
  const targetJunction = getNode(target)?.data.nodeType === 'junction';
  const [branch, setBranch] = useState<{ at: Point; to: Point; incoming: boolean } | null>(null);
  const rightClick = useRef({ time: 0, x: 0, y: 0 });
  const dragCleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => dragCleanup.current?.(), []);
  const waypoints = (pathOptions as { waypoints?: Point[] } | undefined)?.waypoints ?? [];
  const { path, anchor, horizontal, points } = orthogonalPath(
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, waypoints, sourceJunction ? 0 : LEAD, targetJunction ? 0 : LEAD);
  const stroke = (style as { stroke?: string } | undefined)?.stroke ?? 'var(--accent)';

  const closestSegment = (p: Point) => {
    let best = { index: 0, at: points[0], distance: Infinity };
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i], b = points[i + 1];
      const dx = b.x - a.x, dy = b.y - a.y;
      const f = Math.max(0, Math.min(1, ((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy || 1)));
      const at = { x: a.x + f*dx, y: a.y + f*dy };
      const distance = Math.hypot(p.x-at.x, p.y-at.y);
      if (distance < best.distance) best = { index: i, at, distance };
    }
    return best;
  };

  // A click selects. Only an actual drag changes the route, once per undo step.
  const startDrag = (e: ReactPointerEvent) => {
    if (!edit || e.button !== 0 || branch) return;
    e.stopPropagation();
    const start = { x: e.clientX, y: e.clientY };
    const p = screenToFlowPosition(start);
    const { index } = closestSegment(p);
    const a = points[index], b = points[index + 1];
    const horizontalSegment = a.y === b.y;
    let moved = false;
    const move = (ev: PointerEvent) => {
      if (!moved && Math.hypot(ev.clientX-start.x, ev.clientY-start.y) < 4) return;
      if (!moved) { onHistoryMark(); moved = true; }
      const at = screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
      const delta = horizontalSegment ? snap(at.y-p.y) : snap(at.x-p.x);
      const shifted = (q: Point) => horizontalSegment ? { x: q.x, y: q.y+delta } : { x: q.x+delta, y: q.y };
      const next = points.map(q => ({ ...q }));
      next[index] = shifted(a); next[index+1] = shifted(b);
      // Retain the equipment stubs; end segments gain a perpendicular dogleg.
      const inner = next.slice(1, next.length-1);
      if (index === points.length-2) inner.push(shifted(b));
      onEdgeWaypoints(id, inner);
    };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up); dragCleanup.current = null; };
    dragCleanup.current?.(); dragCleanup.current = up;
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up);
  };

  useEffect(() => {
    if (!branch || !edit) return;
    const move = (e: PointerEvent) => setBranch(b => b && ({ ...b, to: screenToFlowPosition({ x: e.clientX, y: e.clientY }) }));
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setBranch(null); } };
    const click = (e: MouseEvent) => {
      if (e.button !== 0) return;
      const hit = e.target as Element;
      const node = hit.closest('.react-flow__node');
      if (!node) return;
      e.preventDefault(); e.stopPropagation();
      const kind = branch.incoming ? 'source' : 'target';
      const direct = hit.closest(`.react-flow__handle.${kind}`);
      const candidates = node.querySelectorAll(`.react-flow__handle.${kind}`);
      // Never guess a nozzle on a multi-port apparatus.
      const handle = direct ?? (candidates.length === 1 ? candidates[0] : null);
      const nodeId = node.getAttribute('data-id');
      if (!handle || !nodeId) return;
      onEdgeBranch(id, nodeId, handle.getAttribute('data-handleid') ?? (branch.incoming ? 'out' : 'in'), branch.at, branch.incoming);
      setBranch(null);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('keydown', key, true);
    window.addEventListener('click', click, true);
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('keydown', key, true); window.removeEventListener('click', click, true); };
  }, [branch, edit, id, onEdgeBranch, screenToFlowPosition]);

  useEffect(() => {
    const cancel = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== id) setBranch(null);
    };
    window.addEventListener('pipe-branch-start', cancel);
    return () => window.removeEventListener('pipe-branch-start', cancel);
  }, [id]);
  useEffect(() => { if (!edit) setBranch(null); }, [edit]);

  const begin = (x: number, y: number, incoming: boolean) => {
    window.dispatchEvent(new CustomEvent('pipe-branch-start', { detail: id }));
    const at = closestSegment(screenToFlowPosition({ x, y })).at;
    setBranch({ at, to: at, incoming });
  };
  return <g>
    <BaseEdge id={id} path={path} markerEnd={targetJunction ? undefined : markerEnd} style={style} interactionWidth={edit ? 20 : 2} />
    {edit && <path d={path} fill="none" stroke="transparent" strokeWidth={18}
      className="pipe-edit-path" data-route={JSON.stringify(points)} style={{ cursor: branch ? 'crosshair' : 'grab' }}
      onPointerDown={startDrag}
      onDoubleClick={e => { e.preventDefault(); e.stopPropagation(); begin(e.clientX, e.clientY, false); }}
      onContextMenu={e => {
        e.preventDefault(); e.stopPropagation();
        const now = performance.now(), prev = rightClick.current;
        if (now-prev.time < 450 && Math.hypot(e.clientX-prev.x,e.clientY-prev.y) < 8) {
          begin(e.clientX,e.clientY,true); rightClick.current.time=0;
        } else rightClick.current={time:now,x:e.clientX,y:e.clientY};
      }}><title>Перетаскивание — сдвинуть участок. Двойной ЛКМ — отвод, двойной ПКМ — входящая ветвь. Затем выберите штуцер; Esc — отмена.</title></path>}
    {edit && branch && <g pointerEvents="none">
      <path d={`M${branch.at.x} ${branch.at.y} L${branch.to.x} ${branch.at.y} L${branch.to.x} ${branch.to.y}`} fill="none" stroke={stroke} strokeWidth={2} strokeDasharray="7 5" />
      <circle cx={branch.at.x} cy={branch.at.y} r={4} fill={stroke} />
      <text x={branch.to.x+12} y={branch.to.y-12} fill={stroke} fontSize={13}>
        {branch.incoming ? 'Выберите выходной штуцер' : 'Выберите входной штуцер'} · Esc — отмена
      </text>
    </g>}
    <StreamTags id={id} data={(data ?? {}) as StreamEdgeData} anchor={anchor} horizontal={horizontal} />
  </g>;
}

export default memo(StreamEdge);
