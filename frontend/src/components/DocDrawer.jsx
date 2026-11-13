import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, ExternalLink, X, ZoomIn, ZoomOut } from 'lucide-react';
import { getDocument, getDocumentOriginal } from '../api.js';
import AgentSteps from './AgentSteps.jsx';
import '../styles/doc-photo.css';

// The photo a patient uploaded (a handwritten prescription, a phone picture of a report), shown
// above the typed reading so a doctor can check each line against it. The selected line is
// boxed on the photo (line.box: fractions of the photo, from GET /documents/{id}).
function OriginalPhoto({ docId, name, box }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    let alive = true;
    let made = null;
    setUrl(null);
    setFailed(false);
    getDocumentOriginal(docId)
      .then((blob) => { if (alive) { made = URL.createObjectURL(blob); setUrl(made); } })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; if (made) URL.revokeObjectURL(made); };
  }, [docId]);

  // the marked line stays in view when zoomed in or when another line is picked
  useEffect(() => { boxRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' }); }, [box, zoomed, url]);

  const pad = 0.006; // a little room around the handwriting
  return (
    <figure className="doc-photo">
      <figcaption className="doc-photo-head">
        <span className="doc-photo-title"><Camera size={16} aria-hidden="true" /> {t('doc.photoTitle')}</span>
        {url && (
          <span className="doc-photo-tools">
            <button type="button" className="icon-btn" onClick={() => setZoomed((z) => !z)}
              aria-pressed={zoomed} aria-label={t(zoomed ? 'doc.zoomOut' : 'doc.zoomIn')} title={t(zoomed ? 'doc.zoomOut' : 'doc.zoomIn')}>
              {zoomed ? <ZoomOut size={16} /> : <ZoomIn size={16} />}
            </button>
            <a className="icon-btn" href={url} target="_blank" rel="noreferrer" aria-label={t('doc.openFull')} title={t('doc.openFull')}>
              <ExternalLink size={16} />
            </a>
          </span>
        )}
      </figcaption>
      <div className={`doc-photo-frame ${zoomed ? 'zoomed' : ''}`}>
        {failed && <p className="muted small doc-photo-msg">{t('doc.photoError')}</p>}
        {!url && !failed && <div className="skeleton doc-photo-loading" />}
        {url && (
          <div className="doc-photo-canvas">
            <img src={url} alt={t('doc.photoAlt', { name })} />
            {box && (
              <span ref={boxRef} className="doc-photo-box" aria-hidden="true" style={{
                left: `${Math.max(0, box[0] - pad) * 100}%`, top: `${Math.max(0, box[1] - pad) * 100}%`,
                width: `${(Math.min(1, box[2] + pad) - Math.max(0, box[0] - pad)) * 100}%`,
                height: `${(Math.min(1, box[3] + pad) - Math.max(0, box[1] - pad)) * 100}%`,
              }} />
            )}
          </div>
        )}
      </div>
      <p className="muted small">{t('doc.photoHint')}</p>
    </figure>
  );
}

// Click-to-proof. Shows the source lines and highlights the quoted line; for a photo upload,
// the photo itself on top with that line boxed. Pick another line to box it instead.
export default function DocDrawer({ docId, highlightLine, onClose }) {
  const { t } = useTranslation();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState('');
  const [picked, setPicked] = useState(null); // line the reader clicked; null = the quoted line
  // parents pass a new onClose function on every render; keep the latest one in a ref so the
  // effect below runs only when the document changes (it used to refetch on every render)
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    if (!docId) return undefined;
    let alive = true;
    setDoc(null); // don't keep showing the previous document while the next one loads
    setError('');
    setPicked(null);
    getDocument(docId)
      .then((d) => { if (alive) setDoc(d); })
      .catch((e) => { if (alive) setError(e.message); });
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current(); };
    window.addEventListener('keydown', onKey);
    return () => { alive = false; window.removeEventListener('keydown', onKey); };
  }, [docId]);

  if (!docId) return null;

  const current = picked ?? highlightLine;
  const photo = Boolean(doc?.original);
  const marked = photo ? doc.lines.find((l) => l.line === current && l.box) : null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className={`drawer ${photo ? 'drawer-wide' : ''}`} role="dialog" aria-label={t('doc.title')} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{doc ? doc.filename : error ? t('common.error') : t('common.loading')}</h2>
            {error && <p className="muted small mono" role="alert">{error}</p>}
            {doc && <p className="muted small">{doc.doc_type} · {doc.document_date}</p>}
            {doc && doc.held_back && <span className="chip chip-danger">{t('doc.held')}</span>}
          </div>
          <button className="icon-btn" aria-label={t('doc.close')} onClick={onClose}><X size={20} /></button>
        </div>
        {photo && <OriginalPhoto docId={docId} name={doc.filename} box={marked?.box} />}
        {doc && <AgentSteps docId={docId} />}
        {photo && <h3 className="doc-reading-title">{t('doc.reading')}</h3>}
        <div className="doc-lines">
          {doc && doc.lines.map((l) => {
            const cls = `doc-line ${l.line === current ? 'hit' : ''}`;
            const body = (
              <>
                <span className="line-no">p{l.page} · l{l.line}</span>
                <span>{l.text}</span>
              </>
            );
            // on a photo, a line that could be placed is a button: it moves the box
            return photo && l.box ? (
              <button key={`${l.page}-${l.line}`} type="button" className={`${cls} doc-line-pick`}
                aria-pressed={l.line === current} onClick={() => setPicked(l.line)}>{body}</button>
            ) : (
              <div key={`${l.page}-${l.line}`} className={cls}>{body}</div>
            );
          })}
          {doc && doc.lines.length === 0 && <p className="muted">—</p>}
        </div>
      </aside>
    </div>
  );
}
