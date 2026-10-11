import { useState } from 'react';
import type { Edge } from '@xyflow/react';
import { PHASE_TYPES, phaseMeta, contrastText, DEFAULT_PHASE } from '../schemeConfig';
import { STREAM_PARAMS } from '../schemeConfig';

interface Props {
  edge: Edge | null;
  onPhase: (edgeId: string, phaseId: string) => void;
  onWaypoints: (edgeId: string, pts: { x: number; y: number }[]) => void;
  onUpdateDisp?: (edgeId: string, keys: string[]) => void;
  onDeleteEdge?: (edgeId: string) => void;
  disp?: string[];
  canEditScheme?: boolean;
}

export default function EdgeInspector({ edge, onPhase, onWaypoints, onUpdateDisp, onDeleteEdge, disp = [], canEditScheme = true }: Props) {
  const phase = edge ? phaseMeta((edge.data as { phase?: string } | undefined)?.phase ?? DEFAULT_PHASE) : phaseMeta(DEFAULT_PHASE);
  const pathOptions = (edge as (Edge & { pathOptions?: { waypoints?: { x: number; y: number }[] } }) | null)?.pathOptions;
  const waypoints = pathOptions?.waypoints ?? [];
  const [draft, setDraft] = useState<string | null>(null);

  if (!edge) {
    return (
      <div className="inspector-empty">
        Кликните по линии на схеме, чтобы задать фазу потока, поправить её трассу, показать свойства потока и удалить линию.
      </div>
    );
  }

  return (
    <div>
      <div className="inspector-header" style={{ borderLeft: `3px solid ${phase.color}` }}>
        <div style={{ fontWeight: 700 }}>Поток: {edge.source} → {edge.target}</div>
        <div style={{ fontSize: 10, color: '#7f93a6' }}>{edge.id}</div>
      </div>

      <div className="inspector-group-title">ФАЗА / СРЕДА В ЛИНИИ</div>
      <select
        className="scenario-select full"
        value={draft ?? phase.id}
        onChange={(e) => {
          setDraft(null);
          onPhase(edge.id, e.target.value);
        }}
        disabled={!canEditScheme}
      >
        {PHASE_TYPES.map((p) => (
          <option key={p.id} value={p.id}>{p.label}</option>
        ))}
      </select>
      <div className="edge-swatch" style={{ background: phase.color, color: contrastText(phase.color) }}>
        <span>{phase.label}</span>
      </div>

      <div className="inspector-group-title">ТРАССА ЛИНИИ</div>
      <div className="edge-offset-row">
        <span className="ctrl-label" style={{ flex: 1 }}>Изломов: {waypoints.length}</span>
        <button
          className="btn btn-ghost"
          onClick={() => onWaypoints(edge.id, [])}
          disabled={!canEditScheme || waypoints.length === 0}
        >
          Выпрямить
        </button>
      </div>
      <div className="inspector-hint">
        Потяните участок трубы: горизонтальный сдвигается вверх и вниз, вертикальный — влево и вправо.
        Двойной ЛКМ начинает отвод, двойной ПКМ — входящую ветвь.
        Затем нажмите нужный штуцер аппарата. Esc отменяет подключение.

      </div>

      {canEditScheme && onUpdateDisp && (
        <div style={{ marginTop: 12 }}>
          <div className="panel-title">ПОКАЗЫВАТЬ НА СХЕМЕ</div>
          <div className="param-list">
            {Object.keys(STREAM_PARAMS).map((k) => {
              const on = disp.includes(k);
              return (
                <label className="param-check" key={k}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => {
                      const next = on ? disp.filter((x) => x !== k) : [...disp, k];
                      onUpdateDisp(edge.id, next);
                    }}
                  />
                  <span>{STREAM_PARAMS[k].label}</span>
                </label>
              );
            })}
          </div>
          <div className="inspector-hint">
            Отмеченные свойства показываются квадратиком у средней части линии. Значения берутся из телеметрии
            узла-источника. Перетаскивайте квадратик, чтобы подвинуть его; ручка в углу меняет размер; двойной клик —
            переименовать подпись.
          </div>
        </div>
      )}

      {canEditScheme && onDeleteEdge && (
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-danger" onClick={() => onDeleteEdge(edge.id)}>🗑 Удалить линию</button>
          <div className="inspector-hint">Также линию можно удалить клавишей Delete/Backspace после клика по ней.</div>
        </div>
      )}
    </div>
  );
}
