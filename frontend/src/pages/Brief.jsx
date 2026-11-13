import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getBrief, checkMedicine, answerQuestion } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import { StatusChip, BadgeChip, FlagChip } from '../components/Chip.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import LoadError from '../components/LoadError.jsx';
import { fmtDate } from '../lib/format.js';

export default function Brief() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [b, setB] = useState(null);
  const [drug, setDrug] = useState('');
  const [result, setResult] = useState(null);
  const [src, setSrc] = useState(null);
  const [questions, setQuestions] = useState([]);

  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    getBrief(pid).then((data) => { setB(data); setQuestions(data.open_questions); }).catch((e) => setError(e.message));
  }, [pid]);

  if (error) return <LoadError message={error} />;
  if (!b) return <div className="skeleton" />;

  const onCheck = async (e) => {
    e.preventDefault();
    if (!drug.trim()) return;
    try {
      setResult(await checkMedicine(pid, drug));
    } catch (err) {
      setResult({ warning: false, error: err.message });
    }
  };

  // a doctor's answers to an open question: confirm | correct | unclear (backend/routes/questions.py)
  const resolve = async (q, action) => {
    try {
      await answerQuestion(q.id, action);
      setQuestions(questions.filter((x) => x.id !== q.id));
    } catch (e) {
      window.alert(e.message);
    }
  };

  const allFlagTypes = Object.entries(b.flags).filter(([, list]) => list.length > 0);

  return (
    <div className="brief-layout">
      <section className="brief-main">
        <div className="page-head">
          <div>
            <h1>{t('brief.title')}: {b.patient.name}</h1>
            <p className="muted">{b.patient.sex} · {t('patients.born')} {b.patient.dob} · {t('patients.bloodGroup')} {b.patient.blood_group}</p>
          </div>
        </div>

        <div className="card">
          <h3>{t('brief.checkTitle')}</h3>
          <form className="row" onSubmit={onCheck}>
            <input className="input" placeholder={t('brief.checkPlaceholder')} value={drug} onChange={(e) => setDrug(e.target.value)} aria-label={t('brief.checkTitle')} />
            <button className="btn btn-primary">{t('brief.check')}</button>
          </form>
          {result && (result.warning
            ? <div className="alert alert-danger" role="alert"><p>{result.text}</p>{result.source && <button className="link-btn" onClick={() => setSrc(result.source)}>{t('doc.title')}</button>}</div>
            : <p className="muted small mt">{result.error || t('brief.noMatch')}</p>)}
        </div>

        <div className="card">
          <h3>{t('brief.flags')}</h3>
          {allFlagTypes.length === 0 && <p className="muted">—</p>}
          <div className="chip-row">
            {/* one chip per flag type with how many facts carry it; the Flags page lists them all */}
            {allFlagTypes.map(([type, list]) => (
              <button key={type} className="link-btn" onClick={() => setSrc(list[0].document_id)}>
                <FlagChip flag={type} /> <span className="muted small">× {new Set(list.map((f) => f.fact_id)).size}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>{t('brief.currentMeds')}</h3>
          {b.current_medicines.length === 0 && <p className="muted">—</p>}
          <ul className="list">
            {b.current_medicines.map((m) => {
              const last = m.entries[m.entries.length - 1];
              return (
                <li key={m.name} className="list-row">
                  <div><strong>{m.name}</strong> <span className="mono">{last.dose}</span> <span className="muted">{last.frequency}</span></div>
                  <div className="muted small">
                    {m.last_fresh_evidence_date ? t('brief.lastEvidence') : t('brief.since')} {fmtDate(m.entries[0].date, i18n.language)}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="muted small">{t('translatedNote')}</p>
        </div>

        <div className="card">
          <h3>{t('brief.allergies')}</h3>
          {b.allergies.length === 0 && <div className="chip chip-gap">{t('status.not_documented')}</div>}
          <ul className="list">
            {b.allergies.map((a) => (
              <li key={a.fact_id} className="list-row">
                <div><StatusChip status={a.status} /> <strong>{a.name}</strong></div>
                <button className="link-btn small" onClick={() => setSrc(a.document_id)}>{a.quote}</button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h3>{t('brief.conditions')}</h3>
          <ul className="list">
            {b.conditions.map((c) => (
              <li key={c.fact_id} className="list-row">
                <span>{c.name}</span> <BadgeChip badge={c.badge} />
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h3>{t('brief.latestResults')}</h3>
          <ul className="list">
            {b.latest_results.map((r) => (
              <li key={r.fact_id} className="list-row">
                <span>{r.name}</span>
                <span className="mono">{r.value} {r.unit}</span>
                <span className="muted small">{r.date_raw}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h3>{t('brief.keyEvents')}</h3>
          {(b.key_events || []).length === 0 && <p className="muted">—</p>}
          <ul className="list">
            {(b.key_events || []).map((e) => (
              <li key={e.fact_id || e.name} className="list-row">
                <span>{e.name}</span>
                {e.document_id
                  ? <button className="link-btn small" onClick={() => setSrc(e.document_id)}>{e.date || e.event_date}</button>
                  : <span className="muted small">{e.date || e.event_date}</span>}
              </li>
            ))}
          </ul>
          <h3 className="mt">{t('brief.redFlags')}</h3>
          {(b.red_flags || []).length === 0 && <p className="muted">—</p>}
          <ul className="list">
            {(b.red_flags || []).map((rf, i) => (
              <li key={i} className="list-row brief-redflag"><FlagChip flag={rf.flag} /> <span className="small">{rf.text}</span></li>
            ))}
          </ul>
        </div>
      </section>

      <aside className="brief-side card">
        <h3>{t('brief.openQuestions')} <span className="count-badge">{questions.length}</span></h3>
        {questions.length === 0 && <p className="muted">—</p>}
        {questions.map((q) => (
          <div key={q.id} className="question">
            {q.routed_to === 'doctor' && (
              <span className="chip chip-danger small" title={t('brief.directTip', { defaultValue: 'The agent sent this straight to the doctor instead of asking the patient first.' })}>
                {t('brief.direct', { defaultValue: 'Sent straight to you' })}: {q.route_reason}
              </span>
            )}
            <p>{q.text}</p>
            {q.source && <button className="link-btn small" onClick={() => setSrc(q.source)}>{q.source}</button>}
            <div className="btn-row">
              <button className="btn btn-sm btn-primary" onClick={() => resolve(q, 'confirm')}>{t('brief.confirm')}</button>
              <button className="btn btn-sm btn-ghost" onClick={() => resolve(q, 'correct')}>{t('brief.correct')}</button>
              <button className="btn btn-sm btn-ghost" onClick={() => resolve(q, 'unclear')}>{t('brief.markUnclear')}</button>
            </div>
          </div>
        ))}
      </aside>

      <DocDrawer docId={src} onClose={() => setSrc(null)} />
    </div>
  );
}
