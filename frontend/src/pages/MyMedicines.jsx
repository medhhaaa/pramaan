import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, X } from 'lucide-react';
import { getMyMedicines, logDose, requestRefill } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import { useAgo } from './MyPatients.jsx';
import '../styles/care-team.css';
import '../styles/refills.css';

// My Medicines (patient): medicines on a Pramaan prescription, today's Taken / Skipped taps,
// and "Request refill". Medicines read from uploaded documents are on the Medication page and
// can't be refilled here. API: backend/routes/refills.py.

const STATUS_CHIP = { pending: 'chip-info', approved: 'chip-verified', declined: 'chip-danger', visit_required: 'chip-warn' };

function RefillBox({ pid, med, onDone }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!med.can_request_refill) {
    if (med.refill_blocked_reason === 'pending') return null; // the status chip already says so
    return <p className="muted small">{t(`myMeds.blocked.${med.refill_blocked_reason}`)}</p>;
  }
  if (!open) return <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>{t('myMeds.requestRefill')}</button>;

  const send = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await requestRefill(pid, med.prescription_item_id, note.trim());
      setOpen(false);
      setNote('');
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={send} className="refill-form">
      <label className="field-label" htmlFor={`note-${med.prescription_item_id}`}>{t('myMeds.noteLabel', { doctor: med.doctor })}</label>
      <textarea id={`note-${med.prescription_item_id}`} className="input" rows={2} maxLength={500} value={note}
        placeholder={t('myMeds.notePlaceholder')} onChange={(e) => setNote(e.target.value)} />
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="btn-row">
        <button className="btn btn-primary btn-sm" disabled={busy}>{busy ? t('common.loading') : t('myMeds.send', { doctor: med.doctor })}</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>{t('careTeam.cancel')}</button>
      </div>
    </form>
  );
}

function Dose({ dose, onTap }) {
  const { t } = useTranslation();
  return (
    <div className="dose-row">
      <span className="mono">{dose.time}</span>
      <div className="btn-row tight" role="group" aria-label={t('myMeds.doseAt', { time: dose.time })}>
        <button className={`answer ${dose.status === 'taken' ? 'selected' : ''}`} aria-pressed={dose.status === 'taken'}
          onClick={() => onTap(dose, 'taken')}><Check size={14} /> {t('myMeds.taken')}</button>
        <button className={`answer ${dose.status === 'skipped' ? 'selected' : ''}`} aria-pressed={dose.status === 'skipped'}
          onClick={() => onTap(dose, 'skipped')}><X size={14} /> {t('myMeds.skipped')}</button>
      </div>
    </div>
  );
}

export default function MyMedicines({ embedded = false }) {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const ago = useAgo();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (!pid) return;
    getMyMedicines(pid).then((d) => { setData(d); setError(''); }).catch((e) => setError(e.message));
  }, [pid]);
  useEffect(load, [load]);

  const tap = async (dose, status) => {
    try {
      await logDose(dose.reminder_id, status);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (error && !data) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!data) return <div className="skeleton" />;

  return (
    <section className="my-medicines">
      {!embedded && <div className="page-head"><h1>{t('myMeds.title')}</h1></div>}
      <p className="muted small">{t('myMeds.intro')}</p>
      {error && <p className="error-text" role="alert">{error}</p>}
      {data.medicines.length === 0 && <div className="empty-state card"><p>{t('myMeds.empty')}</p></div>}

      <ul className="list patient-rows">
        {data.medicines.map((m) => {
          const last = m.last_refill_request;
          return (
            <li key={m.prescription_item_id} className="card med-card">
              <div className="team-row">
                <div>
                  <strong>{m.medicine}</strong> <span className="mono">{m.dose}</span> <span className="muted">{m.frequency}</span>
                  <div className="muted small">{t('myMeds.from', { doctor: m.doctor })} · {t('myMeds.until', { date: m.end_date })}</div>
                  {m.adherence_14d != null && <div className="muted small">{t('myMeds.adherence', { percent: m.adherence_14d })}</div>}
                </div>
                {last && (
                  <span className={`chip ${STATUS_CHIP[last.status]}`}>
                    {t(`myMeds.status.${last.status}`)} · {ago(last.decided_at || last.created_at)}
                  </span>
                )}
              </div>
              {last && last.doctor_note && last.status !== 'pending' && (
                <p className="doctor-note small">{t('myMeds.doctorNote')}: “{last.doctor_note}”</p>
              )}

              {m.today.length > 0 && (
                <div className="mt">
                  <h3 className="small-heading">{t('myMeds.today')}</h3>
                  {m.today.map((d) => <Dose key={d.reminder_id} dose={d} onTap={tap} />)}
                </div>
              )}
              <div className="mt"><RefillBox pid={pid} med={m} onDone={load} /></div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
