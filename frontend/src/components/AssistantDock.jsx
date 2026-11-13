import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bot, Maximize2, Scan, Users, X } from 'lucide-react';
import { useApp, useActivePatientId } from '../context/AppContext.jsx';
import { ASSISTANT_ON } from '../lib/features.js';
import AssistantChat from './AssistantChat.jsx';
import '../styles/assistant.css';

// The assistant as a round button in the bottom-right corner of every page (Layout.jsx), opening
// a chat panel above it (full screen on a phone). Patients: their own records. Doctors: always there;
// it answers about the patient whose share is open, and with none open it offers Scan / My patients. The chat is the same conversation as the /assistant page (same browser
// cache key), and the panel stays mounted once opened, so an answer still arrives if you close it.
export default function AssistantDock() {
  const { t } = useTranslation();
  const { user, setScanOpen } = useApp();
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

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    const log = panel?.querySelector('.assistant-log');
    if (log) log.scrollTop = log.scrollHeight;
    panel?.querySelector('textarea')?.focus();
    const onKey = (e) => {
      // Escape closes an open source document (DocDrawer) or the scan window first, then the panel
      if (e.key !== 'Escape' || document.querySelector('.drawer-backdrop, .modal-backdrop')) return;
      setOpen(false);
      fabRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!ASSISTANT_ON || pathname === '/assistant') return null;

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
            {pid ? (
              // a new patient gets a fresh conversation
              <AssistantChat key={pid} pid={pid} persona={persona} />
            ) : (
              // a doctor with no patient open: the assistant only answers from one patient's shared records
              <div className="assistant-dock-empty">
                <span className="assistant-dock-badge" aria-hidden="true"><Scan size={20} /></span>
                <p>{t('assistant.doctor.noPatient')}</p>
                <div className="btn-row">
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => setScanOpen(true)}>
                    <Scan size={16} aria-hidden="true" /> {t('nav.scan')}
                  </button>
                  {pathname !== '/my-patients' && (
                    <Link to="/my-patients" className="btn btn-ghost btn-sm"><Users size={16} aria-hidden="true" /> {t('nav.myPatients')}</Link>
                  )}
                </div>
              </div>
            )}
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
