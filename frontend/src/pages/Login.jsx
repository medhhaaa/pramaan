import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Eye, EyeOff } from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { ThemeToggle } from '../components/Layout.jsx';
import { useApp } from '../context/AppContext.jsx';
import { login, setToken } from '../api.js';

export default function Login() {
  const { t } = useTranslation();
  const { setUser } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState('login'); // login | signup (demo only)
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const showHint = import.meta.env.VITE_SHOW_DEMO_HINT !== 'false';

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const res = await login(username.trim(), password);
      setToken(res.token);
      setUser({ role: res.role, name: res.name, username: res.username, patientId: res.patientId });
      navigate(res.role === 'doctor' ? '/patients' : '/my-records', { replace: true });
    } catch {
      setError(t('auth.badLogin'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-theme"><ThemeToggle /></div>
      <div className="login-card card-lift">
        <div className="login-logo"><Logo /></div>
        <p className="muted center small">{t('tagline')}</p>

        <div className="login-head">
          <h1>{mode === 'login' ? t('auth.login') : t('auth.signup')}</h1>
          <button className="link-btn" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); }}>
            {mode === 'login' ? `${t('auth.newHere')} ${t('auth.signupLink')}` : `${t('auth.alreadyUser')} ${t('auth.loginLink')}`}
          </button>
        </div>

        <form onSubmit={submit} className="stack">
          <label className="field-label" htmlFor="u">{t('auth.username')}</label>
          <input id="u" className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />

          <label className="field-label" htmlFor="p">{t('auth.password')}</label>
          <div className="input-wrap">
            <input id="p" className="input" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            <button type="button" className="icon-btn" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)}>
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}
          {mode === 'signup' && <p className="muted small">{t('auth.signupDemoOnly')}</p>}

          <button className="btn btn-primary btn-block" disabled={busy}>
            {mode === 'login' ? t('auth.login') : t('auth.signup')}
          </button>
        </form>

        {showHint && mode === 'login' && <div className="demo-hint">{t('auth.demoHint')}</div>}
      </div>
    </div>
  );
}
