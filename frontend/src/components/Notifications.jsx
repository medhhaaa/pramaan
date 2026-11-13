import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bell } from 'lucide-react';
import { getNotifications, readNotification } from '../api.js';
import { useAgo } from '../pages/MyPatients.jsx';

// In-app notifications (patient): refill decisions from the care-team doctor.
// Polls every 10 seconds (no push for the hackathon). API: backend/routes/refills.py.

const POLL_MS = 10000;

export default function Notifications() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const ago = useAgo();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  const load = useCallback(() => { getNotifications().then(setItems).catch(() => {}); }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);

  const unread = items.filter((n) => !n.read_at).length;
  const pick = async (n) => {
    if (!n.read_at) await readNotification(n.id).catch(() => {});
    setOpen(false);
    load();
    if (n.link) navigate(n.link);
  };

  return (
    <div className="notif" ref={box}>
      <button className="icon-btn notif-btn" aria-label={t('notifications.title', { count: unread })} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Bell size={18} />
        {unread > 0 && <span className="notif-count">{unread}</span>}
      </button>
      {open && (
        <div className="notif-panel card" role="dialog" aria-label={t('notifications.heading')}>
          <h3>{t('notifications.heading')}</h3>
          {items.length === 0 && <p className="muted small">{t('notifications.empty')}</p>}
          <ul className="list">
            {items.map((n) => (
              <li key={n.id}>
                <button className={`notif-item ${n.read_at ? '' : 'unread'}`} onClick={() => pick(n)}>
                  <span className="small">{n.text}</span>
                  <span className="muted small">{ago(n.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
