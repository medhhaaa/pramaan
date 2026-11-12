import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getQuestions, answerQuestion } from '../api.js';
import { useApp } from '../context/AppContext.jsx';

const OPTIONS = [
  { key: 'yes', answer: 'yes' },
  { key: 'no', answer: 'no' },
  { key: 'dontKnow', answer: 'dont_know' },
  { key: 'skip', answer: 'skip' },
  { key: 'other', answer: 'value' },
];

export default function Things() {
  const { t } = useTranslation();
  const { user } = useApp();
  const [qs, setQs] = useState([]);
  const [i, setI] = useState(0);
  const [choice, setChoice] = useState(null);
  const [other, setOther] = useState('');
  const [sent, setSent] = useState([]);

  useEffect(() => { getQuestions(user.patientId).then((q) => setQs(q.filter((x) => x.status === 'open'))); }, [user.patientId]);

  if (qs.length === 0) return <div className="empty-state card"><p>{t('things.empty')}</p></div>;
  const q = qs[i];
  const done = sent.length;

  const send = async () => {
    if (!choice) return;
    const opt = OPTIONS.find((o) => o.key === choice);
    await answerQuestion(q.id, opt.answer, choice === 'other' ? other : null);
    setSent([...sent, q.id]);
    setChoice(null);
    setOther('');
    setI(Math.min(i + 1, qs.length - 1));
  };

  const finished = done === qs.length;

  return (
    <section className="things">
      <div className="page-head">
        <h1>{t('things.title')}</h1>
        <span className="muted">{t('things.progress', { done, total: qs.length })}</span>
      </div>

      {!finished && (
        <article className="card question-card">
          <p className="eyebrow">{t('things.problem')}</p>
          <h2>{q.text}</h2>
          <p className="muted small">{t('things.why')} <span className="mono">{q.source}</span></p>

          <div className="chip-row answer-row" role="radiogroup">
            {OPTIONS.map((o) => (
              <button key={o.key} role="radio" aria-checked={choice === o.key}
                className={`answer ${choice === o.key ? 'selected' : ''}`}
                onClick={() => setChoice(o.key)}>
                {t(`things.${o.key}`)}
              </button>
            ))}
          </div>

          {choice === 'other' && (
            <input className="input" value={other} onChange={(e) => setOther(e.target.value)} placeholder={t('things.other')} aria-label={t('things.other')} />
          )}

          <button className="btn btn-primary btn-block" disabled={!choice} onClick={send}>{t('things.send')}</button>
        </article>
      )}

      {finished && <div className="card success-box"><p>{t('things.sentDoctor')}</p></div>}
    </section>
  );
}
