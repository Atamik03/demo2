import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import type { LmsDebrief } from '../types';
import {
  Card,
  Chip,
  Empty,
  Err,
  Loader,
  Page,
  Score,
  fmtClock,
  fmtDur,
  useAsync,
} from '../lms/ui';

const ERROR_LABELS: Record<string, string> = {
  WRONG_SEQUENCE: 'Нарушение последовательности действий',
  DELAYED_ACTION: 'Действие выполнено с задержкой',
  WRONG_EQUIPMENT: 'Выбрано неправильное оборудование',
  WRONG_ACTION_TYPE: 'Выбран неправильный тип действия',
  WRONG_PARAMETER_VALUE: 'Задано неправильное значение параметра',
  MISSED_ACTION: 'Пропущено обязательное действие',
  REGULATORY_VIOLATION: 'Нарушение технологического регламента',
};

const SEVERITY_LABELS: Record<string, string> = {
  LOW: 'низкий',
  MEDIUM: 'средний',
  HIGH: 'высокий',
  CRITICAL: 'критический',
};

const CAUSES = [
  'Потеря ориентации в установке',
  'Долгое время реакции',
  'Непонимание физических процессов',
  'Незнание алгоритма или регламента',
  'Случайная ошибка',
];

function qualTone(q: string): 'q-ok' | 'q-warn' | 'q-bad' {
  if (q.includes('ОТЛИЧНО')) return 'q-ok';
  if (q.includes('НЕ СДАНО')) return 'q-bad';
  return 'q-warn';
}

