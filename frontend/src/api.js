// Every call to the backend goes through this file.
// USE_DUMMY = true  -> return sample data, no backend needed.
// USE_DUMMY = false -> call the real FastAPI backend on localhost:8000.
// Response shapes follow KICKOFF.md "Handoffs".
import dummyBrief from "./dummy/brief.json";
import dummyChecks from "./dummy/check_medicine.json";
import dummyDocuments from "./dummy/documents.json";
import dummyMetrics from "./dummy/metrics_results.json";
import dummyQuestionsSeed from "./dummy/questions.json";
import sampleFacts from "./dummy/sample_facts.json";

export const USE_DUMMY = false;
const BASE_URL = "http://localhost:8000";

export const NOT_DOCUMENTED_ANSWER = "The records don't mention this.";
// the Ask route answers in the user's language; both mean "not documented"
export const NOT_DOCUMENTED_ANSWERS = [NOT_DOCUMENTED_ANSWER, "ದಾಖಲೆಗಳಲ್ಲಿ ಇದರ ಬಗ್ಗೆ ಉಲ್ಲೇಖವಿಲ್ಲ."];

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // storage blocked (private window): the app still works for this tab
  }
}

let token = readStorage("token");

// App.jsx only restores a saved login if there is a token to go with it
export function hasSession() {
  return USE_DUMMY || Boolean(token);
}

