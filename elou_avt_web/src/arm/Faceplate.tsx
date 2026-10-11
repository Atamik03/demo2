import ControlMode from '../components/ControlMode';
import { useEffect, useState } from 'react';
import EquipmentPassport from '../components/EquipmentPassport';
import { PARAM_LABELS, fmtParam } from '../schemeConfig';
import type { NodeTelemetry } from '../types';

/**
 * Панель управления аппаратом (faceplate) для режима АРМ —
 * приказ № 251-П, п. 7.4.8 «б» (панели управления) и п. 7.1.3:
 *  «и» — включение элементов с подтверждением во всплывающем окне;
 *  «е» — управление не более чем за 4 действия;
 *  «к» — панель не перекрывает основные параметры (висит сбоку).
 */
interface Props {
  nodeId: string;
  nodeName: string;
  nodeType: string;
  telemetry: NodeTelemetry | null;
  canControl: boolean;
  canInjectFailure: boolean;
  onUpdateParams?: (id: string, params: Record<string, number>) => Promise<void>;
  onAction: (equipmentId: string, actionType: string, value?: number | null) => Promise<void> | void;
  onFailure: (equipmentId: string) => Promise<void> | void;
  onClose: () => void;
}

const LABEL: Record<string, string> = {
  flow_kg_s: 'Расход, т/ч',
  pressure_bar: 'Избыточное давление, кгс/см²',
  pressure_in_bar: 'Избыточное давление на входе, кгс/см²',
  pressure_out_bar: 'Избыточное давление на выходе, кгс/см²',
  temperature_c: 'Температура, °C',
  temperature_out_c: 'Температура выход, °C',
  level_m: 'Уровень, м',
  level: 'Уровень, м',
  position: 'Открытие, %',
  speed_rpm: 'Частота, об/мин',
  power_w: 'Мощность, Вт',
  fuel_flow: 'Расход топлива',
  duty_w: 'Тепловая нагрузка, Вт',
  reflux_ratio: 'Флегмовое число',
  efficiency: 'КПД',
  volumetric_flow_m3_s: 'Объёмный расход, м³/с',
  mass_flow_kg_s: 'Расход, т/ч',
  pressure_rise_pa: 'Напор, Па',
  npsha_pa: 'NPSH доступный, Па',
  npshr_pa: 'NPSH требуемый, Па',
  setpoint: 'Уставка',
  volume_m3: 'Объём, м³',
  in_flow: 'Приток, т/ч',
  out_flow: 'Отток, т/ч',
};

