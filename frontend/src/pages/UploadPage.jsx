// Upload documents for a patient: PDFs, scans or phone photos. Files go up one at a time so each gets its own result.
import { useState } from "react";
import { uploadDocument } from "../api";
import { useT } from "../i18n";

export default function UploadPage({ patient, onDone }) {
  const t = useT();
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
      <h1>{t("upload.title", { name: patient.name })}</h1>
      <p>{t("upload.intro")}</p>
      <input
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/webp"
        multiple
        onChange={(e) => setFiles([...e.target.files])}
      />
      <p className="actions">
        <button className="btn-primary" onClick={handleUpload} disabled={busy || files.length === 0}>
          {busy
            ? t("upload.busy")
            : files.length === 0
              ? t("upload.buttonNone")
              : files.length === 1
                ? t("upload.buttonOne")
                : t("upload.buttonMany", { n: files.length })}
        </button>
      </p>

      {results.length > 0 && (
        <ul className="list upload-results">
          {results.map((r, i) => (
            <li key={i}>
              <span>{r.name}</span>
              {r.error ? (
                <span className="error">{t("upload.failed", { error: r.error })}</span>
              ) : r.held_back ? (
                <span className="warn">
                  {t("upload.heldBack", { n: r.facts_added })}
                  {r.reasons?.length > 0 && <> {t("upload.why", { reasons: r.reasons.join("; ") })}</>}
                </span>
              ) : (
                <span className="ok">{t("upload.added", { n: r.facts_added })}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {!busy && results.length > 0 && <button className="btn-secondary" onClick={onDone}>{t("upload.viewTimeline")}</button>}
    </section>
  );
}
