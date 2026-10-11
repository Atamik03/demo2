import { useNavigate } from 'react-router-dom';
import { api } from '../../api';
import type { InstructorSessionReviewRow } from '../../types';
import { Card, Chip, Empty, Err, Loader, Page, fmtDateTime, useAsync } from '../../lms/ui';

export default function SessionReviewsPage() {
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync<InstructorSessionReviewRow[]>(
    () => api.lmsInstructorSessionReviews(), [],
  );

  if (loading && !data) return <Loader />;
  if (error && !data) return <Err text={error} />;
  const rows = data ?? [];

  return (
    <Page title="Оценка сессий" subtitle="Разметка возможных причин неудачного прохождения"
      actions={<button className="btn" onClick={() => void reload()}>Обновить</button>}>
      <Card title="Сессии операторов" subtitle={`Всего: ${rows.length}`}>
        {rows.length === 0 ? <Empty text="Завершённых сессий пока нет" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Дата</th><th>Оператор</th><th>Сценарий</th><th>Балл</th><th>Оператор</th><th>Инструктор</th><th /></tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={row.session_id}>
                  <td className="muted">{row.wall_end ? fmtDateTime(row.wall_end) : '—'}</td>
                  <td className="bold">{row.operator_id}</td>
                  <td>{row.scenario_name || row.scenario_id}</td>
                  <td className="num bold">{row.performance_score == null ? '—' : row.performance_score.toFixed(1)}</td>
                  <td><Chip tone={row.operator_reviewed ? 'ok' : 'warn'}>{row.operator_reviewed ? 'размечено' : 'ожидается'}</Chip></td>
                  <td><Chip tone={row.instructor_reviewed ? 'ok' : 'warn'}>{row.instructor_reviewed ? 'размечено' : 'не размечено'}</Chip></td>
                  <td><button className="btn btn-small btn-start" onClick={() => navigate(`/debrief/${row.session_id}`)}>
                    {row.instructor_reviewed ? 'Изменить' : 'Разметить'}
                  </button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </Page>
  );
}
