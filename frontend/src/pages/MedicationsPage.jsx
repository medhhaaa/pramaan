// Each medicine as start -> change -> stop. Stopped medicines are greyed out,
// copied (echo) entries are marked, and the last real evidence date is shown.
import { useEffect, useState } from "react";
import { getMedications } from "../api";

function evidenceSummary(med) {
  const total = med.entries.length;
  const docs = `Mentioned in ${total} document${total === 1 ? "" : "s"}`;
  if (med.echo_count === 0) return `${docs}.`;
  return `${docs}, ${med.echo_count} ${med.echo_count === 1 ? "is a copy" : "are copies"} of an older record.`;
}

export default function MedicationsPage({ patient }) {
  const [meds, setMeds] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMedications(patient.id).then(setMeds).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!meds) return <p>Loading...</p>;

  // current medicines first, then stopped ones
  const sorted = [...meds].sort((a, b) => Number(b.current) - Number(a.current) || a.name.localeCompare(b.name));

  return (
    <section>
      <h1>Medications: {patient.name}</h1>
      <p className="hint">
        "Current" means the latest record does not say it was stopped. It is not proof the patient
        is taking it today.
      </p>
      {sorted.length === 0 && <p>No medicines in the records.</p>}
      {sorted.map((med) => (
        <div key={med.name} className={`med ${med.current ? "" : "med-stopped"}`}>
          <h2>
            {med.name} <small>{med.current ? "current" : "stopped"}</small>
          </h2>
          <p className="hint">
            {evidenceSummary(med)} Last real evidence: {med.last_fresh_evidence_date || "none"}.
          </p>
          <ol className="med-steps">
            {med.entries.map((e) => (
              <li key={e.fact_id} className={e.echo_of ? "med-echo" : ""}>
                <strong>{e.date}</strong> · {e.action || "mentioned"} · {[e.dose, e.frequency].filter(Boolean).join(" ")}
                <small> ({e.document_id})</small>
                {e.echo_of && <small> · copy of {e.echo_of}, not new evidence</small>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}
