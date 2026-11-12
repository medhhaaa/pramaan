// Extraction precision / recall against the answer keys, as Recharts bar charts.
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getMetrics } from "../api";
import { typeLabel } from "../format";
import { useT } from "../i18n";

const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "-");

// {p1: {precision, recall, f1}, ...} -> [{name: "p1", precision, recall, f1}, ...]
const toRows = (obj, label = (name) => name.replace("_", " ")) =>
  Object.entries(obj || {}).map(([name, m]) => ({ name: label(name), ...m }));

function ScoreChart({ title, rows }) {
  const t = useT();
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
          <Bar dataKey="precision" name={t("metrics.precision")} fill="#1f3b57" />
          <Bar dataKey="recall" name={t("metrics.recall")} fill="#4f8fc0" />
          <Bar dataKey="f1" name={t("metrics.f1")} fill="#9cc3e0" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function MetricsPage() {
  const t = useT();
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics().then(setMetrics).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!metrics) return <p>{t("loading")}</p>;

  const { overall = {} } = metrics;

  return (
    <section>
      <h1>{t("metrics.title")}</h1>
      <p className="hint">{t("metrics.hint")}</p>
      {metrics.note && <p className="warn">{metrics.note}</p>}
      <div className="stats">
        <div>
          <strong>{pct(overall.precision)}</strong>
          <span>{t("metrics.precision")}</span>
        </div>
        <div>
          <strong>{pct(overall.recall)}</strong>
          <span>{t("metrics.recall")}</span>
        </div>
        <div>
          <strong>{pct(overall.f1)}</strong>
          <span>{t("metrics.f1")}</span>
        </div>
      </div>
      <ScoreChart title={t("metrics.byType")} rows={toRows(metrics.per_type, (type) => typeLabel(type, t))} />
      <ScoreChart title={t("metrics.byPatient")} rows={toRows(metrics.per_patient)} />
    </section>
  );
}
