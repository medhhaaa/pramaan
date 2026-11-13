// Reviewing facts read from handwriting.
//   Unsure         shows a value with the reader's best-guess words highlighted
//   EditFact       inline correction for a fact (the original is kept by the backend)
//   NeedsReading   handwritten pages no AI was allowed to read: view the image, type medicines in
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { addFactFromImage, correctFact, getNeedsReading, markDocumentRead } from '../api.js';

export function Unsure({ text, words }) {
  if (!text || !words || words.length === 0) return text || null;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return text.split(pattern).map((part, i) =>
    words.some((w) => w.toLowerCase() === part.toLowerCase())
      ? <mark key={i} className="unsure" title="Best guess: check against the image">{part}</mark>
      : part,
  );
}

const EDITABLE = ['name', 'dose', 'frequency', 'value', 'unit'];

export function EditFact({ fact, low, onSaved }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [field, setField] = useState(fact.type === 'medication' ? 'dose' : 'name');
  const [value, setValue] = useState('');
  const [error, setError] = useState('');

  useEffect(() => { setValue(fact[field] ?? ''); }, [field, fact]);

  async function save(e) {
    e.preventDefault();
    setError('');
    try {
      await correctFact(fact.fact_id, field, value.trim());
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!open) {
    return (
      <button className={`btn btn-sm ${low ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setOpen(true)}
              title={t('review.editTip', { defaultValue: 'Correct what was read. The original reading is kept.' })}>
        {t('review.edit', { defaultValue: 'Edit' })}
      </button>
    );
  }
  return (
    <form className="edit-form" onSubmit={save}>
      <select value={field} onChange={(e) => setField(e.target.value)}>
        {EDITABLE.filter((k) => fact.type === 'medication' || !['dose', 'frequency'].includes(k)).map((k) => (
          <option key={k} value={k}>{k}</option>
        ))}
      </select>
      <input value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
      <button type="submit" className="btn btn-primary btn-sm">{t('review.save', { defaultValue: 'Save' })}</button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        {t('review.cancel', { defaultValue: 'Cancel' })}
      </button>
      {error && <span className="error small">{error}</span>}
    </form>
  );
}

function AddMedicine({ docId, onAdded }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ name: '', dose: '', frequency: '' });
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function add(e) {
    e.preventDefault();
    setError('');
    try {
      await addFactFromImage(docId, { type: 'medication', ...form });
      setForm({ name: '', dose: '', frequency: '' });
      onAdded();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <form className="edit-form" onSubmit={add}>
      <input placeholder={t('review.medicine', { defaultValue: 'Medicine' })} value={form.name} onChange={set('name')} required />
      <input placeholder={t('review.dose', { defaultValue: 'Dose (e.g. 500mg)' })} value={form.dose} onChange={set('dose')} />
      <input placeholder={t('review.frequency', { defaultValue: 'How often (e.g. BD)' })} value={form.frequency} onChange={set('frequency')} />
      <button type="submit" className="btn btn-primary btn-sm">{t('review.add', { defaultValue: 'Add medicine' })}</button>
      {error && <span className="error small">{error}</span>}
    </form>
  );
}

export function NeedsReading({ pid, refreshKey, onChanged, onView }) {
  const { t } = useTranslation();
  const [docs, setDocs] = useState([]);

  useEffect(() => { getNeedsReading(pid).then(setDocs).catch(() => setDocs([])); }, [pid, refreshKey]);
  if (docs.length === 0) return null;

  return (
    <div className="card review-card" role="status">
      <h2 className="small">{t('review.title', { defaultValue: 'Handwritten pages to read' })}</h2>
      <p className="muted small">
        {t('review.why', { defaultValue: 'No name label was found on these pages, so the patient\'s details could not be hidden. They were not sent to any AI. Open the image and type in the medicines.' })}
      </p>
      {docs.map((d) => (
        <div key={d.id} className="review-doc">
          <div className="btn-row">
            <strong>{d.filename}</strong>
            <span className="muted small">{d.facts_added} {t('review.added', { defaultValue: 'added so far' })}</span>
            <button className="btn btn-ghost btn-sm" onClick={() => onView(d.id)}>{t('review.view', { defaultValue: 'View image' })}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => markDocumentRead(d.id).then(onChanged)}>
              {t('review.done', { defaultValue: 'Done reading' })}
            </button>
          </div>
          <AddMedicine docId={d.id} onAdded={onChanged} />
        </div>
      ))}
    </div>
  );
}
