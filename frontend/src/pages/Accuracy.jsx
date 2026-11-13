import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts';
import { getMetrics } from '../api.js';
import LoadError from '../components/LoadError.jsx';

export default function Accuracy() {
  const { t } = useTranslation();
  const [m, setM] = useState(null);

  const [error, setError] = useState('');
  useEffect(() => { getMetrics().then(setM).catch((e) => setError(e.message)); }, []);
  if (error) return <LoadError message={error} />;
  if (!m) return <div className="skeleton" />;

  const byType = Object.entries(m.per_type).map(([type, v]) => ({ type, precision: v.precision, recall: v.recall, f1: v.f1 }));
  const pct = (x) => `${Math.round(x * 100)}%`;

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>{t('accuracy.title')}</h1>
          <p className="muted small">{t('accuracy.note')}</p>
        </div>
      </div>

      <div className="stat-row">
        {[['precision', m.overall.precision], ['recall', m.overall.recall], ['f1', m.overall.f1]].map(([k, v]) => (
          <div key={k} className="card stat">
            <span className="muted">{t(`accuracy.${k}`)}</span>
            <strong>{pct(v)}</strong>
          </div>
        ))}
      </div>

      <div className="card">
        <h3>{t('accuracy.byType')}</h3>
        <div style={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={byType}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="type" stroke="var(--text-muted)" />
              <YAxis stroke="var(--text-muted)" domain={[0, 1]} tickFormatter={pct} />
              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} formatter={(v) => pct(v)} />
              <Bar dataKey="precision" fill="var(--brand)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="recall" fill="var(--verified)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card table-wrap">
        <h3>{t('accuracy.byPatient')}</h3>
        <table className="table">
          <thead><tr><th scope="col">Patient</th><th scope="col">{t('accuracy.precision')}</th><th scope="col">{t('accuracy.recall')}</th><th scope="col">{t('accuracy.f1')}</th></tr></thead>
          <tbody>
            {Object.entries(m.per_patient).map(([pid, v]) => (
              <tr key={pid}><td>{pid}</td><td>{pct(v.precision)}</td><td>{pct(v.recall)}</td><td>{pct(v.f1)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
