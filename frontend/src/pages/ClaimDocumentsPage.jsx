// Claim Documents (patient): documents COMMONLY needed for a reimbursement claim after a
// hospital stay, which ones are already saved in Pramaan, and a reminder to collect the rest.
// No insurer integration and no claim decision: the insurer makes the final decision.
// Wording rule: "commonly needed", "saved", "not saved yet"; never "complete", "eligible",
// "approved", "guaranteed" or a claim deadline (the patient may type their own reminder date).
import { useCallback, useEffect, useState } from "react";
import {
  answerQuestion,
  createHospitalStay,
  downloadClaimPack,
  getClaimChecklist,
  getHospitalStays,
  updateHospitalStay,
} from "../api";
import ProofPanel from "../components/ProofPanel";
import { useT } from "../i18n";

const REFRESH_MS = 15000; // new uploads show up without a reload
const CONDITION_ANSWERS = ["yes", "no", "dont_know"];
const ANSWER_FOR = { true: "yes", false: "no" };

function stayLabel(stay, t) {
  if (!stay.admitted_on && !stay.discharged_on) return t("claims.noDates");
  return t("claims.stayDates", {
    from: stay.admitted_on || t("claims.dateUnknown"),
    to: stay.discharged_on || t("claims.dateUnknown"),
  });
}

// the proof panel wants a fact; a saved document's evidence is the line that shows its type
const proofFor = (doc) => ({
  fact_id: doc.id,
  document_id: doc.id,
  quote: doc.doc_type_quote,
  page: doc.doc_type_page,
  line: doc.doc_type_line,
  quote_verified: true,
});

