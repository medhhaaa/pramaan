import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle2, AlertTriangle, Loader2, ScanText, Copy } from 'lucide-react';
import { upload } from '../api.js';
import { useActivePatientId, useApp } from '../context/AppContext.jsx';
import { useCachedState } from '../lib/sessionCache.js';
import PatientGate from '../components/PatientGate.jsx';
import { StatusChip, FlagChip } from '../components/Chip.jsx';
import DocDrawer from '../components/DocDrawer.jsx';
import { fmtDate } from '../lib/format.js';

const CONSENT_KEY = 'pramaan_consent_v1';
// what the backend reads: PDFs (digital or scanned) and phone photos of documents
const ACCEPT = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];

// After a page refresh the browser has lost the reply of an upload that was still running: say so
// (the server may still have saved it: the timeline shows what was kept).
const reviveItems = (items) => (Array.isArray(items) ? items : []).map((it) => (
  it.state === 'waiting' || it.state === 'working' ? { ...it, state: 'interrupted' } : it));

// "Metformin · 1000mg BD" or "HbA1c · 8.1 %": doses and values exactly as written
function what(f) {
  const amount = [f.dose, f.frequency].filter(Boolean).join(' ') || [f.value, f.unit].filter(Boolean).join(' ');
  return amount ? `${f.name} · ${amount}` : f.name;
}