async function request(method, path, body) {
  const isForm = body instanceof FormData;
  const res = await fetch(BASE_URL + path, {
    method,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  // expired or missing token (not the login call itself): back to the login page
  if (res.status === 401 && path !== "/login") {
    logout();
    writeStorage("user", null);
    window.location.reload();
    throw new Error("Your session has expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail || "";
    } catch {
      // response had no JSON body
    }
    throw new Error(detail || `${method} ${path} failed: ${res.status}`);
  }
  return res.json();
}

// ---------- dummy in-memory state (resets on page reload) ----------

let dummyFacts = structuredClone(sampleFacts);
let dummyQuestions = structuredClone(dummyQuestionsSeed);
let dummyDeleted = new Set();
let dummyUser = null;
const dummyAudit = [
  { id: 1, username: "sunita", role: "patient", action: "upload", detail: "d1_prescription_2019.pdf", created_at: "2026-11-12 09:02:11" },
  { id: 2, username: "doctor", role: "doctor", action: "view_timeline", detail: "", created_at: "2026-11-12 09:15:40" },
];

function dummyLog(patientId, action, detail = "") {
  dummyAudit.push({
    id: dummyAudit.length + 1,
    patient_id: patientId,
    username: dummyUser?.username || "?",
    role: dummyUser?.role || "?",
    action,
    detail,
    created_at: new Date().toISOString().slice(0, 19).replace("T", " "),
  });
}

const heldBackIds = () => new Set(dummyDocuments.filter((d) => d.held_back).map((d) => d.id));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------- login ----------

const DUMMY_USERS = { doctor: "doctor123", sunita: "sunita123" };
const dummyLanguages = {}; // username -> "en" | "kn" (dummy mode forgets on reload)

// -> {token, role, username, language}   language is "en", "kn" or null (not chosen yet)
export async function login(username, password) {
  if (USE_DUMMY) {
    if (DUMMY_USERS[username] !== password) throw new Error("Wrong username or password");
    token = "dummy";
    dummyUser = { username, role: username === "doctor" ? "doctor" : "patient" };
    return { token, ...dummyUser, language: dummyLanguages[username] || null };
  }
  const data = await request("POST", "/login", { username, password });
  token = data.token;
  writeStorage("token", token);
  return data;
}

export function logout() {
  token = null;
  writeStorage("token", null);
}

// App.jsx tells dummy mode who is logged in after a page refresh
export function setDummyUser(user) {
  dummyUser = user;
}

// ---------- language ----------

// "en" | "kn" -> {language}. Saved on the user's account; asked once at first login.
export async function setLanguage(language) {
  if (USE_DUMMY) {
    if (dummyUser) dummyLanguages[dummyUser.username] = language;
    return { language };
  }
  return request("PUT", "/me/language", { language });
}

// ---------- patients ----------

export async function getPatients() {
  if (USE_DUMMY) {
    return [{ id: "p1", name: "Sunita Rao", dob: "1952-06-14", sex: "F", blood_group: "O+" }].filter(
      (p) => !dummyDeleted.has(p.id),
    );
  }
  return request("GET", "/patients");
}

// ---------- timeline ----------

export async function getTimeline(patientId) {
  if (USE_DUMMY) {
    // the backend hides facts from held-back (wrong-patient) documents; mimic that here
    const heldBack = heldBackIds();
    return dummyFacts
      .filter((f) => f.patient_id === patientId && !heldBack.has(f.document_id))
      .sort((a, b) => (a.event_date || "").localeCompare(b.event_date || ""));
  }
  return request("GET", `/patients/${patientId}/timeline`);
}

// ---------- medications ----------

// -> [{name, current, last_fresh_evidence_date, echo_count,
//      entries: [{fact_id, document_id, date, dose, frequency, action, echo_of}]}]
export async function getMedications(patientId) {
  if (USE_DUMMY) {
    const heldBack = heldBackIds();
    const byName = {};
    for (const f of dummyFacts) {
      if (f.patient_id !== patientId || f.type !== "medication" || heldBack.has(f.document_id)) continue;
      (byName[f.name.toLowerCase()] ||= []).push(f);
    }
    return Object.values(byName).map((facts) => {
      const entries = facts
        .sort((a, b) => a.event_date.localeCompare(b.event_date))
        .map((f) => ({
          fact_id: f.fact_id,
          document_id: f.document_id,
          date: f.event_date,
          dose: f.dose,
          frequency: f.frequency,
          action: f.action,
          echo_of: f.echo_of,
        }));
      const fresh = entries.filter((e) => !e.echo_of);
      return {
        name: facts[0].name,
        current: entries[entries.length - 1].action !== "stopped",
        last_fresh_evidence_date: fresh.length ? fresh[fresh.length - 1].date : null,
        echo_count: entries.length - fresh.length,
        entries,
      };
    });
  }
  return request("GET", `/patients/${patientId}/medications`);
}

// ---------- flags ----------

export const FLAG_TYPES = [
  "contradiction",
  "duplicate",
  "unit_mismatch",
  "ambiguous_date",
  "wrong_patient",
  "implausible_value",
  "gap",
];

// -> {"contradiction": [fact], "duplicate": [...], ..., "gap": [...]}
export async function getFlags(patientId) {
  if (USE_DUMMY) {
    const groups = Object.fromEntries(FLAG_TYPES.map((t) => [t, []]));
    for (const f of dummyFacts) {
      if (f.patient_id !== patientId) continue;
      for (const flag of f.flags) (groups[flag] ||= []).push(f);
    }
    return groups;
  }
  return request("GET", `/patients/${patientId}/flags`);
}

// ---------- documents (click-to-proof) ----------

// -> {id, patient_id, filename, doc_type, document_date, held_back, pdf_base64, lines: [{page, line, text, covered}]}
export async function getDocument(documentId) {
  if (USE_DUMMY) {
    const doc = dummyDocuments.find((d) => d.id === documentId);
    if (!doc) throw new Error(`Document ${documentId} not found`);
    // no real PDFs in dummy mode: rebuild the known lines from the sample facts' quotes
    const lines = sampleFacts
      .filter((f) => f.document_id === documentId)
      .map((f) => ({ page: f.page, line: f.line, text: f.quote, covered: true }))
      .sort((a, b) => a.page - b.page || a.line - b.line);
    return { ...doc, pdf_base64: null, lines };
  }
  return request("GET", `/documents/${documentId}`);
}

// ---------- corrections ----------

// body {field, new_value} -> the updated fact (corrected: true). The original stays in the
// corrections table and the quote is never changed.
export async function correctFact(factId, field, newValue) {
  if (USE_DUMMY) {
    const fact = dummyFacts.find((f) => f.fact_id === factId);
    if (!fact) throw new Error(`Fact ${factId} not found`);
    dummyLog(fact.patient_id, "correct_fact", `${factId}.${field}: ${fact[field]} -> ${newValue}`);
    fact[field] = newValue;
    fact.corrected = true;
    // mimics backend/logic/badges.py: a doctor's correction or confirmation -> doctor_verified
    if (dummyUser?.role === "doctor") fact.badge = "doctor_verified";
    return { ...fact };
  }
  return request("POST", `/facts/${factId}/correct`, { field, new_value: newValue });
}

// ---------- upload ----------

// -> {document_id, facts_added, held_back}
export async function uploadDocument(patientId, file) {
  if (USE_DUMMY) {
    await sleep(600);
    dummyLog(patientId, "upload", file.name);
    return {
      document_id: `${patientId}_dummy_${Date.now()}`,
      facts_added: 5,
      held_back: /psa/i.test(file.name), // lets you try the held-back message in dummy mode
    };
  }
  const form = new FormData();
  form.append("file", file);
  return request("POST", `/patients/${patientId}/upload`, form);
}

// ---------- ask my records ----------

// body {question} -> {answer, fact_ids, citations: [fact]}
// answer is exactly one of NOT_DOCUMENTED_ANSWERS when the records don't cover the question.
export async function askRecords(patientId, question) {
  if (USE_DUMMY) {
    await sleep(500);
    dummyLog(patientId, "ask", question);
    // dummy: plain keyword match on fact names (the real route uses the AI)
    // first 5 letters as a rough stem, so "allergic" matches "allergy"
    const words = (question.toLowerCase().match(/[a-z0-9]{4,}/g) || []).map((w) => w.slice(0, 5));
    const heldBack = heldBackIds();
    const hits = dummyFacts.filter(
      (f) =>
        f.patient_id === patientId &&
        !heldBack.has(f.document_id) &&
        words.some((w) => f.name.toLowerCase().includes(w) || f.type.includes(w)),
    );
    if (hits.length === 0) return { answer: NOT_DOCUMENTED_ANSWER, fact_ids: [], citations: [] };
    const answer = hits
      .map((f) => {
        const what = [f.name, f.dose, f.frequency, f.value, f.unit].filter(Boolean).join(" ");
        const neg = f.status === "negated" ? "Recorded as absent: " : "";
        const copy = f.echo_of ? " (copied from an older document)" : "";
        return `${neg}${what} on ${f.event_date}${copy} [${f.fact_id}]`;
      })
      .join(". ");
    return { answer, fact_ids: hits.map((f) => f.fact_id), citations: hits };
  }
  return request("POST", `/patients/${patientId}/ask`, { question });
}

// ---------- audit log ----------

// -> [{id, username, role, action, detail, created_at}] newest first
export async function getAudit(patientId) {
  if (USE_DUMMY) {
    return dummyAudit.filter((a) => !a.patient_id || a.patient_id === patientId).slice().reverse();
  }
  return request("GET", `/patients/${patientId}/audit`);
}

// ---------- delete my data ----------

// -> {deleted: {facts, documents, files, corrections, questions}}
export async function deletePatient(patientId) {
  if (USE_DUMMY) {
    await sleep(400);
    const facts = dummyFacts.filter((f) => f.patient_id === patientId).length;
    dummyFacts = dummyFacts.filter((f) => f.patient_id !== patientId);
    dummyDeleted.add(patientId);
    return { deleted: { facts, documents: 7, files: 0, corrections: 0, questions: 0 } };
  }
  return request("DELETE", `/patients/${patientId}`);
}

// ---------- metrics ----------

// -> {overall: {precision, recall, f1}, per_patient: {...}, per_type: {...}}
export async function getMetrics() {
  if (USE_DUMMY) return dummyMetrics;
  return request("GET", "/metrics");
}

// ---------- Things to Check / Open Questions ----------

export const PATIENT_ANSWERS = ["yes", "no", "value", "dont_know", "skip"];
export const DOCTOR_ANSWERS = ["confirm", "correct", "unclear"];

// -> [{id, text, status, answer, fact_ids, facts: [fact], created_at}]
// status: open | answered | sent_to_doctor | resolved
export async function getQuestions(patientId) {
  if (USE_DUMMY) {
    if (dummyDeleted.has(patientId)) return [];
    // re-attach facts so corrections made in this session show up
    return dummyQuestions.map((q) => ({
      ...q,
      facts: q.fact_ids.map((id) => dummyFacts.find((f) => f.fact_id === id)).filter(Boolean),
    }));
  }
  return request("GET", `/patients/${patientId}/questions`);
}

// patient: yes | no | value | dont_know | skip     doctor: confirm | correct | unclear
// -> the updated question
export async function answerQuestion(questionId, answer, value = null) {
  if (USE_DUMMY) {
    const q = dummyQuestions.find((x) => x.id === questionId);
    if (!q) throw new Error("Question not found");
    const role = dummyUser?.role;
    if (PATIENT_ANSWERS.includes(answer) && role !== "patient")
      throw new Error("Only the patient answers Things to Check.");
    if (DOCTOR_ANSWERS.includes(answer) && role !== "doctor")
      throw new Error("Only a doctor resolves open questions.");
    if (q.status === "resolved") throw new Error("This question is already resolved.");
    if (answer === "value" && !value) throw new Error("Please type a value.");
    q.status = DOCTOR_ANSWERS.includes(answer)
      ? "resolved"
      : ["dont_know", "skip"].includes(answer)
        ? "sent_to_doctor"
        : "answered";
    q.answer = {
      answer,
      value,
      by: dummyUser?.username,
      role,
      at: new Date().toISOString().slice(0, 19).replace("T", " "),
    };
    dummyLog("p1", "answer_question", `question ${questionId}: ${answer}`);
    return (await getQuestions("p1")).find((x) => x.id === questionId);
  }
  return request("POST", `/questions/${questionId}/answer`, { answer, value });
}

// ---------- 60-second doctor brief ----------

// -> {patient, current_medicines, allergies, conditions, latest_results, events,
//     red_flags, open_questions}   (shapes documented in backend/routes/brief.py)
export async function getBrief(patientId) {
  if (USE_DUMMY) {
    const open = dummyQuestions
      .filter((q) => q.status !== "resolved")
      .map(({ id, text, status }) => ({ id, text, status }));
    return { ...dummyBrief, open_questions: open };
  }
  return request("GET", `/patients/${patientId}/brief`);
}

// ---------- check a medicine ----------

// body {drug} -> {drug, generic, drug_class, class_label, known, warnings: [{kind, text, source}], note}
export async function checkMedicine(patientId, drug) {
  if (USE_DUMMY) {
    await sleep(300);
    const key = drug.toLowerCase().match(/[a-z]+/)?.[0] || "";
    const saved = dummyChecks[key];
    if (saved) {
      // like the backend: once a doctor resolved the question about an allergy, say so
      const warnings = saved.warnings.map((saved_w) => {
        // the captured text uses the captured name ("augmentin"); show what was typed
        const w = { ...saved_w, text: saved_w.text.replace(saved.drug, drug) };
        const q = dummyQuestions.find(
          (x) => x.status === "resolved" && x.fact_ids.includes(w.source?.fact_id) && ["confirm", "correct"].includes(x.answer?.answer),
        );
        if (!q) return w;
        const text = w.text.replace(/ Another record says .*not resolved\./, "") + ` Confirmed by ${q.answer.by} on ${q.answer.at.slice(0, 10)}.`;
        return { ...w, text };
      });
      return { ...saved, drug, warnings };
    }
    return {
      drug,
      generic: null,
      drug_class: null,
      class_label: null,
      known: false,
      warnings: [],
      note: "Checked against these records only. This is not prescribing advice.",
    };
  }
  return request("POST", `/patients/${patientId}/check-medicine`, { drug });
}

// ---------- QR / code sharing (core backend: backend/routes/share.py) ----------
// Sharing needs the real backend: there is no dummy version.

const needsBackend = () => {
  throw new Error("Sharing works with the real backend only (USE_DUMMY = false).");
};

// patient: body {minutes} -> {share_id, code, token, url, qr_svg, expires_at, seconds_left}
export async function createShare(patientId, minutes) {
  if (USE_DUMMY) needsBackend();
  return request("POST", `/patients/${patientId}/share`, { minutes });
}

// doctor: {code} or {token} -> {share_id, patient, expires_at, seconds_left}
export async function openShare({ code, token }) {
  if (USE_DUMMY) needsBackend();
  return request("POST", "/share/open", code ? { code } : { token });
}

// patient: -> [{share_id, created_at, expires_at, seconds_left, opened_by, opened_at}]
export async function getShares(patientId) {
  if (USE_DUMMY) return [];
  return request("GET", `/patients/${patientId}/shares`);
}

// patient stops a share early -> {stopped: true}
export async function stopShare(shareId) {
  if (USE_DUMMY) needsBackend();
  return request("DELETE", `/share/${shareId}`);
}
