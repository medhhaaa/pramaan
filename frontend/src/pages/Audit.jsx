import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getAudit } from '../api.js';
import { useApp } from '../context/AppContext.jsx';

const PAGE = 20;

export default function Audit() {
  const { t } = useTranslation();
  const { user, session } = useApp();
  const [rows, setRows] = useState([]);
  const [action, setAction] = useState('all');
  const [page, setPage] = useState(0);
  const pid = user.role === 'patient' ? user.patientId : session?.patientId;

  useEffect(() => { getAudit(pid).then(setRows); }, [pid]);

  const filtered = rows.filter((r) => action === 'all' || r.action === action);
  const shown = filtered.slice(page * PAGE, page * PAGE + PAGE);
  const actions = ['all', ...new Set(rows.map((r) => r.action))];

  return (
    <section>
      <div className="page-head">
        <h1>{t('audit.title')}</h1>
        <select className="input select-sm" value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} aria-label="Filter by action">
          {actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{t('audit.time')}</th>
              <th scope="col">{t('audit.who')}</th>
              <th scope="col">{t('audit.action')}</th>
              <th scope="col">{t('audit.patient')}</th>
              <th scope="col">{t('audit.detail')}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i}><td className="mono small">{r.time}</td><td>{r.who}</td><td>{r.action}</td><td>{r.patient}</td><td>{r.detail}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
        <button className="btn btn-ghost btn-sm" disabled={(page + 1) * PAGE >= filtered.length} onClick={() => setPage(page + 1)}>›</button>
      </div>
    </section>
  );
}
