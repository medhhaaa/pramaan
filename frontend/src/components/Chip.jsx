// Small coloured label for flags, badges and status. Colour comes from the CSS class.
const LABELS = {
  // flags
  contradiction: "contradiction",
  duplicate: "duplicate",
  unit_mismatch: "unit mismatch",
  ambiguous_date: "ambiguous date",
  wrong_patient: "wrong patient?",
  implausible_value: "implausible value",
  handwriting: "extracted from handwriting",
  // badges
  doctor_verified: "doctor verified",
  independent_2plus: "2+ documents",
  single_document: "single document",
  patient_reported: "patient reported",
  conflicting: "conflicting",
  // status
  documented: "documented",
  negated: "explicitly negative",
  not_documented: "not documented",
};

export default function Chip({ kind, value }) {
  return <span className={`chip chip-${kind} chip-${value}`}>{LABELS[value] || value}</span>;
}
