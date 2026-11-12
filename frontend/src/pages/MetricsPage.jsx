// Extraction precision / recall against the answer keys, as Recharts bar charts.
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getMetrics } from "../api";

const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "-");

// {p1: {precision, recall, f1}, ...} -> [{name: "p1", precision, recall, f1}, ...]
const toRows = (obj) => Object.entries(obj || {}).map(([name, m]) => ({ name: name.replace("_", " "), ...m }));

function ScoreChart({ title, rows }) {
  if (rows.length === 0) return null;
  return (
    <div className="chart">
      <h2>{title}</h2>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" />
          <YAxis domain={[0, 1]} tickFormatter={pct} />
          <Tooltip formatter={(v) => pct(v)} />
          <Legend />
          <Bar dataKey="precision" fill="#1f3b57" />
          <Bar dataKey="recall" fill="#4f8fc0" />
          <Bar dataKey="f1" fill="#9cc3e0" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics().then(setMetrics).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!metrics) return <p>Loading...</p>;

  const { overall = {} } = metrics;

  return (
    <section>
      <h1>Extraction accuracy</h1>
      <p className="hint">
        Facts Pramaan extracted, compared with hand-written answer keys for the synthetic patients.
        Precision: how many extracted facts are correct. Recall: how many real facts were found.
      </p>
      {metrics.note && <p className="warn">{metrics.note}</p>}
      <div className="stats">
        <div>
          <strong>{pct(overall.precision)}</strong>
          <span>precision</span>
        </div>
        <div>
          <strong>{pct(overall.recall)}</strong>
          <span>recall</span>
        </div>
        <div>
          <strong>{pct(overall.f1)}</strong>
          <span>F1</span>
        </div>
      </div>
      <ScoreChart title="By fact type" rows={toRows(metrics.per_type)} />
      <ScoreChart title="By patient" rows={toRows(metrics.per_patient)} />
    </section>
  );
}
