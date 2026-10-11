import InstrumentLimits from './InstrumentLimits';
import { useEffect, useState } from 'react';
import type { Edge } from '@xyflow/react';
import type { EquipmentNode } from '../nodes/EquipmentNode';
import type { NodeTelemetry } from '../types';
import { FIELD_INSTRUMENTS, instrumentTelemetry } from '../arm/instruments';
import { PARAM_LABELS, fmtParam } from '../schemeConfig';

interface Props {
  node: EquipmentNode;
  nodes: EquipmentNode[];
  equipment: Record<string, NodeTelemetry>;
  streams?: Record<string, NodeTelemetry>;
  edges: Edge[];
  editable: boolean;
  onRename: (id: string, name: string) => void;
  onUpdate: (id: string, key: string, value: unknown) => void;
  onDelete: (id: string) => void;
}

export default function FieldInstrumentInspector({ node, nodes, edges, equipment, streams, editable, onRename, onUpdate, onDelete }: Props) {
  const params = node.data.schemeParams ?? {};
  const [name, setName] = useState(node.data.name);
  useEffect(() => setName(node.data.name), [node.id, node.data.name]);
  const positionTag = String(params.position_tag ?? node.data.name);
  const [tag, setTag] = useState(positionTag);
  const [tagError, setTagError] = useState('');
  useEffect(() => { setTag(positionTag); setTagError(''); }, [node.id, positionTag]);
  const commitTag = () => {
    const next = tag.trim();
    if (!next) { setTagError('Введите позиционное обозначение.'); return; }
    if (nodes.some((other) => other.id !== node.id && other.data.nodeType === 'field_instrument'
      && String(other.data.schemeParams?.position_tag ?? other.data.name).trim().toLocaleUpperCase() === next.toLocaleUpperCase())) {
      setTagError('Прибор с таким обозначением уже есть на схеме.'); return;
    }
    setTagError('');
    if (next !== positionTag) onUpdate(node.id, 'position_tag', next);
  };
  const sourceId = String(params.source_node_id ?? '');
  const pipeId = String(params.source_edge_id ?? '');
  const parameter = String(params.parameter ?? 'pressure_bar');
  const source = instrumentTelemetry(params, equipment, streams, node.id);
  const value = source?.params[parameter];
  const choices = new Set([parameter, ...Object.keys(source?.params ?? {}).filter((key) => typeof source?.params[key] === 'number')]);
  return (
    <div className="field-instrument-inspector">
      <div className="panel-title">ПОЛЕВОЙ КИП</div>
      <label>Позиционное обозначение
        <input value={tag} disabled={!editable} maxLength={80} placeholder="Например, PI-101"
          aria-invalid={Boolean(tagError)} onChange={(e) => { setTag(e.target.value); setTagError(''); }}
          onBlur={commitTag} onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
      </label>
      {tagError && <div role="alert" style={{ color: 'var(--danger)' }}>{tagError}</div>}
      <label>Наименование
        <input value={name} disabled={!editable} onChange={(e) => setName(e.target.value)}
          onBlur={() => { const next = name.trim(); if (next && next !== node.data.name) onRename(node.id, next); else setName(node.data.name); }}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
      </label>
      <label>Тип прибора
        <select aria-label="Тип прибора" value={String(params.instrument_code ?? 'PI')} disabled={!editable}
          onChange={(e) => onUpdate(node.id, 'instrument_code', e.target.value)}>
          {!FIELD_INSTRUMENTS.some((item) => item.code === params.instrument_code) && params.instrument_code != null && (
            <option value={String(params.instrument_code)}>{String(params.instrument_code)} · По регламенту</option>
          )}
          {FIELD_INSTRUMENTS.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.label}</option>)}
        </select>
      </label>
      {editable && <p className="hint">Потяните фиолетовую точку справа от КИП на трубу или штуцер аппарата. Связь скрывается после выхода из редактирования.</p>}
      {params.measurement_link === true && <div className="hint">Удалённая точка измерения
        {editable && <button className="btn" onClick={() => { onUpdate(node.id, 'source_edge_id', ''); onUpdate(node.id, 'source_node_id', ''); onUpdate(node.id, 'measurement_link', false); }}>Отвязать точку</button>}
      </div>}
      <label>Трубопровод
        <select aria-label="Трубопровод" value={pipeId} disabled={!editable} onChange={(e) => onUpdate(node.id, 'source_edge_id', e.target.value)}>
          <option value="">Без привязки к трубе</option>
          {pipeId && !edges.some((edge) => edge.id === pipeId) && <option value={pipeId}>Трубопровод удалён</option>}
          {edges.map((edge) => <option key={edge.id} value={edge.id}>
            {nodes.find((n) => n.id === edge.source)?.data.name ?? edge.source} → {nodes.find((n) => n.id === edge.target)?.data.name ?? edge.target} ({edge.sourceHandle ?? 'out'} → {edge.targetHandle ?? 'in'}) · {edge.id}
          </option>)}
        </select>
      </label>
      {pipeId ? <>
        {editable && <label>Положение на трубе: {Math.round(Number(params.pipe_fraction ?? 0.5) * 100)} %
          <input type="range" min="0" max="100" defaultValue={Math.round(Number(params.pipe_fraction ?? 0.5) * 100)}
            key={`${node.id}:${pipeId}:${params.pipe_fraction}`}
            onPointerUp={(e) => onUpdate(node.id, 'pipe_fraction', Number(e.currentTarget.value) / 100)}
            onKeyUp={(e) => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) onUpdate(node.id, 'pipe_fraction', Number(e.currentTarget.value) / 100); }} />
        </label>}
        <p className="hint">Показание потока выбранного трубопровода. В пределах одного участка трубы модель использует одно значение; для отдельного расчётного участка разделите трубу узлом.</p>
      </> : <label>Оборудование — источник показания
        <select aria-label="Оборудование — источник показания" value={sourceId} disabled={!editable} onChange={(e) => onUpdate(node.id, 'source_node_id', e.target.value)}>
          <option value="">Не привязано</option>
          {sourceId && !nodes.some((n) => n.id === sourceId) && <option value={sourceId}>Объект удалён ({sourceId})</option>}
          {nodes.filter((n) => !['field_instrument', 'junction'].includes(n.data.nodeType)).map((n) => (
            <option key={n.id} value={n.id}>{n.data.name} ({n.id})</option>
          ))}
        </select>
      </label>}
      <label>Измеряемый параметр
        <select aria-label="Измеряемый параметр" value={parameter} disabled={!editable} onChange={(e) => onUpdate(node.id, 'parameter', e.target.value)}>
          {[...choices].map((key) => <option key={key} value={key}>{PARAM_LABELS[key]?.label ?? key}{PARAM_LABELS[key]?.unit ? ` (${PARAM_LABELS[key].unit})` : ''}</option>)}
        </select>
      </label>
      <div className="field-instrument-reading">
        {typeof value === 'number' && Number.isFinite(value) ? fmtParam(parameter, value) : 'Нет показания'}
      </div>
      <InstrumentLimits nodeId={node.id} editable={editable} />
      {params.source_document != null && <p className="hint">
        {String(params.source_document)}, стр. {String(params.source_pages ?? '')}. {String(params.source_context ?? '')}
      </p>}
      <p className="hint">Перетащите прибор прямо на трубу или выберите трубопровод в списке. Позиционное обозначение и привязка сохраняются вместе со схемой.</p>
      {editable && <button className="btn btn-danger" onClick={() => onDelete(node.id)}>Удалить прибор</button>}
    </div>
  );
}
