import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getBrief, checkMedicine, correctFact, answerQuestion } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import { StatusChip, BadgeChip, FlagChip } from '../components/Chip.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { fmtDate } from '../lib/format.js';

export default function Brief() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [b, setB] = useState(null);
  const [drug, setDrug] = useState('');
  const [result, setResult] = useState(null);
  const [src, setSrc] = useState(null);
  const [questions, setQuestions] = useState([]);

  useEffect(() => {
    getBrief(pid).then((data) => { setB(data); setQuestions(data.open_questions); });
  }, [pid]);

  if (!b) return <div className="skeleton" />;

  const onCheck = async (e) => {
    e.preventDefault();
    if (!drug.trim()) return;
    setResult(await checkMedicine(pid, drug));
  };

  const resolve = async (q, action) => {
    if (action === 'confirm') await correctFact(q.fact_ids[0], 'doctor_verified', true);
    await answerQuestion(q.id, action === 'unclear' ? 'dont_know' : 'yes');
    setQuestions(questions.filter((x) => x.id !== q.id));
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
            ? <div className="alert alert-danger" role="alert"><p>{result.text}</p><button className="link-btn" onClick={() => setSrc(result.source)}>{t('doc.title')}</button></div>
            : <p className="muted small mt">{t('brief.noMatch')}</p>)}
        </div>

        <div className="card">
          <h3>{t('brief.flags')}</h3>
          {allFlagTypes.length === 0 && <p className="muted">—</p>}
          <div className="chip-row">
            {allFlagTypes.map(([type, list]) => list.map((f) => (
              <button key={f.fact_id} className="link-btn" onClick={() => setSrc(f.document_id)}>
                <FlagChip flag={type} />
              </button>
            )))}
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
                  <div className="muted small">{t('brief.since')} {fmtDate(m.entries[0].date, i18n.language)}</div>
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
          <p className="muted">—</p>
          <h3 className="mt">{t('brief.redFlags')}</h3>
          <p className="muted">—</p>
        </div>
      </section>

      <aside className="brief-side card">
        <h3>{t('brief.openQuestions')} <span className="count-badge">{questions.length}</span></h3>
        {questions.length === 0 && <p className="muted">—</p>}
        {questions.map((q) => (
          <div key={q.id} className="question">
            <p>{q.text}</p>
            <button className="link-btn small" onClick={() => setSrc(q.source)}>{q.source}</button>
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
