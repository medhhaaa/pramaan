import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bot, Maximize2, X } from 'lucide-react';
import { useApp, useActivePatientId } from '../context/AppContext.jsx';
import { ASSISTANT_ON } from '../lib/features.js';
import AssistantChat from './AssistantChat.jsx';
import '../styles/assistant.css';

// The assistant as a round button in the bottom-right corner of every page (Layout.jsx), opening
// a chat panel above it (full screen on a phone). Patients: their own records. Doctors: only while
// a patient's share is open. The chat is the same conversation as the /assistant page (same browser
// cache key), and the panel stays mounted once opened, so an answer still arrives if you close it.
export default function AssistantDock() {
  const { t } = useTranslation();
  const { user } = useApp();
  const pid = useActivePatientId();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false); // the chat loads on first open, then stays
  const fabRef = useRef(null);
  const panelRef = useRef(null);
  const persona = user.role === 'doctor' ? 'doctor' : 'patient';
  const title = t(`assistant.${persona}.title`);

  // a link in an answer (Upload, Claim documents) opens another page: the panel steps aside
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => { if (!pid) { setOpen(false); setMounted(false); } }, [pid]);

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    const log = panel?.querySelector('.assistant-log');
    if (log) log.scrollTop = log.scrollHeight;
    panel?.querySelector('textarea')?.focus();
    const onKey = (e) => {
      // Escape closes an open source document first (DocDrawer), then the panel
      if (e.key !== 'Escape' || document.querySelector('.drawer-backdrop')) return;
      setOpen(false);
      fabRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!ASSISTANT_ON || !pid || pathname === '/assistant') return null;

  const toggle = () => { setMounted(true); setOpen((o) => !o); };
  const close = () => { setOpen(false); fabRef.current?.focus(); };

  return (
    <>
      {mounted && (
        <div ref={panelRef} id="assistant-dock" className="assistant-dock" role="dialog" aria-modal="false"
          aria-labelledby="assistant-dock-title" hidden={!open}>
          <div className="assistant-dock-head">
            <span className="assistant-dock-badge" aria-hidden="true"><Bot size={18} /></span>
            <h2 id="assistant-dock-title">{title}</h2>
            <Link to="/assistant" className="icon-btn" aria-label={t('assistant.openFull')} title={t('assistant.openFull')}>
              <Maximize2 size={16} />
            </Link>
            <button type="button" className="icon-btn" aria-label={t('common.close')} title={t('common.close')} onClick={close}>
              <X size={18} />
            </button>
          </div>
          <div className="assistant-dock-body">
            {/* a new patient gets a fresh conversation */}
            <AssistantChat key={pid} pid={pid} persona={persona} />
          </div>
        </div>
      )}
      <button ref={fabRef} type="button" className={`assistant-fab ${open ? 'is-open' : ''}`} onClick={toggle}
        aria-expanded={open} aria-controls={mounted ? 'assistant-dock' : undefined}
        aria-label={open ? t('common.close') : title} title={open ? t('common.close') : title}>
        {open ? <X size={24} aria-hidden="true" /> : <Bot size={26} aria-hidden="true" />}
      </button>
    </>
  );
}
