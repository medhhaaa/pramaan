// "What the AI saw": one document's original text next to the exact de-identified text the
// pipeline sends to the AI, with removed parts highlighted. Handwritten pages also show the
// blacked-out picture that went to the vision model. (backend/routes/security.py)
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { getAiView } from '../api.js';
import LoadError from '../components/LoadError.jsx';

// split a line into plain parts and highlighted parts (the given strings)
function highlight(text, parts, cls) {
  const wanted = parts.filter(Boolean).sort((a, b) => b.length - a.length);
  if (!wanted.length || !text) return text;
  const pattern = new RegExp(`(${wanted.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g');
  return text.split(pattern).map((p, i) => (wanted.includes(p) ? <mark key={i} className={cls}>{p}</mark> : p));
}

export default function AiView() {
  const { t } = useTranslation();
  const { docId } = useParams();
  const [v, setV] = useState(null);
  const [error, setError] = useState('');
  const [onlyChanged, setOnlyChanged] = useState(false);

  useEffect(() => { getAiView(docId).then(setV).catch((e) => setError(e.message)); }, [docId]);
  if (error) return <LoadError message={error} />;
  if (!v) return <div className="skeleton" />;

  const originals = v.removed.map((r) => r.original);
  const tokens = v.removed.map((r) => r.token);
  const rows = onlyChanged ? v.lines.filter((l) => l.changed) : v.lines;

  return (
    <section className="ai-view">
      <div className="page-head">
        <div>
          <Link to="/security" className="link-btn small"><ArrowLeft size={14} /> {t('aiView.back', { defaultValue: 'Back to the scorecard' })}</Link>
          <h1>{t('aiView.title', { defaultValue: 'What the AI saw' })}: {v.filename}</h1>
          <p className="muted small">
            {t('aiView.note', { defaultValue: 'Left: the document as stored. Right: exactly what the pipeline sends to the AI (the de-identification step is run again on the stored document and gives the same output). Highlighted: what was removed and what replaced it.' })}
          </p>
        </div>
        <label className="toggle"><input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
          {t('aiView.onlyChanged', { defaultValue: 'Only changed lines' })}</label>
      </div>

      <div className="stat-row">
        <div className="card stat"><span className="muted">{t('aiView.removed', { defaultValue: 'Identifiers removed' })}</span><strong>{v.removed.length}</strong></div>
        <div className="card stat"><span className="muted">{t('aiView.left', { defaultValue: 'Identifiers left in AI text' })}</span>
          <strong className={v.leaks.length ? 'error' : 'ok-text'}>{v.leaks.length}</strong></div>
        <div className="card stat"><span className="muted">{t('aiView.images', { defaultValue: 'Pages sent as pictures' })}</span><strong>{v.images.length}</strong></div>
      </div>

      {v.leaks.length > 0 && <p className="error">{t('aiView.leaks', { defaultValue: 'Still visible to the AI' })}: {v.leaks.join(', ')}</p>}
      {v.unread_pages.length > 0 && (
        <p className="warn">{t('aiView.unread', { defaultValue: 'Handwritten page(s) kept back, never sent to any AI' })}: {v.unread_pages.join(', ')}</p>
      )}

      {v.images.map((img) => (
        <div key={img.page} className="card">
          <h3>{t('aiView.page', { defaultValue: 'Page' })} {img.page}: {t('aiView.picture', { defaultValue: 'picture sent to the vision model' })}</h3>
          <div className="ai-compare">
            <figure><figcaption className="muted small">{t('aiView.original', { defaultValue: 'Original' })}</figcaption>
              <img src={`data:image/png;base64,${img.original_png}`} alt="original page" /></figure>
            <figure><figcaption className="muted small">{t('aiView.sent', { defaultValue: 'Sent to the AI' })}</figcaption>
              {img.masked_png
                ? <img src={`data:image/png;base64,${img.masked_png}`} alt="page with personal details blacked out" />
                : <p className="muted">{t('aiView.notSent', { defaultValue: 'Not sent: no name label to black out.' })}</p>}</figure>
          </div>
          {img.leaks.length > 0 && <p className="error small">{img.leaks.join(', ')}</p>}
        </div>
      ))}

      <div className="card table-wrap">
        <table className="table ai-table">
          <thead>
            <tr>
              <th className="mono">{t('aiView.line', { defaultValue: 'p · line' })}</th>
              <th>{t('aiView.original', { defaultValue: 'Original' })}</th>
              <th>{t('aiView.sent', { defaultValue: 'Sent to the AI' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={`${l.page}-${l.line}`} className={l.changed ? 'ai-changed' : ''}>
                <td className="mono muted small">{l.page} · {l.line}</td>
                <td>{l.changed ? highlight(l.original, originals, 'ai-removed') : l.original}</td>
                <td className="mono">{l.changed ? highlight(l.sent, tokens, 'ai-token') : l.sent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
