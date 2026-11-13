// Dummy data for refills, reminders, notifications and consult records (synthetic).
// Same shapes as backend/routes/refills.py and backend/routes/consult_records.py.

const day = (n) => {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
};
const at = (n, hour = 10) => `${day(n)} ${String(hour).padStart(2, '0')}:00:00`;

export const MY_MEDICINES = {
  date: day(0),
  medicines: [{
    prescription_item_id: 1, medicine: 'Metformin', dose: '500mg', frequency: 'BD',
    start_date: day(26), end_date: day(-3), active: true, doctor: 'Dr. Rao', prescribed_at: at(26),
    can_request_refill: false, refill_blocked_reason: 'pending',
    last_refill_request: { status: 'pending', doctor_note: null, created_at: at(0, 8), decided_at: null },
    today: [{ reminder_id: 1, time: '08:00', status: 'taken' }, { reminder_id: 2, time: '20:00', status: null }],
    adherence_14d: 79,
  }],
};

const EVENING_TAKEN = new Set([1, 2, 4, 5, 7, 9, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]);
const EVENING_SKIPPED = new Set([3, 8, 10, 14]);

export const REFILL_REVIEW = {
  patient_id: 'p7',
  refill_request: { id: 1, status: 'pending', patient_note: 'My tablets finish in 4 days.', doctor_note: null,
    created_at: at(0, 8), decided_at: null },
  medicine: { prescription_item_id: 1, medicine: 'Metformin', dose: '500mg', frequency: 'BD', duration_days: 30,
    start_date: day(26), end_date: day(-3), prescribed_at: at(26), first_prescribed_at: at(26), doctor: 'Dr. Rao' },
  adherence_30d: {
    due: 52, taken: 46, skipped: 4, missed: 2, percent: 88,
    days: Array.from({ length: 30 }, (_, i) => {
      const n = 30 - i;
      const due = n <= 26 ? 2 : 0;
      return { date: day(n), due, taken: due ? 1 + (EVENING_TAKEN.has(n) ? 1 : 0) : 0, skipped: due && EVENING_SKIPPED.has(n) ? 1 : 0 };
    }),
  },
  latest_report: { name: 'HbA1c', value: '7.4', unit: '%', date: '2026-08-20', fact_id: 'p7_d2_f003',
    document_id: 'p7_d2', quote: 'HbA1c 7.4 %', page: 1, line: 14 },
  brief: {
    current_medicines: [{ name: 'Metformin', last_fresh_evidence_date: '2026-08-22',
      entries: [{ date: '2024-02-14', dose: '500mg', frequency: 'BD' }, { date: '2026-08-22', dose: '500mg', frequency: 'BD' }] }],
    allergies: [{ fact_id: 'p7_d1_f008', name: 'Sulfa drugs', status: 'documented', document_id: 'p7_d1',
      quote: 'Allergy: Sulfa drugs (skin rash on co-trimoxazole)' }],
    conditions: [{ fact_id: 'p7_d1_f001', name: 'Type 2 diabetes mellitus', badge: 'independent_2plus' }],
    latest_results: [{ fact_id: 'p7_d2_f003', name: 'HbA1c', value: '7.4', unit: '%', date_raw: '20/08/2026' }],
    red_flags: [], open_questions: [],
  },
  warnings: [],
  note: 'Records and checks only. The decision is yours.',
};

export const NOTIFICATIONS = [];

export const CONSULT_RECORDS = [
  { id: 1, type: 'prescription', created_at: at(26), doctor_name: 'Dr. Rao', corrects_record_id: null,
    decision: { action: 'prescribe', prescription_id: 1,
      items: [{ medicine: 'Metformin', dose: '500mg', frequency: 'BD', duration_days: 30 }] } },
];

export const CONSULT_RECORD_1 = {
  id: 1, doctor_id: 9, patient_id: 'p7', type: 'prescription', created_at: at(26), corrects_record_id: null,
  sha256: '3f7c0a1e9b2d4c6f8a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f',
  snapshot: { brief: REFILL_REVIEW.brief, active_in_app_prescriptions: [], source_document_ids: ['p7_d1', 'p7_d2', 'p7_d3'] },
  decision: CONSULT_RECORDS[0].decision, warnings_shown: [], overrides: [],
  doctor: { id: 9, name: 'Dr. Rao', registration_number: 'KMC 63105' },
  patient: { id: 'p7', name: 'Meena Shenoy', dob: '1966-07-02', sex: 'F' },
};
