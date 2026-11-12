// Audit log: every view and change of this patient's data, newest first.
import { useEffect, useState } from "react";
import { getAudit } from "../api";
import { useT } from "../i18n";

export default function AuditPage({ patient }) {
  const t = useT();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAudit(patient.id).then(setRows).catch((err) => setError(err.message));
  }, [patient.id]);

  if (error) return <p className="error">{error}</p>;
  if (!rows) return <p>{t("loading")}</p>;

  return (
    <section>
      <h1>{t("audit.title", { name: patient.name })}</h1>
      <p className="hint">{t("audit.hint")}</p>
      {rows.length === 0 ? (
        <p>{t("audit.none")}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("audit.when")}</th>
              <th>{t("audit.who")}</th>
              <th>{t("audit.action")}</th>
              <th>{t("audit.detail")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.created_at}</td>
                <td>
                  {r.username || t("audit.unknown")} {r.role && <small>({t(`role.${r.role}`, null, r.role)})</small>}
                </td>
                <td>{t(`auditAction.${r.action}`, null, r.action.replaceAll("_", " "))}</td>
                <td>{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
