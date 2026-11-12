import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import { useActivePatientId } from '../context/AppContext.jsx';
import { getTimeline } from '../api.js';
import { monthsBetween, fmtDate } from '../lib/format.js';
import { useEffect } from 'react';

// Optional module. Shown only when VITE_ENABLE_CLAIM_READY=true. Plain date maths, no AI.
// Rule used: a condition diagnosed up to 36 months before policy start may be treated as pre-existing.
// Check this rule against the policy wording and official sites before the demo.
const PED_MONTHS = 36;

export default function Claim() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [facts, setFacts] = useState([]);
  const [start, setStart] = useState('');
  const [route, setRoute] = useState(null);

  useEffect(() => { if (pid) getTimeline(pid).then(setFacts); }, [pid]);

  if (import.meta.env.VITE_ENABLE_CLAIM_READY !== 'true') return <Navigate to="/" replace />;

  const conditions = facts.filter((f) => f.type === 'condition' && f.event_date);
  const check = (c) => {
    const m = monthsBetween(c.event_date, start);
    if (m < 0) return { c, text: 'Diagnosed after the policy start date.' };
    if (m <= PED_MONTHS) return { c, text: `Recorded about ${m} months before this policy started. It may fall under the waiting period. Check your policy.` };
    return { c, text: `Recorded about ${m} months before this policy started, which is more than ${PED_MONTHS} months.` };
  };

  return (
    <section>
      <div className="page-head"><h1>{t('claim.title')}</h1></div>
      <p className="muted small">{t('claim.caveat')}</p>

      <div className="card">
        <h3>{t('claim.routeTitle')}</h3>
        <div className="chip-row">
          {['pmjay', 'private', 'oop'].map((r) => (
            <button key={r} className={`answer ${route === r ? 'selected' : ''}`} onClick={() => setRoute(r)}>{t(`claim.${r}`)}</button>
          ))}
        </div>
        {route && <p className="muted small mt">{t('claim.verify')}</p>}
      </div>

      <div className="card">
        <h3>{t('claim.pedTitle')}</h3>
        <label className="field-label" htmlFor="start">{t('claim.policyStart')}</label>
        <input id="start" type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
        {start && conditions.map((c) => <p key={c.fact_id} className="mt"><strong>{c.name}</strong> ({fmtDate(c.event_date, i18n.language)}): {check(c).text}</p>)}
      </div>

      <div className="card">
        <h3>{t('claim.deadline')}</h3>
        <h3 className="mt">{t('claim.scamTitle')}</h3>
        <p className="muted small">{t('claim.scam')}</p>
      </div>
    </section>
  );
}
