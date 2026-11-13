import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Send } from 'lucide-react';
import { ask } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import PatientGate from '../components/PatientGate.jsx';

function AskInner() {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const [q, setQ] = useState('');
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);

  const send = async (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    const question = q.trim();
    setQ('');
    setBusy(true);
    try {
      const res = await ask(pid, question);
      setLog((l) => [...l, { question, ...res }]);
    } catch (err) {
      // keep the question visible and free the input again
      setLog((l) => [...l, { question, answer: `${t('common.error')} (${err.message})`, citations: [], failed: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ask">
      <div className="page-head"><h1>{t('ask.title')}</h1></div>
      <div className="chat">
        {log.length === 0 && <p className="muted">{t('ask.footer')}</p>}
        {log.map((m, i) => (
          <div key={i} className="chat-item">
            <p className="bubble-q">{m.question}</p>
            <div className="card bubble-a">
              <p>{m.answer}</p>
              {m.citations.length > 0 && (
                <div className="chip-row">{m.citations.map((c) => <span key={c} className="chip chip-info mono">{c}</span>)}</div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="skeleton" />}
      </div>
      <form className="ask-input" onSubmit={send}>
        <input className="input" value={q} placeholder={t('ask.placeholder')} onChange={(e) => setQ(e.target.value)} aria-label={t('ask.placeholder')} />
        <button className="btn btn-primary" aria-label={t('ask.send')}><Send size={18} /></button>
      </form>
      <p className="muted small">{t('ask.footer')}</p>
    </section>
  );
}

export default function Ask() {
  return <PatientGate><AskInner /></PatientGate>;
}
