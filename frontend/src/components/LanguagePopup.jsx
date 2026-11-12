import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Logo from './Logo.jsx';

export default function LanguagePopup({ onDone }) {
  const { i18n } = useTranslation();
  const [choice, setChoice] = useState(i18n.language || 'en');

  const confirm = () => {
    localStorage.setItem('pramaan_lang', choice);
    i18n.changeLanguage(choice);
    onDone();
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
        <button className="btn btn-primary btn-block" onClick={confirm}>OK</button>
      </div>
    </div>
  );
}
