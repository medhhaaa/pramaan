import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText } from 'lucide-react';
import { listDocuments } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { fmtDate } from '../lib/format.js';
import { useInPageSearch, useFlip } from '../lib/inPageSearch.js';
import { SearchBar, Highlight, ReasonChip, RelatedHeading } from '../components/InPageSearch.jsx';

// Records (doctor): the patient's documents, newest first, with click-to-proof. The search bar
// moves related documents to the top; nothing is hidden and nothing is changed.
function RecordsInner() {
  const { t, i18n } = useTranslation();
  const pid = useActivePatientId();
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null); // {id, line}
  const { query, setQuery, results, busy } = useInPageSearch(pid, 'records');
  const listRef = useRef(null);
  const closeDoc = useCallback(() => setOpen(null), []);

  useEffect(() => { listDocuments(pid).then(setDocs).catch((e) => setError(e.message)); }, [pid]);

  const nameOf = useMemo(() => new Map((docs || []).map((d) => [d.id, d.filename])), [docs]);
  const searching = Boolean(results && query.trim());
  const scored = (docs || []).map((d) => ({ d, r: searching ? results.byId.get(d.id) || null : null }));
  const related = scored.filter((x) => x.r).sort((a, b) => b.r.score - a.r.score);
  const others = scored.filter((x) => !x.r);
  useFlip(listRef, [...related, ...others].map((x) => x.d.id).join('|'));

  if (error) return <div className="card"><p className="error-text">{error}</p></div>;
  if (!docs) return <div className="skeleton" />;

  const typeLabel = (type) => t(`records.types.${type}`, { defaultValue: (type || '').replace(/_/g, ' ') });

  const card = ({ d, r }) => (
    <li key={d.id} data-flip={d.id} className={`card record-card ${r ? 'ips-match' : ''}`}>
      <div className="record-head">
        <FileText size={20} aria-hidden="true" />
        <div className="record-title">
          <strong>{typeLabel(d.doc_type)}</strong>
          <span className="muted small">{d.document_date ? fmtDate(d.document_date, i18n.language) : t('records.noDate')}</span>
        </div>
        <div className="chip-row">
          <span className="chip chip-neutral">{t('records.facts', { count: d.facts })}</span>
          {d.held_back && <span className="chip chip-danger">{t('doc.held')}</span>}
        </div>
      </div>
      <p className="muted small record-file"><Highlight text={d.filename} terms={r?.matched_terms} /></p>
      {r && (
        <div className="ips-why">
          <ReasonChip result={r} viaLabel={nameOf.get(r.via) || r.via} />
          {r.source && <q className="ips-source"><Highlight text={r.source.text} terms={r.matched_terms} /></q>}
        </div>
      )}
      <button className="link-btn small" onClick={() => setOpen({ id: d.id, line: r?.source?.line })}>{t('records.open')}</button>
    </li>
  );

  return (
    <section>
      <div className="page-head">
        <h1>{t('records.title')}</h1>
        <span className="muted">{t('records.count', { count: docs.length })}</span>
      </div>
      {docs.length > 0 && (
        <SearchBar value={query} onChange={setQuery} busy={busy} results={results} placeholder={t('search.placeholderRecords')} />
      )}
      {docs.length === 0 && <div className="empty-state card"><p>{t('records.empty')}</p></div>}

      <div ref={listRef}>
        {searching && related.length > 0 && <RelatedHeading q={results.q} n={related.length} />}
        {related.length > 0 && <ul className="list record-list">{related.map(card)}</ul>}
        {searching && related.length > 0 && others.length > 0 && <h2 className="ips-section-title muted">{t('search.other')}</h2>}
        <ul className={`list record-list ${searching && related.length > 0 ? 'ips-dim' : ''}`}>{others.map(card)}</ul>
      </div>

      {open && <DocDrawer docId={open.id} highlightLine={open.line} onClose={closeDoc} />}
    </section>
  );
}

export default function Records() {
  return <PatientGate><RecordsInner /></PatientGate>;
}
