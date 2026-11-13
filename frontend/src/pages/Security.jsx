// Privacy & security scorecard: every number is measured by the backend when the page opens
// (backend/routes/security.py). Each line says what was checked and how; nothing claims
// "100% secure".
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, XCircle, Eye, RefreshCw } from 'lucide-react';
import { getScorecard } from '../api.js';
import LoadError from '../components/LoadError.jsx';

export default function Security() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);

  const load = (runTests = false) => {
    setRunning(runTests);
    return getScorecard(runTests)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setRunning(false));
  };
  useEffect(() => { load(false); }, []);

  if (error) return <LoadError message={error} />;
  if (!data) return <div className="skeleton" />;

  const passed = data.checks.filter((c) => c.passed).length;

  return (
    <section className="security-page">
      <div className="page-head">
        <div>
          <h1>{t('security.title', { defaultValue: 'Privacy & security scorecard' })}</h1>
          <p className="muted small">
            {t('security.note', { defaultValue: 'Measured just now on the records you can see. Each line says exactly what was checked. We do not claim to be "100% secure"; we show what we tested.' })}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => load(true)} disabled={running}>
          <RefreshCw size={14} /> {running
            ? t('security.running', { defaultValue: 'Running tests…' })
            : t('security.runTests', { defaultValue: 'Run security tests' })}
        </button>
      </div>

      {/* first: the proof people ask about most, what the AI was actually sent */}
      <AiSawTable documents={data.documents} />

      <h2 className="mt">{t('security.checksTitle', { defaultValue: 'Security checks' })}</h2>
      <div className="stat-row">
        <div className="card stat">
          <span className="muted">{t('security.checksPassed', { defaultValue: 'Checks passed' })}</span>
          <strong>{passed}/{data.checks.length}</strong>
        </div>
        <div className="card stat">
          <span className="muted">{t('security.documents', { defaultValue: 'Documents checked' })}</span>
          <strong>{data.documents.length}</strong>
        </div>
        <div className="card stat">
          <span className="muted">{t('security.measured', { defaultValue: 'Measured at' })}</span>
          <strong className="small">{new Date(data.generated_at).toLocaleTimeString()}</strong>
        </div>
      </div>

      <div className="score-list">
        {data.checks.map((c) => (
          <div key={c.key} className={`card score ${c.passed ? 'score-pass' : 'score-fail'}`}>
            <div className="score-head">
              {c.passed ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
              <span className="score-title">{c.title}</span>
              <strong className="score-result">{c.result}</strong>
            </div>
            <p className="muted small">{c.how}{c.ran_at ? ` (${t('security.ranAt', { defaultValue: 'last run' })} ${new Date(c.ran_at).toLocaleTimeString()})` : ''}</p>
            {c.details?.length > 0 && c.details[0] && (
              <ul className="small score-details">{c.details.map((d) => <li key={d}>{d}</li>)}</ul>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// Each document: what was sent to the AI, how many identifiers were removed and left, and a link
// to the side-by-side view (/ai-view/{id}).
function AiSawTable({ documents }) {
  const { t } = useTranslation();
  return (
    <div className="card">
      <h3>{t('security.aiSaw', { defaultValue: 'What the AI saw, document by document' })}</h3>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{t('security.document', { defaultValue: 'Document' })}</th>
              <th>{t('security.sentAs', { defaultValue: 'Sent to the AI as' })}</th>
              <th>{t('security.removed', { defaultValue: 'Identifiers removed' })}</th>
              <th>{t('security.left', { defaultValue: 'Identifiers left' })}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id}>
                <td><div>{d.filename}</div><div className="muted small mono">{d.id} · {d.patient_name}</div></td>
                <td>{d.error ? <span className="error small">{d.error}</span> : d.sent_as}</td>
                <td className="mono">{d.identifiers_removed ?? '–'}</td>
                <td className="mono">{d.leaks === 0 ? <span className="ok-text">0</span> : <strong className="error">{d.leaks}</strong>}</td>
                <td>{!d.error && (
                  <Link className="btn btn-ghost btn-sm" to={`/ai-view/${d.id}`}><Eye size={14} /> {t('security.view', { defaultValue: 'What the AI saw' })}</Link>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
