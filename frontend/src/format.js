// Shared wording for facts. Values are always shown exactly as written in the document.

// "Metformin 500mg twice daily", "HbA1c 7.2 %", "blood group O+", "Penicillin (rash)"
export function describe(fact) {
  if (fact.type === "allergy" && fact.value) return `${fact.name} (${fact.value})`;
  const name = fact.type === "demographic" ? fact.name.replace("_", " ") : fact.name;
  return [name, fact.dose, fact.frequency, fact.value, fact.unit].filter(Boolean).join(" ");
}

// adds "No ..." for explicitly negative facts ("No known drug allergies")
export function describeWithStatus(fact) {
  if (fact.status === "negated") return `No ${describe(fact).toLowerCase()}`;
  if (fact.status === "not_documented") return `${describe(fact)}: not documented`;
  return describe(fact);
}

export const typeLabel = (type) => type.replace("_", " ");
