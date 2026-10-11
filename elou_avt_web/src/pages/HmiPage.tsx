import MeasurementLinks from '../components/MeasurementLinks';
import FieldInstrumentInspector from '../components/FieldInstrumentInspector';
import TechnicalReference from '../components/TechnicalReference';
import DocumentInstrumentPalette from '../components/DocumentInstrumentPalette';
import documentInstruments from '../arm/documentInstruments.json';
import { FIELD_INSTRUMENTS } from '../arm/instruments';
import { instrumentTelemetry, instrumentParameter } from '../arm/instruments';
import { instrumentPosition, nearestPipe, usePipeInstruments } from '../arm/pipeInstruments';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
} from '@xyflow/react';
import type {
  Connection,
  Edge,
  EdgeMouseHandler,
  NodeMouseHandler,
  OnNodeDrag,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { api, connectWs } from '../api';
import type { ApiState, FieldErrorsResponse, HistoryResponse, Scheme, SchemeNodeData, SchemeEdgeData, NodeTelemetry, ScadaLogEventType } from '../types';
import { useAuth } from '../auth';
import { PALETTE, createNode, nextId, nodeSizeFor, mnemoForNode, phaseMeta, normalizePhase, PHASE_TYPES, DEFAULT_PHASE } from '../schemeConfig';
import { mnemoLayout } from '../layout';
import EquipmentNodeComponent, { SchemeEditorContext } from '../nodes/EquipmentNode';
import { AREAS, assignAreas } from '../arm/areas';
import Faceplate from '../arm/Faceplate';
import type { EquipmentNode, EquipmentNodeData, TagCfg } from '../nodes/EquipmentNode';
import Inspector from '../components/Inspector';
import { fmtSimTime } from '../lms/ui';
import EdgeInspector from '../components/EdgeInspector';
import StreamEdge from '../components/StreamEdge';
import type { StreamEdgeData } from '../components/StreamEdge';
import TrendChart, { SERIES_META } from '../components/TrendChart';

const nodeTypes = { equipment: EquipmentNodeComponent };
const edgeTypes = { stream: StreamEdge };


const SCENARIOS: { id: string; label: string }[] = [];

const EDGE_STROKE = 2;

// Overview is a navigation map, not a compressed copy of every P&ID sheet.
// Detailed equipment, valves and field instruments remain on their area tabs.
const OVERVIEW_NODES = [
  { id: 'source_1', name: 'Сырая нефть', x: 0, y: 320 },
  { id: 'hea_10', name: 'Подогрев сырой нефти', x: 180, y: 300 },
  { id: 'elo_14', name: 'Блок ЭЛОУ', x: 410, y: 285 },
  { id: 'hea_33', name: 'Подогрев обессоленной нефти', x: 640, y: 300 },
  { id: 'col_32', name: 'К-1 · атмосферная колонна', x: 900, y: 115 },
  { id: 'hea_54', name: 'Печи П-1…П-3', x: 1160, y: 320 },
  { id: 'col_64', name: 'К-2 · атмосферная колонна', x: 1400, y: 110 },
  { id: 'col_51', name: 'К-4 · стабилизация бензина', x: 1385, y: 575 },
  { id: 'col_140', name: 'К-9 · вторичная перегонка', x: 1650, y: 110 },
  { id: 'col_141', name: 'К-10 · вторичная перегонка', x: 1900, y: 110 },
  { id: 'sep_101', name: 'А-1, А-2/1 · защелачивание', x: 1900, y: 565 },
] as const;

const OVERVIEW_EDGES = [
  ['source_1', 'out', 'hea_10', 'hot_in'],
  ['hea_10', 'hot_out', 'elo_14', 'in'],
  ['elo_14', 'oil_out', 'hea_33', 'hot_in'],
  ['hea_33', 'hot_out', 'col_32', 'in'],
  ['col_32', 'bottoms', 'hea_54', 'in'],
  ['hea_54', 'out', 'col_64', 'in'],
  ['col_32', 'distillate', 'col_51', 'in'],
  ['col_64', 'distillate', 'col_140', 'in'],
  ['col_140', 'distillate', 'col_141', 'in'],
  ['col_140', 'bottoms', 'sep_101', 'in'],
] as const;

// The overview remains in the project but is temporarily hidden while the
// detailed area P&IDs are being refined.
const SHOW_OVERVIEW_TAB = false;

function edgeMarker(color: string) {
  return { type: MarkerType.ArrowClosed, width: 13, height: 13, color };
}

interface EdgeCfg {
  phase?: string;
  /** Точки излома линии (координаты холста). Углы всегда 90°. */
  waypoints?: { x: number; y: number }[];
}

const EDGE_KEY = 'hmi-edge-v1';
const SCHEME_DRAFT_PREFIX = 'elou-avt-scheme-draft-v1:';

interface SchemeDraft {
  savedAt: string;
  nodes: SchemeNodeData[];
  edges: SchemeEdgeData[];
}

function schemeDraftKey(name: string) {
  return `${SCHEME_DRAFT_PREFIX}${name}`;
}

function loadSchemeDraft(name: string): SchemeDraft | null {
  try {
    const draft = JSON.parse(localStorage.getItem(schemeDraftKey(name)) ?? 'null') as SchemeDraft | null;
    return Array.isArray(draft?.nodes) && Array.isArray(draft?.edges) ? draft : null;
  } catch {
    return null;
  }
}

function saveSchemeDraft(name: string, draft: SchemeDraft) {
  try {
    localStorage.setItem(schemeDraftKey(name), JSON.stringify(draft));
  } catch {
    // The server save remains available if the browser storage quota is full.
  }
}

function clearSchemeDraft(name: string) {
  try {
    localStorage.removeItem(schemeDraftKey(name));
  } catch {
    // ignore storage errors
  }
}

/**
 * A browser draft is only a recovery copy of the canvas layout.  Its KIP
 * bindings can be older than the saved scheme, which would leave an otherwise
 * live instrument with no matching telemetry parameter.  Keep the operator's
 * positions and routes, but use the saved source/parameter for instruments
 * that still exist in the scheme.
 */
function applyDraftLayout(scheme: Scheme, draft: SchemeDraft): Scheme {
  const draftNodes = new Map(draft.nodes.map((node) => [node.id, node]));
  return {
    ...scheme,
    // The saved scheme owns topology. A local recovery draft may restore the
    // user's canvas coordinates, but must never resurrect a deleted valve or
    // replace newly saved process connections with stale edges.
    nodes: scheme.nodes.map((node) => {
      const draftNode = draftNodes.get(node.id);
      return draftNode && draftNode.type === node.type
        ? { ...node, x: draftNode.x, y: draftNode.y }
        : node;
    }),
    edges: scheme.edges,
  };
}

function loadEdgeCfg(): Record<string, EdgeCfg> {
  try {
    return JSON.parse(localStorage.getItem(EDGE_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveEdgeCfg(m: Record<string, EdgeCfg>) {
  try {
    localStorage.setItem(EDGE_KEY, JSON.stringify(m));
  } catch {
    // ignore storage errors
  }
}

const EDGE_DISP_KEY = 'hmi-edge-disp-v1';

function loadEdgeDisp(): Record<string, string[]> {
  try {
    return JSON.parse(localStorage.getItem(EDGE_DISP_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveEdgeDisp(m: Record<string, string[]>) {
  try {
    localStorage.setItem(EDGE_DISP_KEY, JSON.stringify(m));
  } catch {
    // ignore storage errors
  }
}

const EDGE_TAGS_KEY = 'hmi-edge-tags-v1';

function loadEdgeTags(): Record<string, Record<string, TagCfg>> {
  try {
    return JSON.parse(localStorage.getItem(EDGE_TAGS_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveEdgeTags(t: Record<string, Record<string, TagCfg>>) {
  try {
    localStorage.setItem(EDGE_TAGS_KEY, JSON.stringify(t));
  } catch {
    // ignore storage errors
  }
}

const DISP_KEY = 'hmi-disp-v1';

function loadDisp(): Record<string, string[]> {
  try {
    return JSON.parse(localStorage.getItem(DISP_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveDisp(d: Record<string, string[]>) {
  try {
    localStorage.setItem(DISP_KEY, JSON.stringify(d));
  } catch {
    // ignore storage errors
  }
}

const TAGS_KEY = 'hmi-tags-v1';

function loadTags(): Record<string, Record<string, TagCfg>> {
  try {
    return JSON.parse(localStorage.getItem(TAGS_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveTags(t: Record<string, Record<string, TagCfg>>) {
  try {
    localStorage.setItem(TAGS_KEY, JSON.stringify(t));
  } catch {
    // ignore storage errors
  }
}

const SCALE_KEY = 'hmi-node-scale-v1';

function loadScale(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(SCALE_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveScale(m: Record<string, number>) {
  try {
    localStorage.setItem(SCALE_KEY, JSON.stringify(m));
  } catch {
    // ignore storage errors
  }
}

function toRfNodes(scheme: Scheme, scaleMap: Record<string, number>): EquipmentNode[] {
  const layout = mnemoLayout(scheme.nodes, scheme.edges, (nd) => nodeSizeFor(nd));
  return scheme.nodes.map((n) => {
    const p = layout.get(n.id);
    return {
      id: n.id,
      type: 'equipment',
      position: { x: n.x, y: n.y },
      data: {
        nodeType: n.type,
        name: n.name,
        telemetry: null,
        schemeParams: n.params,
        size: p?.size ?? nodeSizeFor(n),
        mnemo: p?.mnemo ?? mnemoForNode(n.params),
        scale: scaleMap[n.id] ?? 1,
      },
    };
  });
}

function toRfEdges(
  scheme: Scheme,
  edgeCfg: Record<string, EdgeCfg>,
  edgeDispMap: Record<string, string[]>,
  edgeTagsMap: Record<string, Record<string, TagCfg>>,
): Edge[] {
  return scheme.edges.map((e) => {
    const cfg = edgeCfg[e.id];
    const phase = phaseMeta(normalizePhase(cfg?.phase ?? e.kind));
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_port,
      targetHandle: e.target_port,
      type: 'stream',
      animated: false,
      pathOptions: { waypoints: e.waypoints ?? cfg?.waypoints ?? [] },
      markerEnd: edgeMarker(phase.color),
      style: { stroke: phase.color, strokeWidth: EDGE_STROKE },
      data: { phase: phase.id, disp: edgeDispMap[e.id] ?? [], tags: edgeTagsMap[e.id] ?? {}, sourceTelemetry: null },
    };
  });
}

function HmiInner() {
  const { user, hasPermission, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const canEditScheme = Boolean(user?.roles.includes('administrator')) && hasPermission('manage_scheme');
  const canManageTwin = hasPermission('manage_twin');
  // Fault injection is an administrator function.  Check the effective
  // administrator permission so migrated "system administrator" accounts
  // are recognised even when their role code differs from the seed value.
  const canInjectFailure = hasPermission('manage_users');
  const [edit, setEdit] = useState(false);
  const [showReference, setShowReference] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState<EquipmentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [live, setLive] = useState<ApiState | null>(null);
  const [connected, setConnected] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [trendParam, setTrendParam] = useState('column_pressure_bar');
  const [schemes, setSchemes] = useState<string[]>([]);
  const [currentScheme, setCurrentScheme] = useState('default');
  const [scenario, setScenario] = useState('');
  const [msg, setMsg] = useState('');
  const [practiceContext, setPracticeContext] = useState<FieldErrorsResponse | null>(null);
  const [dispMap, setDispMap] = useState<Record<string, string[]>>(loadDisp);
  const [tagsMap, setTagsMap] = useState<Record<string, Record<string, TagCfg>>>(loadTags);
  const [edgeCfg, setEdgeCfg] = useState<Record<string, EdgeCfg>>(loadEdgeCfg);
  const [edgeDispMap, setEdgeDispMap] = useState<Record<string, string[]>>(loadEdgeDisp);
  const [edgeTagsMap, setEdgeTagsMap] = useState<Record<string, Record<string, TagCfg>>>(loadEdgeTags);
  const [scaleMap, setScaleMap] = useState<Record<string, number>>(loadScale);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [ctxMenu, setCtxMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const lastDraftRef = useRef<string | null>(null);

  const serialiseScheme = useCallback((): Pick<SchemeDraft, 'nodes' | 'edges'> => ({
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.data as unknown as EquipmentNodeData).nodeType,
      name: (n.data as unknown as EquipmentNodeData).name,
      x: Math.round(n.position.x),
      y: Math.round(n.position.y),
      params: (n.data as unknown as EquipmentNodeData).schemeParams ?? {},
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_port: e.sourceHandle ?? 'out',
      target_port: e.targetHandle ?? 'in',
      kind: (e.data as { phase?: string } | undefined)?.phase ?? 'crude',
      waypoints: (e as Edge & { pathOptions?: EdgeCfg }).pathOptions?.waypoints ?? edgeCfg[e.id]?.waypoints ?? [],
    })),
  }), [nodes, edges, edgeCfg]);

  const storeLocalDraft = useCallback(() => {
    if (!currentScheme || !nodes.length) return;
    const data = serialiseScheme();
    const signature = JSON.stringify(data);
    if (signature === lastDraftRef.current) return;
    saveSchemeDraft(currentScheme, { ...data, savedAt: new Date().toISOString() });
    lastDraftRef.current = signature;
  }, [currentScheme, nodes.length, serialiseScheme]);

  // Every edit is copied to local browser storage. It protects the work while
  // the server is busy reconfiguring a large scheme or if the page is closed.
  useEffect(() => {
    if (!edit) return;
    const timer = window.setTimeout(storeLocalDraft, 250);
    return () => window.clearTimeout(timer);
  }, [edit, nodes, edges, storeLocalDraft]);

  // --- Режим АРМ оператора (приказ № 251-П, п. 7.4.8, рисунок 24) --------
  const [arm, setArm] = useState(() => new URLSearchParams(location.search).get('arm') === '1');
  const [now, setNow] = useState(() => new Date());
  const [selectedAlarm, setSelectedAlarm] = useState<string | null>(null);
  const [showJournal, setShowJournal] = useState(false);
  const [armArea, setArmArea] = useState('atm');
  const [armSel, setArmSel] = useState<string | null>(null);

  useEffect(() => {
    if (new URLSearchParams(location.search).get('arm') === '1') {
      setArmArea('atm');
      setArm(true);
    }
  }, [location.search]);

  // Принадлежность оборудования участкам считается по схеме (ближайший
  // якорный аппарат), поэтому правка схемы разбиение не ломает.
  const areaOf = useMemo(
    () => {
      const assigned = assignAreas(nodes.map((n) => n.id), edges);
      for (const node of nodes) {
        const params = node.data.schemeParams;
        const pipe = edges.find((edge) => edge.id === params?.source_edge_id);
        const sourceArea = node.data.nodeType === 'field_instrument' ? assigned[pipe?.source ?? String(params?.source_node_id ?? '')] : undefined;
        const area = sourceArea ?? params?.arm_area;
        if (typeof area === 'string' && area !== 'all') assigned[node.id] = area;
      }
      return assigned;
    },
    [nodes, edges],
  );
  const overviewNodes = useMemo(() => {
    const byId = new Map(nodes.map((node) => [node.id, node]));
    return OVERVIEW_NODES.flatMap(({ id, name, x, y }) => {
      const node = byId.get(id);
      if (!node) return [];
      const scale = (node.data as EquipmentNodeData).nodeType === 'column' ? 0.62 : 0.82;
      return [{
        ...node,
        position: { x, y },
        data: { ...node.data, name, scale, overview: true },
      }];
    });
  }, [nodes]);
  const armNodes = useMemo(
    () => (armArea === 'all' ? overviewNodes : nodes.filter((n) => areaOf[n.id] === armArea)),
    [nodes, overviewNodes, areaOf, armArea],
  );
  const armEdges = useMemo(() => {
    if (armArea === 'all') {
      const visible = new Set(overviewNodes.map((node) => node.id));
      const phase = phaseMeta('oil');
      return OVERVIEW_EDGES.filter(([source, , target]) => visible.has(source) && visible.has(target)).map(
        ([source, sourceHandle, target, targetHandle]) => ({
          id: `overview-${source}-${target}`,
          source,
          target,
          sourceHandle,
          targetHandle,
          type: 'stream',
          animated: false,
          markerEnd: edgeMarker(phase.color),
          style: { stroke: phase.color, strokeWidth: EDGE_STROKE },
          data: { phase: phase.id, disp: [], tags: {}, sourceTelemetry: live?.equipment?.[source] ?? null },
        } as Edge),
      );
    }
    const ids = new Set(armNodes.map((n) => n.id));
    return edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  }, [edges, overviewNodes, armNodes, armArea, live]);
  const armSelNode = armSel ? nodes.find((n) => n.id === armSel) ?? null : null;
  const editingArmCanvas = canEditScheme && edit && armArea !== 'all';
  usePipeInstruments(nodes, edges, setNodes, `${arm}:${armArea}`);

  // В режиме АРМ тема всегда светлая: экран оператора смотрят при дневном
  // освещении операторной, тёмная тема там не нужна.
  useEffect(() => {
    if (!arm) return;
    const root = document.documentElement;
    const prev = root.getAttribute('data-theme');
    root.setAttribute('data-theme', 'light');
    return () => {
      if (prev) root.setAttribute('data-theme', prev);
      else root.removeAttribute('data-theme');
    };
  }, [arm]);

  useEffect(() => {
    if (!arm) return;
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, [arm]);

  // ARM is a separate route. On exit return to the cabinet, never to the
  // embedded HMI that sits behind the fullscreen operator screen.
  const leaveArm = useCallback(() => {
    const roles = user?.roles ?? [];
    const destination = roles.includes('administrator') ? '/admin/users'
      : roles.includes('instructor') ? '/instructor'
      : '/';
    // A full navigation is deliberate here: the fullscreen browser event can
    // otherwise leave the already-mounted HMI visible for one render cycle.
    // ARM is not a regular HMI view; closing it must return to the cabinet.
    window.location.replace(destination);
  }, [user?.roles]);

  useEffect(() => {
    const onFs = () => {
      if (!document.fullscreenElement) leaveArm();
    };
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, [leaveArm]);

  const toggleArm = useCallback(async () => {
    if (arm) {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
      leaveArm();
      return;
    }
    setSelectedId(null);
    setSelectedEdgeId(null);
    setArm(true);
    await document.documentElement.requestFullscreen().catch(() => {});
  }, [arm, leaveArm]);

  const alarmKey = (a: { id?: string; parameter?: string; description?: string }) =>
    a.id ?? `${a.parameter ?? ''}|${a.description ?? ''}`;

  // Backend descriptions begin with a stable operator form:
  // «Авария: К-1 — температура верха …».  Reuse the apparatus/tag in the
  // compact non-АРМ table instead of exposing `col_32_temperature_top`.
  const alarmSubject = (a: { description?: string; node_id?: string | null }) => {
    const match = a.description?.match(/^[^:]+:\s*(.+?)\s+—\s+/);
    return match?.[1] ?? a.node_id ?? '—';
  };

  /**
   * Активные события в порядке приоритета по приказу: аварийный
   * неквитированный → предупредительный неквитированный → аварийный
   * квитированный → предупредительный квитированный, внутри группы — по
   * времени возникновения.
   */
  const activeAlarmIds = new Set((live?.alarms ?? []).map(alarmKey));
  const eventMap = new Map([...(live?.alarm_history ?? []), ...(live?.alarms ?? [])].map(a => [alarmKey(a), a]));
  const alarmJournal = [...eventMap.values()].map(a => {
    const key = alarmKey(a);
    const critical = a.severity === 'CRITICAL';
    const ack = a.acknowledged_at ? { at: new Date(a.acknowledged_at).toLocaleString('ru-RU'), by: a.acknowledged_by ?? '—' } : undefined;
    const cleared = !activeAlarmIds.has(key);
    return { ...a, key, critical, ack, cleared, rank: (ack ? 4 : 0) + (cleared ? 2 : 0) + (critical ? 0 : 1) };
  }).sort((a,b)=>a.rank-b.rank || b.timestamp-a.timestamp);
  // Keep occurrences visible after both acknowledgment and clearing.
  const armAlarms = alarmJournal;

  const ackOne = useCallback((key: string) => {
    void api.acknowledgeAlarms([key]).then(setLive).catch(error => setMsg(String(error)));
  }, []);
  const ackAll = useCallback(() => {
    const ids = [...new Set([...(live?.alarm_history ?? []), ...(live?.alarms ?? [])]
      .filter(a => !a.acknowledged_at).map(a => a.id))];
    if (ids.length) void api.acknowledgeAlarms(ids).then(setLive).catch(error => setMsg(String(error)));
  }, [live]);

  // --- Отмена изменений в режиме редактирования -------------------------
  // Снимок берётся ПЕРЕД каждым изменением. Для непрерывных жестов
  // (перетаскивание узла, излома, квадратика) снимок делается один раз —
  // в начале жеста, иначе стек забился бы промежуточными кадрами.
  type Snapshot = {
    nodes: EquipmentNode[];
    edges: Edge[];
    dispMap: Record<string, string[]>;
    tagsMap: Record<string, Record<string, TagCfg>>;
    edgeCfg: Record<string, EdgeCfg>;
    edgeDispMap: Record<string, string[]>;
    edgeTagsMap: Record<string, Record<string, TagCfg>>;
    scaleMap: Record<string, number>;
  };
  const UNDO_LIMIT = 60;
  const undoStack = useRef<Snapshot[]>([]);
  const [undoDepth, setUndoDepth] = useState(0);
  type CanvasClipboard = {
    nodes: EquipmentNode[];
    edges: Edge[];
    origin: { x: number; y: number };
    disp: Record<string, string[]>;
    tags: Record<string, Record<string, TagCfg>>;
    scale: Record<string, number>;
    edgeCfg: Record<string, EdgeCfg>;
    edgeDisp: Record<string, string[]>;
    edgeTags: Record<string, Record<string, TagCfg>>;
  };
  // Буфер живёт в пределах открытого редактора, поэтому смена вкладки АРМ
  // не теряет скопированные объекты.
  const canvasClipboard = useRef<CanvasClipboard | null>(null);
  const { screenToFlowPosition, fitView } = useReactFlow();
  const msgTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify = useCallback((text: string) => {
    setMsg(text);
    if (msgTimer.current) clearTimeout(msgTimer.current);
    msgTimer.current = setTimeout(() => setMsg(''), 3000);
  }, []);
  // Зеркало состояния: снимок берётся из обработчиков событий, которым иначе
  // досталось бы замыкание с устаревшими значениями.
  const snapRef = useRef<Snapshot>({
    nodes, edges, dispMap, tagsMap, edgeCfg, edgeDispMap, edgeTagsMap, scaleMap,
  });
  snapRef.current = { nodes, edges, dispMap, tagsMap, edgeCfg, edgeDispMap, edgeTagsMap, scaleMap };

  const pushHistory = useCallback(() => {
    undoStack.current.push(structuredClone(snapRef.current));
    if (undoStack.current.length > UNDO_LIMIT) undoStack.current.shift();
    setUndoDepth(undoStack.current.length);
  }, []);

  const undo = useCallback(() => {
    const prev = undoStack.current.pop();
    setUndoDepth(undoStack.current.length);
    if (!prev) return;
    setNodes(prev.nodes);
    setEdges(prev.edges);
    setDispMap(prev.dispMap); saveDisp(prev.dispMap);
    setTagsMap(prev.tagsMap); saveTags(prev.tagsMap);
    setEdgeCfg(prev.edgeCfg); saveEdgeCfg(prev.edgeCfg);
    setEdgeDispMap(prev.edgeDispMap); saveEdgeDisp(prev.edgeDispMap);
    setEdgeTagsMap(prev.edgeTagsMap); saveEdgeTags(prev.edgeTagsMap);
    setScaleMap(prev.scaleMap); saveScale(prev.scaleMap);
    setMsg('Изменение отменено');
  }, [setNodes, setEdges]);

  const copySelection = useCallback(() => {
    if (!editingArmCanvas) return;
    const selected = nodes.filter((node) => node.selected && areaOf[node.id] === armArea);
    if (!selected.length) {
      notify('Выделите один или несколько объектов на схеме');
      return;
    }
    const ids = new Set(selected.map((node) => node.id));
    const copiedEdges = edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    const origin = {
      x: Math.min(...selected.map((node) => node.position.x)),
      y: Math.min(...selected.map((node) => node.position.y)),
    };
    canvasClipboard.current = structuredClone({
      nodes: selected,
      edges: copiedEdges,
      origin,
      disp: Object.fromEntries(selected.map((node) => [node.id, dispMap[node.id] ?? []])),
      tags: Object.fromEntries(selected.map((node) => [node.id, tagsMap[node.id] ?? {}])),
      scale: Object.fromEntries(selected.map((node) => [node.id, scaleMap[node.id] ?? 1])),
      edgeCfg: Object.fromEntries(copiedEdges.map((edge) => [edge.id, edgeCfg[edge.id] ?? {}])),
      edgeDisp: Object.fromEntries(copiedEdges.map((edge) => [edge.id, edgeDispMap[edge.id] ?? []])),
      edgeTags: Object.fromEntries(copiedEdges.map((edge) => [edge.id, edgeTagsMap[edge.id] ?? {}])),
    });
    notify(`Скопировано объектов: ${selected.length}${copiedEdges.length ? `; линий: ${copiedEdges.length}` : ''}`);
  }, [editingArmCanvas, nodes, edges, areaOf, armArea, dispMap, tagsMap, scaleMap, edgeCfg, edgeDispMap, edgeTagsMap, notify]);

  const pasteSelection = useCallback(() => {
    const clip = canvasClipboard.current;
    if (!editingArmCanvas) return;
    if (!clip) {
      notify('Буфер объектов пуст: сначала скопируйте выделение');
      return;
    }
    const rect = document.querySelector('.arm-canvas')?.getBoundingClientRect();
    const anchor = rect
      ? screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
      : { x: clip.origin.x + 40, y: clip.origin.y + 40 };
    const usedIds = new Set(nodes.map((node) => node.id));
    const idMap = new Map<string, string>();
    for (const node of clip.nodes) {
      const id = nextId(node.data.nodeType, usedIds);
      usedIds.add(id);
      idMap.set(node.id, id);
    }
    const existingTags = new Set(nodes
      .filter((node) => node.data.nodeType === 'field_instrument')
      .map((node) => String(node.data.schemeParams?.position_tag ?? node.data.name).toLocaleUpperCase()));
    const pasted = clip.nodes.map((node) => {
      const id = idMap.get(node.id)!;
      const params = structuredClone(node.data.schemeParams ?? {});
      let name = node.data.name;
      if (node.data.nodeType === 'field_instrument') {
        const originalTag = String(params.position_tag ?? name);
        let tag = originalTag;
        let copyNumber = 2;
        while (existingTags.has(tag.toLocaleUpperCase())) tag = `${originalTag} (${copyNumber++})`;
        existingTags.add(tag.toLocaleUpperCase());
        params.position_tag = tag;
        name = tag;
      }
      params.arm_area = armArea;
      return {
        ...structuredClone(node),
        id,
        selected: true,
        position: {
          x: anchor.x + node.position.x - clip.origin.x,
          y: anchor.y + node.position.y - clip.origin.y,
        },
        data: { ...structuredClone(node.data), name, schemeParams: params, telemetry: null, alarms: [] },
      } as EquipmentNode;
    });
    const timestamp = Date.now();
    const pastedEdges = clip.edges.map((edge, index) => {
      const source = idMap.get(edge.source)!;
      const target = idMap.get(edge.target)!;
      return {
        ...structuredClone(edge),
        id: `${source}-${target}-${timestamp + index}`,
        source,
        target,
        selected: true,
        data: { ...structuredClone(edge.data ?? {}), sourceTelemetry: null },
      } as Edge;
    });
    const deselect = (node: EquipmentNode) => ({ ...node, selected: false });
    pushHistory();
    setNodes((current) => [...current.map(deselect), ...pasted]);
    setEdges((current) => [...current.map((edge) => ({ ...edge, selected: false })), ...pastedEdges]);
    setDispMap((current) => {
      const next = { ...current };
      for (const [oldId, id] of idMap) next[id] = structuredClone(clip.disp[oldId] ?? []);
      saveDisp(next); return next;
    });
    setTagsMap((current) => {
      const next = { ...current };
      for (const [oldId, id] of idMap) next[id] = structuredClone(clip.tags[oldId] ?? {});
      saveTags(next); return next;
    });
    setScaleMap((current) => {
      const next = { ...current };
      for (const [oldId, id] of idMap) next[id] = clip.scale[oldId] ?? 1;
      saveScale(next); return next;
    });
    setEdgeCfg((current) => {
      const next = { ...current };
      clip.edges.forEach((edge, index) => { next[pastedEdges[index].id] = structuredClone(clip.edgeCfg[edge.id] ?? {}); });
      saveEdgeCfg(next); return next;
    });
    setEdgeDispMap((current) => {
      const next = { ...current };
      clip.edges.forEach((edge, index) => { next[pastedEdges[index].id] = structuredClone(clip.edgeDisp[edge.id] ?? []); });
      saveEdgeDisp(next); return next;
    });
    setEdgeTagsMap((current) => {
      const next = { ...current };
      clip.edges.forEach((edge, index) => { next[pastedEdges[index].id] = structuredClone(clip.edgeTags[edge.id] ?? {}); });
      saveEdgeTags(next); return next;
    });
    notify(`Вставлено объектов: ${pasted.length}${pastedEdges.length ? `; линий: ${pastedEdges.length}` : ''}. Сохраните схему.`);
  }, [editingArmCanvas, screenToFlowPosition, nodes, armArea, pushHistory, setNodes, setEdges, notify]);

  // Удаление узлов/линий средствами React Flow (клавиша Delete) тоже должно
  // отменяться: снимок берётся до того, как изменение применено.
  const handleNodesChange = useCallback(
    (chs: Parameters<typeof onNodesChange>[0]) => {
      if (chs.some((c) => c.type === 'remove')) pushHistory();
      onNodesChange(chs);
    },
    [onNodesChange, pushHistory],
  );
  const handleEdgesChange = useCallback(
    (chs: Parameters<typeof onEdgesChange>[0]) => {
      if (chs.some((c) => c.type === 'remove')) pushHistory();
      onEdgesChange(chs);
    },
    [onEdgesChange, pushHistory],
  );

  // Горячие клавиши редактора. В полях ввода не перехватываем.
  useEffect(() => {
    if (!edit || showReference) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const el = document.activeElement as HTMLElement | null;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
      const key = e.key.toLowerCase();
      if (key === 'c' && !e.shiftKey) {
        e.preventDefault();
        copySelection();
        return;
      }
      if (key === 'v' && !e.shiftKey) {
        e.preventDefault();
        pasteSelection();
        return;
      }
      if (key !== 'z' || e.shiftKey) return;
      e.preventDefault();
      undo();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [edit, undo, showReference, copySelection, pasteSelection]);
  useEffect(() => {
    if (!arm) return;
    const timer = window.setTimeout(() => { void fitView({ padding: 0.12 }); }, 100);
    return () => window.clearTimeout(timer);
  }, [arm, armArea, edit, fitView]);
  const inspectorRef = useRef<{ objectId: string; objectName: string; openedAt: number } | null>(null);
  const pageEnterRef = useRef<number>(Date.now());
  const scadaFlushedRef = useRef(false);

  const logScada = useCallback(
    (eventType: ScadaLogEventType, objectId: string, objectName: string, durationS?: number) => {
      api.logScadaEvent({ event_type: eventType, object_id: objectId, object_name: objectName, duration_s: durationS })
        .catch(() => undefined);
    },
    [],
  );

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const context = await api.lmsFieldErrors();
        if (alive) setPracticeContext(context);
      } catch {
        if (alive) setPracticeContext(null);
      }
    };
    void poll();
    const timer = window.setInterval(poll, 3000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const canRequestFieldCheck = Boolean(
    practiceContext?.active && practiceContext.multi_operator
    && practiceContext.status === 'RUNNING'
    && (user?.roles ?? []).includes('operator'),
  );

  const requestFieldCheck = useCallback(async (equipmentId: string, equipmentName: string) => {
    const sessionId = practiceContext?.session_id;
    if (!sessionId || !canRequestFieldCheck) throw new Error('Нет активной мультиоператорной практики');
    await api.chatSend({
      session_id: sessionId,
      kind: 'equipment_check',
      object_id: equipmentId,
      text: `Проверьте оборудование «${equipmentName}» (${equipmentId}) и сообщите о его состоянии.`,
    });
    logScada('inspector_open', equipmentId, `Запрос полевому: ${equipmentName}`);
  }, [practiceContext?.session_id, canRequestFieldCheck, logScada]);

  const closeInspector = useCallback(() => {
    const cur = inspectorRef.current;
    if (!cur) return;
    inspectorRef.current = null;
    const duration = (Date.now() - cur.openedAt) / 1000;
    logScada('inspector_close', cur.objectId, cur.objectName, duration);
  }, [logScada]);

  const openInspector = useCallback(
    (node: { id: string; name: string }) => {
      if (inspectorRef.current?.objectId === node.id) return;
      closeInspector();
      inspectorRef.current = { objectId: node.id, objectName: node.name, openedAt: Date.now() };
      logScada('inspector_open', node.id, node.name);
    },
    [closeInspector, logScada],
  );

  // SCADA-журнал: вход на страницу, выход, открытие/закрытие окна объекта
  useEffect(() => {
    logScada('page_enter', '', '');
    const flush = () => {
      if (scadaFlushedRef.current) return;
      scadaFlushedRef.current = true;
      closeInspector();
      logScada('page_exit', '', '', (Date.now() - pageEnterRef.current) / 1000);
    };
    window.addEventListener('beforeunload', flush);
    return () => {
      window.removeEventListener('beforeunload', flush);
      flush();
    };
  }, [logScada, closeInspector]);

  // Смена выбранного объекта управляет окном инспектора
  useEffect(() => {
    if (!selectedId) {
      closeInspector();
      return;
    }
    const n = nodes.find((x) => x.id === selectedId);
    if (n) openInspector({ id: n.id, name: n.data.name });
  }, [selectedId, nodes, closeInspector, openInspector]);

  const withCfg = useCallback(
    (nds: EquipmentNode[]): EquipmentNode[] =>
      nds.map((n) => ({
        ...n,
        data: {
          ...n.data,
          // Voltage is a mandatory live indication for every electro-
          // dehydrator. An operator can still reposition its two labels in
          // edit mode like any other tag.
          disp: dispMap[n.id] ?? (n.data.nodeType === 'elou'
            ? ['voltage_top_kv', 'voltage_bottom_kv'] : []),
          tags: tagsMap[n.id] ?? {},
        },
      })),
    [dispMap, tagsMap],
  );

  const onUpdateDisp = useCallback(
    (nodeId: string, keys: string[]) => {
      pushHistory();
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, disp: keys } } : n)));
      setDispMap((m) => {
        const nm = { ...m, [nodeId]: keys };
        saveDisp(nm);
        return nm;
      });
    },
    [setNodes],
  );

  const onTagChange = useCallback(
    (nodeId: string, key: string, patch: Partial<TagCfg>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  tags: { ...(n.data.tags ?? {}), [key]: { ...(n.data.tags?.[key] ?? {}), ...patch } },
                },
              }
            : n,
        ),
      );
      setTagsMap((m) => {
        const cur = m[nodeId] ?? {};
        const nm = { ...m, [nodeId]: { ...cur, [key]: { ...(cur[key] ?? {}), ...patch } } };
        saveTags(nm);
        return nm;
      });
    },
    [setNodes],
  );

  const onEdgePhase = useCallback(
    (edgeId: string, phaseId: string) => {
      pushHistory();
      const phase = phaseMeta(phaseId);
      setEdges((eds) =>
        eds.map((e) =>
          e.id === edgeId
            ? {
                ...e,
                data: { ...(e.data as object), phase: phaseId },
                markerEnd: edgeMarker(phase.color),
                style: { ...(e.style as object), stroke: phase.color, strokeWidth: EDGE_STROKE },
              }
            : e,
        ),
      );
      setEdgeCfg((m) => {
        const nm = { ...m, [edgeId]: { ...(m[edgeId] ?? {}), phase: phaseId } };
        saveEdgeCfg(nm);
        return nm;
      });
    },
    [setEdges, pushHistory],
  );

  const onEdgeWaypoints = useCallback(
    (edgeId: string, waypoints: { x: number; y: number }[]) => {
      setEdges((eds) => eds.map((e) => (e.id === edgeId ? { ...e, pathOptions: { waypoints } } : e)));
      setEdgeCfg((m) => {
        const nm = { ...m, [edgeId]: { ...(m[edgeId] ?? {}), waypoints } };
        saveEdgeCfg(nm);
        return nm;
      });
    },
    [setEdges],
  );

  const onEdgeDispChange = useCallback(
    (edgeId: string, keys: string[]) => {
      pushHistory();
      setEdges((eds) => eds.map((e) => (e.id === edgeId ? { ...e, data: { ...(e.data as object), disp: keys } } : e)));
      setEdgeDispMap((m) => {
        const nm = { ...m, [edgeId]: keys };
        saveEdgeDisp(nm);
        return nm;
      });
    },
    [setEdges],
  );

  const onEdgeTagChange = useCallback(
    (edgeId: string, key: string, patch: Partial<TagCfg>) => {
      setEdges((eds) =>
        eds.map((e) =>
          e.id === edgeId
            ? {
                ...e,
                data: {
                  ...(e.data as object),
                  tags: { ...((e.data as StreamEdgeData).tags ?? {}), [key]: { ...((e.data as StreamEdgeData).tags?.[key] ?? {}), ...patch } },
                },
              }
            : e,
        ),
      );
      setEdgeTagsMap((m) => {
        const cur = m[edgeId] ?? {};
        const nm = { ...m, [edgeId]: { ...cur, [key]: { ...(cur[key] ?? {}), ...patch } } };
        saveEdgeTags(nm);
        return nm;
      });
    },
    [setEdges],
  );

  const onDeleteEdge = useCallback(
    (edgeId: string) => {
      pushHistory();
      setEdges((eds) => eds.filter((e) => e.id !== edgeId));
      setSelectedEdgeId((cur) => (cur === edgeId ? null : cur));
      setEdgeCfg((m) => {
        const nm = { ...m };
        delete nm[edgeId];
        saveEdgeCfg(nm);
        return nm;
      });
      setEdgeDispMap((m) => {
        const nm = { ...m };
        delete nm[edgeId];
        saveEdgeDisp(nm);
        return nm;
      });
      setEdgeTagsMap((m) => {
        const nm = { ...m };
        delete nm[edgeId];
        saveEdgeTags(nm);
        return nm;
      });
    },
    [setEdges],
  );

  const onScaleNode = useCallback(
    (nodeId: string, scale: number) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, scale } } : n)),
      );
      setScaleMap((m) => {
        const nm = { ...m, [nodeId]: scale };
        saveScale(nm);
        return nm;
      });
    },
    [setNodes],
  );

  // Контекстное меню узла (правый клик в режиме редактирования).
  useEffect(() => {
    const onCtx = (e: Event) => {
      const detail = (e as CustomEvent<{ id: string; x: number; y: number }>).detail;
      if (detail && detail.id) setCtxMenu({ id: detail.id, x: detail.x, y: detail.y });
    };
    window.addEventListener('node-context-menu', onCtx);
    return () => window.removeEventListener('node-context-menu', onCtx);
  }, []);

  const lastSimulationTime = useRef<number | null>(null);
  const applyTelemetry = useCallback((s: ApiState) => {
    if (lastSimulationTime.current !== null && s.simulation_time < lastSimulationTime.current) {
      setSelectedAlarm(null);
    }
    lastSimulationTime.current = s.simulation_time;
    setLive(s);
    setConnected(true);
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: {
          ...n.data,
          telemetry: n.data.nodeType === 'field_instrument' ? instrumentTelemetry(n.data.schemeParams, s.equipment ?? {}, s.streams, n.id) : s.equipment?.[n.id] ?? null,
          alarms: (s.alarms ?? []).filter((a) => a.node_id === n.id || a.parameter.startsWith(`${n.id}_`)),
        },
      })),
    );
    setEdges((eds) =>
      eds.map((e) => {
        const t = s.streams?.[e.id] ?? s.equipment?.[e.source];
        return { ...e, animated: false, data: { ...(e.data as object), sourceTelemetry: t ?? null } };
      }),
    );
  }, [setNodes, setEdges]);

  // Initial load (с ретраями: при старте практики симуляция пересоздаётся,
  // и /scheme может кратко отвечать 500/None).
  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const load = async () => {
      try {
        const scheme = await api.getScheme();
        if (cancelled) return;
        const draft = loadSchemeDraft(scheme.id);
        const displayScheme = draft ? applyDraftLayout(scheme, draft) : scheme;
        setNodes(withCfg(toRfNodes(displayScheme, scaleMap)));
        setEdges(toRfEdges(displayScheme, edgeCfg, edgeDispMap, edgeTagsMap));
        if (draft) notify(`Восстановлен локальный черновик схемы от ${new Date(draft.savedAt).toLocaleString('ru-RU')}`);
        setTimeout(() => fitView({ padding: 0.15, duration: 350 }), 80);
      } catch {
        attempts += 1;
        if (cancelled) return;
        if (attempts >= 5) {
          notify('Не удалось загрузить схему с бэкенда');
        } else {
          setTimeout(load, 1000);
        }
      }
    };
    void load();
    api.getHistory().then(setHistory).catch(() => undefined);
    api.listSchemes().then((r) => {
      setSchemes(r.schemes);
      setCurrentScheme(r.current);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // WebSocket live telemetry
  useEffect(() => {
    const close = connectWs(applyTelemetry);
    return close;
  }, [applyTelemetry]);

  // History refresh
  useEffect(() => {
    const id = setInterval(() => {
      api.getHistory().then(setHistory).catch(() => undefined);
    }, 10000);
    return () => clearInterval(id);
  }, []);

  const refresh = useCallback(async () => {
    try {
      applyTelemetry(await api.getState());
    } catch {
      setConnected(false);
    }
  }, [applyTelemetry]);

  const onDragStart = (e: React.DragEvent, type: string, preset?: string) => {
    e.dataTransfer.setData('application/elou-type', type);
    if (preset) e.dataTransfer.setData('application/elou-preset', preset);
    e.dataTransfer.effectAllowed = 'move';
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData('application/elou-type');
      if (!canEditScheme || !edit || !PALETTE.some((item) => item.type === type)) return;
      const documentTag = e.dataTransfer.getData('application/elou-instrument-tag');
      const documentInstrument = documentInstruments.find((item) => item.tag === documentTag);
      if (documentInstrument && nodes.some((item) => item.data.nodeType === 'field_instrument'
        && String(item.data.schemeParams?.position_tag ?? item.data.name).toLocaleUpperCase() === documentTag.toLocaleUpperCase())) {
        notify(`Прибор «${documentTag}» уже размещён на схеме`);
        return;
      }
      pushHistory();
      const preset = e.dataTransfer.getData('application/elou-preset') || undefined;
      const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const node = createNode(type, pos.x, pos.y, preset, nodes.map((n) => n.id));
      if (documentInstrument) {
        node.name = documentTag;
        Object.assign(node.params, {
          position_tag: documentTag, instrument_code: documentTag.split(' ')[0],
          parameter: instrumentParameter(documentTag),
          source_document: '3. Описание технологического процесса.pdf',
          source_pages: documentInstrument.pages, source_context: documentInstrument.context,
        });
      }
      const pipe = type === 'field_instrument' ? nearestPipe(e.clientX, e.clientY, edges) : null;
      if (pipe) {
        Object.assign(node, instrumentPosition(pipe));
        Object.assign(node.params, { source_edge_id: pipe.edgeId, pipe_fraction: pipe.fraction, source_node_id: '' });
      }
      if (arm && armArea !== 'all') node.params.arm_area = armArea;
      setNodes((nds) => [
        ...nds,
        {
          id: node.id,
          type: 'equipment',
          position: { x: node.x, y: node.y },
          data: {
            nodeType: node.type,
            name: node.name,
            telemetry: null,
            schemeParams: node.params,
            size: nodeSizeFor(node),
            mnemo: mnemoForNode(node.params),
            disp: [],
            tags: {},
          },
        },
      ]);
      setSelectedId(node.id);
      notify(pipe ? `Прибор «${node.name}» установлен на трубопровод` : `Добавлен объект «${node.name}»`);
    },
    [screenToFlowPosition, setNodes, notify, nodes, edges, pushHistory, canEditScheme, edit, arm, armArea],
  );

  const measurementSource = useRef<string | null>(null);
  const onMeasurementEnd = useCallback((event: MouseEvent | TouchEvent) => {
    const sourceId = measurementSource.current;
    measurementSource.current = null;
    if (!sourceId || !canEditScheme || !edit) return;
    const point = 'changedTouches' in event ? event.changedTouches[0] : event;
    if (!point) return;
    const pipe = nearestPipe(point.clientX, point.clientY, edges, 28);
    if (!pipe) { notify('Завершите связь на трубопроводе или штуцере аппарата'); return; }
    pushHistory();
    setNodes(current => current.map(node => node.id !== sourceId ? node : {...node, data: {...node.data,
      schemeParams: {...node.data.schemeParams, measurement_link: true, source_edge_id: pipe.edgeId,
        pipe_fraction: pipe.fraction, source_node_id: ''},
    }}));
    notify('Точка измерения привязана. Связь видна только при редактировании; сохраните схему.');
  }, [canEditScheme, edit, edges, pushHistory, setNodes, notify]);

  const onInstrumentDragStop: OnNodeDrag<EquipmentNode> = useCallback((event, node) => {
    if (!canEditScheme || !edit || node.data.nodeType !== 'field_instrument') return;
    if (node.data.schemeParams?.measurement_link === true) return;
    const point = 'changedTouches' in event ? event.changedTouches[0] : event;
    if (!point) return;
    const pipe = nearestPipe(point.clientX, point.clientY, edges);
    setNodes((current) => current.map((item) => item.id !== node.id ? item : {
      ...item,
      ...(pipe ? { position: instrumentPosition(pipe, item.data.scale) } : {}),
      data: { ...item.data, schemeParams: {
        ...item.data.schemeParams, source_edge_id: pipe?.edgeId ?? '',
        pipe_fraction: pipe?.fraction ?? 0.5,
        ...(pipe ? { source_node_id: '' } : {}),
      } },
    }));
    notify(pipe ? 'Прибор привязан к трубопроводу' : 'Прибор размещён свободно');
  }, [canEditScheme, edit, edges, setNodes, notify]);

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source === c.target) { notify('Нельзя соединить узел с самим собой'); return; }
      const instrument = nodes.find(n => n.id === c.source && n.data.nodeType === 'field_instrument');
      if (instrument) {
        measurementSource.current = null;
        if (!c.target || nodes.find(n => n.id === c.target)?.data.nodeType === 'field_instrument') return;
        const inlet = edges.find(edge => edge.target === c.target && (edge.targetHandle ?? 'in') === (c.targetHandle ?? 'in'));
        if (!inlet) { notify('У штуцера нет потока. Подключите измерение к трубопроводу.'); return; }
        pushHistory();
        setNodes(current => current.map(node => node.id !== instrument.id ? node : {...node, data: {...node.data,
          schemeParams: {...node.data.schemeParams, measurement_link: true, source_node_id: '',
            source_edge_id: inlet.id, pipe_fraction: 1},
        }}));
        notify('Измерительная связь создана. Сохраните схему.');
        return;
      }
      if (nodes.some(n => n.id === c.target && n.data.nodeType === 'field_instrument')) return;
      pushHistory();
      const id = `${c.source}-${c.target}-${Date.now()}`;
      const phase = phaseMeta(DEFAULT_PHASE);
      setEdges((eds) => [
        ...eds,
        {
          id,
          source: c.source!,
          target: c.target!,
          sourceHandle: c.sourceHandle ?? 'out',
          targetHandle: c.targetHandle ?? 'in',
          type: 'stream',
          animated: false,
          pathOptions: { offsetX: 0, offsetY: 0 },
          data: { phase: phase.id, disp: [], tags: {}, sourceTelemetry: null },
          markerEnd: edgeMarker(phase.color),
          style: { stroke: phase.color, strokeWidth: EDGE_STROKE },
        },
      ]);
    },
    [setEdges, setNodes, nodes, edges, pushHistory, notify],
  );

  // Both gestures insert a real tee, preserving the original pipe route.
  const onEdgeBranch = useCallback(
    (edgeId: string, targetNodeId: string, targetHandle: string, teeAt: { x: number; y: number }, incoming = false) => {
      if (!canEditScheme || !edit) return;
      const line = edges.find(e => e.id === edgeId);
      // Один аппарат может иметь несколько штуцеров. Разрешаем врезать
      // ветвь в другой выход печи/колонны, запрещая лишь повторное
      // подключение к тому же самому концу выбранной линии.
      if (!line ||
        (line.source === targetNodeId && (line.sourceHandle ?? 'out') === targetHandle) ||
        (line.target === targetNodeId && (line.targetHandle ?? 'in') === targetHandle)) return;
      const target = nodes.find(n => n.id === targetNodeId);
      if (!target || target.data.nodeType === 'field_instrument') return;
      const path = document.querySelector<SVGPathElement>(`.react-flow__edge[data-id="${CSS.escape(edgeId)}"] .react-flow__edge-path`);
      const length = path?.getTotalLength() ?? 0;
      const fractionAt = (p: { x: number; y: number }) => {
        let best = 0, distance = Infinity;
        for (let i=0; path && i<=256; i++) {
          const q = path.getPointAtLength(length*i/256), d = Math.hypot(q.x-p.x,q.y-p.y);
          if (d<distance) { distance=d; best=i/256; }
        }
        return best;
      };
      const fraction = Math.max(.001,Math.min(.999,fractionAt(teeAt)));
      const route = document.querySelector(`.react-flow__edge[data-id="${CSS.escape(edgeId)}"] .pipe-edit-path`)?.getAttribute('data-route');
      const points: { x: number; y: number }[] = route ? JSON.parse(route).slice(1, -1)
        : (line as Edge & { pathOptions?: EdgeCfg }).pathOptions?.waypoints ?? [];
      const before = points.filter(p => fractionAt(p) < fraction);
      const after = points.filter(p => fractionAt(p) > fraction);
      pushHistory();
      const tee = createNode('junction',teeAt.x,teeAt.y,undefined,nodes.map(n=>n.id));
      tee.params = { ...tee.params, arm_area: areaOf[line.source] ?? armArea };
      const nextId = `${line.id}-after-${Date.now()}`;
      const branchId = `${line.id}-branch-${Date.now()}`;
      setNodes(nds => [...nds.map(n => {
        if (n.data.schemeParams?.source_edge_id !== edgeId) return n;
        const f = Number(n.data.schemeParams.pipe_fraction ?? .5);
        return { ...n, data: { ...n.data, schemeParams: { ...n.data.schemeParams,
          source_edge_id: f <= fraction ? edgeId : nextId,
          pipe_fraction: f <= fraction ? f/fraction : (f-fraction)/(1-fraction),
        } } };
      }), { id:tee.id,type:'equipment',position:{x:teeAt.x-5,y:teeAt.y-5},data:{
        nodeType:'junction',name:'Тройник',telemetry:null,schemeParams:tee.params,size:{w:10,h:10},disp:[],tags:{},
      } }]);
      setEdges(eds => [...eds.filter(e=>e.id!==edgeId),
        { ...line,target:tee.id,targetHandle:'in',pathOptions:{waypoints:before} },
        { ...line,id:nextId,source:tee.id,sourceHandle:'out',pathOptions:{waypoints:after} },
        { ...line,id:branchId,source:incoming?targetNodeId:tee.id,sourceHandle:incoming?targetHandle:'out',
          target:incoming?tee.id:targetNodeId,targetHandle:incoming?'in':targetHandle,
          pathOptions:{waypoints:[]},data:{...line.data,disp:[],tags:{}} },
      ]);
      setEdgeCfg(m => { const next={...m,[edgeId]:{waypoints:before},[nextId]:{waypoints:after}}; saveEdgeCfg(next); return next; });
      notify(incoming ? 'Входящая ветвь подключена через тройник' : 'Отвод создан через тройник');
    }, [canEditScheme,edit,edges,nodes,pushHistory,setNodes,setEdges,areaOf,armArea,notify],
  );

  const onNodeClick: NodeMouseHandler = useCallback((_, node) => {
    const name = (node.data as EquipmentNodeData).name ?? node.id;
    logScada('click', node.id, name);
    setSelectedId(node.id);
    setSelectedEdgeId(null);
  }, [logScada]);

  const onEdgeClick: EdgeMouseHandler = useCallback((_, edge) => {
    setSelectedEdgeId(edge.id);
    setSelectedId(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedId(null);
    setSelectedEdgeId(null);
  }, []);

  const onRename = useCallback(
    (nodeId: string, name: string) => {
      pushHistory();
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? {
          ...n,
          data: {
            ...n.data,
            name,
            size: nodeSizeFor({ type: n.data.nodeType, name, params: n.data.schemeParams }),
          },
        } : n)),
      );
    },
    [setNodes],
  );

  const onDelete = useCallback(
    (nodeId: string) => {
      pushHistory();
      const gone = edges.filter((e) => e.source === nodeId || e.target === nodeId).map((e) => e.id);
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      if (gone.length > 0) {
        setEdgeCfg((m) => {
          const nm = { ...m };
          gone.forEach((id) => { delete nm[id]; });
          saveEdgeCfg(nm);
          return nm;
        });
        setEdgeDispMap((m) => {
          const nm = { ...m };
          gone.forEach((id) => { delete nm[id]; });
          saveEdgeDisp(nm);
          return nm;
        });
        setEdgeTagsMap((m) => {
          const nm = { ...m };
          gone.forEach((id) => { delete nm[id]; });
          saveEdgeTags(nm);
          return nm;
        });
      }
      setSelectedId((cur) => (cur === nodeId ? null : cur));
    },
    [setNodes, setEdges, edges],
  );

  const saveScheme = useCallback(async () => {
    const { nodes: sn, edges: se } = serialiseScheme();
    storeLocalDraft();
    try {
      const state = await api.saveScheme(sn, se, currentScheme, currentScheme);
      applyTelemetry(state);
      clearSchemeDraft(currentScheme);
      lastDraftRef.current = null;
      notify(`Схема «${currentScheme}» сохранена (${sn.length} объектов, ${se.length} связей)`);
    } catch (err) {
      notify(`Сервер не сохранил схему, но локальный черновик сохранён: ${String(err)}`);
    }
  }, [serialiseScheme, storeLocalDraft, applyTelemetry, notify, currentScheme]);

  const loadDefault = useCallback(async () => {
    const scheme = await api.getScheme();
    setNodes(withCfg(toRfNodes(scheme, scaleMap)));
    setEdges(toRfEdges(scheme, edgeCfg, edgeDispMap, edgeTagsMap));
    setSelectedId(null);
    setTimeout(() => fitView({ padding: 0.15, duration: 350 }), 80);
    notify('Схема загружена с бэкенда');
  }, [withCfg, setNodes, setEdges, notify, fitView, edgeCfg, scaleMap, edgeDispMap, edgeTagsMap]);

  const runScenario = useCallback(async () => {
    const label = SCENARIOS.find((s) => s.id === scenario)?.label ?? scenario;
    try {
      const session = await api.startTrainingSession(scenario, user?.username ?? 'demo');
      const state = await api.startScenario(scenario);
      applyTelemetry(state);
      notify(`«${label}» запущен · сессия ${session.session_id}`);
    } catch (e) {
      notify(`Не удалось запустить сценарий: ${(e as Error).message}`);
    }
  }, [scenario, user, applyTelemetry, notify]);

  const finishScenario = useCallback(async () => {
    try {
      const s = await api.finishTrainingSession();
      notify(`Тренировка завершена · счёт ${s.performance_score ?? '—'}`);
    } catch (e) {
      notify(`Нет активной сессии: ${(e as Error).message}`);
    }
  }, []);

  const reLayout = useCallback(() => {
    const layout = mnemoLayout(
      nodes.map((n) => ({
        id: n.id,
        type: (n.data as unknown as EquipmentNodeData).nodeType,
        name: (n.data as unknown as EquipmentNodeData).name,
        x: n.position.x,
        y: n.position.y,
        params: (n.data as unknown as EquipmentNodeData).schemeParams ?? {},
      })),
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_port: e.sourceHandle ?? 'out',
        target_port: e.targetHandle ?? 'in',
        kind: 'process',
      })),
      (nd) => nodeSizeFor(nd),
    );
    setNodes((nds) =>
      nds.map((n) => {
        const p = layout.get(n.id);
        return p
          ? { ...n, position: p.pos, data: { ...n.data, size: p.size, mnemo: p.mnemo } }
          : n;
      }),
    );
    setTimeout(() => fitView({ padding: 0.15, duration: 350 }), 80);
    notify('Раскладка по мнемосхеме применена');
  }, [nodes, edges, setNodes, notify, fitView]);

  const onSelectScheme = useCallback(
    async (name: string) => {
      if (name === currentScheme) return;
      try {
        const state = await api.loadScheme(name);
        applyTelemetry(state);
        const scheme = await api.getScheme();
        setNodes(withCfg(toRfNodes(scheme, scaleMap)));
        setEdges(toRfEdges(scheme, edgeCfg, edgeDispMap, edgeTagsMap));
        setSelectedId(null);
        setCurrentScheme(name);
        notify(`Схема «${name}» загружена`);
      } catch {
        notify('Ошибка загрузки схемы');
      }
    },
    [currentScheme, applyTelemetry, withCfg, setNodes, setEdges, notify, scaleMap, edgeDispMap, edgeTagsMap],
  );

  const onCreateScheme = useCallback(async () => {
    const name = window.prompt('Имя новой схемы (латиница, цифры, _ или -):');
    if (!name) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      await api.createScheme(trimmed);
      const r = await api.listSchemes();
      setSchemes(r.schemes);
      setCurrentScheme(r.current);
      const scheme = await api.getScheme();
      setNodes(withCfg(toRfNodes(scheme, scaleMap)));
      setEdges(toRfEdges(scheme, edgeCfg, edgeDispMap, edgeTagsMap));
      setSelectedId(null);
      notify(`Схема «${trimmed}» создана`);
    } catch (err) {
      notify(`Ошибка создания схемы: ${String(err)}`);
    }
  }, [withCfg, setNodes, setEdges, notify, edgeCfg, scaleMap, edgeDispMap, edgeTagsMap]);

  const onAction = useCallback(
    async (equipmentId: string, actionType: string, value?: number | null) => {
      try {
        applyTelemetry(await api.action(equipmentId, actionType, value));
      } catch {
        notify('Ошибка действия');
      }
    },
    [applyTelemetry, notify],
  );

  const onFailure = useCallback(
    async (equipmentId: string) => {
      try {
        applyTelemetry(await api.injectFailure(equipmentId));
        notify(`Отказ внедрён: ${equipmentId}`);
      } catch {
        notify('Ошибка внедрения отказа');
      }
    },
    [applyTelemetry, notify],
  );

  const onUpdateParams = useCallback(
    async (equipmentId: string, params: Record<string, number>) => {
      try {
        applyTelemetry(await api.updateEquipmentParams(equipmentId, params));
        setNodes((nds) =>
          nds.map((n) =>
            n.id === equipmentId
              ? {
                  ...n,
                  data: {
                    ...n.data,
                    schemeParams: { ...(n.data as EquipmentNodeData).schemeParams, ...params },
                  },
                }
              : n,
          ),
        );
        notify('Физические свойства обновлены');
      } catch {
        notify('Ошибка обновления свойств');
      }
    },
    [applyTelemetry, notify, setNodes],
  );

  const onUpdateSchemeParam = useCallback(
    (nodeId: string, key: string, value: unknown) => {
      pushHistory();
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  schemeParams: {
                    ...n.data.schemeParams, [key]: value,
                    ...(key === 'source_edge_id' ? { source_node_id: '', pipe_fraction: 0.5 } : {}),
                    ...(key === 'source_node_id' ? { source_edge_id: '' } : {}),
                    ...(key === 'instrument_code' ? { parameter: FIELD_INSTRUMENTS.find((item) => item.code === value)?.parameter ?? 'pressure_bar' } : {}),
                  },
                },
              }
            : n,
        ),
      );
    },
    [setNodes],
  );

  const selectedTelemetry = selectedId ? live?.equipment?.[selectedId] ?? null : null;
  const selectedNode = selectedId ? (nodes.find((n) => n.id === selectedId) ?? null) : null;

  const editorPalette = (
    <aside className="palette">
      <div className="panel-title">ПАЛИТРА ОБЪЕКТОВ</div>
      <DocumentInstrumentPalette placedTags={nodes.filter(n=>n.data.nodeType==='field_instrument').map(n=>String(n.data.schemeParams?.position_tag??n.data.name))} />
      {(['instrument', 'boundary', 'equipment'] as const).map((category) => (
        <div key={category}>
          <div className="palette-group">{{ instrument: 'Полевой КИП', boundary: 'Границы', equipment: 'Оборудование' }[category]}</div>
          {PALETTE.filter((item) => item.category === category).map((item) => (
            <div key={`${item.type}-${item.preset ?? ''}`} className="palette-item" draggable
              onDragStart={(e) => onDragStart(e, item.type, item.preset)}>
              <span className="palette-dot" style={{ background: item.color }} />{item.label}
            </div>
          ))}
        </div>
      ))}
      <div className="hint">Перетащите объект на схему. Для полевого КИП выберите источник показания в инспекторе.</div>
    </aside>
  );
  const editorInspector = (
    <aside className="inspector">
      <div className="panel-title">ИНСПЕКТОР</div>
      {selectedEdgeId ? (
        <EdgeInspector edge={edges.find((e) => e.id === selectedEdgeId) ?? null}
          onPhase={onEdgePhase} onWaypoints={onEdgeWaypoints} onUpdateDisp={onEdgeDispChange} onDeleteEdge={onDeleteEdge}
          disp={(edges.find((e) => e.id === selectedEdgeId)?.data as StreamEdgeData | undefined)?.disp ?? []}
          canEditScheme={canEditScheme && edit} />
      ) : selectedNode?.data.nodeType === 'field_instrument' ? (
        <FieldInstrumentInspector node={selectedNode} nodes={nodes} edges={edges} equipment={live?.equipment ?? {}} streams={live?.streams}
          editable={canEditScheme && edit} onRename={onRename} onUpdate={onUpdateSchemeParam} onDelete={onDelete} />
      ) : (
        <Inspector nodeId={selectedId ?? ''} nodeName={selectedNode?.data.name ?? ''}
          nodeType={selectedNode?.data.nodeType ?? ''} schemeParams={selectedNode?.data.schemeParams ?? {}}
          telemetry={selectedTelemetry} history={history} disp={selectedNode?.data.disp ?? []}
          onUpdateDisp={onUpdateDisp} onAction={onAction} onFailure={onFailure} onRename={onRename} onDelete={onDelete}
          onUpdateParams={onUpdateParams} onUpdateSchemeParam={onUpdateSchemeParam}
          canEditScheme={canEditScheme && edit} canManageTwin={canManageTwin} canInjectFailure={canInjectFailure}
          onRequestFieldCheck={canRequestFieldCheck ? requestFieldCheck : undefined} />
      )}
      {!selectedEdgeId && selectedNode?.data.nodeType !== 'field_instrument' && <>
        <div className="panel-title trend-title">ТРЕНД ПАРАМЕТРА</div>
        <select className="scenario-select full" value={trendParam} onChange={(e) => setTrendParam(e.target.value)}>
          {Object.entries(SERIES_META).map(([key, meta]) => <option key={key} value={key}>{meta.label} ({meta.unit})</option>)}
        </select>
        <TrendChart history={history} param={trendParam} />
      </>}
    </aside>
  );
  const editorContextMenu = ctxMenu && (
    <>
      <div className="node-ctx-overlay" onClick={() => setCtxMenu(null)} />
      <div className="node-ctx-menu" style={{ left: ctxMenu.x, top: ctxMenu.y }}>
        <div className="node-ctx-menu-title">{nodes.find((n) => n.id === ctxMenu.id)?.data.name ?? ctxMenu.id}
          <button className="node-ctx-close" onClick={() => setCtxMenu(null)} aria-label="Закрыть">✕</button>
        </div>
        <button onClick={() => {
          const name = window.prompt('Название узла:', nodes.find((n) => n.id === ctxMenu.id)?.data.name ?? '');
          if (name?.trim()) onRename(ctxMenu.id, name.trim());
          setCtxMenu(null);
        }}>Переименовать</button>
        <button disabled={!scaleMap[ctxMenu.id] || scaleMap[ctxMenu.id] === 1}
          onClick={() => { onScaleNode(ctxMenu.id, 1); setCtxMenu(null); }}>Сбросить масштаб</button>
        <button className="node-ctx-danger" onClick={() => { onDelete(ctxMenu.id); setCtxMenu(null); }}>Удалить объект</button>
      </div>
    </>
  );

  // Экран АРМ оператора: зоны по рисунку 24 приказа № 251-П —
  // навигация с индикаторами систем, обзорная схема на нижнем слое,
  // свод опасных факторов в правом верхнем углу, активные события внизу.
  const calculationWarning = live?.calculation_error ? (
    <div role="alert" style={{ position: 'fixed', top: 100, left: '50%', transform: 'translateX(-50%)', zIndex: 2000,
      background: '#7f1d1d', color: '#fff', padding: '12px 20px', borderRadius: 6, maxWidth: '80vw' }}>
      Ошибка расчёта: показания не обновляются. На экране — последние рассчитанные значения.
    </div>
  ) : null;

  const armScreen = (
    <div className={`arm-screen${editingArmCanvas ? ' arm-editing' : ''}`}>
      {calculationWarning}
      {showReference && <TechnicalReference onClose={() => setShowReference(false)} />}
      <header className="arm-top">
        <div className="arm-nav">
          <div className="arm-nav-tabs">
          {SHOW_OVERVIEW_TAB && <button
            className={`arm-navbtn${armArea === 'all' ? ' on' : ''}`}
            onClick={() => { setArmArea('all'); setArmSel(null); }}
          >
            Обзорная
          </button>}
          {AREAS.map((a) => {
            const count = nodes.filter((n) => areaOf[n.id] === a.id).length;
            if (!count) return null;
            return (
              <button
                key={a.id}
                className={`arm-navbtn${armArea === a.id ? ' on' : ''}`}
                onClick={() => { setArmArea(a.id); setArmSel(null); }}
                title={`${a.label}: ${count} аппаратов и элементов`}
              >
                {a.label}
              </button>
            );
          })}
          </div>
        </div>
        <div className="arm-tools">
          <div className="arm-sys">
            {[
              { k: 'РСУ', state: connected ? 'ok' : 'bad', hint: connected ? 'связь есть' : 'нет связи' },
              { k: 'ПАЗ', state: armAlarms.some((a) => a.critical && !a.cleared) ? 'bad' : 'ok', hint: 'по критическим авариям' },
              { k: 'Пожар', state: 'nd', hint: 'пожарообнаружение: нет сигнала в модели' },
              { k: 'Загаз', state: 'nd', hint: 'загазованность: нет сигнала в модели' },
            ].map((s) => (
              <span key={s.k} className={`arm-ind ${s.state}`} title={s.hint}>{s.k}</span>
            ))}
          </div>
          {canEditScheme && <button className={`btn arm-editbtn ${edit ? 'btn-active' : 'btn-ghost'}`}
            onClick={() => { setEdit((value) => !value); setArmSel(null); setSelectedId(null); setSelectedEdgeId(null); setCtxMenu(null); }}>
            {edit ? 'Готово' : 'Редактировать'}
          </button>}
          <button className="arm-user" onClick={logout} title="Сменить пользователя">
            {user?.full_name || user?.username || '—'}
          </button>
          <button className="arm-exit" onClick={toggleArm} title="Выйти из режима АРМ (Esc)">✕</button>
          <label className="arm-speed" title="Скорость модельного времени">
            <select aria-label="Скорость моделирования" className="arm-spd" value={live?.speed ?? 1}
              onChange={e => { void api.setSimulationSpeed(Number(e.target.value)); }}>
              {[1,2,5,10,30].map(speed => <option key={speed} value={speed}>{speed}×</option>)}
            </select>
          </label>
          <button className="btn btn-ghost arm-kts" onClick={() => setShowReference(true)} title="Открыть исходную технологическую схему">Чертёж КТС</button>
          <div className="arm-clock">
            <b>{now.toLocaleTimeString('ru-RU')}</b>
            <span>{now.toLocaleDateString('ru-RU')}</span>
          </div>
        </div>
      </header>

      {editingArmCanvas && <div className="arm-editor-toolbar">
        <strong>Редактирование схемы</strong>
        <button className="btn" onClick={undo} disabled={undoDepth === 0}>↶ Отменить ({undoDepth})</button>
        <button className="btn" onClick={copySelection} title="Ctrl+C">Копировать</button>
        <button className="btn" onClick={pasteSelection} title="Ctrl+V">Вставить</button>
        <button className="btn btn-start" onClick={saveScheme}>Сохранить схему</button>
        <span className="hint">Выделите объекты, Ctrl+C, перейдите на нужную вкладку и нажмите Ctrl+V. Тяните участок трубы. Двойной ЛКМ — отвод, двойной ПКМ — входящая ветвь.</span>
      </div>}
      <main className="arm-main">
        {editingArmCanvas && editorPalette}
        <div className={`arm-canvas${editingArmCanvas ? ' editing' : ''}`}
          onDrop={editingArmCanvas ? onDrop : undefined} onDragOver={(e) => { if (editingArmCanvas) e.preventDefault(); }}>
        <SchemeEditorContext.Provider value={{ edit: editingArmCanvas, onTagChange, onRenameNode: onRename, onEdgeWaypoints, onScaleNode, onEdgeTagChange, onEdgeBranch, onHistoryMark: pushHistory }}>
        <ReactFlow
          key={armArea}
          nodes={armNodes}
          edges={armEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onNodeDragStart={editingArmCanvas ? () => pushHistory() : undefined}
          onNodeDragStop={editingArmCanvas ? onInstrumentDragStop : undefined}
          onConnect={editingArmCanvas ? onConnect : undefined}
          onConnectStart={(_, connection) => { measurementSource.current = connection.handleId === 'measurement' ? connection.nodeId : null; }}
          onConnectEnd={onMeasurementEnd}
          onNodeClick={(event, node) => {
            if (editingArmCanvas || node.data.nodeType === 'field_instrument') { onNodeClick(event, node); setArmSel(null); }
            else { setArmSel(node.id); setSelectedId(null); }
          }}
          onEdgeClick={editingArmCanvas ? onEdgeClick : undefined}
          onPaneClick={() => { onPaneClick(); setArmSel(null); }}
          nodesDraggable={editingArmCanvas}
          nodesConnectable={editingArmCanvas}
          elementsSelectable={editingArmCanvas}
          deleteKeyCode={editingArmCanvas ? ['Backspace', 'Delete'] : null}
          edgesReconnectable={false}
          edgesFocusable={false}
          panOnDrag
          minZoom={0.1}
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          {editingArmCanvas && <MeasurementLinks nodes={armNodes} edges={armEdges} />}
          <Background variant={BackgroundVariant.Dots} gap={22} color="var(--mn-line)" />
          <Controls showInteractive={false} />
        </ReactFlow>
        </SchemeEditorContext.Provider>
        </div>
        {(canEditScheme && edit || selectedNode?.data.nodeType === 'field_instrument') && editorInspector}

        {!edit && armSelNode && (
          <Faceplate
            nodeId={armSelNode.id}
            nodeName={(armSelNode.data as EquipmentNodeData).name ?? armSelNode.id}
            nodeType={(armSelNode.data as EquipmentNodeData).nodeType ?? ''}
            telemetry={live?.equipment?.[armSelNode.id] ?? null}
            canControl={hasPermission('send_commands')}
            canInjectFailure={canInjectFailure}
            onUpdateParams={canManageTwin ? onUpdateParams : undefined}
            onAction={onAction}
            onFailure={onFailure}
            onClose={() => setArmSel(null)}
          />
        )}

      </main>

      {msg && <div className="toast" role="status">{msg}</div>}
      {canEditScheme && edit && editorContextMenu}
      <footer className="arm-events" aria-label="Активные аварии">
        <div className="arm-evt-table">
          <div className="arm-evt-head">
            <span>Возникновение</span><span>Сообщение</span><span>Время квитирования</span><span>Квитировал</span>
          </div>
          {armAlarms.length === 0 && <div className="arm-evt-empty">Активных событий нет</div>}
          {armAlarms.map((a) => (
            <div
              key={a.key}
              className={`arm-evt ${a.critical ? 'crit' : 'warn'}${a.ack ? ' ack' : ' live'}`
                + (selectedAlarm === a.key ? ' sel' : '')}
              onClick={() => setSelectedAlarm(a.key)}
              onDoubleClick={() => ackOne(a.key)}
            >
              <span title={`Модельное время: ${a.timestamp.toFixed(1)} с`}>{a.occurred_at ? new Date(a.occurred_at).toLocaleString('ru-RU') : `${a.timestamp.toFixed(1)} с`}</span>
              <span className="arm-evt-msg" title={a.description}>{a.cleared ? 'Снята · ' : ''}{a.description}</span>
              <span>{a.ack?.at ?? '—'}</span>
              <span>{a.ack?.by ?? '—'}</span>
            </div>
          ))}
        </div>
        <div className="arm-evt-btns">
          <button className="btn" disabled={!selectedAlarm} onClick={() => selectedAlarm && ackOne(selectedAlarm)}>
            Квитировать
          </button>
          <button className="btn" disabled={armAlarms.every((a) => a.ack)} onClick={ackAll}>
            Квитировать все
          </button>
          <button className="btn" onClick={() => setShowJournal((v) => !v)}>
            Журнал событий
          </button>
        </div>
      </footer>

      {showJournal && (
        <div className="arm-journal" onClick={() => setShowJournal(false)}>
          <div className="arm-journal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-title">ЖУРНАЛ СОБЫТИЙ</div>
            {alarmJournal.length === 0 && <div className="arm-evt-empty">Событий нет</div>}
            {alarmJournal.map((a) => (
              <div key={a.key} className={`arm-evt ${a.critical ? 'crit' : 'warn'}${a.ack ? ' ack' : ''}`}>
                <span title={`Модельное время: ${a.timestamp.toFixed(1)} с`}>{a.occurred_at ? new Date(a.occurred_at).toLocaleString('ru-RU') : `${a.timestamp.toFixed(1)} с`}</span>
                <span className="arm-evt-msg" title={a.description}>{a.cleared ? 'Снята · ' : ''}{a.description}</span>
                <span>{a.ack?.at ?? '—'}</span>
                <span>{a.ack?.by ?? '—'}</span>
              </div>
            ))}
            <button className="btn" onClick={() => setShowJournal(false)}>Закрыть</button>
          </div>
        </div>
      )}
    </div>
  );

  if (arm) return armScreen;

  return (
    <div className="hmi-page">
      {calculationWarning}
      {showReference && <TechnicalReference onClose={() => setShowReference(false)} />}
      <div className="hmi-toolbar">
        {SCENARIOS.length > 0 && (
          <select
            className="scenario-select"
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            title="Сценарий"
          >
            {SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
        )}
        <button className="btn btn-start" onClick={runScenario}>▶ Запустить</button>
        <button className="btn btn-stop" onClick={finishScenario}>⏹ Завершить</button>
        <button className="btn btn-ghost" onClick={() => api.resetScenario().then(applyTelemetry)}>⏮ Сброс</button>
        <button className="btn btn-ghost" onClick={() => api.step().then(applyTelemetry)}>⏭ Шаг</button>

        {canEditScheme && (
          <>
            <span className="hmi-sep" />
            <button
              className={`btn ${edit ? 'btn-active' : 'btn-ghost'}`}
              onClick={() => {
                setEdit((v) => !v);
                setSelectedId(null);
                setSelectedEdgeId(null);
              }}
              title={edit ? 'Выйти из режима редактирования' : 'Редактировать схему'}
            >
              {edit ? '✓ Готово' : '🖉 Редактировать схему'}
            </button>
          </>
        )}

        {canEditScheme && edit && (
          <>
            <button
              className="btn btn-ghost"
              onClick={undo}
              disabled={undoDepth === 0}
              title="Отменить последнее изменение (Ctrl+Z)"
            >
              ↶ Отменить{undoDepth ? ` (${undoDepth})` : ''}
            </button>
            <button className="btn btn-ghost" onClick={saveScheme}>💾 Сохранить</button>
            <button className="btn btn-ghost" onClick={onCreateScheme}>＋ Новая схема</button>
            <button className="btn btn-ghost" onClick={loadDefault}>⟳ Загрузить</button>
            <button className="btn btn-ghost" onClick={reLayout}>🗜 Раскладка</button>
            <select
              className="scenario-select"
              value={currentScheme}
              onChange={(e) => onSelectScheme(e.target.value)}
              title="Схема"
            >
              {schemes.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </>
        )}

        <button className="btn btn-ghost" onClick={() => void toggleArm()} title="Полноэкранный режим АРМ оператора">
          ⛶ Режим АРМ
        </button>
        <button className="btn btn-ghost" onClick={() => setShowReference(true)}>Чертёж КТС</button>

        <div className="hmi-chips">
          <span className={`chip ${connected ? 'chip-ok' : 'chip-bad'}`}>
            <span className="dot" /> {connected ? 'LIVE · СВЯЗЬ ЕСТЬ' : 'ОТКЛЮЧЕНО'}
          </span>
          <span className="chip chip-info">t = {(live?.simulation_time ?? 0).toFixed(0)} с</span>
          <label className="chip chip-info speed-chip">
            ⏩ <select
              className="speed-select"
              value={live?.speed ?? 1}
              onChange={(e) => { void api.setSimulationSpeed(Number(e.target.value)); }}
              title="Скорость симуляции"
            >
              <option value={1}>1×</option>
              <option value={2}>2×</option>
              <option value={5}>5×</option>
              <option value={10}>10×</option>
              <option value={30}>30×</option>
            </select>
          </label>
          <span className={`chip ${(live?.alarms?.length ?? 0) > 0 ? 'chip-alarm' : 'chip-ok'}`}>
            ⚠ {(live?.alarms?.length ?? 0)} аварий
          </span>
        </div>
      </div>

      <div className="body">
        {canEditScheme && edit && editorPalette}

        <div className={`canvas${canEditScheme && edit ? ' editing' : ''}`} onDrop={canEditScheme && edit ? onDrop : undefined} onDragOver={(e) => canEditScheme && edit && e.preventDefault()}>
          <SchemeEditorContext.Provider value={{ edit, onTagChange, onRenameNode: onRename, onEdgeWaypoints, onScaleNode, onEdgeTagChange, onEdgeBranch, onHistoryMark: pushHistory }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onNodeDragStart={canEditScheme && edit ? () => pushHistory() : undefined}
            onNodeDragStop={canEditScheme && edit ? onInstrumentDragStop : undefined}
            onConnect={canEditScheme && edit ? onConnect : undefined}
          onConnectStart={(_, connection) => { measurementSource.current = connection.handleId === 'measurement' ? connection.nodeId : null; }}
          onConnectEnd={onMeasurementEnd}
              onNodeClick={onNodeClick}
            onEdgeClick={canEditScheme && edit ? onEdgeClick : undefined}
            onPaneClick={onPaneClick}
            onEdgesDelete={canEditScheme && edit ? (eds) => eds.forEach((e) => onDeleteEdge(e.id)) : undefined}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            nodesDraggable={canEditScheme && edit}
            nodesConnectable={canEditScheme && edit}
            elementsSelectable={canEditScheme && edit}
            edgesFocusable={false}
            edgesReconnectable={false}
            deleteKeyCode={canEditScheme && edit ? ['Backspace', 'Delete'] : null}
            minZoom={0.15}
            maxZoom={3}
            proOptions={{ hideAttribution: true }}
          >
            {canEditScheme && edit && <MeasurementLinks nodes={nodes} edges={edges} />}
            <Background variant={BackgroundVariant.Dots} gap={22} color="var(--mn-line)" />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(n) => {
                const t = (n.data as EquipmentNodeData).telemetry;
                return t?.failed ? '#f87171' : t?.running ? '#35d399' : '#334155';
              }}
              style={{ background: 'var(--panel)' }}
            />
            {!edit && (
              <Panel position="top-center">
                <div className="hmi-banner">ЭЛОУ-АВТ · МНЕМОСХЕМА УСТАНОВКИ</div>
              </Panel>
            )}
            <Panel position="bottom-center">
              <div className="flow-legend">
                {PHASE_TYPES.map((p) => (
                  <span key={p.id}><span className="legend-line" style={{ background: p.color }} />{p.label}</span>
                ))}
              </div>
            </Panel>
          </ReactFlow>
          </SchemeEditorContext.Provider>
        </div>

        {editorInspector}
      </div>

      <div className="mnemo-bottom scada-alarms">
        <div className="mnemo-alarms">
          <div className="panel-title">АВАРИИ · {live?.alarms?.length ?? 0}</div>
          {(live?.alarms?.length ?? 0) === 0 ? (
            <div className="mnemo-alarms-empty">Активных аварий нет</div>
          ) : (
            <div className="alarm-table-wrap">
              <table className="alarm-table">
                <thead>
                  <tr>
                    <th>Время</th>
                    <th>Объект</th>
                    <th>Значение</th>
                    <th>Уставка</th>
                    <th>Описание</th>
                  </tr>
                </thead>
                <tbody>
                  {(live?.alarms ?? []).map((a) => (
                    <tr key={a.id} className={`alarm-row sev-${String(a.severity).toLowerCase()}`}>
                      <td>{fmtSimTime(a.timestamp)}</td>
                      <td>{alarmSubject(a)}</td>
                      <td>{a.actual_value.toFixed(2)}</td>
                      <td>{a.threshold.toFixed(2)}</td>
                      <td className="alarm-desc">{a.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {msg && <div className="toast">{msg}</div>}

      {editorContextMenu}
    </div>
  );
}

export default function HmiPage() {
  return (
    <ReactFlowProvider>
      <HmiInner />
    </ReactFlowProvider>
  );
}
