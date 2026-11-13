import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { decideRefill, getRefillReview } from '../api.js';
import { useApp } from '../context/AppContext.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { StatusChip } from '../components/Chip.jsx';
import '../styles/care-team.css';
import '../styles/refills.css';

// Refill review (doctor). Records and checks only: the medicine, the 60-second brief, 30-day
// adherence for this medicine, the latest relevant report with its source, and the allergy /
// duplicate checks re-run now. The app never suggests approving or declining.
// API: backend/routes/refills.py. Every decision creates a consult record.

const CARE_TEAM_SESSION_MS = 12 * 60 * 60 * 1000;

function AdherenceStrip({ days }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="dose-strip" role="img" aria-label={t('refill.stripLabel')}>
        {days.map((d) => {
          const tip = d.due
            ? t('refill.dayTip', { date: d.date, taken: d.taken, due: d.due, skipped: d.skipped })
            : t('refill.dayNone', { date: d.date });
          return (
            <span key={d.date} className="dose-day" title={tip}>
              {d.due > 0
                ? <span className="dose-track"><span className="dose-fill" style={{ height: `${(100 * d.taken) / d.due}%` }} /></span>
                : <span className="dose-none" />}
            </span>
          );
        })}
      </div>
      <div className="strip-axis muted small"><span>{days[0]?.date}</span><span>{days[days.length - 1]?.date}</span></div>
      <table className="sr-only">
        <caption>{t('refill.stripLabel')}</caption>
        <thead><tr><th>{t('refill.date')}</th><th>{t('myMeds.taken')}</th><th>{t('myMeds.skipped')}</th><th>{t('refill.due')}</th></tr></thead>
        <tbody>{days.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.taken}</td><td>{d.skipped}</td><td>{d.due}</td></tr>)}</tbody>
      </table>
    </>
  );
}

function Decision({ review, onDone }) {
  const { t } = useTranslation();
  const [action, setAction] = useState(null);
  const [note, setNote] = useState('');
  const [override, setOverride] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const hasWarnings = review.warnings.length > 0;
  const needsNote = action === 'decline';
  const needsOverride = action === 'approve' && hasWarnings;
  const ready = action && (!needsNote || note.trim()) && (!needsOverride || override.trim());

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      onDone(await decideRefill(review.refill_request.id, action, note.trim(), needsOverride ? override.trim() : null));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card decision-card" onSubmit={submit}>
      <h3>{t('refill.decision')}</h3>
      <div className="btn-row" role="radiogroup" aria-label={t('refill.decision')}>
        {['approve', 'decline', 'visit'].map((a) => (
          <button type="button" key={a} role="radio" aria-checked={action === a}
            className={`answer ${action === a ? 'selected' : ''}`} onClick={() => setAction(a)}>
            {t(`refill.action.${a}`)}
          </button>
        ))}
      </div>
      {action && (
        <>
          <label className="field-label" htmlFor="refill-note">
            {needsNote ? t('refill.noteRequired') : t('refill.noteOptional')}
          </label>
          <textarea id="refill-note" className="input" rows={2} maxLength={1000} value={note}
            placeholder={action === 'visit' ? t('refill.visitDefault') : ''} onChange={(e) => setNote(e.target.value)} />
        </>
      )}
      {needsOverride && (
        <>
          <label className="field-label" htmlFor="refill-override">{t('refill.overrideLabel')}</label>
          <textarea id="refill-override" className="input" rows={2} maxLength={1000} value={override}
            onChange={(e) => setOverride(e.target.value)} />
        </>
      )}
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="btn-row">
        <button className="btn btn-primary" disabled={!ready || busy}>{busy ? t('common.loading') : t('refill.confirm')}</button>
        <span className="muted small">{t('refill.recordNote')}</span>
      </div>
    </form>
  );
}

