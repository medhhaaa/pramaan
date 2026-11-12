import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, LogOut, Scan, X, LayoutDashboard, Clock, Pill, Flag, MessageSquare, Upload, ShieldCheck, Trash2, Gauge, QrCode, ListChecks, FileText, Sun, Moon, ClipboardCheck } from 'lucide-react';
import Logo from './Logo.jsx';
import { useApp } from '../context/AppContext.jsx';
import { isDummy, saveLanguage } from '../api.js';
import { getTheme, toggleTheme } from '../lib/theme.js';

const DOCTOR_NAV = [
  { to: '/patients', key: 'nav.patients', icon: LayoutDashboard },
  { to: '/accuracy', key: 'nav.accuracy', icon: Gauge },
  { to: '/scan', key: 'nav.scan', icon: Scan, action: 'scan' },
  { to: '/timeline', key: 'nav.timeline', icon: Clock, gated: true },
  { to: '/medication', key: 'nav.medication', icon: Pill, gated: true },
  { to: '/flags', key: 'nav.flags', icon: Flag, gated: true },
  { to: '/ask', key: 'nav.ask', icon: MessageSquare, gated: true },
  { to: '/upload', key: 'nav.upload', icon: Upload, gated: true },
  { to: '/audit', key: 'nav.audit', icon: ShieldCheck },
  { to: '/delete', key: 'nav.delete', icon: Trash2, gated: true },
];

const PATIENT_NAV = [
  { to: '/my-records', key: 'nav.myRecords', icon: FileText },
  { to: '/timeline', key: 'nav.timeline', icon: Clock },
  { to: '/upload', key: 'nav.upload', icon: Upload },
  { to: '/qr', key: 'nav.generateQr', icon: QrCode },
  { to: '/things', key: 'nav.thingsToCheck', icon: ListChecks },
  { to: '/claim-documents', key: 'nav.claimDocuments', icon: ClipboardCheck },
  { to: '/medication', key: 'nav.medication', icon: Pill },
  { to: '/flags', key: 'nav.flags', icon: Flag },
  { to: '/ask', key: 'nav.ask', icon: MessageSquare },
  { to: '/audit', key: 'nav.audit', icon: ShieldCheck },
  { to: '/delete', key: 'nav.delete', icon: Trash2 },
];

export function ThemeToggle() {
  const [theme, setThemeState] = useState(getTheme());
  const flip = () => setThemeState(toggleTheme());
  const isDark = theme === 'dark';
  return (
    <button className="icon-btn theme-toggle" onClick={flip} aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'} title={isDark ? 'Light' : 'Dark'}>
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

export default function Layout() {
  const { t, i18n } = useTranslation();
  const { user, setUser, session, setSession, logout, setScanOpen, setPendingPath } = useApp();
  const [open, setOpen] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const navigate = useNavigate();
  const items = user.role === 'doctor' ? DOCTOR_NAV : PATIENT_NAV;
  const sessionActive = session && session.expiresAt > Date.now();

  const onLang = (e) => {
    const language = e.target.value;
    localStorage.setItem('pramaan_lang', language);
    i18n.changeLanguage(language);
    setUser({ ...user, language });
    saveLanguage(user.username, language).catch(() => {}); // the screen still switches if saving fails
  };

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <div className={`shell role-${user.role}`}>
      {isDummy && <div className="demo-banner">{t('demoBanner')}</div>}
      <div className="shell-body">
        <aside className={`sidebar ${open ? '' : 'collapsed'} ${drawer ? 'drawer-open' : ''}`}>
          <div className="sidebar-top">
            {open && <Logo />}
            {!open && <Logo compact />}
            <button className="icon-btn" aria-label="Toggle sidebar" onClick={() => setOpen(!open)}>
              {drawer ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
          <nav aria-label="Main">
            {items.map(({ to, key, icon: Icon, action, gated }) => {
              if (action === 'scan') {
                return (
                  <button key={key} className="nav-item" onClick={() => setScanOpen(true)} title={t(key)}>
                    <Icon size={20} />{open && <span>{t(key)}</span>}
                  </button>
                );
              }
              return (
                <NavLink
                  key={key + to}
                  to={to}
                  className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                  title={t(key)}
                  onClick={(e) => {
                    if (gated && !sessionActive && user.role === 'doctor') {
                      e.preventDefault();
                      setPendingPath(to);
                      setScanOpen(true);
                    }
                    setDrawer(false);
                  }}
                >
                  <Icon size={20} />{open && <span>{t(key)}</span>}
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <div className="main-col">
          <header className="app-header">
            <button className="icon-btn mobile-only" aria-label="Open menu" onClick={() => setDrawer(!drawer)}><Menu size={22} /></button>
            <div className="header-logo"><Logo compact /></div>
            <div className="header-right">
              <ThemeToggle />
              <select className="lang-select" aria-label="Language" value={i18n.language} onChange={onLang}>
                <option value="en">English</option>
                <option value="hi">हिंदी</option>
                <option value="kn">ಕನ್ನಡ</option>
              </select>
              <span className="user-chip">{user.name} ({user.role})</span>
              <button className="btn btn-ghost" onClick={handleLogout}><LogOut size={16} />{t('auth.logout')}</button>
            </div>
          </header>
          {user.role === 'doctor' && sessionActive && (
            <div className="session-bar">
              <span className="chip chip-verified">{t('scan.sessionChip')}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setSession(null); navigate('/patients'); }}>{t('scan.endSession')}</button>
            </div>
          )}
          <main className="content"><Outlet /></main>
          <footer className="app-footer">{t('disclaimer')}</footer>
        </div>
      </div>
    </div>
  );
}
