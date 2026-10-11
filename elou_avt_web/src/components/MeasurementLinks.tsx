import { useEffect, useState } from 'react';
import { ViewportPortal } from '@xyflow/react';
import type { Edge } from '@xyflow/react';
import type { EquipmentNode } from '../nodes/EquipmentNode';

export default function MeasurementLinks({ nodes, edges }: { nodes: EquipmentNode[]; edges: Edge[] }) {
  const [lines, setLines] = useState<{id: string; x1: number; y1: number; x2: number; y2: number}[]>([]);
  useEffect(() => {
    let frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        setLines(nodes.flatMap(node => {
          const params = node.data.schemeParams;
          if (node.data.nodeType !== 'field_instrument' || params?.measurement_link !== true) return [];
          const edgeId = String(params.source_edge_id ?? '');
          let point: {x: number; y: number} | undefined;
          if (edgeId && edges.some(edge => edge.id === edgeId)) {
            const path = document.querySelector<SVGPathElement>(`.react-flow__edge[data-id="${CSS.escape(edgeId)}"] .react-flow__edge-path`);
            if (path) point = path.getPointAtLength(path.getTotalLength() * Math.max(0, Math.min(1, Number(params.pipe_fraction ?? .5))));
          } else {
            const target = nodes.find(n => n.id === params.source_node_id);
            if (target) point = {x: target.position.x + (target.measured?.width ?? 80) / 2, y: target.position.y + (target.measured?.height ?? 40) / 2};
          }
          const scale = Math.max(.3, Math.min(3, node.data.scale ?? 1));
          return point ? [{id: node.id, x1: node.position.x + 104 * scale, y1: node.position.y + 24 * scale, x2: point.x, y2: point.y}] : [];
        }));
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [nodes, edges]);
  return <ViewportPortal><svg className="measurement-links" style={{position: 'absolute', width: 1, height: 1, overflow: 'visible', pointerEvents: 'none'}}>
    {lines.map(line => <g key={line.id}><line {...{x1:line.x1,y1:line.y1,x2:line.x2,y2:line.y2}} stroke="#8b5cf6" strokeWidth="1.5" strokeDasharray="5 4" />
      <circle cx={line.x2} cy={line.y2} r="4" fill="#8b5cf6" /></g>)}
  </svg></ViewportPortal>;
}
