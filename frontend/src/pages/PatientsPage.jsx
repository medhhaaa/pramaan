// The backend returns only the patients this user may see:
// the doctor gets everyone, a patient gets only themself.
import { useEffect, useState } from "react";
import { getPatients } from "../api";

export default function PatientsPage({ user, onOpen }) {
  const [patients, setPatients] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getPatients().then(setPatients).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!patients) return <p>Loading...</p>;

  return (
    <section>
      <h1>{user.role === "doctor" ? "Patients" : "My records"}</h1>
      {patients.length === 0 && <p>No patients to show.</p>}
      <ul className="list">
        {patients.map((p) => (
          <li key={p.id}>
            <div>
              <strong>{p.name}</strong>
              <small>
                {" "}
                {p.sex} · born {p.dob} · blood group {p.blood_group}
              </small>
            </div>
            <span>
              {user.role === "doctor" ? (
                <button onClick={() => onOpen(p, "brief")}>Brief</button>
              ) : (
                <button onClick={() => onOpen(p, "questions")}>Things to check</button>
              )}{" "}
              <button onClick={() => onOpen(p, "timeline")}>Timeline</button>{" "}
              <button onClick={() => onOpen(p, "upload")}>Upload</button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
