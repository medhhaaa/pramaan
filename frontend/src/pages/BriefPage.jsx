// 60-second doctor brief, Check-a-medicine, and the Open Questions sidebar.
// Every line shows where it came from. Values are exactly as written.
import { useCallback, useEffect, useState } from "react";
import { getBrief } from "../api";
import CheckMedicine from "../components/CheckMedicine";
import OpenQuestionsSidebar from "../components/OpenQuestionsSidebar";

// "prescription 2019-03-12" with the exact quote on hover
function Source({ source }) {
  if (!source) return null;
  const kind = (source.doc_type || "record").replace("_", " ");
  return (
    <small className="source" title={source.quote ? `"${source.quote}"` : ""}>
      {" "}
      ({kind} {source.document_date})
    </small>
  );
}

export default function BriefPage({ patient, user }) {
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    getBrief(patient.id).then(setBrief).catch((err) => setError(err.message));
  }, [patient.id]);

  useEffect(load, [load]);

  return (
    <section className="with-sidebar">
      <div>
        <h1>Brief: {patient.name}</h1>
        {error && <p className="error">{error}</p>}
        {!brief && !error && <p>Loading...</p>}
        {brief && (
          <>
            <p className="hint">
              {brief.patient.sex} · born {brief.patient.dob} · blood group {brief.patient.blood_group}.
              Hover a source to see the exact line.
            </p>

            <CheckMedicine patient={patient} />

            {brief.red_flags.length > 0 && (
              <div className="brief-block brief-red">
                <h2>Red flags ({brief.red_flags.length})</h2>
                <ul>
                  {brief.red_flags.map((f, i) => (
                    <li key={i}>
                      <strong>{f.flag.replace("_", " ")}:</strong> {f.text}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="brief-grid">
              <div className="brief-block">
                <h2>Current medicines</h2>
                <p className="hint">Latest record doesn't say stopped. Not proof of taking it today.</p>
                <ul>
                  {brief.current_medicines.map((m) => (
                    <li key={m.name} className={m.only_copies_since ? "warn" : ""}>
                      <strong>{m.name}</strong> {[m.dose, m.frequency].filter(Boolean).join(" ")}
                      <Source source={m.source} />
                      {m.only_copies_since && (
                        <div>
                          <small>
                            Last real evidence {m.only_copies_since}; {m.echo_count} later mention(s) are
                            copies.
                          </small>
                        </div>
                      )}
                    </li>
                  ))}
                  {brief.current_medicines.length === 0 && <li>None in the records.</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>Allergies</h2>
                <ul>
                  {brief.allergies.map((a) => (
                    <li key={a.source.fact_id} className={a.conflicting ? "warn" : ""}>
                      {a.status === "negated" ? (
                        <>Records say: "{a.source.quote}"</>
                      ) : (
                        <>
                          <strong>{a.name}</strong>
                          {a.reaction && ` (${a.reaction})`}
                        </>
                      )}
                      <Source source={a.source} />
                      {a.conflicting && <small> · conflicting</small>}
                    </li>
                  ))}
                  {brief.allergies.length === 0 && (
                    <li className="warn">Not documented. That does not mean no allergies.</li>
                  )}
                </ul>
              </div>

              <div className="brief-block">
                <h2>Conditions in the records</h2>
                <ul>
                  {brief.conditions.map((c) => (
                    <li key={c.name}>
                      <strong>{c.name}</strong>
                      <small>
                        {" "}
                        · first {c.first_date}, last mentioned {c.last_date}
                      </small>
                    </li>
                  ))}
                  {brief.conditions.length === 0 && <li>None in the records.</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>Latest results</h2>
                <ul>
                  {brief.latest_results.map((r) => (
                    <li key={r.name}>
                      <strong>{r.name}</strong> {r.value} {r.unit} <small>({r.date})</small>
                      {r.previous && (
                        <small>
                          {" "}
                          · before: {r.previous.value} {r.previous.unit} ({r.previous.date})
                        </small>
                      )}
                      {r.flags.includes("unit_mismatch") && <small className="warn"> · units differ, not converted</small>}
                    </li>
                  ))}
                  {brief.latest_results.length === 0 && <li>None in the records.</li>}
                </ul>
              </div>

              <div className="brief-block">
                <h2>Key events</h2>
                <ul>
                  {brief.events.map((e) => (
                    <li key={e.source.fact_id}>
                      <strong>{e.name}</strong> <small>({e.date})</small>
                      <Source source={e.source} />
                    </li>
                  ))}
                  {brief.events.length === 0 && <li>None in the records.</li>}
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
