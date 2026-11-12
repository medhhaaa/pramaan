// Upload one or more PDFs for a patient. Files go up one at a time so each gets its own result.
import { useState } from "react";
import { uploadDocument } from "../api";

export default function UploadPage({ patient, onDone }) {
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);

  async function handleUpload() {
    setBusy(true);
    setResults([]);
    for (const file of files) {
      try {
        const res = await uploadDocument(patient.id, file);
        setResults((prev) => [...prev, { name: file.name, ...res }]);
      } catch (err) {
        setResults((prev) => [...prev, { name: file.name, error: err.message }]);
      }
    }
    setBusy(false);
  }

  return (
    <section className="upload">
      <h1>Upload documents for {patient.name}</h1>
      <p>Prescriptions, lab reports or discharge summaries, as PDF.</p>
      <input
        type="file"
        accept="application/pdf"
        multiple
        onChange={(e) => setFiles([...e.target.files])}
      />
      <p className="actions">
        <button className="btn-primary" onClick={handleUpload} disabled={busy || files.length === 0}>
          {busy ? "Reading documents..." : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}
        </button>
      </p>

      {results.length > 0 && (
        <ul className="list upload-results">
          {results.map((r, i) => (
            <li key={i}>
              <span>{r.name}</span>
              {r.error ? (
                <span className="error">Failed: {r.error}</span>
              ) : r.held_back ? (
                <span className="warn">
                  Held back: this document may belong to a different patient. A reviewer must
                  confirm it before its {r.facts_added} facts appear.
                </span>
              ) : (
                <span className="ok">{r.facts_added} facts added</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {!busy && results.length > 0 && <button className="btn-secondary" onClick={onDone}>View timeline</button>}
    </section>
  );
}
