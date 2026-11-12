// Shared wording for facts. Values are always shown exactly as written in the document;
// only the words around them (type labels, "No ...", "not documented") follow the language.
// t is the translate function from useT() in i18n.jsx.

// "Metformin 500mg twice daily", "HbA1c 7.2 %", "blood group O+", "Penicillin (rash)"
export function describe(fact, t) {
  if (fact.type === "allergy" && fact.value) return `${fact.name} (${fact.value})`;
  const name =
    fact.type === "demographic" ? t(`demo.${fact.name}`, null, fact.name.replace("_", " ")) : fact.name;
  return [name, fact.dose, fact.frequency, fact.value, fact.unit].filter(Boolean).join(" ");
}

// adds "No ..." for explicitly negative facts ("No known drug allergies")
export function describeWithStatus(fact, t) {
  if (fact.status === "negated") {
    const what = t.lang === "en" ? describe(fact, t).toLowerCase() : describe(fact, t);
    return t("fact.negated", { what });
  }
  if (fact.status === "not_documented") return t("fact.notDocumented", { what: describe(fact, t) });
  return describe(fact, t);
}

export const typeLabel = (type, t) => t(`type.${type}`, null, type.replace("_", " "));

export const docTypeLabel = (docType, t) =>
  t(`docType.${docType || "record"}`, null, (docType || "record").replace("_", " "));
