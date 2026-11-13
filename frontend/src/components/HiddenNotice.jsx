import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EyeOff, Send, CheckCircle2 } from 'lucide-react';
import { hiddenSummary, requestMoreRecords } from '../api.js';
import { useActivePatientId } from '../context/AppContext.jsx';
import '../styles/share-scope.css';

const POLL_MS = 5000; // only while a request waits for the patient

// Doctor: "The patient has not shared everything with you". Counts only (never names, groups or
// dates: backend/routes/share_requests.py). During a QR / code share the doctor can ask for more;
// when the patient adds something, onMoreShared() reloads the page under it.
export default function HiddenNotice({ onMoreShared }) {
  const { t } = useTranslation();
  const pid = useActivePatientId();
  const [info, setInfo] = useState(null);
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [shared, setShared] = useState(false);
  const lastStatus = useRef(null);

  const load = useCallback(() => {
    if (!pid) { setInfo(null); return; }
    hiddenSummary(pid).then((res) => {
      const status = res.request?.status || null;
      if (lastStatus.current === 'pending' && status === 'answered') {
        setShared(true);
        onMoreShared?.();
      }
      lastStatus.current = status;
      setInfo(res);
    }).catch(() => setInfo(null)); // share ended: the pages show their own message
  }, [pid, onMoreShared]);

  useEffect(() => { setShared(false); lastStatus.current = null; load(); }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const pending = info?.request?.status === 'pending';
  useEffect(() => {
    if (!pending) return undefined;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, load]);

  const send = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await requestMoreRecords(pid, note.trim());
      setAsking(false);
      setNote('');
      setShared(false);
      load();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  if (shared && !info?.partial) {
    return (
      <div className="hidden-notice hidden-notice-ok" role="status">
        <CheckCircle2 size={18} aria-hidden="true" />
        <p>{t('shareScope.answered')}</p>
        <button className="link-btn small" onClick={() => setShared(false)}>{t('common.close')}</button>
      </div>
    );
  }
  if (!info?.partial) return null;

  const h = info.hidden;
  const parts = [
    h.medicines && t('shareScope.count.medicines', { count: h.medicines })
      + (h.current_medicines ? ` (${t('shareScope.count.current', { count: h.current_medicines })})` : ''),
    h.conditions && t('shareScope.count.conditions', { count: h.conditions }),
    h.tests && t('shareScope.count.tests', { count: h.tests }),
    h.events && t('shareScope.count.events', { count: h.events }),
    h.documents && t('shareScope.count.documents', { count: h.documents }),
  ].filter(Boolean);
  const status = info.request?.status;

  return (
    <div className={`hidden-notice ${h.important ? 'hidden-notice-important' : ''}`} role="region" aria-label={t('shareScope.hiddenTitle')}>
      <EyeOff size={18} aria-hidden="true" />
      <div className="hidden-notice-body">
        <p><strong>{t('shareScope.hiddenTitle')}</strong></p>
        {parts.length > 0 && <p className="small">{t('shareScope.hiddenList', { list: parts.join(', ') })}</p>}
        {h.important && <p className="small">{t('shareScope.importantHint')}</p>}
        <p className="muted small">{t(info.can_request ? 'shareScope.cannotOpen' : 'shareScope.careTeamNote')}</p>
        {shared && <p className="small hidden-notice-ok-text">{t('shareScope.answered')}</p>}
        {status === 'pending' && <p className="small" role="status">{t('shareScope.waiting')}</p>}
        {status === 'declined' && <p className="small" role="status">{t('shareScope.declined')}</p>}
        {error && <p className="error-text small">{error}</p>}

        {info.can_request && status !== 'pending' && (asking ? (
          <form className="hidden-notice-form" onSubmit={send}>
            <label className="field-label" htmlFor="ask-more-note">{t('shareScope.noteLabel')}</label>
            <textarea id="ask-more-note" className="input" rows={2} maxLength={300} value={note}
              placeholder={t('shareScope.notePlaceholder')} onChange={(e) => setNote(e.target.value)} />
            <div className="row">
              <button className="btn btn-primary btn-sm" disabled={busy}><Send size={14} /> {t('shareScope.send')}</button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAsking(false)}>{t('shareScope.cancel')}</button>
            </div>
          </form>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={() => setAsking(true)}>
            {status === 'declined' ? t('shareScope.askAgain') : t('shareScope.ask')}
          </button>
        ))}
      </div>
    </div>
  );
}
