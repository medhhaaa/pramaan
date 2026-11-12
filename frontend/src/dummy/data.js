// Dummy data in the fact contract (CLAUDE.md section 5). Synthetic patients only.

export const USERS = {
  doctor: { password: 'doctor123', role: 'doctor', name: 'Dr. Demo', username: 'doctor' },
  sunita: { password: 'sunita123', role: 'patient', name: 'Sunita', username: 'sunita', patientId: 'p1' },
};

export const PATIENTS = [
  { id: 'p1', name: 'Sunita Rao', sex: 'F', dob: '1952-06-14', blood_group: 'O+' },
  { id: 'p2', name: 'Ramesh Shetty', sex: 'M', dob: '1960-02-11', blood_group: 'B+' },
  { id: 'p3', name: 'Asha Kamath', sex: 'F', dob: '1975-09-03', blood_group: 'A+' },
];

const F = (o) => ({
  patient_id: 'p1', value: null, unit: null, action: null, status: 'documented',
  event_date: null, document_date: null, date_raw: null, quote: '', page: 1, line: 1,
  quote_verified: true, echo_of: null, badge: null, flags: [], corrected: false, ...o,
});

// Facts for p1. d6 and d7 are included so the flags page can show them.
export const P1_FACTS = [
  F({ fact_id: 'p1_d1_f001', document_id: 'p1_d1', type: 'condition', name: 'Type 2 diabetes', event_date: '2019-03-12', document_date: '2019-03-12', date_raw: '12/03/2019', quote: 'Diagnosis: Type 2 diabetes mellitus', line: 4, badge: 'single_document' }),
  F({ fact_id: 'p1_d1_f002', document_id: 'p1_d1', type: 'medication', name: 'Metformin', dose: '500mg', frequency: 'BD', action: 'started', event_date: '2019-03-12', document_date: '2019-03-12', date_raw: '12/03/2019', quote: 'Tab. Metformin 500mg BD', line: 8, badge: 'single_document' }),
  F({ fact_id: 'p1_d1_f003', document_id: 'p1_d1', type: 'medication', name: 'Atenolol', dose: '50mg', frequency: 'OD', action: 'started', event_date: '2019-03-12', document_date: '2019-03-12', date_raw: '12/03/2019', quote: 'Tab. Atenolol 50mg OD', line: 9, badge: 'single_document' }),
  F({ fact_id: 'p1_d1_f004', document_id: 'p1_d1', type: 'allergy', name: 'Drug allergy', status: 'negated', event_date: '2019-03-12', document_date: '2019-03-12', date_raw: '12/03/2019', quote: 'No known drug allergies', line: 12, flags: ['contradiction'], badge: 'conflicting' }),
  F({ fact_id: 'p1_d2_f001', document_id: 'p1_d2', type: 'lab_test', name: 'HbA1c', value: '7.2', unit: '%', event_date: '2021-06-20', document_date: '2021-06-20', date_raw: '2021-06-20', quote: 'HbA1c 7.2 %', line: 6, badge: 'single_document' }),
  F({ fact_id: 'p1_d2_f002', document_id: 'p1_d2', type: 'lab_test', name: 'Fasting glucose', value: '6.8', unit: 'mmol/L', event_date: '2021-06-20', document_date: '2021-06-20', date_raw: '2021-06-20', quote: 'Fasting glucose 6.8 mmol/L', line: 7, flags: ['unit_mismatch'], badge: 'single_document' }),
  F({ fact_id: 'p1_d3_f001', document_id: 'p1_d3', type: 'allergy', name: 'Penicillin', status: 'documented', action: null, event_date: '2022-08-05', document_date: '2022-08-05', date_raw: '05-Aug-2022', quote: 'Allergy: Penicillin (rash)', line: 5, flags: ['contradiction'], badge: 'conflicting' }),
  F({ fact_id: 'p1_d3_f002', document_id: 'p1_d3', type: 'condition', name: 'Myocardial infarction (history)', event_date: '2015-01-01', document_date: '2022-08-05', date_raw: 'in 2015', quote: 'History of MI in 2015', line: 9, badge: 'single_document' }),
  F({ fact_id: 'p1_d3_f003', document_id: 'p1_d3', type: 'medication', name: 'Metformin', dose: '500mg', frequency: 'BD', action: 'mentioned', event_date: '2022-08-05', document_date: '2022-08-05', date_raw: '05-Aug-2022', quote: 'Tab. Metformin 500mg BD', line: 14, echo_of: 'p1_d1_f002', badge: null }),
  F({ fact_id: 'p1_d4_f001', document_id: 'p1_d4', type: 'medication', name: 'Metformin', dose: '1000mg', frequency: 'BD', action: 'changed', event_date: '2023-01-15', document_date: '2023-01-15', date_raw: '15/01/2023', quote: 'Metformin increased to 1000mg BD', line: 6, badge: 'single_document' }),
  F({ fact_id: 'p1_d4_f002', document_id: 'p1_d4', type: 'medication', name: 'Atenolol', dose: '50mg', frequency: 'OD', action: 'mentioned', event_date: '2023-01-15', document_date: '2023-01-15', date_raw: '15/01/2023', quote: 'Tab. Atenolol 50mg OD', line: 9, echo_of: 'p1_d1_f003', badge: null }),
  F({ fact_id: 'p1_d4_f003', document_id: 'p1_d4', type: 'medication', name: 'Amlodipine', dose: '5mg', frequency: 'OD', action: 'started', event_date: '2023-01-15', document_date: '2023-01-15', date_raw: '15/01/2023', quote: 'Tab. Amlodipine 5mg OD', line: 10, badge: 'single_document' }),
  F({ fact_id: 'p1_d5_f001', document_id: 'p1_d5', type: 'lab_test', name: 'HbA1c', value: '8.1', unit: '%', event_date: '2023-01-16', document_date: '2023-01-16', date_raw: '16/01/2023', quote: 'HbA1c 8.1 %', line: 5, badge: 'single_document' }),
  F({ fact_id: 'p1_d5_f002', document_id: 'p1_d5', type: 'lab_test', name: 'Fasting glucose', value: '122', unit: 'mg/dL', event_date: '2023-01-16', document_date: '2023-01-16', date_raw: '16/01/2023', quote: 'Fasting glucose 122 mg/dL', line: 6, flags: ['unit_mismatch'], badge: 'single_document' }),
  F({ fact_id: 'p1_d6_f001', document_id: 'p1_d6', type: 'lab_test', name: 'HbA1c', value: '8.1', unit: '%', event_date: '2023-01-16', document_date: '2023-01-16', date_raw: '16/01/2023', quote: 'HbA1c 8.1 %', line: 5, flags: ['duplicate'], badge: null }),
  F({ fact_id: 'p1_d7_f001', document_id: 'p1_d7', type: 'demographic', name: 'blood_group', value: 'B+', event_date: '2023-05-04', document_date: '2023-05-04', date_raw: '04/05/2023', quote: 'Blood group: B+', line: 3, flags: ['wrong_patient', 'ambiguous_date'], badge: null, held_back: true }),
];

