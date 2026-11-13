import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMedications } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';
import LoadError from '../components/LoadError.jsx';
import { fmtDate } from '../lib/format.js';

function MedicationInner() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [meds, setMeds] = useState([]);
  const [open, setOpen] = useState({});

  const [error, setError] = useState('');
  useEffect(() => { setError(''); getMedications(pid).then(setMeds).catch((e) => setError(e.message)); }, [pid]);

  const sorted = [...meds].sort((a, b) => Number(b.current) - Number(a.current));

  if (error) return <LoadError message={error} />;

  return (
    <section>
      <div className="page-head"><h1>{t('medication.title')}</h1></div>
      {sorted.length === 0 && <div className="empty-state card"><p>{t('medication.empty')}</p></div>}

      <div className="grid-cards">
        {sorted.map((m) => {
          const mentions = m.entries.length;
          const copies = m.echo_count;
          return (
            <article key={m.name} className={`card med-card ${m.current ? '' : 'is-stopped'}`}>
              <div className="page-head">
                <h2>{m.name}</h2>
                <span className={`chip ${m.current ? 'chip-verified' : 'chip-neutral'}`}>{m.current ? t('medication.current') : t('medication.stopped')}</span>
              </div>
              <p className="muted small">
                {t('medication.summary', {
                  mentions, copies, date: m.last_fresh_evidence_date ? fmtDate(m.last_fresh_evidence_date, i18n.language) : '—',
                })}
              </p>

              <ol className="stepper">
                {m.entries.map((e) => (
                  <li key={e.fact_id} className={`step ${e.echo_of ? 'step-echo' : ''}`}>
                    <div className="step-dot" />
                    <div>
                      <div className="mono">{e.dose} {e.frequency}</div>
                      <div className="muted small">{e.action} · {e.date}</div>
                      {e.echo_of && <div className="small">copy</div>}
                    </div>
                  </li>
                ))}
              </ol>

              <button className="link-btn small" onClick={() => setOpen({ ...open, [m.name]: !open[m.name] })}>
                {open[m.name] ? '−' : '+'} {t('timeline.source')}
              </button>
              {open[m.name] && (
                <table className="table small-table">
                  <tbody>
                    {m.entries.map((e) => (
                      <tr key={e.fact_id}><td>{e.date}</td><td>{e.action}</td><td className="mono">{e.dose}</td><td>{e.document_id}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </article>
          );
        })}
      </div>
      <p className="muted small">{t('translatedNote')}</p>
    </section>
  );
}

export default function Medication() {
  return <PatientGate><MedicationInner /></PatientGate>;
}
