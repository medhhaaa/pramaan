// Reviewer corrects one field of a fact. The backend keeps the original value in the
// corrections table (who, role, when), and the source quote is never changed.
import { useState } from "react";
import { correctFact } from "../api";

const FIELDS_BY_TYPE = {
  medication: ["name", "dose", "frequency", "action", "event_date", "status"],
  lab_test: ["name", "value", "unit", "event_date", "status"],
  allergy: ["name", "value", "event_date", "status"],
  condition: ["name", "event_date", "status"],
  event: ["name", "event_date", "status"],
  demographic: ["value"],
};

const CHOICES = {
  status: ["documented", "negated"],
  action: ["started", "continued", "changed", "stopped", "mentioned"],
};

export default function CorrectionForm({ fact, user, onCorrected }) {
  const fields = FIELDS_BY_TYPE[fact.type] || ["name"];
  const [field, setField] = useState(fields[0]);
  const [newValue, setNewValue] = useState(fact[fields[0]] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null); // {field, oldValue, newValue}

  function chooseField(f) {
    setField(f);
    setNewValue(fact[f] ?? "");
  }

  async function handleSave(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const oldValue = fact[field];
    try {
      const updated = await correctFact(fact.fact_id, field, newValue.trim());
      setDone({ field, oldValue, newValue: updated[field] });
      onCorrected(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const unchanged = String(fact[field] ?? "") === newValue.trim();

  return (
    <div className="correction">
      <h3>Correct this fact</h3>
      <form onSubmit={handleSave} className="correction-form">
        <select value={field} onChange={(e) => chooseField(e.target.value)}>
          {fields.map((f) => (
            <option key={f} value={f}>
              {f.replace("_", " ")}
            </option>
          ))}
        </select>
        {CHOICES[field] ? (
          <select value={newValue} onChange={(e) => setNewValue(e.target.value)}>
            {CHOICES[field].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        ) : (
          <input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder={field === "event_date" ? "YYYY-MM-DD" : "new value"}
          />
        )}
        <button type="submit" disabled={busy || unchanged || !newValue.trim()}>
          {busy ? "Saving..." : "Save correction"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      {done && (
        <table className="side-by-side">
          <thead>
            <tr>
              <th>{done.field.replace("_", " ")}</th>
              <th>Original (kept)</th>
              <th>Corrected</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td />
              <td>{String(done.oldValue ?? "empty")}</td>
              <td>{String(done.newValue ?? "empty")}</td>
            </tr>
          </tbody>
        </table>
      )}
      {done && (
        <p className="hint">
          Corrected by {user.username} ({user.role}). The source line above is unchanged.
        </p>
      )}
    </div>
  );
}
