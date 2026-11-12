// Delete my data: removes every fact, document, file, question and correction for this patient.
// The user must type DELETE first, because this cannot be undone.
import { useState } from "react";
import { deletePatient } from "../api";

export default function DeletePage({ patient, onDeleted }) {
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
        <h1>Data deleted</h1>
        <p>All records for {patient.name} have been permanently deleted:</p>
        <ul>
          {Object.entries(result.deleted).map(([what, n]) => (
            <li key={what}>
              {n} {what.replace("_", " ")}
            </li>
          ))}
        </ul>
        <button onClick={onDeleted}>Back to patients</button>
      </section>
    );
  }

  return (
    <section>
      <h1>Delete all data for {patient.name}</h1>
      <p>This permanently deletes:</p>
      <ul>
        <li>every uploaded document and its stored file</li>
        <li>every fact extracted from them, and all corrections</li>
        <li>all questions and answers</li>
        <li>the audit history for this patient (one entry recording the deletion is kept)</li>
      </ul>
      <p className="warn">
        <strong>This cannot be undone.</strong>
      </p>
      <label className="form">
        Type DELETE to confirm
        <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
      </label>
      <p>
        <button className="danger" onClick={handleDelete} disabled={busy || confirmText !== "DELETE"}>
          {busy ? "Deleting..." : "Delete everything"}
        </button>
      </p>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
