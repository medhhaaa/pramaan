import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, EyeOff, FileText, Loader2 } from 'lucide-react';
import { diseaseSearch } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { Highlight } from '../components/InPageSearch.jsx';
import { fmtDate } from '../lib/format.js';
import '../styles/disease-search.css';

const EXAMPLES = ['diabetes', 'high blood pressure', 'heart attack', 'kidney disease', 'thyroid', 'asthma'];
const SECTIONS = ['conditions', 'medicines', 'labs', 'events'];

// Disease search (doctor): everything in this patient's records about one disease, found by its
// name, a synonym ("sugar"), a medicine ("Glycomet") or a lab test ("HbA1c"). Every row opens its
// source line. Only what the patient shared; hidden items are a count, never named.
function DiseaseSearchInner() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [q, setQ] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null); // {id, line}
  const closeDoc = useCallback(() => setOpen(null), []);

  const run = async (query) => {
    const text = query.trim();
    if (!text) return;
    setQ(text);
    setBusy(true);
    setError('');
    try { setResult(await diseaseSearch(pid, text)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const total = result ? SECTIONS.reduce((n, s) => n + result[s].length, 0) : 0;
  const what = (item) => [item.dose, item.frequency, item.value && `${item.value}${item.unit ? ` ${item.unit}` : ''}`]
    .filter(Boolean).join(' · ');

  return (
    <section className="disease-page">
      <div className="page-head"><h1>{t('disease.title')}</h1></div>
      <p className="muted disease-intro">{t('disease.intro')}</p>

      <form className="ips-bar" role="search" onSubmit={(e) => { e.preventDefault(); run(q); }}>
        <div className="search ips-input">
          {busy ? <Loader2 size={18} className="spin" aria-hidden="true" /> : <Search size={18} aria-hidden="true" />}
          <input className="input" type="search" value={q} maxLength={100} placeholder={t('disease.placeholder')}
            aria-label={t('disease.placeholder')} onChange={(e) => setQ(e.target.value)} />
          <button className="btn btn-primary btn-sm" disabled={busy || !q.trim()}>{t('disease.search')}</button>
        </div>
      </form>
      <div className="chip-row disease-examples" aria-label={t('disease.examples')}>
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" className="chip chip-neutral" onClick={() => run(ex)}>{ex}</button>
        ))}
      </div>
      {error && <p className="error-text">{error}</p>}

      {result && !busy && (
        <div className="disease-result" aria-live="polite">
          {!result.disease ? (
            <div className="empty-state card"><p>{t('disease.unknown', { q: result.query })}</p></div>
          ) : (
            <>
              <h2 className="disease-heading">
                {result.label}
                <span className="muted small">{t(`disease.via.${result.matched_by}`, { q: result.query })}</span>
              </h2>
              {result.hidden_count > 0 && (
                <p className="disease-hidden" role="status"><EyeOff size={16} aria-hidden="true" /> {t('disease.hidden', { count: result.hidden_count })}</p>
              )}
              {total === 0 && <div className="empty-state card"><p>{t('disease.nothing', { label: result.label })}</p></div>}

              <div className="disease-grid">
                {SECTIONS.filter((s) => result[s].length > 0).map((s) => (
                  <div key={s} className="card disease-section">
                    <h3>{t(`disease.sections.${s}`)} <span className="muted small">({result[s].length})</span></h3>
                    <ul className="list">
                      {result[s].map((item) => (
                        <li key={item.fact_id} className="disease-item">
                          <div className="disease-item-main">
                            <strong><Highlight text={item.name} terms={result.matched_terms} /></strong>
                            {what(item) && <span className="mono small">{what(item)}</span>}
                            <span className="chip-row">
                              {item.status === 'negated' && <span className="chip chip-neutral">{t('disease.negated')}</span>}
                              {item.echo_of && <span className="chip chip-neutral">{t('disease.copy')}</span>}
                              {(item.flags || []).filter((f) => f !== 'handwriting').map((f) => (
                                <span key={f} className="chip chip-danger">{t(`flagNames.${f}`, { defaultValue: f.replace(/_/g, ' ') })}</span>
                              ))}
                            </span>
                          </div>
                          <div className="disease-item-meta muted small">
                            <span>{item.event_date ? fmtDate(item.event_date, i18n.language) : t('records.noDate')}</span>
                            {item.document_id && (
                              <button className="link-btn small" onClick={() => setOpen({ id: item.document_id, line: item.line })}>
                                {t('disease.source')}
                              </button>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              {result.documents.length > 0 && (
                <div className="card disease-section">
                  <h3>{t('disease.sections.documents')} <span className="muted small">({result.documents.length})</span></h3>
                  <ul className="list">
                    {result.documents.map((d) => (
                      <li key={d.id} className="disease-item">
                        <div className="disease-item-main">
                          <FileText size={16} aria-hidden="true" />
                          <span>{t(`records.types.${d.doc_type}`, { defaultValue: (d.doc_type || '').replace(/_/g, ' ') })}</span>
                          <span className="muted small">{d.document_date ? fmtDate(d.document_date, i18n.language) : t('records.noDate')}</span>
                        </div>
                        <button className="link-btn small" onClick={() => setOpen({ id: d.id })}>{t('records.open')}</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {open && <DocDrawer docId={open.id} highlightLine={open.line} onClose={closeDoc} />}
    </section>
  );
}

export default function DiseaseSearch() {
  return <PatientGate><DiseaseSearchInner /></PatientGate>;
}
