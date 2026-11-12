// 60-second doctor brief, Check-a-medicine, and the Open Questions sidebar.
// Every line shows where it came from. Values are exactly as written.
import { useCallback, useEffect, useState } from "react";
import { getBrief } from "../api";
import CheckMedicine from "../components/CheckMedicine";
import OpenQuestionsSidebar from "../components/OpenQuestionsSidebar";
import { docTypeLabel } from "../format";
import { useT } from "../i18n";

// "prescription 2019-03-12" with the exact quote on hover
function Source({ source }) {
  const t = useT();
  if (!source) return null;
  const kind = docTypeLabel(source.doc_type, t);
  return (
    <small className="source" title={source.quote ? `"${source.quote}"` : ""}>
      {" "}
      ({kind} {source.document_date})
    </small>
  );
}

export default function BriefPage({ patient, user }) {
  const t = useT();
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    getBrief(patient.id).then(setBrief).catch((err) => setError(err.message));
  }, [patient.id, t.lang]); // red flags and questions come from the backend in the user's language

  useEffect(load, [load]);

  return (
    <section className="with-sidebar">
      <div>
        <h1>{t("brief.title", { name: patient.name })}</h1>
        {error && <p className="error">{error}</p>}
        {!brief && !error && <p>{t("loading")}</p>}
        {brief && (
          <>
            <p className="hint">
              {t("patient.meta", { sex: brief.patient.sex, dob: brief.patient.dob, blood: brief.patient.blood_group })}.{" "}
              {t("brief.hover")}
            </p>

            <CheckMedicine patient={patient} />

            {brief.red_flags.length > 0 && (
              <div className="brief-block brief-red">
                <h2>{t("brief.redFlags", { n: brief.red_flags.length })}</h2>
                <ul>
                  {brief.red_flags.map((f, i) => (
                    <li key={i}>
                      <strong>{t(`chip.${f.flag}`, null, f.flag.replace("_", " "))}:</strong> {f.text}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="brief-grid">
              <div className="brief-block">
                <h2>{t("brief.currentMeds")}</h2>
                <p className="hint">{t("brief.currentHint")}</p>
                <ul>
                  {brief.current_medicines.map((m) => (
                    <li key={m.name} className={m.only_copies_since ? "warn" : ""}>
                      <strong>{m.name}</strong> {[m.dose, m.frequency].filter(Boolean).join(" ")}
                      <Source source={m.source} />
                      {m.only_copies_since && (
                        <div>
                          <small>{t("brief.onlyCopies", { date: m.only_copies_since, n: m.echo_count })}</small>
                        </div>
                      )}
                    </li>
                  ))}
                  {brief.current_medicines.length === 0 && <li>{t("noneInRecords")}</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>{t("brief.allergies")}</h2>
                <ul>
                  {brief.allergies.map((a) => (
                    <li key={a.source.fact_id} className={a.conflicting ? "warn" : ""}>
                      {a.status === "negated" ? (
                        <>{t("brief.recordsSay", { quote: a.source.quote })}</>
                      ) : (
                        <>
                          <strong>{a.name}</strong>
                          {a.reaction && ` (${a.reaction})`}
                        </>
                      )}
                      <Source source={a.source} />
                      {a.conflicting && <small> · {t("chip.conflicting")}</small>}
                    </li>
                  ))}
                  {brief.allergies.length === 0 && (
                    <li className="warn">{t("brief.allergiesNotDoc")}</li>
                  )}
                </ul>
              </div>

              <div className="brief-block">
                <h2>{t("brief.conditions")}</h2>
                <ul>
                  {brief.conditions.map((c) => (
                    <li key={c.name}>
                      <strong>{c.name}</strong>
                      <small>
                        {" "}
                        · {t("brief.condDates", { first: c.first_date, last: c.last_date })}
                      </small>
                    </li>
                  ))}
                  {brief.conditions.length === 0 && <li>{t("noneInRecords")}</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>{t("brief.results")}</h2>
                <ul>
                  {brief.latest_results.map((r) => (
                    <li key={r.name}>
                      <strong>{r.name}</strong> {r.value} {r.unit} <small>({r.date})</small>
                      {r.previous && (
                        <small>
                          {" "}
                          · {t("brief.before", { value: r.previous.value, unit: r.previous.unit, date: r.previous.date })}
                        </small>
                      )}
                      {r.flags.includes("unit_mismatch") && <small className="warn"> · {t("brief.unitsDiffer")}</small>}
                    </li>
                  ))}
                  {brief.latest_results.length === 0 && <li>{t("noneInRecords")}</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>{t("brief.events")}</h2>
                <ul>
                  {brief.events.map((e) => (
                    <li key={e.source.fact_id}>
                      <strong>{e.name}</strong> <small>({e.date})</small>
                      <Source source={e.source} />
                    </li>
                  ))}
                  {brief.events.length === 0 && <li>{t("noneInRecords")}</li>}
                </ul>
              </div>
            </div>
          </>
        )}
      </div>
      <OpenQuestionsSidebar patient={patient} user={user} onChange={load} />
    </section>
  );
}