function Report({ res }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(null); // {id, line}: the stored copy, opened at its line
  const closeDoc = useCallback(() => setOpen(null), []);
  const added = res.added || [];
  const duplicates = res.duplicates || [];
  const copyOf = res.copy_of_document;
  // "Lab report from 16 Jan 2023 (d5_lab_2023.pdf)": where the other copy is stored
  const docName = (d) => [
    t(`records.types.${d.doc_type}`, { defaultValue: (d.doc_type || '').replace(/_/g, ' ') }),
    d.document_date ? t('upload.fromDate', { date: fmtDate(d.document_date, i18n.language) }) : null,
  ].filter(Boolean).join(' ') + (d.filename ? ` (${d.filename})` : '');
  const leftOut = res.left_out || [];
  const missed = res.not_captured || [];
  const type = (f) => t(`upload.types.${f.type}`, { defaultValue: f.type });

  return (
    <div className="upload-report">
      <p className="chip-row">
        <span className={`chip ${res.read_with === 'ocr' ? 'chip-warn' : 'chip-neutral'}`}>
          <ScanText size={14} />{t(res.read_with === 'ocr' ? 'upload.readOcr' : 'upload.readText')}
        </span>
        <span className="muted small">
          {t('upload.summary', { added: added.length, left: leftOut.length, missed: missed.length })}
        </span>
      </p>
      {copyOf && (
        <p className="report-copy" role="status">
          <Copy size={16} aria-hidden="true" />
          <span>
            {t('upload.copyOf', { doc: docName(copyOf), n: copyOf.matching })}{' '}
            <button type="button" className="link-btn small" onClick={() => setOpen({ id: copyOf.id })}>{t('upload.openStored')}</button>
          </span>
        </p>
      )}
      {res.held_back && (
        <p className="report-held"><AlertTriangle size={16} className="warn-icon" /> {t('upload.heldNote')}
          {res.reasons?.length > 0 && <span className="muted small"> ({res.reasons.join('; ')})</span>}
        </p>
      )}

      <details open className="report-section report-added">
        <summary>{t('upload.added', { n: added.length })}</summary>
        <p className="muted small">{added.length ? t('upload.addedHint') : t('upload.addedNone')}</p>
        <ul className="report-list">
          {added.map((f) => (
            <li key={f.fact_id}>
              <div className="report-line">
                <span className="report-type">{type(f)}</span>
                <strong>{what(f)}</strong>
                {f.status === 'negated' && <StatusChip status="negated" />}
                {(f.flags || []).map((fl) => <FlagChip key={fl} flag={fl} />)}
              </div>
              <q className="report-quote">{f.quote}</q>
              <span className="muted small"> {t('upload.pageLine', { page: f.page, line: f.line })}</span>
            </li>
          ))}
        </ul>
      </details>

      {duplicates.length > 0 && (
        <details open className="report-section report-duplicates">
          <summary>{t('upload.duplicates', { n: duplicates.length })}</summary>
          <p className="muted small">{t('upload.duplicatesHint')}</p>
          <ul className="report-list">
            {duplicates.map((d) => (
              <li key={d.fact_id}>
                <div className="report-line">
                  <span className="report-type">{type(d)}</span>
                  <strong>{what(d)}</strong>
                  <span className="chip chip-neutral">{t(`upload.dupKind.${d.kind}`)}</span>
                </div>
                <p className="small report-stored">
                  {t('upload.storedIn', { doc: docName(d.original), page: d.original.page, line: d.original.line })}
                  {d.other_documents > 1 && <span className="muted"> {t('upload.alsoIn', { count: d.other_documents - 1, n: d.other_documents - 1 })}</span>}
                  {d.original.held_back && <span className="muted"> · {t('upload.heldBackDoc')}</span>}
                  {' '}<button type="button" className="link-btn small" onClick={() => setOpen({ id: d.original.document_id, line: d.original.line })}>{t('upload.openStored')}</button>
                </p>
                {d.original.quote && <q className="report-quote">{d.original.quote}</q>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {leftOut.length > 0 && (
        <details open className="report-section report-left">
          <summary>{t('upload.leftOut', { n: leftOut.length })}</summary>
          <p className="muted small">{t('upload.leftOutHint')}</p>
          <ul className="report-list">
            {leftOut.map((f, i) => (
              <li key={i}>
                <div className="report-line">
                  <span className="report-type">{type(f)}</span>
                  <strong>{what(f)}</strong>
                  <span className="chip chip-neutral">{t(`upload.reasons.${f.reason}`, { defaultValue: f.reason })}</span>
                </div>
                {f.quote && <q className="report-quote">{f.quote}</q>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {missed.length > 0 && (
        <details open className="report-section report-missed">
          <summary>{t('upload.notCaptured', { n: missed.length })}</summary>
          <p className="muted small">{t('upload.notCapturedHint')}</p>
          <ul className="report-list">
            {missed.map((l) => (
              <li key={`${l.page}-${l.line}`}>
                <q className="report-quote">{l.text}</q>
                <span className="muted small"> {t('upload.pageLine', { page: l.page, line: l.line })}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {open && <DocDrawer docId={open.id} highlightLine={open.line} onClose={closeDoc} />}
    </div>
  );
}

function UploadInner() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const pid = useActivePatientId();
  const { user } = useApp();
  const [consented, setConsented] = useState(() => localStorage.getItem(CONSENT_KEY) === 'yes');
  const [ticks, setTicks] = useState([false, false, false]);
  // one per file: {name, state: waiting|working|done|failed|interrupted, res, error}. Cached in the
  // browser (lib/sessionCache.js): the report is still here after you open another page or refresh.
  const [items, setItems] = useCachedState(`upload:${user?.username}:${pid}`, [], reviveItems);
  const busy = items.some((it) => it.state === 'waiting' || it.state === 'working');
  const [dragging, setDragging] = useState(false);

  const acceptConsent = () => {
    localStorage.setItem(CONSENT_KEY, 'yes');
    setConsented(true);
  };

  const update = (i, patch) => setItems((prev) => prev.map((it, j) => (j === i ? { ...it, ...patch } : it)));

  // one file at a time: each takes ~20-40 s (OCR + AI extraction + quote checks)
  const run = async (list) => {
    const files = list.filter((f) => ACCEPT.includes(f.type));
    if (files.length === 0 || busy) return;
    // new files go on top; earlier reports from this session stay below them
    setItems((prev) => [...files.map((f) => ({ name: f.name, state: 'waiting' })), ...prev]);
    for (let i = 0; i < files.length; i += 1) {
      update(i, { state: 'working' });
      try {
        update(i, { state: 'done', res: await upload(pid, files[i]) });
      } catch (e) {
        update(i, { state: 'failed', error: e.message });
      }
    }
  };

  if (!consented) {
    return (
      <section className="card consent">
        <h1>{t('upload.consentTitle')}</h1>
        {[t('upload.consent1'), t('upload.consent2'), t('upload.consent3')].map((label, i) => (
          <label key={i} className="check-row">
            <input type="checkbox" checked={ticks[i]} onChange={(e) => setTicks(ticks.map((v, j) => (j === i ? e.target.checked : v)))} />
            <span>{label}</span>
          </label>
        ))}
        <button className="btn btn-primary" disabled={!ticks.every(Boolean)} onClick={acceptConsent}>{t('upload.continue')}</button>
      </section>
    );
  }

  return (
    <section>
      <div className="page-head"><h1>{t('upload.title')}</h1></div>

      <label
        className={`dropzone ${dragging ? 'dragging' : ''} ${busy ? 'disabled' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); run(Array.from(e.dataTransfer.files)); }}
      >
        <UploadCloud size={36} />
        <span>{t('upload.drop')}</span>
        <span className="btn btn-ghost btn-sm">{t('upload.choose')}</span>
        <input type="file" accept={ACCEPT.join(',')} multiple hidden disabled={busy}
          onChange={(e) => { run(Array.from(e.target.files)); e.target.value = ''; }} />
      </label>

      {items.map((it, i) => (
        <div key={`${it.name}-${i}`} className="card upload-item">
          <h2 className="upload-item-head">
            {it.state === 'working' && <Loader2 size={20} className="spin" />}
            {it.state === 'done' && <CheckCircle2 size={20} className="success-icon" />}
            {it.state === 'failed' && <AlertTriangle size={20} className="warn-icon" />}
            <span>{it.name}</span>
          </h2>
          {it.state === 'waiting' && <p className="muted small">{t('upload.waiting')}</p>}
          {it.state === 'working' && <p className="muted small">{t('upload.working', { name: it.name })}</p>}
          {it.state === 'failed' && <p className="error-text">{t('upload.failed', { error: it.error })}</p>}
          {it.state === 'interrupted' && <p className="muted small">{t('upload.interrupted')}</p>}
          {it.state === 'done' && <Report res={it.res} />}
        </div>
      ))}

      {!busy && items.length > 0 && (
        <div className="btn-row">
          {items.some((it) => it.state === 'done' || it.state === 'interrupted') && (
            <button className="btn btn-primary" onClick={() => navigate('/timeline')}>{t('upload.openTimeline')}</button>
          )}
          <button className="btn btn-ghost" onClick={() => setItems([])}>{t('upload.clearList')}</button>
        </div>
      )}
    </section>
  );
}

export default function Upload() {
  return <PatientGate><UploadInner /></PatientGate>;
}
