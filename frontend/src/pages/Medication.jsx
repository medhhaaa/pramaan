import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMedications } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';
import { fmtDate } from '../lib/format.js';
import { useInPageSearch, useFlip } from '../lib/inPageSearch.js';
import { SearchBar, Highlight, ReasonChip, RelatedHeading } from '../components/InPageSearch.jsx';

// a medicine card's search result = its best-scoring entry (each entry is one medication fact)
function bestResult(m, byId) {
  let best = null;
  const terms = new Set();
  m.entries.forEach((e) => {
    const r = byId.get(e.fact_id);
    if (!r) return;
    r.matched_terms.forEach((w) => terms.add(w));
    if (!best || r.score > best.score) best = r;
  });
  return best && { ...best, matched_terms: [...terms] };
}

function MedicationInner() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [meds, setMeds] = useState([]);
  const [open, setOpen] = useState({});

  const { query, setQuery, results, busy } = useInPageSearch(pid, 'medications');
  const listRef = useRef(null);

  useEffect(() => { getMedications(pid).then(setMeds); }, [pid]);

  const sorted = [...meds].sort((a, b) => Number(b.current) - Number(a.current));
  // fact_id -> medicine name, for "Same visit as Augmentin"
  const nameOfFact = useMemo(() => new Map(meds.flatMap((m) => m.entries.map((e) => [e.fact_id, m.name]))), [meds]);

  // with a query: matching cards first (best score first), the rest below in normal order
  const searching = Boolean(results && query.trim());
  const scored = searching ? sorted.map((m) => ({ m, r: bestResult(m, results.byId) })) : sorted.map((m) => ({ m, r: null }));
  const related = scored.filter((x) => x.r).sort((a, b) => b.r.score - a.r.score);
  const others = scored.filter((x) => !x.r);
  useFlip(listRef, [...related, ...others].map((x) => x.m.name).join('|'));

  const card = ({ m, r }) => {
    const mentions = m.entries.length;
    const copies = m.echo_count;
    return (
            <article key={m.name} data-flip={m.name} className={`card med-card ${m.current ? '' : 'is-stopped'} ${r ? 'ips-match' : ''}`}>
              <div className="page-head">
                <h2><Highlight text={m.name} terms={r?.matched_terms} /></h2>
                <span className={`chip ${m.current ? 'chip-verified' : 'chip-neutral'}`}>{m.current ? t('medication.current') : t('medication.stopped')}</span>
              </div>
              {r && (
                <div className="ips-why">
                  <ReasonChip result={r} viaLabel={nameOfFact.get(r.via) || r.via} />
                  {r.source && <q className="ips-source"><Highlight text={r.source.text} terms={r.matched_terms} /></q>}
                </div>
              )}
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
  };

  return (
    <section>
      <div className="page-head"><h1>{t('medication.title')}</h1></div>
      {meds.length > 0 && (
        <SearchBar value={query} onChange={setQuery} busy={busy} results={results} placeholder={t('search.placeholderMeds')} />
      )}
      {sorted.length === 0 && <div className="empty-state card"><p>{t('medication.empty')}</p></div>}

      <div ref={listRef}>
        {searching && related.length > 0 && <RelatedHeading q={results.q} n={related.length} />}
        {related.length > 0 && <div className="grid-cards">{related.map(card)}</div>}
        {searching && related.length > 0 && others.length > 0 && <h2 className="ips-section-title muted">{t('search.other')}</h2>}
        <div className={`grid-cards ${searching && related.length > 0 ? 'ips-dim' : ''}`}>{others.map(card)}</div>
      </div>
      <p className="muted small">{t('translatedNote')}</p>
    </section>
  );
}

export default function Medication() {
  return <PatientGate><MedicationInner /></PatientGate>;
}
