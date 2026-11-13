import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Eye, EyeOff } from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { ThemeToggle } from '../components/Layout.jsx';
import { useApp } from '../context/AppContext.jsx';
import { login, setToken, signup } from '../api.js';

export default function Login() {
  const { t, i18n } = useTranslation();
  const { setUser } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState('login'); // login | signup
  const [role, setRole] = useState('patient'); // sign-up only
  const [fullName, setFullName] = useState('');
  const [regNo, setRegNo] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const showHint = import.meta.env.VITE_SHOW_DEMO_HINT !== 'false';

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    const name = username.trim();
    if (mode === 'signup') {
      // same rules as the backend (POST /signup), checked here so the message is in the user's language
      if (!/^[A-Za-z0-9._-]{3,30}$/.test(name)) { setError(t('auth.usernameRule')); return; }
      if (password.length < 6) { setError(t('auth.passwordRule')); return; }
      if (fullName.trim().length < 2) { setError(t('auth.fullNameRule')); return; }
      if (role === 'doctor' && !regNo.trim()) { setError(t('auth.regNoRule')); return; }
    }
    setBusy(true);
    try {
      const res = mode === 'signup'
        ? await signup({ username: name, password, role, fullName: fullName.trim(), registrationNumber: regNo.trim() })
        : await login(name, password);
      setToken(res.token);
      // language is null on the first login: the language popup then asks (App.jsx)
      const language = res.language || null;
      if (language) { i18n.changeLanguage(language); localStorage.setItem('pramaan_lang', language); }
      setUser({ role: res.role, name: res.name, username: res.username, patientId: res.patientId, language });
      navigate(res.role === 'doctor' ? '/my-patients' : '/my-records', { replace: true });
    } catch (err) {
      if (mode === 'login') setError(t('auth.badLogin'));
      else setError(err.status === 409 ? t('auth.usernameTaken') : t('auth.signupFailed'));
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
          {mode === 'signup' && (
            <>
              <span className="field-label" id="role-label">{t('auth.iAm')}</span>
              <div className="btn-row tight" role="radiogroup" aria-labelledby="role-label">
                {['patient', 'doctor'].map((r) => (
                  <button key={r} type="button" role="radio" aria-checked={role === r}
                    className={`answer ${role === r ? 'selected' : ''}`} onClick={() => setRole(r)}>
                    {t(`auth.role_${r}`)}
                  </button>
                ))}
              </div>
              <label className="field-label" htmlFor="fn">{t('auth.fullName')}</label>
              <input id="fn" className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" maxLength={80} required />
              {role === 'doctor' && (
                <>
                  <label className="field-label" htmlFor="rn">{t('auth.regNo')}</label>
                  <input id="rn" className="input" value={regNo} onChange={(e) => setRegNo(e.target.value)} placeholder="KMC 12345" maxLength={40} required />
                </>
              )}
            </>
          )}
          <label className="field-label" htmlFor="u">{t('auth.username')}</label>
          <input id="u" className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />

          <label className="field-label" htmlFor="p">{t('auth.password')}</label>
          <div className="input-wrap">
            <input id="p" className="input" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required />
            <button type="button" className="icon-btn" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)}>
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {error && <p className="error-text" role="alert">{error}</p>}
          {mode === 'signup' && <p className="muted small">{t(role === 'patient' ? 'auth.signupPatientNote' : 'auth.signupDoctorNote')}</p>}

          <button className="btn btn-primary btn-block" disabled={busy}>
            {mode === 'login' ? t('auth.login') : t('auth.signup')}
          </button>
        </form>

        {showHint && mode === 'login' && <div className="demo-hint">{t('auth.demoHint')}</div>}
      </div>
    </div>
  );
}
