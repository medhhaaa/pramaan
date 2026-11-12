// Check-a-medicine: the doctor types a brand or generic name; warnings come from the records only.
import { useState } from "react";
import { checkMedicine } from "../api";

const KIND_TEXT = { allergy: "Allergy", same_medicine: "Already listed", same_class: "Same group" };

export default function CheckMedicine({ patient }) {
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
      <h2>Check a medicine</h2>
      <form onSubmit={handleCheck} className="ask-form">
        <input
          value={drug}
          onChange={(e) => setDrug(e.target.value)}
          placeholder="Brand or generic name, e.g. Augmentin"
          maxLength={100}
        />
        <button type="submit" disabled={busy || !drug.trim()}>
          {busy ? "Checking..." : "Check"}
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
              <span className="hint"> not in Pramaan's drug list; checked by name only.</span>
            )}
          </p>
          {result.warnings.length === 0 ? (
            <p className="ok">No matching allergy or current medicine in the records.</p>
          ) : (
            <ul className="warnings">
              {result.warnings.map((w, i) => (
                <li key={i} className={`warning warning-${w.kind}`}>
                  <strong>{KIND_TEXT[w.kind] || w.kind}:</strong> {w.text}
                  {w.source?.page && (
                    <small> (page {w.source.page}, line {w.source.line})</small>
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
