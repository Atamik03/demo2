import { useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import type { PracticeStatus } from '../types';

const ROLE_LABELS: Record<string, string> = {
  operator: 'Консольный оператор',
  field_operator: 'Полевой оператор',
};

export default function PracticeInvite() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [status, setStatus] = useState<PracticeStatus | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [declining, setDeclining] = useState(false);

  const permissions = user?.permissions ?? [];
  const isAdmin = permissions.includes('manage_users');
  const isInstructor =
    permissions.includes('manage_groups') ||
    permissions.includes('view_analytics') ||
    permissions.includes('monitor_operators');
  const isField = permissions.includes('view_field_operator_screen') && !isAdmin && !isInstructor;
  const isConsole = permissions.includes('view_scheme') && !isAdmin && !isInstructor;

  useEffect(() => {
    if (!isField && !isConsole) return;
    let alive = true;
    const tick = async () => {
      try {
        const cur = await api.lmsPracticeCurrent();
        if (alive) setStatus(cur);
      } catch {
        /* сервер может быть недоступен — ждём следующего опроса */
      }
    };
    tick();
    const t = window.setInterval(tick, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [isField, isConsole]);

  const join = useCallback(() => {
    if (!status) return;
    setDismissed(status.session_id);
    if (isField) {
      navigate('/field');
      return;
    }
    if (status.task_id) {
      navigate(`/run/${status.task_id}`);
      return;
    }
    navigate('/practice');
  }, [isField, status, navigate]);

  const decline = useCallback(async () => {
    if (!status || declining) return;
    setDeclining(true);
    setDismissed(status.session_id);
    try {
      await api.lmsPracticeDecline(status.session_id);
    } catch {
      /* отклонение не критично — окно скрыто */
    } finally {
      setDeclining(false);
    }
  }, [status, declining]);

  const active = !!status && status.status !== 'NO_ACTIVE';
  const onPracticeRoute =
    location.pathname.startsWith('/run/') || location.pathname === '/field';
  if (!isField && !isConsole) return null;
  if (!active || onPracticeRoute || status.session_id === dismissed) return null;

  const pending = status.status === 'PENDING_CONFIRM';
  const confirmed = new Set(status.confirmed_roles ?? []);

  return (
    <div className="practice-invite-overlay">
      <div className="practice-invite-card">
        <div className="practice-invite-title">
          {pending ? 'Практика запущена инструктором' : 'Практика идёт'}
        </div>
        <div className="practice-invite-task">
          {status.task_title ?? status.scenario_name ?? 'Практическое задание'}
        </div>
        {pending ? (
          <>
            <div className="practice-invite-text">
              Подтвердите готовность — практика стартует, когда готовность подтвердит консольный оператор.
            </div>
            <div className="practice-invite-roles">
              {(status.required_roles ?? []).map((role) => (
                <div className={`practice-gate-role ${confirmed.has(role) ? 'ok' : ''}`} key={role}>
                  <span className={`dot ${confirmed.has(role) ? 'dot-ok' : 'dot-wait'}`} />
                  {ROLE_LABELS[role] ?? role}
                  <span className="muted">{confirmed.has(role) ? ' · подтвердил' : ' · ожидание'}</span>
                </div>
              ))}
            </div>
            {status.timeout_seconds != null && status.timeout_seconds > 0 && (
              <div className="practice-invite-sub">
                Автостарт через {status.timeout_seconds} с, если второй оператор не подтвердит.
              </div>
            )}
          </>
        ) : (
          <div className="practice-invite-text">
            Практика уже началась. Перейдите в SCADA, чтобы продолжить работу.
          </div>
        )}
        <div className="practice-invite-actions">
          <button className="btn btn-start practice-invite-btn" onClick={join}>
            {isField ? 'Открыть экран полевого оператора' : 'Перейти к практике'}
          </button>
          {pending && (
            <button className="btn btn-danger practice-invite-btn" disabled={declining} onClick={() => void decline()}>
              Отклонить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
