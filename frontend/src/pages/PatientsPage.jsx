// The backend returns only the patients this user may see:
// the doctor gets everyone, a patient gets only themself.
import { useEffect, useState } from "react";
import { getPatients } from "../api";
import { useT } from "../i18n";

export default function PatientsPage({ user, onOpen }) {
  const t = useT();
  const [patients, setPatients] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getPatients().then(setPatients).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!patients) return <p>{t("loading")}</p>;

  return (
    <section>
      <h1>{user.role === "doctor" ? t("nav.patients") : t("nav.myRecords")}</h1>
      {patients.length === 0 && <p>{t("patients.none")}</p>}
      <ul className="list patient-list">
        {patients.map((p) => (
          <li key={p.id}>
            <div>
              <strong>{p.name}</strong>
              <small>
                {" "}
                {t("patient.meta", { sex: p.sex, dob: p.dob, blood: p.blood_group })}
              </small>
            </div>
            <span className="card-actions">
              {user.role === "doctor" ? (
                <button className="btn-primary" onClick={() => onOpen(p, "brief")}>{t("tab.brief")}</button>
              ) : (
                <button className="btn-primary" onClick={() => onOpen(p, "questions")}>{t("tab.questions")}</button>
              )}{" "}
              <button className="btn-secondary" onClick={() => onOpen(p, "timeline")}>{t("tab.timeline")}</button>{" "}
              <button onClick={() => onOpen(p, "upload")}>{t("tab.upload")}</button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
