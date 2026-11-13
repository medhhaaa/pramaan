import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { getDocument } from '../api.js';

// Click-to-proof. Shows the source lines and highlights the quoted line.
// When the backend returns pdf_base64, render it with react-pdf here (see README note).
export default function DocDrawer({ docId, highlightLine, onClose }) {
  const { t } = useTranslation();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState('');
  // parents pass a new onClose function on every render; keep the latest one in a ref so the
  // effect below runs only when the document changes (it used to refetch on every render)
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    if (!docId) return undefined;
    let alive = true;
    setDoc(null); // don't keep showing the previous document while the next one loads
    setError('');
    getDocument(docId)
      .then((d) => { if (alive) setDoc(d); })
      .catch((e) => { if (alive) setError(e.message); });
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current(); };
    window.addEventListener('keydown', onKey);
    return () => { alive = false; window.removeEventListener('keydown', onKey); };
  }, [docId]);

  if (!docId) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label={t('doc.title')} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{doc ? doc.filename : error ? t('common.error') : t('common.loading')}</h2>
            {error && <p className="muted small mono" role="alert">{error}</p>}
            {doc && <p className="muted small">{doc.doc_type} · {doc.document_date}</p>}
            {doc && doc.held_back && <span className="chip chip-danger">{t('doc.held')}</span>}
          </div>
          <button className="icon-btn" aria-label={t('doc.close')} onClick={onClose}><X size={20} /></button>
        </div>
        <div className="doc-lines">
          {doc && doc.lines.map((l) => (
            <div key={`${l.page}-${l.line}`} className={`doc-line ${l.line === highlightLine ? 'hit' : ''}`}>
              <span className="line-no">p{l.page} · l{l.line}</span>
              <span>{l.text}</span>
            </div>
          ))}
          {doc && doc.lines.length === 0 && <p className="muted">—</p>}
        </div>
      </aside>
    </div>
  );
}
