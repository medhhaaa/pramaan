// Asked once, right after a user's first login (their account has no language yet).
// Written in both languages because we don't know which one they read yet.
// The choice is saved on the account; the header lets them switch later.
import { useState } from "react";
import { LANGUAGES } from "../i18n";

export default function LanguagePopup({ onChoose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function choose(lang) {
    setBusy(true);
    setError("");
    try {
      await onChoose(lang);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="language-title">
        <h2 id="language-title">Choose your language · ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆರಿಸಿ</h2>
        <p>Which language do you prefer? You can change it later from the top bar.</p>
        <p>ನೀವು ಯಾವ ಭಾಷೆಯನ್ನು ಇಷ್ಟಪಡುತ್ತೀರಿ? ಇದನ್ನು ನಂತರ ಮೇಲಿನ ಪಟ್ಟಿಯಿಂದ ಬದಲಾಯಿಸಬಹುದು.</p>
        <p className="actions">
          {LANGUAGES.map(([code, label]) => (
            <button key={code} className="btn-primary" onClick={() => choose(code)} disabled={busy} lang={code}>
              {label}
            </button>
          ))}
        </p>
        <p className="hint">
          Medicine names, doses, units and dates always stay exactly as written in your documents.
          <br />
          ಔಷಧದ ಹೆಸರುಗಳು, ಡೋಸ್, ಘಟಕಗಳು ಮತ್ತು ದಿನಾಂಕಗಳು ಯಾವಾಗಲೂ ನಿಮ್ಮ ದಾಖಲೆಗಳಲ್ಲಿ ಬರೆದಂತೆಯೇ ಇರುತ್ತವೆ.
        </p>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
