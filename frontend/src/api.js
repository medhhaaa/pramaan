// The ONLY file that talks to the backend.
// USE_DUMMY = true: answers come from src/dummy/data.js (no backend needed).
// When the backend is ready: set VITE_USE_DUMMY=false in .env.local. Nothing else changes.
import {
  USERS, PATIENTS, P1_FACTS, DOCUMENTS, QUESTIONS_P1, METRICS, AUDIT_ROWS,
} from './dummy/data.js';
import DUMMY_CLAIM_CHECKLIST from './dummy/claim_checklist.json';

const USE_DUMMY = import.meta.env.VITE_USE_DUMMY !== 'false';
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Token lives in sessionStorage (not localStorage): it survives a page refresh but is gone
// when the tab is closed.
const TOKEN_KEY = 'pramaan_token';
function readSession(key) {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
let token = readSession(TOKEN_KEY);
export const setToken = (t) => {
  token = t;
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* storage blocked: keep it in memory only */ }
};
export const hasToken = () => Boolean(token);

async function http(method, path, body, isForm = false) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  if (!res.ok) {
    // show the backend's own message ("Please upload a PDF or a photo...") when it sends one
    let detail = '';
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' && detail ? detail : `HTTP ${res.status}`);
  }
  return res.json();
}

const wait = (ms = 250) => new Promise((r) => setTimeout(r, ms));

// ---- helpers for dummy mode (same rules the backend will use) ----
const facts = (pid) => P1_FACTS.filter((f) => f.patient_id === pid && !f.held_back);

function groupMedications(pid) {
  const meds = facts(pid).filter((f) => f.type === 'medication');
  const byName = {};
  meds.forEach((f) => { (byName[f.name] ||= []).push(f); });
  return Object.entries(byName).map(([name, list]) => {
    const sorted = [...list].sort((a, b) => (a.event_date > b.event_date ? 1 : -1));
    const latest = sorted[sorted.length - 1];
    const fresh = sorted.filter((f) => !f.echo_of);
    return {
      name,
      current: latest.action !== 'stopped',
      last_fresh_evidence_date: fresh.length ? fresh[fresh.length - 1].event_date : null,
      echo_count: sorted.filter((f) => f.echo_of).length,
      entries: sorted.map((f) => ({
        fact_id: f.fact_id, document_id: f.document_id, date: f.event_date,
        dose: f.dose, frequency: f.frequency, action: f.action, echo_of: f.echo_of,
      })),
    };
  });
}

function groupFlags(pid) {
  const all = P1_FACTS.filter((f) => f.patient_id === pid);
  const out = { contradiction: [], duplicate: [], unit_mismatch: [], ambiguous_date: [], wrong_patient: [], implausible_value: [], gap: [] };
  all.forEach((f) => f.flags.forEach((fl) => out[fl] && out[fl].push(f)));
  if (!all.some((f) => f.type === 'allergy' && f.status === 'documented') && !all.some((f) => f.type === 'allergy')) {
    out.gap.push({ fact_id: `${pid}_gap_allergy`, status: 'not_documented', name: 'Allergy information', document_id: null });
  }
  return out;
}

// ---- API ----

export async function login(username, password) {
  if (USE_DUMMY) {
    await wait();
    const u = USERS[username];
    if (!u || u.password !== password) throw new Error('bad_login');
    token = `dummy-${username}`;
    // demo mode: each demo user's language choice is kept in this browser
    const language = localStorage.getItem(`pramaan_lang:${username}`);
    return { token, role: u.role, name: u.name, username, patientId: u.patientId || null, language };
  }
  const data = await http('POST', '/login', { username, password });
  setToken(data.token);
  // /login has no patientId or name: a patient's own record is the one patient they can see
  let patientId = null;
  let name = data.username;
  if (data.role === 'patient') {
    const [own] = await http('GET', '/patients');
    if (own) { patientId = own.id; name = own.name; }
  }
  return { ...data, name, patientId };
}

// Saves the user's language (en | kn | hi) to their account, so it follows them to any device.
export async function saveLanguage(username, language) {
  if (USE_DUMMY) { localStorage.setItem(`pramaan_lang:${username}`, language); return { language }; }
  return http('PUT', '/me/language', { language });
}

export async function listPatients() {
  if (USE_DUMMY) { await wait(); return PATIENTS; }
  return http('GET', '/patients');
}

export async function getTimeline(pid) {
  if (USE_DUMMY) { await wait(); return facts(pid).sort((a, b) => (a.event_date > b.event_date ? 1 : -1)); }
  return http('GET', `/patients/${pid}/timeline`);
}

