import { useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Edge } from '@xyflow/react';
import type { EquipmentNode } from '../nodes/EquipmentNode';

export interface PipeAnchor { edgeId: string; fraction: number; x: number; y: number }

function pipePath(id: string): SVGPathElement | null {
  return document.querySelector(`.react-flow__edge[data-id="${CSS.escape(id)}"] .react-flow__edge-path`);
}

/** Project a screen point onto the actual rendered pipe, including bends. */
export function nearestPipe(clientX: number, clientY: number, edges: Edge[], tolerance = 22): PipeAnchor | null {
  let best: PipeAnchor | null = null;
  let bestDistance = tolerance * tolerance;
  for (const edge of edges) {
    const path = pipePath(edge.id);
    const matrix = path?.getScreenCTM();
    if (!path || !matrix) continue;
    const length = path.getTotalLength();
    if (!length) continue;
    const steps = Math.min(512, Math.max(32, Math.ceil(length * Math.hypot(matrix.a, matrix.b) / 12)));
    const distanceAt = (at: number) => {
      const point = path.getPointAtLength(at).matrixTransform(matrix);
      return (point.x - clientX) ** 2 + (point.y - clientY) ** 2;
    };
    let closest = 0;
    let distance = Infinity;
    for (let i = 0; i <= steps; i++) {
      const at = length * i / steps;
      const candidate = distanceAt(at);
      if (candidate < distance) { closest = at; distance = candidate; }
    }
    let lo = Math.max(0, closest - length / steps);
    let hi = Math.min(length, closest + length / steps);
    for (let i = 0; i < 14; i++) {
      const a = lo + (hi - lo) / 3;
      const b = hi - (hi - lo) / 3;
      if (distanceAt(a) < distanceAt(b)) hi = b; else lo = a;
    }
    const at = (lo + hi) / 2;
    distance = distanceAt(at);
    if (distance <= bestDistance) {
      const point = path.getPointAtLength(at);
      best = { edgeId: edge.id, fraction: at / length, x: point.x, y: point.y };
      bestDistance = distance;
    }
  }
  return best;
}

export function instrumentPosition(point: { x: number; y: number }, nodeScale = 1) {
  const scale = Math.max(0.3, Math.min(3, nodeScale));
  // Align the centre of the instrument symbol with the pipe, not its label.
  return { x: point.x - 52 * scale, y: point.y - 24 * scale };
}

/** Keep attached instruments on their pipe after equipment or pipe edits. */
export function usePipeInstruments(nodes: EquipmentNode[], edges: Edge[], setNodes: Dispatch<SetStateAction<EquipmentNode[]>>, viewKey = '') {
  useEffect(() => {
    if (!nodes.some((n) => n.data.nodeType === 'field_instrument' && n.data.schemeParams?.source_edge_id)) return;
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        const positions = new Map<string, { x: number; y: number }>();
        for (const node of nodes) {
          if (node.data.nodeType !== 'field_instrument' || node.dragging) continue;
          const params = node.data.schemeParams;
          if (params?.measurement_link === true) continue;
          const edgeId = String(params?.source_edge_id ?? '');
          if (!edgeId || !edges.some((edge) => edge.id === edgeId)) continue;
          const path = pipePath(edgeId);
          if (!path) continue;
          const fraction = Number(params?.pipe_fraction ?? 0.5);
          const point = path.getPointAtLength(path.getTotalLength() * Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0.5)));
          positions.set(node.id, instrumentPosition(point, node.data.scale));
        }
        setNodes((current) => {
          let changed = false;
          const next = current.map((node) => {
            const position = positions.get(node.id);
            if (!position || node.dragging || Math.hypot(position.x - node.position.x, position.y - node.position.y) < 0.05) return node;
            changed = true;
            return { ...node, position };
          });
          return changed ? next : current;
        });
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [nodes, edges, setNodes, viewKey]);
}
