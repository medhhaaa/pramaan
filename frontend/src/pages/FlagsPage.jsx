// Flagged facts grouped by flag type. Clicking a fact opens its source (click-to-proof).
import { useEffect, useState } from "react";
import { FLAG_TYPES, getFlags } from "../api";
import ProofPanel from "../components/ProofPanel";
import { describeWithStatus, typeLabel } from "../format";

const EXPLAIN = {
  contradiction: "Documents disagree with each other.",
  duplicate: "The same result appears in more than one document.",
  unit_mismatch: "The same test is recorded in different units. Values are shown as written, never converted.",
  ambiguous_date: "The date could be read two ways (e.g. 04/05/2023).",
  wrong_patient: "This document may belong to someone else. It is held back from the timeline.",
  implausible_value: "This value looks impossible; it may be a unit or typing error. The original is unchanged.",
  handwriting: "Read from handwriting by an AI model running on this computer. Check it against the original image before relying on it.",
  gap: "Basic information the records never mention. Not documented does not mean absent.",
};

export default function FlagsPage({ patient }) {
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    getFlags(patient.id).then(setGroups).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!groups) return <p>Loading...</p>;

  // known flag types in a fixed order, then anything new the backend sends
  const types = [...FLAG_TYPES, ...Object.keys(groups).filter((t) => !FLAG_TYPES.includes(t))];
  // a fact can carry several flags, so count each fact once
  const total = new Set(types.flatMap((t) => (groups[t] || []).map((f) => f.fact_id))).size;

  return (
    <section className={selected ? "with-panel" : ""}>
      <div>
        <h1>Things flagged: {patient.name}</h1>
        <p className="hint">{total} flagged facts. Click one to see its source line.</p>
        {types.map((type) => {
          const facts = groups[type] || [];
          return (
            <div key={type} className={`flag-group flag-group-${type}`}>
              <h2>
                {type.replace("_", " ")} <small>({facts.length})</small>
              </h2>
              <p className="hint">{EXPLAIN[type] || ""}</p>
              {facts.length === 0 ? (
                <p className="hint">None found.</p>
              ) : (
                <ul className="facts">
                  {facts.map((f) => (
                    <li
                      key={f.fact_id}
                      className={`fact ${selected?.fact_id === f.fact_id ? "fact-selected" : ""}`}
                      onClick={() => setSelected(f)}
                    >
                      <span className="fact-type">{typeLabel(f.type)}</span>
                      {describeWithStatus(f)}
                      <div className="fact-meta">
                        {f.event_date || "date not documented"} · {f.document_id}
                        {f.quote && <> · "{f.quote}"</>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      {selected?.quote && (
        <ProofPanel key={selected.document_id} fact={selected} onClose={() => setSelected(null)} />
      )}
    </section>
  );
}
