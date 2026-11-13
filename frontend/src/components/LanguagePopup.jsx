import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Logo from './Logo.jsx';
import { saveLanguage } from '../api.js';

// Shown once, right after the user's first login (their account has no language yet).
// The choice is saved to the account (PUT /me/language); the header can change it later.
export default function LanguagePopup({ username, onDone }) {
  const { i18n } = useTranslation();
  const [choice, setChoice] = useState(i18n.language || 'en');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const confirm = async () => {
    setBusy(true);
    setError(false);
    try {
      await saveLanguage(username, choice);
      localStorage.setItem('pramaan_lang', choice); // the login page opens in it next time
      i18n.changeLanguage(choice);
      onDone(choice);
    } catch {
      setError(true);
      setBusy(false);
    }
  };

  const opts = [
    { code: 'en', label: 'English', hint: 'default' },
    { code: 'hi', label: 'हिंदी', hint: '' },
    { code: 'kn', label: 'ಕನ್ನಡ', hint: '' },
  ];

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="lang-title">
      <div className="modal card-lift">
        <Logo />
        <h2 id="lang-title" className="lang-title">Choose your language / भाषा चुनें / ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ</h2>
        <div className="radio-list">
          {opts.map((o) => (
            <label key={o.code} className={`radio-row ${choice === o.code ? 'selected' : ''}`}>
              <input type="radio" name="lang" value={o.code} checked={choice === o.code} onChange={() => setChoice(o.code)} />
              <span className="radio-label">{o.label}</span>
              {o.hint && <span className="muted small">{o.hint}</span>}
            </label>
          ))}
        </div>
        <button className="btn btn-primary btn-block" onClick={confirm} disabled={busy}>OK</button>
        {error && <p className="error-text small">Could not save. Please try again. / सहेजा नहीं जा सका। फिर से कोशिश करें। / ಉಳಿಸಲು ಆಗಲಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.</p>}
      </div>
    </div>
  );
}
