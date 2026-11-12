// Shown once per user before their first upload.
// Wording: "built following the safeguards of", never "compliant" (CLAUDE.md section 11).
import { useState } from "react";
import { useT } from "../i18n";

export default function ConsentPage({ onAccept, onCancel }) {
  const t = useT();
  const [checked, setChecked] = useState(false);

  return (
    <section className="consent">
      <h1>{t("consent.title")}</h1>
      <p>{t("consent.intro")}</p>
      <ul className="checklist">
        <li>{t("consent.encrypted")}</li>
        <li>{t("consent.deidentify")}</li>
        <li>{t("consent.proof")}</li>
        <li>{t("consent.audit")}</li>
        <li>{t("consent.delete")}</li>
        <li>{t("consent.noAdvice")}</li>
      </ul>
      <p>{t("consent.safeguards")}</p>
      <label className="checkbox">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        {t("consent.agree")}
      </label>
      <p className="actions">
        <button className="btn-primary" onClick={onAccept} disabled={!checked}>
          {t("consent.continue")}
        </button>{" "}
        <button className="btn-ghost" onClick={onCancel}>{t("cancel")}</button>
      </p>
    </section>
  );
}
