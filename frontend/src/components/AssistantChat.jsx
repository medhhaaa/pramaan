import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Send, Loader2, ShieldCheck, FileText, EyeOff, CheckCircle2, XCircle, Wrench } from 'lucide-react';
import { askAssistant, privacyPreview, confirmAssistantAction, cancelAssistantAction } from '../api.js';
import DocDrawer from './DocDrawer.jsx';
import { fmtDate } from '../lib/format.js';
import '../styles/assistant.css';

const HISTORY_TURNS = 6;
const SUGGESTIONS = {
  doctor: ['brief', 'redFlags', 'diabetes', 'augmentin'],
  patient: ['medicines', 'sugar', 'claim', 'who'],
};

// The doctor and patient assistants (backend/routes/assistant.py). persona: 'doctor' | 'patient'.
// Before a message goes out, the privacy preview shows what the AI would see; if anything gets
// replaced, the user sees it and sends or edits. Answers cite facts / documents (click to open the
// source line). A write (save to claim pack) comes back as a card: nothing happens until Confirm.
export default function AssistantChat({ pid, persona }) {
  const { t, i18n } = useTranslation();
  const [turns, setTurns] = useState([]); // {role: 'user'|'assistant'|'note', text, ...}
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null); // {original, redacted} waiting for "Send"
  const [error, setError] = useState(null); // {text, found}
  const [open, setOpen] = useState(null); // {id, line}
  const endRef = useRef(null);
  const closeDoc = useCallback(() => setOpen(null), []);

  useEffect(() => { endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' }); }, [turns, busy, preview]);

  const history = () => turns.filter((x) => x.role === 'user' || x.role === 'assistant')
    .slice(-HISTORY_TURNS).map((x) => ({ role: x.role, text: x.text }));

  const send = async (message) => {
    setBusy(true);
    setError(null);
    setPreview(null);
    const past = history();
    setTurns((all) => [...all, { role: 'user', text: message }]);
    setText('');
    try {
      const out = await askAssistant(pid, message, past);
      setTurns((all) => [...all, { role: 'assistant', text: out.answer, ...out }]);
    } catch (e) {
      setTurns((all) => all.slice(0, -1));
      setText(message);
      setError({ text: e.message, found: e.detail?.found || [] });
    } finally { setBusy(false); }
  };

  // step 1: what will the AI see? Only ask the user when something would be replaced.
  const submit = async (message) => {
    const m = message.trim();
    if (!m || busy) return;
    setBusy(true);
    setError(null);
    try {
      const p = await privacyPreview(pid, m);
      if (p.blocked) {
        setError({ text: t('assistant.blocked'), found: p.still_found || [] });
        setBusy(false);
        return;
      }
      if (p.redacted && p.redacted !== m) {
        setPreview({ original: m, redacted: p.redacted });
        setBusy(false);
        return;
      }
    } catch { /* preview unavailable: the backend still runs the privacy layer before the AI */ }
    await send(m);
  };

  const act = async (turnIndex, kind) => {
    const turn = turns[turnIndex];
    const id = turn.pending_action.action_id;
    setBusy(true);
    try {
      if (kind === 'confirm') await confirmAssistantAction(pid, id);
      else await cancelAssistantAction(pid, id);
      setTurns((all) => all.map((x, i) => (i === turnIndex ? { ...x, actionState: kind } : x)));
    } catch (e) {
      setTurns((all) => all.map((x, i) => (i === turnIndex ? { ...x, actionState: 'failed', actionError: e.message } : x)));
    } finally { setBusy(false); }
  };

  return (
    <div className="assistant">
      <p className="muted small assistant-note"><ShieldCheck size={14} aria-hidden="true" /> {t('assistant.note')}</p>

      <div className="assistant-log" aria-live="polite">
        {turns.length === 0 && (
          <div className="assistant-empty">
            <p className="muted">{t(`assistant.${persona}.empty`)}</p>
            <div className="chip-row">
              {SUGGESTIONS[persona].map((key) => (
                <button key={key} type="button" className="chip chip-neutral assistant-suggest" disabled={busy}
                  onClick={() => submit(t(`assistant.${persona}.suggest.${key}`))}>
                  {t(`assistant.${persona}.suggest.${key}`)}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (turn.role === 'user' ? (
          <div key={i} className="assistant-turn assistant-user"><p>{turn.text}</p></div>
        ) : (
          <div key={i} className="assistant-turn assistant-bot">
            <p>{turn.text}</p>
            {turn.hidden && (
              <p className="assistant-hidden small"><EyeOff size={14} aria-hidden="true" /> {t('assistant.hidden')}</p>
            )}
            {(turn.citations?.length > 0 || turn.documents?.length > 0) && (
              <div className="assistant-sources">
                <span className="muted small">{t('assistant.sources')}</span>
                <div className="chip-row">
                  {turn.citations.map((c) => (
                    <button key={c.fact_id} type="button" className="chip chip-info assistant-cite"
                      onClick={() => c.document_id && setOpen({ id: c.document_id, line: c.line })}>
                      {c.name}{c.event_date ? ` · ${fmtDate(c.event_date, i18n.language)}` : ''}
                    </button>
                  ))}
                  {(turn.documents || []).map((d) => (
                    <button key={d.id} type="button" className="chip chip-info assistant-cite" onClick={() => setOpen({ id: d.id })}>
                      <FileText size={13} aria-hidden="true" /> {t(`records.types.${d.doc_type}`, { defaultValue: (d.doc_type || '').replace(/_/g, ' ') })}
                      {d.document_date ? ` · ${fmtDate(d.document_date, i18n.language)}` : ''}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turn.pending_action && (
              <div className="assistant-action card">
                <p className="small"><strong>{t('assistant.confirmTitle')}</strong></p>
                <p className="small">{turn.pending_action.summary}</p>
                {!turn.actionState && (
                  <div className="row">
                    <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => act(i, 'confirm')}>{t('assistant.confirm')}</button>
                    <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => act(i, 'cancel')}>{t('assistant.cancel')}</button>
                  </div>
                )}
                {turn.actionState === 'confirm' && <p className="small assistant-done"><CheckCircle2 size={14} aria-hidden="true" /> {t('assistant.done')}</p>}
                {turn.actionState === 'cancel' && <p className="small muted"><XCircle size={14} aria-hidden="true" /> {t('assistant.cancelled')}</p>}
                {turn.actionState === 'failed' && <p className="small error-text">{turn.actionError}</p>}
              </div>
            )}
            {turn.tools_used?.length > 0 && (
              <p className="muted small assistant-tools">
                <Wrench size={12} aria-hidden="true" /> {t('assistant.looked', { tools: turn.tools_used.map((x) => t(`assistant.tools.${x.tool}`, { defaultValue: x.tool })).join(', ') })}
              </p>
            )}
          </div>
        )))}

        {busy && <p className="muted small assistant-thinking"><Loader2 size={14} className="spin" aria-hidden="true" /> {t('assistant.thinking')}</p>}

        {preview && (
          <div className="assistant-preview card" role="dialog" aria-label={t('assistant.previewTitle')}>
            <p className="small"><strong>{t('assistant.previewTitle')}</strong></p>
            <p className="small mono assistant-preview-text">{preview.redacted}</p>
            <p className="muted small">{t('assistant.previewHint')}</p>
            <div className="row">
              <button className="btn btn-primary btn-sm" onClick={() => send(preview.original)}>{t('assistant.sendAnyway')}</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setText(preview.original); setPreview(null); }}>{t('assistant.edit')}</button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          <p className="small">{error.text}</p>
          {error.found.length > 0 && (
            <ul className="small">{error.found.map((f, i) => <li key={i}><span className="mono">{f.text}</span> ({f.kind})</li>)}</ul>
          )}
        </div>
      )}

      <form className="assistant-input" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <label className="sr-only" htmlFor="assistant-text">{t(`assistant.${persona}.placeholder`)}</label>
        <textarea id="assistant-text" className="input" rows={2} maxLength={500} value={text} disabled={busy || Boolean(preview)}
          placeholder={t(`assistant.${persona}.placeholder`)} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(text); } }} />
        <button className="btn btn-primary" disabled={busy || !text.trim() || Boolean(preview)} aria-label={t('assistant.send')}>
          <Send size={16} /> <span className="btn-label">{t('assistant.send')}</span>
        </button>
      </form>

      {open && <DocDrawer docId={open.id} highlightLine={open.line} onClose={closeDoc} />}
    </div>
  );
}
