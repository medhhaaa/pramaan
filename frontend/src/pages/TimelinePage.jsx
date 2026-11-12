// Facts grouped by year of event_date. Clicking a fact opens its source (click-to-proof).
import { useEffect, useMemo, useState } from "react";
import { getTimeline } from "../api";
import FactCard from "../components/FactCard";
import ProofPanel from "../components/ProofPanel";

function groupByYear(facts) {
  const groups = {};
  for (const fact of facts) {
    const year = fact.event_date ? fact.event_date.slice(0, 4) : "Date not documented";
    (groups[year] ||= []).push(fact);
  }
  // newest year first; undated facts last
  return Object.entries(groups).sort(([a], [b]) => {
    if (a === "Date not documented") return 1;
    if (b === "Date not documented") return -1;
    return b.localeCompare(a);
  });
}

export default function TimelinePage({ patient, user }) {
  const [facts, setFacts] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  function handleCorrected(updated) {
    setFacts((prev) => prev.map((f) => (f.fact_id === updated.fact_id ? updated : f)));
    setSelected(updated);
  }

  useEffect(() => {
    getTimeline(patient.id).then(setFacts).catch((err) => setError(err.message));
  }, [patient.id]);

  const byId = useMemo(() => Object.fromEntries((facts || []).map((f) => [f.fact_id, f])), [facts]);

  if (error) return <p className="error">{error}</p>;
  if (!facts) return <p>Loading...</p>;

  return (
    <section className={selected ? "with-panel" : ""}>
      <div>
        <h1>Timeline: {patient.name}</h1>
        <p className="hint">
          {facts.length} facts. Faded entries are copies of an older document, not new evidence.
          Click any fact to see the exact line it came from.
        </p>
        {facts.length === 0 && <p>No facts yet. Upload documents to build the timeline.</p>}
        {groupByYear(facts).map(([year, yearFacts]) => (
          <div key={year} className="year-group">
            <h2 className="year-heading">{year}</h2>
            <ul className="facts">
              {yearFacts.map((fact) => (
                <FactCard
                  key={fact.fact_id}
                  fact={fact}
                  original={fact.echo_of ? byId[fact.echo_of] : null}
                  selected={selected?.fact_id === fact.fact_id}
                  onSelect={setSelected}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
      {selected && (
        <ProofPanel
          key={selected.document_id}
          fact={selected}
          user={user}
          onClose={() => setSelected(null)}
          onCorrected={handleCorrected}
        />
      )}
    </section>
  );
}
