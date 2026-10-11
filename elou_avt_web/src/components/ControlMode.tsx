import type { NodeTelemetry } from '../types';

export default function ControlMode({ telemetry, canControl, onMode }: {
  telemetry: NodeTelemetry | null;
  canControl: boolean;
  onMode: (value: number) => void;
}) {
  if (!telemetry?.control_mode) return null;
  const auto = telemetry.control_mode === 'АВТ';
  return <div className="equipment-mode-control">
    <div>Режим управления: <b>{auto ? 'Автоматический' : 'Ручной'}</b></div>
    <div className="fp-row">
      <button className="fp-btn" disabled={!canControl || auto} aria-pressed={auto} onClick={() => onMode(1)}>
        <span className="mode-mark auto">А</span> Авто
      </button>
      <button className="fp-btn" disabled={!canControl || !auto} aria-pressed={!auto} onClick={() => onMode(0)}>
        <span className="mode-mark manual">Р</span> Ручной
      </button>
    </div>
    <p className="fp-hint">Авто — команды сценария. Ручной — команды оператора. Аварийный останов действует в обоих режимах.</p>
  </div>;
}
