// Dummy data for the care team screens (shape of backend/routes/care_team.py). Synthetic only.
const daysAgo = (n, hour = 10) => {
  const d = new Date(Date.now() - n * 86400000);
  return `${d.toISOString().slice(0, 10)} ${String(hour).padStart(2, '0')}:00:00`;
};

export const CONDITION_TAGS = [
  { tag: 'diabetes', label: 'Diabetes' },
  { tag: 'hypertension', label: 'High blood pressure' },
  { tag: 'heart', label: 'Heart' },
  { tag: 'thyroid', label: 'Thyroid' },
  { tag: 'asthma', label: 'Asthma and breathing' },
  { tag: 'kidney', label: 'Kidney' },
];

export const DOCTORS = [
  { id: 10, name: 'Dr. Rao', registration_number: 'KMC 63105' },
  { id: 11, name: 'Dr. Suresh Kotian', registration_number: 'KMC 51907' },
  { id: 1, name: 'Dr. Demo', registration_number: 'KMC 10001' },
];

export const CARE_TEAM = [
  {
    id: 1, doctor: DOCTORS[0], scope: 'all', scope_labels: 'all', status: 'active',
    created_at: daysAgo(120), revoked_at: null, last_viewed_at: daysAgo(5, 11), review_due: false,
  },
  {
    id: 2, doctor: DOCTORS[1], scope: ['hypertension'], scope_labels: ['High blood pressure'], status: 'active',
    created_at: daysAgo(220), revoked_at: null, last_viewed_at: daysAgo(200, 11), review_due: true,
  },
];

export const ACCESS_HISTORY = [
  { doctor_id: 10, doctor_name: 'Dr. Rao', day: daysAgo(5).slice(0, 10), last_at: daysAgo(5, 11), actions: 3 },
  { doctor_id: 11, doctor_name: 'Dr. Suresh Kotian', day: daysAgo(200).slice(0, 10), last_at: daysAgo(200, 11), actions: 1 },
];

export const MY_PATIENTS = [
  { patient_id: 'p8', name: 'Meena Shenoy', age: 60, sex: 'F', scope: ['diabetes'], conditions: ['Type 2 diabetes mellitus'],
    tags: ['refill_request'], refill_request_id: 1, adherence_14d: 79, followup_on: null, last_activity: daysAgo(0, 8), last_viewed_at: daysAgo(3, 11) },
  { patient_id: 'p1', name: 'Sunita Rao', age: 74, sex: 'F', scope: 'all', conditions: ['Type 2 diabetes mellitus', 'Hypertension'],
    tags: ['new_report'], adherence_14d: null, followup_on: null, last_activity: daysAgo(1), last_viewed_at: daysAgo(5, 11) },
  { patient_id: 'p2', name: 'Mohammed Iqbal', age: 60, sex: 'M', scope: ['hypertension'], conditions: ['Essential hypertension'],
    tags: ['missed_doses'], adherence_14d: 57, followup_on: null, last_activity: daysAgo(1, 21), last_viewed_at: daysAgo(4, 11) },
  { patient_id: 'p3', name: 'Lakshmi Hegde', age: 47, sex: 'F', scope: 'all', conditions: ['Primary hypothyroidism'],
    tags: ['followup_overdue'], adherence_14d: null, followup_on: daysAgo(5).slice(0, 10), last_activity: daysAgo(30), last_viewed_at: daysAgo(20, 11) },
  { patient_id: 'p4', name: "Arjun D'Souza", age: 25, sex: 'M', scope: 'all', conditions: ['Bronchial asthma'],
    tags: ['stable'], adherence_14d: null, followup_on: null, last_activity: daysAgo(30), last_viewed_at: daysAgo(2, 11) },
];