export async function getMedications(pid) {
  if (USE_DUMMY) { await wait(); return groupMedications(pid); }
  return http('GET', `/patients/${pid}/medications`);
}

export async function getFlags(pid) {
  if (USE_DUMMY) { await wait(); return groupFlags(pid); }
  return http('GET', `/patients/${pid}/flags`);
}

export async function getBrief(pid) {
  if (USE_DUMMY) {
    await wait();
    const f = facts(pid);
    const latestLab = {};
    f.filter((x) => x.type === 'lab_test').forEach((x) => {
      if (!latestLab[x.name] || x.event_date > latestLab[x.name].event_date) latestLab[x.name] = x;
    });
    return {
      patient: PATIENTS.find((p) => p.id === pid),
      flags: groupFlags(pid),
      current_medicines: groupMedications(pid).filter((m) => m.current),
      allergies: f.filter((x) => x.type === 'allergy'),
      conditions: f.filter((x) => x.type === 'condition'),
      latest_results: Object.values(latestLab),
      key_events: f.filter((x) => x.type === 'event'),
      red_flags: [],
      open_questions: QUESTIONS_P1.filter((q) => q.patient_id === pid && q.status !== 'resolved'),
    };
  }
  return http('GET', `/patients/${pid}/brief`);
}

export async function checkMedicine(pid, name) {
  if (USE_DUMMY) {
    await wait();
    const n = name.trim().toLowerCase();
    const penicillinClass = ['penicillin', 'amoxicillin', 'ampicillin', 'augmentin'];
    const allergy = facts(pid).find((x) => x.type === 'allergy' && x.status === 'documented' && /penicillin/i.test(x.name));
    if (allergy && penicillinClass.some((c) => n.includes(c) || c.includes(n) && n.length > 3)) {
      return { warning: true, text: 'Penicillin allergy documented in 2022 discharge summary (d3). This may conflict with the medicine you typed.', source: allergy.document_id };
    }
    return { warning: false, text: null };
  }
  return http('POST', `/patients/${pid}/check-medicine`, { name });
}

export async function ask(pid, question) {
  if (USE_DUMMY) {
    await wait(400);
    const q = question.toLowerCase();
    const hit = facts(pid).find((x) => q.split(' ').some((w) => w.length > 3 && (x.name || '').toLowerCase().includes(w)));
    if (!hit) return { answer: "The records don't mention this.", citations: [] };
    return { answer: `Documented: ${hit.name}${hit.dose ? ` ${hit.dose}` : ''}${hit.value ? ` ${hit.value}${hit.unit ? ` ${hit.unit}` : ''}` : ''} (${hit.date_raw}).`, citations: [hit.fact_id] };
  }
  return http('POST', `/patients/${pid}/ask`, { question });
}

export async function getQuestions(pid) {
  if (USE_DUMMY) { await wait(); return QUESTIONS_P1.filter((q) => q.patient_id === pid); }
  return http('GET', `/patients/${pid}/questions`);
}

export async function answerQuestion(qid, answer, value = null) {
  if (USE_DUMMY) {
    await wait();
    const q = QUESTIONS_P1.find((x) => x.id === qid);
    if (q) q.status = answer === 'dont_know' || answer === 'skip' ? 'sent_to_doctor' : 'answered';
    return { ...q, answer, value };
  }
  return http('POST', `/questions/${qid}/answer`, { answer, value });
}

export async function correctFact(fid, field, newValue) {
  if (USE_DUMMY) { await wait(); return { fact_id: fid, field, new_value: newValue, corrected: true }; }
  return http('POST', `/facts/${fid}/correct`, { field, new_value: newValue });
}

export async function upload(pid, file) {
  if (USE_DUMMY) {
    await wait(1200);
    return {
      document_id: `${pid}_dnew`, facts_added: 1, held_back: false, reasons: [], dropped: 1,
      doc_type: 'prescription', document_date: '2023-01-15', read_with: 'ocr',
      added: [{ fact_id: `${pid}_dnew_f001`, type: 'medication', name: 'Metformin', dose: '1000mg', frequency: 'BD',
        value: null, unit: null, action: 'changed', status: 'documented', quote: 'Tab. Metformin increased to 1000mg BD',
        page: 1, line: 9, flags: [] }],
      left_out: [{ type: 'medication', name: 'Atenolol', dose: '25mg', frequency: 'OD', value: null, unit: null,
        quote: 'Tab. Atenolol 50mg OD', reason: 'dose_not_in_line' }],
      not_captured: [{ page: 1, line: 12, text: 'Tab. Amlodipine 5mg OD - start' }],
    };
  }
  const form = new FormData();
  form.append('file', file);
  return http('POST', `/patients/${pid}/upload`, form, true);
}

