import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, LogOut, Scan, X, LayoutDashboard, Clock, Pill, Flag, MessageSquare, Upload, ShieldCheck, Trash2, Gauge, QrCode, ListChecks, FileText, Sun, Moon, ClipboardCheck, Users, Stethoscope, FolderOpen, Tablets, FileCheck } from 'lucide-react';
import logoTransparent from '../assets/pramaan-logo-transparent.png';
import Notifications from './Notifications.jsx';
import { useApp } from '../context/AppContext.jsx';
import { isDummy, saveLanguage } from '../api.js';
import { getTheme, toggleTheme } from '../lib/theme.js';

const DOCTOR_NAV = [
  { to: '/my-patients', key: 'nav.myPatients', icon: Users },
  { to: '/patients', key: 'nav.patients', icon: LayoutDashboard },
  { to: '/accuracy', key: 'nav.accuracy', icon: Gauge },
  { to: '/scan', key: 'nav.scan', icon: Scan, action: 'scan' },
  { to: '/timeline', key: 'nav.timeline', icon: Clock, gated: true },
  { to: '/records', key: 'nav.records', icon: FolderOpen, gated: true },
  { to: '/medication', key: 'nav.medication', icon: Pill, gated: true },
  { to: '/flags', key: 'nav.flags', icon: Flag, gated: true },
  { to: '/ask', key: 'nav.ask', icon: MessageSquare, gated: true },
  { to: '/consult-records', key: 'nav.consultRecords', icon: FileCheck, gated: true },
  // no upload / delete: a doctor's shared access is reading and reviewing only (backend/auth.py)
  { to: '/audit', key: 'nav.audit', icon: ShieldCheck, gated: true },
];

const PATIENT_NAV = [
  { to: '/my-records', key: 'nav.myRecords', icon: FileText },
  { to: '/timeline', key: 'nav.timeline', icon: Clock },
  { to: '/upload', key: 'nav.upload', icon: Upload },
  { to: '/qr', key: 'nav.generateQr', icon: QrCode },
  { to: '/my-medicines', key: 'nav.myMedicines', icon: Tablets },
  { to: '/care-team', key: 'nav.careTeam', icon: Stethoscope },
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

  // phone menu: Escape closes it (the backdrop below closes it on tap)
  useEffect(() => {
    if (!drawer) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setDrawer(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawer]);

  return (
    <div className={`shell role-${user.role}`}>
      {isDummy && <div className="demo-banner">{t('demoBanner')}</div>}
      <div className="shell-body">
        {drawer && <div className="sidebar-backdrop" aria-hidden="true" onClick={() => setDrawer(false)} />}
        <aside className={`sidebar ${open ? '' : 'collapsed'} ${drawer ? 'drawer-open' : ''}`}>
          <div className="sidebar-top">
            {/* desktop: expands / collapses the sidebar. Phones: the menu is open here, so it shows X and closes it. */}
            <button
              className="icon-btn sidebar-toggle"
              aria-label={drawer ? t('common.close') : open ? 'Collapse menu' : 'Expand menu'}
              aria-expanded={drawer || open}
              title={drawer ? t('common.close') : open ? 'Collapse menu' : 'Expand menu'}
              onClick={() => (drawer ? setDrawer(false) : setOpen(!open))}
            >
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
            <Link to="/" className="header-logo">
              <img src={logoTransparent} alt="Pramaan – प्रमाण – ಪ್ರಮಾಣ" className="header-logo-img" height="44" />
            </Link>
            <div className="header-right">
              {user.role === 'patient' && <Notifications />}
              <ThemeToggle />
              <select className="lang-select" aria-label="Language" value={i18n.language} onChange={onLang}>
                <option value="en">English</option>
                <option value="hi">हिंदी</option>
                <option value="kn">ಕನ್ನಡ</option>
              </select>
              <span className="user-chip">{user.name} ({user.role})</span>
              <button className="btn btn-ghost" onClick={handleLogout} aria-label={t('auth.logout')}>
                <LogOut size={16} /><span className="btn-label">{t('auth.logout')}</span>
              </button>
            </div>
          </header>
          {user.role === 'doctor' && sessionActive && (
            <div className="session-bar">
              <span className="chip chip-verified">{session.careTeam ? t('myPatients.careTeamChip') : t('scan.sessionChip')}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setSession(null); navigate(session.careTeam ? '/my-patients' : '/patients'); }}>{t('scan.endSession')}</button>
            </div>
          )}
          <main className="content"><Outlet /></main>
          <footer className="app-footer">{t('disclaimer')}</footer>
        </div>
      </div>
    </div>
  );
}
