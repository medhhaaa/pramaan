// "App not sure": facts the agent could not prove from the document, even after re-reading and
// asking a stronger model (backend/routes/not_sure.py). A person opens the document and decides.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { HelpCircle } from 'lucide-react';
import { getNotSure, resolveNotSure } from '../api.js';

function describe(f) {
  return [f.name, f.dose, f.frequency, f.value, f.unit].filter(Boolean).join(' ');
}

export default function NotSure({ pid, refreshKey, onChanged, onView }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => { getNotSure(pid).then(setItems).catch(() => setItems([])); }, [pid, refreshKey]);
  if (items.length === 0) return null;

  async function act(id, action) {
    setError('');
    try {
      await resolveNotSure(id, action);
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="card review-card" role="status">
      <h2 className="small"><HelpCircle size={16} /> {t('notSure.title', { defaultValue: 'App not sure' })}</h2>
      <p className="muted small">
        {t('notSure.why', { defaultValue: 'The AI found these, but the app could not find them in the document, even after reading it again. Open the document and decide.' })}
      </p>
      {items.map((i) => (
        <div key={i.id} className="review-doc">
          <div className="btn-row">
            <strong>{i.fact.type}: {describe(i.fact)}</strong>
            <span className="muted small">{i.filename} · {i.reason}</span>
          </div>
          {i.fact.quote && <p className="muted small mono">AI said it read: “{i.fact.quote}”</p>}
          <div className="btn-row">
            <button className="btn btn-ghost btn-sm" onClick={() => onView(i.document_id)}>
              {t('notSure.view', { defaultValue: 'View document' })}
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => act(i.id, 'accept')}>
              {t('notSure.accept', { defaultValue: 'It is there: accept' })}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => act(i.id, 'reject')}>
              {t('notSure.reject', { defaultValue: 'Not in the document: reject' })}
            </button>
          </div>
        </div>
      ))}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}