export async function getDocument(did) {
  if (USE_DUMMY) {
    await wait();
    const d = DOCUMENTS[did];
    if (!d) return { id: did, filename: 'Sample document', lines: [], pdf_base64: null };
    return { ...d, pdf_base64: null };
  }
  return http('GET', `/documents/${did}`);
}

export async function getMetrics() {
  if (USE_DUMMY) { await wait(); return METRICS; }
  return http('GET', '/metrics');
}

export async function getAudit(pid) {
  if (USE_DUMMY) { await wait(); return AUDIT_ROWS.filter((r) => !pid || r.patient === pid); }
  return http('GET', `/patients/${pid}/audit`);
}

export async function deletePatient(pid) {
  if (USE_DUMMY) { await wait(); return { ok: true, patient_id: pid }; }
  return http('DELETE', `/patients/${pid}`);
}

// NEW ROUTES, not in CLAUDE.md yet. Agree with the core backend owner before merging.
export async function createQR(pid) {
  if (USE_DUMMY) {
    await wait(200);
    return { token: `demo-${pid}-${Date.now()}`, expires_at: Date.now() + 10 * 60 * 1000 };
  }
  const res = await http('POST', `/patients/${pid}/share`, { minutes: 15 });
  // the screens use expires_at as a millisecond timestamp
  return { ...res, expires_at: Date.parse(res.expires_at) };
}

export async function scanQR(code) {
  if (USE_DUMMY) {
    await wait(500);
    if (!code || !code.startsWith('demo-')) throw new Error('expired');
    return { session_id: 'demo-session', patient_id: code.split('-')[1], expires_at: Date.now() + 30 * 60 * 1000 };
  }
  // a scanned QR holds the long token; a typed code is 8 letters/digits, e.g. K7P3-QXM9
  const value = (code || '').trim();
  const isCode = value.replace(/[^a-z0-9]/gi, '').length === 8;
  const res = await http('POST', '/share/open', isCode ? { code: value } : { token: value });
  return { ...res, patient_id: res.patient.id, expires_at: Date.parse(res.expires_at) };
}

// ---- Claim Documents (backend/routes/claims.py) ----
// Documents COMMONLY needed for a reimbursement claim after a hospital stay, and which ones
// are already saved. No claim decision of any kind. Dummy mode shows Ravi's sample checklist.

async function httpBlob(path) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

let dummyStays = [{ ...DUMMY_CLAIM_CHECKLIST.stay }];

// -> [{id, admitted_on, discharged_on, surgery, implant_used, accident, my_reminder_date,
//      created_at, summary: {saved_count, required_count, unsure_count}}] newest first
export async function getHospitalStays(pid) {
  if (USE_DUMMY) { await wait(); return dummyStays.map((s) => ({ ...s, summary: DUMMY_CLAIM_CHECKLIST.summary })); }
  return http('GET', `/patients/${pid}/hospital-stays`);
}

// patient: "I had a hospital stay" -> the new stay
export async function createHospitalStay(pid) {
  if (USE_DUMMY) {
    await wait();
    const stay = { ...DUMMY_CLAIM_CHECKLIST.stay, id: dummyStays.length + 1, admitted_on: null, discharged_on: null };
    dummyStays = [stay, ...dummyStays];
    return stay;
  }
  return http('POST', `/patients/${pid}/hospital-stays`, {});
}

// patient: {admitted_on, discharged_on, my_reminder_date} as YYYY-MM-DD or '' -> the stay
export async function updateHospitalStay(pid, stayId, changes) {
  if (USE_DUMMY) {
    await wait();
    dummyStays = dummyStays.map((s) => (s.id === stayId ? { ...s, ...changes } : s));
    return dummyStays.find((s) => s.id === stayId);
  }
  return http('PATCH', `/patients/${pid}/hospital-stays/${stayId}`, changes);
}

// -> {stay, items: [{doc, label, when, status, documents}], summary, also_keep_ready,
//     reminder: {show, docs}, condition_questions: {surgery: {id, status}, ...}, note}
export async function getClaimChecklist(pid, stayId) {
  if (USE_DUMMY) {
    await wait();
    return { ...DUMMY_CLAIM_CHECKLIST, stay: dummyStays.find((s) => s.id === stayId) || dummyStays[0] };
  }
  return http('GET', `/patients/${pid}/hospital-stays/${stayId}/claim-checklist`);
}

// -> zip Blob: saved documents in checklist order + checklist.txt
export async function downloadClaimPack(pid, stayId) {
  if (USE_DUMMY) throw new Error('needs_backend');
  return httpBlob(`/patients/${pid}/hospital-stays/${stayId}/claim-pack`);
}

export const isDummy = USE_DUMMY;