export default function DebriefPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [selectedCause, setSelectedCause] = useState('');
  const [instructorAgrees, setInstructorAgrees] = useState<boolean | null>(null);
  const [instructorCauses, setInstructorCauses] = useState<string[]>([]);
  const [savingReview, setSavingReview] = useState(false);
  const [reviewMessage, setReviewMessage] = useState('');
  const { data, error, loading } = useAsync<LmsDebrief>(
    () => (sessionId ? api.lmsDebrief(sessionId) : Promise.reject(new Error('Нет сессии'))),
    [sessionId],
  );

  if (loading) return <Loader text="Формируем разбор выполнения…" />;
  if (error) return <Err text={error} />;
  if (!data) return <Empty />;

  const d = data;
  const review = d.cause_review;
  const predictions = review?.predictions_json ?? [];
  const isInstructor = d.can_review_as_instructor;
  const allOperatorAnswered = predictions.length > 0 && predictions.every((p) => p.cause_id in answers);
  const allRejected = allOperatorAnswered && predictions.every((p) => answers[p.cause_id] === false);

  const saveOperatorReview = async () => {
    if (!sessionId || !allOperatorAnswered || (allRejected && !selectedCause)) return;
    setSavingReview(true); setReviewMessage('');
    try {
      await api.saveOperatorCauseReview(sessionId, answers, selectedCause);
      setReviewMessage('Ваша оценка сохранена');
    } catch (e) { setReviewMessage(e instanceof Error ? e.message : String(e)); }
    finally { setSavingReview(false); }
  };

  const saveInstructorReview = async () => {
    if (!sessionId || instructorAgrees == null || (!instructorAgrees && instructorCauses.length === 0)) return;
    setSavingReview(true); setReviewMessage('');
    try {
      await api.saveInstructorCauseReview(sessionId, instructorAgrees, instructorCauses);
      setReviewMessage('Разметка инструктора сохранена');
    } catch (e) { setReviewMessage(e instanceof Error ? e.message : String(e)); }
    finally { setSavingReview(false); }
  };

  return (
    <Page
      title="Анализ выполнения задания"
      subtitle={d.task_title || d.scenario_name || d.scenario_id}
      actions={
        <>
          <button className="btn" onClick={() => navigate('/practice')}>К практике</button>
          <button className="btn btn-ghost" onClick={() => navigate('/history')}>К истории</button>
        </>
      }
    >
      <Card title="Итоги">
        <div className="debrief-score">
          <Score value={d.performance_score} size={112} />
          <div className="col" style={{ gap: 8 }}>
            <div>
              <div className="muted" style={{ fontSize: 11 }}>Квалификационная оценка</div>
              <div className={`qual ${qualTone(d.qualification)}`}>{d.qualification || '—'}</div>
            </div>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
              <div>
                <div className="muted" style={{ fontSize: 11 }}>Длительность</div>
                <div className="bold num">{fmtDur(d.duration_s)}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11 }}>Симуляционное время</div>
                <div className="bold num">{fmtClock(d.sim_start)} – {fmtClock(d.sim_end)}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 11 }}>Оператор</div>
                <div className="bold">{d.operator_id}</div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="hero-row">
        <div className="hero-main">
          <Card title="Последовательность действий" subtitle={`Журнал операций · ${d.steps.length}`}>
            {d.steps.length === 0 ? (
              <Empty text="Действий не зафиксировано" />
            ) : (
              <ul className="steps">
                {d.steps.map((s) => (
                  <li key={s.seq} className="step-row">
                    <span className="step-seq">{s.seq}</span>
                    <div className="step-body">
                      <div className="step-desc">{s.description}</div>
                      <div className="step-detail">{s.detail}</div>
                    </div>
                    <span className="step-time">{fmtClock(s.timestamp)}</span>
                    {s.status === 'rejected' && (
                      <span className="step-status">
                        <Chip tone="bad">отклонено</Chip>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Ошибки и замечания" subtitle={`${d.remarks.length + d.errors.length}`}>
            {d.remarks.length > 0 && (
              <ul className="err-list">
                {d.remarks.map((r, i) => (
                  <li key={i} className="err-item remark-item">
                    <div className="err-title remark-title">{r}</div>
                  </li>
                ))}
              </ul>
            )}
            {d.errors.length === 0 ? (
              d.remarks.length > 0 ? null : <Empty text="Ошибок не зафиксировано — отличная работа" />
            ) : (
              <ul className="err-list">
                {d.errors.map((e, i) => (
                  e.rule_error_type === 'PRACTICE_FEEDBACK' ? (
                    <li key={i} className="err-item remark-item">
                      <div className="err-title remark-title">{e.cause || e.rule_error_type}</div>
                    </li>
                  ) : (
                  <li key={i} className="err-item">
                    <div className="err-title">{ERROR_LABELS[e.rule_error_type] ?? e.rule_error_type}</div>
                    <div className="err-meta">
                      {e.severity && `Уровень: ${SEVERITY_LABELS[e.severity] ?? e.severity} · `}Время: {fmtClock(e.timestamp)}
                    </div>
                    {e.cause && <div className="err-meta">Причина: {e.cause}</div>}
                    {e.consequence && <div className="err-meta">Последствие: {e.consequence}</div>}
                    {e.expected_action && <div className="err-meta">Ожидалось: {e.expected_action}</div>}
                  </li>
                  )
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="hero-side">
          {review && predictions.length > 0 && (
            <Card title="Возможные причины неудачного прохождения">
              <div className="cause-review">
                {predictions.map((p, index) => (
                  <div className="cause-prediction" key={p.cause_id}>
                    <div className="bold">{index + 1}. {p.cause}</div>
                    <div className="muted">Уверенность модели: {(p.confidence * 100).toFixed(1)}%</div>
                    <div className="cause-question">Согласны ли вы с этой причиной?</div>
                    {!isInstructor ? (
                      <div className="row">
                        <button className={`btn btn-small ${answers[p.cause_id] === true ? 'btn-start' : ''}`}
                          onClick={() => setAnswers((old) => ({ ...old, [p.cause_id]: true }))}>Да</button>
                        <button className={`btn btn-small ${answers[p.cause_id] === false ? 'btn-stop' : ''}`}
                          onClick={() => setAnswers((old) => ({ ...old, [p.cause_id]: false }))}>Нет</button>
                      </div>
                    ) : <div className="muted">Ответ оператора: {review.operator_answers_json?.[p.cause_id] == null ? 'нет разметки' : review.operator_answers_json[p.cause_id] ? 'да' : 'нет'}</div>}
                  </div>
                ))}

                {!isInstructor && allRejected && (
                  <label className="cause-select-label">
                    Укажите причину неудачи, которую вы считаете достоверной.
                    <select className="scenario-select full" value={selectedCause} onChange={(e) => setSelectedCause(e.target.value)}>
                      <option value="">Выберите причину</option>
                      {CAUSES.map((cause) => <option key={cause} value={cause}>{cause}</option>)}
                    </select>
                  </label>
                )}
                {!isInstructor && (
                  <button className="btn btn-start" disabled={savingReview || !allOperatorAnswered || (allRejected && !selectedCause)} onClick={() => void saveOperatorReview()}>
                    Сохранить оценку
                  </button>
                )}

                {isInstructor && (
                  <div className="instructor-review">
                    <div className="muted">Выбор оператора: {review.operator_selected_cause || 'отдельная причина не выбрана'}</div>
                    <div className="cause-question">Вы согласны с итоговой разметкой?</div>
                    <div className="row">
                      <button className={`btn btn-small ${instructorAgrees === true ? 'btn-start' : ''}`} onClick={() => setInstructorAgrees(true)}>Да</button>
                      <button className={`btn btn-small ${instructorAgrees === false ? 'btn-stop' : ''}`} onClick={() => setInstructorAgrees(false)}>Нет</button>
                    </div>
                    {instructorAgrees === false && CAUSES.map((cause) => (
                      <label className="cause-check" key={cause}>
                        <input type="checkbox" checked={instructorCauses.includes(cause)} onChange={(e) => setInstructorCauses((old) => e.target.checked ? [...old, cause] : old.filter((x) => x !== cause))} />
                        {cause}
                      </label>
                    ))}
                    <button className="btn btn-start" disabled={savingReview || instructorAgrees == null || (instructorAgrees === false && instructorCauses.length === 0)} onClick={() => void saveInstructorReview()}>
                      Сохранить разметку инструктора
                    </button>
                  </div>
                )}
                {reviewMessage && <div className="muted">{reviewMessage}</div>}
              </div>
            </Card>
          )}
          <Card title="Рекомендации">
            {d.recommendations.length === 0 ? (
              <Empty text="Рекомендаций нет" />
            ) : (
              <ul className="reco-list">
                {d.recommendations.map((r, i) => (
                  <li key={i} className="reco-item">
                    <span className="reco-ico">→</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Изменение компетенций">
            {d.competency_delta.length === 0 ? (
              <Empty text="Связанные компетенции не определены" />
            ) : (
              <div>
                {d.competency_delta.map((c) => (
                  <div key={c.code} className="delta-row">
                    <span className="delta-title">{c.title}</span>
                    <span className="delta-old num">{c.old.toFixed(1)}</span>
                    <span className="delta-arrow">→</span>
                    <span className={`delta-new num ${c.delta >= 0 ? 'up' : 'down'}`}>
                      {c.new.toFixed(1)}
                    </span>
                    <span className="delta-val">
                      {c.delta >= 0 ? '+' : ''}{c.delta.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {d.alarms.length > 0 && (
            <Card title={`События аварий · ${d.alarms.length}`}>
              <div className="table-wrap">
                <table className="table" style={{ fontSize: 11.5 }}>
                  <thead>
                    <tr><th>Время</th><th>Тревога</th><th>Значение</th></tr>
                  </thead>
                  <tbody>
                    {d.alarms.slice(0, 20).map((a, i) => (
                      <tr key={i}>
                        <td className="num">{fmtClock(Number(a.raised_at ?? a.timestamp ?? 0))}</td>
                        <td>{String(a.parameter ?? a.description ?? '—')}</td>
                        <td className="num">{a.actual_value != null ? Number(a.actual_value).toFixed(1) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );
}
