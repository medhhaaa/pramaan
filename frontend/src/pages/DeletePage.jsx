// Delete my data: removes every fact, document, file, question and correction for this patient.
// The user must type DELETE first, because this cannot be undone.
import { useState } from "react";
import { deletePatient } from "../api";
import { useT } from "../i18n";

export default function DeletePage({ patient, onDeleted }) {
  const t = useT();
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleDelete() {
    setBusy(true);
    setError("");
    try {
      setResult(await deletePatient(patient.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <section>
        <h1>{t("delete.doneTitle")}</h1>
        <p>{t("delete.doneText", { name: patient.name })}</p>
        <ul>
          {Object.entries(result.deleted).map(([what, n]) => (
            <li key={what}>
              {t("delete.count", { n, what: t(`deleted.${what}`, null, what.replace("_", " ")) })}
            </li>
          ))}
        </ul>
        <button className="btn-secondary" onClick={onDeleted}>{t("delete.back")}</button>
      </section>
    );
  }

  return (
    <section className="danger-zone">
      <h1>{t("delete.title", { name: patient.name })}</h1>
      <p>{t("delete.intro")}</p>
      <ul>
        <li>{t("delete.docs")}</li>
        <li>{t("delete.facts")}</li>
        <li>{t("delete.questions")}</li>
        <li>{t("delete.audit")}</li>
      </ul>
      <p className="warn">
        <strong>{t("delete.cannotUndo")}</strong>
      </p>
      <label className="form">
        {t("delete.type")}
        <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
      </label>
      <p className="actions">
        <button className="danger" onClick={handleDelete} disabled={busy || confirmText !== "DELETE"}>
          {busy ? t("delete.busy") : t("delete.button")}
        </button>
      </p>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
