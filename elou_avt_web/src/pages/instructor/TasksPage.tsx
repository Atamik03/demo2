import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api';
import type { Difficulty, LmsInviteCandidate, LmsPracticeTask, LmsScenario, PracticeStatus, TaskCategory } from '../../types';
import { Card, Chip, DifficultyTag, Empty, Err, Loader, Page, notifyToast, useAsync } from '../../lms/ui';

const EMPTY_FORM = {
  title: '',
  description: '',
  scenario_id: '',
  category: 'practice' as TaskCategory,
  difficulty: 'MIDDLE' as Difficulty,
  duration_min: 10,
  required_competencies: '',
  is_random: false,
  enabled: true,
};

export default function InstructorTasksPage() {
  const { data, error, loading, reload } = useAsync<LmsPracticeTask[]>(() => api.lmsPracticeTasks(true), []);
  const scenarios = useAsync<LmsScenario[]>(() => api.lmsScenarios(), []);
  const navigate = useNavigate();
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [launchingId, setLaunchingId] = useState<number | null>(null);
  const [inviteTask, setInviteTask] = useState<LmsPracticeTask | null>(null);
  const [candidates, setCandidates] = useState<LmsInviteCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [inviteConsole, setInviteConsole] = useState('');
  const [inviteField, setInviteField] = useState('');
  const [current, setCurrent] = useState<PracticeStatus | null>(null);
  const [finishingId, setFinishingId] = useState(false);

  // Активная (идущая/ожидающая) практика — чтобы инструктор мог подключиться
  // и завершить её прямо со списка заданий.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const c = await api.lmsPracticeCurrent();
        if (alive) setCurrent(c);
      } catch {
        /* сервер недоступен — ждём следующего опроса */
      }
    };
    tick();
    const t = window.setInterval(tick, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  const finishCurrent = async () => {
    if (!current?.session_id || finishingId) return;
    setFinishingId(true);
    try {
      const a = await api.lmsPracticeFinish(current.session_id);
      setCurrent(null);
      notifyToast('Практика завершена');
      navigate(`/debrief/${a.session_id ?? current.session_id}`, { replace: true });
    } catch (e) {
      notifyToast(`Ошибка завершения: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setFinishingId(false);
    }
  };

  useEffect(() => {
    if (!inviteTask) return;
    let alive = true;
    setCandidatesLoading(true);
    setInviteConsole('');
    setInviteField('');
    api.lmsInviteCandidates(inviteTask.scenario_id)
      .then((c) => {
        if (alive) setCandidates(c);
      })
      .catch(() => {
        if (alive) setCandidates([]);
      })
      .finally(() => {
        if (alive) setCandidatesLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [inviteTask]);

  const openInvite = (task: LmsPracticeTask) => {
    setInviteTask(task);
  };

  const openNew = () => {
    setForm({ ...EMPTY_FORM });
    setEditId(0);
  };

  const openEdit = (t: LmsPracticeTask) => {
    setForm({
      title: t.title,
      description: t.description,
      scenario_id: t.scenario_id,
      category: t.category,
      difficulty: t.difficulty,
      duration_min: t.duration_min,
      required_competencies: t.required_competencies.join(', '),
      is_random: t.is_random,
      enabled: t.enabled,
    });
    setEditId(t.id);
  };

  const save = async () => {
    const body = {
      ...form,
      required_competencies: form.required_competencies.split(',').map((s) => s.trim()).filter(Boolean),
    };
    try {
      if (editId === 0) {
        await api.lmsCreateTask(body);
        notifyToast('Задание создано');
      } else if (editId) {
        await api.lmsUpdateTask(editId, body);
        notifyToast('Задание обновлено');
      }
      setEditId(null);
      await reload();
    } catch (e) {
      notifyToast(`Ошибка: ${e instanceof Error ? e.message : e}`);
    }
  };

  const toggleEnabled = async (t: LmsPracticeTask) => {
    try {
      await api.lmsUpdateTask(t.id, { enabled: !t.enabled });
      await reload();
    } catch (e) {
      notifyToast(`Ошибка: ${e instanceof Error ? e.message : e}`);
    }
  };

  const launch = async (task: LmsPracticeTask, invitedUsernames: string[]) => {
    const moduleId = task.module_id ?? 0;
    if (!moduleId || launchingId != null) return;
    setLaunchingId(task.id);
    try {
      const s = await api.lmsPracticeStart(moduleId, 'gated', invitedUsernames);
      const who = (s.invited_users ?? [])
        .map((i) => i.full_name || i.username)
        .join(', ');
      notifyToast(
        `Практика запущена (сессия ${s.session_id.slice(0, 8)}).${who ? ` Приглашён: ${who}.` : ''} Ожидается подтверждение консольного оператора.`,
      );
      setInviteTask(null);
    } catch (e) {
      notifyToast(`Ошибка запуска: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLaunchingId(null);
    }
  };

  if (loading && !data) return <Loader />;
  if (error && !data) return <Err text={error} />;

  const tasks = data ?? [];

  return (
    <Page
      title="Практические задания"
      subtitle="Библиотека заданий тренажёра"
      actions={
        <>
          <button className="btn" onClick={() => void reload()}>Обновить</button>
          <button className="btn btn-start" onClick={openNew}>Новое задание</button>
        </>
      }
    >
      {current && (
        <Card>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <div className="bold">{current.task_title || current.scenario_name || 'Активная практика'}</div>
              <div className="muted" style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span className={`chip ${current.status === 'RUNNING' ? 'chip-ok' : 'chip-info'}`}>
                  {current.status === 'RUNNING' ? 'ИДЁТ' : 'ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ'}
                </span>
                <span>сессия <span className="mono">{current.session_id.slice(0, 12)}</span></span>
                {current.status === 'RUNNING' && current.sim_time != null && (
                  <span>t = {current.sim_time.toFixed(0)} с</span>
                )}
              </div>
            </div>
            <div className="row" style={{ gap: 8 }}>
              {current.task_id != null && (
                <button
                  className="btn btn-start"
                  onClick={() => navigate(`/run/${current.task_id}?instructor=1`)}
                >
                  Подключиться к сессии
                </button>
              )}
              {current.status === 'RUNNING' && (
                <button className="btn btn-stop" disabled={finishingId} onClick={() => void finishCurrent()}>
                  {finishingId ? 'Завершаем…' : 'Завершить практику'}
                </button>
              )}
            </div>
          </div>
        </Card>
      )}

      <Card>
        {tasks.length === 0 ? (
          <Empty text="Заданий нет" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Задание</th>
                  <th>Сценарий</th>
                  <th>Категория</th>
                  <th>Сложность</th>
                  <th>Длительность</th>
                  <th>Компетенции</th>
                  <th>Случайное</th>
                  <th>Активно</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id}>
                    <td className="bold">{t.title}</td>
                    <td className="muted">{t.scenario_name || t.scenario_id}</td>
                    <td><Chip tone={t.category === 'exam' ? 'bad' : 'ok'}>{t.category}</Chip></td>
                    <td><DifficultyTag d={t.difficulty} /></td>
                    <td className="num">⏱ {t.duration_min} мин</td>
                    <td style={{ maxWidth: 280 }}>
                      <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                        {t.required_competencies.map((c) => (
                          <Chip key={c}>{c}</Chip>
                        ))}
                      </div>
                    </td>
                    <td><Chip tone={t.is_random ? 'warn' : 'muted'}>{t.is_random ? 'да' : 'нет'}</Chip></td>
                    <td>
                      <button className={`btn ${t.enabled ? 'btn-start' : 'btn-danger'}`} onClick={() => void toggleEnabled(t)}>
                        {t.enabled ? 'Вкл' : 'Выкл'}
                      </button>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn" onClick={() => openEdit(t)}>Изменить</button>
                        <button
                          className="btn btn-start"
                          disabled={!t.module_id || !t.enabled || launchingId != null}
                          onClick={() => openInvite(t)}
                        >
                          {launchingId === t.id ? 'Запуск…' : 'Запустить практику'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {inviteTask && (
        <div className="modal-overlay" onClick={() => setInviteTask(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="page-title" style={{ fontSize: 16 }}>
              Запуск практики: {inviteTask.title}
            </div>
            {candidatesLoading ? (
              <Loader text="Загрузка операторов…" />
            ) : (
              (() => {
                const sc = (scenarios.data ?? []).find((s) => s.id === inviteTask.scenario_id);
                const isMulti = Boolean(sc?.multi_operator);
                const consoleOps = candidates.filter((c) => c.role !== 'field_operator');
                const fieldOps = candidates.filter((c) => c.role === 'field_operator');
                return (
                  <>
                    <div className="settings-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                      <div className="form-field">
                        <label className="form-label">Консольный оператор</label>
                        <select
                          className="scenario-select full"
                          value={inviteConsole}
                          onChange={(e) => setInviteConsole(e.target.value)}
                        >
                          <option value="">— не приглашать —</option>
                          {consoleOps.map((c) => (
                            <option key={c.username} value={c.username}>
                              {c.full_name || c.username}
                            </option>
                          ))}
                        </select>
                        <div className="inspector-hint">Управляет процессом с мнемосхемы.</div>
                      </div>
                      <div className="form-field">
                        <label className="form-label">Полевой оператор</label>
                        <select
                          className="scenario-select full"
                          value={inviteField}
                          disabled={!isMulti}
                          onChange={(e) => setInviteField(e.target.value)}
                        >
                          <option value="">— не приглашать —</option>
                          {fieldOps.map((c) => (
                            <option key={c.username} value={c.username}>
                              {c.full_name || c.username}
                            </option>
                          ))}
                        </select>
                        {isMulti ? (
                          <div className="inspector-hint">Работает с 3D-экраном установки.</div>
                        ) : (
                          <div className="inspector-hint" style={{ color: 'var(--danger)' }}>
                            Сценарий не мультиоператорный — полевой оператор недоступен.
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="row" style={{ justifyContent: 'flex-end' }}>
                      <button className="btn" onClick={() => setInviteTask(null)}>Отмена</button>
                      <button
                        className="btn btn-start"
                        disabled={launchingId != null}
                        onClick={() => void launch(inviteTask, [inviteConsole, inviteField].filter(Boolean))}
                      >
                        {launchingId === inviteTask.id ? 'Запуск…' : 'Запустить'}
                      </button>
                    </div>
                  </>
                );
              })()
            )}
          </div>
        </div>
      )}

      {editId !== null && (
        <div className="modal-overlay" onClick={() => setEditId(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="page-title" style={{ fontSize: 16 }}>
              {editId === 0 ? 'Новое задание' : `Задание #${editId}`}
            </div>
            <div className="form-field">
              <label className="form-label">Название</label>
              <input className="form-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div className="form-field">
              <label className="form-label">Описание</label>
              <textarea className="form-input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="settings-grid">
              <div className="form-field">
                <label className="form-label">Сценарий</label>
                <select className="scenario-select full" value={form.scenario_id} onChange={(e) => setForm({ ...form, scenario_id: e.target.value })}>
                  <option value="">— выберите —</option>
                  {(scenarios.data ?? []).map((s) => (
                    <option key={s.id} value={s.id}>{s.name || s.id}</option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label className="form-label">Категория</label>
                <select className="scenario-select full" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as TaskCategory })}>
                  <option value="practice">Практика</option>
                  <option value="exam">Экзамен</option>
                  <option value="random">Случайное</option>
                </select>
              </div>
              <div className="form-field">
                <label className="form-label">Сложность</label>
                <select className="scenario-select full" value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value as Difficulty })}>
                  <option value="EASY">Просто</option>
                  <option value="MIDDLE">Средне</option>
                  <option value="HARD">Сложно</option>
                </select>
              </div>
              <div className="form-field">
                <label className="form-label">Длительность, мин</label>
                <input className="form-input" type="number" min={1} value={form.duration_min} onChange={(e) => setForm({ ...form, duration_min: Number(e.target.value) || 10 })} />
              </div>
            </div>
            <div className="form-field">
              <label className="form-label">Требуемые компетенции (через запятую)</label>
              <input className="form-input" value={form.required_competencies} onChange={(e) => setForm({ ...form, required_competencies: e.target.value })} />
            </div>
            <div className="row" style={{ gap: 16 }}>
              <label className="ctrl-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <input type="checkbox" checked={form.is_random} onChange={(e) => setForm({ ...form, is_random: e.target.checked })} />
                Случайные условия
              </label>
              <label className="ctrl-label" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                Активно
              </label>
            </div>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setEditId(null)}>Отмена</button>
              <button className="btn btn-start" onClick={() => void save()}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </Page>
  );
}