function ConditionQuestion({ condition, stay, question, onAnswered }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = stay[condition] === null ? null : ANSWER_FOR[stay[condition]];

  async function send(answer) {
    setBusy(true);
    setError("");
    try {
      await answerQuestion(question.id, answer);
      onAnswered();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="claim-question">
      <span>{t(`claims.question.${condition}`)}</span>{" "}
      {CONDITION_ANSWERS.map((a) => (
        <button
          key={a}
          className={current === a ? "btn-primary" : ""}
          onClick={() => send(a)}
          disabled={busy || !question || current === a}
        >
          {t(`answer.${a}`)}
        </button>
      ))}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function StayDates({ patient, stay, onSaved }) {
  const t = useT();
  const [form, setForm] = useState({
    admitted_on: stay.admitted_on || "",
    discharged_on: stay.discharged_on || "",
    my_reminder_date: stay.my_reminder_date || "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await updateHospitalStay(patient.id, stay.id, form);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const field = (key) => (
    <label key={key}>
      {t(`claims.${key === "admitted_on" ? "admitted" : key === "discharged_on" ? "discharged" : "myReminder"}`)}
      <input type="date" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  );

  return (
    <details className="claim-dates">
      <summary>{t("claims.datesTitle")}</summary>
      <form onSubmit={save} className="form">
        {field("admitted_on")}
        {field("discharged_on")}
        {field("my_reminder_date")}
        <p className="hint">{t("claims.myReminderHint")}</p>
        <button type="submit" disabled={busy}>{t("claims.save")}</button>
        {error && <p className="error">{error}</p>}
      </form>
    </details>
  );
}

export default function ClaimDocumentsPage({ patient, user, stayId, onStayChange }) {
  const t = useT();
  const [stays, setStays] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null); // document open in the proof panel
  const [busy, setBusy] = useState(false);

  const loadStays = useCallback(
    () => getHospitalStays(patient.id).then(setStays).catch((err) => setError(err.message)),
    [patient.id],
  );
  useEffect(() => {
    loadStays();
  }, [loadStays]);

  const stay = stays && (stays.find((s) => s.id === stayId) || stays[0]);
  const activeId = stay?.id;

  const loadChecklist = useCallback(() => {
    if (!activeId) return;
    getClaimChecklist(patient.id, activeId)
      .then(setChecklist)
      .catch((err) => setError(err.message));
  }, [patient.id, activeId]);

  useEffect(() => {
    loadChecklist();
    const timer = setInterval(loadChecklist, REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadChecklist, t.lang]);

  async function newStay() {
    setBusy(true);
    setError("");
    try {
      const created = await createHospitalStay(patient.id);
      await loadStays();
      onStayChange(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setBusy(true);
    setError("");
    try {
      const blob = await downloadClaimPack(patient.id, activeId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `claim_pack_stay_${activeId}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function refresh() {
    loadStays();
    loadChecklist();
  }

  if (error && !stays) return <p className="error">{error}</p>;
  if (!stays) return <p>{t("loading")}</p>;

  const isPatient = user.role === "patient";
  const newStayButton = isPatient && (
    <button className="btn-secondary" onClick={newStay} disabled={busy}>
      {t("claims.newStay")}
    </button>
  );

  if (stays.length === 0) {
    return (
      <section>
        <h1>{t("claims.title")}</h1>
        <p className="claim-banner">{t("claims.banner")}</p>
        <p>{t("claims.noStays")}</p>
        {newStayButton}
        {error && <p className="error">{error}</p>}
      </section>
    );
  }

  const ready = checklist && checklist.stay.id === activeId;
  const docLabel = (doc) => t(`claims.doc.${doc}`);

  return (
    <section className={selected ? "with-panel" : ""}>
      <div>
        <h1>{t("claims.title")}</h1>
        <p className="hint">{stayLabel(stay, t)}</p>
        <p className="claim-banner" role="note">
          {t("claims.banner")} {t("claims.finalDecision")}
        </p>
        {error && <p className="error">{error}</p>}
        {!ready && <p>{t("loading")}</p>}

        {ready && (
          <>
            <h2>
              {t("claims.count", {
                saved: checklist.summary.saved_count,
                required: checklist.summary.required_count,
              })}
            </h2>

            {checklist.reminder.show && (
              <p className="claim-reminder" role="status">
                {t("claims.reminder", { list: checklist.reminder.docs.map(docLabel).join(", ") })}
              </p>
            )}
            {checklist.stay.my_reminder_date && (
              <p className="hint">{t("claims.reminderSet", { date: checklist.stay.my_reminder_date })}</p>
            )}

            <ul className="claim-items">
              {checklist.items.map((item) => (
                <li key={item.doc} className={`claim-item claim-${item.status}`}>
                  <div className="claim-item-head">
                    <strong>{docLabel(item.doc)}</strong>{" "}
                    <span className={`chip claim-chip claim-chip-${item.status}`}>
                      {t(`claims.status.${item.status}`)}
                    </span>
                  </div>
                  {item.status === "saved" &&
                    item.documents.map((doc) => (
                      <button key={doc.id} className="link" onClick={() => setSelected(proofFor(doc))}>
                        {doc.filename}
                        {doc.document_date ? ` (${doc.document_date})` : ""}
                      </button>
                    ))}
                  {item.status === "not_saved" && <p className="hint">{t("claims.tipNotSaved")}</p>}
                  {item.when !== "always" && isPatient && (
                    <ConditionQuestion
                      condition={item.when}
                      stay={checklist.stay}
                      question={checklist.condition_questions[item.when]}
                      onAnswered={refresh}
                    />
                  )}
                </li>
              ))}
            </ul>

            <h2>{t("claims.alsoKeep")}</h2>
            <p className="hint">{t("claims.alsoKeepHint")}</p>
            <ul>
              {checklist.also_keep_ready.map((k) => (
                <li key={k.key}>{t(`claims.keep.${k.key}`, null, k.label)}</li>
              ))}
            </ul>

            <p className="actions">
              <button className="btn-primary" onClick={download} disabled={busy || checklist.summary.saved_count === 0}>
                {busy ? t("claims.downloading") : t("claims.download")}
              </button>{" "}
              {newStayButton}
            </p>

            {isPatient && <StayDates key={stay.id} patient={patient} stay={checklist.stay} onSaved={refresh} />}
          </>
        )}

        {stays.length > 1 && (
          <p className="hint">
            {t("claims.otherStays")}{" "}
            {stays
              .filter((s) => s.id !== activeId)
              .map((s) => (
                <button key={s.id} className="link" onClick={() => onStayChange(s.id)}>
                  {stayLabel(s, t)}
                </button>
              ))}
          </p>
        )}
      </div>
      {selected && (
        <ProofPanel key={selected.document_id} fact={selected} onClose={() => setSelected(null)} />
      )}
    </section>
  );
}