export default function RefillReview() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { setSession } = useApp();
  const [review, setReview] = useState(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState(null);
  const [src, setSrc] = useState(null); // {doc, line}

  useEffect(() => {
    getRefillReview(id).then((r) => {
      setReview(r);
      // the patient is open for this doctor (care team), so the other screens and sources work
      setSession({ patientId: r.patient_id, expiresAt: Date.now() + CARE_TEAM_SESSION_MS, careTeam: true });
    }).catch((e) => setError(e.message));
  }, [id, setSession]);

  if (error) return <div className="card"><p className="error-text">{error}</p><Link to="/my-patients">{t('refill.back')}</Link></div>;
  if (!review) return <div className="skeleton" />;

  const { medicine: m, adherence_30d: adh, latest_report: rep, brief: b, refill_request: req } = review;
  const decided = done || (req.status !== 'pending' ? { status: req.status, note: req.doctor_note } : null);

  return (
    <section className="refill-review">
      <button className="btn btn-ghost btn-sm" onClick={() => navigate('/my-patients')}><ArrowLeft size={16} /> {t('refill.back')}</button>
      <div className="page-head">
        <h1>{t('refill.title')}</h1>
        {review.patient && <span className="muted">{review.patient.name}</span>}
      </div>
      <p className="records-only small">{t('refill.recordsOnly')}</p>

      <div className="refill-grid">
        <div className="card">
          <h3>{t('refill.medicine')}</h3>
          <p><strong>{m.medicine}</strong> <span className="mono">{m.dose}</span> <span className="muted">{m.frequency}</span></p>
          <dl className="facts-dl small">
            <dt>{t('refill.firstPrescribed')}</dt><dd>{m.first_prescribed_at.slice(0, 10)}</dd>
            <dt>{t('refill.thisPrescription')}</dt><dd>{m.prescribed_at.slice(0, 10)} · {m.doctor}</dd>
            <dt>{t('refill.runsUntil')}</dt><dd>{m.end_date}</dd>
            <dt>{t('refill.requested')}</dt><dd>{req.created_at.slice(0, 16)} UTC</dd>
          </dl>
          {req.patient_note && <p className="doctor-note small">{t('refill.patientNote')}: “{req.patient_note}”</p>}
        </div>

        <div className="card">
          <h3>{t('refill.adherence')}</h3>
          <p className="big-number">{adh.percent == null ? '—' : `${adh.percent}%`}</p>
          <p className="muted small">{t('refill.adherenceCounts', { taken: adh.taken, due: adh.due, skipped: adh.skipped, missed: adh.missed })}</p>
          <AdherenceStrip days={adh.days} />
        </div>

        <div className="card">
          <h3>{t('refill.latestReport')}</h3>
          {!rep && <p className="muted">{t('refill.noReport')}</p>}
          {rep && (
            <>
              <p><strong>{rep.name}</strong> <span className="mono">{rep.value} {rep.unit}</span> <span className="muted small">{rep.date}</span></p>
              <button className="link-btn small" onClick={() => setSrc({ doc: rep.document_id, line: rep.line })}>“{rep.quote}”</button>
            </>
          )}
        </div>

        <div className="card">
          <h3>{t('refill.checks')}</h3>
          {review.warnings.length === 0 && <p className="muted">{t('refill.noWarnings')}</p>}
          {review.warnings.map((w, i) => (
            <div key={i} className="alert alert-danger" role="alert">
              <p>{w.text}</p>
              {w.source?.document_id && <button className="link-btn small" onClick={() => setSrc({ doc: w.source.document_id, line: w.source.line })}>{t('doc.title')}</button>}
            </div>
          ))}
        </div>
      </div>

      <div className="card mt">
        <h3>{t('refill.brief')}</h3>
        <div className="brief-compact">
          <div>
            <h4>{t('brief.currentMeds')}</h4>
            {b.current_medicines.length === 0 && <p className="muted">—</p>}
            <ul className="list">{b.current_medicines.map((x) => {
              const last = x.entries[x.entries.length - 1];
              return <li key={x.name}><strong>{x.name}</strong> <span className="mono">{last.dose}</span> <span className="muted">{last.frequency}</span></li>;
            })}</ul>
          </div>
          <div>
            <h4>{t('brief.allergies')}</h4>
            {b.allergies.length === 0 && <span className="chip chip-gap">{t('status.not_documented')}</span>}
            <ul className="list">{b.allergies.map((a) => (
              <li key={a.fact_id}><StatusChip status={a.status} /> <strong>{a.name}</strong>{' '}
                <button className="link-btn small" onClick={() => setSrc({ doc: a.document_id, line: a.line })}>{a.quote}</button></li>
            ))}</ul>
          </div>
          <div>
            <h4>{t('brief.conditions')}</h4>
            <ul className="list">{b.conditions.map((c) => <li key={c.fact_id}>{c.name}</li>)}</ul>
          </div>
          <div>
            <h4>{t('brief.latestResults')}</h4>
            <ul className="list">{b.latest_results.map((r) => <li key={r.fact_id}>{r.name} <span className="mono">{r.value} {r.unit}</span> <span className="muted small">{r.date_raw}</span></li>)}</ul>
          </div>
          {(b.red_flags || []).length > 0 && (
            <div>
              <h4>{t('brief.redFlags')}</h4>
              <ul className="list">{b.red_flags.map((rf, i) => <li key={i} className="small">{rf.text}</li>)}</ul>
            </div>
          )}
        </div>
      </div>

      {decided
        ? (
          <div className="card mt decision-card">
            <h3>{t(`myMeds.status.${decided.status}`)}</h3>
            {decided.note && <p className="small">{t('refill.noteSent')}: “{decided.note}”</p>}
            {decided.reminders_until && <p className="small">{t('refill.remindersUntil', { date: decided.reminders_until })}</p>}
            <div className="btn-row">
              <button className="btn btn-primary btn-sm" onClick={() => navigate('/my-patients')}>{t('refill.back')}</button>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate('/consult-records')}>{t('consult.title')}</button>
            </div>
          </div>
        )
        : <div className="mt"><Decision review={review} onDone={setDone} /></div>}

      <DocDrawer docId={src?.doc} highlightLine={src?.line} onClose={() => setSrc(null)} />
    </section>
  );
}