export const HELD_BACK_DOCS = ['p1_d7'];

export const DOCUMENTS = {
  p1_d1: { id: 'p1_d1', patient_id: 'p1', filename: 'prescription_2019.pdf', doc_type: 'prescription', document_date: '2019-03-12', held_back: false,
    lines: [
      { page: 1, line: 4, text: 'Diagnosis: Type 2 diabetes mellitus' },
      { page: 1, line: 8, text: 'Tab. Metformin 500mg BD' },
      { page: 1, line: 9, text: 'Tab. Atenolol 50mg OD' },
      { page: 1, line: 12, text: 'No known drug allergies' },
    ] },
  p1_d3: { id: 'p1_d3', patient_id: 'p1', filename: 'discharge_summary_2022.pdf', doc_type: 'discharge_summary', document_date: '2022-08-05', held_back: false,
    lines: [
      { page: 1, line: 5, text: 'Allergy: Penicillin (rash)' },
      { page: 1, line: 9, text: 'History of MI in 2015' },
      { page: 1, line: 14, text: 'Tab. Metformin 500mg BD' },
    ] },
};

export const QUESTIONS_P1 = [
  { id: 'q1', patient_id: 'p1', fact_ids: ['p1_d1_f004', 'p1_d3_f001'], text: 'Do you have a known drug allergy? Your 2019 record says none, and your 2022 record says Penicillin.', status: 'open', source: 'p1_d3' },
  { id: 'q2', patient_id: 'p1', fact_ids: ['p1_d4_f002'], text: 'Are you still taking Atenolol 50mg once daily? It is copied in the 2023 record.', status: 'open', source: 'p1_d4' },
  { id: 'q3', patient_id: 'p1', fact_ids: ['p1_d2_f002'], text: 'Is your fasting glucose reported in mmol/L or mg/dL in your latest test?', status: 'open', source: 'p1_d2' },
];

export const METRICS = {
  overall: { precision: 0.92, recall: 0.88, f1: 0.9 },
  per_patient: { p1: { precision: 0.94, recall: 0.9, f1: 0.92 }, p2: { precision: 0.9, recall: 0.86, f1: 0.88 } },
  per_type: {
    medication: { precision: 0.95, recall: 0.92, f1: 0.93 },
    allergy: { precision: 0.9, recall: 0.85, f1: 0.87 },
    lab_test: { precision: 0.93, recall: 0.9, f1: 0.91 },
    condition: { precision: 0.88, recall: 0.84, f1: 0.86 },
  },
};

export const AUDIT_ROWS = [
  { time: '2026-11-13 09:12', who: 'doctor (doctor)', action: 'scan_session', patient: 'p1', detail: 'Scan access granted' },
  { time: '2026-11-13 09:13', who: 'doctor (doctor)', action: 'view_brief', patient: 'p1', detail: 'Brief opened' },
  { time: '2026-11-13 09:15', who: 'sunita (patient)', action: 'generate_qr', patient: 'p1', detail: 'QR generated, 10 min' },
  { time: '2026-11-12 18:40', who: 'sunita (patient)', action: 'answer_question', patient: 'p1', detail: 'Question q2 answered: yes' },
];

export const PATIENT_RECORD_OUTLINE = { p1: { lastFreshEvidence: '2019-03-12' } };
