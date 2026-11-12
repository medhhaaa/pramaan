// Each medicine as start -> change -> stop. Stopped medicines are greyed out,
// copied (echo) entries are marked, and the last real evidence date is shown.
import { useEffect, useState } from "react";
import { getMedications } from "../api";
import { useT } from "../i18n";

function evidenceSummary(med, t) {
  const total = med.entries.length;
  const docs = total === 1 ? t("meds.mentionedOne") : t("meds.mentionedMany", { n: total });
  if (med.echo_count === 0) return `${docs}.`;
  return docs + (med.echo_count === 1 ? t("meds.copiesOne") : t("meds.copiesMany", { n: med.echo_count }));
}

export default function MedicationsPage({ patient }) {
  const t = useT();
  const [meds, setMeds] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMedications(patient.id).then(setMeds).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!meds) return <p>{t("loading")}</p>;

  // current medicines first, then stopped ones
  const sorted = [...meds].sort((a, b) => Number(b.current) - Number(a.current) || a.name.localeCompare(b.name));

  return (
    <section>
      <h1>{t("meds.title", { name: patient.name })}</h1>
      <p className="hint">{t("meds.hint")}</p>
      {sorted.length === 0 && <p>{t("meds.none")}</p>}
      {sorted.map((med) => (
        <div key={med.name} className={`med ${med.current ? "" : "med-stopped"}`}>
          <h2>
            {med.name} <small>{med.current ? t("meds.current") : t("meds.stopped")}</small>
          </h2>
          <p className="hint">
            {evidenceSummary(med, t)}{" "}
            {t("meds.lastEvidence", { date: med.last_fresh_evidence_date || t("meds.noEvidence") })}
          </p>
          <ol className="med-steps">
            {med.entries.map((e) => (
              <li key={e.fact_id} className={e.echo_of ? "med-echo" : ""}>
                <strong>{e.date}</strong> · {t(`action.${e.action || "mentioned"}`, null, e.action)} · {[e.dose, e.frequency].filter(Boolean).join(" ")}
                <small> ({e.document_id})</small>
                {e.echo_of && <small>{t("meds.copyOf", { id: e.echo_of })}</small>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}
