// Reviewer corrects one field of a fact. The backend keeps the original value in the
// corrections table (who, role, when), and the source quote is never changed.
import { useState } from "react";
import { correctFact } from "../api";
import { useT } from "../i18n";

const FIELDS_BY_TYPE = {
  medication: ["name", "dose", "frequency", "action", "event_date", "status"],
  lab_test: ["name", "value", "unit", "event_date", "status"],
  allergy: ["name", "value", "event_date", "status"],
  condition: ["name", "event_date", "status"],
  event: ["name", "event_date", "status"],
  demographic: ["value"],
};

// the saved value stays in English; only the label shown follows the language
const CHOICES = {
  status: ["documented", "negated"],
  action: ["started", "continued", "changed", "stopped", "mentioned"],
};
const CHOICE_LABEL = { status: "chip", action: "action" };

export default function CorrectionForm({ fact, user, onCorrected }) {
  const t = useT();
  const fields = FIELDS_BY_TYPE[fact.type] || ["name"];
  const [field, setField] = useState(fields[0]);
  const [newValue, setNewValue] = useState(fact[fields[0]] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null); // {field, oldValue, newValue}

  const fieldLabel = (f) => t(`field.${f}`, null, f.replace("_", " "));

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
      <h3>{t("correct.title")}</h3>
      <form onSubmit={handleSave} className="correction-form">
        <select value={field} onChange={(e) => chooseField(e.target.value)}>
          {fields.map((f) => (
            <option key={f} value={f}>
              {fieldLabel(f)}
            </option>
          ))}
        </select>
        {CHOICES[field] ? (
          <select value={newValue} onChange={(e) => setNewValue(e.target.value)}>
            {CHOICES[field].map((c) => (
              <option key={c} value={c}>
                {t(`${CHOICE_LABEL[field]}.${c}`, null, c)}
              </option>
            ))}
          </select>
        ) : (
          <input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder={field === "event_date" ? "YYYY-MM-DD" : t("correct.newValue")}
          />
        )}
        <button type="submit" disabled={busy || unchanged || !newValue.trim()}>
          {busy ? t("correct.saving") : t("correct.save")}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      {done && (
        <table className="side-by-side">
          <thead>
            <tr>
              <th>{fieldLabel(done.field)}</th>
              <th>{t("correct.original")}</th>
              <th>{t("correct.corrected")}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td />
              <td>{String(done.oldValue ?? t("correct.empty"))}</td>
              <td>{String(done.newValue ?? t("correct.empty"))}</td>
            </tr>
          </tbody>
        </table>
      )}
      {done && <p className="hint">{t("correct.by", { user: user.username, role: t(`role.${user.role}`) })}</p>}
    </div>
  );
}
