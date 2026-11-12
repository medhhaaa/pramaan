// Flagged facts grouped by flag type. Clicking a fact opens its source (click-to-proof).
import { useEffect, useState } from "react";
import { FLAG_TYPES, getFlags } from "../api";
import ProofPanel from "../components/ProofPanel";
import { describeWithStatus, typeLabel } from "../format";
import { useT } from "../i18n";

export default function FlagsPage({ patient }) {
  const t = useT();
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    getFlags(patient.id).then(setGroups).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!groups) return <p>{t("loading")}</p>;

  // known flag types in a fixed order, then anything new the backend sends
  const types = [...FLAG_TYPES, ...Object.keys(groups).filter((t) => !FLAG_TYPES.includes(t))];
  // a fact can carry several flags, so count each fact once
  const total = new Set(types.flatMap((t) => (groups[t] || []).map((f) => f.fact_id))).size;

  return (
    <section className={selected ? "with-panel" : ""}>
      <div>
        <h1>{t("flags.title", { name: patient.name })}</h1>
        <p className="hint">{t("flags.hint", { n: total })}</p>
        {types.map((type) => {
          const facts = groups[type] || [];
          return (
            <div key={type} className={`flag-group flag-group-${type}`}>
              <h2>
                {t(`chip.${type}`, null, type.replace("_", " "))} <small>({facts.length})</small>
              </h2>
              <p className="hint">{t(`explain.${type}`, null, "")}</p>
              {facts.length === 0 ? (
                <p className="hint">{t("flags.noneFound")}</p>
              ) : (
                <ul className="facts">
                  {facts.map((f) => (
                    <li
                      key={f.fact_id}
                      className={`fact ${selected?.fact_id === f.fact_id ? "fact-selected" : ""}`}
                      onClick={() => setSelected(f)}
                    >
                      <span className="fact-type">{typeLabel(f.type, t)}</span>
                      {describeWithStatus(f, t)}
                      <div className="fact-meta">
                        {f.event_date || t("fact.noDate")} · {f.document_id}
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
