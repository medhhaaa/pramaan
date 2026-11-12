// Check-a-medicine: the doctor types a brand or generic name; warnings come from the records only.
// The warning text, class label and note arrive from the backend in the user's language.
import { useState } from "react";
import { checkMedicine } from "../api";
import { useT } from "../i18n";

export default function CheckMedicine({ patient }) {
  const t = useT();
  const [drug, setDrug] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleCheck(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await checkMedicine(patient.id, drug.trim()));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="check-medicine">
      <h2>{t("med.title")}</h2>
      <form onSubmit={handleCheck} className="ask-form">
        <input
          value={drug}
          onChange={(e) => setDrug(e.target.value)}
          placeholder={t("med.placeholder")}
          maxLength={100}
        />
        <button type="submit" disabled={busy || !drug.trim()}>
          {busy ? t("med.busy") : t("med.button")}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="check-result">
          <p>
            <strong>{result.drug}</strong>
            {result.known ? (
              <> = {result.generic} ({result.class_label})</>
            ) : (
              <span className="hint">{t("med.notInList")}</span>
            )}
          </p>
          {result.warnings.length === 0 ? (
            <p className="ok">{t("med.noMatch")}</p>
          ) : (
            <ul className="warnings">
              {result.warnings.map((w, i) => (
                <li key={i} className={`warning warning-${w.kind}`}>
                  <strong>{t(`med.kind.${w.kind}`, null, w.kind)}:</strong> {w.text}
                  {w.source?.page && (
                    <small> {t("med.pageLine", { page: w.source.page, line: w.source.line })}</small>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="hint">{result.note}</p>
        </div>
      )}
    </div>
  );
}