export default function Faceplate({
  nodeId, nodeName, nodeType, telemetry, canControl, canInjectFailure, onAction, onFailure, onClose, onUpdateParams,
}: Props) {
  const p = (telemetry?.params ?? {}) as Record<string, number | boolean | string | null>;
  const running = telemetry?.running === true;
  const failed = telemetry?.failed === true;
  const num = (k: string) => (typeof p[k] === 'number' ? (p[k] as number) : undefined);

  const [sourceTemp, setSourceTemp] = useState(num('configured_temperature_c') ?? num('temperature_c') ?? 25);
  const [sourceFlow, setSourceFlow] = useState((num('configured_flow_kg_s') ?? num('flow_kg_s') ?? 100) * 3.6);
  const [sourceMessage, setSourceMessage] = useState('');
  useEffect(() => { setSourceTemp(num('configured_temperature_c') ?? num('temperature_c') ?? 25); setSourceFlow((num('configured_flow_kg_s') ?? num('flow_kg_s') ?? 100) * 3.6); setSourceMessage(''); }, [nodeId]);
  const [pos, setPos] = useState(num('position') ?? 70);
  const [speed, setSpeed] = useState(num('speed_rpm') ?? 1450);
  const [fuel, setFuel] = useState(num('fuel_flow') ?? 0.8);
  const [confirm, setConfirm] = useState<{ text: string; run: () => void } | null>(null);
  useEffect(() => { setPos(num('position') ?? 70); setSpeed(num('speed_rpm') ?? 1450); setFuel(num('fuel_flow') ?? 0.8); }, [nodeId]);   // eslint-disable-line react-hooks/exhaustive-deps

  /** Дискретные команды — только через подтверждение (п. 7.1.3 «и»). */
  const ask = (text: string, run: () => void) => setConfirm({ text, run });

  const controls = () => {
    if (!canControl) return <div className="fp-hint">Нет прав на управление</div>;
    switch (nodeType) {
      case 'source':
        return onUpdateParams ? <>
          <label className="fp-field">Температура внешнего потока, °C
            <input type="number" min={-50} max={1000} value={sourceTemp} onChange={e => setSourceTemp(Number(e.target.value))} />
          </label>
          {p.pressure_driven === true ? <div className="fp-hint">Расход определяется напором насосов и сопротивлением трубопроводов и клапанов.</div> : <label className="fp-field">Расход внешнего потока, т/ч
            <input type="number" min={0} max={1800} value={sourceFlow} onChange={e => setSourceFlow(Number(e.target.value))} />
          </label>}
          <button className="fp-btn" disabled={!Number.isFinite(sourceTemp) || sourceTemp < -50 || sourceTemp > 1000 || !Number.isFinite(sourceFlow) || sourceFlow < 0 || sourceFlow > 1800}
            onClick={async () => {
              try { await onUpdateParams(nodeId, { temperature_c: sourceTemp, ...(p.pressure_driven === true ? {} : { flow_kg_s: sourceFlow / 3.6 }) }); setSourceMessage('Граничные условия применены'); }
              catch { setSourceMessage('Не удалось применить граничные условия'); }
            }}>Применить граничные условия</button>
          {sourceMessage && <div className="fp-hint">{sourceMessage}</div>}
        </> : <div className="fp-hint">Изменение граничных условий доступно администратору</div>;
      case 'pump':
        return (
          <>
            <div className="fp-row">
              <button className="fp-btn go" disabled={running}
                onClick={() => ask(`Пустить «${nodeName}»?`, () => onAction(nodeId, 'TURN_ON'))}>Пуск</button>
              <button className="fp-btn stop" disabled={!running}
                onClick={() => ask(`Остановить «${nodeName}»?`, () => onAction(nodeId, 'TURN_OFF'))}>Стоп</button>
            </div>
            <label className="fp-field">
              Частота, об/мин
              <input type="number" step={50} value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))} />
            </label>
            <button className="fp-btn" onClick={() => void onAction(nodeId, 'SET_SPEED', speed)}>
              Применить частоту
            </button>
          </>
        );
      case 'valve':
      case 'angle_valve':
        return (
          <>
            <label className="fp-field">
              Открытие: <b>{pos.toFixed(0)} %</b>
              <input type="range" min={0} max={100} step={1} value={pos}
                onChange={(e) => setPos(Number(e.target.value))} />
            </label>
            <button className="fp-btn" onClick={() => void onAction(nodeId, 'SET_VALUE', pos / 100)}>
              Применить открытие
            </button>
          </>
        );
      case 'gate_valve':
        return (
          <div className="fp-row">
            <button className="fp-btn go"
              onClick={() => ask(`Открыть задвижку «${nodeName}»?`, () => onAction(nodeId, 'TURN_ON'))}>Открыть</button>
            <button className="fp-btn stop"
              onClick={() => ask(`Закрыть задвижку «${nodeName}»?`, () => onAction(nodeId, 'TURN_OFF'))}>Закрыть</button>
          </div>
        );
      case 'heater':
        return (
          <>
            <label className="fp-field">
              Расход топлива: <b>{fuel.toFixed(2)}</b>
              <input type="range" min={0} max={3.6} step={0.036} value={fuel * 3.6}
                onChange={(e) => setFuel(Number(e.target.value) / 3.6)} />
            </label>
            <button className="fp-btn" onClick={() => void onAction(nodeId, 'SET_VALUE', fuel)}>
              Применить расход
            </button>
            <button className="fp-btn stop"
              onClick={() => ask(`Сбросить топливо на печи «${nodeName}»?`,
                () => onAction(nodeId, 'EMERGENCY_STOP'))}>
              Сброс топлива
            </button>
          </>
        );
      case 'column':
        return (
          <label className="fp-field">
            Флегмовое число
            <input type="number" step={0.1} defaultValue={num('reflux_ratio') ?? 2}
              onBlur={(e) => void onAction(nodeId, 'SET_VALUE', Number(e.target.value))} />
          </label>
        );
      default:
        return <div className="fp-hint">Для этого аппарата управление не предусмотрено</div>;
    }
  };

  return (
    <aside className="arm-fp">
      <div className="fp-head">
        <div>
          <div className="fp-name">{nodeName}</div>
          <div className="fp-tag">{nodeId} · {nodeType}</div>
        </div>
        <button className="fp-x" onClick={onClose}>✕</button>
      </div>

      <div className={`fp-state ${failed ? 'bad' : running ? 'ok' : 'off'}`}>
        {failed ? 'ОТКАЗ' : nodeType === 'source' ? ((num('flow_kg_s') ?? 0) > 0 ? 'ПОТОК ПОСТУПАЕТ' : 'НЕТ РАСХОДА') : running ? 'В РАБОТЕ' : 'ОСТАНОВЛЕН'}
      </div>

      {p.heat_exchange_status && <p className="fp-hint">{String(p.heat_exchange_status)}</p>}
      <div className="fp-params">
        {Object.entries(p)
          .filter(([k, v]) => typeof v === 'number' && !k.startsWith('configured_'))
          .map(([k, v]) => (
            <div className="fp-param" key={k}>
              <span>{PARAM_LABELS[k]?.label ?? LABEL[k] ?? k}</span>
              <b>{fmtParam(k, v)}</b>
            </div>
          ))}
      </div>

      <EquipmentPassport nodeId={nodeId} />
      <ControlMode telemetry={telemetry} canControl={canControl}
        onMode={value => ask(`Перевести «${nodeName}» в ${value ? 'автоматический' : 'ручной'} режим?`, () => onAction(nodeId, 'SET_MODE', value))} />
      <div className="fp-controls">
        {controls()}
        {canInjectFailure && !failed && nodeType !== 'source' && nodeType !== 'sink' && (
          <button className="fp-btn failure"
            onClick={() => ask(`Смоделировать отказ оборудования «${nodeName}»?`, () => onFailure(nodeId))}>
            Имитация отказа
          </button>
        )}
      </div>

      {confirm && (
        <div className="fp-confirm">
          <div className="fp-confirm-box">
            <div className="fp-confirm-text">{confirm.text}</div>
            <div className="fp-row">
              <button className="fp-btn go" onClick={() => { confirm.run(); setConfirm(null); }}>Да</button>
              <button className="fp-btn" onClick={() => setConfirm(null)}>Отмена</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
