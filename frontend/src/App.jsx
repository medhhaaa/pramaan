// Starter screen: shows patient p1's timeline from api.js.
// Medha replaces this with the real pages in src/pages/.
import { useEffect, useState } from "react";
import { getTimeline } from "./api";

export default function App() {
  const [facts, setFacts] = useState([]);

  useEffect(() => {
    getTimeline("p1").then(setFacts);
  }, []);

  return (
    <main style={{ maxWidth: 800, margin: "0 auto", padding: 16 }}>
      <h1>Pramaan</h1>
      <p>Information from your records only. Not medical advice.</p>
      <ul>
        {facts.map((f) => (
          <li key={f.fact_id}>
            <b>{f.event_date}</b> {f.type}: {f.name} {f.dose || ""} {f.value || ""} {f.unit || ""}
            {f.flags.length > 0 && <em> [{f.flags.join(", ")}]</em>}
            <br />
            <small>"{f.quote}" (page {f.page}, line {f.line})</small>
          </li>
        ))}
      </ul>
    </main>
  );
}
