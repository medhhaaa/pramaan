// Shown once per user before their first upload.
// Wording: "built following the safeguards of", never "compliant" (CLAUDE.md section 11).
import { useState } from "react";

export default function ConsentPage({ onAccept, onCancel }) {
  const [checked, setChecked] = useState(false);

  return (
    <section className="consent">
      <h1>Before you upload</h1>
      <p>Pramaan reads your medical documents to build a dated timeline. Before you continue:</p>
      <ul className="checklist">
        <li>Your files are stored encrypted, and only people you give access to can see them.</li>
        <li>
          Names, phone numbers, ID numbers, addresses, doctor and hospital names are replaced with
          tokens before any text is sent to the AI. The AI never sees who you are.
        </li>
        <li>Every fact shown links back to the exact line in your document.</li>
        <li>Every view and change is written to an audit log you can read.</li>
        <li>You can delete all your data at any time.</li>
        <li>Pramaan does not diagnose or give treatment or dose advice.</li>
      </ul>
      <p>Built following the safeguards of GDPR, the EU AI Act and India's DPDP Act.</p>
      <label className="checkbox">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />I
        agree to Pramaan processing these documents as described above.
      </label>
      <p className="actions">
        <button className="btn-primary" onClick={onAccept} disabled={!checked}>
          Continue
        </button>{" "}
        <button className="btn-ghost" onClick={onCancel}>Cancel</button>
      </p>
    </section>
  );
}
