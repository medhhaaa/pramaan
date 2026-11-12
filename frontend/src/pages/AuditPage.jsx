// Audit log: every view and change of this patient's data, newest first.
import { useEffect, useState } from "react";
import { getAudit } from "../api";

export default function AuditPage({ patient }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAudit(patient.id).then(setRows).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p>Loading...</p>;

  return (
    <section>
      <h1>Audit log: {patient.name}</h1>
      <p className="hint">Who looked at or changed these records, and when.</p>
      {rows.length === 0 ? (
        <p>No entries yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Action</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.created_at}</td>
                <td>
                  {r.username || "unknown"} {r.role && <small>({r.role})</small>}
                </td>
                <td>{r.action.replaceAll("_", " ")}</td>
                <td>{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
