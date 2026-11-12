// Every call to the backend goes through this file.
// USE_DUMMY = true  -> return sample data, no backend needed.
// USE_DUMMY = false -> call the real FastAPI backend on localhost:8000.
import sampleFacts from "./dummy/sample_facts.json";

export const USE_DUMMY = true;
const BASE_URL = "http://localhost:8000";

let token = localStorage.getItem("token");

async function request(method, path, body) {
  const res = await fetch(BASE_URL + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status}`);
  return res.json();
}

export async function login(username, password) {
  if (USE_DUMMY) {
    token = "dummy";
    return { token, role: username === "doctor" ? "doctor" : "patient", username };
  }
  const data = await request("POST", "/login", { username, password });
  token = data.token;
  localStorage.setItem("token", token);
  return data;
}

export async function getPatients() {
  if (USE_DUMMY) {
    return [{ id: "p1", name: "Sunita Rao", dob: "1952-06-14", sex: "F", blood_group: "O+" }];
  }
  return request("GET", "/patients");
}

export async function getTimeline(patientId) {
  if (USE_DUMMY) {
    // the backend hides held-back (wrong-patient) documents; mimic that here
    return sampleFacts
      .filter((f) => f.patient_id === patientId && f.document_id !== "p1_d7")
      .sort((a, b) => a.event_date.localeCompare(b.event_date));
  }
  return request("GET", `/patients/${patientId}/timeline`);
}
